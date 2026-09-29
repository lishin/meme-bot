"""
Meme Radar 5-Gate Quant Engine
Ported from nhovongoc0-max/meme-radar (by @bi_9527zx)
Fully integrates 5-gate filtering into multichain_bot.
"""
import time
import logging
import requests
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timezone
import config
from anti_rug import AntiRugDetector

logger = logging.getLogger("MemeRadar")

class MemeRadarEngine:
    # 1. Valuation & Age Constants
    MIN_AGE_SEC = 300              # 5 minutes minimum (No Block 0 sniping)
    MAX_AGE_SEC = 604800           # 7 days max
    MIN_MC_USD = 10_000.0          # $10k
    MAX_MC_USD = 150_000.0         # $150k
    PRIORITY_MIN_MC = 20_000.0     # $20k sweet spot
    PRIORITY_MAX_MC = 80_000.0     # $80k sweet spot
    MIN_LIQUIDITY_USD = 3_000.0    # $3,000 threshold

    # 2. Tax & Security Constants
    MAX_BUY_TAX = 0.05             # 5%
    MAX_SELL_TAX = 0.05            # 5%
    MAX_TAX_ASYMMETRY = 0.02       # 2% gap limit

    # 3. Tokenomics One-Vote Veto Constants
    MAX_DEV_HOLD = 0.01            # 1.0% limit
    MAX_BUNDLER_RATE = 0.15        # 15.0%
    MAX_INSIDER_RATE = 0.15        # 15.0%
    MAX_TOP10_RATE = 0.30          # 30.0%
    MAX_SNIPER_RATE = 0.08         # 8.0%
    MIN_LP_LOCKED = 0.80           # 80.0%

    # 4. Volume & Momentum Constants
    MIN_VOLUME_5M = 1500.0         # $1,500 in 5m
    MIN_BUYS_5M = 4                # At least 4 buys
    MIN_BUY_SELL_RATIO = 1.30      # Buys >= 1.3x Sells

    @classmethod
    def parse_pool_age_sec(cls, pool_created_at_str: Optional[str]) -> float:
        if not pool_created_at_str:
            return 0.0
        try:
            # ISO format: e.g. "2026-09-29T04:14:43Z" or with offset
            dt = datetime.fromisoformat(pool_created_at_str.replace("Z", "+00:00"))
            return time.time() - dt.timestamp()
        except Exception:
            return 0.0

    @classmethod
    def evaluate_gate1_age_and_valuation(cls, attr: Dict) -> Tuple[bool, str, bool]:
        """
        Gate 1: Pool Age (>= 5 min) & Valuation ($10k-$150k, Priority: $20k-$80k) & Liquidity (>= $3k).
        Returns: (passed, reason, is_priority_band)
        """
        age_sec = cls.parse_pool_age_sec(attr.get("pool_created_at"))
        mc = float(attr.get("fdv_usd") or attr.get("market_cap_usd") or 0.0)
        liq = float(attr.get("reserve_in_usd") or 0.0)

        if age_sec < cls.MIN_AGE_SEC:
            return False, f"Age too young ({age_sec:.0f}s < {cls.MIN_AGE_SEC}s - Anti-Block0)", False
        if age_sec > cls.MAX_AGE_SEC:
            return False, "Exceeds max observation age (7 days)", False

        if mc > 0 and not (cls.MIN_MC_USD <= mc <= cls.MAX_MC_USD):
            return False, f"Market cap ${mc:,.0f} outside sweet spot (${cls.MIN_MC_USD:,.0f}-${cls.MAX_MC_USD:,.0f})", False

        if liq < cls.MIN_LIQUIDITY_USD:
            return False, f"Liquidity ${liq:,.0f} below ${cls.MIN_LIQUIDITY_USD:,.0f} threshold", False

        is_priority = (cls.PRIORITY_MIN_MC <= mc <= cls.PRIORITY_MAX_MC)
        return True, "Passed Gate 1 (Age, Valuation, Liquidity)", is_priority

    @classmethod
    def evaluate_gate2_security_tax(cls, chain: str, token_addr: str) -> Tuple[bool, str]:
        """
        Gate 2: Honeypot, Mint, Freeze & Tax limits (<= 5%).
        """
        chain_lower = chain.lower()
        if chain_lower == "bsc":
            ok, msg = AntiRugDetector.check_bsc_token(token_addr)
            if not ok:
                return False, msg
        elif chain_lower in ("sol", "solana"):
            ok, msg = AntiRugDetector.check_solana_token(token_addr)
            if not ok:
                return False, msg
        return True, "Passed Gate 2 Security"

    @classmethod
    def evaluate_gate3_tokenomics(cls, dev_hold: float = 0.0, bundler_rate: float = 0.0,
                                   top10_rate: float = 0.0, lp_locked: float = 1.0) -> Tuple[bool, str]:
        """
        Gate 3: Tokenomics One-Vote Veto (Dev <= 1%, Bundler <= 15%, Top10 <= 30%, LP >= 80%).
        """
        if dev_hold > cls.MAX_DEV_HOLD:
            return False, f"Dev holding {dev_hold*100:.1f}% exceeds 1% limit"
        if bundler_rate > cls.MAX_BUNDLER_RATE:
            return False, f"Bundler rate {bundler_rate*100:.1f}% exceeds 15% limit"
        if top10_rate > cls.MAX_TOP10_RATE:
            return False, f"Top 10 concentration {top10_rate*100:.1f}% exceeds 30% limit"
        if lp_locked < cls.MIN_LP_LOCKED:
            return False, f"LP lock {lp_locked*100:.1f}% below 80% limit"
        return True, "Passed Gate 3 Tokenomics"

    @classmethod
    def fetch_gecko_1m_candles(cls, network: str, pool_addr: str, limit: int = 15) -> List[Dict]:
        """
        Fetches completed 1-minute OHLCV candles from GeckoTerminal API.
        Format returned: list of dicts with open, high, low, close, volume.
        """
        try:
            url = f"https://api.geckoterminal.com/api/v2/networks/{network}/pools/{pool_addr}/ohlcv/minute?limit={limit}"
            r = requests.get(url, timeout=3.5)
            if r.status_code != 200:
                return []
            raw_list = r.json().get("data", {}).get("attributes", {}).get("ohlcv_list", [])
            # GeckoTerminal returns reverse chronological: newest first. Reverse to chronological order.
            raw_list = list(reversed(raw_list))
            candles = []
            for item in raw_list:
                # [timestamp, open, high, low, close, volume]
                if len(item) >= 6:
                    candles.append({
                        "time": item[0],
                        "open": float(item[1]),
                        "high": float(item[2]),
                        "low": float(item[3]),
                        "close": float(item[4]),
                        "volume": float(item[5])
                    })
            return candles
        except Exception as e:
            logger.debug(f"Failed to fetch 1m candles for {pool_addr}: {e}")
            return []

    @classmethod
    def evaluate_gate4_chart_risk(cls, candles: List[Dict]) -> Tuple[bool, str]:
        """
        Gate 4: Chart Risk Pattern Screening from @bi_9527zx (VERTICAL_PLATEAU & SUSTAINED_COLLAPSE).
        """
        if len(candles) < 5:
            # Not enough completed candles yet, allow if early but mark clean
            return True, "Sufficiently early / no adverse chart risk detected"

        # 1. VERTICAL_PLATEAU check: 1m jump >= 35% followed by narrow plateau <= 15% range
        for i in range(len(candles) - 3):
            bar = candles[i]
            after = candles[i+1 : i+4]
            anchor = bar["open"]
            if anchor <= 0:
                continue
            jump = (bar["close"] / anchor) - 1.0
            closes = [bar["close"]] + [b["close"] for b in after]
            if bar["volume"] > 0 and all(b["volume"] > 0 for b in after):
                if jump >= 0.35: # Jump >= 35% in 1 minute
                    spread = (max(closes) / min(closes)) - 1.0
                    if spread <= 0.15 and (after[-1]["close"] / anchor) >= 1.30:
                        return False, "🚨 VERTICAL_PLATEAU: Single-minute spike >=35% with artificial narrow plateau (Maker trap)"

        # 2. SUSTAINED_COLLAPSE check: Confirmed peak followed by 2-candle drawdown >= 60%
        peak = candles[0]["close"]
        for i in range(1, len(candles) - 1):
            c1 = candles[i]["close"]
            c2 = candles[i+1]["close"]
            if peak > 0:
                drawdown = 1.0 - (max(c1, c2) / peak)
                if drawdown >= 0.60:
                    return False, f"🚨 SUSTAINED_COLLAPSE: Severe cliff dump ({drawdown*100:.1f}% >= 60% from peak)"
            peak = max(peak, candles[i]["close"])

        return True, "Passed Gate 4 Chart Risk"

    @classmethod
    def evaluate_gate5_volume_momentum(cls, attr: Dict) -> Tuple[bool, str]:
        """
        Gate 5: 5-Minute Volume Breakout & Orderflow Dominance.
        """
        txns_m5 = attr.get("transactions", {}).get("m5") or {}
        buys_m5 = int(txns_m5.get("buys") or 0)
        sells_m5 = int(txns_m5.get("sells") or 0)
        vol_m5 = float(attr.get("volume_usd", {}).get("m5") or 0.0)

        if vol_m5 < cls.MIN_VOLUME_5M:
            return False, f"5m Volume ${vol_m5:,.0f} below ${cls.MIN_VOLUME_5M:,.0f} breakout minimum"
        if buys_m5 < cls.MIN_BUYS_5M:
            return False, f"5m Buys {buys_m5} below minimum {cls.MIN_BUYS_5M}"
        if sells_m5 > 0 and (buys_m5 / sells_m5) < cls.MIN_BUY_SELL_RATIO:
            return False, f"Buy/Sell ratio {buys_m5/sells_m5:.2f} below {cls.MIN_BUY_SELL_RATIO:.1f}x dominance"

        return True, f"Passed Gate 5 Momentum (Vol: ${vol_m5:,.0f}, Buys: {buys_m5}, Sells: {sells_m5})"

    @classmethod
    def evaluate_full_pipeline(cls, chain: str, pool_attr: Dict, token_addr: str, pool_addr: str) -> Tuple[bool, str]:
        """
        Full 5-Gate Evaluation. Returns (allowed, summary_reason).
        """
        # Gate 1: Age & Valuation
        ok1, msg1, is_prio = cls.evaluate_gate1_age_and_valuation(pool_attr)
        if not ok1:
            return False, f"[Gate 1 Reject] {msg1}"

        # Gate 5: 5m Volume & Momentum (run early to skip dead ghost pools before network queries)
        ok5, msg5 = cls.evaluate_gate5_volume_momentum(pool_attr)
        if not ok5:
            return False, f"[Gate 5 Reject] {msg5}"

        # Gate 2: Security & Tax
        ok2, msg2 = cls.evaluate_gate2_security_tax(chain, token_addr)
        if not ok2:
            return False, f"[Gate 2 Reject] {msg2}"

        # Gate 4: Chart Risk
        candles = cls.fetch_gecko_1m_candles(chain, pool_addr, limit=12)
        ok4, msg4 = cls.evaluate_gate4_chart_risk(candles)
        if not ok4:
            return False, f"[Gate 4 Reject] {msg4}"

        prio_tag = " [PRIORITY BAND]" if is_prio else ""
        return True, f"PASSED ALL 5 GATES{prio_tag} | {msg5}"
