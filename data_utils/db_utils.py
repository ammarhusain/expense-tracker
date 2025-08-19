"""
Database utilities for SQLite setup, validation, and maintenance.
"""

import sqlite3
import os
import logging
from typing import Dict, List, Tuple
from config import config

logger = logging.getLogger(__name__)

def setup_sqlite_database(db_path: str = None) -> bool:
    """
    Create fresh SQLite database - ready for fresh sync from Plaid API.
    
    Process:
    1. Create database schema (tables + indexes)
    2. Initialize with empty tables
    3. Ready for fresh sync from Plaid API
    
    Args:
        db_path: Path to database file. If None, uses config.data_path (if .db)
        
    Returns:
        bool: True if setup successful, False otherwise
    """
    if db_path is None:
        if config.data_path.endswith('.db'):
            db_path = config.data_path
        else:
            db_path = config.sqlite_db_path  # fallback to legacy property
    
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        # Read schema from file
        schema_path = os.path.join(os.path.dirname(__file__), 'db_schema.sql')
        if not os.path.exists(schema_path):
            logger.error(f"Schema file not found: {schema_path}")
            return False
            
        with open(schema_path, 'r') as f:
            schema_sql = f.read()
        
        # Create database and execute schema
        conn = sqlite3.connect(db_path)
        try:
            # Execute schema using executescript for proper handling of complex SQL
            conn.executescript(schema_sql)
            
            logger.info(f"SQLite database created successfully at {db_path}")
            return True
            
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Database setup failed: {e}")
        return False

