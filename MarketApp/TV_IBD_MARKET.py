import streamlit as st
import pandas as pd
import numpy as np
import os
import glob
import io
from datetime import datetime
import yfinance as yf
from streamlit_lightweight_charts import renderLightweightCharts
from tradingview_screener import Query, Column

# ==========================================
# 📁 הגדרות נתיבים
# ==========================================
DATA_DIR = "data"

# הגדרת הפונקציה בראש הקוד כדי שתהיה זמינה לכולם
def find_file_robust(directory, filename_target):
    if not os.path.exists(directory):
        return None
    try:
        files = os.listdir(directory)
        target = filename_target.lower().strip()
        for f in files:
            if f.lower().strip() == target:
                return os.path.join(directory, f)
    except:
        pass
    return None

# ==========================================
# ⚙️ הגדרות עמוד ותצורה
# ==========================================
st.set_page_config(
    page_title="Terminal :: Hybrid Market",
    page_icon="📟",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
    .stApp { background-color: #0E1117; }
    .block-container { padding-top: 1.5rem; padding-bottom: 1.5rem; direction: rtl; max-width: 95%; }
    h1, h2, h3 { color: #E6EDF3; font-family: 'Consolas', 'Courier New', monospace; text-transform: uppercase; letter-spacing: 1px; }
    h1 { border-bottom: 2px solid #238636; padding-bottom: 10px; }
    .stDataFrame { direction: ltr; }
    div[data-baseweb="input"] { background-color: #161B22; border: 1px solid #30363D; border-radius: 4px; }
    div[data-baseweb="select"] > div { background-color: #161B22; border: 1px solid #30363D; }
    div[data-testid="stMetricValue"] { color: #2EA043; font-weight: bold; }
    .counter-badge { color: #2EA043; font-weight: bold; font-size: 0.9em; }
    .stDownloadButton > button { background-color: #238636; color: white; border: none; width: 100%; }
    .stDownloadButton > button:hover { background-color: #2EA043; border: none; }
    .refresh-btn > button { background-color: #1F6FEB; color: white; border: 1px solid #388BFD; font-weight: bold; }
    .refresh-btn > button:hover { background-color: #388BFD; border-color: #58A6FF; }
    .diagnostic-box { background-color: #30363D; padding: 15px; border-radius: 5px; margin-bottom: 20px; border-left: 5px solid #D2A8FF;}
    .log-text { color: #8B949E; font-family: monospace; font-size: 0.85em; margin-top: 10px;}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 📡 טעינת נתונים חסינת-תקלות
# ==========================================
@st.cache_data(ttl=1800, show_spinner=False)
def load_hybrid_data():
    debug_log = []
    try:
        # --- 1. משיכת נתונים חיים מ-TV ---
        debug_log.append("📡 מתחיל משיכת נתונים מ-TradingView...")
        query = (Query()
                 .set_markets('america')
                 .select('name', 'close', 'open', 'high', 'low', 'volume', 'average_volume_10d_calc', 
                         'market_cap_basic', 'sector', 'industry', 
                         'SMA10', 'SMA20', 'SMA50', 'SMA200', 'price_52_week_high', 'price_52_week_low',
                         'Perf.W', 'Perf.1M', 'Perf.3M', 'Perf.Y', 'ATR')
                 .where(Column('close') > 1, Column('average_volume_10d_calc') > 100000)
                 .limit(4500)) 
        
        count, df_tv = query.get_scanner_data()
        if df_tv.empty: 
            return pd.DataFrame(), pd.DataFrame(), ["❌ שגיאה: לא התקבלו נתונים מ-TV"]

        rename_map = {'ticker': 'Symbol', 'name': 'Company_Name', 'close': 'Price', 'volume': 'TV_Volume', 'average_volume_10d_calc': 'TV_AvgVol10', 'market_cap_basic': 'Market Cap', 'industry': 'Industry Group Name'}
        df_raw = df_tv.rename(columns=rename_map).copy()
        df_raw['Symbol'] = df_raw['Symbol'].apply(lambda x: x.split(':')[-1] if isinstance(x, str) and ':' in x else x)
        df_raw['TV_Link'] = "https://www.tradingview.com/chart/?symbol=" + df_raw['Symbol']
        df_raw['Market_Cap_B'] = pd.to_numeric(df_raw['Market Cap'], errors='coerce') / 1_000_000_000.0
        df_raw['Dollar_Volume_M'] = (df_raw['Price'] * df_raw['TV_AvgVol10']) / 1_000_000.0

        # --- 2. מנוע תבניות חי ---
        df_raw['Rel_Volume'] = df_raw['TV_Volume'] / df_raw['TV_AvgVol10']
        df_raw['Spread'] = df_raw['high'] - df_raw['low']
        df_raw['Close_Pos'] = np.where(df_raw['Spread'] > 0, (df_raw['Price'] - df_raw['low']) / df_raw['Spread'], 0.5)
        df_raw['ADR_Pct'] = np.where(df_raw['low'] > 0, (df_raw['ATR'] / df_raw['low']) * 100, 0)

        def get_patterns(row):
            b = []
            p, op, hi, lo = row.get('Price', 0), row.get('open', 0), row.get('high', 0), row.get('low', 0)
            rvol, atr, adr = row.get('Rel_Volume', 1), row.get('ATR', 0), row.get('ADR_Pct', 0)
            sma10, sma20, sma50, sma200 = row.get('SMA10', 0), row.get('SMA20', 0), row.get('SMA50', 0), row.get('SMA200', 0)
            cp = row.get('Close_Pos', 0.5)
            perf3 = (row.get('Perf.3M', 0) / 100) if not pd.isna(row.get('Perf.3M')) else 0
            h52 = row.get('price_52_week_high', 0)
            h52p = (p-h52)/h52 if h52 > 0 else -1

            if p <= 0: return ""
            if sma50 > 0 and lo < sma50 < p: b.append("U&R(50) 🛡️")
            if sma20 > 0 and lo < sma20 < p: b.append("U&R(21) 🛡️")
            if sma50 > 0 and (0.0 <= (p-sma50)/sma50 <= 0.03) and p > sma200: b.append("Bounce50 🏀")
            if rvol > 1.5 and p > op and cp > 0.7: b.append("HVC 🚀")
            if rvol > 1.2 and adr > 0 and ((hi-lo)/lo*100) > adr and cp < 0.4: b.append("SQUAT 🏋️")
            if perf3 > 0.9 and h52p >= -0.2: b.append("HTF 🚩")
            if h52p >= -0.02: b.append("52W High 👑")
            return "  ".join(b)

        df_raw['Pattern_Badges'] = df_raw.apply(get_patterns, axis=1)

        # --- 3. Weinstein ---
        p, ma50, ma200 = df_raw['Price'], df_raw['SMA50'], df_raw['SMA200']
        h52, l52 = df_raw['price_52_week_high'], df_raw['price_52_week_low']
        df_raw['52W_High_Pct'] = np.where(h52 > 0, (p - h52) / h52, -1)
        df_raw['52W_Low_Pct'] = np.where(l52 > 0, (p - l52) / l52, 0)
        
        c2 = (p > ma50) & (ma50 > ma200) & (df_raw['52W_Low_Pct'] >= 0.25) & (df_raw['52W_High_Pct'] >= -0.25)
        c4 = (p < ma50) & (ma50 < ma200)
        df_raw['Weinstein_Stage'] = np.select([c2, c4], ['Stage 2 🚀 Adv', 'Stage 4 📉 Dec'], default='N/A')

        # --- 4. IBD & Groups ---
        df_ibd = pd.DataFrame()
        ibd_p = find_file_robust(DATA_DIR, "IBD.csv")
        if ibd_p:
            try:
                try: df_ibd = pd.read_csv(ibd_p, encoding='utf-8-sig')
                except: df_ibd = pd.read_csv(ibd_p, encoding='cp1252')
                df_ibd.columns = df_ibd.columns.str.strip()
                for c in ['RS Rating', 'Comp. Rating', 'EPS Rating', 'Industry Group Rank']:
                    if c in df_ibd.columns: df_ibd[c] = pd.to_numeric(df_ibd[c].astype(str).str.replace('%','').str.replace(',',''), errors='coerce')
                debug_log.append(f"✅ IBD נטען")
            except Exception as e: debug_log.append(f"❌ שגיאת IBD: {e}")

        group_p = find_file_robust(DATA_DIR, "Group Ranking.csv")
        group_df = pd.DataFrame()
        if group_p:
            try:
                try: gdf = pd.read_csv(group_p, encoding='utf-8-sig')
                except: gdf = pd.read_csv(group_p, encoding='cp1252')
                gdf.columns = gdf.columns.str.strip()
                rd = {}
                for c in gdf.columns:
                    cl = c.lower()
                    if 'this wk' in cl or cl == 'rank': rd[c] = 'Rank this Wk'
                    elif '3 wks' in cl: rd[c] = '3 Wks ago'
                    elif 'industry' in cl or 'name' in cl: rd[c] = 'Industry Group Name'
                group_df = gdf.rename(columns=rd)
                if 'Rank this Wk' in group_df.columns and '3 Wks ago' in group_df.columns:
                    group_df['Rank this Wk'] = pd.to_numeric(group_df['Rank this Wk'], errors='coerce')
                    group_df['3 Wks ago'] = pd.to_numeric(group_df['3 Wks ago'], errors='coerce')
                    group_df['Rank_Improvement'] = group_df['3 Wks ago'] - group_df['Rank this Wk']
                debug_log.append(f"✅ Group Ranking נטען")
            except Exception as e: debug_log.append(f"❌ שגיאת Group: {e}")

        if not df_ibd.empty and not group_df.empty:
            df_ibd = pd.merge(df_ibd, group_df[['Rank this Wk', 'Rank_Improvement', 'Industry Group Name']], left_on='Industry Group Rank', right_on='Rank this Wk', how='left')

        if not df_ibd.empty:
            if 'Industry Group Name' in df_raw.columns and 'Industry Group Name' in df_ibd.columns: df_raw = df_raw.drop(columns=['Industry Group Name'])
            icols = ['Symbol', 'RS Rating', 'Comp. Rating', 'EPS Rating', 'Acc/Dis Rating', 'SMR Rating', 'Spon Rating', 'Ind Grp RS', 'Industry Group Rank', 'Rank_Improvement', 'Industry Group Name']
            df_raw = pd.merge(df_raw, df_ibd[[c for c in icols if c in df_ibd.columns]], on='Symbol', how='left')
        
        if 'Perf.Y' in df_raw.columns:
            df_raw['RS Rating'] = df_raw['RS Rating'].fillna(df_raw['Perf.Y'].rank(pct=True)*99).astype(int)

        # --- 5. Excel ---
        ex_p = glob.glob(os.path.join(DATA_DIR, "Ultimate_Market_V3f_*.xlsx"))
        if ex_p:
            try:
                edfx = pd.read_excel(max(ex_p, key=os.path.getmtime), sheet_name='Full Raw Data')
                df_raw = pd.merge(df_raw, edfx[['Symbol', 'Earnings_Alert', 'Kinetic_Slope', 'VDU_Alert']], on='Symbol', how='left')
            except: pass
        
        for c in ['Earnings_Alert', 'Kinetic_Slope', 'VDU_Alert']:
            if c not in df_raw.columns: df_raw[c] = ''

        debug_log.append("✅ מיזוג הושלם")
        return df_raw, group_df, debug_log
    except Exception as e:
        return pd.DataFrame(), pd.DataFrame(), [f"❌ שגיאה כללית: {e}"]

# ==========================================
# UI Logic
# ==========================================
st.title("📟 HYBRID COMMAND CENTER :: TV + IBD")

with st.sidebar:
    if st.button("📡 רענן נתונים כעת"):
        load_hybrid_data.clear()
        st.rerun()

df_raw, group_df, debug_log = load_hybrid_data()

# פאנל אבחון
with st.expander("🔍 מצב אבחון קבצים (X-Ray)"):
    if os.path.exists(DATA_DIR):
        st.write(f"קבצים בתיקייה: {os.listdir(DATA_DIR)}")
    for log in debug_log: st.write(log)

if df_raw.empty:
    st.error("⚠️ לא ניתן היה לטעון נתונים. בדוק את האבחון.")
    st.stop()

# פילטרים
st.markdown("### ⚙️ CORE PARAMETERS")
c1, c2, c3, c4 = st.columns(4)
with c1: min_rs = st.number_input("⚡ RS Rating", 1, 99, 85)
with c2: min_v = st.number_input("💵 $ Vol (M)", 0.0, 500.0, 5.0)
with c3: req_lc = st.toggle("> $1B Cap", False)
with c4:
    stgs = [s for s in df_raw['Weinstein_Stage'].unique() if s != '']
    stg_f = st.multiselect("📊 Stage", stgs, default=["Stage 2 🚀 Adv"] if "Stage 2 🚀 Adv" in stgs else None)

mask = (df_raw['RS Rating'] >= min_rs) & (df_raw['Dollar_Volume_M'] >= min_v)
if req_lc: mask &= (df_raw['Market_Cap_B'] >= 1.0)
df_filtered = df_raw[mask].copy()
if stg_f: df_filtered = df_filtered[df_filtered['Weinstein_Stage'].isin(stg_f)]

# Action Score
df_filtered['Action_Score'] = (df_filtered['RS Rating'] / 10) + (pd.to_numeric(df_filtered.get('Kinetic_Slope', 0), errors='coerce').fillna(0) / 50).clip(upper=3)

# טבלה
st.markdown(f"### 🎯 ACTION GRID ({len(df_filtered)} STOCKS)")
v_cols = ['TV_Link', 'Price', 'RS Rating', 'Action_Score', 'Comp. Rating', 'EPS Rating', 'Acc/Dis Rating', 'Ind Grp RS', 'Weinstein_Stage', 'Pattern_Badges', 'Rank_Improvement']
show_cols = [c for c in v_cols if c in df_filtered.columns]
strike_zone_df = df_filtered[show_cols].sort_values('Action_Score', ascending=False)

st.dataframe(strike_zone_df, use_container_width=True, hide_index=True, height=400,
    column_config={"TV_Link": st.column_config.LinkColumn("SYM 🔗", display_text=r"symbol=(.*)"),
                   "RS Rating": st.column_config.ProgressColumn("RS", min_value=0, max_value=99)})

# גרף
st.markdown("---")
st.markdown("### 📈 INTERACTIVE CHARTING")
tks = sorted(df_filtered['Symbol'].unique())
if tks:
    sel_t = st.selectbox("🎯 בחר מניה:", tks)
    td = yf.download(sel_t, period="1y", interval="1d", progress=False)
    if not td.empty:
        if isinstance(td.columns, pd.MultiIndex): td.columns = td.columns.get_level_values(0)
        td['SMA21'], td['SMA50'], td['SMA200'] = td['Close'].rolling(21).mean(), td['Close'].rolling(50).mean(), td['Close'].rolling(200).mean()
        disp = td.tail(130)
        cands, vols, s21, s50, s200 = [], [], [], [], []
        for d, r in disp.iterrows():
            ts = d.strftime('%Y-%m-%d')
            cands.append({"time": ts, "open": float(r['Open']), "high": float(r['High']), "low": float(r['Low']), "close": float(r['Close'])})
            vols.append({"time": ts, "value": float(r['Volume']), "color": '#26a69a80' if r['Close'] >= r['Open'] else '#ef535080'})
            if pd.notna(r['SMA21']): s21.append({"time": ts, "value": float(r['SMA21'])})
            if pd.notna(r['SMA50']): s50.append({"time": ts, "value": float(r['SMA50'])})
            if pd.notna(r['SMA200']): s200.append({"time": ts, "value": float(r['SMA200'])})
        
        renderLightweightCharts([{"chart": {"width": 1400, "height": 800, "layout": {"textColor": 'white', "background": {"color": '#0E1117'}}, "watermark": {"visible": True, "fontSize": 140, "text": sel_t, "color": 'rgba(255,255,255,0.06)'}, "rightPriceScale": {"scaleMargins": {"top": 0.05, "bottom": 0.25}}, "leftPriceScale": {"visible": False, "scaleMargins": {"top": 0.8, "bottom": 0}}}, 
                                  "series": [{"type": 'Candlestick', "data": cands}, {"type": 'Histogram', "data": vols, "options": {"priceScaleId": 'left'}},
                                             {"type": 'Line', "data": s21, "options": {"color": "#1053e6", "title": 'SMA 21'}},
                                             {"type": 'Line', "data": s50, "options": {"color": "#14b11c", "title": 'SMA 50'}},
                                             {"type": 'Line', "data": s200, "options": {"color": '#d50000', "title": 'SMA 200'}}]}], 'chart')

# Macro
st.markdown("---")
st.markdown("### 🌊 MACRO: SECTOR VELOCITY")
m1, m2 = st.columns(2)
with m1:
    if not group_df.empty:
        st.caption("🏆 LEADERS: TOP 40 IBD GROUPS")
        st.dataframe(group_df.sort_values('Rank this Wk').head(40), use_container_width=True, hide_index=True, height=350)
with m2:
    if not group_df.empty:
        top_j = group_df.sort_values('Rank_Improvement', ascending=False).head(20)
        j_df = df_raw[df_raw['Industry Group Name'].isin(top_j['Industry Group Name'])]
        st.caption("🚀 MOMENTUM: JUMPING GROUPS")
        st.dataframe(j_df[['Industry Group Name', 'Rank_Improvement', 'TV_Link', 'RS Rating']].sort_values(['Rank_Improvement', 'RS Rating'], ascending=False), use_container_width=True, hide_index=True, height=350)

# Export
def to_excel(df):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='xlsxwriter') as w:
        df.to_excel(w, index=False)
    return out.getvalue()

st.download_button("📥 הורד ל-Excel", to_excel(strike_zone_df), f"Market_Export_{datetime.now().strftime('%Y%m%d')}.xlsx")
