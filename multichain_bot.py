import sys
import time
import signal
import logging

import config
from multichain_manager import MultiChainPositionManager
from chains.robinhood import RobinhoodWorker
from chains.bsc import BSCWorker
from chains.solana import SolanaWorker
from chains.arc import ArcWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("MultiChainBot")

running = True

def signal_handler(sig, frame):
    global running
    logger.info("Shutdown requested. Gracefully exiting...")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def main():
    logger.info("=" * 65)
    logger.info("   4-CHAIN MEMECOIN TRADING BOT (ROBINHOOD, BSC, SOLANA, ARC)")
    logger.info("=" * 65)
    logger.info(f"Mode: {'[PAPER TRADING / DRY_RUN]' if config.DRY_RUN else '[LIVE TRADING]'}")
    logger.info(f"Rules: Trailing Stop (Active >= +{config.TRAILING_STOP_ACTIVATION}%, Callback {config.TRAILING_STOP_CALLBACK}%) | Hard TP: +{config.TAKE_PROFIT_PCT}% | SL: -{config.STOP_LOSS_PCT}%")
    logger.info(f"Robinhood Strategy: Min Reserve >= {config.RH_MIN_RESERVE_ETH} ETH (Real buys > 1.68 baseline) | Max Dev: {config.RH_MAX_DEV_LAUNCHES}")
    logger.info(f"BSC Strategy: Min Liq >= ${config.BSC_MIN_LIQ_USD:,.0f} | Min Buys: {config.BSC_MIN_BUYS}")
    logger.info(f"Solana Strategy: Min Liq >= ${config.SOL_MIN_LIQ_USD:,.0f} | Min Buys: {config.SOL_MIN_BUYS}")
    logger.info(f"Arc Strategy: Sentinel Active (Awaiting Sept 16 Mainnet Pools)")

    pos_manager = MultiChainPositionManager()

    rh_worker = RobinhoodWorker(pos_manager)
    bsc_worker = BSCWorker(pos_manager)
    sol_worker = SolanaWorker(pos_manager)
    arc_worker = ArcWorker(pos_manager)

    rh_ok = rh_worker.initialize()
    bsc_ok = bsc_worker.initialize()
    sol_ok = sol_worker.initialize()
    arc_ok = arc_worker.initialize()

    last_pos_check = 0
    logger.info("All 4 Chain Workers running surveillance concurrently...")

    while running:
        try:
            # 1. Step individual chain workers
            if rh_ok:
                rh_worker.step()
            if bsc_ok:
                bsc_worker.step()
            if sol_ok:
                sol_worker.step()
            if arc_ok:
                arc_worker.step()

            # 2. Check Line C positions across all 4 chains
            now = time.time()
            if now - last_pos_check >= 10:
                pos_manager.check_open_positions()
                last_pos_check = now

            time.sleep(config.POLL_INTERVAL_SEC)

        except Exception as e:
            logger.error(f"Error in main bot loop: {e}")
            time.sleep(3)

    logger.info("Multi-Chain Bot terminated cleanly.")

if __name__ == "__main__":
    main()
