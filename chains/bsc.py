import time
import logging
import requests
import config

logger = logging.getLogger("BSC-Worker")

class BSCWorker:
    def __init__(self, pos_manager):
        self.pos_manager = pos_manager
        self.known_pools = set()
        self.api_url = "https://api.geckoterminal.com/api/v2/networks/bsc/new_pools?page=1"

    def initialize(self):
        try:
            r = requests.get(self.api_url, timeout=6)
            if r.status_code == 200:
                pools = r.json().get("data", [])
                for p in pools:
                    self.known_pools.add(p["attributes"]["address"].lower())
                logger.info(f"[BSC Chain] Online | Loaded {len(self.known_pools)} baseline pools")
                return True
        except Exception as e:
            logger.error(f"[BSC Worker] Init error: {e}")
        return True

    def step(self):
        try:
            r = requests.get(self.api_url, timeout=6)
            if r.status_code != 200:
                return

            pools = r.json().get("data", [])
            for p in pools:
                pool_addr = p["attributes"]["address"].lower()
                name = p["attributes"]["name"]
                if pool_addr in self.known_pools:
                    continue
                self.known_pools.add(pool_addr)

                # Line A: Banned keywords
                if any(b in name.lower() for b in config.BANNED_KEYWORDS):
                    continue

                # Line B: Liquidity & Velocity Breakout Filter
                liq_usd = float(p["attributes"].get("reserve_in_usd") or 0.0)
                txns_h1 = p["attributes"].get("transactions", {}).get("h1") or {}
                txns_m5 = p["attributes"].get("transactions", {}).get("m5") or {}
                buys_h1 = txns_h1.get("buys", 0)
                buys_m5 = txns_m5.get("buys", 0)
                vol_m5 = float(p["attributes"].get("volume_usd", {}).get("m5") or 0.0)

                # 1. Sweet-Spot Liquidity Cap ($15k <= Liq <= $65k) - prevents dead zombie whales & ultra-illiquid rugs
                if liq_usd < config.BSC_MIN_LIQ_USD or liq_usd > config.BSC_MAX_LIQ_USD:
                    continue

                # 2. 1-Hour Baseline Activity Filter
                if buys_h1 < config.BSC_MIN_BUYS:
                    continue

                # 3. 5-Minute Fresh Momentum Breakout Filter: Require immediate active buy velocity
                if buys_m5 < config.BSC_MIN_BUYS_M5 or vol_m5 < config.BSC_MIN_VOL_M5:
                    logger.debug(f"[BSC Reject Cold] {name}: m5 buys={buys_m5} (<{config.BSC_MIN_BUYS_M5}), vol_m5=${vol_m5:.0f}")
                    continue

                # Anti-Rug & Transaction Health Checks (Require >= 6 unique buyers and >= 2 real sells)
                from anti_rug import AntiRugDetector
                ok_tx, reason_tx = AntiRugDetector.check_pool_transactions(txns_h1, min_unique_buyers=6, min_sells=2)
                if not ok_tx:
                    logger.warning(f"[BSC Anti-Rug] Rejected {name}: {reason_tx}")
                    continue

                base_token = p["relationships"]["base_token"]["data"]["id"].replace("bsc_", "")
                ok_sec, reason_sec = AntiRugDetector.check_bsc_token(base_token)
                if not ok_sec:
                    logger.warning(f"[BSC Anti-Rug] Rejected {name}: {reason_sec}")
                    continue

                # On-Chain LP Lock / Burn Check (Must be >= 80% locked/burned)
                ok_lp, reason_lp = AntiRugDetector.check_bsc_lp_lock_onchain(pool_addr, config.BSC_RPC_URL)
                if not ok_lp:
                    logger.warning(f"[BSC Anti-Rug] Rejected {name}: {reason_lp}")
                    continue

                if self.pos_manager.get_open_count("bsc") >= config.MAX_POSITIONS_PER_CHAIN:
                    continue
                logger.info(f"[BSC Line B WIN] Found breakout Meme Pool: {name} (Liq: ${liq_usd:,.0f}, m5 Buys: {buys_m5}, m5 Vol: ${vol_m5:,.0f})")

                self.pos_manager.add_position(
                    chain="bsc",
                    token=base_token,
                    curve_or_pool=pool_addr,
                    symbol=name.split("/")[0].strip(),
                    entry_amount=config.BSC_BUY_AMOUNT_BNB,
                    unit="BNB",
                    entry_val=liq_usd
                )

        except Exception as e:
            logger.debug(f"[BSC Worker] Step error: {e}")
