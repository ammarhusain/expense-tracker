from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging
import json
import os
import time
from plaid_client import PlaidClient
from data_manager import DataManager
from config import config

def make_json_serializable(obj):
    """Recursively convert objects to JSON-serializable format"""
    if hasattr(obj, 'value'):  # Handle enums
        return str(obj.value)
    elif hasattr(obj, 'isoformat'):  # Handle dates
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: make_json_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [make_json_serializable(item) for item in obj]
    elif obj is None:
        return None
    else:
        return obj

class TransactionSyncService:
    def __init__(self):
        self.plaid_client = PlaidClient()
        self.data_manager = DataManager()
        self.logger = logging.getLogger(__name__)
        self.access_tokens_file = "data/access_tokens.json"
    
    def save_access_token(self, institution_name: str, access_token: str, account_info: Dict):
        """Save access token and account info to local file"""
        # Create data directory if it doesn't exist
        os.makedirs(os.path.dirname(self.access_tokens_file), exist_ok=True)
        
        tokens = self.load_access_tokens()
        
        # Make account_info JSON serializable
        serializable_account_info = make_json_serializable(account_info)
        
        tokens[institution_name] = {
            "access_token": access_token,
            "account_info": serializable_account_info,
            "created_at": datetime.now().isoformat(),
            "last_sync": None  # Track when we last synced
        }
        
        with open(self.access_tokens_file, 'w') as f:
            json.dump(tokens, f, indent=2)
        
        self.logger.info(f"Saved access token for {institution_name}")
    
    def load_access_tokens(self) -> Dict:
        """Load saved access tokens"""
        if not os.path.exists(self.access_tokens_file):
            return {}
        
        try:
            with open(self.access_tokens_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Error loading access tokens: {e}")
            return {}
    
    def can_sync_institution(self, institution_name: str, tokens: Dict) -> tuple[bool, str]:
        """Check if we can sync this institution (rate limiting)"""
        if institution_name not in tokens:
            return False, "Institution not found"
        
        last_sync = tokens[institution_name].get('last_sync')
        if not last_sync:
            return True, "Never synced before"
        
        last_sync_time = datetime.fromisoformat(last_sync)
        time_since_sync = datetime.now() - last_sync_time
        
        # Rate limiting: Allow sync only if more than 5 minutes have passed
        if time_since_sync < timedelta(minutes=5):
            remaining = timedelta(minutes=5) - time_since_sync
            remaining_minutes = int(remaining.total_seconds() / 60)
            return False, f"Rate limited. Try again in {remaining_minutes + 1} minutes."
        
        return True, "OK to sync"
    
    def update_last_sync_time(self, institution_name: str):
        """Update the last sync time for an institution"""
        tokens = self.load_access_tokens()
        if institution_name in tokens:
            tokens[institution_name]['last_sync'] = datetime.now().isoformat()
            with open(self.access_tokens_file, 'w') as f:
                json.dump(tokens, f, indent=2)
    
    def sync_all_accounts(self, days_back: int = 30, force_start_date: datetime = None) -> Dict:
        """Sync transactions from all connected accounts"""
        tokens = self.load_access_tokens()
        if not tokens:
            return {"error": "No bank accounts connected. Please link your accounts first."}
        
        results = {
            "total_new_transactions": 0,
            "accounts_synced": 0,
            "errors": [],
            "account_details": {},
            "rate_limited": []
        }
        
        end_date = datetime.now()
        if force_start_date:
            start_date = force_start_date
        else:
            start_date = self.data_manager.get_last_sync_date() or (end_date - timedelta(days=days_back))
        
        self.logger.info(f"Syncing transactions from {start_date} to {end_date}")
        
        for institution_name, token_data in tokens.items():
            # Check rate limiting
            can_sync, reason = self.can_sync_institution(institution_name, tokens)
            if not can_sync:
                results["rate_limited"].append(f"{institution_name}: {reason}")
                continue
                
            try:
                access_token = token_data["access_token"]
                
                # Add delay between API calls to avoid rate limits
                time.sleep(1)
                
                # Get account info
                accounts = self.plaid_client.get_accounts(access_token)
                
                # Add delay before transactions call
                time.sleep(1)
                
                # Get transactions
                transactions = self.plaid_client.get_transactions(
                    access_token=access_token,
                    start_date=start_date,
                    end_date=end_date
                )
                
                # Add bank identifier to transactions
                for transaction in transactions:
                    transaction['bank_name'] = institution_name
                
                # Save to CSV
                new_count = self.data_manager.add_transactions(transactions)
                
                # Update last sync time
                self.update_last_sync_time(institution_name)
                
                results["total_new_transactions"] += new_count
                results["accounts_synced"] += 1
                results["account_details"][institution_name] = {
                    "accounts": len(accounts),
                    "new_transactions": new_count,
                    "total_transactions_fetched": len(transactions)
                }
                
                self.logger.info(f"Synced {new_count} new transactions from {institution_name}")
                
            except Exception as e:
                error_msg = f"Error syncing {institution_name}: {str(e)}"
                self.logger.error(error_msg)
                results["errors"].append(error_msg)
        
        # Add rate limiting info to results
        if results["rate_limited"]:
            results["info"] = "Some accounts were rate limited. " + "; ".join(results["rate_limited"])
        
        return results
    
    def sync_specific_account(self, institution_name: str, days_back: int = 30, force_start_date: datetime = None) -> Dict:
        """Sync transactions from a specific account"""
        tokens = self.load_access_tokens()
        
        if institution_name not in tokens:
            return {"error": f"No access token found for {institution_name}"}
        
        try:
            access_token = tokens[institution_name]["access_token"]
            
            end_date = datetime.now()
            if force_start_date:
                start_date = force_start_date
            else:
                start_date = self.data_manager.get_last_sync_date() or (end_date - timedelta(days=days_back))
            
            # Get transactions
            transactions = self.plaid_client.get_transactions(
                access_token=access_token,
                start_date=start_date,
                end_date=end_date
            )
            
            # Add bank identifier
            for transaction in transactions:
                transaction['bank_name'] = institution_name
            
            # Save to CSV
            new_count = self.data_manager.add_transactions(transactions)
            
            return {
                "institution": institution_name,
                "new_transactions": new_count,
                "total_transactions_fetched": len(transactions),
                "date_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                }
            }
            
        except Exception as e:
            return {"error": f"Error syncing {institution_name}: {str(e)}"}
    
    def get_connected_accounts(self) -> Dict:
        """Get info about all connected accounts"""
        tokens = self.load_access_tokens()
        if not tokens:
            return {"message": "No accounts connected"}
        
        accounts_info = {}
        
        for institution_name, token_data in tokens.items():
            try:
                access_token = token_data["access_token"]
                accounts = self.plaid_client.get_accounts(access_token)
                
                accounts_info[institution_name] = {
                    "connected_at": token_data.get("created_at"),
                    "accounts": [
                        {
                            "name": acc["name"],
                            "type": acc["type"],
                            "subtype": acc["subtype"],
                            "balance": acc["balance_current"]
                        }
                        for acc in accounts
                    ]
                }
                
            except Exception as e:
                accounts_info[institution_name] = {
                    "error": f"Error fetching account info: {str(e)}"
                }
        
        return accounts_info
    
    def sync_historical_transactions(self, months_back: int = 24) -> Dict:
        """Sync historical transactions going back specified months"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=months_back * 30)  # Approximate months to days
        
        self.logger.info(f"Starting historical sync from {start_date.date()} to {end_date.date()}")
        
        return self.sync_all_accounts(force_start_date=start_date)