# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Environment Setup

Start the FastAPI application:
```bash
python app.py
```

Install dependencies:
```bash
pip install -r requirements.txt
```

Environment configuration requires a `.env` file based on `.env.example` with Plaid API credentials.

## Architecture Overview

This is a personal finance tracker built with FastAPI that integrates with the Plaid API to fetch bank transaction data. The application follows a service-oriented architecture:

**Core Components:**
- `app.py` - FastAPI web application with embedded HTML frontend for account linking and transaction viewing
- `plaid_client.py` - Plaid API wrapper handling authentication, account fetching, and transaction retrieval with comprehensive data formatting
- `sync_service.py` - Transaction synchronization service managing access tokens and orchestrating data fetching from multiple bank accounts
- `data_manager.py` - CSV-based data persistence layer handling transaction storage, deduplication, and summary generation
- `config.py` - Configuration management using environment variables and transaction categorization mappings

**Data Flow:**
1. User links bank accounts via Plaid Link (web interface)
2. Public tokens are exchanged for access tokens (stored in `access_tokens.json`)
3. Transaction sync service fetches transactions from all connected accounts
4. Data manager processes, categorizes, and stores transactions in CSV format
5. Web interface provides account overview and transaction summaries

**Key Features:**
- Multi-bank account support (Capital One, Chase, US Bank)
- Automatic transaction categorization using keyword mapping
- Incremental sync to avoid duplicate transactions
- Comprehensive transaction metadata capture (location, payment details)
- Web-based account linking and management interface

**Data Storage:**
- Access tokens stored in `access_tokens.json`
- Transaction data stored in `transactions.csv` with comprehensive field structure
- Automatic duplicate detection using transaction IDs

The application operates in Plaid's sandbox environment by default for development/testing.