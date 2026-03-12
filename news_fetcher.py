import requests
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")

def get_company_news(ticker, days=7):
    try:
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        url = f"https://finnhub.io/api/v1/company-news"
        params = {
            "symbol": ticker.upper(),
            "from": start_date,
            "to": end_date,
            "token": FINNHUB_API_KEY
        }
        
        response = requests.get(url, params=params, timeout=5)
        news = response.json()
        
        if not isinstance(news, list):
            return []
        
        cleaned = []
        for article in news[:10]:
            cleaned.append({
                "headline": article.get("headline", ""),
                # Hardlimit summary (that claude API recieves) to 500 characters to avoid token exhaustion
                "summary": article.get("summary", "")[:500],
                "source": article.get("source", ""),
                "datetime": datetime.fromtimestamp(article.get("datetime", 0)).strftime("%Y-%m-%d")
            })
        
        return cleaned
    except:
        return []

def get_earnings_calendar(ticker):
    """Company's quarterly financial results"""
    try:
        url = f"https://finnhub.io/api/v1/calendar/earnings"
        today = datetime.now().strftime("%Y-%m-%d")
        next_month = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        
        params = {
            "from": today,
            "to": next_month,
            "symbol": ticker.upper(),
            "token": FINNHUB_API_KEY
        }
        
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        
        earnings = data.get("earningsCalendar", [])
        
        if not earnings:
            return None
            
        next_earnings = earnings[0]
        return {
            "date": next_earnings.get("date", ""),
            "estimate_eps": next_earnings.get("epsEstimate", None),
            "actual_eps": next_earnings.get("epsActual", None)
        }
    except:
        return None

def get_macro_events():
    try:
        url = "https://finnhub.io/api/v1/calendar/economic"
        today = datetime.now().strftime("%Y-%m-%d")
        next_week = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        
        params = {
            "from": today,
            "to": next_week,
            "token": FINNHUB_API_KEY
        }
        
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        
        events = data.get("economicCalendar", [])
        
        if not events:
            return []
        
        filtered = []
        for event in events:
            if event.get("impact", "") in ["high", "medium"]:
                filtered.append({
                    "event": event.get("event", ""),
                    "date": event.get("date", ""),
                    "country": event.get("country", "")
                })
        
        return filtered[:5]
    except:
        return []
    
def get_full_news(ticker):
    news = get_company_news(ticker)
    earnings = get_earnings_calendar(ticker)
    macro = get_macro_events()
    
    return {
        "news": news,
        "earnings": earnings,
        "macro_events": macro
    }