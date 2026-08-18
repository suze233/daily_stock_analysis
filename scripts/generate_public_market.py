#!/usr/bin/env python3
"""Generate the static GitHub Pages market brief from public market/news feeds."""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from time import time
from zoneinfo import ZoneInfo

ASSETS = (
    ("NASDAQ 100", "纳斯达克 100 指数", "^NDX", "Nasdaq 100 technology stocks Federal Reserve", "美股"),
    ("VIX", "CBOE 波动率指数", "^VIX", "VIX volatility stock market risk", "避险"),
    ("S&P 500", "标普 500", "^GSPC", "S&P 500 US stock market economy", "美股"),
    ("GOLD", "COMEX 黄金期货", "GC=F", "gold price dollar Federal Reserve", "黄金"),
    ("WTI", "WTI 原油期货", "CL=F", "oil price OPEC inventory supply", "能源"),
)
HEADERS = {"User-Agent": "Mozilla/5.0 DSA-Public-Brief/1.0"}


def request_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read()


def fetch_quote(ticker: str) -> tuple[float, float, str, list[float], str]:
    encoded = urllib.parse.quote(ticker, safe="")
    payload = json.loads(request_bytes(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range=7d&interval=1d"
    ))
    result = payload["chart"]["result"][0]
    points = [
        (timestamp, close)
        for timestamp, close in zip(result["timestamp"], result["indicators"]["quote"][0]["close"])
        if close is not None
    ]
    if len(points) < 2:
        raise RuntimeError(f"insufficient quote history for {ticker}")
    regular = result.get("meta", {}).get("currentTradingPeriod", {}).get("regular", {})
    is_regular_session = regular.get("start", 0) <= time() <= regular.get("end", -1)
    # Yahoo's final daily candle can still be revised during regular trading.
    # Use the preceding confirmed bar for a daily report generated intraday.
    if is_regular_session and len(points) >= 3:
        points = points[:-1]
    current, previous = points[-1][1], points[-2][1]
    change = (current / previous - 1) * 100
    exchange_timezone = result.get("meta", {}).get("exchangeTimezoneName", "America/New_York")
    trade_date = datetime.fromtimestamp(points[-1][0], ZoneInfo(exchange_timezone)).strftime("%Y.%m.%d")
    session = "\u6700\u8fd1\u65e5\u7ebf"
    return current, change, trade_date, [round(value, 2) for _, value in points[-5:]], session


def fetch_news(query: str, category: str) -> list[dict[str, str]]:
    encoded = urllib.parse.quote(f"{query} when:1d")
    root = ET.fromstring(request_bytes(
        f"https://news.google.com/rss/search?q={encoded}&hl=zh-CN&gl=US&ceid=US:zh-Hans"
    ))
    items: list[dict[str, str]] = []
    for item in root.findall("./channel/item")[:3]:
        raw_title = item.findtext("title", "").strip()
        title = re.sub(r"\s+-\s+[^-]+$", "", raw_title)
        published = item.findtext("pubDate", "")
        try:
            display_time = datetime.strptime(published, "%a, %d %b %Y %H:%M:%S %Z").strftime("%H:%M")
        except ValueError:
            display_time = "今日"
        items.append({
            "title": title,
            "link": item.findtext("link", ""),
            "source": item.findtext("source", "公开资讯").strip(),
            "time": display_time,
            "category": category,
        })
    return items


def fetch_article_summary(link: str) -> str:
    """Return a short, source-provided description from the linked article when available."""
    if not link:
        return ""
    try:
        page = request_bytes(link).decode("utf-8", errors="ignore")
    except OSError:
        return ""
    for pattern in (
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']',
    ):
        match = re.search(pattern, page, flags=re.IGNORECASE)
        if match:
            summary = re.sub(r"\s+", " ", match.group(1)).strip()
            if summary and "aggregated from sources all over the world by google news" not in summary.lower():
                return summary[:360]
    return ""


