# 📑 MEME RADAR STRATEGY SPECIFICATION (FOR LLM AGENTS)
> **Source Repository**: `https://github.com/nhovongoc0-max/meme-radar`  
> **Original Author**: DeFi狙击手 (`@bi_9527zx`)  
> **Target Audience**: Any AI Coding Assistant / Quant Developer implementing or extending this system.  
> **Date**: September 2026

---

## 1. Executive Philosophy & System Architecture

### 1.1 Core Principles
1. **Decoupled Architecture**: Discovery Radar (Read-Only) is physically decoupled from Trade Execution (Private Key / Signer).
2. **Zero-Assumption Safety ("未知绝不等于安全")**: If an API or query returns `null`, `undefined`, or times out for a risk field (e.g. Honeypot, Tax, Insider), the token **CANNOT** pass. It is categorized as `WAIT_RECHECK`. Never default missing fields to `0% risk`.
3. **No Block-0 Sniping**: Tokens under 5 minutes old (`ageSec < 300`) are explicitly banned. Block 0 is infested with Dev Jito bundles and toxic MEV. We only enter once the initial dump has settled and real organic buyer flow appears.
4. **Sweet Spot Sizing**: 
   - Acceptable Market Cap: **$10,000 to $150,000 USD**
   - High Priority Band: **$20,000 to $80,000 USD** (Optimal risk/reward ratio for explosive meme runs).

---

## 2. The 5-Gate Filtering Pipeline

Every candidate token must pass five sequential gates. If any gate fails, the token is tagged with `HARD_REJECT` or `WAIT_RECHECK`.

```
Raw Candidate Pool
       │
       ▼ [Gate 1: Pool Age & Market Cap]
       ├─ Age ≥ 300s (5m)
       ├─ MC: $10k - $150k (Priority: $20k - $80k)
       ├─ Liquidity ≥ $3,000 (Deep audit ≥ $8,000)
       ▼
       ▼ [Gate 2: Contract Security & Tax]
       ├─ Buy Tax ≤ 5%, Sell Tax ≤ 5%
       ├─ |BuyTax - SellTax| ≤ 2% (Tax Asymmetry Guard)
       ├─ IsHoneypot == False, Sellable == True
       ▼
       ▼ [Gate 3: Holder & Tokenomics (One-Vote Veto)]
       ├─ Dev / Creator Hold ≤ 1.0% (STRICT)
       ├─ Bundler Rate ≤ 15.0%
       ├─ Insider / Rat Trader Rate ≤ 15.0%
       ├─ Top 10 Holders ≤ 30.0%
       ├─ Sniper Hold Rate ≤ 8.0%
       ├─ LP Locked Rate ≥ 80.0%
       ├─ Distinct Ordinary Wallets ≥ 8
       ▼
       ▼ [Gate 4: Chart Risk Pattern Screening]
       ├─ Reject VERTICAL_PLATEAU (1m spike ≥ 35% + narrow plateau)
       ├─ Reject SUSTAINED_COLLAPSE (Peak to 2x 1m candles drawdown ≥ 60%)
       ├─ Reject COLLAPSED_ATH (Price ≤ 10% of ATH without 20% 1h rebound)
       ▼
       ▼ [Gate 5: 5-Minute Volume & Momentum]
       ├─ Volume (5m) ≥ $1,500 USD
       ├─ Recent 5m Buys ≥ 4 to 6
       ├─ Buys / Sells Ratio ≥ 1.3x
       ▼
[QUALIFIED FOR EXECUTION]
```

---

## 3. Mathematical Formulations & Exact Thresholds

### 3.1 Gate 1: Pool Age & Valuation Gate
- `age_sec = now_timestamp - first_trade_timestamp`
- **Rule**: $300 \le \text{age\_sec} \le 604,800$ (Between 5 minutes and 7 days).
- **Valuation**:
  $$\$10,000 \le \text{MarketCap} \le \$150,000$$
  $$\text{PriorityScore Boost if } \$20,000 \le \text{MarketCap} \le \$80,000$$
