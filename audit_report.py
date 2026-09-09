import json
import time

START_TS = 1788768868 # Clean baseline starting Sept 7 08:14 UTC

PRICES = {"ETH": 2500.0, "BNB": 580.0, "SOL": 140.0}

def generate_audit():
    with open("/home/lishin/robinhood_meme_bot/positions.json") as f:
        positions = json.load(f)

    now = int(time.time())
    pos_list = [p for p in positions if p.get("entry_time", 0) >= START_TS]

    report = []
    report.append("# 4-Chain Memecoin Performance & Audit Report (Clean Slate - $25/Trade)\n")
    report.append(f"**Session Start**: 2026-09-07 08:14:00 UTC | **Current Time**: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n")
    report.append(f"**当前纯净样本数**: {len(pos_list)} 笔 (单笔仓位: ~$25 USD)\n")

    report.append("## 一、 🚀 4 链实时表现审计表 (Clean Performance from Now)\n")
    report.append("| 链 (Chain) | 总开仓 | 监控中 | 已平仓 | 胜/平/负 | 胜率 (>0%) | 净投入 | 净盈亏 (含Gas) | 单链ROI |")
    report.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")

    by_chain = {}
    for p in pos_list:
        c = p.get("chain", "robinhood")
        by_chain.setdefault(c, []).append(p)

    tot_in_all = 0.0
    tot_net_all = 0.0

    for chain in ["solana", "bsc", "robinhood", "arc"]:
        p_list = by_chain.get(chain, [])
        if not p_list:
            report.append(f"| **{chain.upper()}** | 0 | 0 | 0 | - | - | - | - | *待命中* |")
            continue

        closed = [p for p in p_list if p.get("status") == "CLOSED"]
        open_pos = [p for p in p_list if p.get("status") == "OPEN"]
        
        wins = sum(1 for p in closed if p.get("pnl_pct", 0) > 0)
        losses = sum(1 for p in closed if p.get("pnl_pct", 0) < 0)
        flats = sum(1 for p in closed if p.get("pnl_pct", 0) == 0)
        win_rate = (wins / len(closed) * 100) if closed else 0.0

        unit = p_list[0].get("unit", "USD")
        price = PRICES.get(unit, 1.0)
        tot_in = sum(p.get("entry_amount", 0) * price for p in closed)

        tot_net = 0.0
        for p in closed:
            inv_usd = p.get("entry_amount", 0) * price
            pnl = p.get("pnl_pct", 0)
            eff_pnl = min(pnl, 300.0) if pnl > 0 else max(pnl, -100.0)
            gas = p.get("gas_cost_usd", 0.1)
            tot_net += (inv_usd * (eff_pnl / 100.0)) - gas

        roi = (tot_net / tot_in * 100) if tot_in > 0 else 0.0
        tot_in_all += tot_in
        tot_net_all += tot_net

        report.append(f"| **{chain.upper()}** | {len(p_list)} | {len(open_pos)} | {len(closed)} | {wins}/{flats}/{losses} | **{win_rate:.1f}%** | ${tot_in:,.2f} | **${tot_net:+,.2f}** | **{roi:+.2f}%** |")

    overall_roi = (tot_net_all / tot_in_all * 100) if tot_in_all > 0 else 0.0
    report.append(f"\n> **本次纯净综合表现**：总投入 **${tot_in_all:,.2f}** | 净盈亏 **${tot_net_all:+,.2f}** | 综合 ROI **{overall_roi:+.2f}%**\n")

    report.append("\n---\n")

    report.append("## 二、 🏆 本次纯净运行捕获的胜单明细 (Realized Winners)")
    report.append("| 链 | 代币 Symbol | 投入金额 | 最终 PnL | 离场原因 |")
    report.append("| :--- | :--- | :--- | :---: | :--- |")
    winners = [p for p in pos_list if p.get("pnl_pct", 0.0) > 0 and p.get("status") == "CLOSED"]
    if not winners:
        report.append("| - | *暂无已结胜单* | - | - | *新周期刚启动* |")
    else:
        for p in winners:
            chain = p.get("chain", "robinhood").upper()
            sym = p.get("symbol")
            amt = f"{p.get('entry_amount', 0)} {p.get('unit', '')}"
            pnl = f"+{p.get('pnl_pct', 0.0):.1f}%"
            reason = p.get("exit_reason", "")
            report.append(f"| {chain} | **{sym}** | {amt} | **{pnl}** | {reason} |")

    report.append("\n---\n")

    report.append("## 三、 🟢 当前 4 链实时持仓表 (Active Positions)")
    report.append("| 链 | 代币 Symbol | 投入仓位 | 当前浮盈亏 | 持有时长 | 状态 |")
    report.append("| :--- | :--- | :--- | :---: | :--- |")
    open_all = [p for p in positions if p.get("status") == "OPEN"]
    if not open_all:
        report.append("| - | *当前无活跃持仓* | - | - | - | *等待高确信度突破* |")
    else:
        for p in open_all:
            chain = p.get("chain", "robinhood").upper()
            sym = p.get("symbol")
            amt = f"{p.get('entry_amount', 0)} {p.get('unit', '')}"
            pnl = f"{p.get('pnl_pct', 0.0):+.1f}%"
            held = f"{(now - p.get('entry_time', now)) / 60.0:.1f} min"
            report.append(f"| {chain} | **{sym}** | {amt} | **{pnl}** | {held} | 监控中 |")

    return "\n".join(report)

if __name__ == "__main__":
    print(generate_audit())
