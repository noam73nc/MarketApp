# app.py
import streamlit as st
import pandas as pd
import numpy as np
import os
import io
from datetime import datetime
import yfinance as yf
from streamlit_lightweight_charts import renderLightweightCharts

# הגדרת נתיב אבסולוטי כדי ש-Streamlit לא ילך לאיבוד בתתי-תיקיות
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

# ==========================================
# ⚙️ הגדרות עמוד ותצורה ו-CSS מותאם
# ==========================================
st.set_page_config(
    page_title="Terminal :: Hybrid Market",
    page_icon="📟",
    layout="wide",
    initial_sidebar_state="expanded" 
)

st.markdown("""
    <style>
    /* 1. יבוא פונט טרמינל עתידני מ-Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&display=swap');

    /* 2. הגדרות מסך ראשי - חלל עמוק */
    .stApp { 
        background: radial-gradient(circle at 50% 0%, #152238 0%, #0B0F19 100%);
        color: #8AB4F8; 
        font-family: 'Rajdhani', sans-serif;
    }
    .block-container { padding-top: 1.5rem; padding-bottom: 1.5rem; direction: rtl; max-width: 98%; }

    /* 3. כותרות - ציאן קרח מואר */
    h1, h2, h3, h4 { 
        color: #00E5FF !important; 
        text-transform: uppercase; 
        letter-spacing: 2px; 
        font-weight: 600;
        text-shadow: 0 0 10px rgba(0, 229, 255, 0.2);
    }
    h1 { border-bottom: 1px solid rgba(0, 229, 255, 0.4); padding-bottom: 15px; }

    /* 4. סיידבר (תפריט צד) - אפקט לוח זכוכית */
    [data-testid="stSidebar"] {
        background-color: rgba(11, 15, 25, 0.6) !important;
        border-left: 1px solid rgba(0, 229, 255, 0.1);
        backdrop-filter: blur(12px);
    }

    /* 5. כפתורים (Space Switches) - כפתור הרענון והייצוא */
    .stButton>button {
        background-color: rgba(0, 229, 255, 0.05) !important;
        border: 1px solid #00E5FF !important;
        color: #00E5FF !important;
        border-radius: 4px !important;
        text-transform: uppercase;
        letter-spacing: 1px;
        font-weight: 600;
        transition: all 0.3s ease;
        box-shadow: 0 0 10px rgba(0, 229, 255, 0.1);
        width: 100%;
    }
    .stButton>button:hover {
        background-color: #00E5FF !important;
        color: #0B0F19 !important;
        box-shadow: 0 0 20px rgba(0, 229, 255, 0.6);
        transform: translateY(-2px);
    }

    /* 6. תיבות טקסט ובחירה (Dropdowns) */
    .stSelectbox div[data-baseweb="select"] > div, 
    .stMultiSelect div[data-baseweb="select"] > div {
        background-color: rgba(16, 25, 43, 0.8) !important;
        border: 1px solid #4DD0E1 !important;
        color: #00E5FF !important;
        border-radius: 4px;
    }

    /* 7. טבלאות הנתונים (DataFrames) */
    [data-testid="stDataFrame"] {
        border: 1px solid rgba(0, 229, 255, 0.2);
        border-radius: 6px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    
    /* 8. התראות ואזהרות (דברים שצריכים לבלוט) - סגול חלל (Magenta) */
    .stWarning, .stAlert, .stInfo {
        background: rgba(255, 0, 255, 0.05) !important;
        border: 1px solid #FF00FF !important;
        color: #E040FB !important;
        border-radius: 6px;
        backdrop-filter: blur(4px);
    }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# ⚠️ דיסקליימר וכפתור רענון בסיידבר
# ==========================================
st.sidebar.markdown("### © כל הזכויות שמורות Noam73nc מידע משפטי וסיכונים")
st.sidebar.info("""
**אין לראות במידע זה המלצה, ייעוץ השקעות, או הצעה לקנייה/מכירה של ניירות ערך.** הנתונים נמשכים ממקורות צד-שלישי. המשתמש נושא באחריות הבלעדית לכל פעולת מסחר.
""")
st.sidebar.markdown("---")

if st.sidebar.button("📡 רענן תצוגת נתונים", type="primary"):
    st.cache_data.clear() 
    st.rerun()

st.sidebar.markdown("---")

# ==========================================
# 📡 קריאת הנתונים מהקבצים המקומיים בלבד
# ==========================================
@st.cache_data(ttl=60, show_spinner=False)
def load_local_data():
    market_path = os.path.join(DATA_DIR, "market_snapshot.pkl")
    group_path = os.path.join(DATA_DIR, "group_snapshot.pkl")
    
    if os.path.exists(market_path) and os.path.exists(group_path):
        try:
            df_raw = pd.read_pickle(market_path)
            group_df = pd.read_pickle(group_path)
            
            # --- התיקון לשעון ישראל ---
            # קורא את הזמן (Epoch), הופך ל-UTC, ואז ממיר לשעון ירושלים
            timestamp = os.path.getmtime(market_path)
            last_mod = pd.to_datetime(timestamp, unit='s', utc=True).tz_convert('Asia/Jerusalem').strftime('%H:%M:%S')
            
            return df_raw, group_df, last_mod
        except Exception as e:
            st.error(f"שגיאה בקריאת הנתונים: {e}")
            return pd.DataFrame(), pd.DataFrame(), None
    return pd.DataFrame(), pd.DataFrame(), None

# ==========================================
# UI Logic
# ==========================================
st.title("📟 HYBRID COMMAND CENTER by noam73nc © ")

df_raw, group_df, last_updated = load_local_data()

if df_raw.empty:
    st.error("⚠️ הנתונים טרם עודכנו בשרת. יש להפעיל את סקריפט העדכון (Worker) תחילה.")
    st.stop()

st.caption(f"⏱️ נתונים מעודכנים לשעה: {last_updated}")

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
                    'Spon Rating', 'Ind Grp RS', 'Rank_Improvement', 'Weinstein_Stage', 'Pattern_Badges', 'VDU_Alert', 'Earnings_Date']
    available_cols = [c for c in possible_cols if c in df_raw.columns]
    default_cols = ['TV_Link', 'Price', 'RS Rating', 'Comp. Rating', 'Ind Grp RS', 'Rank_Improvement', 'Weinstein_Stage', 'Pattern_Badges', 'Earnings_Date']
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
        "RS Rating": st.column_config.ProgressColumn("RS", format="%d", min_value=0, max_value=99),
        "Price": st.column_config.NumberColumn("PRICE", format="$%.2f"),
        "Earnings_Date": st.column_config.TextColumn("דוחות 📅")
    })

# --- CHARTING ---
st.markdown("---")
st.markdown("### 📈 INTERACTIVE CHARTING")
tks = sorted(df_filtered['Symbol'].dropna().unique())

if tks:
    # --- יצירת סרגל הכלים שלנו ב-Streamlit ---
    c_top1, c_top2, c_top3, c_top4 = st.columns([2, 1.5, 1.5, 1.5])
    with c_top1:
        sel_t = st.selectbox("🎯 בחר מניה:", tks)
    with c_top2:
        timeframe = st.selectbox("⏳ טווח זמן:", ["יומי (1D)", "שבועי (1W)"])
    with c_top3:
        chart_type = st.selectbox("📊 תצוגה:", ["נרות יפניים", "קו חלק (Line)"])
    with c_top4:
        history = st.selectbox("📅 היסטוריה:", ["שנתיים (2Y)", "5 שנים (5Y)", "מקסימום (Max)"])

    # תרגום הבחירות לפרמטרים של Yahoo Finance
    interval_map = {"יומי (1D)": "1d", "שבועי (1W)": "1wk"}
    period_map = {"שנתיים (2Y)": "2y", "5 שנים (5Y)": "5y", "מקסימום (Max)": "max"}

    with st.spinner(f"מושך נתוני היסטוריה עבור {sel_t}..."):
        try:
            # משיכת הנתונים עם הטווח והזמן שנבחרו דינמית בסרגל
            td = yf.download(sel_t, period=period_map[history], interval=interval_map[timeframe], progress=False)
            
            if td.empty:
                st.warning(f"⚠️ Yahoo Finance לא החזיר נתונים עבור {sel_t}. ייתכן שמדובר בחסימת רשת.")
            else:
                if isinstance(td.columns, pd.MultiIndex): 
                    td.columns = td.columns.get_level_values(0)
                
                # חישוב ממוצעים نעים
                td['SMA21'] = td['Close'].rolling(21).mean()
                td['SMA50'] = td['Close'].rolling(50).mean()
                td['SMA200'] = td['Close'].rolling(200).mean()
                
                # הסרנו את ההגבלה! מציג כעת את כל ההיסטוריה שנבחרה
                disp = td.dropna(subset=['Close']) 
                
                main_data, vols, s21, s50, s200 = [], [], [], [], []
                for d, r in disp.iterrows():
                    ts = d.strftime('%Y-%m-%d')
                    
                    # בניית הנתונים לפי סוג הגרף שנבחר
                    if chart_type == "נרות יפניים":
                        main_data.append({"time": ts, "open": float(r['Open']), "high": float(r['High']), "low": float(r['Low']), "close": float(r['Close'])})
                    else: # גרף קווי
                        main_data.append({"time": ts, "value": float(r['Close'])})
                        
                    vols.append({"time": ts, "value": float(r['Volume']), "color": '#26a69a80' if r['Close'] >= r['Open'] else '#ef535080'})
                    if pd.notna(r['SMA21']): s21.append({"time": ts, "value": float(r['SMA21'])})
                    if pd.notna(r['SMA50']): s50.append({"time": ts, "value": float(r['SMA50'])})
                    if pd.notna(r['SMA200']): s200.append({"time": ts, "value": float(r['SMA200'])})
                
                # עיצוב הגרף (מותאם אישית לאווירת Space Command)
                opts = {
                    "height": 700,
                    "layout": {"textColor": '#D1D4DC', "background": {"type": 'solid', "color": '#0B0F19'}},
                    "grid": {
                        "vertLines": {"color": 'rgba(42, 46, 57, 0.5)', "style": 1},
                        "horzLines": {"color": 'rgba(42, 46, 57, 0.5)', "style": 1}
                    },
                    "watermark": {"visible": True, "fontSize": 120, "text": f"{sel_t} | {timeframe.split(' ')[0]}", "color": 'rgba(255, 255, 255, 0.03)'},
                    "rightPriceScale": {"scaleMargins": {"top": 0.05, "bottom": 0.2}, "borderColor": '#2B2B43'},
                    "leftPriceScale": {"visible": False, "scaleMargins": {"top": 0.85, "bottom": 0}},
                    "timeScale": {"borderColor": '#2B2B43'}
                }
                
                # הגדרות תצוגה דינמיות לסדרה הראשית
                series_type = 'Candlestick' if chart_type == "נרות יפניים" else 'Line'
                series_opts = {"upColor": '#26a69a', "downColor": '#ef5350', "borderVisible": False, "wickUpColor": '#26a69a', "wickDownColor": '#ef5350'} if chart_type == "נרות יפניים" else {"color": '#00E5FF', "lineWidth": 3}
                
                c_left, c_main, c_right = st.columns([0.01, 0.98, 0.01])
                with c_main:
                    # מפתח ייחודי קריטי כדי שהגרף יתרנדר מחדש כשמשנים טווח זמן
                    renderLightweightCharts([{"chart": opts, "series": [
                        {"type": series_type, "data": main_data, "options": series_opts},
                        {"type": 'Histogram', "data": vols, "options": {"priceFormat": {"type": 'volume'}, "priceScaleId": 'left'}},
                        {"type": 'Line', "data": s21, "options": {"color": "#1053e6", "lineWidth": 2, "title": 'MA 21'}},
                        {"type": 'Line', "data": s50, "options": {"color": "#14b11c", "lineWidth": 2, "title": 'MA 50'}},
                        {"type": 'Line', "data": s200, "options": {"color": '#FF00FF', "lineWidth": 2, "title": 'MA 200'}}
                    ]}], key=f'chart_{sel_t}_{history}_{timeframe}_{chart_type}')
                    
        except Exception as e:
            st.error(f"שגיאה בהפקת הגרף: {e}")
else:
    st.info("אין מניות שעונות על תנאי הסינון. שחרר פילטרים כדי לראות גרף.")

# --- MACRO ---
st.markdown("---")
st.markdown("### 🌊 MACRO: SECTOR VELOCITY")

m1, m2 = st.columns(2)
with m1:
    if not group_df.empty:
        st.caption("🏆 LEADERS: TOP 40 IBD GROUPS")
        # הסינון החדש: מסנן החוצה את ה-0 (המדדים) ולוקח רק דירוגים מ-1 ומעלה
        leaders_df = group_df[group_df['Rank this Wk'] > 0].sort_values('Rank this Wk').head(40)
        st.dataframe(leaders_df, use_container_width=True, hide_index=True, height=350)
    else:
        st.warning("⚠️ טבלת Macro מוסתרת כי הקובץ 'Group Ranking.csv' לא נמצא בתיקיית הנתונים בגיטהאב.")

with m2:
    if not group_df.empty and 'Industry Group Name' in df_raw.columns:
        top_j = group_df.sort_values('Rank_Improvement', ascending=False).head(20)
        j_df = df_raw[df_raw['Industry Group Name'].isin(top_j['Industry Group Name'])]
        st.caption("🚀 MOMENTUM: TOP STOCKS IN JUMPING GROUPS")
        st.dataframe(j_df[['Industry Group Name', 'Rank_Improvement', 'TV_Link', 'RS Rating']].sort_values(['Rank_Improvement', 'RS Rating'], ascending=False), 
                     use_container_width=True, hide_index=True, height=350,
                     column_config={"TV_Link": st.column_config.LinkColumn("SYM 🔗", display_text=r"symbol=(.*)"),
                                   "RS Rating": st.column_config.ProgressColumn("RS", format="%d", min_value=0, max_value=99)})

# --- EXPORT ---
def to_excel(df):
    out = io.BytesIO()
    export_df = df.copy()
    
    if 'TV_Link' in export_df.columns:
        symbols = export_df['TV_Link'].str.extract(r'symbol=(.*)')[0]
        export_df['TV_Link'] = '=HYPERLINK("' + export_df['TV_Link'] + '", "' + symbols + '")'
        
    with pd.ExcelWriter(out, engine='xlsxwriter') as w:
        export_df.to_excel(w, index=False)
    return out.getvalue()

st.sidebar.markdown("### ייצוא נתונים")
st.sidebar.download_button("📥 הורד רשימה ל-Excel", to_excel(strike_zone_df), f"Market_Export_{datetime.now().strftime('%Y%m%d')}.xlsx")
