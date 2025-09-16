from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import logging
import json
import os
import pandas as pd
from plaid_client import PlaidClient
from config import create_data_manager, config
from llm_service.llm_categorizer import TransactionLLMCategorizer
from transaction_types import (
    TransactionFilters, SyncResult, CategorizationResult, BulkCategorizationResult,
    LinkResult, SummaryStats, CleanupOptions, CleanupResult
)

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

class TransactionService:
    """
    Business logic layer - orchestrates data operations, Plaid sync, and AI categorization.
    No direct file I/O - delegates to DataManager (CSV or SQLite based on configuration).
    """
    
    def __init__(self, data_manager=None, plaid_client: PlaidClient = None, 
                 categorizer: TransactionLLMCategorizer = None):
        """
        Initialize with injected dependencies.
        
        Args:
            data_manager: Data access layer (auto-created if None using factory pattern)
            plaid_client: Optional Plaid client (created if None)
            categorizer: Optional AI categorizer (created if None)
        """
        self.data_manager = data_manager or create_data_manager()
        self.plaid_client = plaid_client or PlaidClient()
        self.categorizer = categorizer or TransactionLLMCategorizer()
        self.logger = logging.getLogger(__name__)
    
    # SYNC operations
    def sync_all_accounts(self, full_sync: bool = False) -> SyncResult:
        """
        Sync all connected accounts using database-driven institution management.
        
        Returns:
            SyncResult with statistics and status
        """
        sync_time = datetime.now()
        institution_results = {}
        total_new = 0
        total_updated = 0
        errors = []
        
        try:
            # Get all institutions from database
            institutions = self.data_manager.get_all_institutions()
            
            if not institutions:
                return SyncResult(
                    success=False,
                    new_transactions=0,
                    updated_transactions=0,
                    errors=["No accounts connected"],
                    sync_time=sync_time,
                    institution_results={}
                )
            
            # Sync each institution
            for institution in institutions:
                institution_name = institution['id']
                try:
                    result = self.sync_account(institution_name, full_sync)
                    institution_results[institution_name] = result.new_transactions
                    total_new += result.new_transactions
                    total_updated += result.updated_transactions
                    errors.extend(result.errors)
                    
                except Exception as e:
                    error_msg = f"Error syncing {institution_name}: {str(e)}"
                    errors.append(error_msg)
                    self.logger.error(error_msg)
            
            # Update last sync time for all institutions
            self._update_last_sync_time(sync_time)
            
            return SyncResult(
                success=len(errors) == 0,
                new_transactions=total_new,
                updated_transactions=total_updated,
                errors=errors,
                sync_time=sync_time,
                institution_results=institution_results
            )
            
        except Exception as e:
            error_msg = f"Sync failed: {str(e)}"
            self.logger.error(error_msg)
            return SyncResult(
                success=False,
                new_transactions=0,
                updated_transactions=0,
                errors=[error_msg],
                sync_time=sync_time,
                institution_results={}
            )
    
    def sync_account(self, institution_name: str, full_sync: bool = False) -> SyncResult:
        """Sync specific account using database-driven institution management."""
        sync_time = datetime.now()
        
        try:
            # Get access token from database
            access_token = self.data_manager.get_institution_access_token(institution_name)
            
            if not access_token:
                return SyncResult(
                    success=False,
                    new_transactions=0,
                    updated_transactions=0,
                    errors=[f"Institution {institution_name} not found"],
                    sync_time=sync_time,
                    institution_results={}
                )
            
            # Get sync cursor from database
            if full_sync:
                cursor = None
            else:
                cursor = self.data_manager.get_institution_cursor(institution_name)
            
            # Fetch transactions from Plaid
            transactions_data = self.plaid_client.transactions_sync(
                access_token=access_token,
                cursor=cursor
            )
            
            # Process and store transactions
            new_transactions = []
            for transaction in transactions_data.get('transactions', []):
                # Convert Plaid transaction to our format
                processed_transaction = self._process_plaid_transaction(
                    transaction, institution_name
                )
                new_transactions.append(processed_transaction)
            
            # Create new transactions in database (handles both inserts and updates)
            processed_ids = self.data_manager.create(new_transactions)
            
            # # Automatically categorize all processed transactions (both created and updated)
            # if processed_ids:
            #     self.logger.info(f"Auto-categorizing {len(processed_ids)} processed transactions")
            #     for transaction_id in processed_ids:
            #         try:
            #             categorization_result = self.categorize_transaction(transaction_id)
            #             if not categorization_result.success:
            #                 self.logger.warning(f"Failed to categorize {transaction_id}: {categorization_result.error}")
            #         except Exception as e:
            #             self.logger.error(f"Error auto-categorizing {transaction_id}: {e}")
            
            # Update cursor and last sync time in database
            new_cursor = transactions_data.get('next_cursor')
            if new_cursor:
                self.data_manager.update_institution_cursor(institution_name, new_cursor)
            
            # Always update last sync time, regardless of whether there's a new cursor
            self.data_manager.update_institution_last_sync(institution_name, sync_time.isoformat())
            
            self.logger.info(f"Synced {len(processed_ids)} transactions from {institution_name}")
            
            return SyncResult(
                success=True,
                new_transactions=len(processed_ids),
                updated_transactions=0,
                errors=[],
                sync_time=sync_time,
                institution_results={institution_name: len(processed_ids)}
            )
            
        except Exception as e:
            error_msg = f"Error syncing {institution_name}: {str(e)}"
            self.logger.error(error_msg)
            return SyncResult(
                success=False,
                new_transactions=0,
                updated_transactions=0,
                errors=[error_msg],
                sync_time=sync_time,
                institution_results={}
            )
    
    def get_sync_status(self) -> Dict[str, datetime]:
        """Get last sync time for each institution from database."""
        institutions = self.data_manager.get_all_institutions()
        status = {}
        
        for institution in institutions:
            institution_name = institution['id']
            last_sync = institution.get('last_sync')
            if last_sync:
                try:
                    status[institution_name] = datetime.fromisoformat(last_sync)
                except:
                    status[institution_name] = None
            else:
                status[institution_name] = None
        
        return status
    
    # ACCOUNT management
    def link_account(self, public_token: str, institution_name: str) -> LinkResult:
        """Link new Plaid account using database-driven institution management."""
        try:
            # Exchange public token for access token
            access_token = self.plaid_client.exchange_public_token(public_token)
            
            # Get account information from Plaid
            account_info = self.plaid_client.get_accounts(access_token)
            
            # Create institution record in database
            institution_created = self.data_manager.create_institution(institution_name, access_token)
            if not institution_created:
                self.logger.warning(f"Institution {institution_name} may already exist, continuing with account creation")
            
            # Create accounts in database
            accounts_created = self.data_manager.create_accounts_from_plaid(
                institution_name, account_info
            )
            self.logger.info(f"Created {accounts_created} accounts in database for {institution_name}")
            
            return LinkResult(
                success=True,
                institution_name=institution_name,
                account_count=len(account_info)
            )
            
        except Exception as e:
            error_msg = f"Error linking {institution_name}: {str(e)}"
            self.logger.error(error_msg)
            return LinkResult(
                success=False,
                institution_name=institution_name,
                account_count=0,
                error=error_msg
            )
    
    def get_accounts(self) -> Dict[str, List[Dict]]:
        """Get all linked accounts with balances using database-driven management."""
        try:
            # Get accounts grouped by institution from database
            accounts_data = self.data_manager.get_all_accounts_with_institutions()
            accounts = {}
            
            # For each institution, try to get fresh data from Plaid, fallback to database
            for institution_name, institution_data in accounts_data.items():
                try:
                    access_token = self.data_manager.get_institution_access_token(institution_name)
                    if access_token:
                        # Try to get fresh account info from Plaid
                        try:
                            fresh_account_info = self.plaid_client.get_accounts(access_token)
                            accounts[institution_name] = {
                                'accounts': fresh_account_info,
                                'last_sync': institution_data.get('last_sync'),
                                'created_at': institution_data.get('created_at')
                            }
                            self.logger.info(f"Retrieved fresh account data for {institution_name}")
                        except Exception as plaid_error:
                            # Plaid API failed (e.g., wrong environment), use database data
                            self.logger.warning(f"Plaid API failed for {institution_name}, using database data: {plaid_error}")
                            accounts[institution_name] = {
                                'accounts': institution_data.get('accounts', []),
                                'last_sync': institution_data.get('last_sync'),
                                'created_at': institution_data.get('created_at'),
                                'plaid_error': str(plaid_error)
                            }
                    else:
                        # No access token found, use database data
                        accounts[institution_name] = {
                            'accounts': institution_data.get('accounts', []),
                            'last_sync': institution_data.get('last_sync'),
                            'created_at': institution_data.get('created_at')
                        }
                except Exception as e:
                    self.logger.error(f"Error processing accounts for {institution_name}: {e}")
                    # Fallback to database data on any error
                    accounts[institution_name] = {
                        'accounts': institution_data.get('accounts', []),
                        'last_sync': institution_data.get('last_sync'),
                        'created_at': institution_data.get('created_at'),
                        'error': str(e)
                    }
            
            return accounts
            
        except Exception as e:
            self.logger.error(f"Error getting all accounts: {e}")
            return {}
    
    def unlink_account(self, institution_name: str) -> bool:
        """Unlink account using database-driven institution management."""
        try:
            # Delete institution and all its accounts from database
            success = self.data_manager.delete_institution(institution_name)
            if success:
                self.logger.info(f"Unlinked institution: {institution_name}")
                return True
            else:
                self.logger.warning(f"Institution {institution_name} not found for unlinking")
                return False
            
        except Exception as e:
            self.logger.error(f"Error unlinking {institution_name}: {e}")
            return False
    
    # CATEGORIZATION operations
    def categorize_transaction(self, transaction_id: str) -> CategorizationResult:
        """AI categorize single transaction with transfer detection."""
        try:
            self.logger.info(f"GONNA START {transaction_id}")
            # Get transaction data from database
            transaction_dict = self.data_manager.read_by_id(transaction_id)
            self.logger.info(f"GONNA START {transaction_dict}")

            if not transaction_dict:
                return CategorizationResult(
                    success=False,
                    error=f"Transaction {transaction_id} not found"
                )
            
            # Find potential transfer matches
            potential_transfers = self.data_manager.find_potential_transfers(
                transaction_id=transaction_id,
                amount=float(transaction_dict.get('amount', 0)),
                date=transaction_dict.get('date', ''),
                account_id=transaction_dict.get('account_id', '')
            )
            
            # Convert to Transaction object
            from transaction_types import Transaction
            transaction = Transaction.from_dict(transaction_dict)
            
            # Use the LLM categorizer with Transaction object and potential transfers
            result = self.categorizer._categorize_with_llm(transaction, potential_transfers=potential_transfers)
            
            if "error" in result:
                return CategorizationResult(
                    success=False,
                    error=result["error"]
                )
            
            # Update the transaction with the categorization
            updates = {
                'ai_category': result.get('category', ''),
                'ai_reason': result.get('reasoning', '')
            }
            
            success = self.data_manager.update_by_id(transaction_id, updates)
            
            return CategorizationResult(
                success=success,
                category=result.get('category'),
                reasoning=result.get('reasoning')
            )
            
        except Exception as e:
            error_msg = f"Error categorizing transaction {transaction_id}: {str(e)}"
            self.logger.error(error_msg)
            return CategorizationResult(
                success=False,
                error=error_msg
            )
    
    def bulk_categorize(self, force_recategorize: bool = False) -> BulkCategorizationResult:
        """
        AI categorize multiple transactions.
        
        Args:
            force_recategorize: If True, recategorize ALL transactions
                               If False, only categorize uncategorized transactions (default behavior)
        
        Returns:
            BulkCategorizationResult with processing statistics
        """
        try:
            if force_recategorize:
                # Get all transactions
                transactions_df = self.data_manager.read_all()
                self.logger.info(f"Force recategorizing {len(transactions_df)} transactions")
            else:
                # Original behavior - only uncategorized transactions
                transactions_df = self.data_manager.read_uncategorized()
                self.logger.info(f"Categorizing {len(transactions_df)} uncategorized transactions")
            
            if transactions_df.empty:
                return BulkCategorizationResult(
                    successful_count=0,
                    failed_count=0,
                    errors=[],
                    results=[]
                )
            
            results = []
            successful_count = 0
            failed_count = 0
            errors = []
            
            for _, row in transactions_df.iterrows():
                transaction_id = row.get('transaction_id')
                if not transaction_id:
                    continue
                    
                result = self.categorize_transaction(transaction_id)
                results.append(result)
                
                if result.success:
                    successful_count += 1
                else:
                    failed_count += 1
                    if result.error:
                        errors.append(f"{transaction_id}: {result.error}")
            
            operation_type = "force recategorization" if force_recategorize else "categorization"
            self.logger.info(f"Bulk {operation_type} completed: {successful_count} successful, {failed_count} failed")
            
            return BulkCategorizationResult(
                successful_count=successful_count,
                failed_count=failed_count,
                errors=errors,
                results=results
            )
            
        except Exception as e:
            error_msg = f"Error in bulk categorization: {str(e)}"
            self.logger.error(error_msg)
            return BulkCategorizationResult(
                successful_count=0,
                failed_count=0,
                errors=[error_msg],
                results=[]
            )
    
    def update_category(self, transaction_id: str, category: str, reasoning: str = None, 
                       source: str = "manual") -> bool:
        """Update transaction category (manual or AI)."""
        try:
            if source == "manual":
                # For manual categories, use manual_category field
                updates = {'manual_category': category}
                
                # Add manual categorization note
                transaction = self.data_manager.read_by_id(transaction_id)
                if transaction:
                    current_notes = transaction.get('notes', '') or ''
                    manual_note = f"Manual categorization: {category}"
                    
                    if current_notes:
                        updates['notes'] = f"{current_notes} | {manual_note}"
                    else:
                        updates['notes'] = manual_note
            else:
                # For AI categories, use ai_category field
                updates = {'ai_category': category}
                
                if reasoning:
                    updates['ai_reason'] = reasoning
            
            return self.data_manager.update_by_id(transaction_id, updates)
            
        except Exception as e:
            self.logger.error(f"Error updating category for {transaction_id}: {e}")
            return False
    
    def update_manual_category(self, transaction_id: str, category: str) -> bool:
        """Convenience method to update manual category override."""
        return self.update_category(transaction_id, category, source="manual")
    
    def clear_manual_category(self, transaction_id: str) -> bool:
        """Clear manual category override (fall back to AI or Plaid)."""
        try:
            updates = {'manual_category': ''}
            return self.data_manager.update_by_id(transaction_id, updates)
        except Exception as e:
            self.logger.error(f"Error clearing manual category for {transaction_id}: {e}")
            return False
    
    # DATA operations (business logic wrappers)
    def get_transactions(self, filters: TransactionFilters = None) -> pd.DataFrame:
        """Get transactions with optional filtering."""
        if filters:
            return self.data_manager.read_with_filters(filters)
        else:
            return self.data_manager.read_all()
    
    def get_summary_stats(self, date_range: Tuple[datetime, datetime] = None) -> SummaryStats:
        """Get financial summary statistics."""
        try:
            if date_range:
                df = self.data_manager.read_by_date_range(date_range[0], date_range[1])
                stats_date_range = date_range
            else:
                df = self.data_manager.read_all()
                db_start, db_end = self.data_manager.get_date_range()
                stats_date_range = (db_start, db_end)
            
            if df.empty:
                return SummaryStats(
                    total_transactions=0,
                    total_spending=0.0,
                    total_income=0.0,
                    net_flow=0.0,
                    date_range=stats_date_range,
                    category_breakdown={},
                    monthly_trends={}
                )
            
            # Convert amount to numeric
            df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
            
            # Calculate basic stats
            total_transactions = len(df)
            spending_df = df[df['amount'] > 0]
            income_df = df[df['amount'] < 0]
            
            total_spending = spending_df['amount'].sum() if not spending_df.empty else 0.0
            total_income = abs(income_df['amount'].sum()) if not income_df.empty else 0.0
            net_flow = total_income - total_spending
            
            # Category breakdown
            category_breakdown = {}
            if 'ai_category' in df.columns:
                spending_by_category = spending_df.groupby('ai_category')['amount'].sum()
                category_breakdown = spending_by_category.to_dict()
            
            # Monthly trends
            monthly_trends = {}
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
                df['month'] = df['date'].dt.to_period('M').astype(str)
                monthly_spending = spending_df.groupby('month')['amount'].sum()
                monthly_trends = monthly_spending.to_dict()
            
            return SummaryStats(
                total_transactions=total_transactions,
                total_spending=float(total_spending),
                total_income=float(total_income),
                net_flow=float(net_flow),
                date_range=stats_date_range,
                category_breakdown={k: float(v) for k, v in category_breakdown.items()},
                monthly_trends={k: float(v) for k, v in monthly_trends.items()}
            )
            
        except Exception as e:
            self.logger.error(f"Error calculating summary stats: {e}")
            return SummaryStats(
                total_transactions=0,
                total_spending=0.0,
                total_income=0.0,
                net_flow=0.0,
                date_range=(None, None),
                category_breakdown={},
                monthly_trends={}
            )
    
    def cleanup_data(self, cleanup_options: CleanupOptions) -> CleanupResult:
        """Clean up old pending transactions, duplicates, etc."""
        removed_pending = 0
        removed_duplicates = 0
        fixed_data_issues = 0
        errors = []
        
        try:
            # Remove old pending transactions
            if cleanup_options.remove_old_pending_days:
                df = self.data_manager.read_all()
                if not df.empty and 'pending' in df.columns and 'date' in df.columns:
                    df['date'] = pd.to_datetime(df['date'], errors='coerce')
                    cutoff_date = datetime.now() - timedelta(days=cleanup_options.remove_old_pending_days)
                    
                    old_pending_mask = (df['pending'] == True) & (df['date'] < cutoff_date)
                    old_pending_ids = df[old_pending_mask]['transaction_id'].tolist()
                    
                    if old_pending_ids:
                        removed_pending = self.data_manager.delete_by_ids(old_pending_ids)
            
            # Remove duplicates (basic implementation)
            if cleanup_options.remove_duplicates:
                # This would need more sophisticated duplicate detection logic
                pass
            
        except Exception as e:
            error_msg = f"Error during cleanup: {str(e)}"
            errors.append(error_msg)
            self.logger.error(error_msg)
        
        return CleanupResult(
            removed_pending=removed_pending,
            removed_duplicates=removed_duplicates,
            fixed_data_issues=fixed_data_issues,
            errors=errors
        )
    
    def export_data(self, filters: TransactionFilters = None, 
                   export_format: str = "csv") -> pd.DataFrame:
        """Export transactions in specified format."""
        # Future: Could add different export formats (JSON, Excel, etc.)
        return self.get_transactions(filters)
    
    def _update_last_sync_time(self, sync_time: datetime) -> None:
        """Update last sync time for all institutions in database."""
        try:
            institutions = self.data_manager.get_all_institutions()
            
            for institution in institutions:
                institution_name = institution['id']
                self.data_manager.update_institution_last_sync(institution_name, sync_time.isoformat())
            
        except Exception as e:
            self.logger.error(f"Error updating last sync time: {e}")
    
    def _process_plaid_transaction(self, transaction_dict: Dict, institution_name: str) -> Dict:
        """Process a formatted transaction dict from PlaidClient and add institution info."""
        try:
            # PlaidClient already returns formatted dictionaries, just add institution info
            transaction_dict['bank_name'] = institution_name
            
            # Initialize AI categorization fields if not present
            if 'ai_category' not in transaction_dict:
                transaction_dict['ai_category'] = ''
            if 'ai_reason' not in transaction_dict:
                transaction_dict['ai_reason'] = ''
            if 'notes' not in transaction_dict:
                transaction_dict['notes'] = ''
            if 'tags' not in transaction_dict:
                transaction_dict['tags'] = ''
            
            return transaction_dict
            
        except Exception as e:
            self.logger.error(f"Error processing Plaid transaction: {e}")
            return {}