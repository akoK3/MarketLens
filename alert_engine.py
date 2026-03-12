import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from database import add_alert

load_dotenv()

# ── Email config ────────────────────────────────────────────────
EMAIL_SENDER   = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

# ── Thresholds ───────────────────────────────────────────────────
THRESHOLDS = {
    "rsi": {
        "red_high": 80, "orange_high": 75, "yellow_high": 70,
        "yellow_low": 30, "orange_low": 25, "red_low": 20
    },
    "atr_pct": {
        "yellow": 1.5, "orange": 2.5, "red": 3.5
    },
    "volume_ratio": {
        "red_high": 3.5, "orange_high": 2.5, "yellow_high": 1.8,
        "yellow_low": 0.5, "orange_low": 0.3
    },
    "price_vs_atr": {
        "yellow": 1.5, "orange": 2.0, "red": 3.0
    },
    "vix": {
        "yellow": 25, "orange": 30, "red": 35,
        "spike_pct": 15
    },
    "relative_strength": {
        "yellow": 1.5, "orange": 2.5, "red": 4.0
    },
    "fear_greed": {
        "red_low": 15, "orange_low": 25,
        "orange_high": 75, "red_high": 85
    }
}

# ── Tier ranking ─────────────────────────────────────────────────
TIER_RANK = {"yellow": 1, "orange": 2, "red": 3}

def _upgrade(current, new):
    """Keep highest tier."""
    if TIER_RANK.get(new, 0) > TIER_RANK.get(current, 0):
        return new
    return current


# ── Individual checks ────────────────────────────────────────────
def _check_rsi(snapshot, triggered):
    rsi = snapshot.get("momentum", {}).get("rsi")
    if rsi is None:
        return

    t = THRESHOLDS["rsi"]
    if rsi >= t["red_high"]:
        triggered.append(("red", "overbought", f"RSI {rsi:.1f} — extreme overbought (≥{t['red_high']})"))
    elif rsi >= t["orange_high"]:
        triggered.append(("orange", "overbought", f"RSI {rsi:.1f} — strong overbought (≥{t['orange_high']})"))
    elif rsi >= t["yellow_high"]:
        triggered.append(("yellow", "overbought", f"RSI {rsi:.1f} — elevated overbought (≥{t['yellow_high']})"))
    elif rsi <= t["red_low"]:
        triggered.append(("red", "oversold", f"RSI {rsi:.1f} — extreme oversold (≤{t['red_low']})"))
    elif rsi <= t["orange_low"]:
        triggered.append(("orange", "oversold", f"RSI {rsi:.1f} — strong oversold (≤{t['orange_low']})"))
    elif rsi <= t["yellow_low"]:
        triggered.append(("yellow", "oversold", f"RSI {rsi:.1f} — elevated oversold (≤{t['yellow_low']})"))


def _check_atr(snapshot, triggered):
    atr_pct = snapshot.get("volatility", {}).get("atr_pct")
    if atr_pct is None:
        return

    t = THRESHOLDS["atr_pct"]
    if atr_pct >= t["red"]:
        triggered.append(("red", "volatility_spike", f"ATR% {atr_pct:.2f}% — abnormal volatility (≥{t['red']}%)"))
    elif atr_pct >= t["orange"]:
        triggered.append(("orange", "volatility_spike", f"ATR% {atr_pct:.2f}% — significant volatility (≥{t['orange']}%)"))
    elif atr_pct >= t["yellow"]:
        triggered.append(("yellow", "volatility_spike", f"ATR% {atr_pct:.2f}% — elevated volatility (≥{t['yellow']}%)"))


