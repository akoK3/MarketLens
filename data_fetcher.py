import yfinance as yf
import pandas as pd
import numpy as np
import requests
import os
from dotenv import load_dotenv

load_dotenv()

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")

def get_price_data(ticker, period="2y"):
    df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(col).strip() for col in df.columns]
    if df.empty:
        return None
    return df

def calculate_atr(df, window=14):
    high_low = df["High"] - df["Low"]
    high_prev_close = (df["High"] - df["Close"].shift(1)).abs()
    low_prev_close = (df["Low"] - df["Close"].shift(1)).abs()
    true_range = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
    return true_range.ewm(com=window - 1, adjust=False).mean()

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_macd(series, short=12, long=26, signal=9):
    ema_short = series.ewm(span=short, adjust=False).mean()
    ema_long = series.ewm(span=long, adjust=False).mean()
    macd = ema_short - ema_long
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    histogram = macd - signal_line
    return macd, signal_line, histogram

def calculate_volume_ratio(df, window=20):
    avg_volume = df["Volume"].rolling(window).mean()
    return df["Volume"] / avg_volume
def get_macro_indicators():
    try:
        # Yield curve
        ten_year = yf.download("^TNX", period="5d", progress=False, auto_adjust=True)
        two_year = yf.download("^IRX", period="5d", progress=False, auto_adjust=True)
        dxy = yf.download("DX-Y.NYB", period="5d", progress=False, auto_adjust=True)
        
        for df in [ten_year, two_year, dxy]:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
        
        result = {}
        
        if not ten_year.empty and not two_year.empty:
            ten_yr = float(ten_year["Close"].iloc[-1])
            two_yr = float(two_year["Close"].iloc[-1])
            spread = round(ten_yr - two_yr, 3)
            result["yield_curve"] = {
                "ten_year": round(ten_yr, 3),
                "two_year": round(two_yr, 3),
                "spread": spread,
                "inverted": spread < 0
            }
        
        if not dxy.empty:
            result["dxy"] = round(float(dxy["Close"].iloc[-1]), 2)
        
        return result if result else None
    except:
        return None

def get_market_snapshot(ticker):
    df = get_price_data(ticker)
    if df is None:
        return None
    
    # Compute technicals
    df["ATR"] = calculate_atr(df)
    df["ATR_pct"] = df["ATR"] / df["Close"] * 100
    df["RSI"] = calculate_rsi(df["Close"])
    df["MACD"], df["Signal"], df["MACD_hist"] = calculate_macd(df["Close"])
    df["SMA20"] = df["Close"].rolling(20).mean()
    df["SMA50"] = df["Close"].rolling(50).mean()
    df["SMA200"] = df["Close"].rolling(200).mean()
    df["Volume_ratio"] = calculate_volume_ratio(df)
    df = df.dropna()
    
    if df.empty:
        return None
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    # Returns
    close_5d_ago = df["Close"].iloc[-6] if len(df) >= 6 else df["Close"].iloc[0]
    close_20d_ago = df["Close"].iloc[-21] if len(df) >= 21 else df["Close"].iloc[0]
    return_5d = ((latest["Close"] - close_5d_ago) / close_5d_ago) * 100
    return_20d = ((latest["Close"] - close_20d_ago) / close_20d_ago) * 100
    spy_df = get_price_data("SPY", period="2y")
    if spy_df is not None:
        spy_return = float((spy_df["Close"].iloc[-1] - spy_df["Close"].iloc[-2]) / spy_df["Close"].iloc[-2] * 100)
        ticker_return = float((df["Close"].iloc[-1] - df["Close"].iloc[-2]) / df["Close"].iloc[-2] * 100)
        df["Relative_Strength"] = round(ticker_return - spy_return, 3)
    else:
        df["Relative_Strength"] = 0.0
    return {
        "ticker": ticker.upper(),
        "current_price": round(float(latest["Close"]), 2),
        "daily_change_pct": round(float((latest["Close"] - prev["Close"]) / prev["Close"] * 100), 2),
        "trend": {
            "sma20": round(float(latest["SMA20"]), 2),
            "sma50": round(float(latest["SMA50"]), 2),
            "sma200": round(float(latest["SMA200"]), 2),
            "price_vs_sma20": round(float((latest["Close"] - latest["SMA20"]) / latest["SMA20"] * 100), 2),
            "price_vs_sma50": round(float((latest["Close"] - latest["SMA50"]) / latest["SMA50"] * 100), 2),
            "price_vs_sma200": round(float((latest["Close"] - latest["SMA200"]) / latest["SMA200"] * 100), 2),
            "return_5d": round(float(return_5d), 2),
            "return_20d": round(float(return_20d), 2),
        },
        "volatility": {
            "atr": round(float(latest["ATR"]), 2),
            "atr_pct": round(float(latest["ATR_pct"]), 2),
            "relative_strength_vs_spy": round(float(df["Relative_Strength"].iloc[-1]), 3),
        },
        "momentum": {
            "rsi": round(float(latest["RSI"]), 2),
            "macd": round(float(latest["MACD"]), 4),
            "signal": round(float(latest["Signal"]), 4),
            "macd_hist": round(float(latest["MACD_hist"]), 4),
        },
        "volume": {
            "current": int(latest["Volume"]),
            "ratio": round(float(latest["Volume_ratio"]), 2),
        }
    }

