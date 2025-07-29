import streamlit as st
import pandas as pd
from data_manager import DataManager
from datetime import datetime
import io

def data_export_page():
    st.header("📊 Data Export & Analysis")
    
    data_manager = DataManager()
    
    # Load data
    df = data_manager.read_transactions()
    
    if df.empty:
        st.warning("No transaction data found. Please sync your accounts first.")
        return
    
    # Convert date column
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
    
    st.subheader("📈 Data Summary")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Transactions", len(df))
    
    with col2:
        if 'bank_name' in df.columns:
            st.metric("Connected Banks", df['bank_name'].nunique())
    
    with col3:
        if 'date' in df.columns:
            date_range = (df['date'].max() - df['date'].min()).days
            st.metric("Days of Data", date_range)
    
    with col4:
        if 'custom_category' in df.columns:
            st.metric("Categories", df['custom_category'].nunique())
    
    # Export options
    st.subheader("💾 Export Options")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Date range for export
        if not df.empty and 'date' in df.columns:
            min_date = df['date'].min().date()
            max_date = df['date'].max().date()
            
            export_date_range = st.date_input(
                "Export Date Range",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date
            )
        
        # Category selection
        if 'custom_category' in df.columns:
            selected_categories = st.multiselect(
                "Export Categories",
                options=sorted(df['custom_category'].dropna().unique()),
                default=sorted(df['custom_category'].dropna().unique())
            )
    
    with col2:
        # Column selection
        available_columns = [
            'date', 'name', 'amount', 'custom_category', 
            'merchant_name', 'bank_name', 'category', 
            'original_description', 'pending'
        ]
        
        export_columns = st.multiselect(
            "Export Columns",
            options=[col for col in available_columns if col in df.columns],
            default=[col for col in ['date', 'name', 'amount', 'custom_category', 'merchant_name', 'bank_name'] if col in df.columns]
        )
        
        # Export format
        export_format = st.selectbox(
            "Export Format",
            options=["CSV", "Excel", "JSON"]
        )
    
    # Filter data for export
    if len(export_date_range) == 2 and 'date' in df.columns:
        start_date, end_date = export_date_range
        export_df = df[(df['date'].dt.date >= start_date) & (df['date'].dt.date <= end_date)]
    else:
        export_df = df
    
    if 'custom_category' in df.columns and selected_categories:
        export_df = export_df[export_df['custom_category'].isin(selected_categories)]
    
    if export_columns:
        export_df = export_df[export_columns]
    
    # Show preview
    st.subheader("👀 Export Preview")
    st.dataframe(export_df.head(10), use_container_width=True)
    st.info(f"Export will contain {len(export_df)} transactions")
    
    # Download buttons
    if not export_df.empty:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if export_format == "CSV":
                csv_data = export_df.to_csv(index=False)
                st.download_button(
                    label="📥 Download CSV",
                    data=csv_data,
                    file_name=f"transactions_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    type="primary"
                )
        
        with col2:
            if export_format == "Excel":
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    export_df.to_excel(writer, sheet_name='Transactions', index=False)
                excel_data = buffer.getvalue()
                
                st.download_button(
                    label="📥 Download Excel",
                    data=excel_data,
                    file_name=f"transactions_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary"
                )
        
        with col3:
            if export_format == "JSON":
                json_data = export_df.to_json(orient='records', date_format='iso', indent=2)
                st.download_button(
                    label="📥 Download JSON",
                    data=json_data,
                    file_name=f"transactions_{datetime.now().strftime('%Y%m%d')}.json",
                    mime="application/json",
                    type="primary"
                )
    
    # Quick insights
    st.subheader("💡 Quick Insights")
    
    if not export_df.empty and 'amount' in export_df.columns:
        col1, col2 = st.columns(2)
        
        with col1:
            # Top spending categories
            if 'custom_category' in export_df.columns:
                spending_by_cat = export_df[export_df['amount'] > 0].groupby('custom_category')['amount'].sum().sort_values(ascending=False).head(5)
                st.write("**Top 5 Spending Categories:**")
                for cat, amount in spending_by_cat.items():
                    st.write(f"• {cat}: ${amount:,.2f}")
        
        with col2:
            # Top merchants
            if 'merchant_name' in export_df.columns:
                top_merchants = export_df[export_df['amount'] > 0].groupby('merchant_name')['amount'].sum().sort_values(ascending=False).head(5)
                st.write("**Top 5 Merchants:**")
                for merchant, amount in top_merchants.items():
                    if pd.notna(merchant):
                        st.write(f"• {merchant}: ${amount:,.2f}")

if __name__ == "__main__":
    data_export_page()