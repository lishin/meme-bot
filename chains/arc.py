import time
import logging
import requests
import config

logger = logging.getLogger("ARC-Worker")

class ArcWorker:
    def __init__(self, pos_manager):
        self.pos_manager = pos_manager
        self.known_pools = set()
        self.last_check = 0

    def initialize(self):
        logger.info("[Arc Chain] Sentinel Active | Monitoring GMGN & Arc Launchpad readiness (Target: Sept 16 Mainnet)")
        return True

    def step(self):
        # Poll every 60 seconds for Arc network emergence on DEX aggregators
        now = time.time()
        if now - self.last_check < 60:
            return
        self.last_check = now

        try:
            r = requests.get("https://api.geckoterminal.com/api/v2/networks/arc/new_pools", timeout=4)
            if r.status_code == 200:
                pools = r.json().get("data", [])
                for p in pools:
                    pool_addr = p["attributes"]["address"]
                    name = p["attributes"]["name"]
                    if pool_addr in self.known_pools:
                        continue
                    self.known_pools.add(pool_addr)
                    logger.info(f"[Arc Mainnet LIVE!] Detected first pool: {name}")
                    self.pos_manager.add_position(
                        chain="arc",
                        token=p["relationships"]["base_token"]["data"]["id"],
                        curve_or_pool=pool_addr,
                        symbol=name.split("/")[0].strip(),
                        entry_amount=config.ARC_BUY_AMOUNT,
                        unit="ETH",
                        entry_val=float(p["attributes"].get("reserve_in_usd") or 1.0)
                    )
        except Exception:
            # Standby state expected prior to mainnet deployment
            pass
