# Personal Finance Tracker

A Streamlit-based personal finance application that integrates with Plaid to automatically sync and categorize your bank transactions. Track your spending, visualize your finances, and manage your money like Mint or Monarch.

## ✨ Features

- **🏦 Multiple Bank Connections**: Connect checking, savings, and credit card accounts via Plaid
- **🔄 Automatic Sync**: Real-time transaction synchronization with smart duplicate detection
- **📊 Rich Visualizations**: Interactive dashboards with charts, spending trends, and category breakdowns
- **🏷️ Smart Categorization**: Automatic transaction categorization with manual override options
- **📤 Data Export**: Export transaction data to CSV for external analysis
- **🔒 Secure**: All data stored locally with encryption-ready backup options
- **📱 Modern UI**: Clean, responsive Streamlit interface

## 🚀 Quick Start

### 1. Install Dependencies
```bash
cd /Users/ammarh/budgeting
pip install -r requirements.txt
```

### 2. Set Up Plaid Account
1. Go to https://dashboard.plaid.com/signup
2. Sign up and verify your email
3. Complete developer questionnaire (select "Personal project")
4. Get your `client_id` and `sandbox secret key` from "Team and API Keys"

### 3. Configure Environment
1. Copy the environment template:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your Plaid credentials:
   ```bash
   PLAID_CLIENT_ID=your_actual_client_id_here
   PLAID_SECRET=your_actual_sandbox_secret_here
   PLAID_ENV=sandbox
   CSV_FILE_PATH=./data/transactions.csv
   SYNC_INTERVAL_HOURS=24
   ```

### 4. Create Data Directory
```bash
mkdir -p data
```

### 5. Run the Application
```bash
streamlit run streamlit_app.py
```

### 6. Open Your Browser
Navigate to `http://localhost:8501`

## 🏦 Linking Bank Accounts

### Development/Testing (Sandbox)
- Use Plaid's test credentials
- No real bank connections required
- Perfect for development and testing

### Production (Real Banks)
1. **Apply for Production**: Go to Plaid Dashboard → "Apply for Production"
2. **Wait for Approval**: Usually 1-3 business days
3. **Get Production Keys**: Copy your production secret key
4. **Update Environment**: Change `PLAID_ENV=production` in `.env`
5. **Link Real Accounts**: Use actual bank credentials

## 📊 Using the Application

### Dashboard
- **Account Overview**: See all connected accounts and balances
- **Transaction History**: Browse and edit recent transactions
- **Spending Analysis**: Charts and category breakdowns
- **Monthly Trends**: Track spending patterns over time

### Account Linking Page
- **Recent Sync**: Daily transaction updates (last 30 days)
- **Historical Import**: Import 3, 6, 12, or 24 months of transaction history
- **Account Management**: View connected accounts and their status

### Data Export Page
- **CSV Export**: Download transaction data for external analysis
- **Filtered Exports**: Export specific date ranges or categories
- **Backup Creation**: Generate encrypted backups of your financial data

## 🔒 Security & Privacy

### Data Storage
- All sensitive data stored locally in `data/` directory
- No data sent to external servers (except Plaid for sync)
- `data/` directory excluded from version control
- Access tokens encrypted and stored locally

### Best Practices
1. **Never commit sensitive files**:
   ```
   .env
   data/
   access_tokens*.json
   transactions*.csv
   *.gpg
   ```

2. **Regular encrypted backups**:
   ```bash
   # Create encrypted backup
   tar czf - data/ | gpg -c > finance_backup_$(date +%Y%m%d).tar.gz.gpg
   ```

3. **Secure your environment**:
   - Use strong passwords for your system
   - Consider full-disk encryption
   - Keep your OS and dependencies updated

## ⚙️ Configuration

### Environment Variables
| Variable | Description | Default |
|----------|-------------|---------|
| `PLAID_CLIENT_ID` | Your Plaid client ID | Required |
| `PLAID_SECRET` | Your Plaid secret key | Required |
| `PLAID_ENV` | Plaid environment (`sandbox`/`production`) | `sandbox` |
| `CSV_FILE_PATH` | Transaction data file path | `./data/transactions.csv` |
| `SYNC_INTERVAL_HOURS` | Hours between automatic syncs | `24` |

