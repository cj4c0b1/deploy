import pandas as pd
import plotly.express as px
import streamlit as st

from frontend.st_utils import get_backend_api_client, initialize_st_page

initialize_st_page(title="Portfolio", icon="💰")

# Page content
client = get_backend_api_client()
NUM_COLUMNS = 4


# Convert portfolio state to DataFrame for easier manipulation
def portfolio_state_to_df(portfolio_state):
    data = []
    for account, exchanges in portfolio_state.items():
        for exchange, tokens_info in exchanges.items():
            for info in tokens_info:
                data.append({
                    "account": account,
                    "exchange": exchange,
                    "token": info["token"],
                    "price": info["price"],
                    "units": info["units"],
                    "value": info["value"],
                    "available_units": info["available_units"],
                })
    return pd.DataFrame(data)


# Convert historical portfolio states to DataFrame
def portfolio_history_to_df(history):
    data = []
    for record in history:
        timestamp = record["timestamp"]
        for account, exchanges in record["state"].items():
            for exchange, tokens_info in exchanges.items():
                for info in tokens_info:
                    data.append({
                        "timestamp": timestamp,
                        "account": account,
                        "exchange": exchange,
                        "token": info["token"],
                        "price": info["price"],
                        "units": info["units"],
                        "value": info["value"],
                        "available_units": info["available_units"],
                    })
    return pd.DataFrame(data)


# Aggregate portfolio history by grouping nearby timestamps
def aggregate_portfolio_history(history_df, time_window_seconds=10):
    """
    Aggregate portfolio history by grouping timestamps within a time window.
    This solves the issue where different exchanges are logged at slightly different times.
    """
    if len(history_df) == 0:
        return history_df
    
    # Convert timestamp to pandas datetime if not already
    history_df['timestamp'] = pd.to_datetime(history_df['timestamp'])
    
    # Sort by timestamp
    history_df = history_df.sort_values('timestamp')
    
    # Create time groups by rounding timestamps to the nearest time window
    history_df['time_group'] = history_df['timestamp'].dt.floor(f'{time_window_seconds}s')
    
    # For each time group, aggregate the data
    aggregated_data = []
    
    for time_group in history_df['time_group'].unique():
        group_data = history_df[history_df['time_group'] == time_group]
        
        # Aggregate by account, exchange, token within this time group
        agg_group = group_data.groupby(['account', 'exchange', 'token']).agg({
            'value': 'sum',
            'units': 'sum', 
            'available_units': 'sum',
            'price': 'mean'  # Use mean price for the time group
        }).reset_index()
        
        # Add the time group as timestamp
        agg_group['timestamp'] = time_group
        
        aggregated_data.append(agg_group)
    
    if aggregated_data:
        return pd.concat(aggregated_data, ignore_index=True)
    else:
        return pd.DataFrame()


# Global filters (outside fragments to avoid duplication)
def get_portfolio_filters():
    """Get portfolio filters that are shared between fragments"""
    # Get available accounts
    try:
        accounts_list = client.accounts.list_accounts()
    except Exception as e:
        st.error(f"Failed to fetch accounts: {e}")
        return None, None, None
    
    if len(accounts_list) == 0:
        st.warning("No accounts found.")
        return None, None, None
    
    # Account selection
    selected_accounts = st.multiselect("Select Accounts", accounts_list, accounts_list, key="main_accounts")
    if len(selected_accounts) == 0:
        st.warning("Please select at least one account.")
        return None, None, None
    
    # Get portfolio state for available exchanges and tokens
    try:
        portfolio_state = client.portfolio.get_state(account_names=selected_accounts)
    except Exception as e:
        st.error(f"Failed to fetch portfolio state: {e}")
        return None, None, None
    
    # Extract available exchanges
    exchanges_available = []
    for account in selected_accounts:
        if account in portfolio_state:
            exchanges_available.extend(portfolio_state[account].keys())
    
    exchanges_available = list(set(exchanges_available))
    
    if len(exchanges_available) == 0:
        st.warning("No exchanges found for selected accounts.")
        return None, None, None
    
    selected_exchanges = st.multiselect("Select Exchanges", exchanges_available, exchanges_available, key="main_exchanges")
    
    # Extract available tokens
    tokens_available = []
    for account in selected_accounts:
        if account in portfolio_state:
            for exchange in selected_exchanges:
                if exchange in portfolio_state[account]:
                    tokens_available.extend([info["token"] for info in portfolio_state[account][exchange]])
    
    tokens_available = list(set(tokens_available))
    selected_tokens = st.multiselect("Select Tokens", tokens_available, tokens_available, key="main_tokens")
    
    return selected_accounts, selected_exchanges, selected_tokens


