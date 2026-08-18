# GitHub Pages 全球市场日报

项目可在 GitHub Pages 上发布只读的中文全球市场日报，首位展示纳斯达克 100 指数，并展示 VIX 波动率指数、标普 500、纽约黄金和 WTI 原油的最近交易日涨跌、五日趋势、公开新闻与可能原因。

“今日解读”不会使用固定原因模板。GitHub Actions 每次更新时会解析当日新闻原文链接和媒体公开摘要，并通过仓库 Secret `OPENAI_API_KEY`（可配合 `OPENAI_BASE_URL`、`OPENAI_MODEL`）或 `DEEPSEEK_API_KEY` 动态生成中文报道要点、市场影响和后续观察。未配置密钥或生成失败时，页面会明确显示“实时解读暂不可用”。

## 自动更新

工作流 `.github/workflows/public-market-pages.yml` 在工作日 UTC 22:30（北京时间次日 06:30）运行，也支持手动触发。它会：

1. 运行 `scripts/generate_public_market.py` 获取公开行情与新闻；
2. 生成 `apps/dsa-web/public/market.json`；
3. 以 `VITE_PUBLIC_MARKET_MODE=true` 构建只读日报页；
4. 将构建产物发布到 GitHub Pages。

该公开页面不连接 DSA 后端，不公开自选股、持仓、API Key 或历史分析数据。完整 Web 工作台仍按原有方式运行。

## 启用 Pages

在仓库的 `Settings → Pages → Build and deployment` 中选择 `GitHub Actions`。随后手动运行一次 `Public Market Daily Pages` 工作流即可完成首次发布。

> 原因分析是将价格方向与同日公开资讯结合后的可能归因，不代表已经证实的单一因果关系，也不构成投资建议。
