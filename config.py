import os
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import Dict, List

load_dotenv()

@dataclass
class Config:
    # Plaid API configuration
    plaid_client_id: str = os.getenv("PLAID_CLIENT_ID", "")
    plaid_secret: str = os.getenv("PLAID_SECRET", "")
    plaid_env: str = os.getenv("PLAID_ENV", "sandbox")
    
    # Data storage configuration - single path, format determined by extension
    data_path: str = os.getenv("DATA_PATH", "./data/transactions.csv")  # .csv = CSV, .db = SQLite
        
    # SQLite configuration
    sqlite_timeout: float = float(os.getenv("SQLITE_TIMEOUT", "60.0"))
    
    # General configuration
    sync_interval_hours: int = int(os.getenv("SYNC_INTERVAL_HOURS", "24"))
    

config = Config()

# Factory pattern for DataManager - SQLite only
def create_data_manager(data_path: str = None):
    """Factory function to create SQLite DataManager."""
    path = data_path or config.data_path
    
    if not path.endswith('.db'):
        raise ValueError(f"Only SQLite databases (.db) are supported. Got: {path}")
    
    from data_utils.sqlite_data_manager import SqliteDataManager
    return SqliteDataManager(path)

# Factory pattern for TransactionService with S3 support
def create_transaction_service(data_manager):
    """
    Smart factory that creates the appropriate TransactionService type.
    
    Returns:
        - S3TransactionService if S3 is enabled (has AWS secrets)
        - TransactionService if running locally without S3
    """
    from data_utils.s3_database_manager import db_manager
    
    if db_manager.is_s3_enabled():
        from data_utils.s3_transaction_service import S3TransactionService
        return S3TransactionService(data_manager, db_manager)
    else:
        from transaction_service import TransactionService
        return TransactionService(data_manager)

def create_services(local_db_path: str = "./data/transactions.prod.db"):
    """
    Factory function to create both data manager and transaction service.
    Handles the complete service initialization with S3 support and fallback.
    
    Args:
        local_db_path: Path to local database file for fallback mode
    
    Returns:
        tuple: (transaction_service, data_manager)
    """
    from data_utils.s3_database_manager import db_manager
    
    # Try S3 first if configured
    s3_db_path = db_manager.is_s3_enabled()
    
    if s3_db_path:
        # S3 worked, use S3-enabled services
        data_manager = create_data_manager(s3_db_path)
        from data_utils.s3_transaction_service import S3TransactionService
        transaction_service = S3TransactionService(data_manager, db_manager)
        return transaction_service, data_manager
    else:
        # S3 failed or not configured, use local fallback
        data_manager = create_data_manager(local_db_path)
        
        from transaction_service import TransactionService
        transaction_service = TransactionService(data_manager)
        
        return transaction_service, data_manager

CATEGORY_MAPPING = {
  "income": ["paychecks", "interest_income", "business_income", "investment income"],
  "benevolence": ["charity", "gifts"],
  "transportation": ["auto_payment", "public_transit", "gas", "auto_maintenance", "parking_or_tolls", "taxi_or_ride_shares"],
  "housing": ["mortgage", "rent", "furniture", "home_maintenance", "remodel"],
  "utilities": ["garbage", "water", "gas_and_electric", "internet", "phone", "software_subscriptions"],
  "food": ["groceries", "restaurants_or_bars", "coffee_shops"],
  "travel": ["travel_general", "airfare", "accommodation"],
  "shopping": ["shopping", "clothing", "housewares", "electronics"],
  "lifestyle": ["personal_grooming", "hobbies", "education", "entertainment_or_recreation"],
  "health_wellness": ["medical", "dental", "fitness"],
  "financial": ["loan_repayment", "financial_legal_services", "atm_cash_withdrawal", "insurance", "taxes", "penalties", "hand_loans", "invest"],
  "other": ["uncategorized", "miscellaneous", "maaji_bauji", "mummy-g_daddy-g", "loss", "reimburse"],
  "transfers": ["transfer", "credit_card_payment", "to_india"]
}