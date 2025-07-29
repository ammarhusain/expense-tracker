import pandas as pd
import os
from datetime import datetime
from typing import List, Dict, Optional
import logging
from config import config, CATEGORY_MAPPING

class DataManager:
    def __init__(self, csv_path: str = None):
        self.csv_path = csv_path or config.csv_file_path
        self.logger = logging.getLogger(__name__)
        self._ensure_csv_exists()
    
    def _ensure_csv_exists(self):
        """Create CSV file with headers if it doesn't exist"""
        if not os.path.exists(self.csv_path):
            # Define comprehensive CSV columns
            columns = [
                'date', 'authorized_date', 'transaction_id', 'account_id',
                'amount', 'iso_currency_code', 'name', 'original_description',
                'merchant_name', 'merchant_entity_id', 'category', 'category_detailed',
                'category_id', 'transaction_type', 'transaction_code', 'check_number', 'pending',
                'pending_transaction_id', 'account_owner', 'location',
                'payment_reference_number', 'payment_ppd_id', 'payment_payee',
                'payment_by_order_of', 'payment_payer', 'payment_method',
                'payment_processor', 'payment_reason', 'website', 'logo_url',
                'subaccount_id', 'custom_category', 'notes', 'tags', 'bank_name', 'created_at'
            ]
            
            df = pd.DataFrame(columns=columns)
            df.to_csv(self.csv_path, index=False)
            self.logger.info(f"Created new CSV file at {self.csv_path}")
    
    def read_transactions(self) -> pd.DataFrame:
        """Read all transactions from CSV"""
        try:
            df = pd.read_csv(self.csv_path)
            return df
        except Exception as e:
            self.logger.error(f"Error reading CSV: {e}")
            return pd.DataFrame()
    
    def get_existing_transaction_ids(self) -> set:
        """Get set of existing transaction IDs to avoid duplicates"""
        df = self.read_transactions()
        if not df.empty and 'transaction_id' in df.columns:
            return set(df['transaction_id'].dropna().astype(str))
        return set()
    
    def categorize_transaction(self, transaction: Dict) -> str:
        """Apply custom categorization rules"""
        description = ((transaction.get('name') or '') + ' ' + 
                      (transaction.get('original_description') or '') + ' ' +
                      (transaction.get('merchant_name') or '')).lower()
        
        for category, keywords in CATEGORY_MAPPING.items():
            for keyword in keywords:
                if keyword in description:
                    return category
        
        # Use Plaid's category if no custom match
        return transaction.get('category', 'Other')
    
    def find_matching_pending_transaction(self, new_transaction: Dict, existing_df: pd.DataFrame) -> bool:
        """Check if this confirmed transaction matches an existing pending one"""
        if new_transaction.get('pending') or existing_df.empty:
            return False
        
        # Look for pending transactions that match this confirmed one
        pending_mask = existing_df['pending'] == True
        if not pending_mask.any():
            return False
        
        pending_df = existing_df[pending_mask]
        
        # Match criteria: same amount, similar date, same merchant (within 3 days)
        for _, pending_row in pending_df.iterrows():
            # Check amount match
            if abs(float(pending_row['amount']) - float(new_transaction['amount'])) > 0.01:
                continue
            
            # Check merchant match
            pending_merchant = str(pending_row.get('merchant_name', '')).lower()
            new_merchant = str(new_transaction.get('merchant_name', '')).lower()
            pending_name = str(pending_row.get('name', '')).lower()
            new_name = str(new_transaction.get('name', '')).lower()
            
            if (pending_merchant and new_merchant and pending_merchant in new_merchant) or \
               (new_merchant and pending_merchant and new_merchant in pending_merchant) or \
               (pending_name and new_name and pending_name in new_name) or \
               (new_name and pending_name and new_name in pending_name):
                
                # Check date proximity (within 3 days)
                try:
                    import pandas as pd
                    pending_date = pd.to_datetime(pending_row['date'])
                    new_date = pd.to_datetime(new_transaction['date'])
                    date_diff = abs((pending_date - new_date).days)
                    
                    if date_diff <= 3:
                        return True
                except:
                    pass
        
        return False

    def add_transactions(self, transactions: List[Dict]) -> int:
        """Add new transactions to CSV, avoiding duplicates and handling pending->confirmed transitions"""
        if not transactions:
            return 0
        
        existing_df = self.read_transactions()
        existing_ids = self.get_existing_transaction_ids()
        new_transactions = []
        confirmed_replacing_pending = 0
        
        for transaction in transactions:
            transaction_id = str(transaction.get('transaction_id', ''))
            
            if transaction_id not in existing_ids:
                # Check if this confirmed transaction replaces a pending one
                if not transaction.get('pending', False):
                    if self.find_matching_pending_transaction(transaction, existing_df):
                        confirmed_replacing_pending += 1
                        self.logger.info(f"Confirmed transaction found for pending: {transaction.get('name', 'Unknown')} ${transaction.get('amount', 0)}")
                
                # Add custom categorization
                transaction['custom_category'] = self.categorize_transaction(transaction)
                
                # Add timestamp for when we imported this
                transaction['created_at'] = datetime.now().isoformat()
                
                new_transactions.append(transaction)
        
        if new_transactions:
            df_new = pd.DataFrame(new_transactions)
            
            # Combine and save
            df_combined = pd.concat([existing_df, df_new], ignore_index=True)
            
            # Sort by date (newest first)
            if 'date' in df_combined.columns:
                df_combined['date'] = pd.to_datetime(df_combined['date'])
                df_combined = df_combined.sort_values('date', ascending=False)
            
            df_combined.to_csv(self.csv_path, index=False)
            
            log_message = f"Added {len(new_transactions)} new transactions to CSV"
            if confirmed_replacing_pending > 0:
                log_message += f" ({confirmed_replacing_pending} confirmed transactions that replace pending ones)"
            
            self.logger.info(log_message)
        
        return len(new_transactions)
    
    def get_last_sync_date(self) -> Optional[datetime]:
        """Get the date of the most recent transaction for incremental sync"""
        df = self.read_transactions()
        if df.empty or 'date' not in df.columns:
            return None
        
        try:
            df['date'] = pd.to_datetime(df['date'])
            return df['date'].max()
        except Exception as e:
            self.logger.error(f"Error getting last sync date: {e}")
            return None
    
    def cleanup_old_pending_transactions(self, days_old: int = 7) -> int:
        """Remove pending transactions older than specified days (they likely became confirmed)"""
        df = self.read_transactions()
        if df.empty:
            return 0
        
        try:
            # Convert date column and identify old pending transactions
            df['date'] = pd.to_datetime(df['date'])
            cutoff_date = datetime.now() - timedelta(days=days_old)
            
            old_pending_mask = (df['pending'] == True) & (df['date'] < cutoff_date)
            old_pending_count = old_pending_mask.sum()
            
            if old_pending_count > 0:
                # Remove old pending transactions
                df_cleaned = df[~old_pending_mask]
                df_cleaned.to_csv(self.csv_path, index=False)
                
                self.logger.info(f"Cleaned up {old_pending_count} old pending transactions (older than {days_old} days)")
                return old_pending_count
            
        except Exception as e:
            self.logger.error(f"Error cleaning up pending transactions: {e}")
        
        return 0

    def export_summary(self) -> Dict:
        """Generate summary statistics"""
        df = self.read_transactions()
        if df.empty:
            return {"message": "No transactions found"}
        
        summary = {
            "total_transactions": len(df),
            "date_range": {
                "earliest": df['date'].min() if 'date' in df.columns else None,
                "latest": df['date'].max() if 'date' in df.columns else None
            },
            "accounts": df['account_id'].nunique() if 'account_id' in df.columns else 0,
            "total_spending": abs(df[df['amount'] > 0]['amount'].sum()) if 'amount' in df.columns else 0,
            "total_income": abs(df[df['amount'] < 0]['amount'].sum()) if 'amount' in df.columns else 0,
            "categories": df['custom_category'].value_counts().to_dict() if 'custom_category' in df.columns else {}
        }
        
        return summary