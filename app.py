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

load_dotenv()

app = Flask(__name__)
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

    # Fetch fresh data
    snapshot = get_full_snapshot(ticker)
    if not snapshot:
        return jsonify({"error": f"Could not fetch data for {ticker}. Check the ticker symbol."}), 404

    news = get_full_news(ticker)

    # Claude analysis
    try:
        analysis = analyze_market(snapshot, news)
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