#!/usr/bin/env python3
"""
Test script for SQLite database setup - Step 1 verification
"""

import os
import sys
import logging
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from config import config, create_data_manager
from data_utils.db_utils import setup_sqlite_database, validate_database_schema, get_database_stats
from data_utils.sqlite_data_manager import SqliteDataManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_database_setup():
    """Test database creation and schema validation."""
    print("🧪 Testing SQLite Database Setup")
    print("=" * 50)
    
    # Test 1: Database creation
    print("
1. Testing database setup...")
    test_db_path = "./test_transactions.db"
    
    # Clean up any existing test database
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    
    success = setup_sqlite_database(test_db_path)
    if success:
        print("✅ Database created successfully")
    else:
        print("❌ Database creation failed")
        return False
    
    # Test 2: Schema validation
    print("
2. Testing schema validation...")
    valid = validate_database_schema(test_db_path)
    if valid:
        print("✅ Schema validation passed")
    else:
        print("❌ Schema validation failed")
        return False
    
    # Test 3: Database stats
    print("
3. Testing database statistics...")
    stats = get_database_stats(test_db_path)
    if 'error' not in stats:
        print("✅ Database stats retrieved")
        print(f"   File size: {stats.get('file_size_mb', 0)} MB")
        print(f"   Accounts: {stats.get('account_count', 0)}")
        print(f"   Transactions: {stats.get('transaction_count', 0)}")
    else:
        print(f"❌ Database stats failed: {stats['error']}")
        return False
    
    # Test 4: SqliteDataManager instantiation
    print("
4. Testing SqliteDataManager...")
    try:
        data_manager = SqliteDataManager(test_db_path)
        print("✅ SqliteDataManager created successfully")
        
        # Test basic read operation
        df = data_manager.read_all()
        print(f"✅ read_all() returned DataFrame with {len(df)} rows")
        
        # Test count operation
        count = data_manager.count_all()
        print(f"✅ count_all() returned {count}")
        
    except Exception as e:
        print(f"❌ SqliteDataManager test failed: {e}")
        return False
    
    # Test 5: Factory pattern
    print("
5. Testing factory pattern...")
    try:
        # Test CSV mode
        dm_csv = create_data_manager("./test_transactions.csv")
        print(f"✅ Factory created CSV DataManager: {type(dm_csv).__name__}")
        
        # Test SQLite mode
        dm_sqlite = create_data_manager(test_db_path)
        print(f"✅ Factory created SQLite DataManager: {type(dm_sqlite).__name__}")
        
        # Test error handling
        try:
            create_data_manager("./test.txt")
            print("❌ Factory should have failed for .txt file")
            return False
        except ValueError as e:
            print(f"✅ Factory correctly rejected unsupported extension: {e}")
        
    except Exception as e:
        print(f"❌ Factory pattern test failed: {e}")
        return False
    
    # Test 6: Create sample account and transaction
    print("
6. Testing basic CRUD operations...")
    try:
        # Create sample account
        sample_account = {
            'id': 'test_account_123',
            'bank_name': 'Test Bank',
            'account_name': 'Test Checking',
            'account_owner': 'Test User'
        }
        
        # Create sample transaction
        sample_transaction = {
            'transaction_id': 'test_txn_123',
            'account_id': 'test_account_123',
            'date': datetime.now().date().isoformat(),
            'name': 'Test Transaction',
            'merchant_name': 'Test Merchant',
            'amount': 10.50,
            'category': 'Food and Drink',
            'category_detailed': 'Food and Drink > Restaurants',
            'personal_finance_category': 'FOOD_AND_DRINK',
            'personal_finance_category_detailed': 'FOOD_AND_DRINK_RESTAURANTS',
            'personal_finance_category_confidence': 'VERY_HIGH'
        }
        
        # Test create operation
        created_ids = data_manager.create([sample_transaction])
        if created_ids:
            print(f"✅ Created transaction: {created_ids[0]}")
        else:
            print("❌ Transaction creation failed")
            return False
        
        # Test read operation
        transaction = data_manager.read_by_id('test_txn_123')
        if transaction:
            print("✅ Retrieved transaction by ID")
            print(f"   Name: {transaction.get('name')}")
            print(f"   Amount: ${transaction.get('amount')}")
            print(f"   Plaid Category: {transaction.get('plaid_category')}")
        else:
            print("❌ Failed to retrieve transaction")
            return False
        
        # Test update operation
        update_result = data_manager.update_ai_category('test_txn_123', 'restaurants', 'AI detected restaurant transaction')
        if update_result:
            print("✅ Updated AI category")
        else:
            print("❌ AI category update failed")
            return False
        
        # Verify update
        updated_transaction = data_manager.read_by_id('test_txn_123')
        if updated_transaction and updated_transaction.get('ai_category') == 'restaurants':
            print("✅ AI category update verified")
        else:
            print("❌ AI category update verification failed")
            return False
        
    except Exception as e:
        print(f"❌ CRUD operations test failed: {e}")
        return False
    
    # Final stats
    print("
7. Final database statistics...")
    final_stats = get_database_stats(test_db_path)
    print(f"   Accounts: {final_stats.get('account_count', 0)}")
    print(f"   Transactions: {final_stats.get('transaction_count', 0)}")
    
    # Cleanup
    print("
8. Cleaning up test database...")
    try:
        os.remove(test_db_path)
        print("✅ Test database cleaned up")
    except Exception as e:
        print(f"⚠️  Cleanup warning: {e}")
    
    print("
🎉 All tests passed! SQLite setup is working correctly.")
    return True

if __name__ == "__main__":
    success = test_database_setup()
    sys.exit(0 if success else 1)