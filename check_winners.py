
import json, requests, time
from web3 import Web3

with open("/home/lishin/robinhood_meme_bot/positions.json") as f:
    data = json.load(f)

winners = [p for p in data if p.get("pnl_pct", 0) > 0 and p.get("status") == "CLOSED"]

w3_rh = Web3(Web3.HTTPProvider("https://rpc.mainnet.chain.robinhood.com"))
CURVE_ABI = [{"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint256","name":"reserveETH","type":"uint256"},{"internalType":"uint256","name":"reserveToken","type":"uint256"}],"stateMutability":"view","type":"function"}]

results = []

for i, w in enumerate(winners):
    c = w.get("chain")
    sym = w.get("symbol")
    token = w.get("token")
    pool = w.get("curve_or_pool")
    entry_val = float(w.get("entry_val"))
    exit_pnl = float(w.get("pnl_pct"))
    
    current_val = 0.0
    status_note = ""
    
    if c == "robinhood":
        try:
            curve_contract = w3_rh.eth.contract(address=w3_rh.to_checksum_address(pool), abi=CURVE_ABI)
            res_eth, _ = curve_contract.functions.getReserves().call()
            current_val = float(w3_rh.from_wei(res_eth, "ether"))
            status_note = "Pons V2"
        except Exception as e:
            current_val = entry_val
            status_note = "Curve Finished"
    else:
        try:
            r = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{token}", timeout=4)
            if r.status_code == 200:
                pairs = r.json().get("pairs") or []
                if pairs:
                    pair_match = [p for p in pairs if p.get("pairAddress", "").lower() == pool.lower()]
                    p = pair_match[0] if pair_match else pairs[0]
                    current_val = float(p.get("liquidity", {}).get("usd") or 0.0)
                    price_usd = p.get("priceUsd", "0")
                    status_note = f"${price_usd}"
                else:
                    current_val = 0.0
                    status_note = "Liq=0"
            time.sleep(0.15)
        except Exception as e:
            current_val = 0.0
            status_note = f"Error: {e}"

    hold_pnl = ((current_val - entry_val) / entry_val) * 100.0 if entry_val > 0 else -100.0
    diff = hold_pnl - exit_pnl
    
    idx = i + 1
    chain_str = c.upper()
    print(f"{idx:2d}. {chain_str:9} {sym:10} | Entry: {entry_val:9.2f} | Now: {current_val:9.2f} | ExitPnL: +{exit_pnl:6.1f}% | HoldNow: {hold_pnl:+7.1f}% | Diff: {diff:+7.1f}% | {status_note}")
    results.append({"sym": sym, "chain": chain_str, "exit_pnl": exit_pnl, "hold_pnl": hold_pnl, "diff": diff})

# Summary
better_exit = sum(1 for r in results if r["exit_pnl"] > r["hold_pnl"])
better_hold = sum(1 for r in results if r["hold_pnl"] > r["exit_pnl"])
print("-" * 75)
print(f"Total evaluated: {len(results)} winners")
print(f"Exiting with Take-Profit was better in: {better_exit} / {len(results)} tokens ({better_exit/len(results)*100:.1f}%)")
print(f"Holding until now was better in: {better_hold} / {len(results)} tokens ({better_hold/len(results)*100:.1f}%)")
