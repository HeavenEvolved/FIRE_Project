import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import date
import io

# 1. Page Config
st.set_page_config(page_title="High-Precision Portfolio Ledger", layout="wide")
st.title("🔬 High-Precision Daily Performance Ledger")
st.write("Fixed Shares Bought: **Jan 26, 2026** | Window Ends: **Apr 10, 2026**")

# Constants
tickers = ['SPY', 'SCHX', 'XLF', 'VUG', 'QQQ']
budget_per_ticker = 100000.0
total_budget = 500000.0
start_date = "2026-01-26"
end_date = "2026-04-10"
precision = 2

# Kill-switch logic
today = str(date.today())
fetch_end = min(today, end_date)

@st.cache_data(ttl=86400)
def get_data(ticker_list, start, end):
    # Fetching adjusted close data
    data = yf.download(ticker_list, start=start, end=end, auto_adjust=True)['Close'] # type: ignore
    return data

try:
    df = get_data(tickers, start_date, fetch_end)

    if not df.empty:
        # Lock Shares on Jan 26 - Rounded to 4 decimals
        initial_prices = df.loc[start_date]
        shares_owned = (budget_per_ticker / initial_prices).round(precision)

        # 2. Build Multi-Level DataFrame
        frames = {}
        for t in tickers:
            frames[(t, 'Adj Close')] = df[t].round(precision)
            frames[(t, 'Shares')] = shares_owned[t]

        # Calculate Total Daily Values
        total_val = (df * shares_owned).sum(axis=1).round(precision)
        
        # --- DAILY G/L LOGIC (4 Decimal Precision) ---
        daily_gl_dollars = total_val.diff().fillna(0.0).round(4)
        daily_gl_pct = (total_val.pct_change().fillna(0.0) * 100).round(precision)

        frames[('Portfolio Metrics', 'Total Value ($)')] = total_val
        frames[('Portfolio Metrics', 'Daily G/L ($)')] = daily_gl_dollars
        frames[('Portfolio Metrics', 'Daily G/L (%)')] = daily_gl_pct

        multi_df = pd.DataFrame(frames)
        multi_df.columns = pd.MultiIndex.from_tuples(multi_df.columns) # type: ignore

        # 3. Metric Cards (Displaying 4 decimals where applicable)
        current = multi_df['Portfolio Metrics'].iloc[-1]
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Current Portfolio Value", f"${current['Total Value ($)']:,.{precision}f}", 
                   f"${current['Daily G/L ($)']:,.{precision}f} today")
        
        total_profit = (current['Total Value ($)'] - total_budget)
        col2.metric("Total Profit/Loss", f"${total_profit:,.{precision}f}")
        
        col3.metric("Today's Change (%)", f"{current['Daily G/L (%)']:.{precision}f}%")

        st.divider()

        # 4. Display the Ledger Table
        st.subheader("Daily Tracking Ledger (Precise)")
        
        # Using format to force 4 decimal places in the Streamlit view
        st.dataframe(multi_df.style.format(f"{{:.{precision}f}}"), width='stretch')

        # 5. CSV Export (Maintains 4 decimal precision)
        csv_df = multi_df.copy()
        csv_df.columns = ['_'.join(col).strip() for col in csv_df.columns.values]
        csv = csv_df.to_csv().encode('utf-8')
        
        st.download_button(
            label="📩 Download Precise CSV",
            data=csv,
            file_name=f"portfolio_precise_pnl_{today}.csv",
            mime="text/csv"
        )

    else:
        st.info(f"The tracking window starts on {start_date}.")

except Exception as e:
    st.error(f"Error: {e}")