import time
import logging
from collections import defaultdict
from web3 import Web3
import config
from abi import FACTORY_ADDRESS, TOPIC_TOKEN_LAUNCHED, CURVE_ABI, ERC20_ABI

logger = logging.getLogger("RH-Worker")

class RobinhoodWorker:
    def __init__(self, pos_manager):
        self.pos_manager = pos_manager
        self.w3 = Web3(Web3.HTTPProvider(config.RH_RPC_URL))
        self.factory = self.w3.to_checksum_address(FACTORY_ADDRESS)
        self.dev_counts = defaultdict(int)
        self.seen_tokens = set()
        self.watchlist = {}  # token -> {"curve": curve, "deployer": deployer, "symbol": sym, "created_at": ts}
        self.bought_tokens = set()
        self.last_scanned_block = None

    def initialize(self):
        if not self.w3.is_connected():
            logger.error("Failed to connect to Robinhood RPC!")
            return False
        latest = self.w3.eth.block_number
        self.last_scanned_block = latest - 10
        logger.info(f"[Robinhood Chain] Online at block {latest} | Strategy: Dynamic Watchlist -> Reserve >= {config.RH_MIN_RESERVE_ETH} ETH")
        return True

    def get_token_metadata(self, token_address: str) -> dict:
        try:
            tok = self.w3.eth.contract(address=self.w3.to_checksum_address(token_address), abi=ERC20_ABI)
            return {
                "name": tok.functions.name().call(),
                "symbol": tok.functions.symbol().call()
            }
        except Exception:
            return {"name": "Unknown", "symbol": "TOKEN"}

    def check_curve(self, curve_address: str):
        try:
            curve = self.w3.eth.contract(address=self.w3.to_checksum_address(curve_address), abi=CURVE_ABI)
            res_eth, res_token = curve.functions.getReserves().call()
            threshold = curve.functions.graduationThreshold().call()
            graduated = curve.functions.graduated().call()
            progress = (res_eth / threshold * 100.0) if threshold > 0 else 0.0
            return float(self.w3.from_wei(res_eth, "ether")), progress, graduated
        except Exception as e:
            logger.debug(f"Curve check error {curve_address}: {e}")
            return 0.0, 0.0, False

    def step(self):
        try:
            current_block = self.w3.eth.block_number
            if current_block > self.last_scanned_block:
                from_block = self.last_scanned_block + 1
                to_block = min(current_block, from_block + 40)

                logs = self.w3.eth.get_logs({
                    "fromBlock": from_block,
                    "toBlock": to_block,
                    "address": self.factory,
                    "topics": [TOPIC_TOKEN_LAUNCHED]
                })

                now = time.time()
                for log in logs:
                    token = "0x" + log.topics[1].hex()[-40:]
                    curve = "0x" + log.topics[2].hex()[-40:]
                    deployer = "0x" + log.topics[3].hex()[-40:]

                    if token in self.seen_tokens:
                        continue
                    self.seen_tokens.add(token)

                    # Line A: Dev spam filter
                    self.dev_counts[deployer.lower()] += 1
                    if self.dev_counts[deployer.lower()] > config.RH_MAX_DEV_LAUNCHES:
                        logger.debug(f"[RH Line A] Dev {deployer[:8]} spam eliminated")
                        continue

                    # Line A: Metadata & Banned keywords
                    meta = self.get_token_metadata(token)
                    sym = meta["symbol"]
                    name = meta["name"]
                    if any(b in (name + " " + sym).lower() for b in config.BANNED_KEYWORDS):
                        logger.debug(f"[RH Line A] Banned keyword in {sym}")
                        continue

                    # Add to dynamic watchlist to monitor organic bonding curve momentum
                    self.watchlist[token] = {
                        "curve": curve,
                        "deployer": deployer,
                        "symbol": sym,
                        "created_at": now
                    }
                    logger.info(f"[RH Watchlist] Added {sym} ({token[:10]}...) to active radar")

                self.last_scanned_block = to_block

            # Poll active watchlist curves for organic breakout (1.68 ETH -> >= 2.10 ETH)
            now = time.time()
            watchlist_items = list(self.watchlist.items())
            for token, info in watchlist_items:
                # Prune if expired (> 2 hours)
                if now - info["created_at"] > config.RH_WATCHLIST_TIMEOUT_SEC:
                    del self.watchlist[token]
                    continue

                curve = info["curve"]
                sym = info["symbol"]
                res_eth, progress, graduated = self.check_curve(curve)

                if res_eth > config.RH_MAX_RESERVE_ETH or graduated:
                    # Surpassed safe entry or graduated - stop tracking
                    logger.debug(f"[RH Watchlist] {sym} graduated or exceeded max reserve ({res_eth:.3f} ETH)")
                    del self.watchlist[token]
                    continue

                if res_eth >= config.RH_MIN_RESERVE_ETH:
                    # Breakout threshold reached! Check open position limit
                    if self.pos_manager.get_open_count("robinhood") >= config.MAX_POSITIONS_PER_CHAIN:
                        # Waiting for slot
                        continue

                    real_buy_eth = res_eth - config.RH_BASELINE_VIRTUAL_ETH
                    logger.info(f"[RH Line B WIN] Watchlist breakout triggered: {sym} (Real Buys: +{real_buy_eth:.3f} ETH, Reserve: {res_eth:.3f} ETH)")
                    self.pos_manager.add_position(
                        chain="robinhood",
                        token=token,
                        curve_or_pool=curve,
                        symbol=sym,
                        entry_amount=config.RH_BUY_AMOUNT_ETH,
                        unit="ETH",
                        entry_val=max(res_eth, 0.01)
                    )
                    self.bought_tokens.add(token)
                    del self.watchlist[token]

        except Exception as e:
            logger.error(f"[RH Worker] Step error: {e}")