def summarize_headline(symbol: str, headline: str) -> str:
    """Produce a Chinese event brief when the source does not expose an article summary."""
    text = headline.lower()
    if symbol in {"NASDAQ 100", "NASDAQ", "S&P 500"}:
        if "tech boost" in text:
            return "报道指出科技板块走强正在提振标普与纳斯达克期货，说明市场资金当时偏向大型科技权重股。"
        if "rate hike bets retreat" in text:
            return "报道指出市场下调了对进一步加息的押注，同时等待零售企业财报和新的经济数据，以重新评估增长与利率路径。"
        if "oil price above" in text or "nasdaq fall" in text:
            return "报道指出道指、标普和纳指当日走弱，同时油价升至较高水平，市场正在权衡能源价格对通胀和风险偏好的压力。"
        if "hedge" in text:
            return "报道聚焦市场连续上涨后是否需要增加对冲，反映投资者开始讨论估值、回撤风险和仓位保护。"
    elif symbol == "GOLD":
        if "softer dollar" in text or "dollar weakens" in text:
            return "报道将黄金上涨与美元走弱、市场对联储继续加息的预期减弱联系起来，这两项变化均改善了黄金的相对吸引力。"
    elif symbol == "WTI":
        if "hormuz" in text or "disruption" in text:
            return "报道指出霍尔木兹航运中断可能持续，市场因担忧原油运输受限而提高了即时供应风险的定价。"
    if symbol == "VIX":
        if "volatility" in text or "vix" in text:
            return "市场新闻聚焦股市波动与避险需求的变化，投资者正在重新评估短期风险。"
        return "市场新闻聚焦风险偏好与股市波动，VIX 用于衡量标普 500 期权隐含的预期波动。"
    if symbol in {"NASDAQ 100", "NASDAQ", "S&P 500"}:
        return "市场新闻聚焦美股风险偏好、宏观数据与企业盈利预期的变化。"
    if symbol == "GOLD":
        return "市场新闻聚焦美元、利率预期和避险需求对黄金的共同影响。"
    return "市场新闻聚焦原油供应、运输风险和库存预期的变化。"


def explain(symbol: str, change: float, headlines: list[dict[str, str]]) -> tuple[str, str, list[str], str, str]:
    direction = "走强" if change >= 0 else "承压"
    headline_text = " ".join(item["title"] for item in headlines).lower()
    if symbol == "VIX":
        reason = "市场避险需求升温，VIX 上升" if change >= 0 else "市场避险需求回落，VIX 下降"
        tags = ["市场波动", "避险需求", "风险偏好"]
    elif symbol in {"NASDAQ 100", "NASDAQ", "S&P 500"}:
        if any(keyword in headline_text for keyword in ("tech boost", "technology stocks", "ai", "科技股")):
            reason, tags = f"科技权重股表现变化，带动指数{direction}", ["科技权重", "企业盈利", "资金流向"]
        elif any(keyword in headline_text for keyword in ("rate hike bets retreat", "fed", "rate", "inflation", "利率", "通胀")):
            reason, tags = f"联储利率预期变化，影响成长股估值，指数{direction}", ["联储政策", "利率预期", "成长股估值"]
        elif any(keyword in headline_text for keyword in ("earnings", "retail earnings", "财报")):
            reason, tags = f"企业财报预期变化，令指数{direction}", ["企业盈利", "业绩预期", "风险偏好"]
        else:
            reason, tags = f"当日美股资金风险偏好变化，令指数{direction}", ["市场情绪", "资金流向", "宏观预期"]
    elif symbol == "GOLD":
        if any(keyword in headline_text for keyword in ("softer dollar", "dollar weakens", "美元走弱")):
            reason, tags = f"美元走弱降低非美元买入成本，推动黄金{direction}", ["美元指数", "实际利率", "避险需求"]
        elif any(keyword in headline_text for keyword in ("rate", "fed", "利率")):
            reason, tags = f"利率预期回落，降低持有黄金的机会成本，黄金{direction}", ["实际利率", "联储政策", "避险需求"]
        else:
            reason, tags = f"避险需求与美元变化共同影响黄金{direction}", ["美元指数", "实际利率", "避险需求"]
    else:
        if any(keyword in headline_text for keyword in ("hormuz", "航运", "disruption")):
            reason, tags = f"霍尔木兹运输中断担忧压缩供应预期，推动油价{direction}", ["霍尔木兹", "供应中断", "地缘风险"]
        elif any(keyword in headline_text for keyword in ("inventory", "库存")):
            reason, tags = f"原油库存预期变化影响供需判断，油价{direction}", ["原油库存", "供需预期", "OPEC+"]
        else:
            reason, tags = f"供应风险与库存预期变化，令油价{direction}", ["OPEC+", "原油库存", "地缘风险"]
    evidence = headlines[0]["title"] if headlines else "当日公开市场信息"
    source = headlines[0]["source"] if headlines else "公开资讯"
    evidence_link = headlines[0]["link"] if headlines else ""
    source_summary = headlines[0].get("summary", "") if headlines else ""
    # Google News and many publishers do not provide a reliably reusable article
    # synopsis. Use a concise Chinese event brief instead of echoing headlines.
    reported_fact = summarize_headline(symbol, evidence)
    if "科技权重" in tags:
        mechanism = "纳斯达克 100 与纳指的科技权重较高，龙头科技股的上涨或回落会通过指数权重迅速放大到整体表现。"
        watch = "关注大型科技公司股价、财报指引，以及半导体和 AI 产业链新闻是否延续。"
    elif "联储政策" in tags:
        mechanism = "利率预期会改变未来现金流的折现率；对估值更敏感的成长股通常会比大盘对这一变化反应更强。"
        watch = "关注联储官员讲话、通胀与就业数据，以及利率期货对下一次会议的定价变化。"
    elif "企业盈利" in tags:
        mechanism = "财报和经营指引会直接改变市场对未来盈利的判断，进而影响估值和资金风险偏好。"
        watch = "关注重点公司的实际业绩、营收展望及市场对盈利预期的修正方向。"
    elif "市场波动" in tags:
        mechanism = "VIX 由标普 500 期权的隐含波动率计算得出；VIX 上升通常表示期权市场正在为更大的短期价格波动定价，并不等同于股市必然下跌。"
        watch = "关注标普 500 的实际波动、期权隐含波动率期限结构，以及重大宏观事件前后的避险需求。"
    elif "美元指数" in tags:
        mechanism = "黄金以美元计价；美元走弱时，其他货币持有者的购买成本下降，同时实际利率预期也会影响无息黄金的吸引力。"
        watch = "关注美元指数、美国实际利率、联储政策预期和避险需求的同步变化。"
    elif "霍尔木兹" in tags:
        mechanism = "霍尔木兹海峡是重要原油运输通道；运输受阻或延误会抬升即时供应风险溢价，并推高近月油价。"
        watch = "关注航运通行情况、产油国表态、库存数据以及原油期货近远月价差。"
    elif "原油库存" in tags:
        mechanism = "库存数据反映短期供需是否偏紧；低于预期的库存通常支持油价，高于预期则可能压制油价。"
        watch = "关注 EIA/API 库存、炼厂开工率、OPEC+ 供应政策及全球需求数据。"
    else:
        mechanism = "市场价格通常由资金风险偏好、宏观预期与相关资产联动共同决定，单条新闻不能解释全部涨跌。"
        watch = "关注后续宏观数据、利率和美元走势，以及同一主题是否被多家可靠媒体持续确认。"
    detail = f"【报道要点】{reported_fact}\n【市场影响】{mechanism}\n【后续观察】{watch}"
    return reason, detail, tags, source, evidence_link


