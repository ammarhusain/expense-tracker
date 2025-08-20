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

    