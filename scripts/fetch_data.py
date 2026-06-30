"""
データ取得モジュール
- yfinance で株価・指数・ETFデータ取得
- RSS フィードからニュース取得
"""

import json
import math
import feedparser
import yfinance as yf
import yaml
import os
from datetime import datetime, timedelta, timezone
import traceback


def _safe_float(val):
    if val is None:
        return None
    f = float(val)
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def load_config():
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
    "輸出", "輸入", "貿易", "関税", "規制", "補助金", "ビットコイン", "仮想通貨",
]


def _is_finance_related(title):
    title_lower = title.lower()
    return any(kw.lower() in title_lower for kw in FINANCE_KEYWORDS)


def _make_sparkline_svg(prices):
    if not prices or len(prices) < 2:
        return ""
    w, h = 120, 32
    mn, mx = min(prices), max(prices)
    rng = mx - mn if mx != mn else 1
    pad = 5
    points = []
    for i, p in enumerate(prices):
        x = round(i / (len(prices) - 1) * w, 1)
        y = round(pad + (1 - (p - mn) / rng) * (h - pad * 2), 1)
        points.append(f"{x},{y}")
    return "M" + " L".join(points)


def _fetch_ticker_1yr(ticker_str):
    """1年分の履歴を取得して共通フォーマットで返す"""
    ticker = yf.Ticker(ticker_str)
    hist = ticker.history(period="1y")
    if len(hist) < 2:
        return None, None, None, None, None

    price = _safe_float(hist.iloc[-1]["Close"])
    prev  = _safe_float(hist.iloc[-2]["Close"])
    if price is None or prev is None or prev == 0:
        return None, None, None, None, None

    change_pct = (price - prev) / prev * 100
    spark_prices = [float(r["Close"]) for _, r in hist.tail(20).iterrows()
                    if _safe_float(r["Close"]) is not None]
    sparkline = _make_sparkline_svg(spark_prices)
    dates  = [str(d.date()) for d in hist.index]
    prices = [round(float(r["Close"]), 4) for _, r in hist.iterrows()
              if _safe_float(r["Close"]) is not None]
    return price, change_pct, sparkline, dates, prices


# ── 各セクションのデータ取得 ──────────────────────────

def fetch_rss_feeds(config):
    all_news = []
    for feed_info in config.get("rss_feeds", []):
        try:
            feed = feedparser.parse(feed_info["url"])
            for entry in feed.entries[:15]:
                title = entry.get("title", "")
                if not _is_finance_related(title):
                    continue
                published = getattr(entry, "published", "") or getattr(entry, "updated", "")
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
    return all_news


def fetch_index_data(config):
    """ヘッダー用主要指数（1ヶ月履歴）"""
    indices = []
    for idx_info in config.get("indices", []):
        try:
            ticker = yf.Ticker(idx_info["code"])
            hist = ticker.history(period="1mo")
            if len(hist) < 1:
                indices.append({**idx_info, "price": None, "change": None,
                                "change_pct": None, "sparkline": "", "sparkline_prices_json": "[]"})
                continue

            price = _safe_float(hist.iloc[-1]["Close"])
            if price is None:
                indices.append({**idx_info, "price": None, "change": None,
                                "change_pct": None, "sparkline": "", "sparkline_prices_json": "[]"})
                continue

            change, change_pct = 0.0, 0.0
            if len(hist) >= 2:
                prev = _safe_float(hist.iloc[-2]["Close"])
                if prev and prev != 0:
                    change = price - prev
                    change_pct = change / prev * 100

            spark_prices = [float(r["Close"]) for _, r in hist.tail(20).iterrows()
                            if _safe_float(r["Close"]) is not None]
            sparkline = _make_sparkline_svg(spark_prices)

            if spark_prices and spark_prices[0] != 0:
                base = spark_prices[0]
                spark_pct = [round((p - base) / base * 100, 3) for p in spark_prices]
            else:
                spark_pct = []

            indices.append({
                "name": idx_info["name"],
                "code": idx_info["code"],
                "price": round(price, 2),
                "change": round(float(change), 2),
                "change_pct": round(float(change_pct), 2),
                "sparkline": sparkline,
                "sparkline_prices_json": json.dumps(spark_pct),
            })
        except Exception as e:
            print(f"[WARN] 指数取得失敗 ({idx_info['name']}): {e}")
            indices.append({**idx_info, "price": None, "change": None,
                            "change_pct": None, "sparkline": "", "sparkline_prices_json": "[]"})
    return indices


def fetch_nisa_indices(config):
    """NISA候補ファンドが連動する指数（1年履歴付き）"""
    result = []
    for item in config.get("nisa_indices", []):
        try:
            price, change_pct, sparkline, dates, prices = _fetch_ticker_1yr(item["ticker"])
            if price is None:
                continue

            # 1ヶ月リターン（約21営業日）
            month_ret = 0.0
            if len(prices) >= 21:
                base = prices[-21]
                if base and base != 0:
                    month_ret = (prices[-1] - base) / base * 100

            # 1年リターン
            year_ret = 0.0
            if prices:
                base = prices[0]
                if base and base != 0:
                    year_ret = (prices[-1] - base) / base * 100

            result.append({
                "ticker":       item["ticker"],
                "name":         item["name"],
                "fund_example": item.get("fund_example", ""),
                "description":  item.get("description", ""),
                "price":        round(float(price), 2),
                "change_pct":   round(float(change_pct), 2),
                "month_ret":    round(float(month_ret), 2),
                "year_ret":     round(float(year_ret), 2),
                "sparkline":    sparkline,
                "dates_json":   json.dumps(dates),
                "prices_json":  json.dumps(prices),
            })
        except Exception as e:
            print(f"[WARN] NISA指数取得失敗 ({item.get('name','?')}): {e}")
    return result


