"""
データ取得モジュール
- RSS フィードからニュース取得
- yfinance で株価・指数データ取得
"""

import feedparser
import yfinance as yf
import yaml
import os
from datetime import datetime, timedelta
import traceback


def load_config():
    """config.yaml を読み込む"""
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


FINANCE_KEYWORDS = [
    "株", "市場", "日経", "TOPIX", "指数", "金利", "為替", "円安", "円高",
    "ドル", "債券", "利回り", "FRB", "日銀", "金融", "決算", "業績",
    "投資", "ファンド", "ETF", "IPO", "上場", "配当", "増収", "減収",
    "景気", "GDP", "インフレ", "デフレ", "利上げ", "利下げ", "緩和",
    "半導体", "AI", "セクター", "銘柄", "株価", "売買", "相場",
    "economy", "stock", "market", "Fed", "rate", "inflation", "GDP",
    "earnings", "bond", "yield", "trade", "tariff", "S&P", "Nasdaq",
    "鉄鋼", "エネルギー", "原油", "PMI", "雇用", "失業",
    "輸出", "輸入", "貿易", "関税", "規制", "補助金",
]


def _is_finance_related(title):
    """ニュース見出しが投資・経済に関連するか判定"""
    title_lower = title.lower()
    return any(kw.lower() in title_lower for kw in FINANCE_KEYWORDS)


def fetch_rss_feeds(config):
    """RSSフィードからニュースを取得（投資関連のみフィルタ）"""
    all_news = []
    for feed_info in config.get("rss_feeds", []):
        try:
            feed = feedparser.parse(feed_info["url"])
            for entry in feed.entries[:15]:
                title = entry.get("title", "")
                if not _is_finance_related(title):
                    continue

                published = ""
                if hasattr(entry, "published"):
                    published = entry.published
                elif hasattr(entry, "updated"):
                    published = entry.updated

                all_news.append({
                    "title": title,
                    "link": entry.get("link", ""),
                    "source": feed_info["name"],
                    "category": feed_info["category"],
                    "published": published,
                    "summary": entry.get("summary", "")[:200],
                })
        except Exception as e:
            print(f"[WARN] RSS取得失敗 ({feed_info['name']}): {e}")
            continue
    return all_news


def _make_sparkline_svg(prices):
    """終値リストからスパークラインSVGパスを生成"""
    if not prices or len(prices) < 2:
        return ""
    w, h = 120, 32
    mn, mx = min(prices), max(prices)
    rng = mx - mn if mx != mn else 1
    pad = 2
    points = []
    for i, p in enumerate(prices):
        x = round(i / (len(prices) - 1) * w, 1)
        y = round(pad + (1 - (p - mn) / rng) * (h - pad * 2), 1)
        points.append(f"{x},{y}")
    path = "M" + " L".join(points)
    return path


def fetch_index_data(config):
    """主要指数の最新データを取得（スパークライン用履歴付き）"""
    indices = []
    for idx_info in config.get("indices", []):
        try:
            ticker = yf.Ticker(idx_info["code"])
            hist = ticker.history(period="1mo")
            if len(hist) < 1:
                print(f"[WARN] 指数データなし: {idx_info['name']}")
                indices.append({
                    "name": idx_info["name"],
                    "code": idx_info["code"],
                    "price": None,
                    "change": None,
                    "change_pct": None,
                    "sparkline": "",
                })
                continue

            latest = hist.iloc[-1]
            price = latest["Close"]

            if len(hist) >= 2:
                prev = hist.iloc[-2]["Close"]
                change = price - prev
                change_pct = (change / prev) * 100
            else:
                change = 0
                change_pct = 0

            spark_prices = [float(row["Close"]) for _, row in hist.tail(20).iterrows()]
            sparkline = _make_sparkline_svg(spark_prices)

            indices.append({
                "name": idx_info["name"],
                "code": idx_info["code"],
                "price": round(float(price), 2),
                "change": round(float(change), 2),
                "change_pct": round(float(change_pct), 2),
                "sparkline": sparkline,
            })
        except Exception as e:
            print(f"[WARN] 指数取得失敗 ({idx_info['name']}): {e}")
            indices.append({
                "name": idx_info["name"],
                "code": idx_info["code"],
                "price": None,
                "change": None,
                "change_pct": None,
                "sparkline": "",
            })
    return indices


def fetch_watchlist_data(config):
    """ウォッチリスト銘柄のデータを取得"""
    stocks = []
    for stock_info in config.get("watchlist", []):
        try:
            ticker = yf.Ticker(stock_info["code"])
            hist = ticker.history(period="5d")
            if len(hist) < 1:
                stocks.append({
                    "name": stock_info["name"],
                    "code": stock_info["code"],
                    "theme": stock_info["theme"],
                    "price": None,
                    "change": None,
                    "change_pct": None,
                })
                continue

            latest = hist.iloc[-1]
            price = latest["Close"]

            if len(hist) >= 2:
                prev = hist.iloc[-2]["Close"]
                change = price - prev
                change_pct = (change / prev) * 100
            else:
                change = 0
                change_pct = 0

            stocks.append({
                "name": stock_info["name"],
                "code": stock_info["code"],
                "theme": stock_info["theme"],
                "price": round(float(price), 2),
                "change": round(float(change), 2),
                "change_pct": round(float(change_pct), 2),
            })
        except Exception as e:
            print(f"[WARN] 銘柄取得失敗 ({stock_info['name']}): {e}")
            stocks.append({
                "name": stock_info["name"],
                "code": stock_info["code"],
                "theme": stock_info["theme"],
                "price": None,
                "change": None,
                "change_pct": None,
            })
    return stocks


def fetch_sector_data(config):
    """セクターETFのデータを取得（ヒートマップ用）"""
    sectors = []
    for sector_info in config.get("sector_etfs", []):
        try:
            ticker = yf.Ticker(sector_info["code"])
            hist = ticker.history(period="5d")
            if len(hist) < 2:
                sectors.append({
                    "name": sector_info["name"],
                    "change_pct": 0,
                })
                continue

            latest = hist.iloc[-1]["Close"]
            prev = hist.iloc[-2]["Close"]
            change_pct = ((latest - prev) / prev) * 100

            sectors.append({
                "name": sector_info["name"],
                "change_pct": round(float(change_pct), 2),
            })
        except Exception as e:
            print(f"[WARN] セクター取得失敗 ({sector_info['name']}): {e}")
            sectors.append({
                "name": sector_info["name"],
                "change_pct": 0,
            })
    return sectors


def fetch_all_data():
    """全データを取得して辞書で返す"""
    config = load_config()
    print("[INFO] データ取得開始...")

    print("[INFO] RSS取得中...")
    news = fetch_rss_feeds(config)
    print(f"[INFO] ニュース {len(news)} 件取得")

    print("[INFO] 指数データ取得中...")
    indices = fetch_index_data(config)

    print("[INFO] ウォッチリスト取得中...")
    watchlist = fetch_watchlist_data(config)

    print("[INFO] セクターデータ取得中...")
    sectors = fetch_sector_data(config)

    return {
        "news": news,
        "indices": indices,
        "watchlist": watchlist,
        "sectors": sectors,
        "config": config,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M JST"),
    }


if __name__ == "__main__":
    import json
    data = fetch_all_data()
    print(json.dumps(data, ensure_ascii=False, indent=2))
