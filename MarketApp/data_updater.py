# data_updater.py
import pandas as pd
import numpy as np
import os
import glob
import json
from datetime import datetime
from tradingview_screener import Query, Column

DATA_DIR = "data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

def find_file_robust(directory, filename_target):
    if not os.path.exists(directory): return None
    try:
        files = os.listdir(directory)
        target = filename_target.lower().replace(" ", "").strip()
        for f in files:
            if f.lower().replace(" ", "").strip() == target:
                return os.path.join(directory, f)
    except: pass
    return None

def validate_data(df):
    """
    מנוע אימות (Circuit Breaker).
    זורק שגיאה (ValueError) אם הנתונים לא עוברים את בדיקות השפיות הקפדניות.
    """
    if df.empty:
        raise ValueError("Dataframe is completely empty.")

    # 1. מינימום שורות (מניות)
    min_stocks = 2500
    if len(df) < min_stocks:
        raise ValueError(f"Too few stocks processed ({len(df)}). Expected at least {min_stocks}. Possible API throttling.")

    # 2. עמודות חובה
    critical_cols = ['Symbol', 'Price', 'Rel_Volume']
    missing = [c for c in critical_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing absolute critical columns: {', '.join(missing)}")

    # 3. בדיקת ערכים חסרים (Nulls)
    if df['Price'].isnull().mean() > 0.05:
        raise ValueError("Excessive nulls in 'Price' column (> 5%).")

    if 'RS Rating' in df.columns and df['RS Rating'].isnull().mean() > 0.40:
        raise ValueError("Excessive nulls in 'RS Rating' (> 40%). IBD merge likely failed.")

    if 'Action_Score' in df.columns and df['Action_Score'].isnull().mean() > 0.50:
        raise ValueError("Excessive nulls in 'Action_Score' (> 50%). Excel sheet merge likely failed.")

    # 4. בדיקת הזנת אפסים (Zero-rate Check)
    if (df['Rel_Volume'] == 0).mean() > 0.20:
        raise ValueError("Over 20% of stocks have EXACTLY 0 RVOL. Upstream volume feed error suspected.")

def update_market_data():
    run_status = "success"
    error_msg = ""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] מתחיל משיכת נתונים ועדכון...")
    
    try:
        # 1. TradingView Live Data
        query = (Query()
                 .set_markets('america')
                 .select('name','type', 'close', 'open', 'high', 'low', 'volume', 'average_volume_10d_calc', 
                         'market_cap_basic', 'sector', 'industry', 
                         'SMA10', 'SMA20', 'SMA50', 'SMA200', 'price_52_week_high', 'price_52_week_low',
                         'Perf.W', 'Perf.1M', 'Perf.3M', 'Perf.Y', 'ATR')
                 .where(Column('close') > 1, Column('average_volume_10d_calc') > 100000)
                 .limit(10000)) 
        
        count, df_tv = query.get_scanner_data()
        
        if df_tv.empty: 
            raise ValueError("לא התקבלו נתונים מ-TradingView (DataFrame is empty).")
            
        if 'type' in df_tv.columns:
            df_tv = df_tv[df_tv['type'].isin(['stock', 'dr'])]
            
        rename_map = {'ticker': 'Symbol', 'name': 'Company_Name', 'close': 'Price', 'volume': 'TV_Volume', 
                      'average_volume_10d_calc': 'TV_AvgVol10', 'market_cap_basic': 'Market Cap', 
                      'industry': 'Industry Group Name'}
        df_raw = df_tv.rename(columns=rename_map).copy()
        
        df_raw['Symbol'] = df_raw['Symbol'].apply(lambda x: x.split(':')[-1] if isinstance(x, str) and ':' in x else x)
        df_raw['TV_Link'] = "https://www.tradingview.com/chart/?symbol=" + df_raw['Symbol']
        df_raw['Market_Cap_B'] = pd.to_numeric(df_raw['Market Cap'], errors='coerce') / 1_000_000_000.0
        df_raw['Dollar_Volume_M'] = (df_raw['Price'] * df_raw['TV_AvgVol10']) / 1_000_000.0

        # 2. Live Pattern Engine
        df_raw['Rel_Volume'] = np.where(df_raw['TV_AvgVol10'] > 0, df_raw['TV_Volume'] / df_raw['TV_AvgVol10'], 0)
        df_raw['Spread'] = df_raw['high'] - df_raw['low']
        df_raw['Close_Pos'] = np.where(df_raw['Spread'] > 0, (df_raw['Price'] - df_raw['low']) / df_raw['Spread'], 0.5)
        df_raw['ADR_Pct'] = np.where(df_raw['low'] > 0, (df_raw['ATR'] / df_raw['low']) * 100, 0)
        
        df_raw['SMA20_Pct'] = np.where(pd.to_numeric(df_raw['SMA20'], errors='coerce') > 0, 
                                      (df_raw['Price'] - df_raw['SMA20']) / df_raw['SMA20'], 0)
        df_raw['SMA50_Pct'] = np.where(pd.to_numeric(df_raw['SMA50'], errors='coerce') > 0, 
                                      (df_raw['Price'] - df_raw['SMA50']) / df_raw['SMA50'], 0)

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
            if adr > 0 and (spread / lo * 100 if lo > 0 else adr) < (adr * 0.6) and rvol < 1.0: b.append("Tight 🤏")
            if h52p >= -0.02: b.append("52W High 👑")
            if sma10 > 0 and (p / sma10 - 1) > 0.15: b.append("EXT ⚠️")
            return "  ".join(b)

        df_raw['Pattern_Badges'] = df_raw.apply(get_patterns, axis=1)

        # 3. Weinstein Stages
        p, ma50, ma200 = df_raw['Price'], df_raw['SMA50'], df_raw['SMA200']
        h52, l52 = df_raw['price_52_week_high'], df_raw['price_52_week_low']
        df_raw['52W_High_Pct'] = np.where(h52 > 0, (p - h52) / h52, -1)
        df_raw['52W_Low_Pct'] = np.where(l52 > 0, (p - l52) / l52, 0)
        
        c2 = (p > ma50) & (ma50 > ma200) & (df_raw['52W_Low_Pct'] >= 0.25) & (df_raw['52W_High_Pct'] >= -0.25)
        c4 = (p < ma50) & (ma50 < ma200)
        c3 = (~c2) & (~c4) & (ma50 >= ma200)
        c1 = (~c2) & (~c4) & (ma50 < ma200)

        df_raw['Weinstein_Stage'] = np.select(
            [c2, c4, c3, c1], 
            ['Stage 2 🚀 Adv', 'Stage 4 📉 Dec', 'Stage 3 ⚠️ Top', 'Stage 1 🏗️ Base'], 
            default='Unknown'
        )

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
            except Exception as e: print(f"❌ שגיאת IBD: {e}")

        group_df = pd.DataFrame()
        group_p = find_file_robust(DATA_DIR, "Group Ranking.csv")
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
            except Exception as e: print(f"❌ שגיאת Group: {e}")

        if not df_ibd.empty and not group_df.empty:
            df_ibd = pd.merge(df_ibd, group_df[['Rank this Wk', 'Rank_Improvement', 'Industry Group Name']], 
                              left_on='Industry Group Rank', right_on='Rank this Wk', how='left')

        if not df_ibd.empty:
            if 'Industry Group Name' in df_raw.columns and 'Industry Group Name' in df_ibd.columns: 
                df_raw = df_raw.drop(columns=['Industry Group Name'])
            icols = ['Symbol', 'RS Rating', 'Comp. Rating', 'EPS Rating', 'Acc/Dis Rating', 'SMR Rating', 
                    'Spon Rating', 'Ind Grp RS', 'Industry Group Rank', 'Rank_Improvement', 'Industry Group Name']
            df_raw = pd.merge(df_raw, df_ibd[[c for c in icols if c in df_ibd.columns]], on='Symbol', how='left')
        
        ex_p = glob.glob(os.path.join(DATA_DIR, "Ultimate_Market_V3f_*.xlsx"))
        if ex_p:
            try:
                latest_excel = max(ex_p, key=os.path.getmtime)
                edfx = pd.read_excel(latest_excel, sheet_name='Full Raw Data')
                cols_to_merge = ['Symbol', 'Earnings_Date', 'Kinetic_Slope', 'VDU_Alert', 'Industry Group Name', 'Action_Score']
                available_cols = [c for c in cols_to_merge if c in edfx.columns]
                
                if 'Symbol' in available_cols:
                    df_raw = pd.merge(df_raw, edfx[available_cols], on='Symbol', how='left', suffixes=('', '_excel'))
                    if 'Industry Group Name_excel' in df_raw.columns:
                        df_raw['Industry Group Name'] = df_raw['Industry Group Name_excel'].combine_first(df_raw['Industry Group Name'])
                        df_raw.drop(columns=['Industry Group Name_excel'], inplace=True)
            except Exception as e: print(f"❌ שגיאת אקסל: {e}")

        # --- השלב החדש: אימות קפדני (Strict Validation) לפני שמירה ---
        print("🔍 מריץ אימות נתונים קפדני (Circuit Breaker)...")
        validate_data(df_raw)

        # נשמור נתונים רק אם עברנו את האימות (לא נזרקה שגיאה)
        df_raw.to_pickle(os.path.join(DATA_DIR, "market_snapshot.pkl"))
        group_df.to_pickle(os.path.join(DATA_DIR, "group_snapshot.pkl"))
        print(f"✅ אימות עבר! העדכון הסתיים בהצלחה והנתונים נשמרו.")

    except Exception as e:
        # אם האימות נכשל, אנחנו מגיעים לכאן. הנתונים הישנים מוגנים!
        run_status = "failed"
        error_msg = str(e)
        print(f"❌ הריצה נכשלה/נבלמה: {error_msg}")

    # --- יצירת קובץ Manifest ---
    finally:
        manifest_data = {
            "last_updated": datetime.now().isoformat(),
            "status": run_status,
            "error_message": error_msg,
            "total_stocks_processed": len(df_raw) if 'df_raw' in locals() and not df_raw.empty else 0,
            "columns_available": list(df_raw.columns) if 'df_raw' in locals() and not df_raw.empty else []
        }
        with open(os.path.join(DATA_DIR, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=4)

if __name__ == "__main__":
    update_market_data()
