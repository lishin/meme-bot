import time
import logging
import requests
from web3 import Web3
from eth_account import Account
import config
from abi import ARC_SWAP_ROUTER_ADDRESS, ARC_USDC_ADDRESS, SWAP_ROUTER_ABI, ERC20_ABI

logger = logging.getLogger("ARC-Worker")

class ArcTrader:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(config.ARC_RPC_URL))
        self.account = None
        self.wallet_address = None
        self.router_address = Web3.to_checksum_address(ARC_SWAP_ROUTER_ADDRESS)
        self.usdc_address = Web3.to_checksum_address(ARC_USDC_ADDRESS)
        self.router_contract = self.w3.eth.contract(address=self.router_address, abi=SWAP_ROUTER_ABI)
        self.usdc_contract = self.w3.eth.contract(address=self.usdc_address, abi=ERC20_ABI)

        pk = getattr(config, "ARC_PRIVATE_KEY", None) or config.PRIVATE_KEY
        if pk:
            try:
                if not pk.startswith("0x"):
                    pk = "0x" + pk
                self.account = Account.from_key(pk)
                self.wallet_address = self.account.address
                logger.info(f"[Arc Live Trader] Dedicated Arc Wallet initialized: {self.wallet_address}")
            except Exception as e:
                logger.error(f"[Arc Live Trader] Failed to load Arc private key: {e}")
        else:
            logger.info("[Arc Live Trader] Running in SIMULATION / DRY_RUN mode (No Arc private key set)")

    @property
    def is_dry_run(self) -> bool:
        return getattr(config, "ARC_DRY_RUN", config.DRY_RUN) or not self.account

    def get_usdc_balance(self) -> float:
        if not self.wallet_address:
            return 0.0
        try:
            bal_raw = self.usdc_contract.functions.balanceOf(self.wallet_address).call()
            return bal_raw / 1e6
        except Exception as e:
            logger.error(f"[Arc Live Trader] Error getting USDC balance: {e}")
            return 0.0

    def ensure_usdc_approved(self, amount_units: int) -> bool:
        if self.is_dry_run:
            return True
        try:
            allowance = self.usdc_contract.functions.allowance(self.wallet_address, self.router_address).call()
            if allowance >= amount_units:
                return True
            logger.info("[Arc Live Trader] Approving USDC for Arc SwapRouter...")
            tx = self.usdc_contract.functions.approve(self.router_address, 2**256 - 1).build_transaction({
                "from": self.wallet_address,
                "nonce": self.w3.eth.get_transaction_count(self.wallet_address),
                "gasPrice": int(self.w3.eth.gas_price * 1.2),
                "chainId": config.ARC_CHAIN_ID
            })
            tx["gas"] = self.w3.eth.estimate_gas(tx)
            signed = self.account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            logger.info(f"[Arc Live Trader] USDC Approval tx broadcast: {tx_hash.hex()}")
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
            return receipt.status == 1
        except Exception as e:
            logger.error(f"[Arc Live Trader] Approval failed: {e}")
            return False

    def buy_token(self, token_address: str, fee_tier: int = 10000, usdc_amount: float = 25.0) -> dict:
        if self.is_dry_run:
            return {"success": True, "tx_hash": f"SIM_ARC_BUY_{int(time.time())}", "amount_in": usdc_amount}
        try:
            token_chk = self.w3.to_checksum_address(token_address)
            amount_units = int(usdc_amount * 1e6)
            bal = self.get_usdc_balance()
            if bal < usdc_amount:
                logger.error(f"[Arc Live Trader] Insufficient USDC balance: {bal:.2f} < {usdc_amount:.2f}")
                return {"success": False, "error": "Insufficient USDC balance"}

            if not self.ensure_usdc_approved(amount_units):
                return {"success": False, "error": "USDC approval failed"}

            params = (
                self.usdc_address,
                token_chk,
                fee_tier,
                self.wallet_address,
                int(time.time()) + 180,
                amount_units,
                0,
                0
            )

            tx = self.router_contract.functions.exactInputSingle(params).build_transaction({
                "from": self.wallet_address,
                "nonce": self.w3.eth.get_transaction_count(self.wallet_address),
                "gasPrice": int(self.w3.eth.gas_price * 1.25),
                "chainId": config.ARC_CHAIN_ID
            })
            tx["gas"] = int(self.w3.eth.estimate_gas(tx) * 1.25)
            signed = self.account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            logger.info(f"[Arc LIVE BUY] Tx Broadcast: {tx_hash.hex()} | Token: {token_chk}")
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
            if receipt.status == 1:
                return {"success": True, "tx_hash": tx_hash.hex(), "amount_in": usdc_amount}
            return {"success": False, "error": "Tx reverted on-chain"}
        except Exception as e:
            logger.error(f"[Arc Live Buy Error]: {e}")
            return {"success": False, "error": str(e)}

    def sell_token(self, token_address: str, fee_tier: int = 10000) -> dict:
        if self.is_dry_run:
            return {"success": True, "tx_hash": f"SIM_ARC_SELL_{int(time.time())}"}
        try:
            token_chk = self.w3.to_checksum_address(token_address)
            tok_c = self.w3.eth.contract(address=token_chk, abi=ERC20_ABI)
            bal = tok_c.functions.balanceOf(self.wallet_address).call()
            if bal <= 0:
                return {"success": False, "error": "Zero token balance"}

            allowance = tok_c.functions.allowance(self.wallet_address, self.router_address).call()
            if allowance < bal:
                app_tx = tok_c.functions.approve(self.router_address, 2**256 - 1).build_transaction({
                    "from": self.wallet_address,
                    "nonce": self.w3.eth.get_transaction_count(self.wallet_address),
                    "gasPrice": int(self.w3.eth.gas_price * 1.2),
                    "chainId": config.ARC_CHAIN_ID
                })
                app_tx["gas"] = self.w3.eth.estimate_gas(app_tx)
                signed_app = self.account.sign_transaction(app_tx)
                h = self.w3.eth.send_raw_transaction(signed_app.raw_transaction)
                self.w3.eth.wait_for_transaction_receipt(h, timeout=30)

            params = (
                token_chk,
                self.usdc_address,
                fee_tier,
                self.wallet_address,
                int(time.time()) + 180,
                bal,
                0,
                0
            )
            tx = self.router_contract.functions.exactInputSingle(params).build_transaction({
                "from": self.wallet_address,
                "nonce": self.w3.eth.get_transaction_count(self.wallet_address),
                "gasPrice": int(self.w3.eth.gas_price * 1.25),
                "chainId": config.ARC_CHAIN_ID
            })
            tx["gas"] = int(self.w3.eth.estimate_gas(tx) * 1.25)
            signed = self.account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            logger.info(f"[Arc LIVE SELL] Tx Broadcast: {tx_hash.hex()} | Token: {token_chk}")
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
            return {"success": receipt.status == 1, "tx_hash": tx_hash.hex()}
        except Exception as e:
            logger.error(f"[Arc Live Sell Error]: {e}")
            return {"success": False, "error": str(e)}

