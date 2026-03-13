from flask import Flask, jsonify, request, render_template
from datetime import datetime, timedelta
import json
import os
from dotenv import load_dotenv

from database import init_db, get_cached_analysis, save_analysis, get_portfolio, add_holding, delete_holding
from data_fetcher import get_full_snapshot
from news_fetcher import get_full_news
from claude_analyst import analyze_market
from alert_engine import run_alert_engine

from collections import defaultdict
from datetime import datetime, timedelta
import threading

import sys
print("Python version:", sys.version, flush=True)
print("Starting imports...", flush=True)
load_dotenv()

from flask import Flask, jsonify, request, render_template
print("Flask imported", flush=True)
from datetime import datetime, timedelta
print("datetime imported", flush=True)
import json, os
from dotenv import load_dotenv
print("dotenv imported", flush=True)
from database import init_db, get_cached_analysis, save_analysis, get_portfolio, add_holding, delete_holding
print("database imported", flush=True)
from data_fetcher import get_full_snapshot
print("data_fetcher imported", flush=True)
from news_fetcher import get_full_news
print("news_fetcher imported", flush=True)
from claude_analyst import analyze_market
print("claude_analyst imported", flush=True)
from alert_engine import run_alert_engine
print("alert_engine imported", flush=True)

app = Flask(__name__)

# ── Rate limiting ─────────────────────────────────────────────
RATE_LIMIT_MINUTES = 10
DAILY_CLAUDE_LIMIT = 50

_rate_lock = threading.Lock()
_ip_last_call = defaultdict(lambda: datetime.min)
_daily_calls = {"count": 0, "reset_date": datetime.utcnow().date()}

def check_rate_limit(ip):
    with _rate_lock:
        now = datetime.utcnow()

        # Reset daily counter if new day
        if now.date() > _daily_calls["reset_date"]:
            _daily_calls["count"] = 0
            _daily_calls["reset_date"] = now.date()

        # Check daily budget
        if _daily_calls["count"] >= DAILY_CLAUDE_LIMIT:
            return False, "Daily analysis limit reached. Try again tomorrow."

        # Check per-IP rate limit
        last = _ip_last_call[ip]
        if now - last < timedelta(minutes=RATE_LIMIT_MINUTES):
            wait = RATE_LIMIT_MINUTES - int((now - last).total_seconds() / 60)
            return False, f"Rate limit: wait {wait} more minute(s) before next analysis."

        return True, None

def record_claude_call(ip):
    with _rate_lock:
        _ip_last_call[ip] = datetime.utcnow()
        _daily_calls["count"] += 1

CACHE_TTL_MINUTES = 60

init_db()


# ── Cache helper ─────────────────────────────────────────────────
def get_fresh_cache(ticker):
    cached = get_cached_analysis(ticker)
    if not cached:
        return None
    cached_time = datetime.strptime(cached["timestamp"], "%Y-%m-%d %H:%M:%S")
    if datetime.utcnow() - cached_time < timedelta(minutes=CACHE_TTL_MINUTES):
        return json.loads(cached["analysis_json"])
    return None


# ── Routes ───────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/portfolio")
def portfolio_page():
    return render_template("portfolio.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    ticker = data.get("ticker", "").upper().strip()

    if not ticker:
        return jsonify({"error": "Ticker is required"}), 400

    # Check cache first
    cached = get_fresh_cache(ticker)
    if cached:
        cached["cached"] = True
        return jsonify(cached)
    # Check rate limit
    ip = request.remote_addr
    allowed, reason = check_rate_limit(ip)
    if not allowed:
        return jsonify({"error": reason}), 429  
    # Fetch fresh data
    snapshot = get_full_snapshot(ticker)
    if not snapshot:
        return jsonify({"error": f"Could not fetch data for {ticker}. Check the ticker symbol."}), 404

    news = get_full_news(ticker)

    # Claude analysis
    try:
        analysis = analyze_market(snapshot, news)
        record_claude_call(ip)
    except Exception as e:
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500

    # Alert engine
    try:
        alert = run_alert_engine(ticker, snapshot, analysis)
    except Exception as e:
        alert = {"alert_tier": None, "alerts": [], "notified": False}

    # Build response
    response = {
        "ticker": ticker,
        "snapshot": snapshot,
        "analysis": analysis,
        "alert": alert,
        "cached": False,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "news": news.get("news", [])
    }

    # Save to cache
    save_analysis(ticker, json.dumps(response))

    return jsonify(response)


@app.route("/portfolio/add", methods=["POST"])
def portfolio_add():
    data = request.get_json()
    ticker = data.get("ticker", "").upper().strip()
    shares = data.get("shares")
    average_cost = data.get("average_cost")

    if not ticker or shares is None or average_cost is None:
        return jsonify({"error": "ticker, shares, and average_cost are required"}), 400

    try:
        add_holding(ticker, float(shares), float(average_cost))
        return jsonify({"success": True, "message": f"Added {shares} shares of {ticker}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/portfolio/delete", methods=["POST"])
def portfolio_delete():
    data = request.get_json()
    holding_id = data.get("id")

    if holding_id is None:
        return jsonify({"error": "id is required"}), 400

    try:
        delete_holding(holding_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/portfolio/get", methods=["GET"])
def portfolio_get():
    try:
        holdings = get_portfolio()
        return jsonify({"holdings": holdings})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/portfolio/analyze", methods=["GET"])
def portfolio_analyze():
    holdings = get_portfolio()
    if not holdings:
        return jsonify({"error": "No holdings in portfolio"}), 404

    results = []
    for holding in holdings:
        ticker = holding["ticker"]
        cached = get_fresh_cache(ticker)

        if cached:
            result = cached
            result["cached"] = True
        else:
            snapshot = get_full_snapshot(ticker)
            if not snapshot:
                continue
            news = get_full_news(ticker)
            try:
                analysis = analyze_market(snapshot, news)
                alert = run_alert_engine(ticker, snapshot, analysis)
            except Exception as e:
                print(f"Error analyzing {ticker}: {str(e)}")
                continue

            result = {
                "ticker": ticker,
                "snapshot": snapshot,
                "analysis": analysis,
                "alert": alert,
                "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "news": news.get("news", [])
            }
            save_analysis(ticker, json.dumps(result))

        result["holding"] = holding
        results.append(result)

    return jsonify({"portfolio": results})


if __name__ == "__main__":
    app.run(debug=True, port=5000)