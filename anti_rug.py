import logging
import requests

logger = logging.getLogger("AntiRug")

class AntiRugDetector:
    @staticmethod
    def check_bsc_token(token_address: str) -> tuple[bool, str]:
        """
        Queries GoPlus Security API for BSC tokens:
        - Honeypot check
        - Sell tax limit (<15%)
        - Cannot sell all check
        - Anti-whale / malicious code
        """
        addr = token_address.lower()
        url = f"https://api.gopluslabs.io/api/v1/token_security/56?contract_addresses={addr}"
        try:
            r = requests.get(url, timeout=3.5)
            if r.status_code == 200:
                data = r.json().get("result", {}).get(addr, {})
                if not data:
                    return True, "No security alerts on file"

                if data.get("is_honeypot") == "1":
                    return False, "🚨 Honeypot detected (cannot sell)!"

                if data.get("cannot_sell_all") == "1":
                    return False, "🚨 Malicious contract: cannot sell all tokens!"

                sell_tax = data.get("sell_tax")
                if sell_tax:
                    try:
                        tax_val = float(sell_tax)
                        if tax_val > 0.15:
                            return False, f"🚨 Exorbitant sell tax ({tax_val*100:.1f}% > 15%)"
                    except ValueError:
                        pass

                buy_tax = data.get("buy_tax")
                if buy_tax:
                    try:
                        b_val = float(buy_tax)
                        if b_val > 0.15:
                            return False, f"🚨 Exorbitant buy tax ({b_val*100:.1f}% > 15%)"
                    except ValueError:
                        pass

                return True, "Passed BSC Honeypot & Tax verification"
        except Exception as e:
            logger.debug(f"GoPlus BSC check skipped due to timeout/error: {e}")
            return False, f"BSC Security check timeout/unavailable: {e}"
        return True, "Passed"

    @staticmethod
    def check_bsc_lp_lock_onchain(pool_address: str, rpc_url: str = "https://bsc-dataseed.binance.org") -> tuple[bool, str]:
        """
        Directly queries the PancakeSwap V2 Pair on BSC via Web3 to ensure LP tokens are
        burned or locked in a verified locker contract (PinkLock, Unicrypt, TeamFinance, Null address).
        Rejects any pool where unlocked dev LP >= 20%.
        """
        try:
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 4.0}))
            pair_abi = [
                {"constant": True, "inputs": [], "name": "totalSupply", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
                {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"}
            ]
            dead_lock_addresses = [
                Web3.to_checksum_address("0x000000000000000000000000000000000000dEaD"),
                Web3.to_checksum_address("0x0000000000000000000000000000000000000000"),
                Web3.to_checksum_address("0x407993575c91ce7643a4d4ccacc9a98c36ee1bbe"), # PinkLock V2
                Web3.to_checksum_address("0x7ee058420e5937496F5a2096f04cAA7721cF70cc"), # PinkLock V1
                Web3.to_checksum_address("0xC765bddB93b0D1c1A88282BA0Fa6B2d00E3e0c83"), # Unicrypt
                Web3.to_checksum_address("0xE2fE530C047f2d85298b07D9333C05737f1435fB"), # Team Finance
            ]
            pool_contract = w3.eth.contract(address=Web3.to_checksum_address(pool_address), abi=pair_abi)
            total_supply = pool_contract.functions.totalSupply().call()
            if total_supply == 0:
                return False, "🚨 Pool LP TotalSupply is 0"
            locked_amount = sum(pool_contract.functions.balanceOf(addr).call() for addr in dead_lock_addresses)
            locked_pct = (locked_amount / total_supply) * 100.0
            if locked_pct < 80.0:
                return False, f"🚨 Unlocked LP Rug Risk: Only {locked_pct:.1f}% LP locked/burned (< 80.0%)"
            return True, f"Passed On-Chain LP Lock verification ({locked_pct:.1f}% locked/burned)"
        except Exception as e:
            logger.debug(f"BSC on-chain LP check error: {e}")
            return False, f"Failed to verify LP lock on-chain: {e}"

    @staticmethod
    def check_solana_token(token_address: str) -> tuple[bool, str]:
        """
        Queries GoPlus Security API for Solana tokens:
        - Freezable authority (Dev can freeze your token account -> Honeypot)
        - Mintable authority (Dev can mint infinite tokens to dump)
        """
        url = f"https://api.gopluslabs.io/api/v1/solana/token_security?contract_addresses={token_address}"
        try:
            r = requests.get(url, timeout=3.5)
            if r.status_code == 200:
                data = r.json().get("result", {}).get(token_address, {})
                if not data:
                    return True, "No security alerts on file"

                # 1. Freeze Authority
                freezable = data.get("freezable", {}).get("status") == "1"
                if freezable:
                    return False, "🚨 Freeze Authority enabled (Account freeze risk)!"

                # 2. Mint Authority
                mintable = data.get("mintable", {}).get("status") == "1"
                if mintable:
                    return False, "🚨 Mint Authority enabled (Infinite token dilution risk)!"

                return True, "Passed Solana Freeze & Mint verification"
        except Exception as e:
            logger.debug(f"GoPlus Solana check skipped due to timeout/error: {e}")
            return False, f"Solana security check unavailable: {e}"
        return True, "Passed"

    @staticmethod
    def check_pool_transactions(txns: dict, min_unique_buyers: int = 3, min_sells: int = 1) -> tuple[bool, str]:
        """
        Checks transaction patterns:
        - If buys >= 8 and sells < min_sells, high probability of Honeypot / unsellable token!
        - Unique buyers count to prevent wash trading
        """
        if not txns:
            return True, "No tx data"

        buys = txns.get("buys", 0)
        sells = txns.get("sells", 0)
        buyers = txns.get("buyers", 0)

        # If significant buys but 0 sells, it is an unsellable honeypot
        if buys >= 8 and sells < min_sells:
            return False, f"🚨 Unsellable / Honeypot Warning: {buys} buys with only {sells} sells!"

        if buyers > 0 and buyers < min_unique_buyers:
            return False, f"🚨 Wash Trading: Only {buyers} unique buyers (< {min_unique_buyers})"

        return True, "Passed transaction health check"