def main() -> None:
    markets: list[dict] = []
    news_items: list[dict[str, str]] = []
    dates: list[str] = []
    for symbol, name, ticker, query, category in ASSETS:
        try:
            headlines = fetch_news(query, category)
        except (OSError, ET.ParseError):
            headlines = []
        if headlines:
            headlines[0]["summary"] = fetch_article_summary(headlines[0]["link"])
        value, change, trade_date, history, session = fetch_quote(ticker)
        reason, detail, tags, evidence_source, evidence_link = explain(symbol, change, headlines)
        markets.append({
            "symbol": symbol,
            "name": name,
            "value": f"{value:,.2f}" if symbol in {"NASDAQ 100", "VIX", "S&P 500"} else f"${value:,.2f}",
            "change": round(change, 2),
            "history": history,
            "session": session,
            "reason": reason,
            "detail": detail,
            "tags": tags,
            "evidenceSource": evidence_source,
            "evidenceLink": evidence_link,
        })
        news_items.extend(headlines[:2])
        dates.append(trade_date)

    equity_change = (markets[0]["change"] + markets[2]["change"]) / 2
    title = "风险偏好回升" if equity_change > 0.25 else "风险情绪趋弱" if equity_change < -0.25 else "市场情绪相对谨慎"
    payload = {
        "date": max(dates),
        "updatedAt": datetime.now(timezone.utc).strftime("数据源：Yahoo Finance · UTC %Y-%m-%d %H:%M"),
        "pulse": {
            "title": title,
            "summary": f"纳指与标普平均变动 {equity_change:+.2f}%；黄金 {markets[2]['change']:+.2f}%，WTI 原油 {markets[3]['change']:+.2f}%。",
        },
        "markets": markets,
        "news": news_items[:8],
    }
    payload["pulse"]["summary"] = (
        f"\u7eb3\u65af\u8fbe\u514b 100 \u4e0e\u6807\u666e\u5e73\u5747\u53d8\u52a8 {equity_change:+.2f}%\uff1b"
        f"VIX {markets[1]['change']:+.2f}%\uff0c\u9ec4\u91d1 {markets[3]['change']:+.2f}%\uff0cWTI \u539f\u6cb9 {markets[4]['change']:+.2f}%\u3002"
    )
    output = Path(__file__).resolve().parents[1] / "apps" / "dsa-web" / "public" / "market.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {output} for {payload['date']}")


if __name__ == "__main__":
    main()
