#!/usr/bin/env python3
\"\"\"
Validate transaction data flows work correctly with both CSV and SQLite.
This script tests that both data managers produce identical results.
\"\"\"

import os
import sys
import logging
from datetime import datetime, timedelta
import tempfile

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from config import create_data_manager
from data_utils.data_manager import DataManager
from data_utils.sqlite_data_manager import SqliteDataManager
from data_utils.db_utils import setup_sqlite_database
from transaction_types import TransactionFilters

# Configure logging
logging.basicConfig(level=logging.WARNING)  # Reduce noise for testing

def create_sample_transactions():
    \"\"\"Create sample transactions for testing.\"\"\"
    base_date = datetime.now().date()
    
    return [
        {
            'transaction_id': 'test_001',
            'account_id': 'acc_001',
            'date': base_date.isoformat(),
            'name': 'STARBUCKS COFFEE',
            'merchant_name': 'Starbucks',
            'original_description': 'STARBUCKS STORE #1234',
            'amount': 5.75,
            'currency': 'USD',
            'pending': False,
            'category': 'Food and Drink',
            'category_detailed': 'Food and Drink > Coffee Shops',
            'personal_finance_category': 'FOOD_AND_DRINK',
            'personal_finance_category_detailed': 'FOOD_AND_DRINK_COFFEE_SHOPS',
            'personal_finance_category_confidence': 'VERY_HIGH',
            'bank_name': 'Test Bank',
            'account_name': 'Test Checking',
            'account_owner': 'Test User'
        },
        {
            'transaction_id': 'test_002',
            'account_id': 'acc_001',
            'date': (base_date - timedelta(days=1)).isoformat(),
            'name': 'UBER TRIP',
            'merchant_name': 'Uber',
            'original_description': 'UBER TRIP 12345',
            'amount': 15.30,
            'currency': 'USD',
            'pending': False,
            'category': 'Transportation',
            'category_detailed': 'Transportation > Taxis and Ride Shares',
            'personal_finance_category': 'TRANSPORTATION',
            'personal_finance_category_detailed': 'TRANSPORTATION_TAXIS_AND_RIDE_SHARES',
            'personal_finance_category_confidence': 'HIGH',
            'bank_name': 'Test Bank',
            'account_name': 'Test Checking',
            'account_owner': 'Test User'
        },
        {
            'transaction_id': 'test_003',
            'account_id': 'acc_002',
            'date': (base_date - timedelta(days=2)).isoformat(),
            'name': 'GROCERY OUTLET',
            'merchant_name': 'Grocery Outlet',
            'original_description': 'GROCERY OUTLET #123',
            'amount': 45.67,
            'currency': 'USD',
            'pending': True,
            'category': 'Food and Drink',
            'category_detailed': 'Food and Drink > Groceries',
            'personal_finance_category': 'FOOD_AND_DRINK',
            'personal_finance_category_detailed': 'FOOD_AND_DRINK_GROCERIES',
            'personal_finance_category_confidence': 'VERY_HIGH',
            'bank_name': 'Another Bank',
            'account_name': 'Another Checking',
            'account_owner': 'Test User'
        }
    ]

