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
# 📁 הגדרות נתיבים ופונקציות עזר
# ==========================================
DATA_DIR = "data"

def find_file_robust(directory, filename_target):
    if not os.path.exists(directory):
        return None
    try:
        files = os.listdir(directory)
        target = filename_target.lower().replace(" ", "").strip()
        for f in files:
            clean_f = f.lower().replace(" ", "").strip()
            if clean_f == target:
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
    .block-container { padding-top: 1.5rem; padding-bottom: 1.5rem; direction: rtl; max-width: 98%; }
    h1, h2, h3 { color: #E6EDF3; font-family: 'Consolas', 'Courier New', monospace; text-transform: uppercase; letter-spacing: 1px; }
    h1 { border-bottom: 2px solid #238636; padding-bottom: 10px; }
    .stDataFrame { direction: ltr; }
    div[data-baseweb="input"] { background-color: #161B22; border: 1px solid #30363D; border-radius: 4px; }
    div[data-baseweb="select"] > div { background-color: #161B22; border: 1px solid #30363D; }
    .stDownloadButton > button { background-color: #238636; color: white; border: none; width: 100%; }
    .stDownloadButton > button:hover { background-color: #2EA043; border: none; }
    .diagnostic-box { background-color: #161B22; border: 1px solid #30363D; padding: 15px; border-radius: 5px; margin-bottom: 20px;}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 📡 טעינת נתונים משולבת (TV + IBD + Group Ranking)
# ==========================================
@st.cache_data(ttl=1800, show_spinner=False)
def load_hybrid_data():
    debug_log = []
    try:
        # 1. TradingView Live Data
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
            return pd.DataFrame(), pd.DataFrame(), ["❌ לא התקבלו נתונים מ-TV"]

        rename_map = {'ticker': 'Symbol', 'name': 'Company_Name', 'close': 'Price', 'volume': 'TV_Volume', 
                      'average_volume_10d_calc': 'TV_AvgVol10', 'market_cap_basic': 'Market Cap', 
                      'industry': 'Industry Group Name'}
        df_raw = df_tv.rename(columns=rename_map).copy()
        df_raw['Symbol'] = df_raw['Symbol'].apply(lambda x: x.split(':')[-1] if isinstance(x, str) and ':' in x else x)
        df_raw['TV_Link'] = "https://www.tradingview.com/chart/?symbol=" + df_raw['Symbol']
        df_raw['Market_Cap_B'] = pd.to_numeric(df_raw['Market Cap'], errors='coerce') / 1_000_000_000.0
        df_raw['Dollar_Volume_M'] = (df_raw['Price'] * df_raw['TV_AvgVol10']) / 1_000_000.0

        # 2. Live Pattern Engine (Restored FULL Logic)
        df_raw['Rel_Volume'] = df_raw['TV_Volume'] / df_raw['TV_AvgVol10']
        df_raw['Spread'] = df_raw['high'] - df_raw['low']
        df_raw['Close_Pos'] = np.where(df_raw['Spread'] > 0, (df_raw['Price'] - df_raw['low']) / df_raw['Spread'], 0.5)
        df_raw['ADR_Pct'] = np.where(df_raw['low'] > 0, (df_raw['ATR'] / df_raw['low']) * 100, 0)

        def get_patterns(row):
            b = []
            p, op, hi, lo = row.get('Price', 0), row.get('open', 0), row.get('high', 0), row.get('low', 0)
            rvol, atr, adr = row.get('Rel_Volume', 1), row.get('ATR', 0), row.get('ADR_Pct', 0)
            sma10, sma20, sma50, sma200 = row.get('SMA10', 0), row.get('SMA20', 0), row.get('SMA50', 0), row.get('SMA200', 0)
            spread, cp = row.get('Spread', 0), row.get('Close_Pos', 0.5)
            
            perf3 = row.get('Perf.3M', 0)
            perf3 = (perf3 / 100.0) if not pd.isna(perf3) else 0
            
            h52 = row.get('price_52_week_high', 0)
            h52p = (p - h52) / h52 if h52 and h52 > 0 else -99

            if p <= 0: return ""
            if sma50 > 0 and lo < sma50 < p: b.append("U&R(50) 🛡️")
            if sma20 > 0 and lo < sma20 < p: b.append("U&R(21) 🛡️")
            if sma50 > 0 and (0.0 <= (p - sma50) / sma50 <= 0.03) and p > sma200: b.append("Bounce50 🏀")
            if sma20 > 0 and sma50 > 0 and (0.0 <= (p - sma20) / sma20 <= 0.035) and sma20 > sma50: b.append("Ride20 🏄")
            if rvol > 1.5 and p > op and cp > 0.7: b.append("HVC 🚀")
            if rvol > 1.2 and adr > 0 and (spread / lo * 100 if lo > 0 else 0) > adr and cp < 0.4: b.append("SQUAT 🏋️")
            if atr > 0 and spread < (atr * 0.7) and cp > 0.5: b.append("ID 🕯️")
            if perf3 > 0.90 and h52p >= -0.20: b.append("HTF 🚩")
            if adr > 0 and (spread / lo * 100 if lo > 0 else adr) < (adr * 0.6) and rvol < 1.0: b.append("Tight/VCP 🤏")
            if h52p >= -0.02: b.append("52W High 👑")
            if sma10 > 0 and (p / sma10 - 1) > 0.15: b.append("EXT ⚠️")
            
            move_pct = spread / lo * 100 if lo > 0 else 0
            adr_ratio = move_pct / adr if adr > 0 else 0
            if 0.8 <= adr_ratio <= 1.2: b.append("1 ADR 📏")
            elif 1.5 <= adr_ratio <= 2.5: b.append("2 ADR 🔥")

            return "  ".join(b)

        df_raw['Pattern_Badges'] = df_raw.apply(get_patterns, axis=1)

        # 3. Weinstein Stages
        p, ma50, ma200 = df_raw['Price'], df_raw['SMA50'], df_raw['SMA200']
        h52, l52 = df_raw['price_52_week_high'], df_raw['price_52_week_low']
        df_raw['52W_High_Pct'] = np.where(h52 > 0, (p - h52) / h52, -1)
        df_raw['52W_Low_Pct'] = np.where(l52 > 0, (p - l52) / l52, 0)
        
        c2 = (p > ma50) & (ma50 > ma200) & (df_raw['52W_Low_Pct'] >= 0.25) & (df_raw['52W_High_Pct'] >= -0.25)
        c4 = (p < ma50) & (ma50 < ma200)
        df_raw['Weinstein_Stage'] = np.select([c2, c4], ['Stage 2 🚀 Adv', 'Stage 4 📉 Dec'], default='Stage 1/3')

        # 4. IBD & Group Ranking Load
        df_ibd = pd.DataFrame()
        ibd_p = find_file_robust(DATA_DIR, "IBD.csv")
        if ibd_p:
            try:
                try: df_ibd = pd.read_csv(ibd_p, encoding='utf-8-sig')
                except: df_ibd = pd.read_csv(ibd_p, encoding='cp1252')
                df_ibd.columns = df_ibd.columns.str.strip()
                for c in ['RS Rating', 'Comp. Rating', 'EPS Rating', 'Industry Group Rank']:
                    if c in df_ibd.columns: df_ibd[c] = pd.to_numeric(df_ibd[c].astype(str).str.replace('%','').str.replace(',',''), errors='coerce')
                debug_log.append("✅ קובץ IBD נטען בהצלחה")
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
                debug_log.append("✅ קובץ Group Ranking נטען בהצלחה")
            except Exception as e: debug_log.append(f"❌ שגיאת Group: {e}")

        # Merging
        if not df_ibd.empty and not group_df.empty:
            df_ibd = pd.merge(df_ibd, group_df[['Rank this Wk', 'Rank_Improvement', 'Industry Group Name']], 
                              left_on='Industry Group Rank', right_on='Rank this Wk', how='left')

        if not df_ibd.empty:
            if 'Industry Group Name' in df_raw.columns and 'Industry Group Name' in df_ibd.columns: 
                df_raw = df_raw.drop(columns=['Industry Group Name'])
            icols = ['Symbol', 'RS Rating', 'Comp. Rating', 'EPS Rating', 'Acc/Dis Rating', 'SMR Rating', 
                    'Spon Rating', 'Ind Grp RS', 'Industry Group Rank', 'Rank_Improvement', 'Industry Group Name']
            df_raw = pd.merge(df_raw, df_ibd[[c for c in icols if c in df_ibd.columns]], on='Symbol', how='left')
        
        # RS Backfill
        if 'Perf.Y' in df_raw.columns:
            df_raw['RS Rating'] = df_raw['RS Rating'].fillna(df_raw['Perf.Y'].rank(pct=True)*99).astype(int)

        # Excel Alerts Backfill
        ex_p = glob.glob(os.path.join(DATA_DIR, "Ultimate_Market_V3f_*.xlsx"))
        if ex_p:
            try:
                edfx = pd.read_excel(max(ex_p, key=os.path.getmtime), sheet_name='Full Raw Data')
                df_raw = pd.merge(df_raw, edfx[['Symbol', 'Earnings_Alert', 'Kinetic_Slope', 'VDU_Alert']], on='Symbol', how='left')
            except: pass

        for c in ['Earnings_Alert', 'Kinetic_Slope', 'VDU_Alert']:
            if c not in df_raw.columns: df_raw[c] = ''

        debug_log.append("✅ מיזוג נתונים סופי הושלם")
        return df_raw, group_df, debug_log
    except Exception as e:
        return pd.DataFrame(), pd.DataFrame(), [f"❌ שגיאה כללית: {e}"]

# ==========================================
# UI Logic
# ==========================================
st.title("📟 HYBRID COMMAND CENTER :: TV + IBD")

df_raw, group_df, debug_log = load_hybrid_data()

# Diagnostic
with st.expander("🔍 מצב אבחון קבצים (X-Ray)"):
    if os.path.exists(DATA_DIR): st.write(f"קבצים בתיקייה: {os.listdir(DATA_DIR)}")
    for log in debug_log: st.write(log)
    if st.button("📡 רענן נתונים ופתח מטמון"):
        load_hybrid_data.clear()
        st.rerun()

if df_raw.empty:
    st.error("⚠️ לא ניתן היה לטעון נתונים.")
    st.stop()

# --- CORE FILTERS ---
st.markdown("### ⚙️ CORE PARAMETERS")
c1, c2, c3, c4 = st.columns(4)
with c1: min_rs = st.number_input("⚡ RS Rating", 1, 99, 85)
with c2: min_v = st.number_input("💵 $ Vol (M)", 0.0, 500.0, 5.0)
with c3: req_lc = st.toggle("> $1B Cap", False)
with c4:
    stgs = sorted([str(s) for s in df_raw['Weinstein_Stage'].unique() if s])
    stg_f = st.multiselect("📊 Stage", stgs, default=["Stage 2 🚀 Adv"] if "Stage 2 🚀 Adv" in stgs else None)

mask = (df_raw['RS Rating'] >= min_rs) & (df_raw['Dollar_Volume_M'] >= min_v)
if req_lc: mask &= (df_raw['Market_Cap_B'] >= 1.0)
df_filtered = df_raw[mask].copy()
if stg_f: df_filtered = df_filtered[df_filtered['Weinstein_Stage'].isin(stg_f)]

# --- ADVANCED FILTERS & COLUMNS ---
with st.expander("🛠️ ADVANCED FILTERS & COLUMNS"):
    adv1, adv2, adv3 = st.columns(3)
    with adv1:
        if 'Pattern_Badges' in df_filtered.columns:
            all_b = sorted(list(set(df_filtered['Pattern_Badges'].str.split('  ').explode().dropna())))
            b_filt = st.multiselect("LIVE Patterns", [x for x in all_b if x])
            for b in b_filt: df_filtered = df_filtered[df_filtered['Pattern_Badges'].str.contains(b, na=False)]
    with adv2:
        m_comp = st.number_input("Min Comp", 1, 99, 1)
        if m_comp > 1: df_filtered = df_filtered[df_filtered['Comp. Rating'] >= m_comp]
    with adv3:
        m_eps = st.number_input("Min EPS", 1, 99, 1)
        if m_eps > 1: df_filtered = df_filtered[df_filtered['EPS Rating'] >= m_eps]

    st.markdown("---")
    ib1, ib2, ib3, ib4 = st.columns(4)
    for col, widget in zip(['Ind Grp RS', 'SMR Rating', 'Acc/Dis Rating', 'Spon Rating'], [ib1, ib2, ib3, ib4]):
        if col in df_filtered.columns:
            opts = sorted([str(x) for x in df_filtered[col].dropna().unique() if str(x) != 'nan'])
            sel = widget.multiselect(col, opts)
            if sel: df_filtered = df_filtered[df_filtered[col].astype(str).isin(sel)]

    st.markdown("---")
    possible_cols = ['TV_Link', 'Price', 'RS Rating', 'Comp. Rating', 'EPS Rating', 'Acc/Dis Rating', 'SMR Rating', 
                    'Spon Rating', 'Ind Grp RS', 'Rank_Improvement', 'Weinstein_Stage', 'Pattern_Badges', 'VDU_Alert', 'Earnings_Alert']
    available_cols = [c for c in possible_cols if c in df_raw.columns]
    default_cols = ['TV_Link', 'Price', 'RS Rating', 'Comp. Rating', 'Ind Grp RS', 'Rank_Improvement', 'Weinstein_Stage', 'Pattern_Badges']
    selected_view = st.multiselect("👀 בחר עמודות להצגה:", available_cols, default=[c for c in default_cols if c in available_cols])

# Action Score calculation
df_filtered['Action_Score'] = (df_filtered['RS Rating'] / 10) + (pd.to_numeric(df_filtered.get('Kinetic_Slope', 0), errors='coerce').fillna(0) / 50).clip(upper=3)

# --- ACTION GRID ---
st.markdown(f"### 🎯 ACTION GRID ({len(df_filtered)} STOCKS)")
display_final = selected_view.copy()
if 'Action_Score' not in display_final: display_final.insert(0, 'Action_Score')

strike_zone_df = df_filtered[display_final].sort_values('Action_Score', ascending=False)

st.dataframe(strike_zone_df, use_container_width=True, hide_index=True, height=400,
    column_config={
        "TV_Link": st.column_config.LinkColumn("SYM 🔗", display_text=r"symbol=(.*)"),
        "RS Rating": st.column_config.ProgressColumn("RS", min_value=0, max_value=99),
        "Price": st.column_config.NumberColumn("PRICE", format="$%.2f")
    })

# --- CHARTING ---
st.markdown("---")
st.markdown("### 📈 INTERACTIVE CHARTING")
tks = sorted(df_filtered['Symbol'].dropna().unique())
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
        
        # הגדרות גרף - פרופורציונלי לחלוטין (מצב כהה, ללא שטחים מתים, ווליום בתחתית)
        opts = {
            "height": 700,
            "layout": {"textColor": '#D1D4DC', "background": {"type": 'solid', "color": '#0E1117'}},
            "grid": {
                "vertLines": {"color": 'rgba(42, 46, 57, 0.5)', "style": 1},
                "horzLines": {"color": 'rgba(42, 46, 57, 0.5)', "style": 1}
            },
            "watermark": {"visible": True, "fontSize": 120, "text": sel_t, "color": 'rgba(255, 255, 255, 0.05)'},
            "rightPriceScale": {"scaleMargins": {"top": 0.05, "bottom": 0.2}, "borderColor": '#2B2B43'},
            "timeScale": {"borderColor": '#2B2B43'}
        }
        
        c_left, c_main, c_right = st.columns([0.01, 0.98, 0.01])
        with c_main:
            renderLightweightCharts([{"chart": opts, "series": [
                {"type": 'Candlestick', "data": cands, "options": {"upColor": '#26a69a', "downColor": '#ef5350', "borderVisible": False, "wickUpColor": '#26a69a', "wickDownColor": '#ef5350'}},
                # הווליום מוגדר כ-Overlay ומוגבל ל-15% התחתונים בלבד ("top": 0.85)
                {"type": 'Histogram', "data": vols, "options": {"priceFormat": {"type": 'volume'}, "priceScaleId": '', "scaleMargins": {"top": 0.85, "bottom": 0}}},
                {"type": 'Line', "data": s21, "options": {"color": "#1053e6", "lineWidth": 2, "title": 'SMA 21'}},
                {"type": 'Line', "data": s50, "options": {"color": "#14b11c", "lineWidth": 2, "title": 'SMA 50'}},
                {"type": 'Line', "data": s200, "options": {"color": '#d50000', "lineWidth": 2, "title": 'SMA 200'}}
            ]}], 'chart')

# --- MACRO ---
st.markdown("---")
st.markdown("### 🌊 MACRO: SECTOR VELOCITY")
m1, m2 = st.columns(2)
with m1:
    if not group_df.empty:
        st.caption("🏆 LEADERS: TOP 40 IBD GROUPS")
        st.dataframe(group_df.sort_values('Rank this Wk').head(40), use_container_width=True, hide_index=True, height=350)
with m2:
    if not group_df.empty and 'Industry Group Name' in df_raw.columns:
        top_j = group_df.sort_values('Rank_Improvement', ascending=False).head(20)
        j_df = df_raw[df_raw['Industry Group Name'].isin(top_j['Industry Group Name'])]
        st.caption("🚀 MOMENTUM: TOP STOCKS IN JUMPING GROUPS")
        st.dataframe(j_df[['Industry Group Name', 'Rank_Improvement', 'TV_Link', 'RS Rating']].sort_values(['Rank_Improvement', 'RS Rating'], ascending=False), 
                     use_container_width=True, hide_index=True, height=350,
                     column_config={"TV_Link": st.column_config.LinkColumn("SYM 🔗", display_text=r"symbol=(.*)"),
                                   "RS Rating": st.column_config.ProgressColumn("RS", min_value=0, max_value=99)})

# --- EXPORT ---
def to_excel(df):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='xlsxwriter') as w:
        df.to_excel(w, index=False)
    return out.getvalue()

st.download_button("📥 הורד רשימה ל-Excel", to_excel(strike_zone_df), f"Market_Export_{datetime.now().strftime('%Y%m%d')}.xlsx")