# Get filters once at the top level
st.header("Portfolio Filters")
selected_accounts, selected_exchanges, selected_tokens = get_portfolio_filters()

if not selected_accounts:
    st.stop()


@st.fragment
def portfolio_overview():
    """Fragment for portfolio overview and metrics"""
    st.markdown("---")
    
    # Get portfolio state and summary
    try:
        portfolio_state = client.portfolio.get_state(account_names=selected_accounts)
        portfolio_summary = client.portfolio.get_portfolio_summary()
    except Exception as e:
        st.error(f"Failed to fetch portfolio data: {e}")
        return
    
    # Filter portfolio state
    filtered_portfolio_state = {}
    for account in selected_accounts:
        if account in portfolio_state:
            filtered_portfolio_state[account] = {}
            for exchange in selected_exchanges:
                if exchange in portfolio_state[account]:
                    filtered_portfolio_state[account][exchange] = [
                        token_info for token_info in portfolio_state[account][exchange]
                        if token_info["token"] in selected_tokens
                    ]
    
    if len(filtered_portfolio_state) == 0:
        return
    
    # Convert to DataFrame
    portfolio_df = portfolio_state_to_df(filtered_portfolio_state)
    
    # Debug: Print DataFrame columns and first few rows
    st.write("Debug - DataFrame columns:", portfolio_df.columns.tolist())
    st.write("Debug - First few rows:", portfolio_df.head().to_dict('records'))
    
    # Safely calculate total balance
    try:
        if 'value' in portfolio_df.columns:
            total_balance_usd = round(portfolio_df["value"].sum(), 2)
        else:
            st.warning("Warning: 'value' column not found in portfolio data. Showing 0 balance.")
            st.warning(f"Available columns: {portfolio_df.columns.tolist()}")
            total_balance_usd = 0.0
    except Exception as e:
        st.error(f"Error calculating total balance: {e}. Available columns: {portfolio_df.columns.tolist()}")
        return
    
    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Balance (USD)", f"${total_balance_usd:,.2f}")
    
    with col2:
        st.metric("Accounts", len(selected_accounts))
    
    with col3:
        st.metric("Exchanges", len(selected_exchanges))
    
    with col4:
        st.metric("Tokens", len(selected_tokens))
    
    # Create visualizations
    c1, c2 = st.columns([1, 1])
    
    with c1:
        # Check if required columns exist
        required_columns = ['value', 'token', 'account', 'exchange']
        missing_columns = [col for col in required_columns if col not in portfolio_df.columns]
        
        if missing_columns:
            st.error(f"Missing required columns for visualization: {', '.join(missing_columns)}")
            st.warning(f"Available columns: {portfolio_df.columns.tolist()}")
        elif total_balance_usd <= 0:
            st.warning("Total balance is zero or negative. Cannot calculate allocations.")
        else:
            try:
                # Portfolio allocation visualization
                portfolio_df['% Allocation'] = (portfolio_df['value'] / total_balance_usd) * 100
                portfolio_df['label'] = portfolio_df['token'] + ' ($' + portfolio_df['value'].apply(
                    lambda x: f'{x:,.2f}') + ')'
                
                fig = px.sunburst(
                    portfolio_df,
                    path=['account', 'exchange', 'label'],
                    values='value',
                    hover_data={'% Allocation': ':.2f'},
                    title='Portfolio Allocation',
                    color='account',
                    color_discrete_sequence=px.colors.qualitative.Vivid
                )
                
                fig.update_traces(textinfo='label+percent entry')
                fig.update_layout(margin=dict(t=50, l=0, r=0, b=0), height=600)
                st.plotly_chart(fig, use_container_width=True)
                
            except Exception as e:
                st.error(f"Error creating portfolio visualization: {str(e)}")
                st.warning("Debug info - DataFrame sample:")
                st.write(portfolio_df.head().to_dict('records'))
    
    with c2:
        # Token distribution
        try:
            if 'token' not in portfolio_df.columns or 'value' not in portfolio_df.columns:
                st.warning("Cannot display token distribution: Missing required columns.")
                if 'token' not in portfolio_df.columns:
                    st.warning("- 'token' column is missing")
                if 'value' not in portfolio_df.columns:
                    st.warning("- 'value' column is missing")
            else:
                token_distribution = portfolio_df.groupby('token')['value'].sum().reset_index()
                token_distribution = token_distribution.sort_values('value', ascending=False)
                
                if not token_distribution.empty:
                    fig = px.bar(
                        token_distribution, 
                        x='token', 
                        y='value',
                        title='Token Distribution',
                        color='value',
                        color_continuous_scale='Blues',
                        labels={'value': 'Value (USD)', 'token': 'Token'}
                    )
                    fig.update_layout(
                        xaxis_title='Token',
                        yaxis_title='Value (USD)',
                        coloraxis_colorbar=dict(title='Value (USD)')
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("No token distribution data available.")
        except Exception as e:
            st.error(f"Error creating token distribution: {str(e)}")
            st.warning("Debug info - DataFrame columns:")
            st.write(portfolio_df.columns.tolist())
            if 'token' in portfolio_df.columns:
                st.warning("Sample token values:")
                st.write(portfolio_df['token'].head().tolist())
            if 'value' in portfolio_df.columns:
                st.warning("Sample value statistics:")
                st.write(portfolio_df['value'].describe().to_dict())
    
    # Portfolio details table
    st.subheader("Portfolio Details")
    
    # Define the columns we'd like to show, in order of preference
    desired_columns = [
        'account', 'exchange', 'token', 'units', 'available_units', 'price', 'value'
    ]
    
    # Filter to only include columns that exist in the DataFrame
    available_columns = [col for col in desired_columns if col in portfolio_df.columns]
    
    if not available_columns:
        st.warning("No valid columns available for the portfolio details table.")
        st.warning(f"Available columns: {portfolio_df.columns.tolist()}")
    else:
        # Show which columns are being displayed
        missing_columns = set(desired_columns) - set(available_columns)
        if missing_columns:
            st.warning(f"Note: Some columns are not available: {', '.join(sorted(missing_columns))}")
        
        # Display the table with available columns
        try:
            st.dataframe(
                portfolio_df[available_columns],
                use_container_width=True,
                column_config={
                    'value': st.column_config.NumberColumn('Value (USD)', format='$%.2f'),
                    'price': st.column_config.NumberColumn('Price', format='$%.8f'),
                    'units': st.column_config.NumberColumn('Units', format='%.8f'),
                    'available_units': st.column_config.NumberColumn('Available Units', format='%.8f')
                }
            )
        except Exception as e:
            st.error(f"Error displaying portfolio details: {str(e)}")
            st.warning("Debug info - DataFrame sample:")
            st.write(portfolio_df.head().to_dict('records'))


@st.fragment
def portfolio_history():
    """Fragment for portfolio history and charts"""
    st.markdown("---")
    st.subheader("Portfolio History")
    
    # Date range selection
    col1, col2, col3 = st.columns(3)
    with col1:
        days_back = st.selectbox("Time Period", [7, 30, 90, 180, 365], index=1, key="history_days")
    with col2:
        limit = st.number_input("Max Records", min_value=10, max_value=1000, value=100, key="history_limit")
    with col3:
        time_window = st.selectbox("Time Aggregation Window", [5, 10, 30, 60, 300], index=1, key="time_window", 
                                   help="Seconds to group nearby timestamps (fixes exchange timing differences)")
    
    # Get portfolio history
    try:
        from datetime import datetime, timezone, timedelta
        
        # Calculate start time for filtering
        start_time = datetime.now(timezone.utc) - timedelta(days=days_back)
        
        response = client.portfolio.get_history(
            selected_accounts,  # account_names
            None,              # connector_names
            limit,             # limit
            None,              # cursor
            int(start_time.timestamp()),  # start_time
            None               # end_time
        )
        
        # Extract data from response
        history_data = response.get("data", [])
        
    except Exception as e:
        st.error(f"Failed to fetch portfolio history: {e}")
        return
    
    if not history_data or len(history_data) == 0:
        st.warning("No historical data available.")
        return
    
    # Convert to DataFrame
    history_df = portfolio_history_to_df(history_data)
    history_df['timestamp'] = pd.to_datetime(history_df['timestamp'], format='ISO8601')
    
    # Filter by selected exchanges and tokens
    history_df = history_df[
        (history_df['exchange'].isin(selected_exchanges)) & 
        (history_df['token'].isin(selected_tokens))
    ]
    
    # Aggregate timestamps to solve the "electrocardiogram" issue
    history_df = aggregate_portfolio_history(history_df, time_window_seconds=time_window)
    
    if len(history_df) == 0:
        st.warning("No historical data available for selected filters.")
        return
    
    # Portfolio evolution by account (area chart)
    st.subheader("Portfolio Evolution by Account")
    account_evolution_df = history_df.groupby(['timestamp', 'account'])['value'].sum().reset_index()
    account_evolution_df = account_evolution_df.sort_values('timestamp')
    
    fig = px.area(account_evolution_df, x='timestamp', y='value', color='account', 
                  title='Portfolio Value Evolution by Account',
                  color_discrete_sequence=px.colors.qualitative.Set3)
    fig.update_layout(xaxis_title='Time', yaxis_title='Value (USD)', height=400)
    st.plotly_chart(fig, use_container_width=True)
    
    # Portfolio evolution by token (area chart)  
    st.subheader("Portfolio Evolution by Token")
    token_evolution_df = history_df.groupby(['timestamp', 'token'])['value'].sum().reset_index()
    token_evolution_df = token_evolution_df.sort_values('timestamp')
    
    # Show only top 10 tokens by average value to avoid clutter
    top_tokens = token_evolution_df.groupby('token')['value'].mean().sort_values(ascending=False).head(10).index
    token_evolution_filtered = token_evolution_df[token_evolution_df['token'].isin(top_tokens)]
    
    fig = px.area(token_evolution_filtered, x='timestamp', y='value', color='token', 
                  title='Portfolio Value Evolution by Token (Top 10)',
                  color_discrete_sequence=px.colors.qualitative.Vivid)
    fig.update_layout(xaxis_title='Time', yaxis_title='Value (USD)', height=400)
    st.plotly_chart(fig, use_container_width=True)
    
    # Portfolio evolution by exchange (area chart)
    st.subheader("Portfolio Evolution by Exchange")
    exchange_evolution_df = history_df.groupby(['timestamp', 'exchange'])['value'].sum().reset_index()
    exchange_evolution_df = exchange_evolution_df.sort_values('timestamp')
    
    fig = px.area(exchange_evolution_df, x='timestamp', y='value', color='exchange', 
                  title='Portfolio Value Evolution by Exchange',
                  color_discrete_sequence=px.colors.qualitative.Pastel)
    fig.update_layout(xaxis_title='Time', yaxis_title='Value (USD)', height=400)
    st.plotly_chart(fig, use_container_width=True)
    
    # Portfolio evolution table - total values
    st.subheader("Portfolio Total Value Over Time")
    total_evolution_df = history_df.groupby('timestamp')['value'].sum().reset_index()
    total_evolution_df = total_evolution_df.sort_values('timestamp')
    evolution_table = total_evolution_df.copy()
    evolution_table['timestamp'] = evolution_table['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
    evolution_table['value'] = evolution_table['value'].round(2)
    evolution_table = evolution_table.rename(columns={'timestamp': 'Time', 'value': 'Total Value (USD)'})
    st.dataframe(evolution_table, use_container_width=True)


# Main portfolio page
st.header("Portfolio Overview")
portfolio_overview()

st.header("Portfolio History")
portfolio_history()
