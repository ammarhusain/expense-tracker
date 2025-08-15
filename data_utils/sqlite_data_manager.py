import sqlite3
import pandas as pd
import os
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import logging
from contextlib import contextmanager
from config import config
from transaction_types import TransactionFilters

class SqliteDataManager:
    """
    SQLite-based data manager maintaining identical interface to CSV version.
    
    Key Features:
    - 100% API compatibility with existing DataManager
    - Connection management with proper cleanup
    - Transaction management for data integrity
    - Optimized queries with proper indexing
    - Simple 2-table schema (accounts + transactions)
    """
    
    def __init__(self, db_path: str = None):
        """Initialize with database path."""
        self.db_path = db_path or config.data_path
        if not self.db_path.endswith('.db'):
            raise ValueError(f"SqliteDataManager requires .db file, got: {self.db_path}")
        self.logger = logging.getLogger(__name__)
        self._ensure_database_exists()
    
    def _ensure_database_exists(self):
        """Create database with schema if it doesn't exist."""
        if not os.path.exists(self.db_path):
            self.logger.info(f"Creating new SQLite database at {self.db_path}")
            self._create_database_schema()
        else:
            self.logger.info(f"Using existing SQLite database at {self.db_path}")
    
    def _create_database_schema(self):
        """Create database schema from SQL file."""
        try:
            schema_path = os.path.join(os.path.dirname(__file__), 'db_schema.sql')
            with open(schema_path, 'r') as f:
                schema_sql = f.read()
            
            with self._get_connection() as conn:
                # Execute schema (split by semicolon for multiple statements)
                for statement in schema_sql.split(';'):
                    statement = statement.strip()
                    if statement:
                        conn.execute(statement)
                conn.commit()
            
            self.logger.info("Database schema created successfully")
            
        except Exception as e:
            self.logger.error(f"Error creating database schema: {e}")
            raise
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections with proper cleanup."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        try:
            yield conn
        finally:
            conn.close()
    
    # READ operations - maintaining identical interface to CSV DataManager
    
    def read_all(self) -> pd.DataFrame:
        """
        Return view matching CSV structure - simple 2-table JOIN.
        """
        query = """
        SELECT 
            t.transaction_id,
            t.date,
            t.name,
            t.merchant_name,
            t.original_description,
            t.amount,
            t.currency,
            t.pending,
            t.transaction_type,
            t.location,
            t.payment_details,
            t.website,
            t.check_number,
            -- Account info
            a.bank_name,
            a.account_name,
            a.account_owner,
            t.account_id,
            -- Category columns (for CSV compatibility)
            t.plaid_category as category,
            t.plaid_category as category_detailed,
            t.plaid_category as personal_finance_category,
            t.plaid_category as personal_finance_category_detailed,
            t.plaid_category as personal_finance_category_confidence,
            t.ai_category,
            t.ai_reason,
            t.manual_category as custom_category,
            -- Metadata
            t.notes,
            t.tags,
            t.created_at
        FROM transactions t
        JOIN accounts a ON t.account_id = a.id
        ORDER BY t.date DESC
        """
        
        with self._get_connection() as conn:
            return pd.read_sql_query(query, conn)
    
    def read_by_id(self, transaction_id: str) -> Optional[Dict]:
        """Read single transaction by ID."""
        try:
            query = """
            SELECT 
                t.*,
                a.bank_name,
                a.account_name,
                a.account_owner
            FROM transactions t
            JOIN accounts a ON t.account_id = a.id
            WHERE t.transaction_id = ?
            """
            
            with self._get_connection() as conn:
                cursor = conn.execute(query, (transaction_id,))
                row = cursor.fetchone()
                
                if row:
                    # Convert sqlite3.Row to dict and clean up None values
                    transaction = dict(row)
                    for key, value in transaction.items():
                        if value is None:
                            transaction[key] = ""
                    return transaction
                
                return None
                
        except Exception as e:
            self.logger.error(f"Error retrieving transaction {transaction_id}: {str(e)}")
            return None
    
    def read_by_date_range(self, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """Read transactions within date range."""
        query = """
        SELECT t.*, a.bank_name, a.account_name, a.account_owner
        FROM transactions t
        JOIN accounts a ON t.account_id = a.id
        WHERE t.date >= ? AND t.date <= ?
        ORDER BY t.date DESC
        """
        
        with self._get_connection() as conn:
            return pd.read_sql_query(
                query, 
                conn, 
                params=(start_date.isoformat(), end_date.isoformat())
            )
    
    def read_uncategorized(self, limit: int = None) -> pd.DataFrame:
        """Read transactions without AI categories."""
        query = """
        SELECT t.*, a.bank_name, a.account_name, a.account_owner
        FROM transactions t
        JOIN accounts a ON t.account_id = a.id
        WHERE (t.ai_category IS NULL OR t.ai_category = '')
        ORDER BY t.date DESC
        """
        
        if limit is not None:
            query += f" LIMIT {limit}"
        
        with self._get_connection() as conn:
            return pd.read_sql_query(query, conn)
    
    def read_with_filters(self, filters: TransactionFilters) -> pd.DataFrame:
        """
        Optimized filtering using WHERE clauses instead of pandas filtering.
        Significant performance improvement for large datasets.
        """
        where_conditions = []
        params = {}
        
        # Date filters
        if filters.date_start:
            where_conditions.append("t.date >= :date_start")
            params['date_start'] = filters.date_start.isoformat()
        
        if filters.date_end:
            where_conditions.append("t.date <= :date_end")
            params['date_end'] = filters.date_end.isoformat()
        
        # Bank filters
        if filters.banks:
            placeholders = ','.join([f':bank_{i}' for i in range(len(filters.banks))])
            where_conditions.append(f"a.bank_name IN ({placeholders})")
            for i, bank in enumerate(filters.banks):
                params[f'bank_{i}'] = bank
        
        # Amount filters
        if filters.amount_min is not None:
            where_conditions.append("t.amount >= :amount_min")
            params['amount_min'] = filters.amount_min
        
        if filters.amount_max is not None:
            where_conditions.append("t.amount <= :amount_max")
            params['amount_max'] = filters.amount_max
        
        # Pending filter
        if filters.pending_only is not None:
            where_conditions.append("t.pending = :pending")
            params['pending'] = filters.pending_only
        
        # Category filters (search within full structured strings)
        if filters.categories:
            category_conditions = []
            for i, category in enumerate(filters.categories):
                category_conditions.extend([
                    f"t.plaid_category LIKE '%{category}%'",  # Search anywhere in structured string
                    f"t.ai_category = :cat_{i}", 
                    f"t.manual_category = :cat_{i}"
                ])
                params[f'cat_{i}'] = category
            
            where_conditions.append(f"({' OR '.join(category_conditions)})")
        
        # Uncategorized filter (simple NULL checks)
        if filters.uncategorized_only:
            where_conditions.append("""
                (t.ai_category IS NULL OR t.ai_category = '') 
                AND (t.manual_category IS NULL OR t.manual_category = '')
                AND (t.plaid_category IS NULL OR t.plaid_category = '')
            """)
        
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
        
        query = f"""
        SELECT 
            t.*,
            a.bank_name,
            a.account_name,
            a.account_owner
        FROM transactions t
        JOIN accounts a ON t.account_id = a.id
        WHERE {where_clause}
        ORDER BY t.date DESC
        """
        
        with self._get_connection() as conn:
            return pd.read_sql_query(query, conn, params=params)
    
    # WRITE operations - maintaining identical interface
    
    def create(self, transactions: List[Dict]) -> List[str]:
        """
        Create transactions - much simpler with embedded categories!
        Direct INSERT with all category columns.
        """
        if not transactions:
            return []
        
        created_ids = []
        
        with self._get_connection() as conn:
            try:
                conn.execute("BEGIN TRANSACTION")
                
                for transaction in transactions:
                    transaction_id = transaction.get('transaction_id')
                    if not transaction_id:
                        continue
                    
                    # Check if transaction already exists
                    if self._transaction_exists(conn, transaction_id):
                        continue
                    
                    # Ensure account exists
                    account_id = transaction.get('account_id')
                    if account_id:
                        self._ensure_account_exists(conn, transaction)
                    
                    # Single INSERT with all data (much simpler!)
                    self._insert_transaction_with_categories(conn, transaction)
                    
                    created_ids.append(transaction_id)
                
                conn.execute("COMMIT")
                self.logger.info(f"Created {len(created_ids)} new transactions")
                
            except Exception as e:
                conn.execute("ROLLBACK")
                self.logger.error(f"Error creating transactions: {e}")
                created_ids = []
        
        return created_ids
    
    def update_by_id(self, transaction_id: str, updates: Dict) -> bool:
        """Update single transaction by ID."""
        try:
            if not updates:
                return False
            
            set_clauses = []
            params = []
            
            for field, value in updates.items():
                set_clauses.append(f"{field} = ?")
                params.append(value)
            
            # Add updated_at timestamp
            set_clauses.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            params.append(transaction_id)
            
            query = f"""
                UPDATE transactions 
                SET {', '.join(set_clauses)}
                WHERE transaction_id = ?
            """
            
            with self._get_connection() as conn:
                cursor = conn.execute(query, params)
                if cursor.rowcount > 0:
                    conn.commit()
                    self.logger.info(f"Updated transaction {transaction_id}")
                    return True
                else:
                    self.logger.error(f"Transaction {transaction_id} not found for update")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Error updating transaction {transaction_id}: {e}")
            return False
    
    def bulk_update(self, updates: Dict[str, Dict]) -> int:
        """
        Simplified bulk update - direct column updates.
        """
        if not updates:
            return 0
        
        updated_count = 0
        
        with self._get_connection() as conn:
            try:
                conn.execute("BEGIN TRANSACTION")
                
                # Simple batch updates - all columns in one table
                for tx_id, field_updates in updates.items():
                    if field_updates:
                        set_clauses = []
                        params = []
                        
                        for field, value in field_updates.items():
                            set_clauses.append(f"{field} = ?")
                            params.append(value)
                        
                        # Add updated_at timestamp
                        set_clauses.append("updated_at = ?")
                        params.append(datetime.now().isoformat())
                        params.append(tx_id)
                        
                        query = f"""
                            UPDATE transactions 
                            SET {', '.join(set_clauses)}
                            WHERE transaction_id = ?
                        """
                        
                        cursor = conn.execute(query, params)
                        if cursor.rowcount > 0:
                            updated_count += 1
                
                conn.execute("COMMIT")
                
            except Exception as e:
                conn.execute("ROLLBACK")
                self.logger.error(f"Error in bulk update: {e}")
                updated_count = 0
        
        return updated_count
    
    def delete_by_ids(self, transaction_ids: List[str]) -> int:
        """Delete transactions by IDs."""
        if not transaction_ids:
            return 0
        
        try:
            placeholders = ','.join(['?' for _ in transaction_ids])
            query = f"DELETE FROM transactions WHERE transaction_id IN ({placeholders})"
            
            with self._get_connection() as conn:
                cursor = conn.execute(query, transaction_ids)
                removed_count = cursor.rowcount
                conn.commit()
                
                if removed_count > 0:
                    self.logger.info(f"Removed {removed_count} transactions")
                
                return removed_count
                
        except Exception as e:
            self.logger.error(f"Error deleting transactions: {e}")
            return 0
    
    # UTILITY operations - maintaining identical interface
    
    def exists(self, transaction_id: str) -> bool:
        """Check if transaction exists."""
        return self.read_by_id(transaction_id) is not None
    
    def count_all(self) -> int:
        """Count total transactions."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM transactions")
                return cursor.fetchone()[0]
        except Exception as e:
            self.logger.error(f"Error counting transactions: {e}")
            return 0
    
    def get_date_range(self) -> Tuple[Optional[datetime], Optional[datetime]]:
        """Get min/max transaction dates."""
        try:
            query = "SELECT MIN(date), MAX(date) FROM transactions"
            
            with self._get_connection() as conn:
                cursor = conn.execute(query)
                result = cursor.fetchone()
                
                if result and result[0] and result[1]:
                    min_date = datetime.fromisoformat(result[0])
                    max_date = datetime.fromisoformat(result[1])
                    return min_date, max_date
                
                return None, None
                
        except Exception as e:
            self.logger.error(f"Error getting date range: {e}")
            return None, None
    
    def find_duplicates(self, transaction: Dict) -> List[str]:
        """
        Enhanced duplicate detection using database queries.
        Much faster than CSV scanning for large datasets.
        """
        query = """
        SELECT transaction_id 
        FROM transactions 
        WHERE ABS(amount - ?) < 0.01
        AND date BETWEEN date(?, '-3 days') AND date(?, '+3 days')
        AND (
            merchant_name LIKE '%' || ? || '%' OR
            name LIKE '%' || ? || '%' OR
            ? LIKE '%' || merchant_name || '%' OR
            ? LIKE '%' || name || '%'
        )
        """
        
        params = [
            transaction.get('amount', 0),
            transaction.get('date', ''),
            transaction.get('date', ''),
            transaction.get('merchant_name', ''),
            transaction.get('name', ''),
            transaction.get('merchant_name', ''),
            transaction.get('name', '')
        ]
        
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(query, params)
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"Error finding duplicates: {e}")
            return []
    
    # Helper methods
    
    def _transaction_exists(self, conn: sqlite3.Connection, transaction_id: str) -> bool:
        """Check if transaction exists using provided connection."""
        cursor = conn.execute("SELECT 1 FROM transactions WHERE transaction_id = ?", (transaction_id,))
        return cursor.fetchone() is not None
    
    def _ensure_account_exists(self, conn: sqlite3.Connection, transaction: Dict):
        """Ensure account exists, create if needed."""
        account_id = transaction.get('account_id')
        if not account_id:
            return
        
        # Check if account exists
        cursor = conn.execute("SELECT 1 FROM accounts WHERE id = ?", (account_id,))
        if cursor.fetchone():
            return
        
        # Create account
        account_data = {
            'id': account_id,
            'bank_name': transaction.get('bank_name', ''),
            'account_name': transaction.get('account_name', ''),
            'account_owner': transaction.get('account_owner', '')
        }
        
        conn.execute("""
            INSERT INTO accounts (id, bank_name, account_name, account_owner)
            VALUES (?, ?, ?, ?)
        """, (
            account_data['id'],
            account_data['bank_name'],
            account_data['account_name'],
            account_data['account_owner']
        ))
        
        self.logger.info(f"Created account {account_id}")
    
    def _insert_transaction_with_categories(self, conn: sqlite3.Connection, transaction: Dict):
        """Insert transaction with all embedded category data."""
        
        # Prepare plaid_category structured string
        plaid_category = self._format_plaid_category_string(transaction)
        
        conn.execute("""
            INSERT INTO transactions (
                transaction_id, account_id, date, name, merchant_name, original_description,
                amount, currency, pending, transaction_type, location, payment_details, 
                website, check_number, plaid_category, ai_category, ai_reason,
                manual_category, notes, tags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            transaction.get('transaction_id'),
            transaction.get('account_id'),
            transaction.get('date'),
            transaction.get('name'),
            transaction.get('merchant_name'),
            transaction.get('original_description'),
            transaction.get('amount'),
            transaction.get('currency', 'USD'),
            transaction.get('pending', False),
            transaction.get('transaction_type'),
            transaction.get('location'),
            transaction.get('payment_details'),
            transaction.get('website'),
            transaction.get('check_number'),
            plaid_category,
            transaction.get('ai_category'),
            transaction.get('ai_reason'),
            transaction.get('manual_category'),
            transaction.get('notes'),
            transaction.get('tags')
        ))
    
    def _format_plaid_category_string(self, transaction: Dict) -> str:
        """Format Plaid category data into structured string."""
        parts = []
        
        # Add legacy categories if present
        category = transaction.get('category')
        category_detailed = transaction.get('category_detailed')
        if category:
            parts.append(f"leg_cgr: {category}")
        if category_detailed:
            parts.append(f"leg_det: {category_detailed}")
        
        # Add personal finance categories if present
        pf_category = transaction.get('personal_finance_category')
        pf_detailed = transaction.get('personal_finance_category_detailed')
        pf_confidence = transaction.get('personal_finance_category_confidence')
        
        if pf_category:
            parts.append(f"cgr: {pf_category}")
        if pf_detailed:
            parts.append(f"det: {pf_detailed}")
        if pf_confidence:
            parts.append(f"cnf: {pf_confidence}")
        
        return ", ".join(parts) if parts else ""
    
    # Category Management - New simplified methods
    
    def update_ai_category(self, transaction_id: str, category: str, reason: str = None) -> bool:
        """Update AI category for a transaction."""
        updates = {'ai_category': category}
        if reason:
            updates['ai_reason'] = reason
        return self.update_by_id(transaction_id, updates)
    
    def update_manual_category(self, transaction_id: str, category: str) -> bool:
        """Set manual override category."""
        return self.update_by_id(transaction_id, {'manual_category': category})
    
    def get_effective_category(self, transaction: Dict) -> str:
        """Get effective category with precedence: Manual > AI > Plaid."""
        return (
            transaction.get('manual_category') or 
            transaction.get('ai_category') or 
            transaction.get('plaid_category') or  # Use full structured string
            'Uncategorized'
        )