### Transaction Categories
Customize categorization rules in `config.py`:
```python
CATEGORY_MAPPING = {
    'Groceries': ['safeway', 'trader joe', 'whole foods'],
    'Restaurants': ['restaurant', 'cafe', 'food'],
    # Add your own rules...
}
```

## 🔄 Syncing Transactions

### Manual Sync
- **Recent Transactions**: Sync last 30 days
- **Historical Import**: Import up to 24 months of history
- **Rate Limiting**: 5-minute cooldown between syncs per institution

### Automatic Features
- **Duplicate Detection**: Prevents importing the same transaction twice
- **Pending Transaction Handling**: Smart detection of pending→confirmed transitions
- **Bank Identification**: Automatically tags transactions with source bank
- **Date Normalization**: Handles various date formats from different banks

## 📈 Advanced Features

### Custom Categories
- **Manual Override**: Edit transaction categories in the dashboard
- **Bulk Categorization**: Apply rules to multiple transactions
- **Category Analytics**: Spending breakdown by custom categories

### Data Analysis
- **Export Options**: CSV, filtered exports, date ranges
- **Visualization**: Charts, trends, spending patterns
- **Search & Filter**: Find specific transactions quickly

### Backup & Recovery
- **Automated Backups**: Script for regular data backups
- **Version Control**: Track changes to your financial data
- **Recovery Options**: Restore from backups when needed

## 🚨 Production Considerations

### Moving to Production
1. **Apply for Plaid Production Access**
2. **Update credentials** in `.env`
3. **Start with one account** to test
4. **Gradually add more accounts**
5. **Set up regular backups**

### Institution Support
- **Major Banks**: Most US banks supported
- **Credit Unions**: Many supported, check Plaid's institution list
- **International**: Limited support outside US
- **Check Coverage**: https://plaid.com/institutions/

### Rate Limits
- **Development**: 100 requests/day
- **Production**: Higher limits, monitor usage
- **Best Practice**: Sync daily, not hourly

## 🛠️ Development

### File Structure
```
/Users/ammarh/budgeting/
├── streamlit_app.py          # Main Streamlit application
├── pages/                    # Streamlit pages
│   ├── 1_🏦_Account_Linking.py
│   └── 2_📊_Data_Export.py
├── plaid_client.py          # Plaid API integration
├── sync_service.py          # Transaction sync logic
├── data_manager.py          # CSV data management
├── config.py               # Configuration and categories
├── requirements.txt        # Python dependencies
├── data/                   # Data storage (not in git)
│   ├── transactions.csv
│   └── access_tokens.json
└── .env                    # Environment variables (not in git)
```

### Adding New Features
1. **New Pages**: Add files to `pages/` directory
2. **New Categories**: Update `CATEGORY_MAPPING` in `config.py`
3. **New Visualizations**: Add charts to dashboard
4. **New Export Formats**: Extend `data_manager.py`

## 📞 Support & Resources

### Plaid Resources
- **Support**: https://plaid.com/support/
- **Status**: https://status.plaid.com/
- **Documentation**: https://plaid.com/docs/

### Troubleshooting
- **Connection Issues**: Check Plaid status and credentials
- **Missing Transactions**: Try historical import
- **Sync Errors**: Check rate limiting and account status
- **UI Issues**: Refresh browser, check Streamlit logs

## 🔄 Rollback to Sandbox

If you need to return to sandbox mode:
```bash
# Update environment
PLAID_ENV=sandbox
PLAID_SECRET=your_sandbox_secret

# Optionally restore sandbox data
cp data/transactions_sandbox.csv data/transactions.csv
cp data/access_tokens_sandbox.json data/access_tokens.json
```

---

## 🎯 Next Steps

1. **Link your first account** using sandbox credentials
2. **Import historical data** to see more transactions
3. **Customize categories** for your spending patterns
4. **Set up regular backups** for your financial data
5. **Apply for production** when ready for real accounts

Enjoy tracking your finances! 🎉