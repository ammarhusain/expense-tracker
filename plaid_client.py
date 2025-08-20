from plaid.api import plaid_api
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.model.transactions_sync_response import TransactionsSyncResponse
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.link_token_transactions import LinkTokenTransactions
from plaid.model.country_code import CountryCode
from plaid.model.products import Products
from plaid.configuration import Configuration
from plaid.api_client import ApiClient
from plaid import ApiException
from typing import List, Dict, Optional
import logging
import json
import os
from datetime import datetime
from config import config

def safe_str(value):
    """Safely convert any value to string, handling enums"""
    if hasattr(value, 'value'):
        return str(value.value)
    return str(value) if value is not None else None

def safe_date(value):
    """Safely convert date objects to ISO string"""
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value) if value is not None else None

class PlaidClient:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Create debug directory if it doesn't exist
        self.debug_dir = os.path.join(os.getcwd(), 'debug')
        os.makedirs(self.debug_dir, exist_ok=True)
        
        configuration = Configuration(
            host=self._get_plaid_host(),
            api_key={
                'clientId': config.plaid_client_id,
                'secret': config.plaid_secret,
            }
        )
        api_client = ApiClient(configuration)
        self.client = plaid_api.PlaidApi(api_client)
        
    def _log_api_response(self, endpoint: str, response, access_token: str = None):
        """Log raw API response to debug directory"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Mask access token for security
            token_suffix = access_token[-4:] if access_token else "unknown"
            filename = f"{endpoint}_{timestamp}_{token_suffix}.json"
            filepath = os.path.join(self.debug_dir, filename)
            
            # Convert response to dict safely
            try:
                if hasattr(response, 'to_dict'):
                    response_dict = response.to_dict()
                    response_str = json.dumps(response_dict, indent=2, default=str)
                else:
                    response_str = f"Response type: {type(response)}\nResponse content: {str(response)}"
            except Exception as e:
                response_str = f"Could not serialize response: {e}"
            
            with open(filepath, 'w') as f:
                f.write(response_str)
            
            self.logger.info(f"API response logged to: {filepath}")
            
        except Exception as e:
            self.logger.error(f"Failed to log API response: {e}")
            # Don't let logging errors break the actual sync
            pass

    def _get_plaid_host(self):
        env_to_host = {
            'sandbox': 'https://sandbox.plaid.com',
            'development': 'https://development.plaid.com',
            'production': 'https://production.plaid.com'
        }
        return env_to_host.get(config.plaid_env, 'https://sandbox.plaid.com')
    
    def create_link_token(self, user_id: str) -> str:
        try:
            # Create base request with transactions configuration
            request = LinkTokenCreateRequest(
                products=[Products('transactions')],
                client_name="Personal Finance Tracker",
                country_codes=[CountryCode('US')],
                language='en',
                user=LinkTokenCreateRequestUser(client_user_id=user_id),
                transactions=LinkTokenTransactions(
                    days_requested=730  # Request 24 months (730 days) of transaction history
                )
            )
            
            # Note: redirect_uri only needed for OAuth institutions in production
            # and must be configured in Plaid dashboard first
            
            response = self.client.link_token_create(request)
            response_dict = response.to_dict() if hasattr(response, 'to_dict') else response
            return response_dict['link_token']
            
        except ApiException as e:
            self.logger.error(f"Plaid API error in create_link_token: {e}")
            raise
    
    def exchange_public_token(self, public_token: str) -> str:
        try:
            request = ItemPublicTokenExchangeRequest(
                public_token=public_token
            )
            
            response = self.client.item_public_token_exchange(request)
            response_dict = response.to_dict() if hasattr(response, 'to_dict') else response
            return response_dict['access_token']
            
        except ApiException as e:
            self.logger.error(f"Plaid API error in exchange_public_token: {e}")
            raise
    
    def get_accounts(self, access_token: str) -> List[Dict]:
        try:
            request = AccountsGetRequest(access_token=access_token)
            response = self.client.accounts_get(request)
            response_dict = response.to_dict() if hasattr(response, 'to_dict') else response
            
            accounts = []
            for account in response_dict.get('accounts', []):
                accounts.append({
                    'account_id': account.get('account_id'),
                    'name': account.get('name'),
                    'official_name': account.get('official_name'),
                    'type': safe_str(account.get('type')),
                    'subtype': safe_str(account.get('subtype')),
                    'mask': account.get('mask'),
                    'balance_current': account.get('balances', {}).get('current'),
                    'balance_available': account.get('balances', {}).get('available'),
                    'balance_limit': account.get('balances', {}).get('limit'),
                    'currency_code': account.get('balances', {}).get('iso_currency_code', 'USD')
                })
            
            return accounts
            
        except ApiException as e:
            self.logger.error(f"Plaid API error in get_accounts: {e}")
            raise
    
    def _format_plaid_category_string(self, transaction: Dict) -> str:
        """Format Plaid category data into structured string."""
        parts = []
        
        # Add legacy categories if present
        category = transaction.get('category', [None])[0] if transaction.get('category') else None
        category_detailed = ' > '.join(transaction.get('category', [])) if transaction.get('category') else None
        if category:
            parts.append(f"leg_cgr: {category}")
        if category_detailed:
            parts.append(f"leg_det: {category_detailed}")
        
        # Add personal finance categories if present
        pf_data = transaction.get('personal_finance_category', {})
        pf_category = pf_data.get('primary') if pf_data else None
        pf_detailed = pf_data.get('detailed') if pf_data else None
        pf_confidence = pf_data.get('confidence_level') if pf_data else None
        
        if pf_category:
            parts.append(f"cgr: {pf_category}")
        if pf_detailed:
            parts.append(f"det: {pf_detailed}")
        if pf_confidence:
            parts.append(f"cnf: {pf_confidence}")
        
        return ", ".join(parts) if parts else ""
    
    def _format_transaction(self, transaction) -> Dict:
        """Format a single transaction object into our standard format"""
        # Convert transaction to dict if it's an object
        if hasattr(transaction, 'to_dict'):
            transaction = transaction.to_dict()
        
        # Extract location data if available and combine into single field
        location_parts = []
        if transaction.get('location'):
            location = transaction['location']
            if location.get('address'):
                location_parts.append(location.get('address'))
            if location.get('city'):
                location_parts.append(location.get('city'))
            if location.get('region'):
                location_parts.append(location.get('region'))
            if location.get('postal_code'):
                location_parts.append(location.get('postal_code'))
            if location.get('country'):
                location_parts.append(location.get('country'))
            # Add coordinates with lat/lon prefixes
            if location.get('lat') and location.get('lon'):
                location_parts.append(f"lat {location.get('lat')} lon {location.get('lon')}")
            if location.get('store_number'):
                location_parts.append(f"Store #{location.get('store_number')}")
        
        location_string = ', '.join(location_parts) if location_parts else None
        
        # Extract and combine payment meta into single field
        payment_details_parts = []
        if transaction.get('payment_meta'):
            pm = transaction['payment_meta']
            if pm.get('reference_number'):
                payment_details_parts.append(f"Ref: {pm.get('reference_number')}")
            if pm.get('payee'):
                payment_details_parts.append(f"Payee: {pm.get('payee')}")
            if pm.get('payer'):
                payment_details_parts.append(f"Payer: {pm.get('payer')}")
            if pm.get('payment_method'):
                payment_details_parts.append(f"Method: {pm.get('payment_method')}")
        
        payment_details = ', '.join(payment_details_parts) if payment_details_parts else None
        
        # Return only the columns defined in data_manager.py
        return {
            # Core fields from data_manager
            'date': safe_date(transaction.get('date')),
            'name': transaction.get('name'),
            'merchant_name': transaction.get('merchant_name'),
            'original_description': transaction.get('original_description'),
            'amount': transaction.get('amount'),
            'plaid_category': self._format_plaid_category_string(transaction),
            'transaction_type': safe_str(transaction.get('transaction_type')),
            'currency': transaction.get('iso_currency_code', 'USD'),
            'pending': transaction.get('pending', False),
            'account_owner': transaction.get('account_owner'),
            'location': location_string,
            'payment_details': payment_details,
            'website': transaction.get('website'),
            'notes': None,  # For user notes
            'tags': None,   # For user tags
            # These will be added by sync_service
            'bank_name': None,  
            'account_name': None,
            'created_at': None,  # Added by data_manager
            'transaction_id': transaction.get('transaction_id'),
            'account_id': transaction.get('account_id'),
            'check_number': transaction.get('check_number')
        }

    def transactions_sync(self, access_token: str, cursor: Optional[str] = None) -> Dict:
        """
        Sync transactions using Plaid's sync API with cursor-based pagination.
        Automatically handles pagination to fetch ALL available transactions.
        
        Args:
            access_token: The access token for the account
            cursor: The sync cursor from previous sync (None for initial sync)
            
        Returns:
            Dict containing:
            - transactions: List of ALL formatted transactions (from all pages)
            - added: Total number of added transactions (across all pages)
            - modified: Total number of modified transactions (across all pages)
            - removed: List of removed transaction IDs (from all pages)
            - next_cursor: Final cursor for next sync
            - pages_fetched: Number of API calls made
        """
        print(f"Transaction sync called - access_token:{access_token}, cursor: {cursor[:20] if cursor else 'None'}")
        
        # Accumulators for all pages
        all_formatted_transactions = []
        total_added = 0
        total_modified = 0
        all_removed = []
        final_cursor = cursor
        pages_fetched = 0
        
        try:
            # Keep fetching until has_more is False
            current_cursor = cursor
            
            while True:
                pages_fetched += 1
                print(f"Fetching page {pages_fetched}, cursor: {current_cursor[:20] if current_cursor else 'None'}")
                
                request_params = {
                    'access_token': access_token
                }
                
                if current_cursor:
                    request_params['cursor'] = current_cursor
                    
                request = TransactionsSyncRequest(**request_params)
                response = self.client.transactions_sync(request)
                
                # Log the raw API response for debugging
                self._log_api_response(f"transactions_sync_page_{pages_fetched}", response, access_token)
                
                # Convert response to dict for easier access
                response_dict = response.to_dict() if hasattr(response, 'to_dict') else response
                
                page_added = len(response_dict.get('added', []))
                page_modified = len(response_dict.get('modified', []))
                has_more = response_dict.get('has_more', False)
                next_cursor = response_dict.get('next_cursor', '')
                
                print(f"Page {pages_fetched} summary: added={page_added}, modified={page_modified}, has_more={has_more}, next_cursor={next_cursor[:20] if next_cursor else 'empty'}")
                
                # Accumulate counters
                total_added += page_added
                total_modified += page_modified
                all_removed.extend(response_dict.get('removed', []))
                final_cursor = next_cursor
                
                # Format and accumulate transactions from this page
                # Process added transactions
                for transaction in response_dict.get('added', []):
                    formatted_transaction = self._format_transaction(transaction)
                    all_formatted_transactions.append(formatted_transaction)
                
                # Process modified transactions
                for transaction in response_dict.get('modified', []):
                    formatted_transaction = self._format_transaction(transaction)
                    all_formatted_transactions.append(formatted_transaction)
                
                # Update cursor for next iteration
                current_cursor = next_cursor
                
                # Break if no more pages
                if not has_more:
                    print(f"Pagination complete after {pages_fetched} pages")
                    break
                
                # Safety check to prevent infinite loops
                if pages_fetched > 50:  # Reasonable limit
                    self.logger.warning(f"Reached maximum page limit ({pages_fetched}) - stopping pagination")
                    break
            
            result = {
                'transactions': all_formatted_transactions,
                'added': total_added,
                'modified': total_modified,
                'removed': all_removed,
                'next_cursor': final_cursor,
                'pages_fetched': pages_fetched
            }
            
            print(f"Final result: transactions={len(result['transactions'])}, total_added={total_added}, total_modified={total_modified}, pages_fetched={pages_fetched}")
            return result
            
        except ApiException as e:
            self.logger.error(f"Plaid API error in transactions_sync (page {pages_fetched}): {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error in transactions_sync (page {pages_fetched}): {e}")
            raise