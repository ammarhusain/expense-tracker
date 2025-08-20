import sqlite3
import pandas as pd
import os
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any
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
                # Execute schema - SQLite executescript handles multiple statements better
                conn.executescript(schema_sql)
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
            -- Category columns
            t.plaid_category,
            t.ai_category,
            t.ai_reason,
            t.manual_category,
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
        Create or update transactions (upsert behavior).
        
        If transaction_id already exists, updates the record with new data.
        If transaction_id is new, inserts a new record.
        
        Returns list of transaction IDs that were either created or updated.
        """
        if not transactions:
            return []
        
        processed_ids = []
        created_count = 0
        updated_count = 0
        
        with self._get_connection() as conn:
            try:
                conn.execute("BEGIN TRANSACTION")
                
                for transaction in transactions:
                    transaction_id = transaction.get('transaction_id')
                    if not transaction_id:
                        continue
                    
                    # Ensure account exists
                    account_id = transaction.get('account_id')
                    if account_id:
                        self._ensure_account_exists(conn, transaction)
                    
                    # Check if transaction already exists
                    if self._transaction_exists(conn, transaction_id):
                        # Update existing transaction with new data
                        if self._update_existing_transaction(conn, transaction):
                            updated_count += 1
                            processed_ids.append(transaction_id)
                    else:
                        # Insert new transaction
                        self._insert_transaction_with_categories(conn, transaction)
                        created_count += 1
                        processed_ids.append(transaction_id)
                
                conn.execute("COMMIT")
                self.logger.info(f"Processed {len(processed_ids)} transactions: {created_count} created, {updated_count} updated")
                
            except Exception as e:
                conn.execute("ROLLBACK")
                self.logger.error(f"Error processing transactions: {e}")
                processed_ids = []
        
        return processed_ids
    
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
        """Ensure account exists, create if needed (fallback for accounts not created during linking)."""
        account_id = transaction.get('account_id')
        if not account_id:
            return
        
        # Check if account exists
        cursor = conn.execute("SELECT 1 FROM accounts WHERE id = ?", (account_id,))
        if cursor.fetchone():
            return
        
        # Create account with fallback data (should rarely happen if linking works properly)
        bank_name = transaction.get('bank_name', 'Unknown Bank')
        account_name = transaction.get('account_name') or f"Account {account_id[-4:]}"  # Use last 4 chars of ID
        
        account_data = {
            'id': account_id,
            'bank_name': bank_name,
            'account_name': account_name,
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
        
        self.logger.warning(f"Created fallback account {account_id}: {account_name} (should have been created during linking)")
    
    # Institution Management Methods (replaces access_tokens.json)
    
    def create_institution(self, institution_name: str, access_token: str) -> bool:
        """Create a new institution record."""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO institutions (id, access_token)
                    VALUES (?, ?)
                """, (institution_name, access_token))
                conn.commit()
                self.logger.info(f"Created institution: {institution_name}")
                return True
        except Exception as e:
            self.logger.error(f"Error creating institution {institution_name}: {e}")
            return False
    
    def get_institution_access_token(self, institution_id: str) -> Optional[str]:
        """Get access token for an institution."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT access_token FROM institutions WHERE id = ?", 
                    (institution_id,)
                )
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            self.logger.error(f"Error getting access token for {institution_id}: {e}")
            return None
    
    def update_institution_cursor(self, institution_id: str, cursor: str) -> bool:
        """Update sync cursor for an institution."""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    UPDATE institutions 
                    SET cursor = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (cursor, institution_id))
                conn.commit()
                return True
        except Exception as e:
            self.logger.error(f"Error updating cursor for {institution_id}: {e}")
            return False
    
    def update_institution_last_sync(self, institution_id: str, last_sync: str) -> bool:
        """Update last sync timestamp for an institution."""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    UPDATE institutions 
                    SET last_sync = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (last_sync, institution_id))
                conn.commit()
                return True
        except Exception as e:
            self.logger.error(f"Error updating last sync for {institution_id}: {e}")
            return False
    
    def get_institution_cursor(self, institution_id: str) -> Optional[str]:
        """Get sync cursor for an institution."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT cursor FROM institutions WHERE id = ?", 
                    (institution_id,)
                )
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            self.logger.error(f"Error getting cursor for {institution_id}: {e}")
            return None
    
    def get_all_institutions(self) -> List[Dict]:
        """Get all institutions with their metadata."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT id, access_token, cursor, created_at, last_sync
                    FROM institutions
                    ORDER BY created_at DESC
                """)
                institutions = []
                for row in cursor.fetchall():
                    institutions.append({
                        'id': row[0],
                        'access_token': row[1],
                        'cursor': row[2],
                        'created_at': row[3],
                        'last_sync': row[4]
                    })
                return institutions
        except Exception as e:
            self.logger.error(f"Error getting institutions: {e}")
            return []
    
    def delete_institution(self, institution_id: str) -> bool:
        """Delete an institution and all its accounts (cascade)."""
        try:
            with self._get_connection() as conn:
                conn.execute("BEGIN TRANSACTION")
                
                # Delete accounts for this institution
                conn.execute("DELETE FROM accounts WHERE institution_id = ?", (institution_id,))
                
                # Delete the institution
                conn.execute("DELETE FROM institutions WHERE id = ?", (institution_id,))
                
                conn.execute("COMMIT")
                self.logger.info(f"Deleted institution {institution_id} and its accounts")
                return True
        except Exception as e:
            conn.execute("ROLLBACK")
            self.logger.error(f"Error deleting institution {institution_id}: {e}")
            return False
    
    # Enhanced Account Management Methods
    
    def create_accounts_from_plaid(self, institution_name: str, plaid_accounts: List[Dict]) -> int:
        """Create accounts in database from Plaid account data during linking."""
        if not plaid_accounts:
            return 0
        
        created_count = 0
        
        with self._get_connection() as conn:
            try:
                conn.execute("BEGIN TRANSACTION")
                
                for account in plaid_accounts:
                    account_id = account.get('account_id')
                    if not account_id:
                        continue
                    
                    # Check if account already exists
                    cursor = conn.execute("SELECT 1 FROM accounts WHERE id = ?", (account_id,))
                    if cursor.fetchone():
                        self.logger.info(f"Account {account_id} already exists, updating")
                        # Update existing account
                        self._update_account_from_plaid_data(conn, account, institution_name)
                        continue
                    
                    # Create new account with full Plaid data
                    account_name = (
                        account.get('official_name') or 
                        account.get('name') or 
                        f"{account.get('type', 'Unknown')} Account"
                    )
                    
                    conn.execute("""
                        INSERT INTO accounts (
                            id, institution_id, bank_name, account_name, official_name,
                            account_type, account_subtype, mask, balance_current,
                            balance_available, balance_limit, currency_code, account_owner
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        account_id,
                        institution_name,
                        institution_name,
                        account_name,
                        account.get('official_name'),
                        account.get('type'),
                        account.get('subtype'),
                        account.get('mask'),
                        account.get('balance_current'),
                        account.get('balance_available'),
                        account.get('balance_limit'),
                        account.get('currency_code', 'USD'),
                        ''  # account_owner not available from Plaid
                    ))
                    
                    created_count += 1
                    self.logger.info(f"Created account {account_id}: {account_name} at {institution_name}")
                
                conn.commit()
                self.logger.info(f"Successfully created/updated {created_count} accounts for {institution_name}")
                return created_count
                
            except Exception as e:
                conn.rollback()
                self.logger.error(f"Error creating accounts from Plaid data: {e}")
                raise
    
    def _update_account_from_plaid_data(self, conn, account: Dict, institution_name: str):
        """Update existing account with fresh Plaid data."""
        account_id = account.get('account_id')
        account_name = (
            account.get('official_name') or 
            account.get('name') or 
            f"{account.get('type', 'Unknown')} Account"
        )
        
        conn.execute("""
            UPDATE accounts SET
                account_name = ?, official_name = ?, account_type = ?,
                account_subtype = ?, mask = ?, balance_current = ?,
                balance_available = ?, balance_limit = ?, currency_code = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            account_name,
            account.get('official_name'),
            account.get('type'),
            account.get('subtype'),
            account.get('mask'),
            account.get('balance_current'),
            account.get('balance_available'),
            account.get('balance_limit'),
            account.get('currency_code', 'USD'),
            account_id
        ))
    
    def update_account_balances(self, account_id: str, balances: Dict) -> bool:
        """Update account balances from Plaid API."""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    UPDATE accounts SET
                        balance_current = ?,
                        balance_available = ?,
                        balance_limit = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (
                    balances.get('current'),
                    balances.get('available'),
                    balances.get('limit'),
                    account_id
                ))
                conn.commit()
                return True
        except Exception as e:
            self.logger.error(f"Error updating balances for account {account_id}: {e}")
            return False
    
    def get_accounts_by_institution(self, institution_id: str) -> List[Dict]:
        """Get all accounts for a specific institution."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT * FROM accounts 
                    WHERE institution_id = ? AND is_active = 1
                    ORDER BY account_name
                """, (institution_id,))
                
                accounts = []
                for row in cursor.fetchall():
                    # Convert sqlite3.Row to dict
                    account = dict(row)
                    accounts.append(account)
                return accounts
        except Exception as e:
            self.logger.error(f"Error getting accounts for institution {institution_id}: {e}")
            return []
    
    def get_all_accounts_with_institutions(self) -> Dict[str, Dict]:
        """Get all accounts grouped by institution (replaces JSON file structure)."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT 
                        i.id as institution_id,
                        i.created_at as institution_created_at,
                        i.last_sync,
                        a.id as account_id,
                        a.account_name,
                        a.official_name,
                        a.account_type,
                        a.account_subtype,
                        a.mask,
                        a.balance_current,
                        a.balance_available,
                        a.balance_limit,
                        a.currency_code
                    FROM institutions i
                    LEFT JOIN accounts a ON i.id = a.institution_id
                    WHERE a.is_active = 1 OR a.is_active IS NULL
                    ORDER BY i.id, a.account_name
                """)
                
                # Group accounts by institution
                institutions = {}
                for row in cursor.fetchall():
                    inst_id = row[0]
                    if inst_id not in institutions:
                        institutions[inst_id] = {
                            'created_at': row[1],
                            'last_sync': row[2],
                            'accounts': []
                        }
                    
                    # Add account if it exists (LEFT JOIN might have NULLs)
                    if row[3]:  # account_id exists
                        account = {
                            'account_id': row[3],           # a.id
                            'name': row[4],                # a.account_name
                            'official_name': row[5],       # a.official_name
                            'type': row[6],                # a.account_type
                            'subtype': row[7],             # a.account_subtype
                            'mask': row[8],                # a.mask
                            'balance_current': row[9],     # a.balance_current
                            'balance_available': row[10],  # a.balance_available
                            'balance_limit': row[11],      # a.balance_limit
                            'currency_code': row[12]       # a.currency_code
                        }
                        institutions[inst_id]['accounts'].append(account)
                
                return institutions
        except Exception as e:
            self.logger.error(f"Error getting accounts with institutions: {e}")
            return {}
    
    
    def _insert_transaction_with_categories(self, conn: sqlite3.Connection, transaction: Dict):
        """Insert transaction with all embedded category data."""
        
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
            transaction.get('plaid_category'),
            transaction.get('ai_category'),
            transaction.get('ai_reason'),
            transaction.get('manual_category'),
            transaction.get('notes'),
            transaction.get('tags')
        ))
    
    def _update_existing_transaction(self, conn: sqlite3.Connection, transaction: Dict) -> bool:
        """
        Update existing transaction with new data from Plaid.
        
        Only updates fields that may change from Plaid (like pending status, amounts, names).
        Preserves user-set fields like manual_category, notes, tags.
        
        Returns True if any fields were actually updated, False otherwise.
        """
        transaction_id = transaction.get('transaction_id')
        if not transaction_id:
            return False
        
        # Get current transaction data
        current = self.read_by_id(transaction_id)
        if not current:
            return False
        
        # Fields that can be updated from Plaid data
        updatable_fields = {
            'date': transaction.get('date'),
            'name': transaction.get('name'), 
            'merchant_name': transaction.get('merchant_name'),
            'original_description': transaction.get('original_description'),
            'amount': transaction.get('amount'),
            'currency': transaction.get('currency', 'USD'),
            'pending': transaction.get('pending', False),
            'transaction_type': transaction.get('transaction_type'),
            'location': transaction.get('location'),
            'payment_details': transaction.get('payment_details'),
            'website': transaction.get('website'),
            'check_number': transaction.get('check_number'),
            'plaid_category': transaction.get('plaid_category')
        }
        
        # Only update fields that have actually changed
        updates = {}
        for field, new_value in updatable_fields.items():
            current_value = current.get(field)
            
            # Handle None/empty string equivalence and type conversions
            if self._values_differ(current_value, new_value):
                updates[field] = new_value
        
        if not updates:
            # No changes detected
            return False
        
        # Add updated_at timestamp
        updates['updated_at'] = datetime.now().isoformat()
        
        # Build UPDATE query
        set_clauses = []
        params = []
        
        for field, value in updates.items():
            set_clauses.append(f"{field} = ?")
            params.append(value)
        
        params.append(transaction_id)
        
        query = f"""
            UPDATE transactions 
            SET {', '.join(set_clauses)}
            WHERE transaction_id = ?
        """
        
        cursor = conn.execute(query, params)
        
        if cursor.rowcount > 0:
            updated_fields = list(updates.keys())
            self.logger.info(f"Updated transaction {transaction_id} fields: {updated_fields}")
            return True
        
        return False
    
    def _values_differ(self, current_value, new_value) -> bool:
        """
        Check if two values are different, handling None/empty string equivalence
        and float precision for amounts.
        """
        # Handle None/empty string equivalence
        if not current_value and not new_value:
            return False
        
        if current_value is None:
            current_value = ""
        if new_value is None:
            new_value = ""
        
        # Convert to strings for comparison
        current_str = str(current_value).strip()
        new_str = str(new_value).strip()
        
        # For numeric values, handle float precision
        if self._is_numeric(current_str) and self._is_numeric(new_str):
            try:
                return abs(float(current_str) - float(new_str)) > 0.001
            except (ValueError, TypeError):
                pass
        
        return current_str != new_str
    
    def _is_numeric(self, value: str) -> bool:
        """Check if a string represents a numeric value."""
        try:
            float(value)
            return True
        except (ValueError, TypeError):
            return False
    
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
    
    def find_potential_transfers(self, transaction_id: str, amount: float, date: str, 
                               account_id: str, days_window: int = 3) -> List[Dict]:
        """
        Find transactions with matching amounts from different accounts within a date window.
        
        Args:
            transaction_id: Current transaction ID (to exclude from results)
            amount: Transaction amount to match (will look for opposite sign)
            date: Transaction date
            account_id: Current account ID (to exclude from results) 
            days_window: Days before/after to search (default 3)
        
        Returns:
            List of potential matching transactions with account info
        """
        try:
            # Look for opposite sign amount (if current is -500, look for +500)
            target_amount = -amount
            
            query = """
            SELECT 
                t.transaction_id,
                t.amount,
                t.date,
                t.name,
                t.merchant_name,
                a.bank_name,
                a.account_name,
                a.id as account_id
            FROM transactions t
            JOIN accounts a ON t.account_id = a.id
            WHERE t.transaction_id != ?
            AND t.account_id != ?
            AND ABS(t.amount - ?) < 0.01
            AND t.date BETWEEN date(?, '-{} days') AND date(?, '+{} days')
            ORDER BY ABS(julianday(t.date) - julianday(?)) ASC
            LIMIT 5
            """.format(days_window, days_window)
            
            params = [
                transaction_id,
                account_id, 
                target_amount,
                date, date,
                date
            ]
            
            with self._get_connection() as conn:
                cursor = conn.execute(query, params)
                matches = []
                for row in cursor.fetchall():
                    matches.append({
                        'transaction_id': row[0],
                        'amount': row[1],
                        'date': row[2],
                        'name': row[3],
                        'merchant_name': row[4],
                        'bank_name': row[5],
                        'account_name': row[6],
                        'account_id': row[7]
                    })
                return matches
                
        except Exception as e:
            self.logger.error(f"Error finding potential transfers: {e}")
            return []
    
    # Enhanced SQLite-specific features for Step 3
    
    def get_category_statistics(self, date_range: Tuple[Optional[datetime], Optional[datetime]] = None) -> Dict:
        """Get comprehensive category statistics with spending analysis."""
        try:
            with self._get_connection() as conn:
                where_clause = ""
                params = []
                
                if date_range and date_range[0] and date_range[1]:
                    where_clause = "WHERE date BETWEEN ? AND ?"
                    params = [date_range[0].date().isoformat(), date_range[1].date().isoformat()]
                
                # Category spending (positive amounts)
                spending_query = f"""
                    SELECT 
                        COALESCE(manual_category, ai_category, 'Uncategorized') as category,
                        COUNT(*) as transaction_count,
                        SUM(amount) as total_spent,
                        AVG(amount) as avg_amount,
                        MIN(amount) as min_amount,
                        MAX(amount) as max_amount,
                        MIN(date) as first_transaction,
                        MAX(date) as last_transaction
                    FROM transactions 
                    {where_clause} AND amount > 0
                    GROUP BY COALESCE(manual_category, ai_category, 'Uncategorized')
                    ORDER BY total_spent DESC
                """
                
                # Income analysis (negative amounts)
                income_query = f"""
                    SELECT 
                        COALESCE(manual_category, ai_category, 'Income') as category,
                        COUNT(*) as transaction_count,
                        SUM(ABS(amount)) as total_income,
                        AVG(ABS(amount)) as avg_amount
                    FROM transactions 
                    {where_clause} AND amount < 0
                    GROUP BY COALESCE(manual_category, ai_category, 'Income')
                    ORDER BY total_income DESC
                """
                
                # Monthly trends
                monthly_query = f"""
                    SELECT 
                        substr(date, 1, 7) as month,
                        COALESCE(manual_category, ai_category, 'Uncategorized') as category,
                        SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as spending,
                        SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as income,
                        COUNT(*) as transaction_count
                    FROM transactions 
                    {where_clause}
                    GROUP BY substr(date, 1, 7), COALESCE(manual_category, ai_category, 'Uncategorized')
                    ORDER BY month DESC, spending DESC
                """
                
                spending_stats = conn.execute(spending_query, params).fetchall()
                income_stats = conn.execute(income_query, params).fetchall()
                monthly_trends = conn.execute(monthly_query, params).fetchall()
                
                return {
                    'spending_by_category': [
                        {
                            'category': row[0],
                            'transaction_count': row[1],
                            'total_spent': round(row[2], 2),
                            'avg_amount': round(row[3], 2),
                            'min_amount': round(row[4], 2),
                            'max_amount': round(row[5], 2),
                            'first_transaction': row[6],
                            'last_transaction': row[7]
                        } for row in spending_stats
                    ],
                    'income_by_category': [
                        {
                            'category': row[0],
                            'transaction_count': row[1],
                            'total_income': round(row[2], 2),
                            'avg_amount': round(row[3], 2)
                        } for row in income_stats
                    ],
                    'monthly_trends': [
                        {
                            'month': row[0],
                            'category': row[1],
                            'spending': round(row[2], 2),
                            'income': round(row[3], 2),
                            'transaction_count': row[4]
                        } for row in monthly_trends
                    ]
                }
                
        except Exception as e:
            self.logger.error(f"Error getting category statistics: {e}")
            return {'spending_by_category': [], 'income_by_category': [], 'monthly_trends': []}
    
    def get_account_summaries(self) -> List[Dict]:
        """Get comprehensive account summaries with transaction statistics."""
        try:
            with self._get_connection() as conn:
                query = """
                    SELECT 
                        a.id,
                        a.bank_name,
                        a.account_name,
                        a.account_owner,
                        COUNT(t.transaction_id) as total_transactions,
                        SUM(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END) as total_spending,
                        SUM(CASE WHEN t.amount < 0 THEN ABS(t.amount) ELSE 0 END) as total_income,
                        AVG(t.amount) as avg_transaction,
                        MIN(t.date) as first_transaction_date,
                        MAX(t.date) as last_transaction_date,
                        SUM(CASE WHEN t.pending = 1 THEN 1 ELSE 0 END) as pending_count,
                        COUNT(CASE WHEN t.ai_category IS NOT NULL AND t.ai_category != '' THEN 1 END) as categorized_count,
                        COUNT(CASE WHEN t.manual_category IS NOT NULL AND t.manual_category != '' THEN 1 END) as manual_categorized_count
                    FROM accounts a
                    LEFT JOIN transactions t ON a.id = t.account_id
                    GROUP BY a.id, a.bank_name, a.account_name, a.account_owner
                    ORDER BY a.bank_name, a.account_name
                """
                
                rows = conn.execute(query).fetchall()
                
                summaries = []
                for row in rows:
                    net_flow = (row[7] or 0) * (row[4] or 0)  # avg_transaction * total_transactions
                    categorization_rate = (row[11] / row[4] * 100) if row[4] > 0 else 0
                    
                    summaries.append({
                        'account_id': row[0],
                        'bank_name': row[1],
                        'account_name': row[2],
                        'account_owner': row[3],
                        'total_transactions': row[4] or 0,
                        'total_spending': round(row[5] or 0, 2),
                        'total_income': round(row[6] or 0, 2),
                        'net_flow': round(net_flow, 2),
                        'avg_transaction': round(row[7] or 0, 2),
                        'first_transaction_date': row[8],
                        'last_transaction_date': row[9],
                        'pending_count': row[10] or 0,
                        'categorized_count': row[11] or 0,
                        'manual_categorized_count': row[12] or 0,
                        'categorization_rate': round(categorization_rate, 1)
                    })
                
                return summaries
                
        except Exception as e:
            self.logger.error(f"Error getting account summaries: {e}")
            return []
    
    def get_spending_trends(self, category: str = None, months: int = 12) -> Dict:
        """Get spending trends over time with optional category filtering."""
        try:
            with self._get_connection() as conn:
                where_clause = "WHERE amount > 0"
                params = []
                
                if category:
                    where_clause += " AND (manual_category = ? OR (manual_category IS NULL AND ai_category = ?))"
                    params = [category, category]
                
                # Monthly spending trend
                monthly_query = f"""
                    SELECT 
                        substr(date, 1, 7) as month,
                        COUNT(*) as transaction_count,
                        SUM(amount) as total_spending,
                        AVG(amount) as avg_transaction
                    FROM transactions 
                    {where_clause}
                    GROUP BY substr(date, 1, 7)
                    ORDER BY month DESC
                    LIMIT ?
                """
                
                params.append(months)
                
                # Weekly spending trend (last 12 weeks)
                weekly_query = f"""
                    SELECT 
                        strftime('%Y-W%W', date) as week,
                        COUNT(*) as transaction_count,
                        SUM(amount) as total_spending,
                        AVG(amount) as avg_transaction
                    FROM transactions 
                    {where_clause}
                    AND date >= date('now', '-84 days')
                    GROUP BY strftime('%Y-W%W', date)
                    ORDER BY week DESC
                """
                
                # Top merchants in the period
                merchant_query = f"""
                    SELECT 
                        merchant_name,
                        COUNT(*) as transaction_count,
                        SUM(amount) as total_spent,
                        AVG(amount) as avg_amount
                    FROM transactions 
                    {where_clause}
                    AND merchant_name IS NOT NULL
                    AND date >= date('now', '-{months * 30} days')
                    GROUP BY merchant_name
                    ORDER BY total_spent DESC
                    LIMIT 10
                """
                
                monthly_data = conn.execute(monthly_query, params[:-1] + [months]).fetchall()
                weekly_data = conn.execute(weekly_query, params[:-1] if category else []).fetchall()
                merchant_data = conn.execute(merchant_query, params[:-1] if category else []).fetchall()
                
                return {
                    'monthly_trends': [
                        {
                            'month': row[0],
                            'transaction_count': row[1],
                            'total_spending': round(row[2], 2),
                            'avg_transaction': round(row[3], 2)
                        } for row in monthly_data
                    ],
                    'weekly_trends': [
                        {
                            'week': row[0],
                            'transaction_count': row[1],
                            'total_spending': round(row[2], 2),
                            'avg_transaction': round(row[3], 2)
                        } for row in weekly_data
                    ],
                    'top_merchants': [
                        {
                            'merchant_name': row[0],
                            'transaction_count': row[1],
                            'total_spent': round(row[2], 2),
                            'avg_amount': round(row[3], 2)
                        } for row in merchant_data
                    ]
                }
                
        except Exception as e:
            self.logger.error(f"Error getting spending trends: {e}")
            return {'monthly_trends': [], 'weekly_trends': [], 'top_merchants': []}
    
    def optimize_database(self) -> Dict[str, Any]:
        """Run database optimization and return performance statistics."""
        try:
            with self._get_connection() as conn:
                # Apply performance optimizations
                optimization_sql_path = os.path.join(os.path.dirname(__file__), 'performance_optimization.sql')
                if os.path.exists(optimization_sql_path):
                    with open(optimization_sql_path, 'r') as f:
                        optimization_sql = f.read()
                    
                    # Execute each statement separately
                    for statement in optimization_sql.split(';'):
                        statement = statement.strip()
                        if statement:
                            conn.execute(statement)
                
                # Run ANALYZE to update query planner statistics
                conn.execute("ANALYZE")
                
                # Run VACUUM to optimize database file
                conn.execute("VACUUM")
                
                # Get database statistics
                file_size = os.path.getsize(self.db_path) / (1024 * 1024)  # MB
                
                # Index usage statistics
                index_query = """
                    SELECT name, sql 
                    FROM sqlite_master 
                    WHERE type = 'index' AND name NOT LIKE 'sqlite_%'
                    ORDER BY name
                """
                
                indexes = conn.execute(index_query).fetchall()
                
                # Table statistics
                table_stats = {}
                for table in ['accounts', 'transactions']:
                    count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    table_stats[table] = count
                
                return {
                    'optimization_applied': True,
                    'database_size_mb': round(file_size, 2),
                    'total_indexes': len(indexes),
                    'table_statistics': table_stats,
                    'indexes': [{'name': idx[0], 'sql': idx[1]} for idx in indexes]
                }
                
        except Exception as e:
            self.logger.error(f"Error optimizing database: {e}")
            return {
                'optimization_applied': False,
                'error': str(e),
                'database_size_mb': 0,
                'total_indexes': 0,
                'table_statistics': {},
                'indexes': []
            }