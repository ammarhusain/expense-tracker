from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Tuple, Union
import pandas as pd

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