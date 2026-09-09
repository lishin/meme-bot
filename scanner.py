import logging
from collections import defaultdict
from web3 import Web3
import config
from abi import (
    FACTORY_ADDRESS,
    TOPIC_TOKEN_LAUNCHED,
    TOPIC_POOL_GRADUATED,
    CURVE_ABI,
    ERC20_ABI
)

logger = logging.getLogger("Scanner")

class Scanner:
    def __init__(self, w3: Web3):
        self.w3 = w3
        self.factory_address = self.w3.to_checksum_address(FACTORY_ADDRESS)
        self.dev_launch_counts = defaultdict(int)
        self.known_tokens = set()

    def get_token_metadata(self, token_address: str) -> dict:
        try:
            tok = self.w3.eth.contract(
                address=self.w3.to_checksum_address(token_address),
                abi=ERC20_ABI
            )
            name = tok.functions.name().call()
            symbol = tok.functions.symbol().call()
            decimals = tok.functions.decimals().call()
            supply = tok.functions.totalSupply().call()
            return {
                "name": name,
                "symbol": symbol,
                "decimals": decimals,
                "totalSupply": supply
            }
        except Exception as e:
            logger.debug(f"Failed to fetch metadata for {token_address}: {e}")
            return {"name": "UNKNOWN", "symbol": "UNKNOWN", "decimals": 18, "totalSupply": 0}

    def parse_token_launched_log(self, log) -> dict:
        """
        Parses TokenLaunched event log:
        topic0: hash
        topic1: token address
        topic2: curve address
        topic3: deployer address
        data: pairToken (address), salt/param (uint256), graduationThreshold (uint256)
        """
        token = "0x" + log.topics[1].hex()[-40:]
        curve = "0x" + log.topics[2].hex()[-40:]
        deployer = "0x" + log.topics[3].hex()[-40:]

        data_hex = log.data.hex()
        if data_hex.startswith("0x"):
            data_hex = data_hex[2:]

        pair_token = "0x0000000000000000000000000000000000000000"
        graduation_threshold = 0

        if len(data_hex) >= 64:
            pair_token = "0x" + data_hex[24:64]
        if len(data_hex) >= 192:
            graduation_threshold = int(data_hex[128:192], 16)

        return {
            "token": self.w3.to_checksum_address(token),
            "curve": self.w3.to_checksum_address(curve),
            "deployer": self.w3.to_checksum_address(deployer),
            "pairToken": self.w3.to_checksum_address(pair_token),
            "graduationThreshold": graduation_threshold,
            "blockNumber": log.blockNumber,
            "txHash": log.transactionHash.hex()
        }

    def filter_launch(self, item: dict) -> tuple[bool, str]:
        """
        Line A Hard Elimination Rules:
        Returns (passed: bool, reason: str)
        """
        token_addr = item["token"]
        deployer = item["deployer"]
        pair_token = item["pairToken"]

        # 1. Update and check deployer launches
        self.dev_launch_counts[deployer.lower()] += 1
        dev_count = self.dev_launch_counts[deployer.lower()]
        if dev_count > config.MAX_DEV_LAUNCHES:
            return False, f"Dev spam filter (Dev launched {dev_count} tokens > max {config.MAX_DEV_LAUNCHES})"

        # 2. Check Quote / Pair Token filter
        is_eth_pair = (pair_token.lower() == config.ZERO_ADDRESS.lower())
        is_nvda_pair = (pair_token.lower() == config.NVDA_TOKEN.lower())

        if config.PAIR_FILTER == "ETH_ONLY" and not is_eth_pair:
            return False, f"Non-ETH pair asset ({pair_token})"
        elif config.PAIR_FILTER == "STOCK_ONLY" and not is_nvda_pair:
            return False, f"Non-NVDA pair asset ({pair_token})"

        # 3. Check Metadata & Banned keywords
        meta = self.get_token_metadata(token_addr)
        item["name"] = meta["name"]
        item["symbol"] = meta["symbol"]
        item["decimals"] = meta["decimals"]

        full_text = (meta["name"] + " " + meta["symbol"]).lower()
        for banned in config.BANNED_KEYWORDS:
            if banned in full_text:
                return False, f"Banned keyword '{banned}' in name/symbol ({meta['symbol']})"

        return True, "Passed Line A filters"

    def check_curve_progress(self, curve_address: str) -> dict:
        """
        Line B Curve Progress Check:
        Returns reserve_eth, progress_pct, graduated status
        """
        curve_addr = self.w3.to_checksum_address(curve_address)
        try:
            curve = self.w3.eth.contract(address=curve_addr, abi=CURVE_ABI)
            res_eth, res_token = curve.functions.getReserves().call()
            threshold = curve.functions.graduationThreshold().call()
            graduated = curve.functions.graduated().call()

            progress_pct = 0.0
            if threshold > 0:
                progress_pct = (res_eth / threshold) * 100.0

            return {
                "reserve_eth": float(self.w3.from_wei(res_eth, "ether")),
                "reserve_token": res_token,
                "progress_pct": progress_pct,
                "threshold_eth": float(self.w3.from_wei(threshold, "ether")),
                "graduated": graduated
            }
        except Exception as e:
            logger.error(f"Failed to check curve progress for {curve_address}: {e}")
            return {
                "reserve_eth": 0.0,
                "reserve_token": 0,
                "progress_pct": 0.0,
                "threshold_eth": 0.0,
                "graduated": False
            }

    def scan_blocks(self, from_block: int, to_block: int) -> list[dict]:
        """
        Scans block range for TokenLaunched logs on Pons V2 Factory
        """
        try:
            logs = self.w3.eth.get_logs({
                "fromBlock": from_block,
                "toBlock": to_block,
                "address": self.factory_address,
                "topics": [TOPIC_TOKEN_LAUNCHED]
            })
            launches = []
            for log in logs:
                parsed = self.parse_token_launched_log(log)
                if parsed["token"] not in self.known_tokens:
                    self.known_tokens.add(parsed["token"])
                    launches.append(parsed)
            return launches
        except Exception as e:
            logger.error(f"Error scanning blocks {from_block} to {to_block}: {e}")
            return []
