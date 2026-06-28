"""ダッシュボードHTML生成メインスクリプト"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(__file__))

from fetch_data import fetch_all_data
from analyze import analyze_market
from jinja2 import Environment, FileSystemLoader


def generate():
    project_root = os.path.join(os.path.dirname(__file__), "..")

    print("=" * 50)
    print("経済動向ダッシュボード 生成開始")
    print("=" * 50)

    data = fetch_all_data()

    print("[INFO] AI分析開始...")
    analysis = analyze_market(data)
    print(f"[INFO] AI分析完了 (provider: {analysis.get('_provider', 'unknown')})")

    # ニュースにAIコメントをマージ
    news_comments = {nc["index"]: nc["comment"] for nc in analysis.get("news_comments", [])}
    for i, item in enumerate(data["news"]):
        item["ai_comment"] = news_comments.get(i, "")

    # FANG+にAIハイライトをマージ
    fang_highlights = {fh["ticker"]: fh["highlight"] for fh in analysis.get("fang_highlights", [])}
    for s in data["fang_plus"]:
        s["highlight"] = fang_highlights.get(s["ticker"], "")

    print("[INFO] HTML生成中...")
    template_dir = os.path.join(project_root, "templates")
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template("dashboard.html")

    html = template.render(
        indices=data["indices"],
        nisa_indices=data["nisa_indices"],
        fang_plus=data["fang_plus"],
        investment_themes=data["investment_themes"],
        watchlist=data["watchlist"],
        sectors=data["sectors"],
        news=data["news"],
        analysis=analysis,
        updated_at=data["updated_at"],
        provider=analysis.get("_provider", "unknown"),
    )

    output_dir = os.path.join(project_root, "docs")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "index.html")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[INFO] 生成完了: {output_path}")
    print("=" * 50)


if __name__ == "__main__":
    generate()
