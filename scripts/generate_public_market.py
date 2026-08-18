#!/usr/bin/env python3
"""Generate the static GitHub Pages market brief from public market/news feeds."""
from __future__ import annotations

import json
import os
import re
import html
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from time import sleep, time
from zoneinfo import ZoneInfo

try:
    from googlenewsdecoder import gnewsdecoder
except ImportError:  # Local fallback; GitHub Actions installs the resolver.
    gnewsdecoder = None

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


def fetch_meta_summary(url: str) -> str:
    if not url:
        return ""
    try:
        page = request_bytes(url).decode("utf-8", errors="ignore")
    except OSError:
        return ""
    for pattern in (
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']',
    ):
        match = re.search(pattern, page, flags=re.IGNORECASE)
        if match:
            summary = re.sub(r"\s+", " ", html.unescape(match.group(1))).strip()
            if summary and "aggregated from sources all over the world by google news" not in summary.lower():
                return summary[:600]
    return ""


def enrich_news_item(item: dict[str, str]) -> dict[str, str]:
    enriched = dict(item)
    if gnewsdecoder is None:
        enriched["summary"] = ""
        return enriched
    try:
        decoded = gnewsdecoder(item["link"], interval=0)
        original_url = decoded.get("decoded_url", "") if decoded.get("status") else ""
    except Exception as error:
        print(f"News URL resolution failed for {item['source']}: {error}")
        original_url = ""
    if original_url:
        enriched["link"] = original_url
        enriched["summary"] = fetch_meta_summary(original_url)
    else:
        enriched["summary"] = ""
    return enriched


def discover_openai_model(base_url: str, token: str) -> str:
    configured = os.environ.get("OPENAI_MODEL", "").strip()
    if configured:
        return configured
    request = urllib.request.Request(
        f"{base_url}/models",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read())
        model_ids = [item.get("id", "") for item in payload.get("data", []) if item.get("id")]
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"Model discovery unavailable: {error}")
        model_ids = []
    priorities = ("gpt-4o-mini", "gpt-4.1-mini", "deepseek-chat", "deepseek-v3", "qwen")
    for preferred in priorities:
        match = next((model_id for model_id in model_ids if preferred in model_id.lower()), None)
        if match:
            print(f"Auto-selected market analysis model: {match}")
            return match
    usable = next((
        model_id for model_id in model_ids
        if not any(word in model_id.lower() for word in ("embedding", "image", "audio", "tts", "rerank"))
    ), None)
    if usable:
        print(f"Auto-selected market analysis model: {usable}")
        return usable
    return "gpt-4o-mini"


