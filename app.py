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
import matplotlib.pyplot as plt
import numpy as np

# 1. Page Config
st.set_page_config(page_title="Dual Portfolio Ledger", layout="wide")

st.title("🔬 High-Precision Dual Portfolio Ledger")
st.write("Fixed Allocation: **Jan 26, 2026** | Window Ends: **Apr 10, 2026**")

# Constants
tickers = ['SCHX', 'XLRE', 'XLF', 'QQQ', 'MSFT']
budget_per_ticker = 100000.0
total_budget = 500000.0
start_date = "2026-01-26"
end_date = "2026-04-10"
precision = 2

options_symbols = {
    'SCHX': "SCHX260515C00027000",
    'XLRE': "XLRE260515C00041000",
    'XLF': "XLF260515C00053000",
    'QQQ': "QQQ260515C00625000",
    'MSFT': "MSFT260515C00470000"
}

# Kill-switch logic
today = str(date.today())
fetch_end = (pd.to_datetime(min(today, end_date)) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

def get_color_for_change(change_pct, cmap_name='RdGy_r', vmin=-5, vmax=5):
    """Get RGB color string for a given percentage change."""
    cmap = plt.get_cmap(cmap_name)
    # Normalize the change percentage to [0, 1]
    normalized = np.clip((change_pct - vmin) / (vmax - vmin), 0, 1)
    rgba = cmap(normalized)
    return f'rgba({int(rgba[0]*255)}, {int(rgba[1]*255)}, {int(rgba[2]*255)}, {rgba[3]})'

@st.cache_data(ttl=86400)
def get_data(ticker_list, option_dict, start, end, opt_lookback_days=90):
    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end)

    # Stocks: only need your analysis window
    stock_data = yf.download( # type: ignore
        ticker_list,
        start=start_dt.strftime("%Y-%m-%d"),
        end=end_dt.strftime("%Y-%m-%d"),
        auto_adjust=True
    )["Close"]

    # Options: pull a longer window so we can find last traded close before start
    opt_list = list(option_dict.values())
    opt_start_dt = start_dt - pd.Timedelta(days=opt_lookback_days)

    opt_data = yf.download( # type: ignore
        opt_list,
        start=opt_start_dt.strftime("%Y-%m-%d"),
        end=end_dt.strftime("%Y-%m-%d"),
        auto_adjust=True
    )["Close"]

    # Normalize to DataFrame even if one column comes back as Series
    if isinstance(stock_data, pd.Series):
        stock_data = stock_data.to_frame()
    if isinstance(opt_data, pd.Series):
        opt_data = opt_data.to_frame()

    # ---- Cleaning ----

    # Options: IMPORTANT — use forward-fill only (stale last trade)
    # This will carry the last traded close forward in time.
    opt_data = opt_data.ffill()

    # Detect options that never traded in the entire pulled window
    never_traded = opt_data.columns[opt_data.isna().all()]
    if len(never_traded) > 0:
        # Choose what you want here: 0.0 is a practical fallback
        opt_data[never_traded] = 0.0

    # Trim options back to your analysis window after we’ve established last trade prices
    opt_data = opt_data.loc[start_dt.strftime("%Y-%m-%d"):]

    return stock_data, opt_data

