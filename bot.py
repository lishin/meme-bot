import sys
import time
import signal
import logging
from web3 import Web3

import config
from trader import Trader
from scanner import Scanner
from position_manager import PositionManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("MemeBot")

running = True

def signal_handler(sig, frame):
    global running
    logger.info("Received exit signal. Shutting down gracefully...")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def main():
    logger.info("=" * 60)
    logger.info("Robinhood Chain Pons V2 Memecoin Automated Trading Bot")
    logger.info("=" * 60)

    # 1. Initialize Web3
    w3 = Web3(Web3.HTTPProvider(config.RPC_URL))
    if not w3.is_connected():
        logger.error(f"Failed to connect to RPC: {config.RPC_URL}")
        sys.exit(1)

    chain_id = w3.eth.chain_id
    latest_block = w3.eth.block_number
    logger.info(f"Connected to Chain ID: {chain_id} | Latest Block: {latest_block}")

    # 2. Components
    trader = Trader(w3)
    scanner = Scanner(w3)
    pos_manager = PositionManager()

    logger.info(f"Mode: {'[DRY RUN / SIMULATION]' if config.DRY_RUN else '[LIVE TRADING]'}")
    logger.info(f"Buy Size: {config.BUY_AMOUNT_ETH} ETH | Slippage: {config.SLIPPAGE_PCT}%")
    logger.info(f"Take Profit: +{config.TAKE_PROFIT_PCT}% | Stop Loss: -{config.STOP_LOSS_PCT}%")
    logger.info(f"Pair Filter: {config.PAIR_FILTER} | Max Open Positions: {config.MAX_ACTIVE_POSITIONS}")

    if trader.wallet_address:
        eth_bal = trader.get_eth_balance()
        logger.info(f"Wallet Address: {trader.wallet_address} (Balance: {eth_bal:.4f} ETH)")
    else:
        logger.warning("No wallet configured. Set PRIVATE_KEY in .env to trade.")

    last_scanned_block = latest_block - 10
    logger.info(f"Starting surveillance from block {last_scanned_block}...")

    # Main Loop
    last_position_check = 0

    while running:
        try:
            current_block = w3.eth.block_number

            # 1. Line C: Position & Decay Check every 10 seconds
            if time.time() - last_position_check >= 10:
                pos_manager.check_and_manage_positions(trader)
                last_position_check = time.time()

            # 2. Line A & B: Scan for new blocks
            if current_block > last_scanned_block:
                from_block = last_scanned_block + 1
                to_block = min(current_block, from_block + 50)  # Max 50 blocks per batch

                launches = scanner.scan_blocks(from_block, to_block)
                for item in launches:
                    token_addr = item["token"]
                    curve_addr = item["curve"]
                    tx_hash = item["txHash"]

                    logger.info(f"\n[NEW LAUNCH DETECTED] Token: {token_addr} | Curve: {curve_addr}")
                    logger.info(f"Tx: {tx_hash}")

                    # Line A: Filter
                    passed, reason = scanner.filter_launch(item)
                    symbol = item.get("symbol", "TOKEN")
                    name = item.get("name", "Unknown")

                    if not passed:
                        logger.warning(f"-> [ELIMINATED Line A] {symbol} ({name}): {reason}")
                        continue

                    logger.info(f"-> [PASSED Line A] {symbol} ({name}) by Dev {item['deployer'][:10]}...")

                    # Line B: Check Curve Progress
                    curve_info = scanner.check_curve_progress(curve_addr)
                    progress = curve_info["progress_pct"]
                    reserve_eth = curve_info["reserve_eth"]
                    logger.info(f"-> [Line B Check] Curve Progress: {progress:.1f}% | Reserve: {reserve_eth:.3f} ETH")

                    if progress > config.MAX_CURVE_PROGRESS:
                        logger.warning(f"-> [SKIPPED Line B] Progress {progress:.1f}% > Max {config.MAX_CURVE_PROGRESS}% (Too late/near graduation)")
                        continue

                    if progress < config.MIN_CURVE_PROGRESS:
                        logger.info(f"-> [WAITING Line B] Progress {progress:.1f}% < Min {config.MIN_CURVE_PROGRESS}%")
                        continue

                    # Check max positions limit
                    open_count = pos_manager.get_open_positions_count()
                    if open_count >= config.MAX_ACTIVE_POSITIONS:
                        logger.warning(f"-> [SKIPPED] Open positions ({open_count}) >= Max allowed ({config.MAX_ACTIVE_POSITIONS})")
                        continue

                    # Execute Automated Buy
                    logger.info(f"-> [TRIGGERING BUY] Sniping {symbol} on curve {curve_addr} with {config.BUY_AMOUNT_ETH} ETH...")
                    buy_res = trader.buy_token(curve_addr, config.BUY_AMOUNT_ETH)

                    if buy_res.get("status") in ("success", "simulated"):
                        tokens_est = buy_res.get("min_tokens", 0)
                        pos_manager.add_position(
                            token_address=token_addr,
                            curve_address=curve_addr,
                            symbol=symbol,
                            eth_spent=config.BUY_AMOUNT_ETH,
                            tokens_received=tokens_est,
                            entry_reserve_eth=reserve_eth,
                            tx_hash=buy_res.get("tx_hash", "")
                        )
                        logger.info(f"-> [POSITION OPENED] Successfully bought {symbol}!")
                    else:
                        logger.error(f"-> [BUY FAILED] Reason: {buy_res}")

                last_scanned_block = to_block

            time.sleep(config.POLL_INTERVAL_SEC)

        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
            time.sleep(5)

    logger.info("Bot exited cleanly.")

if __name__ == "__main__":
    main()
