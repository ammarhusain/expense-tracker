import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import numpy as np
import time
import os

# NEW: Import new architecture with S3 support
from config import create_services, CATEGORY_MAPPING
from transaction_types import SyncResult
from data_utils.s3_database_manager import db_manager

# Page config
st.set_page_config(
    page_title="Personal Finance Tracker",
    page_icon="💰",
    layout="centered",
    initial_sidebar_state="expanded"
)

# Clear any problematic session state on startup
if 'initialized' not in st.session_state:
    st.session_state.clear()
    st.session_state.initialized = True

# Database Status - S3 or Local
selected_db_path = None  # Initialize variable

with st.sidebar.expander("🗄️ Database Status", expanded=True):
    if db_manager.is_s3_enabled():
        st.info("☁️ Using AWS S3 database")
        
        # Sync status
        sync_status = db_manager.get_sync_status()
        if sync_status["last_sync"]:
            sync_time = sync_status["last_sync"].strftime('%H:%M:%S')
            st.success(f"Last sync: {sync_time}")
        else:
            st.warning("Not synced yet")
        
        # Sync controls
        col1, col2 = st.columns(2)
        with col1:
            if st.button("☁️ Save to S3"):
                if db_manager.upload_to_s3():
                    st.success("✅ Synced!")
                    st.rerun()
        
        with col2:
            if st.button("📥 Load from S3"):
                # Clear cache and reload
                st.cache_resource.clear()
                st.rerun()
                
        # Show file info
        st.caption(f"📁 S3: s3://{sync_status['bucket']}/{sync_status['db_key']}")
    else:
        st.info("🏠 Using local database")
        # Get available .db files in data directory for local mode
        import glob
        import os
        data_dir = "./data"
        db_files = glob.glob(os.path.join(data_dir, "*.db"))
        
        if db_files:
            # Extract just the filename for display
            db_options = [os.path.basename(db_file) for db_file in db_files]
            default_db = "transactions.prod.db" if "transactions.prod.db" in db_options else (db_options[0] if db_options else "transactions.sbox.db")
            
            selected_db = st.selectbox(
                "Select Database",
                options=db_options,
                index=db_options.index(default_db) if default_db in db_options else 0,
                help="Choose which database file to load"
            )
            
            selected_db_path = os.path.join(data_dir, selected_db)
            st.caption(f"📁 Local: {selected_db_path}")
        else:
            st.caption("📁 Local: ./data/transactions.prod.db")

# Initialize services with S3 support and selected database path
@st.cache_resource
def get_services(local_path, cache_key):
    """Initialize services with S3-aware database management."""
    return create_services(local_path)

# Create a cache key that changes when database selection changes
cache_key = f"services_{selected_db_path}"
transaction_service, data_manager = get_services(selected_db_path, cache_key)

# Database info
with st.sidebar.expander("📊 Database Info", expanded=False):
    try:
        total_transactions = data_manager.count_all()
        date_range = data_manager.get_date_range()
        
        st.metric("Total Transactions", f"{total_transactions:,}")
        
        if date_range[0] and date_range[1]:
            st.caption(f"📅 {date_range[0].strftime('%Y-%m-%d')} to {date_range[1].strftime('%Y-%m-%d')}")
        
        # File size
        sync_status = db_manager.get_sync_status()
        if sync_status["local_path"] and os.path.exists(sync_status["local_path"]):
            file_size = os.path.getsize(sync_status["local_path"]) / (1024 * 1024)  # MB
            st.caption(f"💾 Size: {file_size:.1f} MB")
        
    except Exception as e:
        st.error(f"Error reading database: {str(e)}")

# Header
st.header('💰 Personal Finance Tracker')

# Load transaction data using new service
@st.cache_data
def load_transactions(cache_key):
    """Load transactions using the service layer."""
    df = transaction_service.get_transactions()
    if not df.empty and 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
        df['month'] = df['date'].dt.to_period('M')
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
    return df

df = load_transactions(cache_key)

if df.empty:
    st.warning("No transactions found. Please sync your accounts or check your data files.")
    # st.stop()

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
    if 'ai_category' in df_filtered.columns:
        categories = st.multiselect(
            "Categories",
            options=sorted(df_filtered['ai_category'].dropna().unique()),
            default=sorted(df_filtered['ai_category'].dropna().unique())
        )
        df_filtered = df_filtered[df_filtered['ai_category'].isin(categories)]
    
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
    