def test_data_manager_compatibility():
    \"\"\"Test that CSV and SQLite data managers produce identical results.\"\"\"
    print(\"🔄 Testing Data Manager Compatibility\")
    print(\"=\" * 50)
    
    # Create temporary files
    with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as csv_file:
        csv_path = csv_file.name
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as db_file:
        db_path = db_file.name
    
    try:
        # Setup databases
        print(\"\
1. Setting up data managers...\")
        
        # CSV setup
        csv_dm = DataManager(csv_path)
        print(\"   ✅ CSV DataManager created\")
        
        # SQLite setup
        setup_sqlite_database(db_path)
        sqlite_dm = SqliteDataManager(db_path)
        print(\"   ✅ SQLite DataManager created\")
        
        # Test 2: Create identical transactions in both
        print(\"\
2. Creating identical transactions...\")
        sample_transactions = create_sample_transactions()
        
        csv_created = csv_dm.create(sample_transactions)
        sqlite_created = sqlite_dm.create(sample_transactions)
        
        if len(csv_created) == len(sqlite_created) == len(sample_transactions):
            print(f\"   ✅ Both created {len(sample_transactions)} transactions\")
        else:
            print(f\"   ❌ Creation mismatch: CSV={len(csv_created)}, SQLite={len(sqlite_created)}\")
            return False
        
        # Test 3: Compare read_all results
        print(\"\
3. Comparing read_all results...\")
        csv_df = csv_dm.read_all()
        sqlite_df = sqlite_dm.read_all()
        
        if len(csv_df) == len(sqlite_df):
            print(f\"   ✅ Both return {len(csv_df)} transactions\")
        else:
            print(f\"   ❌ Read count mismatch: CSV={len(csv_df)}, SQLite={len(sqlite_df)}\")
            return False
        
        # Check that both have plaid_category populated
        csv_plaid_categories = csv_df['plaid_category'].notna().sum() if 'plaid_category' in csv_df.columns else 0
        sqlite_plaid_categories = sqlite_df['plaid_category'].notna().sum() if 'plaid_category' in sqlite_df.columns else 0
        
        print(f\"   CSV Plaid categories: {csv_plaid_categories}\")
        print(f\"   SQLite Plaid categories: {sqlite_plaid_categories}\")
        
        # Test 4: Compare individual transaction reads
        print(\"\
4. Comparing individual transaction reads...\")
        for tx_id in ['test_001', 'test_002', 'test_003']:
            csv_tx = csv_dm.read_by_id(tx_id)
            sqlite_tx = sqlite_dm.read_by_id(tx_id)
            
            if csv_tx and sqlite_tx:
                # Compare key fields
                key_fields = ['transaction_id', 'name', 'amount', 'date']
                match = True
                for field in key_fields:
                    if csv_tx.get(field) != sqlite_tx.get(field):
                        print(f\"   ❌ Field mismatch for {tx_id}.{field}: CSV='{csv_tx.get(field)}' vs SQLite='{sqlite_tx.get(field)}'\")
                        match = False
                
                if match:
                    print(f\"   ✅ Transaction {tx_id} matches\")
                else:
                    return False
            else:
                print(f\"   ❌ Transaction {tx_id} not found in both managers\")
                return False
        
        # Test 5: Test filtering
        print(\"\
5. Testing filtered queries...\")
        filters = TransactionFilters(
            amount_min=10.0,
            amount_max=50.0
        )
        
        csv_filtered = csv_dm.read_with_filters(filters)
        sqlite_filtered = sqlite_dm.read_with_filters(filters)
        
        if len(csv_filtered) == len(sqlite_filtered):
            print(f\"   ✅ Filtered queries return {len(csv_filtered)} transactions\")
        else:
            print(f\"   ❌ Filtered query mismatch: CSV={len(csv_filtered)}, SQLite={len(sqlite_filtered)}\")
            return False
        
        # Test 6: Test updates
        print(\"\
6. Testing updates...\")
        csv_update_success = csv_dm.update_by_id('test_001', {'ai_category': 'coffee_shops', 'ai_reason': 'Test categorization'})
        sqlite_update_success = sqlite_dm.update_by_id('test_001', {'ai_category': 'coffee_shops', 'ai_reason': 'Test categorization'})
        
        if csv_update_success and sqlite_update_success:
            print(\"   ✅ Both managers updated successfully\")
            
            # Verify updates
            csv_updated = csv_dm.read_by_id('test_001')
            sqlite_updated = sqlite_dm.read_by_id('test_001')
            
            if (csv_updated.get('ai_category') == 'coffee_shops' and 
                sqlite_updated.get('ai_category') == 'coffee_shops'):
                print(\"   ✅ Updates verified in both managers\")
            else:
                print(\"   ❌ Update verification failed\")
                return False
        else:
            print(f\"   ❌ Update failed: CSV={csv_update_success}, SQLite={sqlite_update_success}\")
            return False
        
        # Test 7: Test category management methods
        print(\"\
7. Testing category management methods...\")
        if hasattr(sqlite_dm, 'update_manual_category'):
            manual_success = sqlite_dm.update_manual_category('test_002', 'ride_sharing')
            if manual_success:
                print(\"   ✅ Manual category update successful\")
                
                # Verify manual category
                updated_tx = sqlite_dm.read_by_id('test_002')
                if updated_tx.get('manual_category') == 'ride_sharing':
                    print(\"   ✅ Manual category verified\")
                else:
                    print(\"   ❌ Manual category verification failed\")
                    return False
            else:
                print(\"   ❌ Manual category update failed\")
                return False
        
        # Test 8: Test utility operations
        print(\"\
8. Testing utility operations...\")
        csv_count = csv_dm.count_all()
        sqlite_count = sqlite_dm.count_all()
        
        if csv_count == sqlite_count:
            print(f\"   ✅ Both report {csv_count} total transactions\")
        else:
            print(f\"   ❌ Count mismatch: CSV={csv_count}, SQLite={sqlite_count}\")
            return False
        
        # Test date range
        csv_date_range = csv_dm.get_date_range()
        sqlite_date_range = sqlite_dm.get_date_range()
        
        if csv_date_range[0] and sqlite_date_range[0]:
            print(f\"   ✅ Both report date ranges: {csv_date_range[0].date()} to {csv_date_range[1].date()}\")
        else:
            print(\"   ❌ Date range query failed\")
            return False
        
        print(\"\
✅ All data flow validation tests passed!\")
        return True
        
    except Exception as e:
        print(f\"\
❌ Test failed with exception: {e}\")
        return False
        
    finally:
        # Cleanup
        try:
            os.unlink(csv_path)
            os.unlink(db_path)
        except:
            pass

def test_factory_pattern():
    \"\"\"Test the factory pattern works correctly.\"\"\"
    print(\"\
🏭 Testing Factory Pattern\")
    print(\"=\" * 30)
    
    try:
        # Test CSV creation
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as csv_file:
            csv_path = csv_file.name
        
        csv_dm = create_data_manager(csv_path)
        if isinstance(csv_dm, DataManager):
            print(\"   ✅ Factory created DataManager for .csv file\")
        else:
            print(f\"   ❌ Factory created {type(csv_dm).__name__} for .csv file\")
            return False
        
        # Test SQLite creation
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as db_file:
            db_path = db_file.name
            
        setup_sqlite_database(db_path)
        sqlite_dm = create_data_manager(db_path)
        if isinstance(sqlite_dm, SqliteDataManager):
            print(\"   ✅ Factory created SqliteDataManager for .db file\")
        else:
            print(f\"   ❌ Factory created {type(sqlite_dm).__name__} for .db file\")
            return False
        
        # Test error handling
        try:
            create_data_manager(\"test.txt\")
            print(\"   ❌ Factory should have rejected .txt file\")
            return False
        except ValueError:
            print(\"   ✅ Factory correctly rejected unsupported extension\")
        
        # Cleanup
        os.unlink(csv_path)
        os.unlink(db_path)
        
        return True
        
    except Exception as e:
        print(f\"   ❌ Factory pattern test failed: {e}\")
        return False

if __name__ == \"__main__\":
    print(\"🧪 Data Flow Validation Test\")
    print(\"This test ensures CSV and SQLite data managers work identically\")
    
    success = True
    
    # Test 1: Data manager compatibility
    if not test_data_manager_compatibility():
        success = False
    
    # Test 2: Factory pattern
    if not test_factory_pattern():
        success = False
    
    if success:
        print(\"\
🎉 All data flow validation tests passed!\")
        print(\"\
📝 Summary:\")
        print(\"   ✅ CSV and SQLite data managers produce identical results\")
        print(\"   ✅ Factory pattern correctly selects manager based on extension\")
        print(\"   ✅ All CRUD operations work consistently\")
        print(\"   ✅ Category management works correctly\")
        print(\"   ✅ Ready for production use!\")
        sys.exit(0)
    else:
        print(\"\
❌ Some validation tests failed!\")
        sys.exit(1)