import pandas as pd
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import logging
from config import config
from transaction_types import TransactionFilters

class DataManager:
    """
    Pure data access layer - handles CSV/database operations only.
    No business logic, just CRUD operations.
    """
    
    def __init__(self, csv_path: str = None):
        """Initialize with storage path."""
        self.csv_path = csv_path or config.csv_file_path
        self.logger = logging.getLogger(__name__)
        self._ensure_csv_exists()
    
    def _ensure_csv_exists(self):
        """Create CSV file with headers if it doesn't exist."""
        if not os.path.exists(self.csv_path):
            # Define comprehensive CSV columns
            columns = [
                'date', 'name', 'merchant_name', 'original_description', 
                'amount','category', 'category_detailed',
                'personal_finance_category', 'personal_finance_category_detailed', 'personal_finance_category_confidence',
                'transaction_type', 'currency', 'pending', 'account_owner',
                'location', 'payment_details', 'website',
                'ai_category', 'ai_reason', 'notes', 'tags', 'bank_name', 'account_name', 'created_at', 'transaction_id', 'account_id', 'check_number'
            ]
            
            df = pd.DataFrame(columns=columns)
            df.to_csv(self.csv_path, index=False)
            self.logger.info(f"Created new CSV file at {self.csv_path}")
    
    # READ operations
    def read_all(self) -> pd.DataFrame:
        """Read all transactions from storage."""
        try:
            df = pd.read_csv(self.csv_path)
            return df
        except Exception as e:
            self.logger.error(f"Error reading CSV: {e}")
            return pd.DataFrame()
    
    def read_by_id(self, transaction_id: str) -> Optional[Dict]:
        """Read single transaction by ID."""
        try:
            df = self.read_all()
            if df.empty or 'transaction_id' not in df.columns:
                return None
            
            transaction_row = df[df['transaction_id'] == transaction_id]
            if transaction_row.empty:
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
    
    def read_by_date_range(self, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """Read transactions within date range."""
        df = self.read_all()
        if df.empty or 'date' not in df.columns:
            return pd.DataFrame()
        
        try:
            df['date'] = pd.to_datetime(df['date'])
            return df[(df['date'] >= start_date) & (df['date'] <= end_date)]
        except Exception as e:
            self.logger.error(f"Error filtering by date range: {e}")
            return pd.DataFrame()
    
    def read_uncategorized(self, limit: int = None) -> pd.DataFrame:
        """Read transactions without AI categories."""
        df = self.read_all()
        if df.empty:
            return pd.DataFrame()
        
        # Find transactions with empty or missing AI categories
        if 'ai_category' not in df.columns:
            uncategorized = df
        else:
            uncategorized = df[
                (df['ai_category'].isna()) | 
                (df['ai_category'] == '') | 
                (df['ai_category'] == 'nan')
            ]
        
        if limit is not None:
            uncategorized = uncategorized.head(limit)
        
        return uncategorized
    
    def read_with_filters(self, filters: TransactionFilters) -> pd.DataFrame:
        """Read transactions with applied filters."""
        df = self.read_all()
        if df.empty:
            return pd.DataFrame()
        
        try:
            # Apply date filters
            if filters.date_start or filters.date_end:
                if 'date' in df.columns:
                    df['date'] = pd.to_datetime(df['date'])
                    if filters.date_start:
                        df = df[df['date'] >= filters.date_start]
                    if filters.date_end:
                        df = df[df['date'] <= filters.date_end]
            
            # Apply bank filters
            if filters.banks and 'bank_name' in df.columns:
                df = df[df['bank_name'].isin(filters.banks)]
            
            # Apply category filters
            if filters.categories and 'ai_category' in df.columns:
                df = df[df['ai_category'].isin(filters.categories)]
            
            # Apply amount filters
            if filters.amount_min is not None and 'amount' in df.columns:
                df = df[pd.to_numeric(df['amount'], errors='coerce') >= filters.amount_min]
            if filters.amount_max is not None and 'amount' in df.columns:
                df = df[pd.to_numeric(df['amount'], errors='coerce') <= filters.amount_max]
            
            # Apply pending filter
            if filters.pending_only is not None and 'pending' in df.columns:
                df = df[df['pending'] == filters.pending_only]
            
            # Apply uncategorized filter
            if filters.uncategorized_only and 'ai_category' in df.columns:
                df = df[
                    (df['ai_category'].isna()) | 
                    (df['ai_category'] == '') | 
                    (df['ai_category'] == 'nan')
                ]
            
            return df
            
        except Exception as e:
            self.logger.error(f"Error applying filters: {e}")
            return pd.DataFrame()
    
    # WRITE operations
    def create(self, transactions: List[Dict]) -> List[str]:
        """
        Create new transactions.
        Returns list of created transaction IDs.
        """
        if not transactions:
            return []
        
        try:
            existing_df = self.read_all()
            existing_ids = set()
            
            if not existing_df.empty and 'transaction_id' in existing_df.columns:
                existing_ids = set(existing_df['transaction_id'].dropna().astype(str))
            
            # Filter out existing transactions
            new_transactions = []
            created_ids = []
            
            for transaction in transactions:
                transaction_id = str(transaction.get('transaction_id', ''))
                if transaction_id and transaction_id not in existing_ids:
                    # Add timestamp for when we imported this
                    transaction['created_at'] = datetime.now().isoformat()
                    new_transactions.append(transaction)
                    created_ids.append(transaction_id)
            
            if new_transactions:
                df_new = pd.DataFrame(new_transactions)
                
                # Combine and save
                df_combined = pd.concat([existing_df, df_new], ignore_index=True)
                
                # Sort by date (newest first)
                if 'date' in df_combined.columns:
                    df_combined['date'] = pd.to_datetime(df_combined['date'])
                    df_combined = df_combined.sort_values('date', ascending=False)
                
                df_combined.to_csv(self.csv_path, index=False)
                self.logger.info(f"Created {len(new_transactions)} new transactions")
            
            return created_ids
            
        except Exception as e:
            self.logger.error(f"Error creating transactions: {e}")
            return []
    
    def update_by_id(self, transaction_id: str, updates: Dict) -> bool:
        """Update single transaction by ID."""
        try:
            df = self.read_all()
            if df.empty:
                return False
            
            mask = df['transaction_id'] == transaction_id
            if not mask.any():
                self.logger.error(f"Transaction {transaction_id} not found for update")
                return False
            
            # Apply updates
            for field, value in updates.items():
                if field in df.columns:
                    df.loc[mask, field] = value
            
            # Save back to CSV
            df.to_csv(self.csv_path, index=False)
            self.logger.info(f"Updated transaction {transaction_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error updating transaction {transaction_id}: {e}")
            return False
    
    def bulk_update(self, updates: Dict[str, Dict]) -> int:
        """
        Bulk update multiple transactions.
        Args: {transaction_id: {field: value}}
        Returns: Number of updated records
        """
        try:
            df = self.read_all()
            if df.empty:
                return 0
            
            updated_count = 0
            
            for transaction_id, field_updates in updates.items():
                mask = df['transaction_id'] == transaction_id
                if mask.any():
                    for field, value in field_updates.items():
                        if field in df.columns:
                            df.loc[mask, field] = value
                    updated_count += 1
            
            if updated_count > 0:
                df.to_csv(self.csv_path, index=False)
                self.logger.info(f"Bulk updated {updated_count} transactions")
            
            return updated_count
            
        except Exception as e:
            self.logger.error(f"Error in bulk update: {e}")
            return 0
    
    def delete_by_ids(self, transaction_ids: List[str]) -> int:
        """Delete transactions by IDs."""
        if not transaction_ids:
            return 0
        
        try:
            df = self.read_all()
            if df.empty:
                return 0
            
            initial_count = len(df)
            df = df[~df['transaction_id'].isin(transaction_ids)]
            removed_count = initial_count - len(df)
            
            if removed_count > 0:
                df.to_csv(self.csv_path, index=False)
                self.logger.info(f"Removed {removed_count} transactions")
            
            return removed_count
            
        except Exception as e:
            self.logger.error(f"Error deleting transactions: {e}")
            return 0
    
    # UTILITY operations
    def exists(self, transaction_id: str) -> bool:
        """Check if transaction exists."""
        return self.read_by_id(transaction_id) is not None
    
    def count_all(self) -> int:
        """Count total transactions."""
        df = self.read_all()
        return len(df)
    
    def get_date_range(self) -> Tuple[Optional[datetime], Optional[datetime]]:
        """Get min/max transaction dates."""
        df = self.read_all()
        if df.empty or 'date' not in df.columns:
            return None, None
        
        try:
            df['date'] = pd.to_datetime(df['date'])
            return df['date'].min(), df['date'].max()
        except Exception as e:
            self.logger.error(f"Error getting date range: {e}")
            return None, None
    
    def find_duplicates(self, transaction: Dict) -> List[str]:
        """Find potential duplicate transaction IDs."""
        df = self.read_all()
        if df.empty:
            return []
        
        try:
            # Match criteria: same amount, similar date, same merchant (within 3 days)
            duplicates = []
            
            for _, row in df.iterrows():
                # Check amount match
                if abs(float(row.get('amount', 0)) - float(transaction.get('amount', 0))) > 0.01:
                    continue
                
                # Check merchant match
                row_merchant = str(row.get('merchant_name', '')).lower()
                new_merchant = str(transaction.get('merchant_name', '')).lower()
                row_name = str(row.get('name', '')).lower()
                new_name = str(transaction.get('name', '')).lower()
                
                if not ((row_merchant and new_merchant and row_merchant in new_merchant) or
                       (new_merchant and row_merchant and new_merchant in row_merchant) or
                       (row_name and new_name and row_name in new_name) or
                       (new_name and row_name and new_name in row_name)):
                    continue
                
                # Check date proximity (within 3 days)
                try:
                    row_date = pd.to_datetime(row.get('date'))
                    new_date = pd.to_datetime(transaction.get('date'))
                    date_diff = abs((row_date - new_date).days)
                    
                    if date_diff <= 3:
                        duplicates.append(str(row.get('transaction_id', '')))
                except:
                    pass
            
            return duplicates
            
        except Exception as e:
            self.logger.error(f"Error finding duplicates: {e}")
            return []
    
    def create_accounts_from_plaid(self, institution_name: str, plaid_accounts: List[Dict]) -> int:
        """No-op for CSV compatibility. CSV doesn't have separate accounts table."""
        return 0  # CSV doesn't create separate account records