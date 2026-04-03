# 📟 Hybrid Command Center

A professional, automated stock market analysis dashboard integrating TradingView data, IBD ratings, and custom trading algorithms (CAN SLIM & Swing Trading methodologies).

© All rights reserved Noam73nc

---

## 🏗️ System Architecture

The system operates on a decoupled SaaS architecture, ensuring high performance, zero API rate-limiting on the user side, and near real-time data delivery.

1. **Backend Worker (GitHub Actions):** A cron job runs every 15 minutes, triggering `data_updater.py`. This script fetches live market data from TradingView, merges it with local static files (IBD Ratings, Group Rankings, Earnings), calculates complex metrics (Pattern Badges, Weinstein Stages), and generates compressed `.pkl` snapshots.
2. **Database (GitHub Repo):** 
The `.pkl` snapshots are pushed back to the `data/` directory in the repository, serving as a lightweight database.
3. **Frontend UI (Streamlit Cloud):** 
The `app.py` dashboard reads the pre-processed `.pkl` files. This allows the app to load instantly and handle multiple concurrent users without executing heavy calculations or API calls.

---

## ✨ Key Features

* **Advanced Filtering:** Filter the market by RS Rating, Dollar Volume, Market Cap, and proprietary Action Scores.
* **Live Pattern Engine:** Automatically detects structural setups (U&R, HVC, VCP, Squat, Stage 2 Advancing) based on live price action.
* **Macro Sector Velocity:** Tracks institutional money flow by analyzing IBD's Top 40 Industry Groups and identifying momentum stocks in jumping sectors.
* **Interactive Charting:** Built-in TradingView Lightweight Charts displaying candlestick data, volume histograms, and key moving averages (21, 50, 200).
* **One-Click Export:** Download the filtered "Strike Zone" directly to an Excel file with hyperlinked tickers.

* Live Market Updates (Automated)
The GitHub Actions workflow is scheduled to run continuously.

To trigger an immediate data refresh: Go to the Actions tab -> Select Update Market Data -> Click Run workflow. 

App Refresh
Users can pull the latest data from the server instantly by clicking the "📡 Refresh data view" button in the Streamlit sidebar.

⚠️ Disclaimer
For informational purposes only. This is not financial advice or a recommendation to buy/sell securities. Data is aggregated from third-party sources. The user assumes full responsibility for all trading decisions.

© All rights reserved Noam73nc
