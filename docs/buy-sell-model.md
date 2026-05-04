🧠 CORE IDEA

You want a function like:

decision = evaluate_position(price, rsi, trend, volume, position_state)

👉 Output:

BUY
ADD
HOLD
TRIM
SELL
🧩 1. INPUT MODEL (keep it minimal but powerful)
inputs:
  price:
    current: float
    ma20: float
    ma50: float

  rsi:
    value: float

  volume:
    current: float
    avg_20d: float

  structure:
    higher_highs: boolean
    higher_lows: boolean
    breakout: boolean
    consolidation: boolean

  position:
    has_position: boolean
    avg_cost: float
    position_size_pct: float   # % of capital
    type: enum [core, trading]
⚙️ 2. DERIVED SIGNALS
derived:
  trend_strength:
    if price > ma20 and ma20 > ma50 → "strong_uptrend"
    if price > ma50 → "uptrend"
    else → "weak"

  volume_strength:
    if current > 1.5 * avg_20d → "high"
    if current > avg_20d → "normal"
    else → "low"

  rsi_zone:
    < 35 → "oversold"
    35–55 → "neutral"
    55–70 → "bullish"
    70–80 → "overbought"
    > 80 → "extreme"

  extension:
    (price - ma20) / ma20
🧠 3. DECISION ENGINE (THE HEART)
🟢 BUY (no position yet)
BUY:
  conditions:
    - structure.breakout == true
    - volume_strength == "high"
    - rsi_zone in ["bullish"]
    - trend_strength in ["uptrend", "strong_uptrend"]
  action:
    - enter_position_pct: 25
🟩 ADD (build position)
ADD:
  conditions:
    - position.has_position == true
    - structure.consolidation == true OR pullback to ma20
    - rsi_zone in ["neutral", "bullish"]
    - trend_strength == "strong_uptrend"
  action:
    - add_position_pct: 15–25
🟡 HOLD (do nothing)
HOLD:
  conditions:
    - trend_strength in ["uptrend", "strong_uptrend"]
    - structure.higher_highs == true
    - rsi_zone in ["bullish", "neutral"]
  action:
    - no_change
🟠 TRIM (take profits, NOT exit)
TRIM:
  conditions:
    - rsi_zone in ["overbought", "extreme"]
    - extension > 0.08   # >8% above MA20
    - volume_strength == "high"
  action:
    - reduce_position_pct: 20–40

👉 This is EXACTLY what CRDO did at 120

🔴 SELL (exit completely)
SELL:
  conditions:
    - trend_strength == "weak"
    - price < ma50
    - structure.higher_lows == false
    - volume_strength == "high"   # distribution
  action:
    - exit_all
⚡ 4. PRIORITY ORDER (VERY IMPORTANT)

When multiple conditions match:

SELL > TRIM > ADD > BUY > HOLD
🧠 5. SPECIAL RULES (this is where edge comes from)
🚨 Rule 1: Never SELL in strong uptrend
if trend_strength == "strong_uptrend" AND price > ma20:
  block SELL
  allow only TRIM
🚨 Rule 2: Parabolic move = TRIM, not BUY
if rsi > 75 AND extension > 0.1:
  force_action: TRIM
🚨 Rule 3: Pullback = opportunity
if price near ma20 AND trend_strength == "strong_uptrend":
  bias: ADD
🚨 Rule 4: No chasing
if extension > 0.12:
  block BUY
🧪 6. SAMPLE OUTPUT (what your system returns)
{
  "decision": "TRIM",
  "confidence": 0.82,
  "reason": [
    "RSI in overbought zone (78)",
    "Price extended 10% above MA20",
    "High volume spike detected"
  ],
  "suggested_action": {
    "reduce_pct": 30
  }
}
🏗️ 7. HOW THIS MAPS TO YOUR SYSTEM

This fits PERFECTLY into your:

YAML-driven formulas ✅
LangGraph agent ✅
Fair value engine mindset ✅

You just add:
👉 TechnicalDecisionService

🔥 PRO INSIGHT (this is the real edge)

Most people:

BUY when RSI is high ❌
SELL when RSI is low ❌

Your system will:

ADD when others are scared
TRIM when others are greedy

👉 That’s literally the edge.