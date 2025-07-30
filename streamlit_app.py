import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import numpy as np
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

# Sidebar for controls
with st.sidebar:
    st.header("🔧 Controls")
    
    # Account Management
    st.subheader("Account Management")
    
    # Sync options
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔄 Incremental Sync", type="primary", help="Fetch only new transactions since last sync"):
            with st.spinner("Syncing new transactions..."):
                result = sync_service.sync_all_accounts(full_sync=False)
                if result.get('errors'):
                    st.error(f"Sync errors: {', '.join(result['errors'])}")
                if result.get('info'):
                    st.warning(result['info'])
                if result.get('total_new_transactions', 0) > 0 or result.get('accounts_synced', 0) > 0:
                    st.success(f"✅ Synced {result.get('total_new_transactions', 0)} new, {result.get('total_modified_transactions', 0)} modified, {result.get('total_removed_transactions', 0)} removed transactions from {result.get('accounts_synced', 0)} accounts")
                if not result.get('errors') and not result.get('total_new_transactions', 0):
                    st.info("No new transactions found or rate limited.")
                st.rerun()
    
    with col2:
        if st.button("🔄 Full Sync", type="secondary", help="Re-fetch all historical transactions"):
            with st.spinner("Performing full sync..."):
                result = sync_service.sync_all_accounts(full_sync=True)
                if result.get('errors'):
                    st.error(f"Sync errors: {', '.join(result['errors'])}")
                if result.get('info'):
                    st.warning(result['info'])
                if result.get('total_new_transactions', 0) > 0 or result.get('accounts_synced', 0) > 0:
                    st.success(f"✅ Full sync: {result.get('total_new_transactions', 0)} new, {result.get('total_modified_transactions', 0)} modified, {result.get('total_removed_transactions', 0)} removed transactions from {result.get('accounts_synced', 0)} accounts")
                if not result.get('errors') and not result.get('total_new_transactions', 0):
                    st.info("No transactions found or rate limited.")
                st.rerun()
    
    # Connected accounts info
    accounts = sync_service.get_connected_accounts()
    if accounts and not accounts.get('message'):
        st.subheader("Connected Accounts")
        for bank, info in accounts.items():
            if 'accounts' in info:
                st.write(f"**{bank}**: {len(info['accounts'])} accounts")

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

# Main dashboard
if not df_filtered.empty:
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
        avg_transaction = spending / max(transaction_count, 1)
        st.metric(
            "🧾 Avg Transaction", 
            f"${avg_transaction:.2f}",
            delta=f"{transaction_count} total"
        )
    
    # Charts row
    st.markdown('<h2 class="section-header">📈 Spending Analysis</h2>', unsafe_allow_html=True)
    
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
    
    # Transaction management section
    st.markdown('<h2 class="section-header">🏷️ Transaction Management</h2>', unsafe_allow_html=True)
    
    # Search and bulk operations
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        search_term = st.text_input("🔍 Search transactions", placeholder="Search by description, merchant, etc.")
    with col2:
        show_pending = st.checkbox("Show pending only")
    with col3:
        sort_by = st.selectbox("Sort by", ["date", "amount", "custom_category", "name"])
    
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
    
    # Sort data
    df_display = df_display.sort_values(sort_by, ascending=False)
    
    # Display transactions with editing capabilities
    if not df_display.empty:
        # Select columns to display and edit
        display_columns = [
            'transaction_id', 'date', 'authorized_date', 'name', 'amount', 'custom_category', 
            'merchant_name', 'bank_name', 'pending'
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
                "transaction_id": st.column_config.TextColumn(
                    "Transaction ID",
                    disabled=True,
                    help="Unique transaction identifier"
                ),
                "authorized_date": st.column_config.DateColumn(
                    "Auth Date",
                    format="MM/DD/YYYY",
                    help="When transaction was authorized"
                ),
                "custom_category": st.column_config.SelectboxColumn(
                    "Category",
                    options=list(CATEGORY_MAPPING.keys()),
                    required=True,
                ),
                "amount": st.column_config.NumberColumn(
                    "Amount",
                    format="$%.2f",
                ),
                "date": st.column_config.DateColumn(
                    "Date",
                    format="MM/DD/YYYY",
                ),
                "pending": st.column_config.CheckboxColumn(
                    "Pending"
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
                                # Update the columns that were edited
                                for col in available_columns:
                                    if col in edited_df.columns and col != 'transaction_id':
                                        value = row[col]
                                        
                                        # Convert datetime back to string for storage
                                        if col in ['date', 'authorized_date'] and pd.notna(value):
                                            if hasattr(value, 'strftime'):
                                                value = value.strftime('%Y-%m-%d')
                                            elif hasattr(value, 'date'):
                                                value = value.date().isoformat()
                                        
                                        original_df.loc[mask, col] = value
                
                # Save back to CSV
                original_df.to_csv(data_manager.csv_path, index=False)
                st.success("✅ Changes saved successfully! Refresh the page to see updates.")
                
            except Exception as e:
                st.error(f"❌ Error saving changes: {str(e)}")
                st.error("Please try again or check your data format.")
    
    else:
        st.info("No transactions match your current filters.")

else:
    st.warning("No transactions found with current filters.")