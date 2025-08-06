import os
import json
import logging
from typing import Dict, Optional
import pandas as pd
import anthropic
from datetime import datetime
from data_manager import DataManager
from config import CATEGORY_MAPPING


class TransactionLLMCategorizer:
    def __init__(self, api_key: str = None):
        """Initialize the LLM categorizer with Claude API client"""
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("Anthropic API key not found. Set ANTHROPIC_API_KEY environment variable.")
        
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.data_manager = DataManager()
        self.logger = logging.getLogger(__name__)
        
        # Model configuration
        self.model = "claude-sonnet-4-20250514"
        self.max_tokens = 150
        
        # Load prompt template - throw error if not found
        self.prompt_template = self._load_prompt_template()
    
    def _load_prompt_template(self) -> str:
        """Load the categorization prompt template"""
        prompt_path = os.path.join(os.path.dirname(__file__), 'prompts', 'categorization_prompt.md')
        try:
            with open(prompt_path, 'r') as f:
                return f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"Prompt template not found at {prompt_path}. Please create the prompt file.")
    
    def get_transaction_by_id(self, transaction_id: str) -> Optional[Dict]:
        """Extract transaction data by ID from CSV with all metadata"""
        try:
            df = self.data_manager.read_transactions()
            
            if df.empty or 'transaction_id' not in df.columns:
                self.logger.error("No transactions found or transaction_id column missing")
                return None
            
            # Find transaction by ID
            transaction_row = df[df['transaction_id'] == transaction_id]
            
            if transaction_row.empty:
                self.logger.error(f"Transaction with ID {transaction_id} not found")
                return None
            
            # Convert to dict and handle NaN values
            transaction = transaction_row.iloc[0].to_dict()
            
            # Clean up NaN values
            for key, value in transaction.items():
                if pd.isna(value):
                    transaction[key] = ""
            
            return transaction
            
        except Exception as e:
            self.logger.error(f"Error retrieving transaction {transaction_id}: {str(e)}")
            return None
    
    def _format_transaction_context(self, transaction: Dict) -> str:
        """Format transaction data into a context string for the LLM"""
        # Extract key fields with fallbacks
        date = transaction.get('date', 'Unknown')
        name = transaction.get('name', '')
        original_description = transaction.get('original_description', '')
        merchant_name = transaction.get('merchant_name', '')
        amount = transaction.get('amount', 0)
        bank_name = transaction.get('bank_name', '')
        location = transaction.get('location', '')
        payment_details = transaction.get('payment_details', '')
        
        # Format Plaid categories
        plaid_categories = []
        if transaction.get('personal_finance_category'):
            plaid_categories.append(f"Primary: {transaction['personal_finance_category']}")
        if transaction.get('personal_finance_category_detailed'):
            plaid_categories.append(f"Detailed: {transaction['personal_finance_category_detailed']}")
        if transaction.get('category'):
            plaid_categories.append(f"General: {transaction['category']}")
        
        plaid_category_str = '; '.join(plaid_categories) if plaid_categories else "None"
        
        # Fill in the prompt template
        return self.prompt_template.format(
            date=date,
            name=name,
            original_description=original_description,
            merchant_name=merchant_name,
            amount=abs(float(amount)) if amount else 0,
            bank_name=bank_name,
            location=location,
            payment_details=payment_details,
            plaid_categories=plaid_category_str
        )
    
    def _parse_llm_response(self, response_text: str) -> Dict:
        """Parse LLM JSON response and validate format"""
        try:
            # Try to extract JSON from response
            response_text = response_text.strip()
            
            # Handle case where response might have additional text around JSON
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx != -1 and end_idx != 0:
                json_str = response_text[start_idx:end_idx]
                result = json.loads(json_str)
                
                # Validate required fields
                if 'category' not in result or 'reasoning' not in result:
                    raise ValueError("Missing required fields in LLM response")
                
                # Create list of all valid categories (values from CATEGORY_MAPPING)
                valid_categories = []
                for category_list in CATEGORY_MAPPING.values():
                    valid_categories.extend(category_list)
                
                # Validate category is in our mapping - must match exactly
                if result['category'] not in valid_categories:
                    raise ValueError(f"LLM returned invalid category: '{result['category']}'. Must be one of: {valid_categories}")
                
                return result
                
            else:
                raise ValueError("No valid JSON found in response")
                
        except Exception as e:
            self.logger.error(f"Error parsing LLM response: {str(e)}")
            self.logger.error(f"Response was: {response_text}")
            raise e
    
    def categorize_transaction(self, transaction_id: str) -> Dict:
        """Main method to categorize a transaction using Claude API"""
        # Get transaction data
        transaction = self.get_transaction_by_id(transaction_id)
        if not transaction:
            return {"error": f"Transaction {transaction_id} not found"}
        
        # Format context for LLM
        prompt = self._format_transaction_context(transaction)

        # Call Claude API
        message = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=0.1,
            messages=[{"role": "user", "content": prompt}]
        )
        print("--------------")
        # Parse and return response
        response_text = message.content[0].text

        print(f"response_text {response_text}")

        return self._parse_llm_response(response_text)
    
    def update_transaction_category(self, transaction_id: str, category: str, reasoning: str = None) -> bool:
        """Update the transaction category in the database"""
        try:
            df = self.data_manager.read_transactions()
            
            # Find and update the transaction
            mask = df['transaction_id'] == transaction_id
            if not mask.any():
                self.logger.error(f"Transaction {transaction_id} not found for update")
                return False
            
            # Update category
            df.loc[mask, 'ai_category'] = category
            
            # Add reasoning to notes if provided
            if reasoning:
                current_notes = df.loc[mask, 'notes'].iloc[0]
                ai_note = f"AI: {reasoning}"
                
                if pd.isna(current_notes) or current_notes == "":
                    df.loc[mask, 'notes'] = ai_note
                else:
                    df.loc[mask, 'notes'] = f"{current_notes} | {ai_note}"
            
            # Save back to CSV
            df.to_csv(self.data_manager.csv_path, index=False)
            self.logger.info(f"Updated transaction {transaction_id} with category: {category}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error updating transaction {transaction_id}: {str(e)}")
            return False