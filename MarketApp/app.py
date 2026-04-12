# app.py
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from streamlit_lightweight_charts import renderLightweightCharts
import data_manager
from datetime import datetime

# --- הגדרות עמוד ועיצוב Space Command ---
st.set_page_config(page_title="Hybrid Command Center", layout="wide", page_icon="📟")

# --- מערכת אבטחה (שומר סף) ---
def check_password():
    """מחזיר True אם המשתמש הזין את הסיסמה הנכונה."""
    def password_entered():
        # כאן אתה מגדיר את הסיסמה שתיתן לחברים! 
        if st.session_state["password"] == "StrikeZone2026":
            st.session_state["password_correct"] = True
            del st.session_state["password"] # מחיקת הסיסמה מהזיכרון מטעמי אבטחה
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.markdown("<h3 style='text-align: center; color: #00E5FF;'>🔒 אנא הזן סיסמת גישה למערכת</h3>", unsafe_allow_html=True)
        st.text_input("", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.markdown("<h3 style='text-align: center; color: #00E5FF;'>🔒 אנא הזן סיסמת גישה למערכת</h3>", unsafe_allow_html=True)
        st.text_input("", type="password", on_change=password_entered, key="password")
        st.error("😕 סיסמה שגויה, נסה שוב.")
        return False
    return True

# אם הסיסמה לא נכונה, המערכת פשוט תעצור כאן ולא תטען את הנתונים
if not check_password():
    st.stop()

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&display=swap');
    .stApp { background: radial-gradient(circle at 50% 0%, #152238 0%, #0B0F19 100%); color: #8AB4F8; font-family: 'Rajdhani', sans-serif; }
    .block-container { padding-top: 1.5rem; padding-bottom: 1.5rem; direction: rtl; max-width: 98%; }
    h1, h2, h3, h4 { color: #00E5FF !important; text-transform: uppercase; letter-spacing: 2px; font-weight: 600; text-shadow: 0 0 10px rgba(0, 229, 255, 0.2); }
    h1 { border-bottom: 1px solid rgba(0, 229, 255, 0.4); padding-bottom: 15px; }
    [data-testid="stSidebar"] { background-color: rgba(11, 15, 25, 0.6) !important; border-left: 1px solid rgba(0, 229, 255, 0.1); backdrop-filter: blur(12px); }
    .stButton>button { background-color: rgba(0, 229, 255, 0.05) !important; border: 1px solid #00E5FF !important; color: #00E5FF !important; border-radius: 4px !important; text-transform: uppercase; letter-spacing: 1px; font-weight: 600; transition: all 0.3s ease; box-shadow: 0 0 10px rgba(0, 229, 255, 0.1); width: 100%; }
    .stButton>button:hover { background-color: #00E5FF !important; color: #0B0F19 !important; box-shadow: 0 0 20px rgba(0, 229, 255, 0.6); transform: translateY(-2px); }
    .stSelectbox div[data-baseweb="select"] > div, .stMultiSelect div[data-baseweb="select"] > div { background-color: rgba(16, 25, 43, 0.8) !important; border: 1px solid #4DD0E1 !important; color: #00E5FF !important; border-radius: 4px; }
    [data-testid="stDataFrame"] { border: 1px solid rgba(0, 229, 255, 0.2); border-radius: 6px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
    </style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=900)
def fetch_ui_data():
    return data_manager.get_ui_data()

df_raw, df_grp, manifest = fetch_ui_data()

if df_raw.empty:
    st.error("לא נמצאו נתונים כלל. ודא ש-data_updater.py רץ בהצלחה.")
    st.stop()

run_status = manifest.get("status", "unknown")
error_msg = manifest.get("error_message", "Unknown error")
last_updated_raw = manifest.get("last_updated", "")
try:
    last_updated = datetime.fromisoformat(last_updated_raw).strftime("%Y-%m-%d %H:%M:%S")
except:
    last_updated = "לא ידוע"

with st.sidebar:
    st.header("⚙️ CORE PARAMETERS")
    
    if run_status == "failed":
        st.error(f"⚠️ תקלת שרת בעדכון האחרון!\n\n**סיבה:** {error_msg}")
    else:
        st.success(f"📡 מעודכן ל: {last_updated}")
        
    if st.button("🔄 רענן תצוגת נתונים"):
        st.cache_data.clear()
        st.rerun()
        
    min_rs = st.slider("מינימום RS Rating", 0, 99, 80)
    min_dv = st.number_input("מחזור מסחר מינימלי ($M)", value=5.0)
    min_mc = st.number_input("שווי שוק מינימלי ($B)", value=1.0)
    
    stages = sorted(df_raw['Weinstein_Stage'].dropna().unique())
    selected_stages = st.multiselect("📊 Stage", stages, default=[s for s in stages if "Stage 2" in s])
    
    selected_patterns = st.multiselect("🔍 תבניות מחיר", ["U&R", "HVC", "Tight", "Squat", "VDU", "👑 True VCP", "EP 🚀", "Gap 📈", "1.5 ADR 📏", "2 ADR 🔥"], default=[])

    st.markdown("---")
    st.header("📊 IBD DATA SELECTION")
    ibd_options = ['Comp. Rating', 'EPS Rating', 'Acc/Dis Rating', 'SMR Rating', 'Spon Rating', 'Ind Grp RS']
    available_ibd = [c for c in ibd_options if c in df_raw.columns]
    selected_ibd = st.multiselect("בחר נתוני IBD:", available_ibd, default=[])

df_filtered = df_raw.copy()
if 'RS Rating' in df_filtered.columns:
    df_filtered = df_filtered[pd.to_numeric(df_filtered['RS Rating'], errors='coerce') >= min_rs]
if 'Dollar_Volume_M' in df_filtered.columns:
    df_filtered = df_filtered[pd.to_numeric(df_filtered['Dollar_Volume_M'], errors='coerce') >= min_dv]
if 'Market_Cap_B' in df_filtered.columns:
    df_filtered = df_filtered[pd.to_numeric(df_filtered['Market_Cap_B'], errors='coerce') >= min_mc]
if selected_stages:
    df_filtered = df_filtered[df_filtered['Weinstein_Stage'].isin(selected_stages)]
if selected_patterns:
    pattern_mask = df_filtered['Pattern_Badges'].apply(lambda x: any(p in str(x) for p in selected_patterns))
    df_filtered = df_filtered[pattern_mask]

st.title(f"🚀 STRIKE ZONE: ACTION GRID ({len(df_filtered)} STOCKS)")

for col in ['SMA20_Pct', 'SMA50_Pct']:
    if col in df_filtered.columns:
        df_filtered[col] = pd.to_numeric(df_filtered[col], errors='coerce') * 100

st.markdown("---")

possible_general = [
    'TV_Link', 'Price', 'Rel_Volume', 'Kinetic_Slope', 'RS Rating', 
    'Industry Group Rank', 'Industry Group Name', 'SMA20_Pct', 'SMA50_Pct', 
    'Pattern_Badges', 'Weinstein_Stage', 'Earnings_Date', 'Action_Score',
    'Market_Cap_B', 'ATR', 'ADR_Pct', 'Perf.1M'
]

default_general = [
    'TV_Link', 'Price', 'Rel_Volume', 'Kinetic_Slope', 'RS Rating', 
    'Industry Group Rank', 'Industry Group Name', 'SMA20_Pct', 'SMA50_Pct', 
    'Weinstein_Stage', 'Pattern_Badges', 'Earnings_Date'
]

available_general = [c for c in possible_general if c in df_filtered.columns]

with st.expander("👀 בחירת עמודות כלליות בטבלה", expanded=False):
    selected_general = st.multiselect("סמן עמודות טכניות:", available_general, 
                                     default=[c for c in default_general if c in available_general])

display_final = selected_general + selected_ibd
if 'Action_Score' in df_filtered.columns and 'Action_Score' not in display_final: 
    display_final.insert(0, 'Action_Score')

disp_cols = [c for c in display_final if c in df_filtered.columns]

if 'Action_Score' in df_filtered.columns:
    strike_zone_df = df_filtered[disp_cols].sort_values('Action_Score', ascending=False)
else:
    strike_zone_df = df_filtered[disp_cols]

numeric_cols_to_clean = [
    'Price', 'Rel_Volume', 'Kinetic_Slope', 'RS Rating', 'Industry Group Rank',
    'SMA20_Pct', 'SMA50_Pct', 'Action_Score', 'Market_Cap_B', 'ATR', 'ADR_Pct',
    'Perf.1M', 'Comp. Rating', 'EPS Rating'
]

for col in numeric_cols_to_clean:
    if col in strike_zone_df.columns:
        strike_zone_df[col] = pd.to_numeric(strike_zone_df[col], errors='coerce')

st.dataframe(
    strike_zone_df, 
    use_container_width=True, 
    hide_index=True, 
    height=800,
    column_order=disp_cols,
    column_config={
        "TV_Link": st.column_config.LinkColumn("SYM 🔗", display_text=r"symbol=(.*)"),
        "Price": st.column_config.NumberColumn("PRICE", format="$%.2f"),
        "Rel_Volume": st.column_config.NumberColumn("RVOL 📊", format="%.2f"),
        "Action_Score": st.column_config.NumberColumn("SCORE 🎯", format="%d"),
        "Earnings_Date": st.column_config.TextColumn("דוחות 📅"),
        "Weinstein_Stage": st.column_config.TextColumn("STAGE 📊"),
        "Pattern_Badges": st.column_config.TextColumn("PATTERNS 🔍"),
        "SMA20_Pct": st.column_config.NumberColumn("20MA %", format="%.1f%%"),
        "SMA50_Pct": st.column_config.NumberColumn("50MA %", format="%.1f%%"),
        "Kinetic_Slope": st.column_config.NumberColumn("SLOPE 📈", format="%.2f"),
        "ATR": st.column_config.NumberColumn("ATR ($)", format="%.2f"),
        "ADR_Pct": st.column_config.NumberColumn("ADR %", format="%.2f%%"),
        "Perf.1M": st.column_config.NumberColumn("1M PERF", format="%.1f%%"),
        "Market_Cap_B": st.column_config.NumberColumn("CAP ($B)", format="%.2f"),
        "Industry Group Rank": st.column_config.NumberColumn("GRP RANK 🏆", format="%d"),
        "Industry Group Name": st.column_config.TextColumn("INDUSTRY 🏗️"),
        "RS Rating": st.column_config.ProgressColumn("RS", format="%d", min_value=0, max_value=99),
        "Comp. Rating": st.column_config.ProgressColumn("COMP", format="%d", min_value=0, max_value=99),
        "EPS Rating": st.column_config.ProgressColumn("EPS", format="%d", min_value=0, max_value=99),
        "Acc/Dis Rating": st.column_config.TextColumn("A/D 📈"),
        "SMR Rating": st.column_config.TextColumn("SMR"),
        "Spon Rating": st.column_config.TextColumn("SPON"),
        "Ind Grp RS": st.column_config.TextColumn("GRP RS"),
    }
)

# === מיקום נכון של כפתור הייצוא בסיידבר ===
st.sidebar.markdown("---")
st.sidebar.header("📤 EXPORT DATA")

if not strike_zone_df.empty:
    excel_data = data_manager.export_to_excel(strike_zone_df)
    st.sidebar.download_button(
        label="📥 ייצוא לוח נוכחי לאקסל",
        data=excel_data,
        file_name=f"StrikeZone_Export_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
else:
    st.sidebar.warning("אין נתונים לייצוא (לוח ריק)")

# --- הדיסקליימר וזכויות יוצרים בסיידבר ---
st.sidebar.markdown("<br><br>" * 5, unsafe_allow_html=True)
st.sidebar.markdown("---")
st.sidebar.info("""
**⚠️ (Disclaimer):**
המידע המוצג במערכת זו נועד למטרות לימודיות ואינפורמטיביות בלבד ואינו מהווה המלצה ואו ייעוץ השקעות. המסחר בשוק ההון כרוך בסיכון גבוה. המשתמש נושא באחריות המלאה לכל פעולה שיבצע.
""")
st.sidebar.markdown(f"<div style='text-align: center; font-size: 0.9em; color: #8AB4F8;'>© {datetime.now().year} <b>noam73nc</b>. כל הזכויות שמורות.</div>", unsafe_allow_html=True)

# --- CHARTING ---
st.markdown("---")
st.markdown("### 📈 INTERACTIVE CHARTING")
tks = sorted(df_filtered['Symbol'].dropna().unique()) if 'Symbol' in df_filtered.columns else []

if tks:
    sel_t = st.selectbox("🎯 בחר מניה להצגה (יומי | שנתיים אחורה):", tks)
    with st.spinner(f"מושך נתוני היסטוריה עבור {sel_t}..."):
        try:
            td = yf.download(sel_t, period="2y", interval="1d", progress=False)
            if not td.empty:
                if isinstance(td.columns, pd.MultiIndex): td.columns = td.columns.get_level_values(0)
                td['SMA21'] = td['Close'].rolling(21).mean()
                td['SMA50'] = td['Close'].rolling(50).mean()
                td['SMA200'] = td['Close'].rolling(200).mean()
                
                disp = td.dropna(subset=['Close']) 
                main_data, vols, s21, s50, s200 = [], [], [], [], []
                
                for d, r in disp.iterrows():
                    ts = d.strftime('%Y-%m-%d')
                    main_data.append({"time": ts, "open": float(r['Open']), "high": float(r['High']), "low": float(r['Low']), "close": float(r['Close'])})
                    vols.append({"time": ts, "value": float(r['Volume']), "color": '#26a69a80' if r['Close'] >= r['Open'] else '#ef535080'})
                    if pd.notna(r['SMA21']): s21.append({"time": ts, "value": float(r['SMA21'])})
                    if pd.notna(r['SMA50']): s50.append({"time": ts, "value": float(r['SMA50'])})
                    if pd.notna(r['SMA200']): s200.append({"time": ts, "value": float(r['SMA200'])})
                
                opts = {"height": 700, "layout": {"textColor": '#D1D4DC', "background": {"type": 'solid', "color": '#0B0F19'}},
                        "grid": {"vertLines": {"color": 'rgba(42, 46, 57, 0.5)', "style": 1}, "horzLines": {"color": 'rgba(42, 46, 57, 0.5)', "style": 1}},
                        "watermark": {"visible": True, "fontSize": 120, "text": f"{sel_t} | 1D", "color": 'rgba(255, 255, 255, 0.03)'},
                        "rightPriceScale": {"scaleMargins": {"top": 0.05, "bottom": 0.2}, "borderColor": '#2B2B43'},
                        "leftPriceScale": {"visible": False, "scaleMargins": {"top": 0.85, "bottom": 0}}, "timeScale": {"borderColor": '#2B2B43'}}
                
                c_left, c_main, c_right = st.columns([0.01, 0.98, 0.01])
                with c_main:
                    renderLightweightCharts([{"chart": opts, "series": [
                        {"type": 'Candlestick', "data": main_data, "options": {"upColor": '#26a69a', "downColor": '#ef5350', "borderVisible": False, "wickUpColor": '#26a69a', "wickDownColor": '#ef5350'}},
                        {"type": 'Histogram', "data": vols, "options": {"priceFormat": {"type": 'volume'}, "priceScaleId": 'left'}},
                        {"type": 'Line', "data": s21, "options": {"color": "#1053e6", "lineWidth": 2, "title": 'MA 21'}},
                        {"type": 'Line', "data": s50, "options": {"color": "#14b11c", "lineWidth": 2, "title": 'MA 50'}},
                        {"type": 'Line', "data": s200, "options": {"color": '#FF0000', "lineWidth": 2, "title": 'MA 200'}}
                    ]}], key=f'chart_{sel_t}')
        except: pass
else:
    st.info("אין מניות שעונות על תנאי הסינון. שחרר פילטרים כדי לראות גרף.")

# --- MACRO MOMENTUM ---
st.markdown("---")
if not df_filtered.empty and 'Rank_Improvement' in df_filtered.columns:
    st.markdown("### 🚀 MOMENTUM: TOP STOCKS IN JUMPING GROUPS")
    j_df = df_filtered[df_filtered['Rank_Improvement'] > 0]
    
    if not j_df.empty:
        ideal_cols = ['Industry Group Name', 'Rank_Improvement', 'TV_Link', 'RS Rating']
        exist_cols = [c for c in ideal_cols if c in j_df.columns]
        
        sort_cols = ['Rank_Improvement']
        if 'RS Rating' in exist_cols: 
            sort_cols.append('RS Rating')
        
        st.dataframe(
            j_df[exist_cols].sort_values(sort_cols, ascending=False), 
            use_container_width=True, 
            hide_index=True, 
            height=350,
            column_config={
                "TV_Link": st.column_config.LinkColumn("SYM 🔗", display_text=r"symbol=(.*)"),
                "RS Rating": st.column_config.ProgressColumn("RS", format="%d", min_value=0, max_value=99)
            }
        )
