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

ASSETS = (
    ("NASDAQ 100", "纳斯达克 100 指数", "^NDX", "Nasdaq 100 technology stocks Federal Reserve", "美股"),
    ("NASDAQ", "纳斯达克综合指数", "^IXIC", "Nasdaq stock market Federal Reserve", "美股"),
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
    closes = [value for value in result["indicators"]["quote"][0]["close"] if value is not None]
    if len(closes) < 2:
        raise RuntimeError(f"insufficient quote history for {ticker}")
    current, previous = closes[-1], closes[-2]
    change = (current / previous - 1) * 100
    trade_date = datetime.fromtimestamp(result["timestamp"][-1], timezone.utc).strftime("%Y.%m.%d")
    regular = result.get("meta", {}).get("currentTradingPeriod", {}).get("regular", {})
    is_regular_session = regular.get("start", 0) <= time() <= regular.get("end", -1)
    session = "盘中快照" if is_regular_session else "最近日线"
    return current, change, trade_date, [round(value, 2) for value in closes[-5:]], session


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


def explain(symbol: str, change: float, headlines: list[dict[str, str]]) -> tuple[str, str, list[str]]:
    direction = "走强" if change >= 0 else "承压"
    headline_text = " ".join(item["title"] for item in headlines).lower()
    if symbol in {"NASDAQ 100", "NASDAQ", "S&P 500"}:
        if any(keyword in headline_text for keyword in ("fed", "rate", "inflation", "利率", "通胀")):
            reason, tags = f"利率预期变化，指数{direction}", ["利率预期", "宏观数据", "风险偏好"]
        elif any(keyword in headline_text for keyword in ("earnings", "tech", "ai", "财报", "科技")):
            reason, tags = f"科技与盈利预期主导，指数{direction}", ["科技权重", "企业盈利", "资金流向"]
        else:
            reason, tags = f"风险偏好波动，指数{direction}", ["市场情绪", "资金流向", "宏观预期"]
    elif symbol == "GOLD":
        reason, tags = f"美元与利率预期影响，黄金{direction}", ["美元指数", "实际利率", "避险需求"]
    else:
        reason, tags = f"供应与库存预期变化，油价{direction}", ["OPEC+", "原油库存", "地缘风险"]
    evidence = headlines[0]["title"] if headlines else "当日公开市场信息"
    detail = f"当日价格{direction} {abs(change):.2f}%。资讯焦点包括“{evidence}”，与价格方向共同指向上述可能驱动因素。"
    return reason, detail, tags


def main() -> None:
    markets: list[dict] = []
    news_items: list[dict[str, str]] = []
    dates: list[str] = []
    for symbol, name, ticker, query, category in ASSETS:
        try:
            headlines = fetch_news(query, category)
        except (OSError, ET.ParseError):
            headlines = []
        value, change, trade_date, history, session = fetch_quote(ticker)
        reason, detail, tags = explain(symbol, change, headlines)
        markets.append({
            "symbol": symbol,
            "name": name,
            "value": f"{value:,.2f}" if symbol in {"NASDAQ 100", "NASDAQ", "S&P 500"} else f"${value:,.2f}",
            "change": round(change, 2),
            "history": history,
            "session": session,
            "reason": reason,
            "detail": detail,
            "tags": tags,
        })
        news_items.extend(headlines[:2])
        dates.append(trade_date)

    equity_change = sum(item["change"] for item in markets[:3]) / 3
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
        f"\u7eb3\u6307\u3001\u7eb3\u65af\u8fbe\u514b 100 \u4e0e\u6807\u666e\u5e73\u5747\u53d8\u52a8 {equity_change:+.2f}%\uff1b"
        f"\u9ec4\u91d1 {markets[3]['change']:+.2f}%\uff0cWTI \u539f\u6cb9 {markets[4]['change']:+.2f}%\u3002"
    )
    output = Path(__file__).resolve().parents[1] / "apps" / "dsa-web" / "public" / "market.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {output} for {payload['date']}")


if __name__ == "__main__":
    main()