# Key metrics and analysis sections collapsed by default 
with st.expander("📊 Financial Overview", expanded=True):
    # Filter out transfer transactions for financial overview metrics
    transfer_categories = CATEGORY_MAPPING.get("transfers", [])
    overview_data = df_filtered[~df_filtered['ai_category'].isin(transfer_categories)].copy()
    
    # Key metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    spending = overview_data[overview_data['amount'] > 0]['amount'].sum()
    income = abs(overview_data[overview_data['amount'] < 0]['amount'].sum())
    net_flow = income - spending
    transaction_count = len(overview_data)
    
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
            delta="Income - Expenses",
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

with st.expander("📈 Spending Analysis", expanded=True):
    # Combined Income & Expense Multilevel Sunburst
    
    # Filter out transfer transactions from spending analysis
    transfer_categories = CATEGORY_MAPPING.get("transfers", [])
    analysis_data = df_filtered[~df_filtered['ai_category'].isin(transfer_categories)].copy()
    
    # Prepare data for comprehensive sunburst
    income_data = analysis_data[analysis_data['amount'] < 0].copy()
    expense_data = analysis_data[analysis_data['amount'] > 0].copy()
    
    if not income_data.empty or not expense_data.empty:
        flow_data = []
        
        # Add root node
        total_income = income_data['amount'].abs().sum() if not income_data.empty else 0
        total_expenses = expense_data['amount'].sum() if not expense_data.empty else 0
        net_flow = total_income - total_expenses
        
        flow_data.append({
            'ids': "Financial_Flow",
            'labels': f"Net Flow: ${net_flow:,.0f}",
            'parents': "",
            'values': total_income + total_expenses
        })
        
        # Create reverse mapping from AI category to parent category
        ai_to_parent = {}
        for parent_cat, ai_categories in CATEGORY_MAPPING.items():
            for ai_cat in ai_categories:
                ai_to_parent[ai_cat] = parent_cat
        
        # Process Income side
        if not income_data.empty:
            # Add income root
            flow_data.append({
                'ids': "Income_Root",
                'labels': f"Income: ${total_income:,.0f}",
                'parents': "Financial_Flow",
                'values': total_income
            })
            
            # Group income by parent categories
            income_parent_totals = {}
            income_by_category = income_data.groupby('ai_category')['amount'].sum().abs()
            
            for ai_cat, amount in income_by_category.items():
                parent_cat = ai_to_parent.get(ai_cat, 'other')
                if parent_cat not in income_parent_totals:
                    income_parent_totals[parent_cat] = 0
                income_parent_totals[parent_cat] += amount
            
            # Add income parent category nodes
            for parent_cat, total_amount in income_parent_totals.items():
                flow_data.append({
                    'ids': f"income_parent_{parent_cat}",
                    'labels': f"{parent_cat.title()}: ${total_amount:,.0f}",
                    'parents': "Income_Root",
                    'values': total_amount
                })
            
            # Add income AI category nodes
            for ai_cat, amount in income_by_category.items():
                parent_cat = ai_to_parent.get(ai_cat, 'other')
                flow_data.append({
                    'ids': f"income_ai_{ai_cat}",
                    'labels': f"{ai_cat}: ${amount:,.0f}",
                    'parents': f"income_parent_{parent_cat}",
                    'values': amount
                })
        
        # Process Expense side
        if not expense_data.empty:
            # Add expense root
            flow_data.append({
                'ids': "Expense_Root",
                'labels': f"Expenses: ${total_expenses:,.0f}",
                'parents': "Financial_Flow",
                'values': total_expenses
            })
            
            # Group expenses by parent categories
            expense_parent_totals = {}
            expense_by_category = expense_data.groupby('ai_category')['amount'].sum()
            
            for ai_cat, amount in expense_by_category.items():
                parent_cat = ai_to_parent.get(ai_cat, 'other')
                if parent_cat not in expense_parent_totals:
                    expense_parent_totals[parent_cat] = 0
                expense_parent_totals[parent_cat] += amount
            
            # Add expense parent category nodes
            for parent_cat, total_amount in expense_parent_totals.items():
                flow_data.append({
                    'ids': f"expense_parent_{parent_cat}",
                    'labels': f"{parent_cat.title()}: ${total_amount:,.0f}",
                    'parents': "Expense_Root",
                    'values': total_amount
                })
            
            # Add expense AI category nodes
            for ai_cat, amount in expense_by_category.items():
                parent_cat = ai_to_parent.get(ai_cat, 'other')
                flow_data.append({
                    'ids': f"expense_ai_{ai_cat}",
                    'labels': f"{ai_cat}: ${amount:,.0f}",
                    'parents': f"expense_parent_{parent_cat}",
                    'values': amount
                })
        
        flow_df = pd.DataFrame(flow_data)
        
        fig_sunburst_complete = px.sunburst(
            flow_df,
            ids='ids',
            names='labels',
            parents='parents',
            values='values',
            title="Complete Financial Flow - Income & Expenses",
            color='labels'
        )
        fig_sunburst_complete.update_traces(textinfo="label+percent parent")
        fig_sunburst_complete.update_layout(height=700)
        st.plotly_chart(fig_sunburst_complete, use_container_width=True)
    else:
        st.info("No transaction data available for visualization")
    
    # Monthly income vs expense histogram       
    # Prepare monthly data for both income and expenses (excluding transfers)
    if not analysis_data.empty and 'month' in analysis_data.columns:
        monthly_income = analysis_data[analysis_data['amount'] < 0].groupby('month')['amount'].sum().abs()
        monthly_expenses = analysis_data[analysis_data['amount'] > 0].groupby('month')['amount'].sum()
    else:
        monthly_income = pd.Series(dtype=float)
        monthly_expenses = pd.Series(dtype=float)
    
    if not monthly_income.empty or not monthly_expenses.empty:
        # Create combined dataframe for histogram
        all_months = set()
        if not monthly_income.empty:
            all_months.update(monthly_income.index)
        if not monthly_expenses.empty:
            all_months.update(monthly_expenses.index)
        
        histogram_data = []
        for month in sorted(all_months):
            month_str = str(month)
            
            # Add income bar
            income_amount = monthly_income.get(month, 0)
            if income_amount > 0:
                histogram_data.append({
                    'month': month_str,
                    'amount': income_amount,
                    'type': 'Income'
                })
            
            # Add expense bar
            expense_amount = monthly_expenses.get(month, 0)
            if expense_amount > 0:
                histogram_data.append({
                    'month': month_str,
                    'amount': expense_amount,
                    'type': 'Expenses'
                })
        
        if histogram_data:
            histogram_df = pd.DataFrame(histogram_data)
            
            fig_histogram = px.bar(
                histogram_df,
                x='month',
                y='amount',
                color='type',
                title="Monthly Income vs Expenses",
                barmode='group',
                color_discrete_map={
                    'Income': '#2E8B57',  # Sea green
                    'Expenses': '#DC143C'  # Crimson
                }
            )
            fig_histogram.update_layout(
                height=400,
                xaxis_title="Month",
                yaxis_title="Amount ($)",
                yaxis_tickformat="$,.0f"
            )
            st.plotly_chart(fig_histogram, use_container_width=True)
        else:
            st.info("No monthly data available")
    else:
        st.info("No monthly data available")

