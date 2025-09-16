-- SQLite Database Schema for Personal Finance Tracker
-- Enhanced schema with integrated access token management

-- Table 1: Institution information (replaces access_tokens.json)
CREATE TABLE institutions (
    id TEXT PRIMARY KEY,                    -- Institution name (e.g., "Chase", "Ally Bank")
    access_token TEXT NOT NULL,             -- Plaid access token
    cursor TEXT,                            -- Sync cursor for incremental sync
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_sync TEXT,                         -- Last successful sync timestamp
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Table 2: Enhanced account information with full Plaid metadata
CREATE TABLE accounts (
    id TEXT PRIMARY KEY,                    -- Plaid account_id
    institution_id TEXT NOT NULL,          -- Links to institutions table
    bank_name TEXT NOT NULL,               
    account_name TEXT NOT NULL,
    official_name TEXT,                     -- Plaid official name
    account_type TEXT,                      -- checking, savings, etc.
    account_subtype TEXT,                   -- specific subtype
    mask TEXT,                              -- Last 4 digits
    balance_current REAL,                   -- Current balance
    balance_available REAL,                 -- Available balance  
    balance_limit REAL,                     -- Credit limit
    currency_code TEXT DEFAULT 'USD',
    account_owner TEXT,
    is_active BOOLEAN DEFAULT TRUE,         -- For soft deletion
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (institution_id) REFERENCES institutions (id)
);

-- Table 3: Transactions with embedded categories (unchanged)
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
    tags JSON DEFAULT '[]',                              
    
    -- System fields
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (account_id) REFERENCES accounts (id)
);

-- Indexes for institutions table
CREATE INDEX idx_institutions_access_token ON institutions (access_token);
CREATE INDEX idx_institutions_last_sync ON institutions (last_sync);

-- Enhanced indexes for accounts table
CREATE INDEX idx_accounts_institution ON accounts (institution_id);
CREATE INDEX idx_accounts_type ON accounts (account_type);
CREATE INDEX idx_accounts_active ON accounts (is_active);
CREATE INDEX idx_accounts_bank_name ON accounts (bank_name);

-- Core transaction indexes (unchanged)
CREATE INDEX idx_transactions_date ON transactions (date);
CREATE INDEX idx_transactions_account ON transactions (account_id);
CREATE INDEX idx_transactions_amount ON transactions (amount);
CREATE INDEX idx_transactions_merchant ON transactions (merchant_name);
CREATE INDEX idx_transactions_pending ON transactions (pending);

-- Category queries (simplified - direct column indexes)
CREATE INDEX idx_transactions_ai_category ON transactions (ai_category);
CREATE INDEX idx_transactions_manual_category ON transactions (manual_category);

-- JSON tag index for efficient tag searches
CREATE INDEX idx_transactions_tags ON transactions (json_each.value) WHERE json_valid(tags);

-- Composite indexes for common filter combinations
CREATE INDEX idx_transactions_account_date ON transactions (account_id, date);
CREATE INDEX idx_transactions_date_amount ON transactions (date, amount);

-- Index for finding uncategorized transactions
CREATE INDEX idx_transactions_uncategorized ON transactions (ai_category, manual_category);

-- Triggers for automatic updated_at timestamps
CREATE TRIGGER update_institutions_timestamp 
    AFTER UPDATE ON institutions
BEGIN
    UPDATE institutions SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

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