try:
    df, df_opt = get_data(tickers, options_symbols, start_date, fetch_end, opt_lookback_days=90)

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
        # Calculate daily change for each stock position
        s_daily_change_pct_by_stock = {}
        s_total_change_pct_by_stock = {}
        for t in tickers:
            stock_position_val = (df[t] * shares_owned[t]).round(precision)
            s_daily_change_pct_by_stock[t] = (stock_position_val.pct_change().fillna(0.0) * 100).round(precision)
            # Calculate total change % from start to end
            total_change_pct = ((stock_position_val.iloc[-1] - budget_per_ticker) / budget_per_ticker * 100)
            s_total_change_pct_by_stock[t] = total_change_pct
        
        for t in tickers:
            ticker_label = f"{t} ({s_total_change_pct_by_stock[t]:+.{precision}f}%)"
            s_frames[(ticker_label, 'Price')] = df[t].round(precision)
            s_frames[(ticker_label, 'Shares')] = shares_owned[t]
            s_frames[(ticker_label, 'Chg %')] = s_daily_change_pct_by_stock[t]
        s_frames[('Portfolio Metrics', 'Total Value ($)')] = s_total_val
        s_frames[('Portfolio Metrics', 'Daily G/L ($)')] = s_daily_gl_dollars
        s_frames[('Portfolio Metrics', 'Daily G/L (%)')] = s_daily_gl_pct
        multi_df_stock = pd.DataFrame(s_frames)
        multi_df_stock.columns = pd.MultiIndex.from_tuples(multi_df_stock.columns) # type: ignore
        multi_df_stock.index = multi_df_stock.index.strftime('%Y-%m-%d') # type: ignore

        # --- 2. OPTIONS PORTFOLIO CALCULATIONS ---
        initial_opt_prices = df_opt.loc[start_date].replace(0, 0.01)
        contracts_owned = (budget_per_ticker / (initial_opt_prices * 100)).round(precision)

        o_total_val = (df_opt * contracts_owned * 100).sum(axis=1).round(precision)
        o_total_val.iloc[0] = total_budget
        o_daily_gl_dollars = o_total_val.diff().fillna(0.0).round(precision)
        o_daily_gl_pct = (o_total_val.pct_change().fillna(0.0) * 100).round(precision)

        # Options Multi-Index Frame
        o_frames = {}
        # Calculate daily change for each options position
        o_daily_change_pct_by_stock = {}
        o_total_change_pct_by_stock = {}
        for stock, symbol in options_symbols.items():
            option_position_val = (df_opt[symbol] * contracts_owned[symbol] * 100).round(precision)
            o_daily_change_pct_by_stock[stock] = (option_position_val.pct_change().fillna(0.0) * 100).round(precision)
            # Calculate total change % from start to end
            total_change_pct = ((option_position_val.iloc[-1] - budget_per_ticker) / budget_per_ticker * 100)
            o_total_change_pct_by_stock[stock] = total_change_pct
        
        for stock, symbol in options_symbols.items():
            stock_label = f"{stock} ({o_total_change_pct_by_stock[stock]:+.{precision}f}%)"
            o_frames[(stock_label, 'Price')] = df_opt[symbol].round(precision)
            o_frames[(stock_label, 'Contracts')] = contracts_owned[symbol]
            o_frames[(stock_label, 'Chg %')] = o_daily_change_pct_by_stock[stock]
        o_frames[('Portfolio Metrics', 'Total Value ($)')] = o_total_val
        o_frames[('Portfolio Metrics', 'Daily G/L ($)')] = o_daily_gl_dollars
        o_frames[('Portfolio Metrics', 'Daily G/L (%)')] = o_daily_gl_pct
        multi_df_opt = pd.DataFrame(o_frames)
        multi_df_opt.columns = pd.MultiIndex.from_tuples(multi_df_opt.columns) # type: ignore
        multi_df_opt.index = multi_df_opt.index.strftime('%Y-%m-%d') # type: ignore

        # --- 3. UPDATED METRIC CARDS ---
        st.subheader(f"🏛️ Stock Portfolio Summary (${total_budget/1000:,.0f}k Basis)")
        s_curr = multi_df_stock['Portfolio Metrics'].iloc[-1]
        s_total_gl_val = s_curr['Total Value ($)'] - total_budget
        s_total_gl_pct = (s_total_gl_val / total_budget) * 100
        
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Stock Value", f"${s_curr['Total Value ($)']:,.{precision}f}", f"{s_curr['Daily G/L ($)']:,.{precision}f}")
        sc2.metric("Total P/L ($)", f"${s_total_gl_val:,.{precision}f}")
        sc3.metric("Total G/L (%)", f"{s_total_gl_pct:.{precision}f}%")
        sc4.metric("Daily Change (%)", f"{s_curr['Daily G/L (%)']:.{precision}f}%")

        st.divider()

        st.subheader(f"🎯 Options Portfolio Summary (${total_budget/1000:,.0f}k Basis)")
        o_curr = multi_df_opt['Portfolio Metrics'].iloc[-1]
        o_total_gl_val = o_curr['Total Value ($)'] - total_budget
        o_total_gl_pct = (o_total_gl_val / total_budget) * 100

        oc1, oc2, oc3, oc4 = st.columns(4)
        oc1.metric("Options Value", f"${o_curr['Total Value ($)']:,.{precision}f}", f"{o_curr['Daily G/L ($)']:,.{precision}f}")
        oc2.metric("Total P/L ($)", f"${o_total_gl_val:,.{precision}f}")
        oc3.metric("Total G/L (%)", f"{o_total_gl_pct:.{precision}f}%")
        oc4.metric("Daily Change (%)", f"{o_curr['Daily G/L (%)']:.{precision}f}%")

        st.divider()

        # --- 4. DATA TABLES ---
        tab1, tab2 = st.tabs(["Stock Ledger", "Options Ledger"])
        
        with tab1:
            # Style: format numbers and apply color gradient
            styled_stock = multi_df_stock.style.format(f"{{:.{precision}f}}")
            # Apply background color gradient specifically to Chg % columns
            for stock in tickers:
                stock_label = f"{stock} ({s_total_change_pct_by_stock[stock]:+.{precision}f}%)"
                styled_stock = styled_stock.background_gradient(
                    subset=pd.IndexSlice[:, (stock_label, 'Chg %')], # type: ignore
                    cmap='RdGy_r',
                    vmin=-5,
                    vmax=5
                )
            st.dataframe(styled_stock, width='stretch')
            # Stock CSV Export
            s_csv_df = multi_df_stock.copy()
            s_csv_df.columns = ['_'.join(col).strip() for col in s_csv_df.columns.values]
            s_csv = s_csv_df.to_csv().encode('utf-8')
            st.download_button(label="📩 Download Stock CSV", data=s_csv, file_name=f"stock_ledger_{today}.csv", mime="text/csv")
            
        with tab2:
            # Style: format numbers and apply color gradient
            styled_opt = multi_df_opt.style.format(f"{{:.{precision}f}}")
            # Apply background color gradient specifically to Chg % columns
            for stock in options_symbols.keys():
                stock_label = f"{stock} ({o_total_change_pct_by_stock[stock]:+.{precision}f}%)"
                styled_opt = styled_opt.background_gradient(
                    subset=pd.IndexSlice[:, (stock_label, 'Chg %')], # type: ignore
                    cmap='RdGy_r',
                    vmin=-5,
                    vmax=5
                )
            st.dataframe(styled_opt, width='stretch')
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