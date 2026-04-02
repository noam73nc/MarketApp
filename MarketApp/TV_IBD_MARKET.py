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
# ⚙️ הגדרות עמוד ותצורה - Terminal Mode
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
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 🛠️ פאנל מצב רנטגן (אבחון תקלות בענן)
# ==========================================
st.markdown('<div class="diagnostic-box">', unsafe_allow_html=True)
st.markdown("#### 🛠️ מצב אבחון תקלות (X-Ray)")
if not os.path.exists(DATA_DIR):
    st.error(f"❌ שגיאה קריטית: התיקייה '{DATA_DIR}' לא קיימת בשרת! ודא שיצרת תיקייה בשם data בשורש הפרויקט בגיטהאב.")
else:
    files_found = os.listdir(DATA_DIR)
    st.info(f"📁 התיקייה קיימת. קבצים שהשרת רואה בתוכה כרגע: {files_found}")
    
    ibd_f = find_file_robust(DATA_DIR, "IBD.csv")
    if ibd_f: st.success(f"✅ נמצא קובץ IBD: {ibd_f}")
    else: st.error("❌ לא נמצא קובץ ששמו IBD.csv")
    
    grp_f = find_file_robust(DATA_DIR, "Group Ranking.csv")
    if grp_f: st.success(f"✅ נמצא קובץ Group Ranking: {grp_f}")
    else: st.error("❌ לא נמצא קובץ ששמו Group Ranking.csv")
st.markdown('</div>', unsafe_allow_html=True)

# ==========================================
# 📡 טעינת נתונים משולבת + מנוע תבניות חי
# ==========================================
@st.cache_data(ttl=1800, show_spinner=False)
def load_hybrid_data():
    try:
        # --- 1. משיכת נתונים חיים מ-TV ---
        query = (Query()
                 .set_markets('america')
                 .select('name', 'close', 'open', 'high', 'low', 'volume', 'average_volume_10d_calc', 
                         'market_cap_basic', 'sector', 'industry', 
                         'SMA10', 'SMA20', 'SMA50', 'SMA200', 'price_52_week_high', 'price_52_week_low',
                         'Perf.W', 'Perf.1M', 'Perf.3M', 'Perf.Y', 'ATR')
                 .where(
                     Column('close') > 1, 
                     Column('average_volume_10d_calc') > 100000 
                 )
                 .limit(4500)) 
        
        count, df_tv = query.get_scanner_data()
        if df_tv.empty: return pd.DataFrame(), pd.DataFrame()

        rename_map = {
            'ticker': 'Symbol', 'name': 'Company_Name', 'close': 'Price',
            'volume': 'TV_Volume', 'average_volume_10d_calc': 'TV_AvgVol10',
            'market_cap_basic': 'Market Cap', 'industry': 'Industry Group Name'
        }
        df_raw = df_tv.rename(columns=rename_map).copy()
        df_raw['Symbol'] = df_raw['Symbol'].apply(lambda x: x.split(':')[-1] if isinstance(x, str) and ':' in x else x)
        df_raw['TV_Link'] = "https://www.tradingview.com/chart/?symbol=" + df_raw['Symbol']
        df_raw['Market_Cap_B'] = pd.to_numeric(df_raw['Market Cap'], errors='coerce') / 1_000_000_000.0
        df_raw['Dollar_Volume_M'] = (df_raw['Price'] * df_raw['TV_AvgVol10']) / 1_000_000.0

        # --- 2. חישוב תבניות טכניות (LIVE PATTERN ENGINE) ---
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
                df_ibd = pd.read_csv(ibd_path, encoding='utf-8-sig')
                df_ibd.columns = df_ibd.columns.str.strip()
                for c in ['RS Rating', 'Comp. Rating', 'EPS Rating', 'Industry Group Rank']:
                    if c in df_ibd.columns:
                        df_ibd[c] = pd.to_numeric(df_ibd[c].astype(str).str.replace('%','').str.replace(',',''), errors='coerce')
            except Exception as e: print(f"IBD load error: {e}")

        # --- 5. שילוב קובץ Group Ranking ---
        group_path = find_file_robust(DATA_DIR, "Group Ranking.csv")
        group_df = pd.DataFrame()
        if group_path:
            try:
                group_df = pd.read_csv(group_path, encoding='utf-8-sig')
                group_df.columns = group_df.columns.str.strip()
                cols = list(group_df.columns)
                if len(cols) >= 2:
                    cols[0], cols[1] = 'Rank this Wk', '3 Wks ago'
                    for i in range(2, len(cols)):
                        if 'Composite' in str(cols[i]): cols[i] = 'Group Composite Rating'
                        elif 'Industry' in str(cols[i]) or 'Name' in str(cols[i]): cols[i] = 'Industry Group Name'
                    group_df.columns = cols
                
                group_df['Rank this Wk'] = pd.to_numeric(group_df['Rank this Wk'], errors='coerce')
                group_df['3 Wks ago'] = pd.to_numeric(group_df['3 Wks ago'], errors='coerce')
                group_df['Rank_Improvement'] = group_df['3 Wks ago'] - group_df['Rank this Wk']
            except Exception as e: print(f"Group load error: {e}")

        # --- מיזוג נתונים ---
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

        # --- 6. משיכת נתוני אקסל (Earnings/Kinetic) ---
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

        return df_raw, group_df

    except Exception as e:
        st.error(f"Error: {e}")
        return pd.DataFrame(), pd.DataFrame()

