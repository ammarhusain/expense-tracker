from plaid.api import plaid_api
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.country_code import CountryCode
from plaid.model.products import Products
from plaid.configuration import Configuration
from plaid.api_client import ApiClient
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging
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
        
        configuration = Configuration(
            host=self._get_plaid_host(),
            api_key={
                'clientId': config.plaid_client_id,
                'secret': config.plaid_secret,
            }
        )
        api_client = ApiClient(configuration)
        self.client = plaid_api.PlaidApi(api_client)
        
    def _get_plaid_host(self):
        env_to_host = {
            'sandbox': 'https://sandbox.plaid.com',
            'development': 'https://development.plaid.com',
            'production': 'https://production.plaid.com'
        }
        return env_to_host.get(config.plaid_env, 'https://sandbox.plaid.com')
    
    def create_link_token(self, user_id: str) -> str:
        request = LinkTokenCreateRequest(
            products=[Products('transactions')],
            client_name="Personal Finance Tracker",
            country_codes=[CountryCode('US')],
            language='en',
            user=LinkTokenCreateRequestUser(client_user_id=user_id)
        )
        
        # Add redirect URI for production environment
        if config.plaid_env == 'production':
            request.redirect_uri = 'http://localhost:8501'
        
        response = self.client.link_token_create(request)
        return response['link_token']
    
    def exchange_public_token(self, public_token: str) -> str:
        request = ItemPublicTokenExchangeRequest(
            public_token=public_token
        )
        
        response = self.client.item_public_token_exchange(request)
        return response['access_token']
    
    def get_accounts(self, access_token: str) -> List[Dict]:
        request = AccountsGetRequest(access_token=access_token)
        response = self.client.accounts_get(request)
        
        accounts = []
        for account in response['accounts']:
            accounts.append({
                'account_id': account['account_id'],
                'name': account['name'],
                'official_name': account.get('official_name'),
                'type': safe_str(account['type']),
                'subtype': safe_str(account['subtype']),
                'mask': account.get('mask'),
                'balance_current': account['balances']['current'],
                'balance_available': account['balances'].get('available'),
                'balance_limit': account['balances'].get('limit'),
                'currency_code': account['balances'].get('iso_currency_code', 'USD')
            })
        
        return accounts
    
    def get_transactions(self, access_token: str, start_date: datetime, 
                        end_date: datetime, account_ids: Optional[List[str]] = None) -> List[Dict]:
        request_params = {
            'access_token': access_token,
            'start_date': start_date.date(),
            'end_date': end_date.date()
        }
        
        if account_ids:
            request_params['account_ids'] = account_ids
            
        request = TransactionsGetRequest(**request_params)
        
        response = self.client.transactions_get(request)
        total_transactions = response['total_transactions']
        transactions = response['transactions']
        
        # Handle pagination for large transaction sets
        while len(transactions) < total_transactions:
            request_params = {
                'access_token': access_token,
                'start_date': start_date.date(),
                'end_date': end_date.date(),
                'offset': len(transactions)
            }
            
            if account_ids:
                request_params['account_ids'] = account_ids
                
            request = TransactionsGetRequest(**request_params)
            response = self.client.transactions_get(request)
            transactions.extend(response['transactions'])
        
        formatted_transactions = []
        
        for i, transaction in enumerate(transactions):
            # Extract location data if available and combine into single field
            location_parts = []
            if hasattr(transaction, 'location') and transaction.location:
                location = transaction.location
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
            
            # Extract payment meta if available
            payment_meta = {}
            if hasattr(transaction, 'payment_meta') and transaction.payment_meta:
                payment_meta = {
                    'reference_number': transaction.payment_meta.get('reference_number'),
                    'ppd_id': transaction.payment_meta.get('ppd_id'),
                    'payee': transaction.payment_meta.get('payee'),
                    'by_order_of': transaction.payment_meta.get('by_order_of'),
                    'payer': transaction.payment_meta.get('payer'),
                    'payment_method': transaction.payment_meta.get('payment_method'),
                    'payment_processor': transaction.payment_meta.get('payment_processor'),
                    'reason': transaction.payment_meta.get('reason')
                }
            
            formatted_transaction = {
                # Core transaction data
                'transaction_id': transaction['transaction_id'],
                'account_id': transaction['account_id'],
                'amount': transaction['amount'],  # Positive = money out, Negative = money in
                'iso_currency_code': transaction.get('iso_currency_code', 'USD'),
                'unofficial_currency_code': transaction.get('unofficial_currency_code'),
                
                # Date information
                'date': safe_date(transaction['date']),
                'authorized_date': safe_date(transaction.get('authorized_date')),
                
                # Transaction identifiers and descriptions
                'name': transaction['name'],  # Primary transaction description
                'original_description': transaction.get('original_description'),  # Raw bank description
                'merchant_name': transaction.get('merchant_name'),
                'merchant_entity_id': transaction.get('merchant_entity_id'),
                
                # Categorization - prefer personal_finance_category over legacy category
                'category': (transaction.get('personal_finance_category', {}).get('primary') if transaction.get('personal_finance_category') 
                           else transaction['category'][0] if transaction.get('category') 
                           else 'Other'),
                'category_detailed': (transaction.get('personal_finance_category', {}).get('detailed') if transaction.get('personal_finance_category')
                                    else ' > '.join(transaction['category']) if transaction.get('category')
                                    else 'Other'),
                
                # Transaction metadata
                'transaction_type': safe_str(transaction.get('transaction_type')),
                'transaction_code': safe_str(transaction.get('transaction_code')),
                'check_number': transaction.get('check_number'),
                'pending': transaction.get('pending', False),
                'pending_transaction_id': transaction.get('pending_transaction_id'),
                'account_owner': transaction.get('account_owner'),
                
                # Combined location data
                'location': location_string,
                
                # Payment metadata (flattened for CSV)
                'payment_reference_number': payment_meta.get('reference_number'),
                'payment_ppd_id': payment_meta.get('ppd_id'),
                'payment_payee': payment_meta.get('payee'),
                'payment_by_order_of': payment_meta.get('by_order_of'),
                'payment_payer': payment_meta.get('payer'),
                'payment_method': payment_meta.get('payment_method'),
                'payment_processor': payment_meta.get('payment_processor'),
                'payment_reason': payment_meta.get('reason'),
                
                # Additional fields that might be useful
                'website': transaction.get('website'),
                'logo_url': transaction.get('logo_url'),
                'subaccount_id': transaction.get('subaccount_id'),
                
                # Custom fields for our categorization
                'custom_category': None,  # For manual overrides
                'notes': None,  # For user notes
                'tags': None   # For user tags
            }
            
            formatted_transactions.append(formatted_transaction)
        
        return formatted_transactions
    
    def transactions_sync(self, access_token: str, cursor: Optional[str] = None) -> Dict:
        """
        Sync transactions using Plaid's sync API with cursor-based pagination
        
        Args:
            access_token: The access token for the account
            cursor: The sync cursor from previous sync (None for initial sync)
            
        Returns:
            Dict containing:
            - transactions: List of formatted transactions
            - added: Number of added transactions
            - modified: Number of modified transactions  
            - removed: List of removed transaction IDs
            - next_cursor: Cursor for next sync
            - has_more: Boolean indicating if more data available
        """
        request_params = {
            'access_token': access_token
        }
        
        if cursor:
            request_params['cursor'] = cursor
            
        request = TransactionsSyncRequest(**request_params)
        response = self.client.transactions_sync(request)
        
        # Format the transactions using the same logic as get_transactions
        formatted_transactions = []
        
        for transaction in response['added']:
            # Extract location data if available and combine into single field
            location_parts = []
            if hasattr(transaction, 'location') and transaction.location:
                location = transaction.location
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
            
            # Extract payment meta if available
            payment_meta = {}
            if hasattr(transaction, 'payment_meta') and transaction.payment_meta:
                payment_meta = {
                    'reference_number': transaction.payment_meta.get('reference_number'),
                    'ppd_id': transaction.payment_meta.get('ppd_id'),
                    'payee': transaction.payment_meta.get('payee'),
                    'by_order_of': transaction.payment_meta.get('by_order_of'),
                    'payer': transaction.payment_meta.get('payer'),
                    'payment_method': transaction.payment_meta.get('payment_method'),
                    'payment_processor': transaction.payment_meta.get('payment_processor'),
                    'reason': transaction.payment_meta.get('reason')
                }
            
            formatted_transaction = {
                # Core transaction data
                'transaction_id': transaction['transaction_id'],
                'account_id': transaction['account_id'],
                'amount': transaction['amount'],  # Positive = money out, Negative = money in
                'iso_currency_code': transaction.get('iso_currency_code', 'USD'),
                'unofficial_currency_code': transaction.get('unofficial_currency_code'),
                
                # Date information
                'date': safe_date(transaction['date']),
                'authorized_date': safe_date(transaction.get('authorized_date')),
                
                # Transaction identifiers and descriptions
                'name': transaction['name'],  # Primary transaction description
                'original_description': transaction.get('original_description'),  # Raw bank description
                'merchant_name': transaction.get('merchant_name'),
                'merchant_entity_id': transaction.get('merchant_entity_id'),
                
                # Categorization - prefer personal_finance_category over legacy category
                'category': (transaction.get('personal_finance_category', {}).get('primary') if transaction.get('personal_finance_category') 
                           else transaction['category'][0] if transaction.get('category') 
                           else 'Other'),
                'category_detailed': (transaction.get('personal_finance_category', {}).get('detailed') if transaction.get('personal_finance_category')
                                    else ' > '.join(transaction['category']) if transaction.get('category')
                                    else 'Other'),
                
                # Transaction metadata
                'transaction_type': safe_str(transaction.get('transaction_type')),
                'transaction_code': safe_str(transaction.get('transaction_code')),
                'check_number': transaction.get('check_number'),
                'pending': transaction.get('pending', False),
                'pending_transaction_id': transaction.get('pending_transaction_id'),
                'account_owner': transaction.get('account_owner'),
                
                # Combined location data
                'location': location_string,
                
                # Payment metadata (flattened for CSV)
                'payment_reference_number': payment_meta.get('reference_number'),
                'payment_ppd_id': payment_meta.get('ppd_id'),
                'payment_payee': payment_meta.get('payee'),
                'payment_by_order_of': payment_meta.get('by_order_of'),
                'payment_payer': payment_meta.get('payer'),
                'payment_method': payment_meta.get('payment_method'),
                'payment_processor': payment_meta.get('payment_processor'),
                'payment_reason': payment_meta.get('reason'),
                
                # Additional fields that might be useful
                'website': transaction.get('website'),
                'logo_url': transaction.get('logo_url'),
                'subaccount_id': transaction.get('subaccount_id'),
                
                # Custom fields for our categorization
                'custom_category': None,  # For manual overrides
                'notes': None,  # For user notes
                'tags': None   # For user tags
            }
            
            formatted_transactions.append(formatted_transaction)
        
        # Handle modified transactions (same format)
        # For now, we'll include modified transactions in the main transactions array
        # since the sync_service expects them there
        
        for transaction in response['modified']:
            # Extract location data if available and combine into single field
            location_parts = []
            if hasattr(transaction, 'location') and transaction.location:
                location = transaction.location
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
            
            # Extract payment meta if available
            payment_meta = {}
            if hasattr(transaction, 'payment_meta') and transaction.payment_meta:
                payment_meta = {
                    'reference_number': transaction.payment_meta.get('reference_number'),
                    'ppd_id': transaction.payment_meta.get('ppd_id'),
                    'payee': transaction.payment_meta.get('payee'),
                    'by_order_of': transaction.payment_meta.get('by_order_of'),
                    'payer': transaction.payment_meta.get('payer'),
                    'payment_method': transaction.payment_meta.get('payment_method'),
                    'payment_processor': transaction.payment_meta.get('payment_processor'),
                    'reason': transaction.payment_meta.get('reason')
                }
            
            formatted_transaction = {
                # Core transaction data
                'transaction_id': transaction['transaction_id'],
                'account_id': transaction['account_id'],
                'amount': transaction['amount'],  # Positive = money out, Negative = money in
                'iso_currency_code': transaction.get('iso_currency_code', 'USD'),
                'unofficial_currency_code': transaction.get('unofficial_currency_code'),
                
                # Date information
                'date': safe_date(transaction['date']),
                'authorized_date': safe_date(transaction.get('authorized_date')),
                
                # Transaction identifiers and descriptions
                'name': transaction['name'],  # Primary transaction description
                'original_description': transaction.get('original_description'),  # Raw bank description
                'merchant_name': transaction.get('merchant_name'),
                'merchant_entity_id': transaction.get('merchant_entity_id'),
                
                # Categorization - prefer personal_finance_category over legacy category
                'category': (transaction.get('personal_finance_category', {}).get('primary') if transaction.get('personal_finance_category') 
                           else transaction['category'][0] if transaction.get('category') 
                           else 'Other'),
                'category_detailed': (transaction.get('personal_finance_category', {}).get('detailed') if transaction.get('personal_finance_category')
                                    else ' > '.join(transaction['category']) if transaction.get('category')
                                    else 'Other'),
                
                # Transaction metadata
                'transaction_type': safe_str(transaction.get('transaction_type')),
                'transaction_code': safe_str(transaction.get('transaction_code')),
                'check_number': transaction.get('check_number'),
                'pending': transaction.get('pending', False),
                'pending_transaction_id': transaction.get('pending_transaction_id'),
                'account_owner': transaction.get('account_owner'),
                
                # Combined location data
                'location': location_string,
                
                # Payment metadata (flattened for CSV)
                'payment_reference_number': payment_meta.get('reference_number'),
                'payment_ppd_id': payment_meta.get('ppd_id'),
                'payment_payee': payment_meta.get('payee'),
                'payment_by_order_of': payment_meta.get('by_order_of'),
                'payment_payer': payment_meta.get('payer'),
                'payment_method': payment_meta.get('payment_method'),
                'payment_processor': payment_meta.get('payment_processor'),
                'payment_reason': payment_meta.get('reason'),
                
                # Additional fields that might be useful
                'website': transaction.get('website'),
                'logo_url': transaction.get('logo_url'),
                'subaccount_id': transaction.get('subaccount_id'),
                
                # Custom fields for our categorization
                'custom_category': None,  # For manual overrides
                'notes': None,  # For user notes
                'tags': None   # For user tags
            }
            
            formatted_transactions.append(formatted_transaction)
        
        return {
            'transactions': formatted_transactions,
            'added': len(response['added']),
            'modified': len(response['modified']),
            'removed': response['removed'],
            'next_cursor': response['next_cursor'],
            'has_more': response['has_more']
        }