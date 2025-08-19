from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Tuple, Union
import pandas as pd

@dataclass
class Transaction:
    """Transaction data class with all fields."""
    # Core transaction data
    date: Optional[str] = None
    name: Optional[str] = None
    merchant_name: Optional[str] = None
    original_description: Optional[str] = None
    amount: Optional[float] = None
    
    # Plaid categorization (structured string containing all Plaid category data)
    plaid_category: Optional[str] = None
    
    # Transaction metadata
    transaction_type: Optional[str] = None
    currency: Optional[str] = None
    pending: Optional[bool] = None
    account_owner: Optional[str] = None
    location: Optional[str] = None
    payment_details: Optional[str] = None
    website: Optional[str] = None
    
    # AI categorization
    ai_category: Optional[str] = None
    ai_reason: Optional[str] = None
    
    # User fields
    notes: Optional[str] = None
    tags: Optional[str] = None
    
    # Account info
    bank_name: Optional[str] = None
    account_name: Optional[str] = None
    
    # System fields
    created_at: Optional[str] = None
    transaction_id: Optional[str] = None
    account_id: Optional[str] = None
    check_number: Optional[str] = None
    custom_category: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Transaction':
        """Create Transaction from dictionary, handling extra/missing fields."""
        # Only use fields that exist in the dataclass
        field_names = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in field_names}
        return cls(**filtered_data)
    
    def to_dict(self) -> Dict:
        """Convert Transaction to dictionary for CSV/storage."""
        return {k: v for k, v in self.__dict__.items()}

@dataclass
class TransactionFilters:
    """Filter criteria for transaction queries."""
    date_start: Optional[datetime] = None
    date_end: Optional[datetime] = None
    banks: Optional[List[str]] = None
    categories: Optional[List[str]] = None
    amount_min: Optional[float] = None
    amount_max: Optional[float] = None
    pending_only: Optional[bool] = None
    uncategorized_only: Optional[bool] = None

@dataclass
class SyncResult:
    """Result of sync operation."""
    success: bool
    new_transactions: int
    updated_transactions: int
    errors: List[str]
    sync_time: datetime
    institution_results: Dict[str, int]

@dataclass
class CategorizationResult:
    """Result of AI categorization."""
    success: bool
    category: Optional[str] = None
    reasoning: Optional[str] = None
    error: Optional[str] = None

@dataclass
class BulkCategorizationResult:
    """Result of bulk AI categorization."""
    successful_count: int
    failed_count: int
    errors: List[str]
    results: List[CategorizationResult]

@dataclass
class LinkResult:
    """Result of account linking operation."""
    success: bool
    institution_name: str
    account_count: int
    error: Optional[str] = None

@dataclass
class SummaryStats:
    """Financial summary statistics."""
    total_transactions: int
    total_spending: float
    total_income: float
    net_flow: float
    date_range: Tuple[datetime, datetime]
    category_breakdown: Dict[str, float]
    monthly_trends: Dict[str, float]

@dataclass
class CleanupOptions:
    """Options for data cleanup operations."""
    remove_old_pending_days: Optional[int] = 7
    remove_duplicates: bool = False
    validate_data_integrity: bool = True

@dataclass
class CleanupResult:
    """Result of cleanup operation."""
    removed_pending: int
    removed_duplicates: int
    fixed_data_issues: int
    errors: List[str]