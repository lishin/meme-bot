import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# Global Execution Mode
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "").strip()
DRY_RUN = os.getenv("DRY_RUN", "true").lower() in ("true", "1", "yes")

# Line C Unified Risk Rules & Trailing Stop
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "80.0"))     # Hard TP ceiling locked at +80.0% (captures sweet-spot spikes)
TRAILING_STOP_ACTIVATION = float(os.getenv("TRAILING_STOP_ACTIVATION", "25.0")) # Activate earlier when >= +25%
TRAILING_STOP_CALLBACK = float(os.getenv("TRAILING_STOP_CALLBACK", "10.0"))     # Tighten exit: trigger on 10% pullback from peak
BREAKEVEN_TRIGGER_PCT = float(os.getenv("BREAKEVEN_TRIGGER_PCT", "18.0"))       # Activate floor lock if peak reaches >= +18%
BREAKEVEN_PROTECT_PCT = float(os.getenv("BREAKEVEN_PROTECT_PCT", "2.0"))         # Lock floor at +2%
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "20.0"))                       # -20% Stop Loss (cut early)
DECAY_MAX_HOLD_MINUTES = int(os.getenv("DECAY_MAX_HOLD_MINUTES", "30"))         # 30 min decay
MAX_POSITIONS_PER_CHAIN = int(os.getenv("MAX_POSITIONS_PER_CHAIN", "3"))
POLL_INTERVAL_SEC = float(os.getenv("POLL_INTERVAL_SEC", "3.0"))
POSITIONS_FILE = BASE_DIR / "positions.json"

BANNED_KEYWORDS = [
    "official", "airdrop", "teneo", "robinhood", "hood", "giveaway", "claim", "presale", "pump"
]

# 1. Robinhood Chain Config (Dynamic Watchlist & Barker-Style Pool Influx)
RH_RPC_URL = os.getenv("RH_RPC_URL", "https://rpc.mainnet.chain.robinhood.com")
RH_CHAIN_ID = 4663
RH_FACTORY = "0x7eD598BcEf8bd9Edd8C97A195C6d13f40801EC7e"
RH_BUY_AMOUNT_ETH = float(os.getenv("RH_BUY_AMOUNT_ETH", "0.010")) # $25 USD (@ $2500/ETH)
RH_BASELINE_VIRTUAL_ETH = 1.6800
RH_MIN_RESERVE_ETH = float(os.getenv("RH_MIN_RESERVE_ETH", "2.05")) # At least 2.05 ETH reserve
RH_MIN_DELTA_ETH = float(os.getenv("RH_MIN_DELTA_ETH", "0.10"))     # At least 0.10 ETH fresh influx while on radar
RH_MAX_RESERVE_ETH = float(os.getenv("RH_MAX_RESERVE_ETH", "2.75")) # Capped at 2.75 ETH
RH_MAX_DEV_LAUNCHES = int(os.getenv("RH_MAX_DEV_LAUNCHES", "2"))
RH_WATCHLIST_TIMEOUT_SEC = int(os.getenv("RH_WATCHLIST_TIMEOUT_SEC", "7200")) # 2 hours

SOL_ALLOWED_DEXES = ["raydium", "raydium_clmm", "raydium_cpmm", "orca"]
SOL_BANNED_DEXES = ["meteora", "meteora_damm", "meteora_dlmm", "pump_fun", "pumpswap"]

# 2. BSC Config (Barker-Style Pool Influx: Buy/Sell Dominance + 5m Velocity)
BSC_RPC_URL = os.getenv("BSC_RPC_URL", "https://bsc-dataseed.binance.org")
BSC_CHAIN_ID = 56
BSC_BUY_AMOUNT_BNB = float(os.getenv("BSC_BUY_AMOUNT_BNB", "0.043")) # $25 USD (@ $580/BNB)
BSC_MIN_LIQ_USD = float(os.getenv("BSC_MIN_LIQ_USD", "15000.0"))     # $15k - $65k sweet spot
BSC_MAX_LIQ_USD = float(os.getenv("BSC_MAX_LIQ_USD", "65000.0"))
BSC_MIN_BUYS = int(os.getenv("BSC_MIN_BUYS", "15"))                  # Min 15 buys in 1h
BSC_MIN_BUYS_M5 = int(os.getenv("BSC_MIN_BUYS_M5", "8"))            # Min 8 buys in last 5m (active surge)
BSC_MIN_VOL_M5 = float(os.getenv("BSC_MIN_VOL_M5", "4000.0"))        # Min $4,000 volume in last 5m
BSC_MIN_BUY_SELL_RATIO_M5 = float(os.getenv("BSC_MIN_BUY_SELL_RATIO_M5", "1.6")) # Buys >= 1.6x Sells
BSC_MIN_PRICE_CHANGE_M5 = float(os.getenv("BSC_MIN_PRICE_CHANGE_M5", "3.0"))     # Positive price velocity (+3%)

# 3. Solana Config (Enforce Strong Momentum: Min 35 Buys & $20k Liquidity)
SOL_RPC_URL = os.getenv("SOL_RPC_URL", "https://api.mainnet-beta.solana.com")
SOL_BUY_AMOUNT_SOL = float(os.getenv("SOL_BUY_AMOUNT_SOL", "0.18")) # $25 USD (@ $140/SOL)
SOL_MIN_LIQ_USD = float(os.getenv("SOL_MIN_LIQ_USD", "20000.0")) # Raised to $20,000 USD
SOL_MIN_BUYS = int(os.getenv("SOL_MIN_BUYS", "35"))              # Raised to 35 buys (filters dev pump spam)

# 4. Arc Chain Config (Mainnet Circle Layer-1)
ARC_RPC_URL = os.getenv("ARC_RPC_URL", "https://rpc.mainnet.arc.io")
ARC_CHAIN_ID = int(os.getenv("ARC_CHAIN_ID", "5042"))
ARC_BUY_AMOUNT_USDC = float(os.getenv("ARC_BUY_AMOUNT_USDC", "25.0")) # $25 USDC
ARC_ROUTER_ADDRESS = "0x53bf6b0684ec7ef91e1387da3d1a1769bc5a6f77"
ARC_USDC_ADDRESS = "0x3600000000000000000000000000000000000000"
ARC_MIN_LIQ_USD = float(os.getenv("ARC_MIN_LIQ_USD", "1000.0")) # Require at least $1,000 seeded liquidity
ARC_SLIPPAGE_PCT = float(os.getenv("ARC_SLIPPAGE_PCT", "15.0"))
ARC_PRIVATE_KEY = os.getenv("ARC_PRIVATE_KEY", "").strip() or PRIVATE_KEY
ARC_DRY_RUN = os.getenv("ARC_DRY_RUN", str(DRY_RUN)).lower() in ("true", "1", "yes")

