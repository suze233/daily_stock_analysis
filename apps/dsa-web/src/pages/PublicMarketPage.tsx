import { useEffect, useMemo, useState } from 'react';
import { Area, AreaChart, ResponsiveContainer, Tooltip, YAxis } from 'recharts';
import { ArrowDownRight, ArrowUpRight, ExternalLink, RefreshCw, ShieldCheck } from 'lucide-react';
import './PublicMarketPage.css';

type PublicMarket = {
  symbol: string;
  name: string;
  value: string;
  change: number;
  history: number[];
  session?: string;
  reason: string;
  detail: string;
  tags: string[];
  evidenceSource?: string;
  evidenceLink?: string;
};

type PublicNews = { title: string; link: string; source: string; time: string; category: string };
type PublicBrief = {
  date: string;
  updatedAt: string;
  pulse: { title: string; summary: string };
  markets: PublicMarket[];
  news: PublicNews[];
};

const fallback: PublicBrief = {
  date: '等待更新',
  updatedAt: '首次工作流运行后自动刷新',
  pulse: { title: '正在准备首份市场日报', summary: '行情、新闻与原因分析会在美股收盘后自动更新。' },
  markets: [
    ['NASDAQ 100', '纳斯达克 100 指数', [72, 75, 73, 77, 80]],
    ['NASDAQ', '纳斯达克综合指数', [66, 68, 67, 71, 74]],
    ['S&P 500', '标普 500', [58, 60, 59, 62, 64]],
    ['GOLD', '纽约黄金', [72, 70, 71, 68, 67]],
    ['WTI', 'WTI 原油', [51, 54, 53, 57, 59]],
  ].map(([symbol, name, history]) => ({
    symbol: String(symbol), name: String(name), history: history as number[], value: '—', change: 0, session: '等待更新',
    reason: '等待最新数据', detail: '首次自动任务完成后展示最近交易日行情和可能驱动因素。', tags: ['公开行情', '新闻归因'],
  })),
  news: [],
};

const signed = (value: number) => `${value >= 0 ? '+' : '−'}${Math.abs(value).toFixed(2)}%`;

function TrendChart({ market }: { market: PublicMarket }) {
  const data = (market.history?.length ? market.history : [0, 0]).map((value, index) => ({ value, index }));
  const color = market.change >= 0 ? '#ef5b6c' : '#17b978';
  const gradientId = `trend-${market.symbol.replace(/[^a-z0-9]/gi, '')}`;
  return (
    <div className="public-trend" role="img" aria-label={`${market.name}最近五个交易日走势`}>
      <ResponsiveContainer width="100%" height={104}>
        <AreaChart data={data} margin={{ top: 8, right: 5, bottom: 2, left: 5 }}>
          <defs><linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={color} stopOpacity={0.3} /><stop offset="1" stopColor={color} stopOpacity={0} /></linearGradient></defs>
          <YAxis domain={['dataMin - 1', 'dataMax + 1']} hide />
          <Tooltip content={({ active, payload }) => active && payload?.[0] ? <div className="public-chart-tip">{Number(payload[0].value).toLocaleString()}</div> : null} />
          <Area type="monotone" dataKey="value" stroke={color} strokeWidth={2.5} fill={`url(#${gradientId})`} dot={false} activeDot={{ r: 4, fill: 'var(--bg-card)', stroke: color, strokeWidth: 2 }} />
        </AreaChart>
      </ResponsiveContainer>
      <div className="public-trend-label"><span>5 日前</span><span>最近</span></div>
    </div>
  );
}

function EvidenceLink({ market }: { market: PublicMarket }) {
  if (!market.evidenceLink) return null;
  return <a className="public-evidence-link" href={market.evidenceLink} target="_blank" rel="noreferrer">来源：{market.evidenceSource ?? '原始报道'} <ExternalLink size={13} /></a>;
}

