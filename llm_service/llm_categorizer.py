import os
import json
import logging
from typing import Dict, Optional
import pandas as pd
import anthropic
from datetime import datetime
from data_manager import DataManager
from config import CATEGORY_MAPPING
from transaction_types import Transaction
import time

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
            df = self.data_manager.read_all()
            
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
    
    def _format_transaction_context(self, transaction: Transaction) -> str:
        """Format transaction data into a context string for the LLM"""
        # Extract key fields with fallbacks
        date = transaction.date or 'Unknown'
        name = transaction.name or ''
        original_description = transaction.original_description or ''
        merchant_name = transaction.merchant_name or ''
        amount = transaction.amount or 0
        bank_name = transaction.bank_name or ''
        location = transaction.location or ''
        payment_details = transaction.payment_details or ''
        
        # Format Plaid categories
        plaid_categories = []
        if transaction.personal_finance_category:
            plaid_categories.append(f"Primary: {transaction.personal_finance_category}")
        if transaction.personal_finance_category_detailed:
            plaid_categories.append(f"Detailed: {transaction.personal_finance_category_detailed}")
        if transaction.category:
            plaid_categories.append(f"General: {transaction.category}")
        
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
            self.logger.info(f"Raw LLM response: '{response_text}'")
            
            # Handle case where response might have additional text around JSON
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx != -1 and end_idx != 0:
                json_str = response_text[start_idx:end_idx]
                self.logger.info(f"Extracted JSON string: '{json_str}'")
                
                try:
                    result = json.loads(json_str)
                    self.logger.info(f"Parsed JSON result: {result}")
                except json.JSONDecodeError as json_err:
                    self.logger.error(f"JSON decode error: {json_err}")
                    self.logger.error(f"Failed to parse JSON: '{json_str}'")
                    raise ValueError(f"Invalid JSON format: {json_err}")
                
                # Validate required fields
                if 'category' not in result or 'reasoning' not in result:
                    self.logger.error(f"Missing required fields. Result keys: {list(result.keys())}")
                    raise ValueError("Missing required fields in LLM response")
                
                # Create list of all valid categories (values from CATEGORY_MAPPING)
                valid_categories = []
                for category_list in CATEGORY_MAPPING.values():
                    valid_categories.extend(category_list)
                
                # Validate category is in our mapping - must match exactly
                if result['category'] not in valid_categories:
                    self.logger.error(f"Invalid category '{result['category']}' not in valid list")
                    raise ValueError(f"LLM returned invalid category: '{result['category']}'. Must be one of: {valid_categories}")
                
                return result
                
            else:
                self.logger.error(f"No JSON braces found in response: '{response_text}'")
                raise ValueError("No valid JSON found in response")
                
        except Exception as e:
            self.logger.error(f"Error parsing LLM response: {str(e)}")
            self.logger.error(f"Full response was: '{response_text}'")
            self.logger.error(f"Exception type: {type(e).__name__}")
            self.logger.error(f"Exception args: {e.args}")
            raise e
    
    def categorize_transaction(self, transaction: Transaction) -> Dict:
        """Main method to categorize a transaction using Claude API
        
        Args:
            transaction: Transaction object to categorize
            
        Returns:
            Dict with 'category' and 'reasoning' keys, or 'error' key if failed
        """
        # Format context for LLM
        prompt = self._format_transaction_context(transaction)
        print(f"proimpt {prompt}")
        time.sleep(1.0)
        # Call Claude API
        message = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=0.1,
            messages=[{"role": "user", "content": prompt}]
        )
        print(f"-------------- {message}")
        # Parse and return response
        response_text = message.content[0].text

        print(f"response_text {response_text}")

        return self._parse_llm_response(response_text)
    
    def categorize_transaction_by_id(self, transaction_id: str) -> Dict:
        """Legacy method that reads transaction from disk - DEPRECATED
        
        Use categorize_transaction() with Transaction object instead for better performance
        """
        self.logger.warning("categorize_transaction_by_id is deprecated - pass Transaction object directly")
        
        # Get transaction data
        transaction_dict = self.get_transaction_by_id(transaction_id)
        if not transaction_dict:
            return {"error": f"Transaction {transaction_id} not found"}
        
        # Convert to Transaction object
        transaction = Transaction.from_dict(transaction_dict)
        return self.categorize_transaction(transaction)
