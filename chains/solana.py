import time
import logging
import requests
import config

logger = logging.getLogger("SOL-Worker")

class SolanaWorker:
    def __init__(self, pos_manager):
        self.pos_manager = pos_manager
        self.known_pools = set()
        self.api_url = "https://api.geckoterminal.com/api/v2/networks/solana/new_pools?page=1"

    def initialize(self):
        try:
            r = requests.get(self.api_url, timeout=6)
            if r.status_code == 200:
                pools = r.json().get("data", [])
                for p in pools:
                    self.known_pools.add(p["attributes"]["address"])
                logger.info(f"[Solana Chain] Online | Loaded {len(self.known_pools)} baseline pools")
                return True
        except Exception as e:
            logger.error(f"[Solana Worker] Init error: {e}")
        return True

    def step(self):
        try:
            r = requests.get(self.api_url, timeout=6)
            if r.status_code != 200:
                return

            pools = r.json().get("data", [])
            for p in pools:
                pool_addr = p["attributes"]["address"]
                name = p["attributes"]["name"]
                if pool_addr in self.known_pools:
                    continue
                self.known_pools.add(pool_addr)

                # Line A: Banned keywords
                if any(b in name.lower() for b in config.BANNED_KEYWORDS):
                    continue

                # Line A2: Enforce Raydium & Orca (Graduated pools only, reject unbonded Pump.fun curves and Meteora)
                dex_id = p.get("relationships", {}).get("dex", {}).get("data", {}).get("id", "").lower()
                if not any(allowed in dex_id for allowed in config.SOL_ALLOWED_DEXES):
                    logger.warning(f"[SOL Anti-Rug] Rejected {name}: Banned DEX/Internal Curve ({dex_id})")
                    continue

                # Line B: Liquidity & Activity Filter
                liq_usd = float(p["attributes"].get("reserve_in_usd") or 0.0)
                txns = p["attributes"].get("transactions", {}).get("h1") or p["attributes"].get("transactions", {}).get("m5") or {}
                buys = txns.get("buys", 0)

                if liq_usd < config.SOL_MIN_LIQ_USD or buys < config.SOL_MIN_BUYS:
                    # Reject zero-volume ghost pools
                    continue

                # Anti-Rug & Transaction Health Checks (Require >= 12 unique buyers and >= 3 real sells)
                from anti_rug import AntiRugDetector
                ok_tx, reason_tx = AntiRugDetector.check_pool_transactions(txns, min_unique_buyers=12, min_sells=3)
                if not ok_tx:
                    logger.warning(f"[SOL Anti-Rug] Rejected {name}: {reason_tx}")
                    continue

                base_token = p["relationships"]["base_token"]["data"]["id"].replace("solana_", "")
                ok_sec, reason_sec = AntiRugDetector.check_solana_token(base_token)
                if not ok_sec:
                    logger.warning(f"[SOL Anti-Rug] Rejected {name}: {reason_sec}")
                    continue

                if self.pos_manager.get_open_count("solana") >= config.MAX_POSITIONS_PER_CHAIN:
                    continue
                logger.info(f"[Solana Line B WIN] Found active Solana Meme Pool: {name} (Liq: ${liq_usd:,.0f}, Buys: {buys})")

                self.pos_manager.add_position(
                    chain="solana",
                    token=base_token,
                    curve_or_pool=pool_addr,
                    symbol=name.split("/")[0].strip(),
                    entry_amount=config.SOL_BUY_AMOUNT_SOL,
                    unit="SOL",
                    entry_val=liq_usd
                )

        except Exception as e:
            logger.debug(f"[Solana Worker] Step error: {e}")
