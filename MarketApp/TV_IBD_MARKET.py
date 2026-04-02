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
# 📁 הגדרת נתיב נתונים (מותאם לענן ולמקומי)
# ==========================================
DATA_DIR = "data"

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
# 📡 טעינת נתונים חסינת-תקלות (עם לוג פנימי)
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
            debug_log.append("❌ שגיאה: לא התקבלו נתונים מ-TV")
            return pd.DataFrame(), pd.DataFrame(), debug_log

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

        def generate_live_patterns(row):
            badges = []
            price, op, hi, lo = row.get('Price', 0), row.get('open', 0), row.get('high', 0), row.get('low', 0)
            rvol, atr, adr = row.get('Rel_Volume', 1), row.get('ATR', 0), row.get('ADR_Pct', 0)
            sma10, sma20, sma50, sma200 = row.get('SMA10', 0), row.get('SMA20', 0), row.get('SMA50', 0), row.get('SMA200', 0)
            spread, close_pos = row.get('Spread', 0), row.get('Close_Pos', 0.5)
            perf_3m = row.get('Perf.3M', 0)
            perf_3m = (perf_3m / 100.0) if not pd.isna(perf_3m) else 0
            hi52 = row.get('price_52_week_high', 0)
            hi52_pct = (price - hi52) / hi52 if hi52 and hi52 > 0 else -99

            if price <= 0: return ""
            if sma50 > 0 and lo < sma50 < price: badges.append("U&R(50) 🛡️")
            if sma20 > 0 and lo < sma20 < price: badges.append("U&R(21) 🛡️")
            if sma50 > 0 and (0.0 <= (price - sma50) / sma50 <= 0.03) and price > sma200: badges.append("Bounce50 🏀")
            if sma20 > 0 and sma50 > 0 and (0.0 <= (price - sma20) / sma20 <= 0.035) and sma20 > sma50: badges.append("Ride20 🏄")
            if rvol > 1.5 and price > op and close_pos > 0.7: badges.append("HVC 🚀")
            if rvol > 1.2 and adr > 0 and (spread / lo * 100 if lo > 0 else 0) > adr and close_pos < 0.4: badges.append("SQUAT 🏋️")
            if atr > 0 and spread < (atr * 0.7) and close_pos > 0.5: badges.append("ID 🕯️")
            if perf_3m > 0.90 and hi52_pct >= -0.20: badges.append("HTF 🚩")
            if adr > 0 and (spread / lo * 100 if lo > 0 else adr) < (adr * 0.6) and rvol < 1.0: badges.append("Tight/VCP 🤏")
            if hi52_pct >= -0.02: badges.append("52W High 👑")
            if sma10 > 0 and (price / sma10 - 1) > 0.15: badges.append("EXT ⚠️")
            
            move_pct = spread / lo * 100 if lo > 0 else 0
            adr_ratio = move_pct / adr if adr > 0 else 0
            if 0.8 <= adr_ratio <= 1.2: badges.append("1 ADR 📏")
            elif 1.5 <= adr_ratio <= 2.5: badges.append("2 ADR 🔥")
            return "  ".join(badges)

        df_raw['Pattern_Badges'] = df_raw.apply(generate_live_patterns, axis=1)

        # --- 3. זיהוי Weinstein Stages ---
        p, ma50, ma200 = df_raw['Price'], df_raw['SMA50'], df_raw['SMA200']
        hi52, lo52 = df_raw['price_52_week_high'], df_raw['price_52_week_low']
        df_raw['52W_High_Pct'] = np.where(hi52 > 0, (p - hi52) / hi52, -99)
        df_raw['52W_Low_Pct'] = np.where(lo52 > 0, (p - lo52) / lo52, 0)
        
        cond_stage2 = (p > ma50) & (ma50 > ma200) & (df_raw['52W_Low_Pct'] >= 0.25) & (df_raw['52W_High_Pct'] >= -0.25)
        cond_stage4 = (p < ma50) & (ma50 < ma200) & (df_raw['52W_High_Pct'] < -0.25)
        cond_stage3 = (~cond_stage2) & (~cond_stage4) & (df_raw['52W_High_Pct'] >= -0.20) & (p < ma50)
        cond_stage1 = (~cond_stage2) & (~cond_stage4) & (~cond_stage3) & (df_raw['52W_High_Pct'] < -0.20) & (abs(p - ma200)/ma200 < 0.10)

        df_raw['Weinstein_Stage'] = np.select(
            [cond_stage2, cond_stage3, cond_stage4, cond_stage1],
            ['Stage 2 🚀 Adv', 'Stage 3 ⚠️ Top', 'Stage 4 📉 Dec', 'Stage 1 🔵 Base'],
            default='N/A'
        )

        # --- 4. שילוב קובץ IBD ---
        df_ibd = pd.DataFrame()
        ibd_path = find_file_robust(DATA_DIR, "IBD.csv")
        if ibd_path:
            try:
                try: df_ibd = pd.read_csv(ibd_path, encoding='utf-8-sig')
                except UnicodeDecodeError: df_ibd = pd.read_csv(ibd_path, encoding='cp1252')
                
                df_ibd.columns = df_ibd.columns.str.strip()
                for c in ['RS Rating', 'Comp. Rating', 'EPS Rating', 'Industry Group Rank']:
                    if c in df_ibd.columns:
                        df_ibd[c] = pd.to_numeric(df_ibd[c].astype(str).str.replace('%','').str.replace(',',''), errors='coerce')
                debug_log.append(f"✅ IBD נטען: {len(df_ibd)} שורות")
            except Exception as e: debug_log.append(f"❌ שגיאת IBD: {e}")

        # --- 5. שילוב קובץ Group Ranking (גרסה חסינת תקלות) ---
        group_path = find_file_robust(DATA_DIR, "Group Ranking.csv")
        group_df = pd.DataFrame()
        if group_path:
            try:
                debug_log.append(f"📂 מתחיל קריאת Group Ranking מנתיב: {group_path}")
                try: group_df = pd.read_csv(group_path, encoding='utf-8-sig')
                except UnicodeDecodeError: group_df = pd.read_csv(group_path, encoding='cp1252')
                
                group_df.columns = group_df.columns.str.strip()
                debug_log.append(f"🔍 עמודות מקוריות בקובץ הדירוג: {list(group_df.columns)}")
                
                rename_dict = {}
                for col in group_df.columns:
                    cl = col.lower()
                    if 'this wk' in cl or cl == 'rank': rename_dict[col] = 'Rank this Wk'
                    elif '3 wks' in cl: rename_dict[col] = '3 Wks ago'
                    elif 'industry' in cl or 'name' in cl: rename_dict[col] = 'Industry Group Name'
                
                group_df = group_df.rename(columns=rename_dict)
                debug_log.append(f"✨ עמודות לאחר מיפוי חכם: {list(group_df.columns)}")

                if 'Rank this Wk' in group_df.columns and '3 Wks ago' in group_df.columns:
                    group_df['Rank this Wk'] = pd.to_numeric(group_df['Rank this Wk'], errors='coerce')
                    group_df['3 Wks ago'] = pd.to_numeric(group_df['3 Wks ago'], errors='coerce')
                    group_df['Rank_Improvement'] = group_df['3 Wks ago'] - group_df['Rank this Wk']
                else:
                    debug_log.append("⚠️ שגיאה: חסרות עמודות דירוג (Rank this Wk / 3 Wks ago) בקובץ.")

                if 'Industry Group Name' in group_df.columns:
                    group_df['Industry Group Name'] = group_df['Industry Group Name'].astype(str).str.strip()
                    debug_log.append(f"✅ Group Ranking נטען ומופה בהצלחה! ({len(group_df)} תעשיות)")

            except Exception as e: debug_log.append(f"❌ שגיאת קריאת Group Ranking: {e}")

        # --- מיזוג נתונים עמוק ---
        if not df_ibd.empty and not group_df.empty:
            df_ibd = pd.merge(df_ibd, group_df[['Rank this Wk', 'Rank_Improvement', 'Industry Group Name']], 
                              left_on='Industry Group Rank', right_on='Rank this Wk', how='left')

        if not df_ibd.empty:
            if 'Industry Group Name' in df_raw.columns and 'Industry Group Name' in df_ibd.columns:
                df_raw = df_raw.drop(columns=['Industry Group Name']) 
            
            ibd_cols = ['Symbol', 'RS Rating', 'Comp. Rating', 'EPS Rating', 'Acc/Dis Rating', 'SMR Rating', 
                        'Spon Rating', 'Ind Grp RS', 'Industry Group Rank', 'Rank_Improvement', 'Industry Group Name']
            ibd_cols = [c for c in ibd_cols if c in df_ibd.columns]
            df_raw = pd.merge(df_raw, df_ibd[ibd_cols], on='Symbol', how='left')
        else:
            for c in ['RS Rating', 'Comp. Rating', 'EPS Rating', 'Acc/Dis Rating', 'SMR Rating', 'Spon Rating', 'Ind Grp RS', 'Industry Group Rank', 'Rank_Improvement']:
                df_raw[c] = np.nan

        if 'Perf.Y' in df_raw.columns:
            smart_rs = df_raw['Perf.Y'].rank(pct=True) * 99
            df_raw['RS Rating'] = df_raw['RS Rating'].fillna(smart_rs).astype(int)

        # --- 6. משיכת נתוני אקסל ---
        excel_pattern = os.path.join(DATA_DIR, "Ultimate_Market_V3f_*.xlsx")
        excel_files = glob.glob(excel_pattern)
        if excel_files:
            latest_excel = max(excel_files, key=os.path.getmtime)
            try:
                df_excel = pd.read_excel(latest_excel, sheet_name='Full Raw Data')
                excel_cols = ['Symbol', 'Earnings_Alert', 'Kinetic_Slope', 'VDU_Alert']
                excel_cols = [c for c in excel_cols if c in df_excel.columns]
                df_raw = pd.merge(df_raw, df_excel[excel_cols], on='Symbol', how='left')
            except: pass
        
        for c in ['Earnings_Alert', 'Kinetic_Slope', 'VDU_Alert']:
            if c not in df_raw.columns: df_raw[c] = ''

        debug_log.append("✅ כל הנתונים עברו מיזוג סופי בהצלחה.")
        return df_raw, group_df, debug_log

    except Exception as e:
        debug_log.append(f"❌ שגיאה קריטית כללית: {e}")
        return pd.DataFrame(), pd.DataFrame(), debug_log