- **Liquidity**:
  $$\text{Liquidity}_{\text{USD}} \ge \$3,000 \quad (\text{Strict Deep Audit: } \ge \$8,000)$$

### 3.2 Gate 2: Contract & Tax Security
- **Max Buy Tax**: $\tau_{\text{buy}} \le 0.05$ (5%)
- **Max Sell Tax**: $\tau_{\text{sell}} \le 0.05$ (5%)
- **Tax Asymmetry**: $|\tau_{\text{buy}} - \tau_{\text{sell}}| \le 0.02$ (2%)  
  *(Prevents traps like 1% buy tax but 5% or hidden sell tax).*

### 3.3 Gate 3: Tokenomics & Anti-Rug Thresholds
- **Dev Holding**: $\text{Hold}_{\text{dev}} \le 0.01$ (Max 1.0% allowed).
- **Bundler Rate**: $\text{Rate}_{\text{bundler}} \le 0.15$ (Max 15%).
- **Insider / Rat Trader Rate**: $\text{Rate}_{\text{insider}} \le 0.15$ (Max 15%).
- **Top 10 Concentration**: $\sum_{i=1}^{10} \text{Hold}_i \le 0.30$ (Max 30%).
- **Sniper Hold Rate**: $\text{Rate}_{\text{sniper}} \le 0.08$ (Max 8%).
- **LP Lock Rate**: $\text{Rate}_{\text{lp\_locked}} \ge 0.80$ (Min 80% locked or burned).
- **Organic Wallets**: $\text{Count}_{\text{ordinary\_wallets}} \ge 8$.

---

## 4. The `chartRiskScreen` K-Line Pattern Algorithm

This is the proprietary algorithm from `src/chart-risk.mjs`. Any LLM implementing this must inspect the last 15-20 completed 1-minute candles $(O, H, L, C, V)$.

### Pattern A: `VERTICAL_PLATEAU` (Maker Drawing Trap)
Identifies a market maker who pumps the token in a single bar and holds an artificial narrow range to lure retail buyers:
```
Condition:
For candle i:
  jump = (Close[i] / Open[i]) - 1
  If jump >= 0.35 (>= +35% in 1 minute):
    Check next 3 candles (i+1, i+2, i+3):
      plateau_range = max(Close[i..i+3]) / min(Close[i..i+3]) - 1
      If plateau_range <= 0.15 and Close[i+3] / Open[i] >= 1.30:
        TRIGGER HARD_REJECT: "VERTICAL_PLATEAU (单分钟跳升≥35%后窄幅平台，按风险偏好排除)"
```

### Pattern B: `SUSTAINED_COLLAPSE` (Free-Falling Knife)
Prevents buying during a continuous dump:
```
Condition:
Track confirmed peak Close:
  drawdown = 1 - max(Close[i], Close[i+1]) / peak_close
  If drawdown >= 0.60 (>= 60% collapse across 2 consecutive candles):
    TRIGGER HARD_REJECT: "SUSTAINED_COLLAPSE (已观测收盘高点后连续两根回撤≥60%，保留风险排除)"
```

### Pattern C: `COLLAPSED_ATH` (Dead Cat Stagnation)
```
Condition:
If age >= 1 hour:
  ath_ratio = current_price / ATH_price
  If ath_ratio <= 0.10 (fallen >= 90% from peak):
    Unless 1h_price_change >= +0.20 (+20% strong rebound):
      TRIGGER HARD_REJECT: "距历史高点跌幅过深且未出现强势反弹"
```

---

## 5. Execution, Position Sizing & Trade Management

When all 5 gates pass, the execution module fires:

| Parameter | Setting | Description |
| :--- | :--- | :--- |
| **Position Size** | **$10.00 – $15.00 USD** | Max 10–20% of bankroll per trade to minimize friction. |
| **Max Open Trades** | **3 per chain** | Diversifies idiosyncratic meme risk. |
| **Hard Take-Profit** | **+80.0%** | Hard limit ceiling. |
| **Trailing Stop Trigger** | **$\ge +25.0\%$** | Activates dynamic trailing once price reaches +25%. |
| **Trailing Pullback** | **10.0% from peak** | Sells immediately if price retraces 10% from highest peak. |
| **Breakeven Floor** | **Trigger: $+18\%$ $\rightarrow$ Floor: $+2\%$** | Once price hits +18%, SL moves to +2% profit to guarantee zero loss. |
| **Hard Stop-Loss** | **-20.0%** | Hard cutoff on adverse entry. |
| **Decay Stagnation Exit** | **20 minutes if gain $< 2.0\%$** | Sells flat tokens to release capital and prevent LP fee bleed. |

