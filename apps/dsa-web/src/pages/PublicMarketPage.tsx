import { useEffect, useState } from 'react';
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
  analysisStatus?: string;
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
    ['VIX', 'CBOE 波动率指数', [19, 18, 20, 21, 20]],
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

function MarketDetail({ detail }: { detail: string }) {
  return <div className="public-market-detail">{detail.split('\n').map((line, index) => {
    const match = line.match(/^【([^】]+)】(.*)$/);
    return <div key={`${line}-${index}`}><strong>{match?.[1] ?? '解读'}</strong><p>{match?.[2] ?? line}</p></div>;
  })}</div>;
}

function AnalysisCard({ market, featured = false }: { market: PublicMarket; featured?: boolean }) {
  return <article className={`public-analysis-card${featured ? ' is-featured' : ''}`}>
    <div className="public-analysis-meta"><span>{market.symbol}</span><i>{market.analysisStatus ?? '等待更新'}</i></div>
    <h3>{market.reason}</h3>
    <MarketDetail detail={market.detail} />
    <div className="public-analysis-footer"><div>{market.tags.map((tag) => <b key={tag}>{tag}</b>)}</div><EvidenceLink market={market} /></div>
  </article>;
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
  return <main className="public-market">
    <header className="public-nav">
      <div className="public-brand"><span>DSA</span><div><strong>全球市场日报</strong><small>GLOBAL MARKET BRIEF</small></div></div>
      <nav><a href="#overview">市场概览</a><a href="#analysis">今日解读</a><a href="#news">相关新闻</a></nav>
      <div className="public-live"><RefreshCw size={13} className={loading ? 'spin' : ''} /><span>每日自动更新</span></div>
    </header>

    <section className="public-hero">
      <div className="public-hero-copy"><p className="public-kicker">{brief.date} · DAILY BRIEF</p><h1>今天的市场，<br /><em>一眼看清。</em></h1><p>聚合纳斯达克 100、VIX、标普 500、黄金与原油，结合当日新闻生成清晰、可核对的市场解读。</p><div className="public-update"><span className="public-status-dot" />{brief.updatedAt}</div></div>
      <aside><div className="public-pulse-label"><span>今日市场脉搏</span><ShieldCheck size={16} /></div><h2>{brief.pulse.title}</h2><p>{brief.pulse.summary}</p><small>AI 实时生成 · 原文可追溯</small></aside>
    </section>

    <section className="public-section" id="overview">
      <div className="public-section-head"><div><span>01</span><h2>市场概览</h2></div><p>最近交易日 · 五日趋势</p></div>
      <div className="public-market-grid">{brief.markets.map((market, index) => <article key={market.symbol} className={`public-market-card${index === 0 ? ' is-primary' : ''}`}><div className="public-card-top"><div><span>{market.symbol}</span><small>{market.name}</small></div><b className={market.change >= 0 ? 'is-up' : 'is-down'}>{market.change >= 0 ? <ArrowUpRight size={16} /> : <ArrowDownRight size={16} />}{signed(market.change)}</b></div><h3>{market.value}</h3><div className="public-session">{market.session ?? '最近日线'}</div><TrendChart market={market} /></article>)}</div>
    </section>

    <section className="public-section" id="analysis">
      <div className="public-section-head"><div><span>02</span><h2>今日解读</h2></div><p>报道要点 · 市场影响 · 后续观察</p></div>
      <div className="public-analysis">{brief.markets.map((market, index) => <AnalysisCard key={market.symbol} market={market} featured={index === 0} />)}</div>
      <p className="public-caveat">解读由当次工作流根据最新行情、新闻与媒体公开摘要动态生成，不使用固定原因模板。内容是基于公开信息的可能归因，不代表已确认的单一因果关系，也不构成投资建议。</p>
    </section>

    <section className="public-section" id="news">
      <div className="public-section-head"><div><span>03</span><h2>相关新闻</h2></div><p>点击查看媒体原文</p></div>
      <div className="public-news">{brief.news.length ? brief.news.map((item, index) => <a href={item.link} target="_blank" rel="noreferrer" key={`${item.link}-${index}`}><div className="public-news-meta"><span>{item.category}</span><time>{item.time}</time></div><h3>{item.title}</h3><div className="public-news-source">{item.source}<ExternalLink size={15} /></div></a>) : <div className="public-empty">首次自动更新后显示相关新闻。</div>}</div>
    </section>

    <footer><div><strong>DSA 全球市场日报</strong><span>数据自动更新 · 信息仅供研究参考</span></div><a href="https://github.com/suze233/daily_stock_analysis" target="_blank" rel="noreferrer">查看源代码 <ExternalLink size={13} /></a></footer>
  </main>;
}
