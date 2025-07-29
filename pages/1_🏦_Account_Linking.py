import streamlit as st
from plaid_client import PlaidClient
from sync_service import TransactionSyncService
import time

def plaid_link_page():
    st.header("🏦 Link Bank Accounts")
    
    plaid_client = PlaidClient()
    sync_service = TransactionSyncService()
    
    st.info("Connect your bank accounts securely through Plaid to automatically sync transactions.")
    
    # Show connected accounts
    accounts = sync_service.get_connected_accounts()
    if accounts and not accounts.get('message'):
        st.subheader("✅ Connected Accounts")
        for bank, info in accounts.items():
            if 'accounts' in info:
                with st.expander(f"{bank} ({len(info['accounts'])} accounts)"):
                    for acc in info['accounts']:
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.write(f"**{acc['name']}**")
                        with col2:
                            st.write(f"Type: {acc['type']}")
                        with col3:
                            st.write(f"Balance: ${acc['balance']:,.2f}")
    
    st.subheader("🔗 Link New Account")
    
    # Simplified approach - provide instructions to use FastAPI temporarily
    st.markdown("""
    **Quick Setup Instructions:**
    
    Since Plaid Link requires specific JavaScript handling, please use this simple process:
    """)
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        if st.button("🔗 Get Link Token", type="primary"):
            try:
                with st.spinner("Creating link token..."):
                    link_token = plaid_client.create_link_token("user_1")
                    st.session_state['link_token'] = link_token
                st.success("✅ Link token created!")
                st.info("Use the link token below with the Plaid Link demo")
            except Exception as e:
                st.error(f"Error creating link token: {str(e)}")
    
    with col2:
        if 'link_token' in st.session_state:
            st.text_area(
                "Link Token (copy this):", 
                value=st.session_state['link_token'],
                height=100,
                help="Copy this token to use with Plaid Link"
            )
            
            # Create a simple HTML page for linking with better error handling
            plaid_html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Plaid Link - Account Linking</title>
    <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; text-align: center; background: #f5f5f5; }}
        .container {{ max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        button {{ background: #007bff; color: white; padding: 15px 30px; 
                 border: none; border-radius: 5px; cursor: pointer; font-size: 18px; margin: 10px; }}
        button:hover {{ background: #0056b3; }}
        .result {{ margin: 20px 0; padding: 20px; border-radius: 5px; }}
        .success {{ background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }}
        .error {{ background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }}
        textarea {{ width: 100%; height: 120px; margin: 10px 0; padding: 10px; border: 1px solid #ddd; border-radius: 4px; }}
        .debug {{ background: #fff3cd; color: #856404; padding: 10px; margin: 10px 0; border-radius: 4px; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🏦 Connect Your Bank Account</h1>
        <div class="debug">
            <strong>Environment:</strong> Production<br>
            <strong>Token:</strong> {st.session_state['link_token'][:20]}...
        </div>
        
        <button onclick="linkAccount()">Link Account with Plaid</button>
        <div id="result"></div>
    </div>
    
    <script>
        console.log('Plaid Link Token:', '{st.session_state['link_token'][:30]}...');
        
        function linkAccount() {{
            console.log('Starting Plaid Link...');
            
            try {{
                const handler = Plaid.create({{
                    token: '{st.session_state['link_token']}',
                    onSuccess: (public_token, metadata) => {{
                        console.log('Plaid Link Success:', metadata);
                        
                        document.getElementById('result').innerHTML = 
                            '<div class="result success">' +
                            '<h3>✅ Account Successfully Linked!</h3>' +
                            '<p><strong>Institution:</strong> ' + metadata.institution.name + '</p>' +
                            '<p><strong>Accounts Connected:</strong> ' + metadata.accounts.length + '</p>' +
                            '<p><strong>Copy this information and paste it in Streamlit:</strong></p>' +
                            '<textarea readonly onclick="this.select()">' +
                            JSON.stringify({{
                                public_token: public_token,
                                institution_name: metadata.institution.name
                            }}, null, 2) +
                            '</textarea>' +
                            '<p><strong>Next:</strong> Go back to Streamlit and use the "Complete Account Connection" form.</p>' +
                            '</div>';
                    }},
                    onExit: (err, metadata) => {{
                        console.log('Plaid Link Exit:', err, metadata);
                        
                        if (err != null) {{
                            document.getElementById('result').innerHTML = 
                                '<div class="result error">' +
                                '<h3>❌ Account Linking Failed</h3>' +
                                '<p><strong>Error:</strong> ' + (err.error_message || err.error_code || 'Unknown error') + '</p>' +
                                '<p><strong>Error Type:</strong> ' + (err.error_type || 'Unknown') + '</p>' +
                                '<p>Please try again or contact support if the issue persists.</p>' +
                                '</div>';
                        }} else {{
                            document.getElementById('result').innerHTML = 
                                '<div class="result" style="background: #fff3cd; color: #856404; border: 1px solid #ffeaa7;">' +
                                '<h3>Account Linking Cancelled</h3>' +
                                '<p>You cancelled the account linking process.</p>' +
                                '</div>';
                        }}
                    }},
                    onLoad: () => {{
                        console.log('Plaid Link loaded successfully');
                    }},
                    onEvent: (eventName, metadata) => {{
                        console.log('Plaid Link Event:', eventName, metadata);
                    }}
                }});
                
                console.log('Opening Plaid Link...');
                handler.open();
                
            }} catch (error) {{
                console.error('Error initializing Plaid Link:', error);
                document.getElementById('result').innerHTML = 
                    '<div class="result error">' +
                    '<h3>❌ Initialization Error</h3>' +
                    '<p><strong>Error:</strong> ' + error.message + '</p>' +
                    '<p>Check your browser console for more details.</p>' +
                    '</div>';
            }}
        }}
        
        // Auto-check if Plaid is loaded
        window.addEventListener('load', function() {{
            if (typeof Plaid === 'undefined') {{
                document.getElementById('result').innerHTML = 
                    '<div class="result error">' +
                    '<h3>❌ Plaid Library Failed to Load</h3>' +
                    '<p>Please check your internet connection and try refreshing the page.</p>' +
                    '</div>';
            }} else {{
                console.log('Plaid library loaded successfully');
            }}
        }});
    </script>
</body>
</html>"""
            
            # Save HTML to a temporary file or show instructions
            st.download_button(
                label="📄 Download Plaid Link Page",
                data=plaid_html,
                file_name="plaid_link.html",
                mime="text/html",
                help="Download and open this HTML file in your browser to link your account"
            )
            
            st.info("💡 **Instructions:** Download the HTML file above, open it in your browser, and link your account. Then come back here to complete the process.")
    
    # Form to process the linking result
    st.markdown("---")
    st.subheader("📝 Complete Account Connection")
    
    with st.form("process_account_link"):
        st.markdown("After linking your account using the HTML file above, paste the information here:")
        
        col1, col2 = st.columns(2)
        with col1:
            public_token = st.text_input(
                "Public Token", 
                placeholder="public-sandbox-...",
                help="The public_token from the linking result"
            )
        with col2:
            institution_name = st.text_input(
                "Institution Name", 
                placeholder="e.g., Chase, Bank of America",
                help="The institution_name from the linking result"
            )
        
        submitted = st.form_submit_button("💾 Save Connected Account", type="primary")
        
        if submitted:
            if not public_token or not institution_name:
                st.error("Please provide both public token and institution name")
            else:
                try:
                    with st.spinner("Processing account connection..."):
                        # Exchange public token for access token
                        access_token = plaid_client.exchange_public_token(public_token)
                        
                        # Get account information
                        account_info = plaid_client.get_accounts(access_token)
                        
                        # Save access token and account info
                        sync_service.save_access_token(
                            institution_name=institution_name,
                            access_token=access_token,
                            account_info=account_info
                        )
                        
                        st.success(f"✅ Successfully connected {institution_name} with {len(account_info)} accounts!")
                        st.info("Refresh the page to see your connected accounts above.")
                        
                        # Clear the link token
                        if 'link_token' in st.session_state:
                            del st.session_state['link_token']
                        
                except Exception as e:
                    st.error(f"❌ Error processing connection: {str(e)}")
                    st.error("Please check that your public token is correct and try again.")
    
    st.markdown("---")
    st.subheader("🔄 Sync Transactions")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Recent Transactions**")
        if st.button("Sync All Connected Accounts", type="secondary"):
            with st.spinner("Syncing recent transactions..."):
                result = sync_service.sync_all_accounts()
                
                if result.get('errors'):
                    st.error(f"Sync errors: {', '.join(result['errors'])}")
                if result.get('info'):
                    st.warning(result['info'])
                if result.get('total_new_transactions', 0) > 0 or result.get('accounts_synced', 0) > 0:
                    st.success(f"✅ Successfully synced {result.get('total_new_transactions', 0)} new transactions from {result.get('accounts_synced', 0)} accounts!")
                else:
                    st.info("No new transactions found or all accounts were rate limited.")
                    
                # Show sync details
                if result.get('account_details'):
                    with st.expander("📊 Sync Details"):
                        for bank, details in result['account_details'].items():
                            st.write(f"**{bank}**: {details['new_transactions']} new transactions (of {details['total_transactions_fetched']} fetched)")
    
    with col2:
        st.markdown("**Historical Transactions**")
        
        # Historical sync options
        months_back = st.selectbox(
            "Import historical data:",
            options=[3, 6, 12, 24],
            index=2,  # Default to 12 months
            format_func=lambda x: f"Last {x} months",
            help="Note: Plaid typically provides up to 24 months of historical data"
        )
        
        if st.button("🗂️ Import Historical Data", type="primary"):
            with st.spinner(f"Importing {months_back} months of historical transactions..."):
                result = sync_service.sync_historical_transactions(months_back=months_back)
                
                if result.get('errors'):
                    st.error(f"Import errors: {', '.join(result['errors'])}")
                if result.get('info'):
                    st.warning(result['info'])
                if result.get('total_new_transactions', 0) > 0:
                    st.success(f"🎉 Successfully imported {result.get('total_new_transactions', 0)} historical transactions from {result.get('accounts_synced', 0)} accounts!")
                    st.info("Historical data import complete! Check your dashboard for the full transaction history.")
                else:
                    st.info("No historical transactions found or all accounts were rate limited.")
                
                # Show import details
                if result.get('account_details'):
                    with st.expander("📊 Import Details"):
                        for bank, details in result['account_details'].items():
                            st.write(f"**{bank}**: {details['new_transactions']} new transactions (of {details['total_transactions_fetched']} fetched)")
    
    st.info("💡 **Tip**: Use 'Recent Transactions' for daily updates and 'Historical Data' for the initial import of past transactions.")

if __name__ == "__main__":
    plaid_link_page()