# ==========================================
# קריאה לנתונים + כפתור רענון
# ==========================================
title_col, btn_col = st.columns([5, 1])
with title_col:
    st.title("📟 HYBRID COMMAND CENTER :: TV + IBD")
with btn_col:
    st.write("") 
    st.markdown('<div class="refresh-btn">', unsafe_allow_html=True)
    if st.button("📡 רענן נתונים כעת", use_container_width=True):
        load_hybrid_data.clear() 
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

with st.spinner("סורק תבניות טכניות וממזג נתוני שוק..."):
    df_raw, group_df = load_hybrid_data()

if df_raw.empty:
    st.error("⚠️ שגיאה בטעינת הנתונים. ודא שהקבצים קיימים בתיקייה.")
else:
    st.toast("✅ הנתונים שולבו והתבניות עודכנו בהצלחה!", icon="🚀")

# ==========================================
# 🖥️ בניית הממשק (Terminal UI)
# ==========================================
if not df_raw.empty:
    
    # --- 🎛️ פאנל שליטה ראשי ---
    st.markdown("### ⚙️ CORE PARAMETERS")
    ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns(4)
    
    with ctrl_col1:
        min_rs = st.number_input("⚡ RS Rating (Min)", min_value=1, max_value=99, value=85, step=1)
    with ctrl_col2:
        min_dol_vol = st.number_input("💵 Avg $ Vol (Millions)", min_value=0.0, max_value=500.0, value=5.0, step=1.0)
    with ctrl_col3:
        st.write("🏆 Market Cap Filter")
        req_large_cap = st.toggle("> $1 Billion Market Cap", value=False)
    with ctrl_col4:
        if 'Weinstein_Stage' in df_raw.columns:
            available_stages = [s for s in df_raw['Weinstein_Stage'].dropna().unique() if s != '']
            default_stage = ["Stage 2 🚀 Adv"] if "Stage 2 🚀 Adv" in available_stages else None
            stage_filter = st.multiselect("📊 Weinstein Stage", options=available_stages, default=default_stage)
        else:
            stage_filter = []

    mask = (df_raw['RS Rating'] >= min_rs) & (df_raw['Dollar_Volume_M'] >= min_dol_vol)
    if req_large_cap:
        mask = mask & (df_raw['Market_Cap_B'] >= 1.0)
        
    df_filtered = df_raw[mask]
    if stage_filter:
        df_filtered = df_filtered[df_filtered['Weinstein_Stage'].isin(stage_filter)]

    # --- 🛠️ פאנל מתקדם ---
    with st.expander("🛠️ ADVANCED FILTERS & COLUMNS"):
        adv_col1, adv_col2, adv_col3 = st.columns(3)
        with adv_col1:
            if 'Pattern_Badges' in df_raw.columns:
                all_badges = df_raw['Pattern_Badges'].dropna().astype(str).str.split('  ').explode().str.strip()
                unique_badges = sorted([b for b in all_badges.unique() if b and b != 'nan'])
                badge_filter = st.multiselect("LIVE Pattern Badges (AND)", options=unique_badges)
                if badge_filter:
                    for badge in badge_filter:
                        df_filtered = df_filtered[df_filtered['Pattern_Badges'].astype(str).str.contains(badge, regex=False, na=False)]
        with adv_col2:
            if 'Comp. Rating' in df_raw.columns:
                min_comp = st.number_input("Comp. Rating (Min)", min_value=1, max_value=99, value=1, step=1)
                if min_comp > 1: df_filtered = df_filtered[df_filtered['Comp. Rating'] >= min_comp]
        with adv_col3:
            if 'EPS Rating' in df_raw.columns:
                min_eps = st.number_input("EPS Rating (Min)", min_value=1, max_value=99, value=1, step=1)
                if min_eps > 1: df_filtered = df_filtered[df_filtered['EPS Rating'] >= min_eps]

        st.markdown("---")
        st.write("📊 **IBD Grade Filters:**")
        ibd_col1, ibd_col2, ibd_col3, ibd_col4 = st.columns(4)
        
        with ibd_col1:
            if 'Ind Grp RS' in df_raw.columns:
                opts = sorted([str(x) for x in df_raw['Ind Grp RS'].dropna().unique() if str(x).lower() != 'nan'])
                ind_filter = st.multiselect("Ind Grp RS", options=opts)
                if ind_filter: df_filtered = df_filtered[df_filtered['Ind Grp RS'].astype(str).isin(ind_filter)]
        with ibd_col2:
            if 'Spon Rating' in df_raw.columns:
                opts = sorted([str(x) for x in df_raw['Spon Rating'].dropna().unique() if str(x).lower() != 'nan'])
                spon_filter = st.multiselect("Spon Rating", options=opts)
                if spon_filter: df_filtered = df_filtered[df_filtered['Spon Rating'].astype(str).isin(spon_filter)]
        with ibd_col3:
            if 'SMR Rating' in df_raw.columns:
                opts = sorted([str(x) for x in df_raw['SMR Rating'].dropna().unique() if str(x).lower() != 'nan'])
                smr_filter = st.multiselect("SMR Rating", options=opts)
                if smr_filter: df_filtered = df_filtered[df_filtered['SMR Rating'].astype(str).isin(smr_filter)]
        with ibd_col4:
            if 'Acc/Dis Rating' in df_raw.columns:
                opts = sorted([str(x) for x in df_raw['Acc/Dis Rating'].dropna().unique() if str(x).lower() != 'nan'])
                acc_filter = st.multiselect("Acc/Dis Rating", options=opts)
                if acc_filter: df_filtered = df_filtered[df_filtered['Acc/Dis Rating'].astype(str).isin(acc_filter)]

        st.markdown("---")
        st.write("👀 **בחירת עמודות לתצוגה בטבלת הפעולה:**")
        all_possible_cols = [
            'TV_Link', 'Price', 'RS Rating', 'Comp. Rating', 'EPS Rating', 'Acc/Dis Rating', 
            'SMR Rating', 'Spon Rating', 'Ind Grp RS', 'Kinetic_Slope', 'Rank_Improvement', 'Market_Cap_B', 
            'Weinstein_Stage', 'Pattern_Badges', 'VDU_Alert', 'Earnings_Alert'
        ]
        valid_cols = [col for col in all_possible_cols if col in df_filtered.columns]
        
        default_view = [
            'TV_Link', 'Price', 'RS Rating', 'Comp. Rating', 'EPS Rating', 
            'Acc/Dis Rating', 'Action_Score', 'Kinetic_Slope', 'Rank_Improvement', 
            'Weinstein_Stage', 'Pattern_Badges', 'VDU_Alert'
        ]
        default_view = [c for c in default_view if c in valid_cols or c == 'Action_Score']
        selected_display_cols = st.multiselect("", options=valid_cols, default=[c for c in default_view if c != 'Action_Score'])

    st.markdown("---")

    # ==========================================
    # 🎯 אזור הפעולה (Strike Zone)
    # ==========================================
    st.markdown(f"### 🎯 ACTION GRID <span style='color:#2EA043; font-size:0.8em;'>({len(df_filtered)} STOCKS)</span>", unsafe_allow_html=True)
    
    df_filtered['Action_Score'] = df_filtered['RS Rating'] / 10
    if 'Kinetic_Slope' in df_filtered.columns:
        slope_bonus = (pd.to_numeric(df_filtered['Kinetic_Slope'], errors='coerce').fillna(0) / 50).clip(upper=3)
        df_filtered['Action_Score'] += slope_bonus

    cols_to_show = [c for c in selected_display_cols if c in df_filtered.columns]
    if 'Action_Score' not in cols_to_show: cols_to_show.insert(3, 'Action_Score')
    strike_zone_df = df_filtered[cols_to_show].sort_values(by='Action_Score', ascending=False)

    st.dataframe(
        strike_zone_df,
        use_container_width=True,
        hide_index=True,
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
        },
        height=400 
    )
    
    # ==========================================
    # 📈 אזור הגרפים
    # ==========================================
    st.markdown("---")
    st.markdown("### 📈 INTERACTIVE CHARTING")

    if 'Symbol' in df_filtered.columns:
        available_tickers = df_filtered['Symbol'].dropna().unique().tolist()
        available_tickers = sorted([str(t).upper() for t in available_tickers])
    else:
        available_tickers = []

    if available_tickers:
        selected_ticker = st.selectbox("🎯 בחר מניה להצגת גרף אינטראקטיבי:", options=available_tickers)

        if selected_ticker:
            st.markdown(f"<h4 style='text-align: center; color: #2EA043;'>מציג נתוני גרף יומי עבור {selected_ticker}</h4>", unsafe_allow_html=True)
            with st.spinner(f"טוען נתוני גרף עבור {selected_ticker}..."):
                try:
                    ticker_data = yf.download(selected_ticker, period="1y", interval="1d", progress=False)
                    
                    if not ticker_data.empty:
                        if isinstance(ticker_data.columns, pd.MultiIndex):
                            ticker_data.columns = ticker_data.columns.get_level_values(0)
                        
                        ticker_data['SMA21'] = ticker_data['Close'].rolling(window=21).mean()
                        ticker_data['SMA50'] = ticker_data['Close'].rolling(window=50).mean()
                        ticker_data['SMA200'] = ticker_data['Close'].rolling(window=200).mean()

                        display_data = ticker_data.tail(130).copy()

                        candles, volume_data, sma21_data, sma50_data, sma200_data = [], [], [], [], []
                        
                        for date, row in display_data.iterrows():
                            time_str = date.strftime('%Y-%m-%d')
                            op, cl = float(row['Open']), float(row['Close'])
                            
                            candles.append({"time": time_str, "open": op, "high": float(row['High']), "low": float(row['Low']), "close": cl})
                            vol_color = '#26a69a' if cl >= op else '#ef5350'
                            volume_data.append({"time": time_str, "value": float(row['Volume']), "color": vol_color + '80'})

                            if pd.notna(row['SMA21']): sma21_data.append({"time": time_str, "value": float(row['SMA21'])})
                            if pd.notna(row['SMA50']): sma50_data.append({"time": time_str, "value": float(row['SMA50'])})
                            if pd.notna(row['SMA200']): sma200_data.append({"time": time_str, "value": float(row['SMA200'])})

                        chartOptions = {
                            "width": 1200, "height": 700,
                            "layout": { "textColor": 'white', "background": { "type": 'solid', "color": '#0E1117' } },
                            "watermark": { "visible": True, "fontSize": 140, "horzAlign": 'center', "vertAlign": 'center', "color": 'rgba(255, 255, 255, 0.06)', "text": selected_ticker },
                            "rightPriceScale": { "scaleMargins": { "top": 0.05, "bottom": 0.25 }, "borderColor": '#30363D' },
                            "leftPriceScale": { "visible": False, "scaleMargins": { "top": 0.8, "bottom": 0 } },
                            "grid": { "vertLines": {"color": '#1C2128'}, "horzLines": {"color": '#1C2128'} },
                            "crosshair": { "mode": 0 },
                            "timeScale": { "borderColor": '#30363D' }
                        }

                        series_list = [
                            { "type": 'Candlestick', "data": candles, "options": { "upColor": '#26a69a', "downColor": '#ef5350', "borderVisible": False, "wickUpColor": '#26a69a', "wickDownColor": '#ef5350' } },
                            { "type": 'Histogram', "data": volume_data, "options": { "priceFormat": { "type": 'volume' }, "priceScaleId": 'left' } },
                            { "type": 'Line', "data": sma21_data, "options": { "color": "#1053e6", "lineWidth": 2, "title": 'SMA 21' } },
                            { "type": 'Line', "data": sma50_data, "options": { "color": "#14b11c", "lineWidth": 2, "title": 'SMA 50' } },
                            { "type": 'Line', "data": sma200_data, "options": { "color": '#d50000', "lineWidth": 2, "title": 'SMA 200' } }
                        ]

                        spacer1, chart_col, spacer2 = st.columns([1, 10, 1])
                        with chart_col:
                            renderLightweightCharts([{"chart": chartOptions, "series": series_list}], 'chart')
                        
                except Exception as e:
                    st.error(f"שגיאה בטעינת הגרף: {e}")

    # ==========================================
    # 🌊 תנועת כסף סקטוריאלית (IBD Group Ranking)
    # ==========================================
    st.markdown("---")
    st.markdown("### 🌊 MACRO: SECTOR VELOCITY (IBD RANKING)")
    macro_col1, macro_col2 = st.columns(2)
    
    with macro_col1:
        if not group_df.empty:
            top_industries = group_df[['Industry Group Name', 'Rank this Wk', 'Rank_Improvement']].sort_values(by='Rank this Wk', ascending=True).head(40)
            st.caption(f"🏆 LEADERS: TOP 40 IBD INDUSTRY GROUPS", unsafe_allow_html=True)
            st.dataframe(top_industries, use_container_width=True, hide_index=True, height=350)
        else:
            st.info("נתוני Group Ranking לא חושבו. בדוק את תיבת ה-X-Ray למעלה.")

    with macro_col2:
        if not group_df.empty and 'Rank_Improvement' in df_raw.columns:
            top_20_jumping_industries = group_df.sort_values(by='Rank_Improvement', ascending=False).head(20)
            jumpers_display = df_raw[df_raw['Industry Group Name'].isin(top_20_jumping_industries['Industry Group Name'])]
            jumpers_display = jumpers_display[jumpers_display['RS Rating'] >= 70] 
            jumpers_display = jumpers_display.sort_values(by=['Rank_Improvement', 'RS Rating'], ascending=[False, False])
            
            st.caption(f"🚀 MOMENTUM: TOP STOCKS IN JUMPING GROUPS <span class='counter-badge'>({len(jumpers_display)} STOCKS)</span>", unsafe_allow_html=True)
            st.dataframe(
                jumpers_display[['Industry Group Name', 'Rank_Improvement', 'TV_Link', 'RS Rating']], 
                use_container_width=True, hide_index=True, height=350,
                column_config={
                    "Industry Group Name": st.column_config.TextColumn("INDUSTRY"),
                    "Rank_Improvement": st.column_config.NumberColumn("JUMP"),
                    "TV_Link": st.column_config.LinkColumn("SYM 🔗", display_text=r"symbol=(.*)"),
                    "RS Rating": st.column_config.ProgressColumn("RS RATING", format="%d", min_value=0, max_value=99)
                }
            )
        else:
            st.info("נתוני הקופצים תלויים בקובץ ה-Group Ranking.")

    # ==========================================
    # 📥 ייצוא לאקסל
    # ==========================================
    st.markdown("---")
    def to_excel_with_links(df):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Live Filtered Grid')
            workbook = writer.book
            worksheet = writer.sheets['Live Filtered Grid']
            link_format = workbook.add_format({'font_color': 'blue', 'underline': 1, 'bold': True})
            
            if 'TV_Link' in df.columns:
                col_idx = df.columns.get_loc('TV_Link')
                worksheet.set_column(col_idx, col_idx, 15) 
                for row_idx, url in enumerate(df['TV_Link']):
                    if pd.notna(url) and isinstance(url, str) and "symbol=" in url:
                        sym = url.split("symbol=")[-1]
                        worksheet.write_url(row_idx + 1, col_idx, url, link_format, string=sym)
        return output.getvalue()

    excel_data = to_excel_with_links(strike_zone_df)
    st.download_button(
        label="📥 הורד רשימה עדכנית ל-Excel",
        data=excel_data,
        file_name=f"Hybrid_Strike_Zone_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