def validate_database_schema(db_path: str = None) -> bool:
    """
    Validate SQLite database schema matches expected structure.
    
    Args:
        db_path: Path to database file. If None, uses config.data_path (if .db)
        
    Returns:
        bool: True if schema is valid, False otherwise
    """
    if db_path is None:
        if config.data_path.endswith('.db'):
            db_path = config.data_path
        else:
            db_path = config.sqlite_db_path  # fallback to legacy property
    
    if not os.path.exists(db_path):
        logger.error(f"Database file does not exist: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        try:
            # Check required tables exist
            required_tables = ['accounts', 'transactions']
            existing_tables = get_table_names(conn)
            
            for table in required_tables:
                if table not in existing_tables:
                    logger.error(f"Required table missing: {table}")
                    return False
            
            # Validate accounts table structure
            if not _validate_accounts_table(conn):
                return False
                
            # Validate transactions table structure
            if not _validate_transactions_table(conn):
                return False
            
            # Check indexes exist
            if not _validate_indexes(conn):
                return False
            
            logger.info("Database schema validation passed")
            return True
            
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Schema validation failed: {e}")
        return False

def get_database_stats(db_path: str = None) -> Dict:
    """
    Get database statistics and information.
    
    Args:
        db_path: Path to database file. If None, uses config.data_path (if .db)
        
    Returns:
        Dict: Database statistics
    """
    if db_path is None:
        if config.data_path.endswith('.db'):
            db_path = config.data_path
        else:
            db_path = config.sqlite_db_path  # fallback to legacy property
    
    if not os.path.exists(db_path):
        return {"error": "Database file does not exist"}
    
    try:
        conn = sqlite3.connect(db_path)
        try:
            stats = {}
            
            # File size
            stats['file_size_mb'] = round(os.path.getsize(db_path) / (1024 * 1024), 2)
            
            # Table counts
            cursor = conn.execute("SELECT COUNT(*) FROM accounts")
            stats['account_count'] = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM transactions")
            stats['transaction_count'] = cursor.fetchone()[0]
            
            # Date range
            cursor = conn.execute("SELECT MIN(date), MAX(date) FROM transactions")
            result = cursor.fetchone()
            if result[0] and result[1]:
                stats['date_range'] = {
                    'earliest': result[0],
                    'latest': result[1]
                }
            
            # Category statistics
            cursor = conn.execute("""
                SELECT 
                    COUNT(CASE WHEN plaid_category IS NOT NULL AND plaid_category != '' THEN 1 END) as plaid_categorized,
                    COUNT(CASE WHEN ai_category IS NOT NULL AND ai_category != '' THEN 1 END) as ai_categorized,
                    COUNT(CASE WHEN manual_category IS NOT NULL AND manual_category != '' THEN 1 END) as manual_categorized
                FROM transactions
            """)
            result = cursor.fetchone()
            stats['categorization'] = {
                'plaid_categorized': result[0],
                'ai_categorized': result[1], 
                'manual_categorized': result[2]
            }
            
            return stats
            
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error getting database stats: {e}")
        return {"error": str(e)}

def backup_database(db_path: str = None, backup_path: str = None) -> bool:
    """
    Create a backup of the SQLite database.
    
    Args:
        db_path: Source database path. If None, uses config.data_path (if .db)
        backup_path: Backup file path. If None, creates timestamped backup
        
    Returns:
        bool: True if backup successful, False otherwise
    """
    if db_path is None:
        if config.data_path.endswith('.db'):
            db_path = config.data_path
        else:
            db_path = config.sqlite_db_path  # fallback to legacy property
    
    if not os.path.exists(db_path):
        logger.error(f"Source database does not exist: {db_path}")
        return False
    
    if backup_path is None:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{db_path}.backup_{timestamp}"
    
    try:
        # Ensure backup directory exists
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        
        # Create backup using SQLite backup API
        source_conn = sqlite3.connect(db_path)
        backup_conn = sqlite3.connect(backup_path)
        
        try:
            source_conn.backup(backup_conn)
            logger.info(f"Database backed up to: {backup_path}")
            return True
            
        finally:
            source_conn.close()
            backup_conn.close()
            
    except Exception as e:
        logger.error(f"Database backup failed: {e}")
        return False

def optimize_database(db_path: str = None) -> bool:
    """
    Optimize database by running VACUUM and ANALYZE.
    
    Args:
        db_path: Database path. If None, uses config.data_path (if .db)
        
    Returns:
        bool: True if optimization successful, False otherwise
    """
    if db_path is None:
        if config.data_path.endswith('.db'):
            db_path = config.data_path
        else:
            db_path = config.sqlite_db_path  # fallback to legacy property
    
    if not os.path.exists(db_path):
        logger.error(f"Database does not exist: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        try:
            logger.info("Running database optimization...")
            
            # VACUUM reclaims space and defragments
            conn.execute("VACUUM")
            
            # ANALYZE updates query planner statistics
            conn.execute("ANALYZE")
            
            logger.info("Database optimization completed")
            return True
            
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Database optimization failed: {e}")
        return False

# Helper functions

def get_table_names(conn: sqlite3.Connection) -> List[str]:
    """Get list of table names in database."""
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return [row[0] for row in cursor.fetchall()]

def get_table_columns(conn: sqlite3.Connection, table_name: str) -> List[Tuple[str, str]]:
    """Get list of (column_name, column_type) for a table."""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    return [(row[1], row[2]) for row in cursor.fetchall()]

def _validate_accounts_table(conn: sqlite3.Connection) -> bool:
    """Validate accounts table has required columns."""
    required_columns = {
        'id': 'TEXT',
        'bank_name': 'TEXT',
        'account_name': 'TEXT',
        'account_owner': 'TEXT',
        'created_at': 'TEXT',
        'updated_at': 'TEXT'
    }
    
    actual_columns = dict(get_table_columns(conn, 'accounts'))
    
    for col_name in required_columns:
        if col_name not in actual_columns:
            logger.error(f"accounts table missing column: {col_name}")
            return False
    
    return True

def _validate_transactions_table(conn: sqlite3.Connection) -> bool:
    """Validate transactions table has required columns."""
    required_columns = {
        'transaction_id': 'TEXT',
        'account_id': 'TEXT',
        'date': 'TEXT',
        'amount': 'REAL',
        'plaid_category': 'TEXT',
        'ai_category': 'TEXT',
        'manual_category': 'TEXT',
        'created_at': 'TEXT',
        'updated_at': 'TEXT'
    }
    
    actual_columns = dict(get_table_columns(conn, 'transactions'))
    
    for col_name in required_columns:
        if col_name not in actual_columns:
            logger.error(f"transactions table missing column: {col_name}")
            return False
    
    return True

def _validate_indexes(conn: sqlite3.Connection) -> bool:
    """Validate required indexes exist."""
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
    existing_indexes = {row[0] for row in cursor.fetchall()}
    
    # Key indexes for performance
    required_indexes = {
        'idx_transactions_date',
        'idx_transactions_account',
        'idx_transactions_ai_category',
        'idx_transactions_manual_category'
    }
    
    missing_indexes = required_indexes - existing_indexes
    if missing_indexes:
        logger.warning(f"Missing indexes: {missing_indexes}")
        # Don't fail validation for missing indexes, just warn
    
    return True

# CLI utility functions (for manual database management)

def init_database_cli():
    """CLI command to initialize database."""
    print("Initializing SQLite database...")
    success = setup_sqlite_database()
    if success:
        print("✅ Database initialized successfully")
        stats = get_database_stats()
        print(f"Database location: {config.data_path}")
        print(f"File size: {stats.get('file_size_mb', 0)} MB")
        return True
    else:
        print("❌ Database initialization failed")
        return False

def validate_database_cli():
    """CLI command to validate database."""
    print("Validating database schema...")
    success = validate_database_schema()
    if success:
        print("✅ Database schema is valid")
        stats = get_database_stats()
        print(f"Accounts: {stats.get('account_count', 0)}")
        print(f"Transactions: {stats.get('transaction_count', 0)}")
    else:
        print("❌ Database schema validation failed")
    return success

def stats_database_cli():
    """CLI command to show database statistics."""
    stats = get_database_stats()
    
    if 'error' in stats:
        print(f"❌ Error: {stats['error']}")
        return False
    
    print("📊 Database Statistics:")
    print(f"File size: {stats.get('file_size_mb', 0)} MB")
    print(f"Accounts: {stats.get('account_count', 0)}")
    print(f"Transactions: {stats.get('transaction_count', 0)}")
    
    if 'date_range' in stats:
        date_range = stats['date_range']
        print(f"Date range: {date_range['earliest']} to {date_range['latest']}")
    
    if 'categorization' in stats:
        cat_stats = stats['categorization']
        print("Categorization:")
        print(f"  Plaid: {cat_stats['plaid_categorized']}")
        print(f"  AI: {cat_stats['ai_categorized']}")
        print(f"  Manual: {cat_stats['manual_categorized']}")
    
    return True

def optimize_database(db_path: str = None) -> bool:
    """
    Apply performance optimizations to the SQLite database.
    
    Args:
        db_path: Database path. If None, uses config.data_path (if .db)
        
    Returns:
        bool: True if optimization successful, False otherwise
    """
    if db_path is None:
        from config import config
        if not config.data_path.endswith('.db'):
            logger.error("DATA_PATH is not a SQLite database (.db)")
            return False
        db_path = config.data_path
    
    if not os.path.exists(db_path):
        logger.error(f"Database does not exist: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path, timeout=30.0)
        
        try:
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
                
                logger.info("Applied performance optimization indexes")
            
            # Run ANALYZE to update query planner statistics
            conn.execute("ANALYZE")
            logger.info("Updated query planner statistics")
            
            # Run VACUUM to optimize database file
            conn.execute("VACUUM")
            logger.info("Optimized database file structure")
            
            conn.commit()
            logger.info("Database optimization completed successfully")
            return True
            
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error optimizing database: {e}")
        return False

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python db_utils.py [init|validate|stats|backup|optimize]")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "init":
        success = init_database_cli()
    elif command == "validate":
        success = validate_database_cli()
    elif command == "stats":
        success = stats_database_cli()
    elif command == "backup":
        success = backup_database()
        print("✅ Database backup created" if success else "❌ Backup failed")
    elif command == "optimize":
        success = optimize_database()
        print("✅ Database optimized" if success else "❌ Optimization failed")
    else:
        print(f"Unknown command: {command}")
        success = False
    
    sys.exit(0 if success else 1)