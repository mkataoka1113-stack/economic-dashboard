"""
ダッシュボードHTML生成メインスクリプト
- fetch_data でデータ取得
- analyze で AI分析
- Jinja2 でHTML生成 → docs/index.html に出力
"""

import os
import sys
import json

# scriptsディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(__file__))

from fetch_data import fetch_all_data
from analyze import analyze_market
from jinja2 import Environment, FileSystemLoader


def generate():
    """メイン生成処理"""
    project_root = os.path.join(os.path.dirname(__file__), "..")

    # 1. データ取得
    print("=" * 50)
    print("経済動向ダッシュボード 生成開始")
    print("=" * 50)
    data = fetch_all_data()

    # 2. AI分析
    print("[INFO] AI分析開始...")
    analysis = analyze_market(data)
    print(f"[INFO] AI分析完了 (provider: {analysis.get('_provider', 'unknown')})")

    # 2.5. ニュースにAIコメントをマージ
    news_comments = {nc["index"]: nc["comment"] for nc in analysis.get("news_comments", [])}
    for i, item in enumerate(data["news"]):
        item["ai_comment"] = news_comments.get(i, "")

    # 3. HTML生成
    print("[INFO] HTML生成中...")
    template_dir = os.path.join(project_root, "templates")
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template("dashboard.html")

    html = template.render(
        indices=data["indices"],
        watchlist=data["watchlist"],
        sectors=data["sectors"],
        news=data["news"],
        analysis=analysis,
        updated_at=data["updated_at"],
        provider=analysis.get("_provider", "unknown"),
    )

    # 4. 出力
    output_dir = os.path.join(project_root, "docs")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "index.html")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[INFO] ダッシュボード生成完了: {output_path}")
    print("=" * 50)


if __name__ == "__main__":
    generate()