with st.expander("💡 Quick Insights", expanded=False):
    if not df_filtered.empty and 'amount' in df_filtered.columns:
        col1, col2 = st.columns(2)
        
        with col1:
            # Top spending categories
            if 'ai_category' in df_filtered.columns:
                spending_by_cat = df_filtered[df_filtered['amount'] > 0].groupby('ai_category')['amount'].sum().sort_values(ascending=False).head(5)
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

with st.expander("🏷️ Transaction Management", expanded=True):
    
    df_display = df_filtered
    
    # Checkbox to enable editing mode
    enable_editing = st.checkbox("Make Edits", value=False, help="Check this box to enable editing of AI category, notes, and tags")
     
    # Display transactions with editing capabilities
    if not df_display.empty:
        if enable_editing:
            # Select columns for editing mode
            display_columns = [
                'date', 'name', 'merchant_name', 'amount', 'ai_category', 'notes', 'tags',
                'bank_name', 'transaction_id'
            ]
            
            available_columns = [col for col in display_columns if col in df_display.columns]
            
            # Create a copy for display and editing
            df_for_editing = df_display[available_columns].reset_index(drop=True).copy()
            
            # Ensure text columns are properly typed as strings to avoid float type errors
            text_columns = ['ai_category', 'notes', 'tags']
            for col in text_columns:
                if col in df_for_editing.columns:
                    df_for_editing[col] = df_for_editing[col].fillna('').astype(str)
            
            # Get all valid categories from CATEGORY_MAPPING
            valid_categories = []
            for category_list in CATEGORY_MAPPING.values():
                valid_categories.extend(category_list)
            
            # Also include any existing values from the current dataframe to preserve them
            existing_ai_categories = df_for_editing['ai_category'].dropna().unique().tolist() if 'ai_category' in df_for_editing.columns else []
            
            # Combine valid categories with existing ones (remove duplicates)
            all_category_options = list(set(valid_categories + existing_ai_categories))
            all_category_options = [cat for cat in all_category_options if cat and str(cat) != 'nan' and str(cat).strip() != '']
            
            # Display editable dataframe
            edited_df = st.data_editor(
                df_for_editing,
                column_config={
                    "date": st.column_config.DateColumn(
                        "Date",
                        format="MM/DD/YYYY",
                        disabled=True
                    ),
                    "name": st.column_config.TextColumn(
                        "Name",
                        help="Transaction description",
                        disabled=True
                    ),
                    "merchant_name": st.column_config.TextColumn(
                        "Merchant",
                        help="Merchant name",
                        disabled=True
                    ),
                    "amount": st.column_config.NumberColumn(
                        "Amount",
                        format="$%.2f",
                        disabled=True
                    ),
                    "ai_category": st.column_config.SelectboxColumn(
                        "AI Category",
                        help="Select AI category",
                        options=sorted(all_category_options),
                        required=False
                    ),
                    "notes": st.column_config.TextColumn(
                        "Notes",
                        help="Add your notes about this transaction"
                    ),
                    "tags": st.column_config.TextColumn(
                        "Tags",
                        help="Add comma-separated tags"
                    ),
                    "bank_name": st.column_config.TextColumn(
                        "Bank",
                        help="Bank name",
                        disabled=True
                    ),
                    "transaction_id": st.column_config.TextColumn(
                        "Transaction ID",
                        help="Unique transaction identifier",
                        disabled=True
                    )
                },
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                key="transaction_editor"
            )
            
            # Add save button
            if st.button("💾 Save Changes", type="primary"):
                try:
                    # Prepare bulk updates for data manager
                    updates = {}
                    changes_made = 0
                    
                    for idx, edited_row in edited_df.iterrows():
                        transaction_id = edited_row['transaction_id']
                        
                        if transaction_id:
                            # Prepare updates for this transaction
                            row_updates = {}
                            if 'ai_category' in edited_row:
                                row_updates['ai_category'] = edited_row['ai_category']
                            if 'notes' in edited_row:
                                row_updates['notes'] = edited_row['notes']
                            if 'tags' in edited_row:
                                row_updates['tags'] = edited_row['tags']
                            
                            if row_updates:
                                updates[transaction_id] = row_updates
                                changes_made += 1
                    
                    # Use transaction service for bulk update (supports S3 sync)
                    if updates:
                        if hasattr(transaction_service, 'bulk_update_transactions'):
                            updated_count = transaction_service.bulk_update_transactions(updates)
                        else:
                            updated_count = data_manager.bulk_update(updates)
                        st.success(f"✅ Successfully saved changes to {updated_count} transactions!")
                        st.cache_data.clear()  # Clear cache to refresh data
                        st.rerun()  # Refresh the app to show updated data
                    else:
                        st.info("No changes were made.")
                        
                except Exception as e:
                    st.error(f"❌ Error saving changes: {str(e)}")
        else:
            # Display read-only comprehensive view
            display_columns = [
                'date', 'authorized_date', 'name', 'merchant_name', 'amount', 'ai_category', 'notes', 'tags',
                'ai_reason', 'plaid_category', 'bank_name', 'account_owner', 'pending', 'transaction_id'
            ]
            
            available_columns = [col for col in display_columns if col in df_display.columns]
            
            # Create a copy for display and convert date columns to proper datetime
            df_for_display = df_display[available_columns].reset_index(drop=True).copy()
            
            # Convert date strings to datetime for proper display
            if 'authorized_date' in df_for_display.columns:
                df_for_display['authorized_date'] = pd.to_datetime(df_for_display['authorized_date'], errors='coerce')
            
            # Display transactions (read-only)
            st.dataframe(
                df_for_display,
                column_config={
                    "date": st.column_config.DateColumn(
                        "Date",
                        format="MM/DD/YYYY"
                    ),
                    "authorized_date": st.column_config.DateColumn(
                        "Auth Date",
                        format="MM/DD/YYYY",
                        help="When transaction was authorized"
                    ),
                    "name": st.column_config.TextColumn(
                        "Name",
                        help="Transaction description"
                    ),
                    "amount": st.column_config.NumberColumn(
                        "Amount",
                        format="$%.2f"
                    ),
                    "ai_category": st.column_config.TextColumn(
                        "AI Category"
                    ),
                    "ai_reason": st.column_config.TextColumn(
                        "AI Reason",
                        help="AI reasoning for categorization"
                    ),
                    "notes": st.column_config.TextColumn(
                        "Notes",
                        help="Notes about this transaction"
                    ),
                    "tags": st.column_config.TextColumn(
                        "Tags",
                        help="Tags for this transaction"
                    ),
                    "plaid_category": st.column_config.TextColumn(
                        "Plaid categorization",
                        help="Plaid's primary personal finance category"
                    ),
                    "merchant_name": st.column_config.TextColumn(
                        "Merchant",
                        help="Merchant name"
                    ),
                    "bank_name": st.column_config.TextColumn(
                        "Bank",
                        help="Bank name"
                    ),
                    "account_owner": st.column_config.TextColumn(
                        "Account Owner",
                        help="Account owner name"
                    ),
                    "pending": st.column_config.CheckboxColumn(
                        "Pending"
                    ),
                    "transaction_id": st.column_config.TextColumn(
                        "Transaction ID",
                        help="Unique transaction identifier"
                    )
                },
                use_container_width=True,
                hide_index=True
            )
    
    else:
        st.info("No transactions match your current filters.")

    col1, col2 = st.columns([2, 1])
    with col1:
        transaction_id_input = st.text_input(
            "AI Categorize: Transaction ID", 
            placeholder="Paste transaction ID here...",
            help="Copy a transaction ID from the table below to categorize with AI"
        )
    with col2:
        st.write("")  # Add spacing
        ask_ai_button = st.button("🤖 Ask AI", type="primary", disabled=not transaction_id_input)
    
    # Handle single AI categorization
    if ask_ai_button and transaction_id_input:
        try:            
            with st.spinner("🤖 Analyzing transaction with Claude..."):
                try:
                    # Use new service for categorization
                    result = transaction_service.categorize_transaction(transaction_id_input.strip())
                    
                    if result.success:
                        st.success(f"✅ Categorized as: **{result.category}**")
                        st.info(f"Reasoning: {result.reasoning}")
                        # Clear cache to show updated data
                        st.cache_data.clear()
                    else:
                        st.error(f"❌ Error: {result.error}")
                    
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
        
        except ImportError as e:
            st.error(f"❌ Import error: {str(e)}")
    
    # Bulk AI Categorization Section    
    col1, col2 = st.columns([3, 1])
    with col1:
        force_recategorize_all = st.checkbox(
            "Recategorize ALL transactions",
            value=False,
            help="If checked, will recategorize all transactions. If unchecked, only categorizes uncategorized transactions."
        )
    
    with col2:
        st.write("")  # Add spacing
        bulk_categorize_button = st.button("🤖 Bulk Categorize", type="secondary")
    
    # Handle bulk AI categorization
    if bulk_categorize_button:
        try:
            with st.spinner("🤖 Running bulk categorization with Claude..."):
                # Use the checkbox value to set force_recategorize
                result = transaction_service.bulk_categorize(force_recategorize=force_recategorize_all)
                
                if result.successful_count > 0:
                    st.success(f"✅ Successfully categorized {result.successful_count} transactions!")
                    
                if result.failed_count > 0:
                    st.warning(f"⚠️ Failed to categorize {result.failed_count} transactions")
                    
                    # Show first few errors
                    if result.errors:
                        with st.expander("View Errors", expanded=False):
                            for error in result.errors[:10]:  # Show first 10 errors
                                st.error(f"• {error}")
                            if len(result.errors) > 10:
                                st.info(f"... and {len(result.errors) - 10} more errors")
                
                if result.successful_count == 0 and result.failed_count == 0:
                    if force_recategorize_all:
                        st.info(f"No transactions found to categorize")
                    else:
                        st.info(f"No uncategorized transactions found")
                
                # Clear cache to show updated data
                st.cache_data.clear()
                
        except Exception as e:
            st.error(f"❌ Error in bulk categorization: {str(e)}")
    