def get_vix():
    try:
        vix = yf.download("^VIX", period="5d", progress=False, auto_adjust=True)
        if isinstance(vix.columns, pd.MultiIndex):
            vix.columns = vix.columns.get_level_values(0)
        if vix.empty:
            return None
        current_vix = float(vix["Close"].iloc[-1])
        
        if current_vix < 15:
            sentiment = "Complacent"
        elif current_vix < 20:
            sentiment = "Calm"
        elif current_vix < 30:
            sentiment = "Elevated Fear"
        else:
            sentiment = "Panic"
            
        return {
            "value": round(current_vix, 2),
            "sentiment": sentiment
        }
    except:
        return None

def get_fear_greed():
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=5)
        data = response.json()
        score = float(data["fear_and_greed"]["score"])
        rating = data["fear_and_greed"]["rating"]
        
        return {
            "score": round(score, 1),
            "rating": rating
        }
    except:
        return None

def get_sector_performance():
    try:
        sectors = {
            "Technology": "XLK",
            "Financials": "XLF",
            "Energy": "XLE",
            "Healthcare": "XLV",
            "Industrials": "XLI",
            "Consumer": "XLY",
            "Utilities": "XLU"
        }

        tickers = list(sectors.values())
        df = yf.download(tickers, period="5d", progress=False, auto_adjust=True)
        
        if isinstance(df.columns, pd.MultiIndex):
            closes = df["Close"]
        else:
            closes = df

        result = {}
        for sector_name, etf in sectors.items():
            if etf in closes.columns and len(closes[etf].dropna()) >= 2:
                prev = closes[etf].dropna().iloc[-2]
                curr = closes[etf].dropna().iloc[-1]
                result[sector_name] = round(float((curr - prev) / prev * 100), 2)

        return result if result else None
    except:
        return None
def get_full_snapshot(ticker):
    snapshot = get_market_snapshot(ticker)
    if snapshot is None:
        return None
    
    macro_indicators = get_macro_indicators()
    if macro_indicators:
        snapshot["macro"] = macro_indicators

    vix = get_vix()
    if vix:
        snapshot["vix"] = vix
    
    fear_greed = get_fear_greed()
    if fear_greed:
        snapshot["fear_greed"] = fear_greed
    
    sectors = get_sector_performance()
    if sectors:
        snapshot["sectors"] = sectors
    # Price history for charts
    df_hist = get_price_data(ticker, period="10y")
    if df_hist is not None:
        df_hist["SMA20"] = df_hist["Close"].rolling(20).mean()
        df_hist["SMA50"] = df_hist["Close"].rolling(50).mean()
        df_hist["SMA200"] = df_hist["Close"].rolling(200).mean()
        df_hist["RSI"] = calculate_rsi(df_hist["Close"])
        df_hist["MACD"], df_hist["Signal"], df_hist["MACD_hist"] = calculate_macd(df_hist["Close"])
        df_hist = df_hist.dropna()

        snapshot["price_history"] = {
            "dates": df_hist.index.strftime("%Y-%m-%d").tolist(),
            "open": df_hist["Open"].round(2).tolist(),
            "high": df_hist["High"].round(2).tolist(),
            "low": df_hist["Low"].round(2).tolist(),
            "close": df_hist["Close"].round(2).tolist(),
            "volume": df_hist["Volume"].tolist(),
            "sma20": df_hist["SMA20"].round(2).tolist(),
            "sma50": df_hist["SMA50"].round(2).tolist(),
            "sma200": df_hist["SMA200"].round(2).tolist(),
            "rsi": df_hist["RSI"].round(2).tolist(),
            "macd": df_hist["MACD"].round(4).tolist(),
            "signal": df_hist["Signal"].round(4).tolist(),
            "macd_hist": df_hist["MACD_hist"].round(4).tolist(),
        }
    return snapshot