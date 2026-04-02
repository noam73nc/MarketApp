# 📟 Hybrid Market Terminal: Strike Zone Command Center

A professional, real-time stock market screening and charting terminal built with Python and Streamlit. This application combines live market data, proprietary technical pattern recognition, and institutional-grade fundamental ratings into a single, lightning-fast dashboard.

## 🚀 Core Features

* **Hybrid Data Architecture:** Seamlessly merges live technical data from the **TradingView Screener API** with local, fundamental datasets (like **IBD Ratings**).
* **Live Pattern Engine:** Calculates technical patterns in real-time (e.g., *HVC, U&R, VCP/Tight, SQUAT, 1/2 ADR moves*) based on daily price action and volume.
* **Strict Weinstein Stage Analysis:** Automatically classifies stocks into true Weinstein Stages (1-4) using precise moving average slopes and 52-week high/low proximity.
* **Sector Velocity Tracking:** Monitors Industry Group Rankings to identify "Big Jumpers" and track institutional money flow.
* **Interactive Charting:** Features a massive, native TradingView-style interactive chart (powered by `lightweight-charts`) with dynamic SMAs (21, 50, 200) and volume histograms.
* **Excel Export:** One-click export of the filtered "Action Grid" to Excel, complete with active TradingView hyperlinks.

## 🛠️ Tech Stack
* **UI Framework:** [Streamlit](https://streamlit.io/)
* **Data Sources:** `tradingview-screener`, `yfinance`, Local CSVs (IBD & Group Ranking)
* **Charting:** `streamlit-lightweight-charts`
* **Data Manipulation:** `pandas`, `numpy`

## ⚙️ Installation & Setup

1. Clone the repository:
   ```bash
   git clone [https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git](https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git)
   cd YOUR_REPO_NAME