# Account Management Section
with st.expander("🔧 Account Management", expanded=False):
    st.subheader("Sync Options")
    
    # Get connected accounts for dropdown using new service
    accounts = transaction_service.get_accounts()
    account_options = ["All Accounts"]
    
    if accounts:
        for bank_name in accounts.keys():
            if 'accounts' in accounts[bank_name]:
                account_options.append(bank_name)
    
    # Account selection dropdown
    selected_account = st.selectbox(
        "Select Account to Sync",
        options=account_options,
        index=0,
        help="Choose which account to sync, or 'All Accounts' to sync everything",
        key="account_selector"
    )
    
    # Sync options
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔄 Incremental Sync", type="primary", help="Fetch only new transactions since last sync"):
            with st.spinner(f"Syncing new transactions for {selected_account}..."):
                if selected_account == "All Accounts":
                    result: SyncResult = transaction_service.sync_all_accounts(full_sync=False)
                else:
                    result: SyncResult = transaction_service.sync_account(selected_account, full_sync=False)
                
                # Display structured result
                if result.success:
                    st.success(f"✅ Added {result.new_transactions} new transactions")
                    if result.institution_results:
                        for bank, count in result.institution_results.items():
                            st.write(f"• {bank}: {count} transactions")
                else:
                    st.error("❌ Sync failed:")
                    for error in result.errors:
                        st.error(f"  - {error}")
    
    with col2:
        if st.button("🔄 Full Sync", type="secondary", help="Re-fetch all historical transactions"):
            with st.spinner(f"Performing full sync for {selected_account}..."):
                if selected_account == "All Accounts":
                    result: SyncResult = transaction_service.sync_all_accounts(full_sync=True)
                else:
                    result: SyncResult = transaction_service.sync_account(selected_account, full_sync=True)
                
                # Display structured result
                if result.success:
                    st.success(f"✅ Added {result.new_transactions} new transactions")
                    if result.institution_results:
                        for bank, count in result.institution_results.items():
                            st.write(f"• {bank}: {count} transactions")
                else:
                    st.error("❌ Sync failed:")
                    for error in result.errors:
                        st.error(f"  - {error}")
    
    # Connected accounts info
    st.subheader("Connected Accounts")
    if accounts:
        # Get access tokens data for additional info using service
        sync_status = transaction_service.get_sync_status()
        
        for bank, info in accounts.items():
            if 'accounts' in info:
                # Bank header with styling and data source indicator
                data_source_icon = "🔄" if info.get('data_source') != 'database' else "💾"
                data_source_text = "fresh data" if info.get('data_source') != 'database' else "cached data"
                
                st.markdown(f"####### 🏦 {bank} ({len(info['accounts'])} accounts) {data_source_icon}")
                if info.get('data_source') == 'database':
                    st.caption(f"ℹ️ Showing cached data from database (Plaid API unavailable)")
                
                # Display individual accounts
                for acc in info['accounts']:
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        # Handle both fresh API data (name/official_name) and database data (account_name)
                        account_name = (
                            acc.get('official_name') or 
                            acc.get('name') or 
                            acc.get('account_name') or 
                            'Unknown Account'
                        )
                        account_type = acc.get('type') or acc.get('account_type') or 'Unknown'
                        account_subtype = acc.get('subtype') or acc.get('account_subtype') or 'Unknown'
                        
                        st.write(f"**{account_name}**")
                        # st.caption(f"{account_type} - {account_subtype}")
                    with col2:
                        # Handle both fresh API data and database data
                        balance = acc.get('balance_current', -1)
                        # Convert to float if it's a string, handle None
                        try:
                            balance_float = float(balance) if balance is not None else 0.0
                        except (ValueError, TypeError):
                            balance_float = 0.0
                        st.write(f"**Balance:** ${balance_float:,.2f}")
                    with col3:
                        mask = acc.get('mask', 'N/A')
                        st.write(f"**Account:** •••• {mask}")
                
                # Display sync metadata
                col1, col2 = st.columns(2)
                with col1:
                    connected_at = info.get('created_at', 'Unknown')
                    if connected_at and connected_at != 'Unknown':
                        try:
                            connected_dt = datetime.fromisoformat(connected_at)
                            connected_display = connected_dt.strftime('%Y-%m-%d %H:%M')
                        except:
                            connected_display = connected_at
                    else:
                        connected_display = "Unknown"
                    st.write(f"**Connected:** {connected_display}")

                with col2:
                    last_sync = sync_status.get(bank)
                    if last_sync:
                        sync_display = last_sync.strftime('%Y-%m-%d %H:%M')
                    else:
                        sync_display = "Never"
                    st.write(f"**Last Sync:** {sync_display}")

                # Add separator between banks
                st.markdown("---")
    else:
        st.write("No accounts connected. Please link your accounts first.")
        
        # Add link to Account Linking page
        st.info("💡 Use the Link New Account section below to connect your bank accounts.")