def generate_ai_analysis(markets: list[dict], news_by_symbol: dict[str, list[dict[str, str]]]) -> dict[str, dict]:
    openai_key = os.environ.get("OPENAI_API_KEY")
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    if openai_key:
        token = openai_key
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        model = discover_openai_model(base_url, token)
    elif deepseek_key:
        token = deepseek_key
        base_url = "https://api.deepseek.com"
        model = "deepseek-chat"
    else:
        print("AI analysis unavailable: no OPENAI_API_KEY or DEEPSEEK_API_KEY configured")
        return {}
    context = [
        {
            "symbol": market["symbol"],
            "name": market["name"],
            "change": market["change"],
            "news": [
                {
                    "title": item["title"],
                    "source": item["source"],
                    "time": item["time"],
                    "publicSummary": item.get("summary", ""),
                }
                for item in news_by_symbol.get(market["symbol"], [])
            ],
        }
        for market in markets
    ]
    prompt = (
        "根据以下刚抓取的行情、新闻标题与媒体公开摘要，为每个品种生成实时中文解读。只使用输入中的事实，不补造新闻内容，"
        "不要复述或展示新闻标题。每项返回：reason（一句话具体原因）、brief（两句内简要总结新闻内容）、"
        "impact（说明为何影响该品种及方向）、watch（后续关注事项）、tags（2到4个短标签）。"
        "若证据不足，明确写‘现有新闻不足以确认具体原因’，不得套用通用模板。"
        "VIX 上涨表示预期波动扩大，不要把它当普通股指。输出严格 JSON："
        '{"markets":[{"symbol":"...","reason":"...","brief":"...","impact":"...","watch":"...","tags":["..."]}]}\n'
        f"输入数据：{json.dumps(context, ensure_ascii=False)}"
    )
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "你是严谨的中文市场日报编辑，区分事实、推断与不确定性。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 2200,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=body,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": HEADERS["User-Agent"],
        },
        method="POST",
    )
    for attempt, delay in enumerate((0, 5, 15), start=1):
        if delay:
            sleep(delay)
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                result = json.loads(response.read())
            content = result["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE)
            parsed = json.loads(content)
            return {item["symbol"]: item for item in parsed.get("markets", []) if item.get("symbol")}
        except urllib.error.HTTPError as error:
            response_body = error.read().decode("utf-8", errors="ignore")[:500]
            print(f"AI analysis attempt {attempt} failed: HTTP {error.code} {response_body}")
            if error.code not in {429, 500, 502, 503, 504}:
                break
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            print(f"AI analysis attempt {attempt} failed: {error}")
    return {}


def main() -> None:
    markets: list[dict] = []
    news_items: list[dict[str, str]] = []
    news_by_symbol: dict[str, list[dict[str, str]]] = {}
    dates: list[str] = []
    for symbol, name, ticker, query, category in ASSETS:
        try:
            headlines = [enrich_news_item(item) for item in fetch_news(query, category)]
        except (OSError, ET.ParseError):
            headlines = []
        value, change, trade_date, history, session = fetch_quote(ticker)
        markets.append({
            "symbol": symbol,
            "name": name,
            "value": f"{value:,.2f}" if symbol in {"NASDAQ 100", "VIX", "S&P 500"} else f"${value:,.2f}",
            "change": round(change, 2),
            "history": history,
            "session": session,
        })
        news_by_symbol[symbol] = headlines
        news_items.extend(headlines[:2])
        dates.append(trade_date)

    ai_analysis = generate_ai_analysis(markets, news_by_symbol)
    for market in markets:
        analysis = ai_analysis.get(market["symbol"], {})
        headlines = news_by_symbol.get(market["symbol"], [])
        source = headlines[0] if headlines else {}
        if analysis:
            market.update({
                "reason": analysis.get("reason", "实时解读暂不可用"),
                "detail": (
                    f"【报道要点】{analysis.get('brief', '现有新闻不足以形成可靠摘要。')}\n"
                    f"【市场影响】{analysis.get('impact', '现有信息不足以判断具体影响。')}\n"
                    f"【后续观察】{analysis.get('watch', '等待下一次数据更新。')}"
                ),
                "tags": analysis.get("tags", [])[:4],
                "analysisStatus": "实时生成",
            })
        else:
            market.update({
                "reason": "实时解读暂不可用",
                "detail": "【状态】行情和新闻已更新，但本次 AI 解读生成失败；页面不会使用固定模板代替。",
                "tags": ["等待重新生成"],
                "analysisStatus": "生成失败",
            })
        market["evidenceSource"] = source.get("source", "")
        market["evidenceLink"] = source.get("link", "")

    equity_change = (markets[0]["change"] + markets[2]["change"]) / 2
    title = "风险偏好回升" if equity_change > 0.25 else "风险情绪趋弱" if equity_change < -0.25 else "市场情绪相对谨慎"
    payload = {
        "date": max(dates),
        "updatedAt": datetime.now(timezone.utc).strftime("数据源：Yahoo Finance · UTC %Y-%m-%d %H:%M"),
        "analysisGeneratedAt": datetime.now(timezone.utc).isoformat(timespec="minutes"),
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
