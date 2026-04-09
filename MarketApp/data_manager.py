# data_manager.py
import pandas as pd
import json
import os
from datetime import datetime

# מציאת התיקייה שבה יושב הקובץ הזה, וחיפוש תיקיית data בתוכה
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

MANIFEST_PATH = os.path.join(DATA_DIR, "manifest.json")
MARKET_SNAPSHOT_PATH = os.path.join(DATA_DIR, "market_snapshot.pkl")
GROUP_SNAPSHOT_PATH = os.path.join(DATA_DIR, "group_snapshot.pkl")

def get_manifest() -> dict:
    """קורא את קובץ המניפסט כדי להבין את מצב המערכת."""
    if not os.path.exists(MANIFEST_PATH):
        return {"status": "error", "message": "Manifest not found. Backend might not have run yet."}
    
    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"status": "error", "message": f"Failed to read manifest: {str(e)}"}

def load_market_data() -> pd.DataFrame:
    """טוען את נתוני המניות בצורה בטוחה."""
    try:
        if os.path.exists(MARKET_SNAPSHOT_PATH):
            return pd.read_pickle(MARKET_SNAPSHOT_PATH)
    except Exception as e:
        print(f"Error loading market data: {e}")
    return pd.DataFrame()

def load_group_data() -> pd.DataFrame:
    """טוען את נתוני הסקטורים בצורה בטוחה."""
    try:
        if os.path.exists(GROUP_SNAPSHOT_PATH):
            return pd.read_pickle(GROUP_SNAPSHOT_PATH)
    except Exception as e:
        print(f"Error loading group data: {e}")
    return pd.DataFrame()

def get_ui_data():
    """
    פונקציה ייעודית עבור ה-Frontend (app.py).
    מחזירה את טבלאות הנתונים ומחרוזת זמן עדכון מעוצבת להצגה למשתמש.
    """
    manifest = get_manifest()
    last_updated_str = "לא ידוע"
    
    if manifest.get("status") == "success" and "last_updated" in manifest:
        try:
            # המרת זמן השרת לזמן קריא
            dt = datetime.fromisoformat(manifest["last_updated"])
            last_updated_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            pass

    df_market = load_market_data()
    df_group = load_group_data()
    
    return df_market, df_group, last_updated_str

# ==========================================
# הכנה ל-LLM (AI Tooling) בעתיד
# פונקציות שמודל שפה יוכל להפעיל ישירות
# ==========================================
def llm_get_top_stocks(min_score: int = 80, limit: int = 10) -> list:
    """
    LLM Tool: Retrieves the top actionable stocks based on the Action_Score.
    Useful for answering 'What are the best setups right now?'.
    """
    df = load_market_data()
    if df.empty or 'Action_Score' not in df.columns:
        return []
    
    top_df = df[df['Action_Score'] >= min_score].sort_values('Action_Score', ascending=False).head(limit)
    return top_df[['Symbol', 'Price', 'Industry Group Name', 'Action_Score', 'Pattern_Badges']].to_dict('records')