# Link New Account Section
with st.expander("🔗 Link New Account", expanded=False):
    from plaid_client import PlaidClient
    plaid_client = PlaidClient()
    
    # Use simple link token generation and HTML file approach (known to work)
    st.markdown("""
    **Link Your Bank Account:**
    
    This will create a link token and generate an HTML file for you to use with Plaid Link.
    """)
    
    if st.button("🔗 Get Link Token & HTML", type="primary"):
        try:
            with st.spinner("Creating link token..."):
                # Create simple link token
                link_token = plaid_client.create_link_token("user_1")
                st.session_state['link_token'] = link_token
                
            st.success("✅ Link token created!")
            
            # Create simple HTML content
            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Plaid Link</title>
    <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
</head>
<body>
    <h2>Connect Your Bank Account</h2>
    <button id="link-button" style="background: #00D4AA; color: white; padding: 12px 24px; border: none; border-radius: 6px; cursor: pointer; font-size: 16px;">
        Connect Account
    </button>
    
    <div id="result" style="display: none; margin-top: 20px; padding: 15px; background: #f0f8f0; border-radius: 6px;">
        <h3>✅ Success!</h3>
        <p><strong>Public Token:</strong> <span id="public-token"></span></p>
        <p><strong>Institution:</strong> <span id="institution-name"></span></p>
        <p>Copy these values back to the Streamlit app.</p>
    </div>

    <script>
    var handler = Plaid.create({{
        token: '{link_token}',
        onSuccess: function(public_token, metadata) {{
            document.getElementById('public-token').textContent = public_token;
            document.getElementById('institution-name').textContent = metadata.institution.name;
            document.getElementById('result').style.display = 'block';
            document.getElementById('link-button').style.display = 'none';
        }},
        onExit: function(err, metadata) {{
            if (err != null) {{
                alert('Error: ' + JSON.stringify(err));
            }}
        }}
    }});

    document.getElementById('link-button').onclick = function() {{
        handler.open();
    }};
    </script>
