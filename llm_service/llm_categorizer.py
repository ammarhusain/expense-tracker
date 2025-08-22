import os
import json
import logging
from typing import Dict, Optional
import pandas as pd
import anthropic
from datetime import datetime
import streamlit as st
from config import CATEGORY_DEFINITIONS, create_data_manager
from transaction_types import Transaction
import time

class TransactionLLMCategorizer:
    def __init__(self, api_key: str = None):
        """Initialize the LLM categorizer with Claude API client"""
        # Try to get API key from multiple sources
        if api_key:
            self.api_key = api_key
        elif hasattr(st, 'secrets') and "anthropic" in st.secrets and "api_key" in st.secrets["anthropic"]:
            self.api_key = st.secrets["anthropic"]["api_key"]
        else:
            # Fallback to environment variable
            self.api_key = os.getenv('ANTHROPIC_API_KEY')
        
        if not self.api_key:
            raise ValueError(
                "Anthropic API key not found. "
                "Please add it to Streamlit secrets under [anthropic] api_key "
                "or set ANTHROPIC_API_KEY environment variable."
            )
        
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.data_manager = create_data_manager()  # Use factory pattern
        self.logger = logging.getLogger(__name__)
        
        # Model configuration
        self.model = "claude-sonnet-4-20250514"
        self.max_tokens = 1500
        
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
    
    def _generate_category_section(self) -> str:
        """Generate category section for prompt from CATEGORY_DEFINITIONS"""
        sections = []
        
        for parent, data in CATEGORY_DEFINITIONS.items():
            # Add subcategories with descriptions
            for subcat, desc in data['subcategories'].items():
                sections.append(f"**{subcat}**: {desc}")
            
            # Add empty line between parent categories for readability
            sections.append("")
        
        # Remove the last empty line
        return "\n".join(sections[:-1])

    def _format_transaction_context(self, transaction: Transaction, potential_transfers: list = None) -> str:
        """Format transaction data into a context string for the LLM with optional transfer context"""
        # Extract key fields with fallbacks
        date = transaction.date or 'Unknown'
        name = transaction.name or ''
        original_description = transaction.original_description or ''
        merchant_name = transaction.merchant_name or ''
        amount = transaction.amount or 0
        bank_name = transaction.bank_name or ''
        location = transaction.location or ''
        payment_details = transaction.payment_details or ''
        
        # Use the consolidated plaid_category field and make it human-readable
        plaid_category_str = transaction.plaid_category or "None"
        
        # Replace abbreviations with human-readable labels
        plaid_category_str = plaid_category_str.replace("cgr:", "Category:")
        plaid_category_str = plaid_category_str.replace("det:", "Detailed Category:")
        plaid_category_str = plaid_category_str.replace("cnf:", "Categorization Confidence:")
        plaid_category_str = plaid_category_str.replace("leg_cgr:", "Legacy Category:")
        plaid_category_str = plaid_category_str.replace("leg_det:", "Legacy Detailed Category:")
        
        # Generate dynamic categories section
        categories_section = self._generate_category_section()
        
        # Build the base prompt with dynamic categories
        base_prompt = self.prompt_template.format(
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
        
        # Replace categories placeholder with dynamic content
        base_prompt = base_prompt.replace("{{CATEGORIES}}", categories_section)
        
        # Add transfer detection context if potential matches found
        transfer_context = ""
        if potential_transfers:
            transfer_context += "Potential matching transactions:\n"
            for i, match in enumerate(potential_transfers[:3], 1):  # Show up to 3 matches
                match_amount = match.get('amount', 0)
                match_date = match.get('date', 'Unknown')
                match_bank = match.get('bank_name', 'Unknown')
                match_account = match.get('account_name', 'Unknown')
                match_name = match.get('name', 'Unknown')
                
                # Calculate time difference
                try:
                    from datetime import datetime
                    current_date = datetime.fromisoformat(date)
                    match_date_obj = datetime.fromisoformat(match_date)
                    days_diff = abs((current_date - match_date_obj).days)
                    time_diff = f"{days_diff} days apart" if days_diff > 0 else "same day"
                except:
                    time_diff = "unknown time difference"
                
                transfer_context += f"{i}. ${match_amount:.2f} from {match_bank} ({match_account}) on {match_date}\n"
                transfer_context += f"   Description: {match_name}\n"
                transfer_context += f"   Time difference: {time_diff}\n"
                transfer_context += f"   Same institution: {'Yes' if match_bank == bank_name else 'No'}\n\n"
            
            transfer_context += "If this appears to be a transfer between your own accounts, categorize it as 'transfer'."
            transfer_context += "Consider the timing, amounts, and whether the accounts belong to the same person/institution.\n"
                    
        return base_prompt + transfer_context
    
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
                
                # Create list of all valid categories from CATEGORY_DEFINITIONS
                valid_categories = []
                for category_data in CATEGORY_DEFINITIONS.values():
                    valid_categories.extend(category_data['subcategories'].keys())
                
                # Validate category is in our mapping - must match exactly
                if result['category'] not in valid_categories:
                    self.logger.error(f"Invalid category '{result['category']}' not in valid list")
                    raise ValueError(f"LLM returned invalid category: '{result['category']}'. Must be one of: {valid_categories}")
                print(f"AI category: {result['category']}")
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
    
    def _categorize_with_llm(self, transaction: Transaction, potential_transfers: list = None) -> Dict:
        """Internal method to categorize a transaction using Claude API
        
        Args:
            transaction: Transaction object to categorize
            potential_transfers: List of potential matching transfer transactions
            
        Returns:
            Dict with 'category' and 'reasoning' keys, or raises exception if failed
        """
        # Format context for LLM
        prompt = self._format_transaction_context(transaction, potential_transfers)
        # print(f"prompt {prompt}")
        time.sleep(1.0)
        # Call Claude API
        message = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=0.1,
            messages=[{"role": "user", "content": prompt}],
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search"
            }]
        )

        # print(f"response_msg {message}")

        # Parse and return response - handle both direct text and tool use responses
        if hasattr(message.content[0], 'text'):
            # Direct text response
            response_text = message.content[0].text
        else:
            # Tool use response - find the final text block
            text_blocks = [block for block in message.content if hasattr(block, 'text')]
            if text_blocks:
                response_text = text_blocks[-1].text  # Get the last text response
            else:
                raise ValueError("No text response found in LLM output")

        try:
            return self._parse_llm_response(response_text)
        except Exception as e:
            # If parsing fails, return error category with raw response
            self.logger.error(f"Failed to parse LLM response: {e}")
            return {
                'category': 'error',
                'reasoning': message.content
            }