class ArcWorker:
    def __init__(self, pos_manager):
        self.pos_manager = pos_manager
        self.trader = ArcTrader()
        self.known_pools = set()
        self.last_check = 0

    def initialize(self):
        logger.info(f"[Arc Chain] Active on Mainnet (Chain ID: {config.ARC_CHAIN_ID}, RPC: {config.ARC_RPC_URL})")
        if not self.trader.is_dry_run and self.trader.wallet_address:
            bal = self.trader.get_usdc_balance()
            logger.info(f"[Arc Chain] Live Wallet Loaded: {self.trader.wallet_address} | USDC Balance: ${bal:.2f}")
        return True

    def parse_fee_tier(self, pool_name: str) -> int:
        name_lower = pool_name.lower()
        if "0.01%" in name_lower:
            return 100
        elif "0.05%" in name_lower:
            return 500
        elif "0.25%" in name_lower or "0.3%" in name_lower:
            return 2500
        return 10000 # Default 1% pool fee tier

    def step(self):
        now = time.time()
        if now - self.last_check < 30:
            return
        self.last_check = now

        try:
            r = requests.get("https://api.geckoterminal.com/api/v2/networks/arc/new_pools", timeout=4)
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

                # Line B: Ensure real liquidity is seeded (avoid $0 / $1 ghost creation)
                liq_usd = float(p["attributes"].get("reserve_in_usd") or 0.0)
                if liq_usd < config.ARC_MIN_LIQ_USD:
                    continue

                if self.pos_manager.get_open_count("arc") >= config.MAX_POSITIONS_PER_CHAIN:
                    continue

                base_token = p["relationships"]["base_token"]["data"]["id"].replace("arc_", "")
                fee_tier = self.parse_fee_tier(name)

                # Execute Buy (Live or Simulated)
                res = self.trader.buy_token(base_token, fee_tier=fee_tier, usdc_amount=config.ARC_BUY_AMOUNT_USDC)
                if res.get("success"):
                    logger.info(f"[Arc WIN] Entered Meme Pool: {name} (Liq: ${liq_usd:,.0f}, Fee: {fee_tier}, Tx: {res.get('tx_hash')[:12]}...)")
                    self.pos_manager.add_position(
                        chain="arc",
                        token=base_token,
                        curve_or_pool=pool_addr,
                        symbol=name.split("/")[0].strip(),
                        entry_amount=config.ARC_BUY_AMOUNT_USDC,
                        unit="USD",
                        entry_val=liq_usd
                    )
        except Exception as e:
            logger.debug(f"[Arc Worker] Step error: {e}")
