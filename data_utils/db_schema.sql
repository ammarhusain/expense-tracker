-- SQLite Database Schema for Personal Finance Tracker
-- Simple 2-table design with embedded categories

-- Table 1: Account information
CREATE TABLE accounts (
    id TEXT PRIMARY KEY,                    
    bank_name TEXT NOT NULL,               
    account_name TEXT NOT NULL,             
    account_owner TEXT,                     
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Table 2: Transactions with embedded categories (no joins needed!)
CREATE TABLE transactions (
    transaction_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    
    -- Core transaction data
    date TEXT NOT NULL,
    name TEXT,
    merchant_name TEXT,
    original_description TEXT,
    amount REAL NOT NULL,
    currency TEXT DEFAULT 'USD',
    pending BOOLEAN DEFAULT FALSE,
    transaction_type TEXT,
    location TEXT,
    payment_details TEXT,
    website TEXT,
    check_number TEXT,    
    plaid_category TEXT,                    
    ai_category TEXT,                       
    ai_reason TEXT,                         
    manual_category TEXT,                   
    notes TEXT,                             
    tags TEXT,                              
    
    -- System fields
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (account_id) REFERENCES accounts (id)
);

-- Core query patterns
CREATE INDEX idx_transactions_date ON transactions (date);
CREATE INDEX idx_transactions_account ON transactions (account_id);
CREATE INDEX idx_transactions_amount ON transactions (amount);
CREATE INDEX idx_transactions_merchant ON transactions (merchant_name);
CREATE INDEX idx_transactions_pending ON transactions (pending);

-- Category queries (simplified - direct column indexes)
CREATE INDEX idx_transactions_ai_category ON transactions (ai_category);
CREATE INDEX idx_transactions_manual_category ON transactions (manual_category);

-- Composite indexes for common filter combinations
CREATE INDEX idx_transactions_account_date ON transactions (account_id, date);
CREATE INDEX idx_transactions_date_amount ON transactions (date, amount);

-- Index for finding uncategorized transactions
CREATE INDEX idx_transactions_uncategorized ON transactions (ai_category, manual_category);

-- Triggers for automatic updated_at timestamps
CREATE TRIGGER update_accounts_timestamp 
    AFTER UPDATE ON accounts
BEGIN
    UPDATE accounts SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER update_transactions_timestamp 
    AFTER UPDATE ON transactions
BEGIN
    UPDATE transactions SET updated_at = CURRENT_TIMESTAMP WHERE transaction_id = NEW.transaction_id;
END;