---

## 6. Ready-to-Implement Python Module (`meme_radar_rules.py`)

Here is the clean, drop-in Python reference code implementing the exact specifications:

```python
"""
Meme Radar Rule Engine - Turnkey Python Implementation
Ported from nhovongoc0-max/meme-radar for any LLM or Quant Bot.
"""
from typing import Dict, List, Tuple, Optional

class MemeRadarEvaluator:
    # Threshold Constants
    MIN_AGE_SEC = 300              # 5 minutes
    MAX_AGE_SEC = 604800           # 7 days
    MIN_MC_USD = 10_000.0          # $10k
    MAX_MC_USD = 150_000.0         # $150k
    PRIORITY_MIN_MC = 20_000.0     # $20k
    PRIORITY_MAX_MC = 80_000.0     # $80k
    MIN_LIQUIDITY_USD = 3_000.0    # $3k
    MAX_BUY_TAX = 0.05             # 5%
    MAX_SELL_TAX = 0.05            # 5%
    MAX_TAX_ASYMMETRY = 0.02       # 2%
    MAX_DEV_HOLD = 0.01            # 1%
    MAX_BUNDLER_RATE = 0.15        # 15%
    MAX_INSIDER_RATE = 0.15        # 15%
    MAX_TOP10_RATE = 0.30          # 30%
    MAX_SNIPER_RATE = 0.08         # 8%
    MIN_LP_LOCKED = 0.80           # 80%

    @classmethod
    def evaluate_candidate(cls, token: Dict) -> Tuple[bool, List[str]]:
        reasons = []

        # Gate 1: Age & Market Cap
        age = token.get("age_sec", 0)
        mc = token.get("market_cap_usd", 0)
        liq = token.get("liquidity_usd", 0)
        
        if age < cls.MIN_AGE_SEC:
            reasons.append(f"Age too young ({age}s < 300s)")
        if age > cls.MAX_AGE_SEC:
            reasons.append("Exceeds max observation age")
        if not (cls.MIN_MC_USD <= mc <= cls.MAX_MC_USD):
            reasons.append(f"Market cap ${mc:,.0f} outside sweet spot ($10k-$150k)")
        if liq < cls.MIN_LIQUIDITY_USD:
            reasons.append(f"Liquidity ${liq:,.0f} below $3,000 threshold")

        # Gate 2: Security & Tax
        buy_tax = token.get("buy_tax", 0.0)
        sell_tax = token.get("sell_tax", 0.0)
        if token.get("is_honeypot", False) or not token.get("sellable", True):
            reasons.append("HONEYPOT_DETECTED")
        if buy_tax > cls.MAX_BUY_TAX or sell_tax > cls.MAX_SELL_TAX:
            reasons.append(f"Tax too high (Buy: {buy_tax*100}%, Sell: {sell_tax*100}%)")
        if abs(buy_tax - sell_tax) > cls.MAX_TAX_ASYMMETRY:
            reasons.append(f"Tax asymmetry gap > 2% ({abs(buy_tax - sell_tax)*100:.1f}%)")

        # Gate 3: Holder & Tokenomics One-Vote Veto
        dev_hold = token.get("dev_hold_rate", 0.0)
        bundler = token.get("bundler_rate", 0.0)
        insider = token.get("insider_rate", 0.0)
        top10 = token.get("top10_rate", 0.0)
        sniper = token.get("sniper_rate", 0.0)
        lp_lock = token.get("lp_locked_rate", 1.0)

        if dev_hold > cls.MAX_DEV_HOLD:
            reasons.append(f"DEV hold {dev_hold*100:.1f}% exceeds 1% limit")
        if bundler > cls.MAX_BUNDLER_RATE:
            reasons.append(f"Bundler rate {bundler*100:.1f}% exceeds 15% limit")
        if insider > cls.MAX_INSIDER_RATE:
            reasons.append(f"Insider rate {insider*100:.1f}% exceeds 15% limit")
        if top10 > cls.MAX_TOP10_RATE:
            reasons.append(f"Top 10 concentration {top10*100:.1f}% exceeds 30% limit")
        if sniper > cls.MAX_SNIPER_RATE:
            reasons.append(f"Sniper hold {sniper*100:.1f}% exceeds 8% limit")
        if lp_lock < cls.MIN_LP_LOCKED:
            reasons.append(f"LP lock rate {lp_lock*100:.1f}% below 80% limit")

        # Gate 5: Dynamic 5m Volume
        vol_5m = token.get("volume_5m", 0.0)
        buys_5m = token.get("buys_5m", 0)
        sells_5m = token.get("sells_5m", 0)
        if vol_5m < 1500.0:
            reasons.append(f"5m Volume ${vol_5m:,.0f} below $1,500 threshold")
        if buys_5m < 4:
            reasons.append(f"5m Buys {buys_5m} below minimum 4")
        if sells_5m > 0 and (buys_5m / sells_5m) < 1.3:
            reasons.append(f"Buy/Sell ratio {buys_5m/sells_5m:.2f} below 1.3x")

        passed = len(reasons) == 0
        return passed, reasons

    @classmethod
    def evaluate_chart_risk(cls, candles_1m: List[Dict]) -> Tuple[bool, List[str]]:
        """
        candles_1m: list of dicts with keys: 'open', 'high', 'low', 'close', 'volume'
        sorted ascending by time.
        """
        reasons = []
        if len(candles_1m) < 5:
            return False, ["Insufficient candle history (< 5 bars)"]

        # 1. VERTICAL_PLATEAU check
        for i in range(len(candles_1m) - 3):
            bar = candles_1m[i]
            after = candles_1m[i+1 : i+4]
            anchor = bar["open"]
            if anchor <= 0:
                continue
            jump = (bar["close"] / anchor) - 1.0
            closes = [bar["close"]] + [b["close"] for b in after]
            if bar["volume"] > 0 and all(b["volume"] > 0 for b in after):
                if jump >= 0.35: # Jump >= +35%
                    spread = (max(closes) / min(closes)) - 1.0
                    if spread <= 0.15 and (after[-1]["close"] / anchor) >= 1.30:
                        reasons.append("VERTICAL_PLATEAU (Maker 35% spike + artificial narrow hold)")
                        break

        # 2. SUSTAINED_COLLAPSE check
        peak = candles_1m[0]["close"]
        for i in range(1, len(candles_1m) - 1):
            c1 = candles_1m[i]["close"]
            c2 = candles_1m[i+1]["close"]
            if peak > 0:
                drawdown = 1.0 - (max(c1, c2) / peak)
                if drawdown >= 0.60: # Dropped 60% across 2 bars
                    reasons.append("SUSTAINED_COLLAPSE (Rapid >= 60% cliff dump)")
                    break
            peak = max(peak, candles_1m[i]["close"])

        return len(reasons) == 0, reasons
```

---

## 7. Instructions for Any LLM Agent Handling This Task

When another LLM agent resumes or implements this system:
1. **Never relax Gate 3 (Tokenomics)**: A Dev holding > 1% is almost guaranteed to dump on bonding curves or Uniswap pools.
2. **Never snipe Block 0**: Maintain `MIN_AGE_SEC = 300` at all times.
3. **Use the Priority Band**: Score tokens higher if Market Cap is between **$20,000 and $80,000**.
4. **Deploy Small Sizing ($10–$15)**: Do not commit 50% of the wallet to one coin; 3 concurrent small positions with Trailing Stop maximize positive mathematical expectation.
5. **Honor the 20-minute Decay Exit**: If a meme doesn't move within 20 minutes, close it immediately at market to avoid paying dead liquidity opportunity cost.
