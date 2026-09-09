import json
import time
import logging
from pathlib import Path
import config
from trader import Trader

logger = logging.getLogger("PositionManager")

class PositionManager:
    def __init__(self, positions_file: Path = config.POSITIONS_FILE):
        self.positions_file = positions_file
        self.positions = self.load_positions()

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

    def get_open_positions_count(self) -> int:
        return sum(1 for p in self.positions if p.get("status") == "OPEN")

    def add_position(self, token_address: str, curve_address: str, symbol: str, eth_spent: float, tokens_received: int, entry_reserve_eth: float, tx_hash: str):
        pos = {
            "token": token_address,
            "curve": curve_address,
            "symbol": symbol,
            "entry_time": int(time.time()),
            "entry_eth": eth_spent,
            "tokens_bought": tokens_received,
            "entry_reserve_eth": max(entry_reserve_eth, 0.001),
            "highest_reserve_eth": max(entry_reserve_eth, 0.001),
            "status": "OPEN",
            "buy_tx": tx_hash,
            "exit_tx": None,
            "exit_reason": None,
            "pnl_pct": 0.0
        }
        self.positions.append(pos)
        self.save_positions()
        logger.info(f"Position opened for {symbol} ({token_address}) - Invested: {eth_spent} ETH")

    def check_and_manage_positions(self, trader: Trader):
        """
        Line C Automation:
        Monitors open positions, calculates PnL, executes Take-Profit, Stop-Loss, or Decay Exits.
        """
        now = int(time.time())
        updated = False

        for pos in self.positions:
            if pos.get("status") != "OPEN":
                continue

            curve_addr = pos["curve"]
            tok_addr = pos["token"]
            symbol = pos.get("symbol", "TOKEN")
            entry_reserve = pos["entry_reserve_eth"]
            entry_time = pos["entry_time"]
            hold_minutes = (now - entry_time) / 60.0

            res_eth, res_tok, threshold, graduated = trader.get_curve_reserves(curve_addr)
            curr_reserve_eth = float(trader.w3.from_wei(res_eth, "ether"))

            if curr_reserve_eth > pos.get("highest_reserve_eth", 0.0):
                pos["highest_reserve_eth"] = curr_reserve_eth

            # Calculate reserve-based price change as proxy for bonding curve PnL
            gain_pct = ((curr_reserve_eth - entry_reserve) / entry_reserve) * 100.0
            pos["pnl_pct"] = round(gain_pct, 2)

            logger.info(
                f"[Line C Tracker] {symbol} | Reserve: {curr_reserve_eth:.3f} ETH | "
                f"PnL: {gain_pct:+.1f}% | Held: {hold_minutes:.1f}m | Graduated: {graduated}"
            )

            should_exit = False
            exit_reason = None

            # 1. Take Profit
            if gain_pct >= config.TAKE_PROFIT_PCT:
                should_exit = True
                exit_reason = f"TAKE_PROFIT (+{gain_pct:.1f}% >= +{config.TAKE_PROFIT_PCT}%)"

            # 2. Stop Loss
            elif gain_pct <= -config.STOP_LOSS_PCT:
                should_exit = True
                exit_reason = f"STOP_LOSS ({gain_pct:.1f}% <= -{config.STOP_LOSS_PCT}%)"

            # 3. Decay Timeout (held longer than limit and underperforming)
            elif hold_minutes >= config.DECAY_MAX_HOLD_MINUTES and gain_pct < 15.0:
                should_exit = True
                exit_reason = f"DECAY_TIMEOUT (Held {hold_minutes:.0f}m >= {config.DECAY_MAX_HOLD_MINUTES}m with low gain {gain_pct:+.1f}%)"

            # 4. Curve Graduated - Lock profits before liquidity migration
            elif graduated:
                should_exit = True
                exit_reason = f"GRADUATION_TRIGGER (Curve hit threshold -> locking profits)"

            if should_exit:
                logger.warning(f"Exiting position for {symbol}! Reason: {exit_reason}")
                tokens_to_sell = pos.get("tokens_bought", 0)

                # Query on-chain wallet balance if live
                if not config.DRY_RUN and trader.wallet_address:
                    actual_bal = trader.get_token_balance(tok_addr)
                    if actual_bal > 0:
                        tokens_to_sell = actual_bal

                sell_res = trader.sell_token(curve_addr, tok_addr, tokens_to_sell)
                if sell_res.get("status") in ("success", "simulated"):
                    pos["status"] = "CLOSED"
                    pos["exit_tx"] = sell_res.get("tx_hash")
                    pos["exit_reason"] = exit_reason
                    pos["exit_time"] = now
                    updated = True
                    logger.info(f"Position for {symbol} CLOSED successfully! Reason: {exit_reason}")
                else:
                    logger.error(f"Failed to sell {symbol}: {sell_res}")

        if updated:
            self.save_positions()
