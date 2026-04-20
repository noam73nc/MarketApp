# data_updater.py
import pandas as pd
import numpy as np
import os
import glob
import json
from datetime import datetime
from tradingview_screener import Query, Column
from scipy.signal import find_peaks
import yfinance as yf

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
    if df.empty:
        raise ValueError("Dataframe is completely empty.")

    min_stocks = 2500
    if len(df) < min_stocks:
        raise ValueError(f"Too few stocks processed ({len(df)}). Expected at least {min_stocks}. Possible API throttling.")

    critical_cols = ['Symbol', 'Price', 'Rel_Volume']
    missing = [c for c in critical_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing absolute critical columns: {', '.join(missing)}")

def is_true_vcp(hist_df):
    if len(hist_df) < 60: 
        return False
        
    highs = hist_df['High'].values
    lows = hist_df['Low'].values
    vols = hist_df['Volume'].values
    closes = hist_df['Close'].values
    
    peaks, _ = find_peaks(highs, distance=7)
    if len(peaks) < 2:
        return False 
        
    contractions = []
    for i in range(len(peaks)):
        peak_idx = peaks[i]
        peak_price = highs[peak_idx]
        
        end_idx = peaks[i+1] if i + 1 < len(peaks) else len(highs) - 1
        if peak_idx >= end_idx:
            continue
            
        trough_price = np.min(lows[peak_idx:end_idx+1])
        drawdown = ((peak_price - trough_price) / peak_price) * 100
        contractions.append(drawdown)
        
    if len(contractions) < 2 or len(contractions) > 5:
        return False
        
    for i in range(len(contractions) - 1):
        if contractions[i+1] > contractions[i] * 1.10: 
            return False 
            
    if contractions[0] > 35: 
        return False
    final_contraction = contractions[-1]
    if final_contraction > 10: 
        return False
        
    recent_vol = np.mean(vols[-10:])
    avg_vol = np.mean(vols[-50:])
    if recent_vol > avg_vol * 0.8: 
        return False
        
    last_peak_idx = peaks[-1]
    pivot_price = highs[last_peak_idx]
    current_price = closes[-1]
    
    if current_price < pivot_price * 0.95 or current_price > pivot_price * 1.02:
        return False
        
    return True

def update_market_data():
    run_status = "success"
    error_msg = ""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🚀 מתחיל משיכת נתונים ועדכון מערכת...")
    
    try:
        # --- חלק 1: משיכת נתוני בסיס מ-TradingView ---
        print("📡 מתחבר ל-TradingView...")
        query = (Query()
                 .set_markets('america')
                 .select('name','type', 'close', 'open', 'high', 'low', 'change', 'volume', 'average_volume_10d_calc', 
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

        df_raw['Rel_Volume'] = np.where(df_raw['TV_AvgVol10'] > 0, df_raw['TV_Volume'] / df_raw['TV_AvgVol10'], 0)
        df_raw['Spread'] = df_raw['high'] - df_raw['low']
        df_raw['Close_Pos'] = np.where(df_raw['Spread'] > 0, (df_raw['Price'] - df_raw['low']) / df_raw['Spread'], 0.5)
        df_raw['ADR_Pct'] = np.where(df_raw['low'] > 0, (df_raw['ATR'] / df_raw['low']) * 100, 0)
        
        df_raw['SMA20_Pct'] = np.where(pd.to_numeric(df_raw['SMA20'], errors='coerce') > 0, 
                                      (df_raw['Price'] - df_raw['SMA20']) / df_raw['SMA20'], 0)
        df_raw['SMA50_Pct'] = np.where(pd.to_numeric(df_raw['SMA50'], errors='coerce') > 0, 
                                      (df_raw['Price'] - df_raw['SMA50']) / df_raw['SMA50'], 0)

        # --- מנוע תבניות בסיסי (Pattern Engine) ---
        def get_patterns(row):
            b = []
            p = pd.to_numeric(row.get('Price', 0), errors='coerce')
            op = pd.to_numeric(row.get('open', 0), errors='coerce')
            hi = pd.to_numeric(row.get('high', 0), errors='coerce')
            lo = pd.to_numeric(row.get('low', 0), errors='coerce')
            change_val = pd.to_numeric(row.get('change', 0), errors='coerce')
            rvol = pd.to_numeric(row.get('Rel_Volume', 1), errors='coerce')
            atr_val = pd.to_numeric(row.get('ATR', 0), errors='coerce')
            adr = pd.to_numeric(row.get('ADR_Pct', 0), errors='coerce')
            sma10 = pd.to_numeric(row.get('SMA10', 0), errors='coerce')
            sma20 = pd.to_numeric(row.get('SMA20', 0), errors='coerce')
            sma50 = pd.to_numeric(row.get('SMA50', 0), errors='coerce')
            sma200 = pd.to_numeric(row.get('SMA200', 0), errors='coerce')
            spread = pd.to_numeric(row.get('Spread', 0), errors='coerce')
            cp = pd.to_numeric(row.get('Close_Pos', 0.5), errors='coerce')
            perf3 = pd.to_numeric(row.get('Perf.3M', 0), errors='coerce') / 100.0 if pd.notna(row.get('Perf.3M')) else 0
            h52 = pd.to_numeric(row.get('price_52_week_high', 0), errors='coerce')
            h52p = (p - h52) / h52 if pd.notna(h52) and h52 > 0 else -99

            if pd.isna(p) or p <= 0: return ""

            if pd.notna(change_val) and change_val != 0:
                prev_close = p / (1 + (change_val / 100.0))
                if prev_close > 0:
                    gap_pct = ((op - prev_close) / prev_close) * 100
                    if gap_pct >= 10.0: b.append("EP 🚀")
                    elif gap_pct >= 4.0: b.append("Gap 📈")

            if pd.notna(atr_val) and atr_val > 0:
                adr_ratio = spread / atr_val
                if adr_ratio >= 2.0: b.append("2 ADR 🔥")
                elif adr_ratio >= 1.5: b.append("1.5 ADR 📏")

            if sma50 > 0 and lo < sma50 < p: b.append("U&R(50) 🛡️")
            if sma20 > 0 and lo < sma20 < p: b.append("U&R(21) 🛡️")
            if sma50 > 0 and (0.0 <= (p - sma50) / sma50 <= 0.03) and p > sma200: b.append("Bounce50 🏀")
            if sma20 > 0 and sma50 > 0 and (0.0 <= (p - sma20) / sma20 <= 0.035) and sma20 > sma50: b.append("Ride20 🏄")
            if rvol > 1.5 and p > op and cp > 0.7: b.append("HVC 🚀")
            if rvol > 1.2 and adr > 0 and (spread / lo * 100 if lo > 0 else 0) > adr and cp < 0.4: b.append("SQUAT 🏋️")
            if atr_val > 0 and spread < (atr_val * 0.7) and cp > 0.5: b.append("ID 🕯️")
            if perf3 > 0.90 and h52p >= -0.20: b.append("HTF 🚩")
            if adr > 0 and (spread / lo * 100 if lo > 0 else adr) < (adr * 0.6) and rvol < 1.0: b.append("Tight 🤏")
            if h52p >= -0.02: b.append("52W High 👑")
            if sma10 > 0 and (p / sma10 - 1) > 0.15: b.append("EXT ⚠️")
            
            return "  ".join(b)

        df_raw['Pattern_Badges'] = df_raw.apply(get_patterns, axis=1)

        # --- Weinstein Stages ---
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

        # --- שילוב קובצי IBD וקבוצות תעשייה מקומיים ---
        print("📁 מחפש ומשלב קבצי IBD ו-Group Ranking מקומיים...")
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
            
        # --- משיכת נתונים משלימים מאקסל (דוחות, קינטיק סלופ ועוד) ---
        print("📄 מושך נתוני דוחות ושיפוע מתוך האקסל המקומי...")
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
            
        # --- מנוע Action Score דינמי ---
        if 'Action_Score' not in df_raw.columns:
            base_score = pd.to_numeric(df_raw.get('RS Rating', 0), errors='coerce').fillna(0)
            stage_bonus = np.where(df_raw['Weinstein_Stage'].astype(str).str.contains('Stage 2'), 10, 0)
            pattern_bonus = df_raw['Pattern_Badges'].str.count(r'🚀|🛡️|🤏|📈|🔥|🏀|🏄') * 5
            pattern_bonus = pattern_bonus.fillna(0)
            penalty = np.where(df_raw['Pattern_Badges'].astype(str).str.contains('🏋️|⚠️'), -5, 0)
            
            df_raw['Action_Score'] = base_score + stage_bonus + pattern_bonus + penalty
            df_raw['Action_Score'] = df_raw['Action_Score'].round().astype(int)        

        # =======================================================
        # 🧠 מנוע היסטוריה משולב ומוגן: VCP + Pocket Pivots (Batching)
        # =======================================================
        print("\n🔍 מכין מנוע היסטוריה (חישוב PP ו-VCP)...")
        
        df_raw['PP_30d'] = 0 # אתחול העמודה ב-0 לכולן
        df_raw['RS_Num'] = pd.to_numeric(df_raw.get('RS Rating', 0), errors='coerce').fillna(0)
            
        # סינון המניות הרלוונטיות לבדיקה
        analysis_candidates = df_raw[
            (df_raw['RS_Num'] >= 70) & 
            (df_raw['TV_AvgVol10'] >= 200000)
        ]['Symbol'].dropna().unique().tolist()
        
        vcp_strict_list = df_raw[
            (df_raw['Weinstein_Stage'].astype(str).str.contains('Stage 2')) & 
            (df_raw['RS_Num'] >= 80)
        ]['Symbol'].unique().tolist()

        if not analysis_candidates:
            print("⚠️ אין מניות שעומדות בתנאי הבסיס להורדת היסטוריה (RS>70 וכו').")
        else:
            print(f"⏳ מוריד היסטוריית 6 חודשים עבור {len(analysis_candidates)} מניות מ-yfinance...")
            print("   הערה: חילקנו את הבקשה לקבוצות קטנות כדי ש-Yahoo לא יחסום אותנו.")
            
            true_vcp_tickers = []
            pp_results = {}
            success_count = 0
            
            batch_size = 50 # גודל הקבוצה - מונע קריסות של Yahoo
            total_batches = (len(analysis_candidates) // batch_size) + 1
            
            for i in range(0, len(analysis_candidates), batch_size):
                batch_tickers = analysis_candidates[i:i+batch_size]
                current_batch = (i // batch_size) + 1
                print(f"   📥 מוריד ומעבד קבוצה {current_batch} מתוך {total_batches}...")
                
                try:
                    hist_data = yf.download(batch_tickers, period="6mo", group_by='ticker', auto_adjust=True, progress=False)
                    
                    if hist_data.empty:
                        print("   ❌ קבוצה זו חזרה ריקה מ-Yahoo, ממשיך לקבוצה הבאה.")
                        continue
                        
                    for ticker in batch_tickers:
                        try:
                            # 1. חילוץ בטוח של הנתונים למניה הספציפית
                            if len(batch_tickers) == 1:
                                df_ticker = hist_data.dropna(subset=['Close']).copy()
                            else:
                                if ticker not in hist_data:
                                    continue # yfinance החסיר את המניה
                                df_ticker = hist_data[ticker].dropna(subset=['Close']).copy()
                                
                            if df_ticker.empty or len(df_ticker) < 50:
                                continue

                            # 2. חישוב Pocket Pivot
                            df_ticker['SMA50'] = df_ticker['Close'].rolling(window=50).mean()
                            is_green = df_ticker['Close'] > df_ticker['Open']
                            above_sma50 = df_ticker['Close'] > df_ticker['SMA50']
                            
                            # שימוש נטיבי ב-Pandas כדי לא לאבד את התאריכים (Index)
                            down_volume = df_ticker['Volume'].where(df_ticker['Close'] < df_ticker['Open'], 0)
                            highest_down_vol_10d = down_volume.rolling(window=10).max().shift(1)
                            
                            vol_breakout = df_ticker['Volume'] > highest_down_vol_10d
                            
                            is_pp = is_green & above_sma50 & vol_breakout
                            pp_count_30d = int(is_pp.rolling(window=30).sum().fillna(0).iloc[-1])
                            
                            pp_results[ticker] = pp_count_30d
                            success_count += 1
                            
                            # 3. בדיקת VCP
                            if ticker in vcp_strict_list:
                                if is_true_vcp(df_ticker):
                                    true_vcp_tickers.append(ticker)
                                    
                        except Exception as e:
                            print(f"      ⚠️ שגיאת חישוב נקודתית במניה {ticker}: {e}")
                            continue
                except Exception as e:
                    print(f"   ❌ שגיאה בהורדת קבוצה {current_batch}: {e}")
                    
            # --- עדכון הטבלה הראשית ---
            print(f"\n✅ מנוע היסטוריה סיים! חושבו מדדי PP בהצלחה עבור {success_count} מניות.")
            
            if pp_results:
                df_raw['PP_30d'] = df_raw['Symbol'].map(pp_results).fillna(0).astype(int)
                
            if true_vcp_tickers:
                print(f"🎯 בינגו! נמצאו {len(true_vcp_tickers)} מניות True VCP: {true_vcp_tickers}")
                df_raw['Pattern_Badges'] = np.where(
                    df_raw['Symbol'].isin(true_vcp_tickers),
                    df_raw['Pattern_Badges'] + "  👑 True VCP",
                    df_raw['Pattern_Badges']
                )
                df_raw['Action_Score'] = np.where(
                    df_raw['Symbol'].isin(true_vcp_tickers),
                    df_raw['Action_Score'] + 15,
                    df_raw['Action_Score']
                )

        if 'RS_Num' in df_raw.columns:
            df_raw.drop(columns=['RS_Num'], inplace=True)

        print("\n🔍 מריץ אימות נתונים קפדני (Circuit Breaker)...")
        validate_data(df_raw)

        df_raw.to_pickle(os.path.join(DATA_DIR, "market_snapshot.pkl"))
        group_df.to_pickle(os.path.join(DATA_DIR, "group_snapshot.pkl"))
        print(f"✅ אימות עבר! העדכון הסתיים בהצלחה והנתונים נשמרו. עכשיו ניתן לפתוח את האפליקציה.")

    except Exception as e:
        run_status = "failed"
        error_msg = str(e)
        print(f"❌ הריצה נכשלה/נבלמה: {error_msg}")

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
