import streamlit as st
from transaction_service import TransactionService
from data_utils.s3_database_manager import db_manager

class S3TransactionService(TransactionService):
    """
    Enhanced TransactionService with automatic S3 synchronization.
    Inherits all functionality from TransactionService and adds S3 sync after data changes.
    """
    
    def __init__(self, data_manager, db_manager):
        super().__init__(data_manager)
        self.db_manager = db_manager
    
    def _sync_after_change(self):
        """Helper to sync to S3 after any data change"""
        if self.db_manager.s3_client:
            success = self.db_manager.upload_to_s3()
            if success:
                st.toast("✅ Synced to S3", icon="☁️")
            else:
                st.toast("❌ Sync failed", icon="⚠️")
    
    def link_account(self, public_token, institution_name):
        """Override to sync after linking"""
        result = super().link_account(public_token, institution_name)
        if result.success:
            self._sync_after_change()
        return result
    
    def sync_all_accounts(self, full_sync=False):
        """Override to sync after transaction sync"""
        result = super().sync_all_accounts(full_sync)
        if result.success and result.new_transactions > 0:
            self._sync_after_change()
        return result
    
    def sync_account(self, institution_name, full_sync=False):
        """Override to sync after individual account sync"""
        result = super().sync_account(institution_name, full_sync)
        if result.success and result.new_transactions > 0:
            self._sync_after_change()
        return result
    
    def categorize_transaction(self, transaction_id):
        """Override to sync after categorization"""
        result = super().categorize_transaction(transaction_id)
        if result.success:
            self._sync_after_change()
        return result
    
    def bulk_categorize(self, force_recategorize=False):
        """Override to sync after bulk categorization"""
        result = super().bulk_categorize(force_recategorize)
        if result.successful_count > 0:
            self._sync_after_change()
        return result
    
    def bulk_categorize_selected(self, transaction_ids):
        """Override to sync after bulk categorization of selected transactions"""
        result = super().bulk_categorize_selected(transaction_ids)
        if result.successful_count > 0:
            self._sync_after_change()
        return result
    
    def update_category(self, transaction_id, category, reasoning=None, source="manual"):
        """Override to sync after manual category updates"""
        result = super().update_category(transaction_id, category, reasoning, source)
        if result:
            self._sync_after_change()
        return result
    
    def bulk_update_transactions(self, updates):
        """Handle bulk transaction updates (like from data editor) with S3 sync"""
        try:
            # Use data manager for bulk update
            if updates:
                updated_count = self.data_manager.bulk_update(updates)
                if updated_count > 0:
                    self._sync_after_change()
                return updated_count
            return 0
        except Exception as e:
            self.logger.error(f"Error in bulk update: {e}")
            return 0
    
    def get_sync_status(self):
        """Get S3 sync status"""
        return self.db_manager.get_sync_status()
    
    def force_sync_to_s3(self):
        """Force immediate sync to S3"""
        return self.db_manager.upload_to_s3()
    
    def refresh_from_s3(self):
        """Force refresh database from S3"""
        return self.db_manager.force_refresh_from_s3()