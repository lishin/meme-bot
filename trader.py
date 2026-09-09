import time
import logging
from web3 import Web3
from eth_account import Account
import config
from abi import CURVE_ABI, ERC20_ABI

logger = logging.getLogger("Trader")

class Trader:
    def __init__(self, w3: Web3):
        self.w3 = w3
        self.account = None
        self.wallet_address = None

        if config.PRIVATE_KEY:
            try:
                # Ensure 0x prefix
                pk = config.PRIVATE_KEY
                if not pk.startswith("0x"):
                    pk = "0x" + pk
                self.account = Account.from_key(pk)
                self.wallet_address = self.account.address
                logger.info(f"Wallet loaded: {self.wallet_address}")
            except Exception as e:
                logger.error(f"Failed to load private key: {e}")
        else:
            logger.warning("No PRIVATE_KEY provided in .env. Bot running in VIEW/SIMULATION mode.")

    def get_eth_balance(self) -> float:
        if not self.wallet_address:
            return 0.0
        wei = self.w3.eth.get_balance(self.wallet_address)
        return float(self.w3.from_wei(wei, "ether"))

    def get_token_balance(self, token_address: str) -> int:
        if not self.wallet_address:
            return 0
        token_contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(token_address),
            abi=ERC20_ABI
        )
        return token_contract.functions.balanceOf(self.wallet_address).call()

    def get_curve_reserves(self, curve_address: str):
        curve_contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(curve_address),
            abi=CURVE_ABI
        )
        try:
            reserve_eth, reserve_token = curve_contract.functions.getReserves().call()
            threshold = curve_contract.functions.graduationThreshold().call()
            graduated = curve_contract.functions.graduated().call()
            return reserve_eth, reserve_token, threshold, graduated
        except Exception as e:
            logger.error(f"Error reading reserves for curve {curve_address}: {e}")
            return 0, 0, 0, False

    def buy_token(self, curve_address: str, eth_amount: float) -> dict:
        """
        Executes buy on Pons V2 Bonding Curve:
        buy(uint256 ethIn, uint256 minTokensOut, address recipient) payable
        """
        curve_addr = self.w3.to_checksum_address(curve_address)
        eth_wei = self.w3.to_wei(eth_amount, "ether")

        # Read reserves to estimate tokens out
        res_eth, res_token, threshold, graduated = self.get_curve_reserves(curve_addr)
        if graduated:
            logger.warning(f"Curve {curve_address} has already graduated! Skipping curve buy.")
            return {"status": "failed", "reason": "already_graduated"}

        # Estimated tokens out (Constant product or curve formula approx)
        if res_eth > 0 and res_token > 0:
            # k = res_eth * res_token
            # new_eth = res_eth + eth_wei
            # new_token = k / new_eth
            # tokens_out = res_token - new_token
            new_eth = res_eth + eth_wei
            tokens_out_est = (res_token * eth_wei) // new_eth
            min_tokens_out = int(tokens_out_est * (1.0 - config.SLIPPAGE_PCT / 100.0))
        else:
            min_tokens_out = 0

        logger.info(f"Preparing BUY on curve {curve_address} for {eth_amount} ETH (min tokens: {min_tokens_out})")

        if config.DRY_RUN or not self.account:
            logger.info(f"[DRY_RUN] Simulated BUY {eth_amount} ETH -> minTokens: {min_tokens_out}")
            return {
                "status": "simulated",
                "tx_hash": "0xSIMULATED_BUY_" + str(int(time.time())),
                "eth_spent": eth_amount,
                "min_tokens": min_tokens_out
            }

        # Live Execution
        balance = self.get_eth_balance()
        if balance < eth_amount + 0.0005:
            logger.error(f"Insufficient ETH balance ({balance:.4f} ETH) for buy ({eth_amount} ETH + gas)")
            return {"status": "failed", "reason": "insufficient_balance"}

        try:
            curve_contract = self.w3.eth.contract(address=curve_addr, abi=CURVE_ABI)
            nonce = self.w3.eth.get_transaction_count(self.wallet_address)
            gas_price = int(self.w3.eth.gas_price * 1.25)  # 25% buffer for fast execution

            tx_data = curve_contract.functions.buy(
                eth_wei,
                min_tokens_out,
                self.wallet_address
            ).build_transaction({
                "chainId": config.CHAIN_ID,
                "from": self.wallet_address,
                "value": eth_wei,
                "gas": 350000,
                "gasPrice": gas_price,
                "nonce": nonce
            })

            signed_tx = self.account.sign_transaction(tx_data)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            logger.info(f"Buy Tx broadcasted! Hash: {tx_hash.hex()}")

            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            if receipt.status == 1:
                logger.info(f"BUY CONFIRMED! Tx: {tx_hash.hex()} in block {receipt.blockNumber}")
                return {
                    "status": "success",
                    "tx_hash": tx_hash.hex(),
                    "eth_spent": eth_amount,
                    "block": receipt.blockNumber
                }
            else:
                logger.error(f"BUY REVERTED on-chain! Tx: {tx_hash.hex()}")
                return {"status": "reverted", "tx_hash": tx_hash.hex()}

        except Exception as e:
            logger.error(f"Exception during BUY execution: {e}")
            return {"status": "error", "error": str(e)}

    def sell_token(self, curve_address: str, token_address: str, token_amount: int) -> dict:
        """
        Executes sell on Pons V2 Bonding Curve:
        1. approve(curve, token_amount)
        2. sell(token_amount, minEthOut, recipient)
        """
        curve_addr = self.w3.to_checksum_address(curve_address)
        tok_addr = self.w3.to_checksum_address(token_address)

        logger.info(f"Preparing SELL {token_amount} tokens on curve {curve_address}")

        if config.DRY_RUN or not self.account:
            logger.info(f"[DRY_RUN] Simulated SELL {token_amount} tokens on curve {curve_address}")
            return {
                "status": "simulated",
                "tx_hash": "0xSIMULATED_SELL_" + str(int(time.time())),
                "tokens_sold": token_amount
            }

        try:
            token_contract = self.w3.eth.contract(address=tok_addr, abi=ERC20_ABI)
            curve_contract = self.w3.eth.contract(address=curve_addr, abi=CURVE_ABI)

            # Check allowance
            allowance = token_contract.functions.allowance(self.wallet_address, curve_addr).call()
            if allowance < token_amount:
                logger.info("Approving Curve contract to spend tokens...")
                nonce = self.w3.eth.get_transaction_count(self.wallet_address)
                gas_price = int(self.w3.eth.gas_price * 1.2)
                max_uint = 2**256 - 1

                approve_tx = token_contract.functions.approve(curve_addr, max_uint).build_transaction({
                    "chainId": config.CHAIN_ID,
                    "from": self.wallet_address,
                    "gas": 80000,
                    "gasPrice": gas_price,
                    "nonce": nonce
                })
                signed_approve = self.account.sign_transaction(approve_tx)
                app_hash = self.w3.eth.send_raw_transaction(signed_approve.raw_transaction)
                self.w3.eth.wait_for_transaction_receipt(app_hash, timeout=60)
                logger.info("Approval confirmed!")

            # Execute Sell
            nonce = self.w3.eth.get_transaction_count(self.wallet_address)
            gas_price = int(self.w3.eth.gas_price * 1.25)
            min_eth_out = 0  # Can add slippage calculation

            sell_tx = curve_contract.functions.sell(
                token_amount,
                min_eth_out,
                self.wallet_address
            ).build_transaction({
                "chainId": config.CHAIN_ID,
                "from": self.wallet_address,
                "value": 0,
                "gas": 350000,
                "gasPrice": gas_price,
                "nonce": nonce
            })

            signed_sell = self.account.sign_transaction(sell_tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed_sell.raw_transaction)
            logger.info(f"Sell Tx broadcasted! Hash: {tx_hash.hex()}")

            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            if receipt.status == 1:
                logger.info(f"SELL CONFIRMED! Tx: {tx_hash.hex()} in block {receipt.blockNumber}")
                return {
                    "status": "success",
                    "tx_hash": tx_hash.hex(),
                    "tokens_sold": token_amount,
                    "block": receipt.blockNumber
                }
            else:
                logger.error(f"SELL REVERTED on-chain! Tx: {tx_hash.hex()}")
                return {"status": "reverted", "tx_hash": tx_hash.hex()}

        except Exception as e:
            logger.error(f"Exception during SELL execution: {e}")
            return {"status": "error", "error": str(e)}
