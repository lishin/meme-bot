import json
import time
import logging
from pathlib import Path
import requests
from web3 import Web3
import config
from abi import CURVE_ABI
from circuit_breaker import PortfolioCircuitBreaker

logger = logging.getLogger("MultiChain-PM")

# Estimated Gas Costs in USD per trade
GAS_COSTS_USD = {
    "robinhood": 0.35,
    "bsc": 0.18,
    "solana": 0.02,
    "arc": 0.30
}

class MultiChainPositionManager:
    def __init__(self, positions_file: Path = config.POSITIONS_FILE):
        self.positions_file = positions_file
        self.positions = self.load_positions()
        self.w3_rh = Web3(Web3.HTTPProvider(config.RH_RPC_URL))
        self.circuit_breaker = PortfolioCircuitBreaker(max_stops=3, window_sec=1800, cooldown_sec=2700)

    def load_positions(self) -> list[dict]:
        if self.positions_file.exists():
            try:
                with open(self.positions_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading positions: {e}")
        return []

    def save_positions(self):
        try:
            with open(self.positions_file, "w") as f:
                json.dump(self.positions, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving positions: {e}")

    def get_open_count(self, chain: str) -> int:
        return sum(1 for p in self.positions if p.get("chain", "robinhood") == chain and p.get("status") == "OPEN")

    def can_open_new(self) -> tuple[bool, str]:
        return self.circuit_breaker.can_open_new_position()

    def add_position(self, chain: str, token: str, curve_or_pool: str, symbol: str, entry_amount: float, unit: str, entry_val: float):
        # Check Portfolio Circuit Breaker
        allowed, reason = self.can_open_new()
        if not allowed:
            logger.warning(f"[{chain.upper()}] Entry REJECTED: {reason}")
            return

        pos = {
            "chain": chain,
            "token": token,
            "curve_or_pool": curve_or_pool,
            "symbol": symbol,
            "entry_time": int(time.time()),
            "entry_amount": entry_amount,
            "unit": unit,
            "entry_val": max(entry_val, 0.001),
            "highest_val": max(entry_val, 0.001),
            "status": "OPEN",
            "exit_time": None,
            "exit_reason": None,
            "pnl_pct": 0.0,
            "gas_cost_usd": GAS_COSTS_USD.get(chain, 0.2)
        }
        self.positions.append(pos)
        self.save_positions()
        logger.info(f"[{chain.upper()}] OPENED {symbol} ({token[:10]}...) | Invested: {entry_amount} {unit}")

    def check_open_positions(self):
        now = int(time.time())
        updated = False

        for pos in self.positions:
            if pos.get("status") != "OPEN":
                continue

            chain = pos.get("chain", "robinhood")
            target = pos.get("curve_or_pool") or pos.get("curve")
            symbol = pos.get("symbol", "TOKEN")
            entry_val = pos.get("entry_val", pos.get("entry_reserve_eth", 0.001))
            entry_time = pos["entry_time"]
            hold_min = (now - entry_time) / 60.0

            curr_val = entry_val

            # 1. Real-time valuation
            if chain == "robinhood":
                try:
                    c = self.w3_rh.eth.contract(address=self.w3_rh.to_checksum_address(target), abi=CURVE_ABI)
                    res_eth, _ = c.functions.getReserves().call()
                    curr_val = float(self.w3_rh.from_wei(res_eth, "ether"))
                except Exception:
                    curr_val = entry_val
            elif chain in ("bsc", "solana", "arc"):
                try:
                    url = f"https://api.geckoterminal.com/api/v2/networks/{chain}/pools/{target}"
                    r = requests.get(url, timeout=4)
                    if r.status_code == 200:
                        curr_val = float(r.json()["data"]["attributes"].get("reserve_in_usd") or entry_val)
                except Exception:
                    curr_val = entry_val

            if curr_val > pos.get("highest_val", 0.0):
                pos["highest_val"] = curr_val

            # Gross PnL
            gain_pct = ((curr_val - entry_val) / entry_val) * 100.0 if entry_val > 0 else 0.0
            pos["pnl_pct"] = round(gain_pct, 2)

            # Peak drawdown from highest
            highest = pos.get("highest_val", curr_val)
            drawdown_from_peak = ((curr_val - highest) / highest * 100.0) if highest > 0 else 0.0

            # Exit Rule Evaluation (Adaptive + Risk Control)
            should_exit = False
            exit_reason = None

            # A. Hard Take Profit Ceiling (+250% Moonshot Target)
            if gain_pct >= config.TAKE_PROFIT_PCT:
                should_exit = True
                exit_reason = f"TAKE_PROFIT_CEILING (+{gain_pct:.1f}% >= +{config.TAKE_PROFIT_PCT}%)"

            # B. Dynamic Trailing Stop on Strong Winners (Gain reached >= 30%, exit on 15% pullback from peak)
            elif (highest - entry_val) / entry_val >= (config.TRAILING_STOP_ACTIVATION / 100.0) and drawdown_from_peak <= -config.TRAILING_STOP_CALLBACK:
                peak_gain = ((highest - entry_val) / entry_val) * 100.0
                should_exit = True
                exit_reason = f"TRAILING_STOP (Locked in +{gain_pct:.1f}% after pullback from peak +{peak_gain:.1f}%)"

            # B2. Breakeven Profit Floor Lock: If peak ever reached >= +20%, never let it fall back into a loss!
            elif ((highest - entry_val) / entry_val * 100.0) >= config.BREAKEVEN_TRIGGER_PCT and gain_pct <= config.BREAKEVEN_PROTECT_PCT:
                peak_gain = ((highest - entry_val) / entry_val) * 100.0
                should_exit = True
                exit_reason = f"BREAKEVEN_PROTECT (Peak reached +{peak_gain:.1f}%, secured profit floor at +{gain_pct:.1f}%)"

            # C. Hard Stop Loss
            elif gain_pct <= -config.STOP_LOSS_PCT:
                should_exit = True
                exit_reason = f"STOP_LOSS ({gain_pct:.1f}% <= -{config.STOP_LOSS_PCT}%)"
                self.circuit_breaker.record_stop_loss()

            # D. Adaptive Tiered Decay:
            # Tier 1: Zero/Negative traction -> cut early at 20 min
            elif hold_min >= 20.0 and gain_pct <= 2.0:
                should_exit = True
                exit_reason = f"ADAPTIVE_DECAY_TIER1 (Stagnant {hold_min:.0f}m with low gain {gain_pct:+.1f}%)"

            # Tier 2: Mediocre traction (2-15%) -> cut at 40 min
            elif hold_min >= 40.0 and gain_pct < 15.0:
                should_exit = True
                exit_reason = f"ADAPTIVE_DECAY_TIER2 (Fading {hold_min:.0f}m with gain {gain_pct:+.1f}%)"

            # Tier 3: Good momentum (>=15%) -> let it run up to 90 min
            elif hold_min >= 90.0:
                should_exit = True
                exit_reason = f"MAX_TIME_HORIZON_EXIT (Held 90m with PnL {gain_pct:+.1f}%)"

            if should_exit:
                is_arc_dry = getattr(config, "ARC_DRY_RUN", config.DRY_RUN)
                if not is_arc_dry and chain == "arc":
                    try:
                        from chains.arc import ArcTrader
                        trader = ArcTrader()
                        res_sell = trader.sell_token(pos["token"])
                        pos["sell_tx"] = res_sell.get("tx_hash")
                    except Exception as err:
                        logger.error(f"[Arc Live Sell Error] {symbol}: {err}")

                pos["status"] = "CLOSED"
                pos["exit_time"] = now
                pos["exit_reason"] = exit_reason
                updated = True
                logger.info(f"[{chain.upper()}] CLOSED {symbol} | Reason: {exit_reason} | PnL: {gain_pct:+.1f}%")

        if updated:
            self.save_positions()
