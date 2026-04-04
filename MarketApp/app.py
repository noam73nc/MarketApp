import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from streamlit_lightweight_charts import renderLightweightCharts
import os

# --- הגדרות עמוד ---
st.set_page_config(page_title="Hybrid Command Center", layout="wide", page_icon="📟")

# --- SPACE COMMAND CSS (עיצוב טרמינל עתידני) ---
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

    /* 5. כפתורים */
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

    /* 7. טבלאות הנתונים */
    [data-testid="stDataFrame"] {
        border: 1px solid rgba(0, 229, 255, 0.2);
        border-radius: 6px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    
    /* 8. התראות ואזהרות */
    .stWarning, .stAlert, .stInfo {
        background: rgba(255, 0, 255, 0.05) !important;
        border: 1px solid #FF00FF !important;
        color: #E040FB !important;
        border-radius: 6px;
        backdrop-filter: blur(4px);
    }
    </style>
    """, unsafe_allow_html=True)

# --- משיכת הנתונים (DATABASE) ---
@st.cache_data(ttl=900) # שמירת נתונים בזיכרון ל-15 דקות
def load_data():
    try:
        df = pd.read_pickle('data/market_snapshot.pkl')
        grp = pd.read_pickle('data/group_snapshot.pkl')
        return df, grp
    except Exception as e:
        return pd.DataFrame(), pd.DataFrame()

df_raw, df_grp = load_data()

if df_raw.empty:
    st.error("לא נמצאו נתונים. ודא שהבוט בגיטהאב סיים לרוץ ושקובץ ה-PKL קיים בתיקיית data.")
    st.stop()

# --- תפריט צד (SIDEBAR FILTERS) ---
with st.sidebar:
    st.header("⚙️ CORE PARAMETERS")
    if st.button("📡 רענן נתונים"):
        st.cache_data.clear()
        st.rerun()
        
    min_rs = st.slider("מינימום RS Rating", 0, 99, 80)
    min_dv = st.number_input("מחזור מסחר מינימלי (במיליונים)", value=5.0, step=1.0)
    min_mc = st.number_input("שווי שוק מינימלי (במיליארדים)", value=1.0, step=0.5)
    
    stages = sorted(df_raw['Weinstein_Stage'].dropna().unique())
    selected_stages = st.multiselect("📊 Stage", stages, default=[s for s in stages if "Stage 2" in s])
    
    # סינון תבניות (אם קיים)
    if 'Pattern_Badges' in df_raw.columns:
        selected_patterns = st.multiselect("🔍 תבניות מחיר", ["U&R", "HVC", "VCP", "Squat", "VDU"], default=[])
    else:
        selected_patterns = []

# --- הפעלת הסינונים (FILTER LOGIC) ---
df_filtered = df_raw.copy()
if 'RS Rating' in df_filtered.columns:
    df_filtered = df_filtered[pd.to_numeric(df_filtered['RS Rating'], errors='coerce') >= min_rs]
if 'Dollar_Volume_M' in df_filtered.columns:
    df_filtered = df_filtered[pd.to_numeric(df_filtered['Dollar_Volume_M'], errors='coerce') >= min_dv]
if 'Market_Cap_B' in df_filtered.columns:
    df_filtered = df_filtered[pd.to_numeric(df_filtered['Market_Cap_B'], errors='coerce') >= min_mc]
if selected_stages and 'Weinstein_Stage' in df_filtered.columns:
    df_filtered = df_filtered[df_filtered['Weinstein_Stage'].isin(selected_stages)]
    
if selected_patterns and 'Pattern_Badges' in df_filtered.columns:
    pattern_mask = df_filtered['Pattern_Badges'].apply(lambda x: any(p in str(x) for p in selected_patterns))
    df_filtered = df_filtered[pattern_mask]

# ==========================================
# MAIN DASHBOARD AREA
# ==========================================
st.title("🚀 STRIKE ZONE: ACTION GRID")

# רשימת עמודות רצויות (כולל Rel_Volume שהוספנו)
possible_cols = ['TV_Link', 'Price', 'Rel_Volume', 'RS Rating', 'Comp. Rating', 'EPS Rating', 'Acc/Dis Rating', 'SMR Rating', 
                'Spon Rating', 'Ind Grp RS', 'Rank_Improvement', 'Weinstein_Stage', 'Pattern_Badges', 'VDU_Alert', 'Earnings_Date']
default_cols = ['TV_Link', 'Price', 'Rel_Volume', 'RS Rating', 'Comp. Rating', 'Ind Grp RS', 'Rank_Improvement', 'Weinstein_Stage', 'Pattern_Badges', 'Earnings_Date']

disp_cols = [c for c in default_cols if c in df_filtered.columns]
strike_zone_df = df_filtered[disp_cols]

# טבלה מרכזית מוגדלת ל-800 פיקסלים
st.dataframe(strike_zone_df, use_container_width=True, hide_index=True, height=800,
    column_config={
        "TV_Link": st.column_config.LinkColumn("SYM 🔗", display_text=r"symbol=(.*)"),
        "RS Rating": st.column_config.ProgressColumn("RS", format="%d", min_value=0, max_value=99),
        "Price": st.column_config.NumberColumn("PRICE", format="$%.2f"),
        "Rel_Volume": st.column_config.NumberColumn("RVOL 📊", format="%.2f"),
        "Earnings_Date": st.column_config.TextColumn("דוחות 📅")
    })

# --- CHARTING (גרף מסחר נקי) ---
st.markdown("---")
st.markdown("### 📈 INTERACTIVE CHARTING")
tks = sorted(df_filtered['Symbol'].dropna().unique())

if tks:
    # בחירת מניה בלבד - ללא הסרגל המורכב
    sel_t = st.selectbox("🎯 בחר מניה להצגה (יומי | שנתיים אחורה):", tks)

    with st.spinner(f"מושך נתוני היסטוריה עבור {sel_t}..."):
        try:
            # הגדרות קבועות: שנתיים אחורה, נרות יומיים
            td = yf.download(sel_t, period="2y", interval="1d", progress=False)
            
            if td.empty:
                st.warning(f"⚠️ Yahoo Finance לא החזיר נתונים עבור {sel_t}. ייתכן שמדובר בחסימת רשת.")
            else:
                if isinstance(td.columns, pd.MultiIndex): 
                    td.columns = td.columns.get_level_values(0)
                
                td['SMA21'] = td['Close'].rolling(21).mean()
                td['SMA50'] = td['Close'].rolling(50).mean()
                td['SMA200'] = td['Close'].rolling(200).mean()
                
                disp = td.dropna(subset=['Close']) 
                
                main_data, vols, s21, s50, s200 = [], [], [], [], []
                for d, r in disp.iterrows():
                    ts = d.strftime('%Y-%m-%d')
                    
                    # נרות יפניים בלבד
                    main_data.append({"time": ts, "open": float(r['Open']), "high": float(r['High']), "low": float(r['Low']), "close": float(r['Close'])})
                        
                    vols.append({"time": ts, "value": float(r['Volume']), "color": '#26a69a80' if r['Close'] >= r['Open'] else '#ef535080'})
                    if pd.notna(r['SMA21']): s21.append({"time": ts, "value": float(r['SMA21'])})
                    if pd.notna(r['SMA50']): s50.append({"time": ts, "value": float(r['SMA50'])})
                    if pd.notna(r['SMA200']): s200.append({"time": ts, "value": float(r['SMA200'])})
                
                opts = {
                    "height": 700,
                    "layout": {"textColor": '#D1D4DC', "background": {"type": 'solid', "color": '#0B0F19'}},
                    "grid": {
                        "vertLines": {"color": 'rgba(42, 46, 57, 0.5)', "style": 1},
                        "horzLines": {"color": 'rgba(42, 46, 57, 0.5)', "style": 1}
                    },
                    "watermark": {"visible": True, "fontSize": 120, "text": f"{sel_t} | 1D", "color": 'rgba(255, 255, 255, 0.03)'},
                    "rightPriceScale": {"scaleMargins": {"top": 0.05, "bottom": 0.2}, "borderColor": '#2B2B43'},
                    "leftPriceScale": {"visible": False, "scaleMargins": {"top": 0.85, "bottom": 0}},
                    "timeScale": {"borderColor": '#2B2B43'}
                }
                
                # עיצוב אחיד של נרות יפניים
                series_opts = {"upColor": '#26a69a', "downColor": '#ef5350', "borderVisible": False, "wickUpColor": '#26a69a', "wickDownColor": '#ef5350'}
                
                c_left, c_main, c_right = st.columns([0.01, 0.98, 0.01])
                with c_main:
                    renderLightweightCharts([{"chart": opts, "series": [
                        {"type": 'Candlestick', "data": main_data, "options": series_opts},
                        {"type": 'Histogram', "data": vols, "options": {"priceFormat": {"type": 'volume'}, "priceScaleId": 'left'}},
                        {"type": 'Line', "data": s21, "options": {"color": "#1053e6", "lineWidth": 2, "title": 'MA 21'}},
                        {"type": 'Line', "data": s50, "options": {"color": "#14b11c", "lineWidth": 2, "title": 'MA 50'}},
                        {"type": 'Line', "data": s200, "options": {"color": '#FF0000', "lineWidth": 2, "title": 'MA 200'}}
                    ]}], key=f'chart_{sel_t}')
                    
        except Exception as e:
            st.error(f"שגיאה בהפקת הגרף: {e}")
else:
    st.info("אין מניות שעונות על תנאי הסינון. שחרר פילטרים כדי לראות גרף.")

# --- MACRO MOMENTUM (סקטורים קופצים) ---
st.markdown("---")
if not df_grp.empty and 'Rank_Improvement' in df_grp.columns:
    st.markdown("### 🚀 MOMENTUM: TOP STOCKS IN JUMPING GROUPS")
    j_df = df_grp[df_grp['Rank_Improvement'] > 0]
    if not j_df.empty:
        st.dataframe(j_df[['Industry Group Name', 'Rank_Improvement', 'TV_Link', 'RS Rating']].sort_values(['Rank_Improvement', 'RS Rating'], ascending=False), 
                     use_container_width=True, hide_index=True, height=350,
                     column_config={
                         "TV_Link": st.column_config.LinkColumn("SYM 🔗", display_text=r"symbol=(.*)"),
                         "RS Rating": st.column_config.ProgressColumn("RS", format="%d", min_value=0, max_value=99)
                     })
    else:
        st.info("לא נמצאו סקטורים שקפצו בדירוג השבוע.")
