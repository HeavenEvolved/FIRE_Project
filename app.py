import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import date
import io

# 1. Page Config
st.set_page_config(page_title="Dual Portfolio Ledger", layout="wide")
st.title("🔬 High-Precision Dual Portfolio Ledger")
st.write("Fixed Allocation: **Jan 26, 2026** | Window Ends: **Apr 10, 2026**")

# Constants
tickers = ['SCHX', 'XLRE', 'XLF', 'QQQ', 'MSFT']
budget_per_ticker = 100000.0  # Used for both Stocks and Options
total_budget = 500000.0
start_date = "2026-01-12"
end_date = "2026-04-10"
precision = 2  # Change this value to adjust entire app precision

options_symbols = {
    'SCHX': "SCHX260515C00027000",
    'XLRE': "XLRE260515C00041000",
    'XLF': "XLF260515C00054000",
    'QQQ': "QQQ260515C00620000",
    'MSFT': "MSFT260515C00450000"
}

# Kill-switch logic
today = str(date.today())
fetch_end = min(today, end_date)

@st.cache_data(ttl=86400)
def get_data(ticker_list, option_dict, start, end):
    stock_data = yf.download(ticker_list, start=start, end=end, auto_adjust=True)['Close']
    opt_list = list(option_dict.values())
    opt_data = yf.download(opt_list, start=start, end=end, auto_adjust=True)['Close']
    opt_data = opt_data.ffill()
    opt_data = opt_data.bfill()
    return stock_data, opt_data

try:
    df, df_opt = get_data(tickers, options_symbols, start_date, fetch_end)

    if not df.empty and not df_opt.empty:
        # --- 1. STOCK PORTFOLIO CALCULATIONS ---
        initial_stock_prices = df.loc[start_date]
        shares_owned = (budget_per_ticker / initial_stock_prices).round(precision)

        s_frames = {}
        for t in tickers:
            s_frames[(t, 'Price')] = df[t].round(precision)
            s_frames[(t, 'Shares')] = shares_owned[t]

        s_total_val = (df * shares_owned).sum(axis=1).round(precision)
        s_total_val.iloc[0] = total_budget 
        s_daily_gl_dollars = s_total_val.diff().fillna(0.0).round(4)
        s_daily_gl_pct = (s_total_val.pct_change().fillna(0.0) * 100).round(precision)

        s_frames[('Portfolio Metrics', 'Total Value ($)')] = s_total_val
        s_frames[('Portfolio Metrics', 'Daily G/L ($)')] = s_daily_gl_dollars
        s_frames[('Portfolio Metrics', 'Daily G/L (%)')] = s_daily_gl_pct
        
        multi_df_stock = pd.DataFrame(s_frames)
        multi_df_stock.columns = pd.MultiIndex.from_tuples(multi_df_stock.columns)

        # --- 2. OPTIONS PORTFOLIO CALCULATIONS ---
        # Note: Options are traded in contracts of 100 shares. 
        # Price per contract = Option Price * 100
        initial_opt_prices = df_opt.loc[start_date]
        contracts_owned = (budget_per_ticker / (initial_opt_prices * 100)).round(precision)

        o_frames = {}
        for stock, symbol in options_symbols.items():
            o_frames[(stock, 'Price')] = df_opt[symbol].round(precision)
            o_frames[(stock, 'Contracts')] = contracts_owned[symbol]

        o_total_val = (df_opt * contracts_owned * 100).sum(axis=1).round(precision)
        o_total_val.iloc[0] = total_budget
        o_daily_gl_dollars = o_total_val.diff().fillna(0.0).round(4)
        o_daily_gl_pct = (o_total_val.pct_change().fillna(0.0) * 100).round(precision)

        o_frames[('Portfolio Metrics', 'Total Value ($)')] = o_total_val
        o_frames[('Portfolio Metrics', 'Daily G/L ($)')] = o_daily_gl_dollars
        o_frames[('Portfolio Metrics', 'Daily G/L (%)')] = o_daily_gl_pct

        multi_df_opt = pd.DataFrame(o_frames)
        multi_df_opt.columns = pd.MultiIndex.from_tuples(multi_df_opt.columns)

        # --- 3. DISPLAY METRIC CARDS ---
        st.subheader("🏛️ Stock Portfolio Summary ($500k Basis)")
        s_curr = multi_df_stock['Portfolio Metrics'].iloc[-1]
        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("Stock Value", f"${s_curr['Total Value ($)']:,.{precision}f}", f"${s_curr['Daily G/L ($)']:,.{precision}f}")
        sc2.metric("Stock Total P/L", f"${(s_curr['Total Value ($)'] - total_budget):,.{precision}f}")
        sc3.metric("Stock Daily %", f"{s_curr['Daily G/L (%)']:.{precision}f}%")

        st.divider()

        st.subheader("🎯 Options Portfolio Summary ($500k Basis)")
        o_curr = multi_df_opt['Portfolio Metrics'].iloc[-1]
        oc1, oc2, oc3 = st.columns(3)
        oc1.metric("Options Value", f"${o_curr['Total Value ($)']:,.{precision}f}", f"${o_curr['Daily G/L ($)']:,.{precision}f}")
        oc2.metric("Options Total P/L", f"${(o_curr['Total Value ($)'] - total_budget):,.{precision}f}")
        oc3.metric("Options Daily %", f"{o_curr['Daily G/L (%)']:.{precision}f}%")

        st.divider()

        # --- 4. DATA TABLES ---
        tab1, tab2 = st.tabs(["Stock Performance Ledger", "Options Performance Ledger"])
        
        with tab1:
            st.dataframe(multi_df_stock.style.format(f"{{:.{precision}f}}"), width='stretch')
        with tab2:
            st.dataframe(multi_df_opt.style.format(f"{{:.{precision}f}}"), width='stretch')

        # 5. CSV Export
        csv_data = multi_df_stock.to_csv().encode('utf-8')
        st.download_button(label="📩 Download Stock CSV", data=csv_data, file_name=f"stocks_{today}.csv")

    else:
        st.info(f"Awaiting start date: {start_date}")

except Exception as e:
    st.error(f"Error: {e}")