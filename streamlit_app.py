import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import numpy as np
import time
from data_manager import DataManager
from sync_service import TransactionSyncService
from config import CATEGORY_MAPPING

# Page config
st.set_page_config(
    page_title="Personal Finance Tracker",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize services
def get_services():
    return DataManager(), TransactionSyncService()

data_manager, sync_service = get_services()

# Custom CSS for Mint-like styling
st.markdown("""
<style>
    .metric-card {
        background: white;
        padding: 1rem;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        border: 1px solid #e1e5e9;
    }
    .stMetric {
        background: white;
        padding: 1rem;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .main-header {
        font-size: 2.5rem;
        color: #2e7d32;
        text-align: center;
        margin-bottom: 2rem;
    }
    .section-header {
        font-size: 1.5rem;
        color: #1976d2;
        margin: 1.5rem 0 1rem 0;
        border-bottom: 2px solid #e1e5e9;
        padding-bottom: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown('<h1 class="main-header">💰 Personal Finance Tracker</h1>', unsafe_allow_html=True)

# Account Management Section
with st.expander("🔧 Account Management", expanded=False):
    st.subheader("Sync Options")
    
    # Get connected accounts for dropdown
    accounts = sync_service.get_connected_accounts()
    account_options = ["All Accounts"]
    
    if accounts and not accounts.get('message'):
        for bank_name in accounts.keys():
            if 'accounts' in accounts[bank_name]:
                account_options.append(bank_name)
    
    # Account selection dropdown
    selected_account = st.selectbox(
        "Select Account to Sync",
        options=account_options,
        index=0,
        help="Choose which account to sync, or 'All Accounts' to sync everything"
    )
    
    # Sync options
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔄 Incremental Sync", type="primary", help="Fetch only new transactions since last sync"):
            with st.spinner(f"Syncing new transactions for {selected_account}..."):
                if selected_account == "All Accounts":
                    result = sync_service.sync_all_accounts(full_sync=False)
                else:
                    result = sync_service.sync_specific_account(selected_account, full_sync=False)
                st.write(result)
    
    with col2:
        if st.button("🔄 Full Sync", type="secondary", help="Re-fetch all historical transactions"):
            with st.spinner(f"Performing full sync for {selected_account}..."):
                if selected_account == "All Accounts":
                    result = sync_service.sync_all_accounts(full_sync=True)
                else:
                    result = sync_service.sync_specific_account(selected_account, full_sync=True)
                st.write(result)
    
    # Connected accounts info
    st.subheader("Connected Accounts")
    if accounts and not accounts.get('message'):
        # Get access tokens data for additional info
        tokens_data = sync_service.load_access_tokens()
        
        for bank, info in accounts.items():
            if 'accounts' in info:
                st.write(f"**{bank}**: {len(info['accounts'])} accounts")
                
                # Get additional metadata from tokens
                if bank in tokens_data:
                    token_info = tokens_data[bank]
                    
                    # Format dates
                    created_at = token_info.get('created_at')
                    if created_at:
                        try:
                            created_dt = datetime.fromisoformat(created_at)
                            created_display = created_dt.strftime('%Y-%m-%d %H:%M')
                        except:
                            created_display = created_at
                    else:
                        created_display = "Unknown"
                    
                    last_sync = token_info.get('last_sync')
                    if last_sync:
                        try:
                            sync_dt = datetime.fromisoformat(last_sync)
                            sync_display = sync_dt.strftime('%Y-%m-%d %H:%M')
                        except:
                            sync_display = last_sync
                    else:
                        sync_display = "Never"
                    
                    cursor = token_info.get('cursor', '')
                    cursor_display = cursor[:20] + "..." if cursor and len(cursor) > 20 else cursor or "None"
                    
                    # Display metadata in smaller text
                    st.markdown(f"""
                    <div style="margin-left: 20px; font-size: 0.8em; color: #666;">
                        • Created: {created_display}<br>
                        • Last Sync: {sync_display}<br>
                        • Cursor: {cursor_display}
                    </div>
                    """, unsafe_allow_html=True)
                
                st.write("")  # Add spacing between accounts
    else:
        st.write("No accounts connected. Please link your accounts first.")

# Load transaction data
@st.cache_data
def load_transactions():
    df = data_manager.read_transactions()
    if not df.empty and 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
        df['month'] = df['date'].dt.to_period('M')
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
    return df

df = load_transactions()

if df.empty:
    st.warning("No transactions found. Please sync your accounts or check your data files.")
    st.stop()

# Filters in sidebar
with st.sidebar:
    st.subheader("📊 Filters")
    
    # Date range filter
    if not df.empty:
        min_date = df['date'].min().date()
        max_date = df['date'].max().date()
        
        date_range = st.date_input(
            "Date Range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date
        )
        
        if len(date_range) == 2:
            start_date, end_date = date_range
            df_filtered = df[(df['date'].dt.date >= start_date) & (df['date'].dt.date <= end_date)]
        else:
            df_filtered = df
    else:
        df_filtered = df
    
    # Category filter
    if 'custom_category' in df_filtered.columns:
        categories = st.multiselect(
            "Categories",
            options=sorted(df_filtered['custom_category'].dropna().unique()),
            default=sorted(df_filtered['custom_category'].dropna().unique())
        )
        df_filtered = df_filtered[df_filtered['custom_category'].isin(categories)]
    
    # Account filter
    if 'bank_name' in df_filtered.columns:
        banks = st.multiselect(
            "Banks",
            options=sorted(df_filtered['bank_name'].dropna().unique()),
            default=sorted(df_filtered['bank_name'].dropna().unique())
        )
        df_filtered = df_filtered[df_filtered['bank_name'].isin(banks)]
    
    # Amount filter
    if not df_filtered.empty:
        min_amount, max_amount = st.slider(
            "Amount Range",
            min_value=float(df_filtered['amount'].min()),
            max_value=float(df_filtered['amount'].max()),
            value=(float(df_filtered['amount'].min()), float(df_filtered['amount'].max())),
            format="$%.2f"
        )
        df_filtered = df_filtered[
            (df_filtered['amount'] >= min_amount) & 
            (df_filtered['amount'] <= max_amount)
        ]
    
    # Export functionality
    st.subheader("📥 Export Data")
    
    # Column selection for export
    available_export_columns = [
        'date', 'name', 'amount', 'custom_category', 'merchant_name', 
        'bank_name', 'category', 'original_description', 'pending',
        'transaction_id', 'account_name'
    ]
    
    export_columns = st.multiselect(
        "Export Columns",
        options=[col for col in available_export_columns if col in df_filtered.columns],
        default=[col for col in ['date', 'name', 'amount', 'custom_category', 'merchant_name', 'bank_name'] if col in df_filtered.columns],
        help="Select which columns to include in the export"
    )
    
    # Export button
    if export_columns and not df_filtered.empty:
        export_df = df_filtered[export_columns].copy()
        
        # Convert datetime columns to strings for CSV export
        for col in export_df.columns:
            if export_df[col].dtype == 'datetime64[ns]' or col in ['date', 'authorized_date']:
                export_df[col] = pd.to_datetime(export_df[col]).dt.strftime('%Y-%m-%d')
        
        csv_data = export_df.to_csv(index=False)
        
        st.download_button(
            label=f"📥 Export CSV ({len(export_df)} transactions)",
            data=csv_data,
            file_name=f"filtered_transactions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            type="primary",
            help="Download filtered transactions as CSV file"
        )
    elif not export_columns:
        st.info("Select columns to export")
    else:
        st.info("No transactions to export with current filters")

# Key metrics and analysis sections collapsed by default
with st.expander("📊 Financial Overview", expanded=True):
    # Key metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    spending = df_filtered[df_filtered['amount'] > 0]['amount'].sum()
    income = abs(df_filtered[df_filtered['amount'] < 0]['amount'].sum())
    net_flow = income - spending
    transaction_count = len(df_filtered)
    
    with col1:
        st.metric(
            "💸 Total Spending", 
            f"${spending:,.2f}",
            delta=f"{transaction_count} transactions"
        )
    
    with col2:
        st.metric(
            "💰 Total Income", 
            f"${income:,.2f}",
            delta="This period"
        )
    
    with col3:
        net_color = "normal" if net_flow >= 0 else "inverse"
        st.metric(
            "📊 Net Flow", 
            f"${net_flow:,.2f}",
            delta="Income - Spending",
            delta_color=net_color
        )
    
    with col4:
        # Calculate average transactions per week
        if not df_filtered.empty and 'date' in df_filtered.columns:
            date_range_days = (df_filtered['date'].max() - df_filtered['date'].min()).days
            weeks = max(date_range_days / 7, 1)  # Avoid division by zero
            avg_transactions_per_week = transaction_count / weeks
        else:
            avg_transactions_per_week = 0
        
        st.metric(
            "📅 Avg Transactions/Week", 
            f"{avg_transactions_per_week:.1f}",
            delta=f"{transaction_count} total"
        )

with st.expander("📈 Spending Analysis", expanded=False):
    col1, col2 = st.columns(2)
    
    with col1:
        # Spending by category pie chart
        if 'custom_category' in df_filtered.columns:
            spending_by_category = df_filtered[df_filtered['amount'] > 0].groupby('custom_category')['amount'].sum().reset_index()
            
            fig_pie = px.pie(
                spending_by_category, 
                values='amount', 
                names='custom_category',
                title="Spending by Category",
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_pie, use_container_width=True)
    
    with col2:
        # Monthly spending trend
        if 'month' in df_filtered.columns:
            monthly_spending = df_filtered[df_filtered['amount'] > 0].groupby('month')['amount'].sum().reset_index()
            monthly_spending['month_str'] = monthly_spending['month'].astype(str)
            
            fig_line = px.line(
                monthly_spending, 
                x='month_str', 
                y='amount',
                title="Monthly Spending Trend",
                markers=True
            )
            fig_line.update_xaxes(title="Month")
            fig_line.update_yaxes(title="Amount ($)")
            st.plotly_chart(fig_line, use_container_width=True)

with st.expander("💡 Quick Insights", expanded=False):
    if not df_filtered.empty and 'amount' in df_filtered.columns:
        col1, col2 = st.columns(2)
        
        with col1:
            # Top spending categories
            if 'custom_category' in df_filtered.columns:
                spending_by_cat = df_filtered[df_filtered['amount'] > 0].groupby('custom_category')['amount'].sum().sort_values(ascending=False).head(5)
                st.write("**Top 5 Spending Categories:**")
                for cat, amount in spending_by_cat.items():
                    st.write(f"• {cat}: ${amount:,.2f}")
        
        with col2:
            # Top merchants
            if 'merchant_name' in df_filtered.columns:
                top_merchants = df_filtered[df_filtered['amount'] > 0].groupby('merchant_name')['amount'].sum().sort_values(ascending=False).head(5)
                st.write("**Top 5 Merchants:**")
                for merchant, amount in top_merchants.items():
                    if pd.notna(merchant):
                        st.write(f"• {merchant}: ${amount:,.2f}")
    else:
        st.info("No transaction data available for insights.")

with st.expander("🏷️ Transaction Management", expanded=False):
    
    # Search and bulk operations
    col1, col2 = st.columns([2, 1])
    with col1:
        search_term = st.text_input("🔍 Search transactions", placeholder="Search by description, merchant, etc.")
    with col2:
        show_pending = st.checkbox("Show pending only")
    
    # Apply search filter
    if search_term:
        mask = (
            df_filtered['name'].str.contains(search_term, case=False, na=False) |
            df_filtered['merchant_name'].str.contains(search_term, case=False, na=False) |
            df_filtered['custom_category'].str.contains(search_term, case=False, na=False)
        )
        df_display = df_filtered[mask]
    else:
        df_display = df_filtered
    
    if show_pending and 'pending' in df_display.columns:
        df_display = df_display[df_display['pending'] == True]
    
    # Display transactions with editing capabilities
    if not df_display.empty:
        # Select columns to display and edit
        display_columns = [
            'date', 'authorized_date', 'name', 'amount', 'custom_category',
            'personal_finance_category', 'personal_finance_category_detailed', 'personal_finance_category_confidence',
            'merchant_name', 'bank_name', 'pending', 'transaction_id'
        ]
        
        available_columns = [col for col in display_columns if col in df_display.columns]
        
        # Create a copy for display and convert date columns to proper datetime
        df_for_display = df_display[available_columns].reset_index(drop=True).copy()
        
        # Convert date strings to datetime for proper editing
        if 'authorized_date' in df_for_display.columns:
            df_for_display['authorized_date'] = pd.to_datetime(df_for_display['authorized_date'], errors='coerce')
        
        # Create editable dataframe
        edited_df = st.data_editor(
            df_for_display,
            column_config={
                "date": st.column_config.DateColumn(
                    "Date",
                    format="MM/DD/YYYY",
                    disabled=True
                ),
                "authorized_date": st.column_config.DateColumn(
                    "Auth Date",
                    format="MM/DD/YYYY",
                    disabled=True,
                    help="When transaction was authorized"
                ),
                "name": st.column_config.TextColumn(
                    "Name",
                    disabled=True,
                    help="Transaction description"
                ),
                "amount": st.column_config.NumberColumn(
                    "Amount",
                    format="$%.2f",
                    disabled=True
                ),
                "custom_category": st.column_config.SelectboxColumn(
                    "Category",
                    options=list(CATEGORY_MAPPING.keys()),
                    required=True,
                ),
                "personal_finance_category": st.column_config.TextColumn(
                    "PFC Primary",
                    disabled=True,
                    help="Plaid's primary personal finance category"
                ),
                "personal_finance_category_detailed": st.column_config.TextColumn(
                    "PFC Detailed",
                    disabled=True,
                    help="Plaid's detailed personal finance category"
                ),
                "personal_finance_category_confidence": st.column_config.TextColumn(
                    "PFC Confidence",
                    disabled=True,
                    help="Plaid's confidence level for the category"
                ),
                "merchant_name": st.column_config.TextColumn(
                    "Merchant",
                    help="Merchant name (editable)"
                ),
                "bank_name": st.column_config.TextColumn(
                    "Bank",
                    disabled=True,
                    help="Bank name"
                ),
                "pending": st.column_config.CheckboxColumn(
                    "Pending",
                    disabled=True
                ),
                "transaction_id": st.column_config.TextColumn(
                    "Transaction ID",
                    disabled=True,
                    help="Unique transaction identifier"
                )
            },
            num_rows="dynamic",
            use_container_width=True,
            key="transaction_editor"
        )
        
        # Save changes button
        if st.button("💾 Save Changes", type="primary"):
            try:
                # Get the original dataframe
                original_df = data_manager.read_transactions()
                
                # Create a mapping from transaction_id to row index in original_df
                if 'transaction_id' in original_df.columns and 'transaction_id' in df_display.columns:
                    for i, row in edited_df.iterrows():
                        if i < len(df_display):
                            # Get the transaction_id from the original filtered display
                            transaction_id = df_display.iloc[i]['transaction_id']
                            
                            # Find this transaction in the original dataframe
                            mask = original_df['transaction_id'] == transaction_id
                            
                            if mask.any():
                                # Update only the editable columns
                                editable_columns = ['custom_category', 'merchant_name']
                                for col in editable_columns:
                                    if col in edited_df.columns:
                                        value = row[col]
                                        original_df.loc[mask, col] = value
                
                # Save back to CSV
                original_df.to_csv(data_manager.csv_path, index=False)
                st.success("✅ Changes saved successfully! Refresh the page to see updates.")
                
            except Exception as e:
                st.error(f"❌ Error saving changes: {str(e)}")
                st.error("Please try again or check your data format.")
    
    else:
        st.info("No transactions match your current filters.")

# Main dashboard check for data availability
if df_filtered.empty:
    st.warning("No transactions found with current filters.")