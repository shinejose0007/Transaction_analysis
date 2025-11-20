# transaction-analysis-demo/app/streamlit_app.py
import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
import os

st.set_page_config(page_title="Transaction Analysis Dashboard", layout="wide")
st.title("Transaction Analysis Dashboard – LTM & Valuation Multiples (with quarters & peers)")

# Paths
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(THIS_DIR, os.pardir))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)

col1, col2 = st.columns([2,1])

with col1:
    ticker = st.text_input("Enter Ticker (e.g., ADS.DE for Adidas)", "ADS.DE").strip()
with col2:
    peers_input = st.text_input("Peer tickers (comma-separated)", "BMW.DE,DVG.DE").strip()

if ticker:
    try:
        stock = yf.Ticker(ticker)
        # Quarterly and annual income
        q_income = getattr(stock, 'quarterly_financials', None)
        annual_income = getattr(stock, 'financials', None)
        balance = getattr(stock, 'balance_sheet', None)

        # Prepare DataFrames
        q_income_df = q_income.T if (q_income is not None and not q_income.empty) else pd.DataFrame()
        annual_income_df = annual_income.T if (annual_income is not None and not annual_income.empty) else pd.DataFrame()
        balance_df = balance.T if (balance is not None and not balance.empty) else pd.DataFrame()

        # Compute quarter-level breakdown (show last 4 quarters)
        st.subheader(f"Quarter-level breakdown for {ticker}")
        if not q_income_df.empty:
            # Try to find revenue/ebitda-like columns
            rev_col = None
            ebitda_col = None
            for c in q_income_df.columns:
                if 'Revenue' in c or 'Total' in c:
                    rev_col = c; break
            for c in q_income_df.columns:
                if 'Ebitda' in c or 'EBITDA' in c or 'Ebit' in c:
                    ebitda_col = c; break
            display_df = pd.DataFrame()
            if rev_col is not None:
                display_df['Revenue'] = q_income_df[rev_col].astype(float)
            if ebitda_col is not None:
                display_df['EBITDA'] = q_income_df[ebitda_col].astype(float)
            if not display_df.empty:
                # Show newest 4 quarters (yfinance returns newest first)
                st.dataframe(display_df.head(4))
                # Compute simple TTM
                try:
                    ttm_rev = display_df['Revenue'].head(4).sum() if 'Revenue' in display_df.columns else np.nan
                    ttm_ebitda = display_df['EBITDA'].head(4).sum() if 'EBITDA' in display_df.columns else np.nan
                    st.markdown(f"**TTM Revenue:** {ttm_rev:,.0f}" if not np.isnan(ttm_rev) else "**TTM Revenue:** N/A")
                    st.markdown(f"**TTM EBITDA:** {ttm_ebitda:,.0f}" if not np.isnan(ttm_ebitda) else "**TTM EBITDA:** N/A")
                except Exception:
                    st.info("Could not compute TTM from quarterly data for this ticker.")
            else:
                st.info("Quarterly revenue/EBITDA columns not found for this ticker.")
        else:
            st.info("No quarterly financials available via yfinance for this ticker; check the notebook fallback for annual values.")

        # Reuse some logic to compute EV/EBITDA for the main ticker
        def compute_ltm(df_quarters, annual_df, rev_label='Total Revenue'):
            ttm_rev = None; ttm_ebitda = None
            if not df_quarters.empty:
                cols = df_quarters.columns
                rev_cols = [c for c in cols if 'Revenue' in c or 'Total' in c]
                ebit_cols = [c for c in cols if 'Ebitda' in c or 'EBITDA' in c or 'Ebit' in c]
                if rev_cols:
                    ttm_rev = df_quarters[rev_cols[0]].head(4).dropna().astype(float).sum()
                if ebit_cols:
                    ttm_ebitda = df_quarters[ebit_cols[0]].head(4).dropna().astype(float).sum()
            if ttm_rev is None and not annual_df.empty:
                if rev_label in annual_df.columns:
                    try:
                        ttm_rev = float(annual_df[rev_label].iloc[0])
                    except Exception:
                        ttm_rev = None
            if ttm_ebitda is None and not annual_df.empty:
                if 'Ebitda' in annual_df.columns:
                    ttm_ebitda = float(annual_df['Ebitda'].iloc[0])
                else:
                    ebit = annual_df.get('Ebit', pd.Series([np.nan]*len(annual_df)))
                    dep = annual_df.get('Depreciation', pd.Series([0]*len(annual_df)))
                    ttm_ebitda = float((ebit.fillna(0) + dep.fillna(0)).iloc[0]) if len(ebit)>0 else None
            return ttm_rev, ttm_ebitda

        ttm_rev, ttm_ebitda = compute_ltm(q_income_df, annual_income_df)
        # Market cap and net debt
        history = stock.history(period='1d')
        last_price = float(history['Close'].iloc[-1]) if not history.empty else np.nan
        shares = stock.info.get('sharesOutstanding', np.nan)
        market_cap = last_price * shares if (not np.isnan(last_price) and not np.isnan(shares)) else np.nan
        total_debt = None; cash = None
        for col in ['Total Debt','Long Term Debt','Short Term Debt']:
            if col in balance_df.columns:
                try:
                    total_debt = float(balance_df[col].iloc[0]); break
                except Exception:
                    continue
        for col in ['Cash','Cash And Cash Equivalents']:
            if col in balance_df.columns:
                try: cash = float(balance_df[col].iloc[0]); break
                except Exception: continue
        net_debt = (total_debt - cash) if (total_debt is not None and cash is not None) else np.nan
        enterprise_value = market_cap + net_debt if (not np.isnan(market_cap) and not np.isnan(net_debt)) else np.nan
        ev_ebitda = enterprise_value / ttm_ebitda if (ttm_ebitda and not np.isnan(enterprise_value)) else np.nan

        st.subheader('Valuation summary')
        st.write(f"Market Cap: {market_cap:,.0f}" if not np.isnan(market_cap) else "Market Cap: N/A")
        st.write(f"Net Debt: {net_debt:,.0f}" if not np.isnan(net_debt) else "Net Debt: N/A")
        st.write(f"Enterprise Value: {enterprise_value:,.0f}" if not np.isnan(enterprise_value) else "Enterprise Value: N/A")
        st.write(f"EV/TTM EBITDA: {ev_ebitda:.2f}x" if not np.isnan(ev_ebitda) else "EV/TTM EBITDA: N/A")

        # Peer-comps panel
        st.subheader('Peer comps (EV/EBITDA)')
        peer_list = [p.strip() for p in peers_input.split(',') if p.strip()]
        peer_rows = []
        for p in peer_list:
            try:
                peer_stock = yf.Ticker(p)
                peer_q = getattr(peer_stock, 'quarterly_financials', None)
                peer_annual = getattr(peer_stock, 'financials', None)
                peer_q_df = peer_q.T if (peer_q is not None and not peer_q.empty) else pd.DataFrame()
                peer_ann_df = peer_annual.T if (peer_annual is not None and not peer_annual.empty) else pd.DataFrame()
                p_rev, p_ebitda = compute_ltm(peer_q_df, peer_ann_df)
                peer_hist = peer_stock.history(period='1d')
                p_price = float(peer_hist['Close'].iloc[-1]) if not peer_hist.empty else np.nan
                p_shares = peer_stock.info.get('sharesOutstanding', np.nan)
                p_mcap = p_price * p_shares if (not np.isnan(p_price) and not np.isnan(p_shares)) else np.nan
                bdf = getattr(peer_stock, 'balance_sheet', None)
                bdf = bdf.T if (bdf is not None and not bdf.empty) else pd.DataFrame()
                p_total_debt = None; p_cash = None
                for col in ['Total Debt','Long Term Debt','Short Term Debt']:
                    if col in bdf.columns:
                        try: p_total_debt = float(bdf[col].iloc[0]); break
                        except Exception: continue
                for col in ['Cash','Cash And Cash Equivalents']:
                    if col in bdf.columns:
                        try: p_cash = float(bdf[col].iloc[0]); break
                        except Exception: continue
                p_net_debt = (p_total_debt - p_cash) if (p_total_debt is not None and p_cash is not None) else np.nan
                p_ev = p_mcap + p_net_debt if (not np.isnan(p_mcap) and not np.isnan(p_net_debt)) else np.nan
                p_ev_ebitda = p_ev / p_ebitda if (p_ebitda and not np.isnan(p_ev)) else np.nan
                peer_rows.append({'Ticker': p, 'EV/EBITDA': round(p_ev_ebitda,2) if not np.isnan(p_ev_ebitda) else None})
            except Exception as e:
                peer_rows.append({'Ticker': p, 'EV/EBITDA': None})

        peers_df = pd.DataFrame(peer_rows)
        if not peers_df.empty:
            st.dataframe(peers_df)
            # small chart
            chart_df = peers_df.set_index('Ticker')['EV/EBITDA']
            st.bar_chart(chart_df)
        else:
            st.info('No peer data available or peers not provided.')

        # Save to CSV
        df_out = pd.DataFrame({
            'Metric': ['TTM Revenue','TTM EBITDA','Enterprise Value','EV/EBITDA'],
            'Value': [ttm_rev, ttm_ebitda, enterprise_value, ev_ebitda]
        })
        save_path = os.path.join(DATA_DIR, 'financials_raw.csv')
        try:
            df_out.to_csv(save_path, index=False)
            st.caption(f'Saved metrics to {save_path}')
        except Exception as e:
            st.warning(f'Could not save CSV: {e}')

    except Exception as e:
        st.error(f'Error fetching data for ticker {ticker}: {e}')
else:
    st.info('Enter a ticker to start (e.g., ADS.DE)')
