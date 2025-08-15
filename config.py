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
    sqlite_timeout: float = float(os.getenv("SQLITE_TIMEOUT", "30.0"))
    
    # General configuration
    sync_interval_hours: int = int(os.getenv("SYNC_INTERVAL_HOURS", "24"))
    

config = Config()

# Factory pattern for DataManager selection based on file extension
def create_data_manager(data_path: str = None):
    """Factory function to create appropriate DataManager based on file extension."""
    path = data_path or config.data_path
    
    if path.endswith('.db'):
        from data_utils.sqlite_data_manager import SqliteDataManager
        return SqliteDataManager(path)
    elif path.endswith('.csv'):
        from data_utils.data_manager import DataManager
        return DataManager(path)
    else:
        raise ValueError(f"Unsupported data file extension: {path}. Use .csv or .db")

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
  "financial": ["loan_repayment", "financial_legal_services", "atm_cash_withdrawal", "insurance", "taxes", "penalties", "hand loans", "invest"],
  "other": ["uncategorized", "miscellaneous", "maaji bauji", "mummy-g, daddy-g", "loss", "reimburse"],
  "transfers": ["transfer", "credit_card_payment", "to_india"]
}

    