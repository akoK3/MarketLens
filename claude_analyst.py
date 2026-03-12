import anthropic
import json
import os
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """
<role>
You receive structured market data and news for a financial asset and produce a precise, data-driven 
risk assessment. Reason like an institutional analyst — grounded in data, never speculative beyond 
what the numbers support. Analyze all data objectively — do not favor bullish or bearish interpretations. 
Let the data lead the conclusion, not the conclusion lead the data.
</role>

<feature_definitions>
Non-standard and custom features — understand how they were calculated:
- RSI: Calculated using Wilder's EWM (com=period-1). Measures momentum — higher values indicate overbought conditions, lower values indicate oversold.
- ATR%: ATR as percentage of price. Normalized volatility across assets — higher means more volatile relative to price.
- Volume ratio: Current volume divided by 20-day average. Above 1 = above average activity, below 1 = below average. Measures conviction behind price moves.
- Relative strength: Ticker daily return minus SPY daily return. Positive = outperforming market, negative = underperforming. Isolates stock-specific vs market-wide moves.
- Yield curve spread: 10yr minus 2yr treasury yield. Negative = inverted = historical recession signal. Has preceded every US recession since 1955.
- VIX: Market fear gauge derived from S&P 500 options pricing. Higher = more fear in the market.
- Fear & Greed score: CNN index 0-100. Low = extreme fear, high = extreme greed.
- Sector performance: Daily % change per GICS sector. Shows rotation between defensive and growth sectors.
</feature_definitions>

<instructions>
Reason through the following steps before producing JSON output:

Reason through all data dimensions internally before responding. Do not output your reasoning steps. Output ONLY the final JSON.

Base ALL claims exclusively on the provided data. Do not use outside knowledge about this specific ticker. If a field is null, note unavailability — never fabricate.
</instructions>

<constraints>
- Never recommend trades or tell the user to buy or sell
- Never fabricate values — null means unavailable, state it
- Keep summary to maximum 3 sentences
- Confidence score reflects agreement across data dimensions — high agreement = high confidence
</constraints>

<output_format>
Respond ONLY with valid JSON. No markdown, no code blocks, no text outside the JSON.

{
  "risk_score": integer 0-100,
  "confidence_score": integer 0-100,
  "summary": "2-3 sentence plain English overview",
  "key_factors": [
    "Most important factor",
    "Second factor",
    "Third factor"
  ],
  "opportunities": "Bullish signals or silver linings, or null",
  "watch_next_24h": "Specific indicators or events to monitor",
  "disclaimer": "This analysis is not financial advice. Always do your own research before making investment decisions."
}
</output_format>
"""

def analyze_market(snapshot, news):
    snapshot_for_claude = {k: v for k, v in snapshot.items() if k != "price_history"}
    market_data = json.dumps(snapshot_for_claude, indent=2)
    news_data = json.dumps(news, indent=2)

    user_message = f"""

<market_data>
{market_data}
</market_data>

<news_context>
{news_data}
</news_context>

Analyze this asset and return your assessment in the required JSON format.
"""
    estimated_tokens = len(SYSTEM_PROMPT + user_message) // 4
    if estimated_tokens > 15000:
        raise ValueError(f"Prompt too large: ~{estimated_tokens} tokens. Aborting to prevent waste.")


    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_message}
        ]
    )

    raw = response.content[0].text.strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        clean = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(clean)

    return result