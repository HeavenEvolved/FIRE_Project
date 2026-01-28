import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, date, time, timedelta, timezone
import datetime as dt
import io
import os
import json
import requests
from zoneinfo import ZoneInfo

# 1. Page Config
st.set_page_config(page_title="Dual Portfolio Ledger", layout="wide")

st.title("🔬 High-Precision Dual Portfolio Ledger")
st.write("Fixed Allocation: **Jan 26, 2026** | Window Ends: **Apr 10, 2026**")

# Constants
tickers = ['SCHX', 'XLRE', 'XLF', 'QQQ', 'MSFT']
budget_per_ticker = 100000.0
total_budget = 500000.0
start_date = "2026-01-12"
end_date = "2026-04-10"
precision = 2

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
    stock_data = yf.download(ticker_list, start=start, end=end, auto_adjust=True)['Close'] # type: ignore
    opt_list = list(option_dict.values())
    opt_data = yf.download(opt_list, start=start, end=end, auto_adjust=True)['Close'] # type: ignore
    
    # --- DATA CLEANING PIPELINE ---
    # ffill for gaps after start, bfill for gaps on/before start
    stock_data = stock_data.ffill().bfill()
    opt_data = opt_data.ffill().bfill()
    
    return stock_data, opt_data

try:
    df, df_opt = get_data(tickers, options_symbols, start_date, fetch_end)

    if not df.empty and not df_opt.empty:
        # --- 1. STOCK PORTFOLIO CALCULATIONS ---
        initial_stock_prices = df.loc[start_date]
        shares_owned = (budget_per_ticker / initial_stock_prices).round(precision)

        s_total_val = (df * shares_owned).sum(axis=1).round(precision)
        s_total_val.iloc[0] = total_budget 
        s_daily_gl_dollars = s_total_val.diff().fillna(0.0).round(precision)
        s_daily_gl_pct = (s_total_val.pct_change().fillna(0.0) * 100).round(precision)
        
        # Stock Multi-Index Frame
        s_frames = {}
        for t in tickers:
            s_frames[(t, 'Price')] = df[t].round(precision)
            s_frames[(t, 'Shares')] = shares_owned[t]
        s_frames[('Portfolio Metrics', 'Total Value ($)')] = s_total_val
        s_frames[('Portfolio Metrics', 'Daily G/L ($)')] = s_daily_gl_dollars
        s_frames[('Portfolio Metrics', 'Daily G/L (%)')] = s_daily_gl_pct
        multi_df_stock = pd.DataFrame(s_frames)
        multi_df_stock.columns = pd.MultiIndex.from_tuples(multi_df_stock.columns) # type: ignore

        # --- 2. OPTIONS PORTFOLIO CALCULATIONS ---
        initial_opt_prices = df_opt.loc[start_date].replace(0, 0.01)
        contracts_owned = (budget_per_ticker / (initial_opt_prices * 100)).round(precision)

        o_total_val = (df_opt * contracts_owned * 100).sum(axis=1).round(precision)
        o_total_val.iloc[0] = total_budget
        o_daily_gl_dollars = o_total_val.diff().fillna(0.0).round(precision)
        o_daily_gl_pct = (o_total_val.pct_change().fillna(0.0) * 100).round(precision)

        # Options Multi-Index Frame
        o_frames = {}
        for stock, symbol in options_symbols.items():
            o_frames[(stock, 'Price')] = df_opt[symbol].round(precision)
            o_frames[(stock, 'Contracts')] = contracts_owned[symbol]
        o_frames[('Portfolio Metrics', 'Total Value ($)')] = o_total_val
        o_frames[('Portfolio Metrics', 'Daily G/L ($)')] = o_daily_gl_dollars
        o_frames[('Portfolio Metrics', 'Daily G/L (%)')] = o_daily_gl_pct
        multi_df_opt = pd.DataFrame(o_frames)
        multi_df_opt.columns = pd.MultiIndex.from_tuples(multi_df_opt.columns) # type: ignore

        # --- 3. UPDATED METRIC CARDS ---
        st.subheader(f"🏛️ Stock Portfolio Summary (${total_budget/1000:,.0f}k Basis)")
        s_curr = multi_df_stock['Portfolio Metrics'].iloc[-1]
        s_total_gl_val = s_curr['Total Value ($)'] - total_budget
        s_total_gl_pct = (s_total_gl_val / total_budget) * 100
        
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Stock Value", f"${s_curr['Total Value ($)']:,.{precision}f}", f"${s_curr['Daily G/L ($)']:,.{precision}f}")
        sc2.metric("Total P/L ($)", f"${s_total_gl_val:,.{precision}f}")
        sc3.metric("Total G/L (%)", f"{s_total_gl_pct:.{precision}f}%")
        sc4.metric("Daily Change (%)", f"{s_curr['Daily G/L (%)']:.{precision}f}%")

        st.divider()

        st.subheader(f"🎯 Options Portfolio Summary (${total_budget/1000:,.0f}k Basis)")
        o_curr = multi_df_opt['Portfolio Metrics'].iloc[-1]
        o_total_gl_val = o_curr['Total Value ($)'] - total_budget
        o_total_gl_pct = (o_total_gl_val / total_budget) * 100

        oc1, oc2, oc3, oc4 = st.columns(4)
        oc1.metric("Options Value", f"${o_curr['Total Value ($)']:,.{precision}f}", f"${o_curr['Daily G/L ($)']:,.{precision}f}")
        oc2.metric("Total P/L ($)", f"${o_total_gl_val:,.{precision}f}")
        oc3.metric("Total G/L (%)", f"{o_total_gl_pct:.{precision}f}%")
        oc4.metric("Daily Change (%)", f"{o_curr['Daily G/L (%)']:.{precision}f}%")

        st.divider()

        # --- 4. DATA TABLES ---
        tab1, tab2 = st.tabs(["Stock Ledger", "Options Ledger"])
        
        with tab1:
            st.dataframe(multi_df_stock.style.format(f"{{:.{precision}f}}"), width='stretch')
            # Stock CSV Export
            s_csv_df = multi_df_stock.copy()
            s_csv_df.columns = ['_'.join(col).strip() for col in s_csv_df.columns.values]
            s_csv = s_csv_df.to_csv().encode('utf-8')
            st.download_button(label="📩 Download Stock CSV", data=s_csv, file_name=f"stock_ledger_{today}.csv", mime="text/csv")
            
        with tab2:
            st.dataframe(multi_df_opt.style.format(f"{{:.{precision}f}}"), width='stretch')
            # Options CSV Export
            o_csv_df = multi_df_opt.copy()
            o_csv_df.columns = ['_'.join(col).strip() for col in o_csv_df.columns.values]
            o_csv = o_csv_df.to_csv().encode('utf-8')
            st.download_button(label="📩 Download Options CSV", data=o_csv, file_name=f"options_ledger_{today}.csv", mime="text/csv")
        
        with st.expander("Deep Dive Analysis", expanded=False):
            if 'multi_df_stock' in locals() and 'multi_df_opt' in locals():
                st.header("🔎 Deep Dive Analysis")

                st.subheader("Equity Curves (Stock vs Options)")
                stock_equity_curve = multi_df_stock["Portfolio Metrics"]["Total Value ($)"].rename("Stock Portfolio ($)")
                opt_equity_curve = multi_df_opt["Portfolio Metrics"]["Total Value ($)"].rename("Options Portfolio ($)")
                equity_curves = pd.concat([stock_equity_curve, opt_equity_curve], axis=1).dropna(how="all")
                st.line_chart(equity_curves)

                st.subheader("Daily Returns (Stock vs Options)")
                stock_returns_curve = multi_df_stock["Portfolio Metrics"]["Daily G/L ($)"].rename("Stock Portfolio ($)")
                opt_returns_curve = multi_df_opt["Portfolio Metrics"]["Daily G/L ($)"].rename("Options Portfolio ($)")
                returns_curves = pd.concat([stock_returns_curve, opt_returns_curve], axis=1).dropna(how="all")
                st.line_chart(returns_curves)
            else:
                st.warning("Data not available for deep dive analysis.")
except Exception as e:
    st.error(f"Error: {e}")