# ==========================================
# רענון ואבחון UI
# ==========================================
col_t, col_b = st.columns([5, 1])
with col_t: st.title("📟 HYBRID COMMAND CENTER :: TV + IBD")
with col_b:
    st.write("")
    st.markdown('<div class="refresh-btn">', unsafe_allow_html=True)
    if st.button("📡 רענן נתונים כעת", use_container_width=True):
        load_hybrid_data.clear() 
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

with st.spinner("מבצע מיזוג עמוק (TV + IBD + Groups)..."):
    df_raw, group_df, debug_log = load_hybrid_data()

# 🛠️ פאנל מצב רנטגן משודרג (מציג את יומן התקלות)
st.markdown('<div class="diagnostic-box">', unsafe_allow_html=True)
st.markdown("#### 🛠️ מצב אבחון תקלות (X-Ray Dashboard)")
if not os.path.exists(DATA_DIR):
    st.error(f"❌ התיקייה '{DATA_DIR}' לא נמצאה!")
else:
    st.info(f"📁 קבצים בתיקייה: {os.listdir(DATA_DIR)}")
    st.markdown('<div class="log-text">', unsafe_allow_html=True)
    for log in debug_log:
        st.write(log)
    st.markdown('</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

if df_raw.empty:
    st.error("⚠️ האפליקציה לא הצליחה לטעון נתונים. אנא קרא את הלוג למעלה.")
    st.stop()

# ==========================================
# 🖥️ בניית הממשק (Terminal UI)
# ==========================================
# --- פאנל שליטה ראשי ---
st.markdown("### ⚙️ CORE PARAMETERS")
ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns(4)

with ctrl_col1: min_rs = st.number_input("⚡ RS Rating (Min)", 1, 99, 85)
with ctrl_col2: min_dol_vol = st.number_input("💵 Avg $ Vol (Millions)", 0.0, 500.0, 5.0)
with ctrl_col3: req_large_cap = st.toggle("> $1 Billion Market Cap", False)
with ctrl_col4:
    stages = [s for s in df_raw['Weinstein_Stage'].dropna().unique() if s != '']
    stage_filter = st.multiselect("📊 Weinstein Stage", stages, default=["Stage 2 🚀 Adv"] if "Stage 2 🚀 Adv" in stages else None)

mask = (df_raw['RS Rating'] >= min_rs) & (df_raw['Dollar_Volume_M'] >= min_dol_vol)
if req_large_cap: mask &= (df_raw['Market_Cap_B'] >= 1.0)
df_filtered = df_raw[mask]
if stage_filter: df_filtered = df_filtered[df_filtered['Weinstein_Stage'].isin(stage_filter)]

# --- פאנל מתקדם ---
with st.expander("🛠️ ADVANCED FILTERS & COLUMNS"):
    adv_col1, adv_col2, adv_col3 = st.columns(3)
    with adv_col1:
        if 'Pattern_Badges' in df_raw.columns:
            badges = sorted([b for b in df_raw['Pattern_Badges'].str.split('  ').explode().dropna().unique() if b])
            b_filt = st.multiselect("LIVE Pattern Badges (AND)", badges)
            for b in b_filt: df_filtered = df_filtered[df_filtered['Pattern_Badges'].str.contains(b, na=False, regex=False)]
    with adv_col2:
        min_comp = st.number_input("Comp. Rating (Min)", 1, 99, 1)
        if min_comp > 1: df_filtered = df_filtered[df_filtered['Comp. Rating'] >= min_comp]
    with adv_col3:
        min_eps = st.number_input("EPS Rating (Min)", 1, 99, 1)
        if min_eps > 1: df_filtered = df_filtered[df_filtered['EPS Rating'] >= min_eps]

    st.markdown("---")
    st.write("📊 **IBD Grade Filters:**")
    ibd_c1, ibd_c2, ibd_c3, ibd_c4 = st.columns(4)
    with ibd_c1:
        if 'Ind Grp RS' in df_raw.columns:
            opt = sorted([str(x) for x in df_raw['Ind Grp RS'].dropna().unique() if str(x) != 'nan'])
            i_filt = st.multiselect("Ind Grp RS", opt)
            if i_filt: df_filtered = df_filtered[df_filtered['Ind Grp RS'].astype(str).isin(i_filt)]
    with ibd_c2:
        if 'Spon Rating' in df_raw.columns:
            opt = sorted([str(x) for x in df_raw['Spon Rating'].dropna().unique() if str(x) != 'nan'])
            s_filt = st.multiselect("Spon Rating", opt)
            if s_filt: df_filtered = df_filtered[df_filtered['Spon Rating'].astype(str).isin(s_filt)]
    with ibd_c3:
        if 'SMR Rating' in df_raw.columns:
            opt = sorted([str(x) for x in df_raw['SMR Rating'].dropna().unique() if str(x) != 'nan'])
            sm_filt = st.multiselect("SMR Rating", opt)
            if sm_filt: df_filtered = df_filtered[df_filtered['SMR Rating'].astype(str).isin(sm_filt)]
    with ibd_c4:
        if 'Acc/Dis Rating' in df_raw.columns:
            opt = sorted([str(x) for x in df_raw['Acc/Dis Rating'].dropna().unique() if str(x) != 'nan'])
            a_filt = st.multiselect("Acc/Dis Rating", opt)
            if a_filt: df_filtered = df_filtered[df_filtered['Acc/Dis Rating'].astype(str).isin(a_filt)]

    st.markdown("---")
    valid_cols = [c for c in ['TV_Link', 'Price', 'RS Rating', 'Comp. Rating', 'EPS Rating', 'Acc/Dis Rating', 'SMR Rating', 'Spon Rating', 'Ind Grp RS', 'Kinetic_Slope', 'Rank_Improvement', 'Market_Cap_B', 'Weinstein_Stage', 'Pattern_Badges', 'VDU_Alert', 'Earnings_Alert'] if c in df_filtered.columns]
    def_view = [c for c in ['TV_Link', 'Price', 'RS Rating', 'Comp. Rating', 'EPS Rating', 'Acc/Dis Rating', 'Action_Score', 'Kinetic_Slope', 'Rank_Improvement', 'Weinstein_Stage', 'Pattern_Badges', 'VDU_Alert'] if c in valid_cols or c == 'Action_Score']
    disp_cols = st.multiselect("👀 עמודות לתצוגה:", valid_cols, default=[c for c in def_view if c != 'Action_Score'])

# --- אזור הפעולה (Strike Zone) ---
st.markdown("---")
st.markdown(f"### 🎯 ACTION GRID <span style='color:#2EA043; font-size:0.8em;'>({len(df_filtered)} STOCKS)</span>", unsafe_allow_html=True)
df_filtered['Action_Score'] = (df_filtered['RS Rating'] / 10) + (pd.to_numeric(df_filtered.get('Kinetic_Slope', 0), errors='coerce').fillna(0) / 50).clip(upper=3)

cols_show = [c for c in disp_cols if c in df_filtered.columns]
if 'Action_Score' not in cols_show: cols_show.insert(3, 'Action_Score')

strike_zone_df = df_filtered[cols_show].sort_values('Action_Score', ascending=False)

st.dataframe(strike_zone_df, use_container_width=True, hide_index=True, height=400,
    column_config={
        "TV_Link": st.column_config.LinkColumn("SYM 🔗", display_text=r"symbol=(.*)"),
        "Price": st.column_config.NumberColumn("PRICE", format="$%.2f"),
        "RS Rating": st.column_config.ProgressColumn("RS RATING", format="%d", min_value=0, max_value=99),
        "Action_Score": st.column_config.NumberColumn("ACTION SCORE", format="%.1f"),
        "Market_Cap_B": st.column_config.NumberColumn("MKT CAP ($B)", format="%.2f B"),
        "Pattern_Badges": st.column_config.TextColumn("LIVE PATTERNS ⚡"),
        "Weinstein_Stage": st.column_config.TextColumn("STAGE"),
        "Rank_Improvement": st.column_config.NumberColumn("GRP JUMP"),
        "Earnings_Alert": st.column_config.TextColumn("EARNINGS 📅"),
        "Comp. Rating": st.column_config.NumberColumn("COMP"),
        "EPS Rating": st.column_config.NumberColumn("EPS"),
        "Acc/Dis Rating": st.column_config.TextColumn("ACC/DIS"),
        "SMR Rating": st.column_config.TextColumn("SMR"),
        "Spon Rating": st.column_config.TextColumn("SPON"),
        "Ind Grp RS": st.column_config.TextColumn("IND RS"),
        "Kinetic_Slope": st.column_config.NumberColumn("K-SLOPE 🚀", format="%.1f")
    })

# --- אזור הגרפים ---
st.markdown("---")
st.markdown("### 📈 INTERACTIVE CHARTING")
tickers = sorted(df_filtered['Symbol'].dropna().unique()) if 'Symbol' in df_filtered.columns else []

if tickers:
    sel_t = st.selectbox("🎯 בחר מניה לגרף אינטראקטיבי:", tickers)
    if sel_t:
        with st.spinner(f"טוען גרף {sel_t}..."):
            try:
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

                    opts = {"width": 1400, "height": 800, "layout": {"textColor": 'white', "background": {"type": 'solid', "color": '#0E1117'}}, "watermark": {"visible": True, "fontSize": 140, "horzAlign": 'center', "vertAlign": 'center', "color": 'rgba(255, 255, 255, 0.06)', "text": sel_t}, "rightPriceScale": {"scaleMargins": {"top": 0.05, "bottom": 0.25}, "borderColor": '#30363D'}, "leftPriceScale": {"visible": False, "scaleMargins": {"top": 0.8, "bottom": 0}}, "grid": {"vertLines": {"color": '#1C2128'}, "horzLines": {"color": '#1C2128'}}, "crosshair": {"mode": 0}, "timeScale": {"borderColor": '#30363D'}}
                    series = [
                        {"type": 'Candlestick', "data": cands, "options": {"upColor": '#26a69a', "downColor": '#ef5350', "borderVisible": False, "wickUpColor": '#26a69a', "wickDownColor": '#ef5350'}},
                        {"type": 'Histogram', "data": vols, "options": {"priceFormat": {"type": 'volume'}, "priceScaleId": 'left'}},
                        {"type": 'Line', "data": s21, "options": {"color": "#1053e6", "lineWidth": 2, "title": 'SMA 21'}},
                        {"type": 'Line', "data": s50, "options": {"color": "#14b11c", "lineWidth": 2, "title": 'SMA 50'}},
                        {"type": 'Line', "data": s200, "options": {"color": '#d50000', "lineWidth": 2, "title": 'SMA 200'}}
                    ]
                    c1, c2, c3 = st.columns([1, 10, 1])
                    with c2: renderLightweightCharts([{"chart": opts, "series": series}], 'chart')
            except Exception as e: st.error(f"שגיאת גרף: {e}")

# --- Sector Velocity ---
st.markdown("---")
st.markdown("### 🌊 MACRO: SECTOR VELOCITY (IBD RANKING)")
m1, m2 = st.columns(2)
with m1:
    if not group_df.empty:
        top_ind = group_df[['Industry Group Name', 'Rank this Wk', 'Rank_Improvement']].sort_values('Rank this Wk').head(40)
        st.caption("🏆 LEADERS: TOP 40 IBD GROUPS")
        st.dataframe(top_ind, use_container_width=True, hide_index=True, height=350)
    else: st.info("נתוני Group Ranking חסרים ביומן התקלות למעלה.")

with m2:
    if not group_df.empty and 'Rank_Improvement' in df_raw.columns:
        top_jump = group_df.sort_values('Rank_Improvement', ascending=False).head(20)
        jump_disp = df_raw[df_raw['Industry Group Name'].isin(top_jump['Industry Group Name'])]
        jump_disp = jump_disp[jump_disp['RS Rating'] >= 70].sort_values(['Rank_Improvement', 'RS Rating'], ascending=[False, False])
        st.caption(f"🚀 MOMENTUM: TOP STOCKS IN JUMPING GROUPS <span class='counter-badge'>({len(jump_disp)} STOCKS)</span>", unsafe_allow_html=True)
        st.dataframe(jump_disp[['Industry Group Name', 'Rank_Improvement', 'TV_Link', 'RS Rating']], use_container_width=True, hide_index=True, height=350,
            column_config={
                "Industry Group Name": st.column_config.TextColumn("INDUSTRY"),
                "Rank_Improvement": st.column_config.NumberColumn("JUMP"),
                "TV_Link": st.column_config.LinkColumn("SYM 🔗", display_text=r"symbol=(.*)"),
                "RS Rating": st.column_config.ProgressColumn("RS RATING", format="%d", min_value=0, max_value=99)
            })
    else: st.info("לא ניתן להציג קופצים ללא דירוג תעשיות.")

# --- ייצוא לאקסל ---
st.markdown("---")
def to_excel_with_links(df):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='xlsxwriter') as w:
        df.to_excel(w, index=False, sheet_name='Live Grid')
        wb, ws = w.book, w.sheets['Live Grid']
        lf = wb.add_format({'font_color': 'blue', 'underline': 1, 'bold': True})
        if 'TV_Link' in df.columns:
            ci = df.columns.get_loc('TV_Link')
            ws.set_column(ci, ci, 15)
            for i, url in enumerate(df['TV_Link']):
                if pd.notna(url) and isinstance(url, str) and "symbol=" in url:
                    ws.write_url(i+1, ci, url, lf, string=url.split("symbol=")[-1])
    return out.getvalue()

st.download_button("📥 הורד רשימה עדכנית ל-Excel", to_excel_with_links(strike_zone_df), f"Hybrid_Strike_Zone_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
