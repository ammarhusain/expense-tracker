#!/usr/bin/env python3
"""
Test fresh sync implementation with SQLite database.
This script tests the full flow: Plaid sync -> SQLite storage -> AI categorization
"""

import os
import sys
import logging
from datetime import datetime
from typing import Dict, Any

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from config import config, create_data_manager
from transaction_service import TransactionService
from plaid_client import PlaidClient
from data_utils.db_utils import setup_sqlite_database, get_database_stats

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_fresh_sync_to_sqlite():
    """Test fresh sync from Plaid API to SQLite database."""
    print("🔄 Testing Fresh Sync to SQLite")
    print("=" * 50)
    
    # Setup test database
    test_db_path = "./test_sync_transactions.db"
    
    # Clean up any existing test database
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    
    print("\
1. Setting up test SQLite database...")
    success = setup_sqlite_database(test_db_path)
    if not success:
        print("❌ Failed to setup database")
        return False
    print("✅ Test database created")
    
    # Create transaction service with SQLite data manager
    print("\
2. Creating TransactionService with SQLite...")
    try:
        # Force SQLite mode by specifying .db path
        data_manager = create_data_manager(test_db_path)
        transaction_service = TransactionService(data_manager=data_manager)
        print(f\"✅ Created TransactionService with {type(data_manager).__name__}\")
    except Exception as e:
        print(f\"❌ Failed to create TransactionService: {e}\")
        return False
    
    # Test 3: Check if we have any linked accounts
    print(\"\
3. Checking linked accounts...\")
    accounts = transaction_service.get_accounts()
    if not accounts:
        print(\"⚠️  No accounts linked - sync test will be limited\")
        print(\"   To fully test sync, link accounts using the Streamlit app first\")
        
        # Create mock transaction data to test the flow
        print(\"\
4. Testing with mock transaction data...\")
        success = test_mock_transaction_flow(transaction_service)
        if not success:
            return False
    else:
        print(f\"✅ Found {len(accounts)} linked institution(s)\")
        for institution_name, account_data in accounts.items():
            if 'error' in account_data:
                print(f\"   ❌ {institution_name}: {account_data['error']}\")
            else:
                account_count = len(account_data.get('accounts', []))
                last_sync = account_data.get('last_sync', 'Never')
                print(f\"   ✅ {institution_name}: {account_count} accounts, last sync: {last_sync}\")
        
        # Test 4: Perform actual sync
        print(\"\
4. Testing actual sync from Plaid...\")
        success = test_actual_sync(transaction_service)
        if not success:
            return False
    
    # Test 5: Verify database state
    print(\"\
5. Verifying database state...\")
    stats = get_database_stats(test_db_path)
    if 'error' in stats:
        print(f\"❌ Error getting database stats: {stats['error']}\")
        return False
    
    print(\"✅ Database statistics:\")
    print(f\"   File size: {stats.get('file_size_mb', 0)} MB\")
    print(f\"   Accounts: {stats.get('account_count', 0)}\")
    print(f\"   Transactions: {stats.get('transaction_count', 0)}\")
    
    categorization = stats.get('categorization', {})
    print(f\"   Plaid categorized: {categorization.get('plaid_categorized', 0)}\")
    print(f\"   AI categorized: {categorization.get('ai_categorized', 0)}\")
    print(f\"   Manual categorized: {categorization.get('manual_categorized', 0)}\")
    
    # Test 6: Test category management
    print(\"\
6. Testing category management...\")
    success = test_category_management(transaction_service)
    if not success:
        return False
    
    # Cleanup
    print(\"\
7. Cleaning up test database...\")
    try:
        os.remove(test_db_path)
        print(\"✅ Test database cleaned up\")
    except Exception as e:
        print(f\"⚠️  Cleanup warning: {e}\")
    
    print(\"\
🎉 Fresh sync test completed successfully!\")
    return True

def test_mock_transaction_flow(transaction_service: TransactionService) -> bool:
    \"\"\"Test the transaction flow with mock data.\"\"\"
    try:
        # Create mock transactions that mimic Plaid format
        mock_transactions = [
            {
                'transaction_id': 'mock_txn_001',
                'account_id': 'mock_account_001',
                'date': datetime.now().date().isoformat(),
                'name': 'STARBUCKS STORE #12345',
                'merchant_name': 'Starbucks',
                'original_description': 'STARBUCKS STORE #12345 SEATTLE WA',
                'amount': 5.75,
                'currency': 'USD',
                'pending': False,
                'category': 'Food and Drink',
                'category_detailed': 'Food and Drink > Coffee Shops',
                'personal_finance_category': 'FOOD_AND_DRINK',
                'personal_finance_category_detailed': 'FOOD_AND_DRINK_COFFEE_SHOPS',
                'personal_finance_category_confidence': 'VERY_HIGH',
                'bank_name': 'Test Bank',
                'account_name': 'Test Checking'
            },
            {
                'transaction_id': 'mock_txn_002',
                'account_id': 'mock_account_001',
                'date': datetime.now().date().isoformat(),
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
                'account_name': 'Test Checking'
            }
        ]
        
        # Create transactions using data manager directly
        created_ids = transaction_service.data_manager.create(mock_transactions)
        
        if created_ids:
            print(f\"✅ Created {len(created_ids)} mock transactions\")
            
            # Test reading transactions back
            for tx_id in created_ids:
                transaction = transaction_service.data_manager.read_by_id(tx_id)
                if transaction:
                    print(f\"   - {transaction.get('name')}: ${transaction.get('amount')} ({transaction.get('plaid_category', 'No plaid category')})\")
                else:
                    print(f\"   ❌ Failed to read back transaction {tx_id}\")
                    return False
            
            return True
        else:
            print(\"❌ Failed to create mock transactions\")
            return False
            
    except Exception as e:
        print(f\"❌ Mock transaction test failed: {e}\")
        return False

def test_actual_sync(transaction_service: TransactionService) -> bool:
    \"\"\"Test actual sync with Plaid API.\"\"\"
    try:
        # Get sync status before
        sync_status_before = transaction_service.get_sync_status()
        print(f\"   Sync status before: {len(sync_status_before)} institutions\")
        
        # Perform sync
        sync_result = transaction_service.sync_all_accounts(full_sync=False)
        
        if sync_result.success:
            print(f\"✅ Sync completed successfully\")
            print(f\"   New transactions: {sync_result.new_transactions}\")
            print(f\"   Updated transactions: {sync_result.updated_transactions}\")
            
            if sync_result.institution_results:
                for institution, count in sync_result.institution_results.items():
                    print(f\"   {institution}: {count} new transactions\")
            
            return True
        else:
            print(f\"❌ Sync failed: {sync_result.errors}\")
            return False
            
    except Exception as e:
        print(f\"❌ Actual sync test failed: {e}\")
        return False

def test_category_management(transaction_service: TransactionService) -> bool:
    \"\"\"Test AI and manual category management.\"\"\"
    try:
        # Get some transactions to test categorization
        all_transactions = transaction_service.data_manager.read_all()
        
        if all_transactions.empty:
            print(\"   No transactions to test categorization\")
            return True
        
        # Test with first transaction
        first_transaction = all_transactions.iloc[0]
        transaction_id = first_transaction['transaction_id']
        
        print(f\"\
   Testing categorization with transaction: {first_transaction.get('name', 'Unknown')}\")
        
        # Test manual category override
        print(\"   Testing manual category override...\")
        success = transaction_service.update_manual_category(transaction_id, 'test_manual_category')
        if success:
            print(\"   ✅ Manual category set\")
            
            # Verify the update
            updated_transaction = transaction_service.data_manager.read_by_id(transaction_id)
            if updated_transaction and updated_transaction.get('manual_category') == 'test_manual_category':
                print(\"   ✅ Manual category verified\")
            else:
                print(\"   ❌ Manual category verification failed\")
                return False
        else:
            print(\"   ❌ Failed to set manual category\")
            return False
        
        # Test clearing manual category
        print(\"   Testing clear manual category...\")
        success = transaction_service.clear_manual_category(transaction_id)
        if success:
            print(\"   ✅ Manual category cleared\")
        else:
            print(\"   ❌ Failed to clear manual category\")
            return False
        
        # Test AI categorization (if categorizer is available)
        print(\"   Testing AI categorization...\")
        try:
            categorization_result = transaction_service.categorize_transaction(transaction_id)
            if categorization_result.success:
                print(f\"   ✅ AI categorized as: {categorization_result.category}\")
                if categorization_result.reasoning:
                    print(f\"   Reasoning: {categorization_result.reasoning}\")
            else:
                print(f\"   ⚠️  AI categorization failed: {categorization_result.error}\")
                # This is not a failure for the sync test - AI service might not be configured
        except Exception as e:
            print(f\"   ⚠️  AI categorization error: {e}\")
            # This is not a failure for the sync test
        
        return True
        
    except Exception as e:
        print(f\"❌ Category management test failed: {e}\")
        return False

def check_configuration():
    \"\"\"Check and display current configuration.\"\"\"
    print(\"\
📋 Current Configuration:\")
    print(f\"   DATA_PATH: {config.data_path}\")
    print(f\"   Using SQLite: {config.data_path.endswith('.db')}\")
    print(f\"   Plaid Environment: {config.plaid_env}\")
    
    if not config.plaid_client_id or not config.plaid_secret:
        print(\"   ⚠️  Plaid credentials not configured - sync will fail\")
        print(\"   Set PLAID_CLIENT_ID and PLAID_SECRET environment variables\")
        return False
    else:
        print(\"   ✅ Plaid credentials configured\")
    
    return True

if __name__ == \"__main__\":
    print(\"🚀 SQLite Fresh Sync Test\")
    print(\"This test validates the complete flow: Configuration -> Database -> Sync -> Categorization\")
    
    # Check configuration first
    if not check_configuration():
        print(\"\
❌ Configuration issues detected. Please fix before running sync test.\")
        sys.exit(1)
    
    # Run the test
    success = test_fresh_sync_to_sqlite()
    
    if success:
        print(\"\
✅ All tests passed! SQLite fresh sync is working correctly.\")
        print(\"\
📝 Next steps:\")
        print(\"   1. Set DATA_PATH=./data/transactions.db to use SQLite in production\")
        print(\"   2. Link accounts using the Streamlit app\")
        print(\"   3. Run sync to populate the database\")
        sys.exit(0)
    else:
        print(\"\
❌ Some tests failed. Check the errors above.\")
        sys.exit(1)