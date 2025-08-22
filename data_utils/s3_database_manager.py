import boto3
import streamlit as st
import threading
import os
from datetime import datetime
from typing import Optional

class S3DatabaseManager:
    """
    Manages database storage and synchronization with AWS S3.
    Provides bidirectional sync between local SQLite and S3 storage.
    """
    
    def __init__(self):
        self.s3_client = None
        self.local_db_path = None
        self.bucket = None
        self.db_key = None
        self.last_sync = None
        self.sync_lock = threading.Lock()
        
        # Initialize S3 connection if secrets available
        try:
            if hasattr(st, 'secrets') and "aws" in st.secrets:
                self.s3_client = boto3.client(
                    's3',
                    aws_access_key_id=st.secrets["aws"]["access_key"],
                    aws_secret_access_key=st.secrets["aws"]["secret_key"],
                    region_name=st.secrets["aws"]["region"]
                )
                self.bucket = st.secrets["aws"]["bucket"]
                self.db_key = st.secrets["aws"]["db_key"]
        except Exception as e:
            # Fail silently during import - only show error in Streamlit context
            if hasattr(st, 'error'):
                st.error(f"Failed to initialize S3 client: {e}")
            self.s3_client = None
    
    def is_s3_enabled(self):
        """Check if S3 is configured and return database path, or None if failed"""
        if not self.s3_client:
            return None
            
        # If we already have a local database path, return it
        if self.local_db_path:
            return self.local_db_path
            
        # Try to download the database
        try:
            self.local_db_path = self._download_from_s3()
            if self.local_db_path:
                self.last_sync = datetime.now()
                return self.local_db_path
            return None
        except Exception as e:
            # S3 setup failed
            if hasattr(st, 'error'):
                st.error(f"❌ S3 setup failed: {e}")
            return None
    
    def _download_from_s3(self) -> str:
        """Download database from S3 to data directory"""
        try:
            # Ensure data directory exists
            data_dir = "./data"
            os.makedirs(data_dir, exist_ok=True)
            
            # Use a predictable filename in data directory
            local_db_path = os.path.join(data_dir, "transactions.s3.db")
            
            # Download from S3
            self.s3_client.download_file(self.bucket, self.db_key, local_db_path)
            self.local_db_path = local_db_path
            # Note: last_sync will be set by caller to avoid caching issues
            
            return local_db_path
            
        except self.s3_client.exceptions.NoSuchKey:
            st.warning("⚠️ Database not found in S3. Creating new database.")
            # Create empty file in data directory for new database
            data_dir = "./data"
            os.makedirs(data_dir, exist_ok=True)
            local_db_path = os.path.join(data_dir, "transactions.s3.db")
            
            # Create empty database file
            with open(local_db_path, 'w') as f:
                pass  # Create empty file
            
            self.local_db_path = local_db_path
            return local_db_path
            
        except Exception as e:
            st.error(f"❌ Failed to download from S3: {e}")
            st.error("Falling back to local-only mode")
            # Disable S3 for this session
            self.s3_client = None
            return "./data/transactions.prod.db"
    
    def upload_to_s3(self) -> bool:
        """Upload local database back to S3"""
        if not self.s3_client or not self.local_db_path:
            return False
            
        if not os.path.exists(self.local_db_path):
            st.error("❌ Local database file not found for upload")
            return False
            
        try:
            with self.sync_lock:
                # Get file size for display
                file_size = os.path.getsize(self.local_db_path) / (1024 * 1024)  # MB
                
                # Upload with versioning and encryption
                self.s3_client.upload_file(
                    self.local_db_path, 
                    self.bucket, 
                    self.db_key,
                    ExtraArgs={
                        'ServerSideEncryption': 'AES256',
                        'ContentType': 'application/x-sqlite3'
                    }
                )
                
                self.last_sync = datetime.now()
                return True
                
        except Exception as e:
            return False
    
    def sync_if_needed(self, force: bool = False) -> bool:
        """Sync to S3 if changes were made or forced"""
        if not self.s3_client:
            return True  # No S3, so "sync" is successful (no-op)
            
        # Get sync interval from secrets or use default
        sync_interval = 300  # 5 minutes default
        if "aws" in st.secrets and "auto_sync_interval" in st.secrets["aws"]:
            sync_interval = st.secrets["aws"]["auto_sync_interval"]
        
        should_sync = force
        if not should_sync and self.last_sync:
            seconds_since_sync = (datetime.now() - self.last_sync).total_seconds()
            should_sync = seconds_since_sync > sync_interval
            
        if should_sync:
            return self.upload_to_s3()
            
        return True
    
    def get_sync_status(self) -> dict:
        """Get current sync status information"""
        return {
            "s3_enabled": self.is_s3_enabled(),
            "last_sync": self.last_sync,
            "bucket": self.bucket if self.s3_client else None,
            "db_key": self.db_key if self.s3_client else None,
            "local_path": self.local_db_path
        }
    
    def force_refresh_from_s3(self) -> bool:
        """Force download latest version from S3, replacing local copy"""
        if not self.s3_client:
            return False
            
        try:
            # Remove old file if it exists (now in data directory)
            if self.local_db_path and os.path.exists(self.local_db_path):
                os.unlink(self.local_db_path)
            
            # Download fresh copy
            self.local_db_path = None
            self.last_sync = None
            new_path = self._download_from_s3()
            
            return new_path is not None
            
        except Exception as e:
            st.error(f"❌ Failed to refresh from S3: {e}")
            return False

# Global database manager instance
db_manager = S3DatabaseManager()