def _check_volume(snapshot, triggered):
    ratio = snapshot.get("volume", {}).get("ratio")
    if ratio is None:
        return

    t = THRESHOLDS["volume_ratio"]
    if ratio >= t["red_high"]:
        triggered.append(("red", "volume_anomaly", f"Volume ratio {ratio:.2f} — extreme activity (≥{t['red_high']}x avg)"))
    elif ratio >= t["orange_high"]:
        triggered.append(("orange", "volume_anomaly", f"Volume ratio {ratio:.2f} — abnormal activity (≥{t['orange_high']}x avg)"))
    elif ratio >= t["yellow_high"]:
        triggered.append(("yellow", "volume_anomaly", f"Volume ratio {ratio:.2f} — elevated activity (≥{t['yellow_high']}x avg)"))
    elif ratio <= t["orange_low"]:
        triggered.append(("orange", "volume_anomaly", f"Volume ratio {ratio:.2f} — abnormally low volume (≤{t['orange_low']}x avg)"))
    elif ratio <= t["yellow_low"]:
        triggered.append(("yellow", "volume_anomaly", f"Volume ratio {ratio:.2f} — low conviction volume (≤{t['yellow_low']}x avg)"))


def _check_price_move(snapshot, triggered):
    atr = snapshot.get("volatility", {}).get("atr")
    price = snapshot.get("current_price")
    daily_change_pct = snapshot.get("daily_change_pct")
    if None in (atr, price, daily_change_pct):
        return

    daily_move = abs(daily_change_pct / 100 * price)
    multiple = daily_move / atr if atr > 0 else 0
    t = THRESHOLDS["price_vs_atr"]
    direction = "up" if daily_change_pct > 0 else "down"

    if multiple >= t["red"]:
        triggered.append(("red", "anomaly_high" if daily_change_pct > 0 else "anomaly_low",
            f"Price moved {multiple:.1f}x ATR {direction} — abnormal move (≥{t['red']}x ATR)"))
    elif multiple >= t["orange"]:
        triggered.append(("orange", "anomaly_high" if daily_change_pct > 0 else "anomaly_low",
            f"Price moved {multiple:.1f}x ATR {direction} — significant move (≥{t['orange']}x ATR)"))
    elif multiple >= t["yellow"]:
        triggered.append(("yellow", "anomaly_high" if daily_change_pct > 0 else "anomaly_low",
            f"Price moved {multiple:.1f}x ATR {direction} — elevated move (≥{t['yellow']}x ATR)"))


def _check_vix(snapshot, triggered):
    vix = snapshot.get("vix", {})
    if not vix:
        return

    value = vix.get("value")
    prev = vix.get("prev_close")
    t = THRESHOLDS["vix"]

    if value is not None:
        if value >= t["red"]:
            triggered.append(("red", "macro_risk", f"VIX {value:.1f} — crisis level fear (≥{t['red']})"))
        elif value >= t["orange"]:
            triggered.append(("orange", "macro_risk", f"VIX {value:.1f} — fear territory (≥{t['orange']})"))
        elif value >= t["yellow"]:
            triggered.append(("yellow", "macro_risk", f"VIX {value:.1f} — elevated concern (≥{t['yellow']})"))

    if value is not None and prev is not None and prev > 0:
        spike = (value - prev) / prev * 100
        if spike >= t["spike_pct"]:
            triggered.append(("orange", "macro_risk",
                f"VIX spiked {spike:.1f}% in one day — sudden fear surge"))


def _check_relative_strength(snapshot, triggered):
    rs = snapshot.get("volatility", {}).get("relative_strength_vs_spy")
    if rs is None:
        return

    abs_rs = abs(rs)
    t = THRESHOLDS["relative_strength"]
    direction = "outperforming" if rs > 0 else "underperforming"

    if abs_rs >= t["red"]:
        triggered.append(("red", "anomaly_high" if rs > 0 else "anomaly_low",
            f"Relative strength {rs:+.2f}% vs SPY — abnormal divergence, {direction}"))
    elif abs_rs >= t["orange"]:
        triggered.append(("orange", "anomaly_high" if rs > 0 else "anomaly_low",
            f"Relative strength {rs:+.2f}% vs SPY — significant divergence, {direction}"))
    elif abs_rs >= t["yellow"]:
        triggered.append(("yellow", "anomaly_high" if rs > 0 else "anomaly_low",
            f"Relative strength {rs:+.2f}% vs SPY — notable divergence, {direction}"))


