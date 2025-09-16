import streamlit as st
from dataclasses import dataclass
from typing import Dict, List

@dataclass
class Config:
    # Plaid API configuration
    plaid_client_id: str = st.secrets.get("plaid", {}).get("client_id", "")
    plaid_secret: str = st.secrets.get("plaid", {}).get("secret", "")
    plaid_env: str = st.secrets.get("plaid", {}).get("env", "sandbox")
    
    # Data storage configuration - single path, format determined by extension
    data_path: str = st.secrets.get("DATA_PATH", "./data/transactions.db")  # .db = SQLite
        
    # SQLite configuration
    sqlite_timeout: float = float(st.secrets.get("SQLITE_TIMEOUT", "60.0"))
    
    # General configuration
    sync_interval_hours: int = int(st.secrets.get("SYNC_INTERVAL_HOURS", "24"))
    

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

CATEGORY_DEFINITIONS = {
    "income": {
        "description": "Money received from various sources",
        "subcategories": {
            "paychecks": "Regular salary payments from employers",
            "interest_income": "Interest earned from bank accounts, CDs, bonds",
            "business_income": "Revenue from business activities or freelance work",
            "investment_income": "Dividends, capital gains, investment returns"
        }
    },
    "benevolence": {
        "description": "Money given to others",
        "subcategories": {
            "charity": "Donations to charitable organizations",
            "gifts": "Money given to family, friends, or others"
        }
    },
    "transportation": {
        "description": "Vehicle and travel-related expenses",
        "subcategories": {
            "auto_payment": "Car loan or lease payments",
            "public_transit": "Bus, train, subway fares",
            "gas": "Gasoline for vehicles",
            "auto_maintenance": "Car repairs, oil changes, maintenance",
            "parking_or_tolls": "Parking fees, toll road charges",
            "taxi_or_ride_shares": "Uber, Lyft, taxi services"
        }
    },
    "housing": {
        "description": "Home and housing-related expenses",
        "subcategories": {
            "mortgage": "Monthly mortgage payments",
            "rent": "Monthly rental payments",
            "furniture": "Furniture purchases for home",
            "home_maintenance": "Home repairs, maintenance services",
            "remodel": "Home renovation, remodeling expenses"
        }
    },
    "utilities": {
        "description": "Essential home services and subscriptions",
        "subcategories": {
            "garbage": "Waste management services",
            "water": "Water utility bills",
            "gas_and_electric": "Gas and electric utility bills",
            "internet": "Internet service provider bills",
            "phone": "Mobile or landline phone bills",
            "software_subscriptions": "Software, streaming, app subscriptions"
        }
    },
    "food": {
        "description": "Food and dining expenses",
        "subcategories": {
            "groceries": "Food shopping at grocery stores",
            "restaurants_or_bars": "Dining out, bars, takeout",
            "coffee_shops": "Coffee shops, cafes"
        }
    },
    "travel": {
        "description": "Travel and vacation expenses",
        "subcategories": {
            "travel_general": "General travel expenses",
            "airfare": "Flight tickets",
            "accommodation": "Hotels, lodging"
        }
    },
    "shopping": {
        "description": "Retail purchases and consumer goods",
        "subcategories": {
            "shopping": "General retail purchases",
            "clothing": "Apparel, shoes, accessories",
            "housewares": "Household items, home goods",
            "electronics": "Electronics, gadgets, tech purchases"
        }
    },
    "lifestyle": {
        "description": "Personal development and entertainment",
        "subcategories": {
            "personal_grooming": "Haircuts, beauty services, cosmetics",
            "hobbies": "Hobby supplies, craft materials",
            "education": "Educational expenses, courses, books",
            "entertainment_or_recreation": "Movies, concerts, recreational activities"
        }
    },
    "health_wellness": {
        "description": "Health and fitness related expenses",
        "subcategories": {
            "medical": "Doctor visits, medical expenses",
            "dental": "Dental care expenses",
            "fitness": "Gym memberships, fitness services"
        }
    },
    "financial": {
        "description": "Financial services and obligations",
        "subcategories": {
            "loan_repayment": "Loan payments (non-auto, non-mortgage)",
            "financial_legal_services": "Banking fees, legal services",
            "atm_cash_withdrawal": "ATM cash withdrawals",
            "insurance": "Insurance premiums for cars and home",
            "taxes": "Tax payments to IRS or property taxes",
            "penalties": "Late fees, penalties",
            "hand_loans": "Personal loans to/from individuals",
            "invest": "Investment purchases and usually transfers into brokerage accounts"
        }
    },
    "other": {
        "description": "Miscellaneous and uncategorized expenses",
        "subcategories": {
            "uncategorized": "Catch all category for items that don't fit other categories or you cannot figure out with high confidence where to put it",
            "miscellaneous": "Various small expenses",
            "maaji_bauji": "Expenses related to father's family",
            "mummy-g_daddy-g": "Expenses related to mother's family", 
            "loss": "Lost money or theft",
            "reimburse": "Reimbursements received usually as deposits from Venmo or Zelle"
        }
    },
    "transfers": {
        "description": "Money transfers and account movements",
        "subcategories": {
            "transfer": "Money transfers between own accounts",
            "credit_card_payment": "Credit card bill payments",
            "to_india": "Money transfers to India usually money sent to Revolut"
        }
    }
}

# Helper functions to work with the new structure
def get_category_mapping() -> Dict[str, List[str]]:
    """Generate category mapping for existing code compatibility"""
    return {
        parent: list(data['subcategories'].keys())
        for parent, data in CATEGORY_DEFINITIONS.items()
    }

def get_all_subcategories() -> List[str]:
    """Get flat list of all subcategories"""
    subcats = []
    for data in CATEGORY_DEFINITIONS.values():
        subcats.extend(data['subcategories'].keys())
    return subcats

def get_category_description(subcategory: str) -> str:
    """Get description for a specific subcategory"""
    for data in CATEGORY_DEFINITIONS.values():
        if subcategory in data['subcategories']:
            return data['subcategories'][subcategory]
    return "Unknown category"

def get_parent_category(subcategory: str) -> str:
    """Get parent category for a subcategory"""
    for parent, data in CATEGORY_DEFINITIONS.items():
        if subcategory in data['subcategories']:
            return parent
    return "other"