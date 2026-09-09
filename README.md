# 4-Chain Memecoin Automated Trading Bot (Robinhood, BSC, Solana, Arc)

支持 **Robinhood Chain**、**BSC**、**Solana** 以及 **Arc Chain** 四条链的全自动化 Memecoin 扫链与实盘/模拟交易机器人。

---

## 一、 多链架构与策略配置

```
┌──────────────────────────────────────────────────────────────┐
│                    Master MultiChain Orchestrator            │
├───────────────┬────────────────┬───────────────┬─────────────┤
│ Robinhood     │ BSC            │ Solana        │ Arc         │
│ (Pons V2)     │ (Four.meme/PCS)│ (Pump.fun/Ray)│ (Minara/GMGN│
│ RPC Event     │ Gecko / RPC    │ Gecko / SOL   │ Sentinel    │
├───────────────┴────────────────┴───────────────┴─────────────┤
│                    Unified Line C Risk Engine                │
│    • Take Profit: +50%      • Stop Loss: -25%                │
│    • Decay Timeout: 30 min  • Dynamic Reserve / Liq Tracking │
└──────────────────────────────────────────────────────────────┘
```

1. **Robinhood Chain（优化版）**：
   - **入场动量过滤**：`RH_MIN_CURVE_PROGRESS = 15.0%`，彻底避开 98% 开盘即死的 0 交易量鬼盘。
   - **Dev 连环发币过滤**：Dev 24h 发币 > 3 个直接拉黑。
   - **合约交互**：直连 Pons V2 工厂与 Bonding Curve 合约。

2. **BSC (Binance Smart Chain)**：
   - **流动性门槛**：`BSC_MIN_LIQ_USD = $2,500`。
   - **交易笔数过滤**：至少 3 笔真实买单，拒绝虚假自发池。

3. **Solana (Pump.fun / Raydium)**：
   - **高流动性过滤**：`SOL_MIN_LIQ_USD = $3,000`，过滤低流动性诈骗盘。
   - **真实买卖比**：要求至少 4 笔真实独立买入。

4. **Arc Chain (主网就绪哨兵)**：
   - **主网预备**：针对 9 月 16 日前后 Arc 主网上线，已内置 DEX 聚合器与 GMGN 端点哨兵，首发池上线瞬间自动捕获。

---

## 二、 快速运行

```bash
cd /home/lishin/robinhood_meme_bot
./start.sh
```

后台静默运行：
```bash
nohup ./start.sh > bot.log 2>&1 &
tail -f bot.log
```