</body>
</html>"""
            
            # Offer download
            st.download_button(
                label="📄 Download Plaid Link HTML",
                data=html_content,
                file_name="plaid_link.html",
                mime="text/html",
                help="Download and open this file in your browser"
            )
            
            st.info("💡 **Instructions:** Download the HTML file, open it in your browser, connect your account, then copy the tokens back here.")
            
        except Exception as e:
            st.error(f"Error creating link token: {str(e)}")
    
    # Manual token entry fallback
    st.markdown("---")
    st.subheader("📝 Manual Token Entry")
    st.caption("Use this if the automatic link doesn't work or to paste tokens from the link above")
    
    with st.form("manual_token_entry"):
        col1, col2 = st.columns(2)
        with col1:
            manual_public_token = st.text_input(
                "Public Token", 
                placeholder="public-sandbox-...",
                help="The public_token from Plaid Link"
            )
        with col2:
            manual_institution_name = st.text_input(
                "Institution Name", 
                placeholder="e.g., Chase, Bank of America",
                help="The institution_name from Plaid Link"
            )
        
        manual_submitted = st.form_submit_button("💾 Save Connected Account", type="secondary")
        
        if manual_submitted:
            if not manual_public_token or not manual_institution_name:
                st.error("Please provide both public token and institution name")
            else:
                try:
                    with st.spinner("Processing account connection..."):
                        link_result = transaction_service.link_account(manual_public_token, manual_institution_name)
                        
                        if link_result.success:
                            st.success(f"✅ Successfully connected {link_result.institution_name} with {link_result.account_count} accounts!")
                            st.info("Refresh the page to see your connected accounts above.")
                        else:
                            st.error(f"❌ Error processing connection: {link_result.error}")
                            
                except Exception as e:
                    st.error(f"❌ Error processing connection: {str(e)}")

# Main dashboard check for data availability
if df_filtered.empty:
    st.warning("No transactions found with current filters.")