def fetch_fang_plus(config):
    """FANG+構成銘柄（1年履歴付き）"""
    stocks = []
    for item in config.get("fang_plus", []):
        try:
            price, change_pct, sparkline, dates, prices = _fetch_ticker_1yr(item["ticker"])
            if price is None:
                continue
            stocks.append({
                "name":        item["name"],
                "ticker":      item["ticker"],
                "price":       round(float(price), 2),
                "change_pct":  round(float(change_pct), 2),
                "sparkline":   sparkline,
                "dates_json":  json.dumps(dates),
                "prices_json": json.dumps(prices),
            })
        except Exception as e:
            print(f"[WARN] FANG+取得失敗 ({item.get('ticker','?')}): {e}")
    return stocks


def fetch_investment_themes(config):
    """世界の投資テーマ（カテゴリ別・1年履歴付き）"""
    themes = []
    for theme in config.get("investment_themes", []):
        items = []
        for item in theme.get("items", []):
            try:
                price, change_pct, sparkline, dates, prices = _fetch_ticker_1yr(item["ticker"])
                if price is None:
                    continue
                items.append({
                    "ticker":      item["ticker"],
                    "name":        item["name"],
                    "unit":        item.get("unit", "USD"),
                    "price":       round(float(price), 4),
                    "change_pct":  round(float(change_pct), 2),
                    "sparkline":   sparkline,
                    "dates_json":  json.dumps(dates),
                    "prices_json": json.dumps(prices),
                })
            except Exception as e:
                print(f"[WARN] テーマ銘柄取得失敗 ({item.get('ticker','?')}): {e}")

        themes.append({
            "category":    theme["category"],
            "label":       theme["label"],
            "description": theme.get("description", ""),
            "items":       items,
        })
    return themes


def fetch_watchlist_data(config):
    """日本株ウォッチリスト"""
    stocks = []
    for stock_info in config.get("watchlist", []):
        try:
            ticker = yf.Ticker(stock_info["code"])
            hist = ticker.history(period="5d")
            if len(hist) < 1:
                stocks.append({**stock_info, "price": None, "change": None, "change_pct": None})
                continue

            price = _safe_float(hist.iloc[-1]["Close"])
            if price is None:
                stocks.append({**stock_info, "price": None, "change": None, "change_pct": None})
                continue

            change, change_pct = 0.0, 0.0
            if len(hist) >= 2:
                prev = _safe_float(hist.iloc[-2]["Close"])
                if prev and prev != 0:
                    change = price - prev
                    change_pct = change / prev * 100

            stocks.append({
                "name":       stock_info["name"],
                "code":       stock_info["code"],
                "theme":      stock_info["theme"],
                "price":      round(float(price), 2),
                "change":     round(float(change), 2),
                "change_pct": round(float(change_pct), 2),
            })
        except Exception as e:
            print(f"[WARN] ウォッチリスト取得失敗 ({stock_info['name']}): {e}")
            stocks.append({**stock_info, "price": None, "change": None, "change_pct": None})
    return stocks


def fetch_sector_data(config):
    """セクターETF（ヒートマップ用）"""
    sectors = []
    for sector_info in config.get("sector_etfs", []):
        try:
            ticker = yf.Ticker(sector_info["code"])
            hist = ticker.history(period="5d")
            if len(hist) < 2:
                sectors.append({"name": sector_info["name"], "change_pct": 0})
                continue

            latest = _safe_float(hist.iloc[-1]["Close"])
            prev   = _safe_float(hist.iloc[-2]["Close"])
            change_pct = ((latest - prev) / prev * 100) if (latest and prev and prev != 0) else 0
            sectors.append({"name": sector_info["name"], "change_pct": round(float(change_pct), 2)})
        except Exception as e:
            print(f"[WARN] セクター取得失敗 ({sector_info['name']}): {e}")
            sectors.append({"name": sector_info["name"], "change_pct": 0})
    return sectors


# ── メイン ────────────────────────────────────────────

def fetch_all_data():
    config = load_config()
    print("[INFO] データ取得開始...")

    print("[INFO] RSS取得中...")
    news = fetch_rss_feeds(config)
    print(f"[INFO] ニュース {len(news)} 件")

    print("[INFO] 主要指数取得中...")
    indices = fetch_index_data(config)

    print("[INFO] NISA指数取得中...")
    nisa_indices = fetch_nisa_indices(config)

    print("[INFO] FANG+取得中...")
    fang_plus = fetch_fang_plus(config)

    print("[INFO] 投資テーマ取得中...")
    investment_themes = fetch_investment_themes(config)

    print("[INFO] ウォッチリスト取得中...")
    watchlist = fetch_watchlist_data(config)

    print("[INFO] セクターデータ取得中...")
    sectors = fetch_sector_data(config)

    JST = timezone(timedelta(hours=9))
    return {
        "news":              news,
        "indices":           indices,
        "nisa_indices":      nisa_indices,
        "fang_plus":         fang_plus,
        "investment_themes": investment_themes,
        "watchlist":         watchlist,
        "sectors":           sectors,
        "config":            config,
        "updated_at":        datetime.now(JST).strftime("%Y-%m-%d %H:%M JST"),
    }


if __name__ == "__main__":
    data = fetch_all_data()
    print(json.dumps({k: v for k, v in data.items() if k != "config"}, ensure_ascii=False, indent=2))