export default function PublicMarketPage() {
  const [brief, setBrief] = useState<PublicBrief>(fallback);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}market.json`, { cache: 'no-store' })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error('market data unavailable')))
      .then(setBrief)
      .catch(() => setBrief(fallback))
      .finally(() => setLoading(false));
  }, []);
  const equity = useMemo(() => brief.markets.slice(0, 3), [brief.markets]);
  const commodities = useMemo(() => brief.markets.slice(3), [brief.markets]);

  return <main className="public-market">
    <header className="public-nav"><div className="public-brand"><span>DSA</span><strong>全球市场日报</strong></div><nav><a href="#overview">市场概览</a><a href="#analysis">原因分析</a><a href="#news">相关新闻</a></nav><div className="public-live"><RefreshCw size={13} className={loading ? 'spin' : ''} /> 每日自动更新</div></header>
    <section className="public-hero"><div><p className="public-kicker">DAILY GLOBAL MARKET BRIEF · {brief.date}</p><h1>看见涨跌，<br /><em>更看懂背后的原因。</em></h1><p>每天追踪纳指、标普 500、黄金和原油，把分散的行情与新闻整理成一份清晰日报。</p></div><aside><span>今日市场脉搏</span><h2>{brief.pulse.title}</h2><p>{brief.pulse.summary}</p><small><ShieldCheck size={13} /> 基于公开信息的可能归因</small></aside></section>
    <section className="public-section" id="overview"><div className="public-section-head"><div><span>01</span><h2>市场概览</h2></div><p>{brief.updatedAt}</p></div><div className="public-market-grid">{brief.markets.map((market) => <article key={market.symbol} className="public-market-card"><div className="public-card-top"><span>{market.symbol}</span><b className={market.change >= 0 ? 'is-up' : 'is-down'}>{market.change >= 0 ? <ArrowUpRight size={16} /> : <ArrowDownRight size={16} />}{signed(market.change)}</b></div><h3>{market.value}</h3><p>{market.name} <i>{market.session ?? '最近日线'}</i></p><TrendChart market={market} /></article>)}</div></section>
    <section className="public-section" id="analysis"><div className="public-section-head"><div><span>02</span><h2>今日解读</h2></div><p>具体催化 × 报道要点 × 原文链接</p></div><div className="public-analysis"><article className="public-lead"><span>美股</span>{equity.map((item) => <div key={item.symbol}><h3>{item.name}：{item.reason}</h3><p>{item.detail}</p><EvidenceLink market={item} /></div>)}<div>{Array.from(new Set(equity.flatMap((item) => item.tags))).slice(0, 4).map((tag) => <b key={tag}>{tag}</b>)}</div></article><div className="public-reasons">{commodities.map((item) => <article key={item.symbol}><span>{item.name}</span><h3>{item.reason}</h3><p>{item.detail}</p><EvidenceLink market={item} /><div>{item.tags.map((tag) => <b key={tag}>{tag}</b>)}</div></article>)}</div></div><p className="public-caveat">“报道要点”来自原文可公开读取的摘要/导语；无法读取时会明确提示。原因分析表示与当日行情方向一致的可能驱动因素，不代表已经证实的单一因果关系，也不构成投资建议。</p></section>
    <section className="public-section" id="news"><div className="public-section-head"><div><span>03</span><h2>相关新闻</h2></div><p>保留原始报道链接</p></div><div className="public-news">{brief.news.length ? brief.news.map((item, index) => <a href={item.link} target="_blank" rel="noreferrer" key={`${item.link}-${index}`}><time>{item.time}</time><div><span>{item.category} · {item.source}</span><h3>{item.title}</h3></div><ExternalLink size={17} /></a>) : <div className="public-empty">首次自动更新后显示相关新闻。</div>}</div></section>
    <footer><strong>DSA 全球市场日报</strong><span>数据自动更新 · 信息仅供研究参考</span><a href="https://github.com/suze233/daily_stock_analysis" target="_blank" rel="noreferrer">查看源代码 <ExternalLink size={13} /></a></footer>
  </main>;
}
