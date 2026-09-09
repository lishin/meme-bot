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
# Accept 3: Open Profit Ceiling to +250% and ride winners with dynamic Trailing Stop
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "250.0"))   # Hard TP ceiling +250%
TRAILING_STOP_ACTIVATION = float(os.getenv("TRAILING_STOP_ACTIVATION", "30.0")) # Activate when >= +30%
TRAILING_STOP_CALLBACK = float(os.getenv("TRAILING_STOP_CALLBACK", "15.0"))   # Exit if drops 15% from peak
BREAKEVEN_TRIGGER_PCT = float(os.getenv("BREAKEVEN_TRIGGER_PCT", "20.0")) # Activate floor lock if peak reaches >= +20%
BREAKEVEN_PROTECT_PCT = float(os.getenv("BREAKEVEN_PROTECT_PCT", "2.0"))   # Never let a +20% winner turn into a loss (clamp floor at +2%)
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "25.0"))       # -25% Hard Stop Loss
DECAY_MAX_HOLD_MINUTES = int(os.getenv("DECAY_MAX_HOLD_MINUTES", "30")) # 30 min decay
MAX_POSITIONS_PER_CHAIN = int(os.getenv("MAX_POSITIONS_PER_CHAIN", "3"))
POLL_INTERVAL_SEC = float(os.getenv("POLL_INTERVAL_SEC", "3.0"))
POSITIONS_FILE = BASE_DIR / "positions.json"

BANNED_KEYWORDS = [
    "official", "airdrop", "teneo", "robinhood", "hood", "giveaway", "claim", "presale", "pump"
]

# 1. Robinhood Chain Config (Deeply Refined)
# Note: Pons V2 curve starts with 1.68 ETH virtual baseline.
# Real external buying requires reserve > 2.10 ETH (at least 0.42 ETH real external buying)
RH_RPC_URL = os.getenv("RH_RPC_URL", "https://rpc.mainnet.chain.robinhood.com")
RH_CHAIN_ID = 4663
RH_FACTORY = "0x7eD598BcEf8bd9Edd8C97A195C6d13f40801EC7e"
RH_BUY_AMOUNT_ETH = float(os.getenv("RH_BUY_AMOUNT_ETH", "0.010")) # $25 USD (@ $2500/ETH)
RH_BASELINE_VIRTUAL_ETH = 1.6800
RH_MIN_RESERVE_ETH = float(os.getenv("RH_MIN_RESERVE_ETH", "2.10")) # Raised to 2.10 ETH (+0.42 ETH real buying)
RH_MAX_RESERVE_ETH = float(os.getenv("RH_MAX_RESERVE_ETH", "2.75")) # Capped at 2.75 ETH (Avoids late-stage graduation dump)
RH_MAX_DEV_LAUNCHES = int(os.getenv("RH_MAX_DEV_LAUNCHES", "2"))
RH_WATCHLIST_TIMEOUT_SEC = int(os.getenv("RH_WATCHLIST_TIMEOUT_SEC", "7200")) # Track candidate curves for up to 2 hours

SOL_ALLOWED_DEXES = ["raydium", "raydium_clmm", "raydium_cpmm", "orca"]
SOL_BANNED_DEXES = ["meteora", "meteora_damm", "meteora_dlmm", "pump_fun", "pumpswap"]

# 2. BSC Config (Enforced On-Chain LP Lock >= 80% & Strong 5-Min Velocity Breakout)
BSC_RPC_URL = os.getenv("BSC_RPC_URL", "https://bsc-dataseed.binance.org")
BSC_CHAIN_ID = 56
BSC_BUY_AMOUNT_BNB = float(os.getenv("BSC_BUY_AMOUNT_BNB", "0.043")) # $25 USD (@ $580/BNB)
BSC_MIN_LIQ_USD = float(os.getenv("BSC_MIN_LIQ_USD", "15000.0"))     # Raised to $15,000 USD
BSC_MAX_LIQ_USD = float(os.getenv("BSC_MAX_LIQ_USD", "65000.0"))     # Capped at $65,000 USD (Sweet spot momentum)
BSC_MIN_BUYS = int(os.getenv("BSC_MIN_BUYS", "15"))                  # Min 15 buys in 1h
BSC_MIN_BUYS_M5 = int(os.getenv("BSC_MIN_BUYS_M5", "6"))            # Min 6 buys in last 5m (active breakout)
BSC_MIN_VOL_M5 = float(os.getenv("BSC_MIN_VOL_M5", "3000.0"))        # Min $3,000 volume in last 5m

# 3. Solana Config (Enforce Strong Momentum: Min 35 Buys & $20k Liquidity)
SOL_RPC_URL = os.getenv("SOL_RPC_URL", "https://api.mainnet-beta.solana.com")
SOL_BUY_AMOUNT_SOL = float(os.getenv("SOL_BUY_AMOUNT_SOL", "0.18")) # $25 USD (@ $140/SOL)
SOL_MIN_LIQ_USD = float(os.getenv("SOL_MIN_LIQ_USD", "20000.0")) # Raised to $20,000 USD
SOL_MIN_BUYS = int(os.getenv("SOL_MIN_BUYS", "35"))              # Raised to 35 buys (filters dev pump spam)

# 4. Arc Chain Config (Standby Readiness)
ARC_RPC_URL = os.getenv("ARC_RPC_URL", "https://rpc.arc.network")
ARC_CHAIN_ID = int(os.getenv("ARC_CHAIN_ID", "42161"))
ARC_BUY_AMOUNT = float(os.getenv("ARC_BUY_AMOUNT", "0.010")) # $25 USD