def _check_fear_greed(snapshot, triggered):
    fg = snapshot.get("fear_greed")
    if fg is None:
        return

    score = fg.get("score") if isinstance(fg, dict) else fg
    if score is None:
        return

    t = THRESHOLDS["fear_greed"]
    if score <= t["red_low"]:
        triggered.append(("red", "fear_capitulation",
            f"Fear & Greed {score} — extreme fear, potential capitulation"))
    elif score <= t["orange_low"]:
        triggered.append(("orange", "fear_capitulation",
            f"Fear & Greed {score} — deep fear territory"))
    elif score >= t["red_high"]:
        triggered.append(("red", "euphoria_warning",
            f"Fear & Greed {score} — extreme greed, euphoria warning"))
    elif score >= t["orange_high"]:
        triggered.append(("orange", "euphoria_warning",
            f"Fear & Greed {score} — greed territory, elevated reversal risk"))


def _check_yield_curve(snapshot, triggered):
    macro = snapshot.get("macro", {})
    if not macro:
        return
    yc = macro.get("yield_curve", {})
    if yc.get("inverted"):
        spread = yc.get("spread", 0)
        triggered.append(("orange", "macro_risk",
            f"Yield curve inverted (spread {spread:.3f}) — historical recession signal"))


# ── Email sender ─────────────────────────────────────────────────
def _send_email(ticker, tier, alerts, claude_result):
    if not all([EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER]):
        print("Email not configured — skipping notification")
        return

    subject = f"MarketLens [{tier.upper()}] Alert — {ticker}"

    alert_lines = "\n".join(f"  • {a[2]}" for a in alerts)
    summary = claude_result.get("summary", "No summary available.")
    risk_score = claude_result.get("risk_score", "N/A")
    confidence = claude_result.get("confidence_score", "N/A")

    body = f"""
MarketLens Alert — {ticker}
{'=' * 40}
Tier:         {tier.upper()}
Risk Score:   {risk_score}/100
Confidence:   {confidence}/100

Triggered Alerts:
{alert_lines}

Claude Summary:
{summary}

Watch Next 24h:
{claude_result.get('watch_next_24h', 'N/A')}

{claude_result.get('disclaimer', '')}
"""

    msg = MIMEMultipart()
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        print(f"Email sent — {tier.upper()} alert for {ticker}")
    except Exception as e:
        print(f"Email failed: {e}")


# ── Main entry point ─────────────────────────────────────────────
def run_alert_engine(ticker, snapshot, claude_result):
    triggered = []

    _check_rsi(snapshot, triggered)
    _check_atr(snapshot, triggered)
    _check_volume(snapshot, triggered)
    _check_price_move(snapshot, triggered)
    _check_vix(snapshot, triggered)
    _check_relative_strength(snapshot, triggered)
    _check_fear_greed(snapshot, triggered)
    _check_yield_curve(snapshot, triggered)

    if not triggered:
        return {
            "ticker": ticker,
            "alert_tier": None,
            "alerts": [],
            "notified": False
        }

    # Highest tier wins
    top_tier = max(triggered, key=lambda x: TIER_RANK[x[0]])[0]

    # Send email if orange or red
    if top_tier in ("orange", "red"):
        _send_email(ticker, top_tier, triggered, claude_result)
        notified = True
    else:
        notified = False

    # Save to database
    for tier, alert_type, reason in triggered:
        add_alert(ticker, alert_type, reason, tier)

    return {
        "ticker": ticker,
        "alert_tier": top_tier,
        "alerts": [{"tier": t, "type": a, "reason": r} for t, a, r in triggered],
        "notified": notified
    }