"""
AI分析モジュール
- Gemini Flash（メイン）→ Groq → Cerebras のフォールバック構成
- ニュース要約・テーマ抽出・学びコーナー生成
- 個人情報は一切送らない（公開ニュースのみ）
"""

import os
import json
import traceback


def _call_gemini(prompt):
    """Gemini Flash APIを呼び出す"""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY が設定されていません")

    from google import genai

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
    )
    return response.text


def _call_groq(prompt):
    """Groq APIを呼び出す（フォールバック1）"""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY が設定されていません")

    import requests
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 4000,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _call_cerebras(prompt):
    """Cerebras APIを呼び出す（フォールバック2）"""
    api_key = os.environ.get("CEREBRAS_API_KEY")
    if not api_key:
        raise ValueError("CEREBRAS_API_KEY が設定されていません")

    import requests
    response = requests.post(
        "https://api.cerebras.ai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "llama-3.3-70b",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 4000,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def call_llm(prompt):
    """LLMをフォールバック付きで呼び出す"""
    providers = [
        ("Gemini", _call_gemini),
        ("Groq", _call_groq),
        ("Cerebras", _call_cerebras),
    ]

    for name, func in providers:
        try:
            print(f"[INFO] {name} に問い合わせ中...")
            result = func(prompt)
            print(f"[INFO] {name} から応答取得成功")
            return result, name
        except Exception as e:
            print(f"[WARN] {name} 失敗: {e}")
            continue

    print("[ERROR] 全LLMプロバイダーが失敗しました")
    return None, None


def analyze_market(data):
    """市場データを分析してダッシュボード用コンテンツを生成"""

    # ニュースの見出しだけを抽出（個人情報は含まない）
    news_titles = []
    for n in data["news"][:30]:
        news_titles.append(f"- [{n['source']}] {n['title']}")
    news_text = "\n".join(news_titles)

    # 指数サマリー
    index_text = []
    for idx in data["indices"]:
        if idx["price"] is not None:
            direction = "↑" if idx["change"] >= 0 else "↓"
            index_text.append(
                f"- {idx['name']}: {idx['price']:,.2f} ({direction}{abs(idx['change_pct']):.2f}%)"
            )
    index_summary = "\n".join(index_text)

    # セクターサマリー
    sector_text = []
    for s in data["sectors"]:
        direction = "↑" if s["change_pct"] >= 0 else "↓"
        sector_text.append(f"- {s['name']}: {direction}{abs(s['change_pct']):.2f}%")
    sector_summary = "\n".join(sector_text)

    # 固定テーマ
    fixed_themes = data["config"].get("fixed_themes", [])
    themes_text = "、".join(fixed_themes)

    # 学習レベル
    level = data["config"].get("learning_level", "beginner")
    level_desc = {
        "beginner": "投資初心者向け（専門用語を使う場合は必ず平易な説明を添える）",
        "intermediate": "中級者向け（基本用語は説明不要、やや専門的な内容もOK）",
        "advanced": "上級者向け（専門的な分析やテクニカル指標にも触れてOK）",
    }.get(level, "投資初心者向け")

    prompt = f"""あなたは日本の株式市場・経済動向の専門アナリストです。
以下のデータを基に、経済動向ダッシュボード用のコンテンツを日本語で生成してください。

【重要】必ず以下のJSON形式で出力してください。JSON以外のテキストは一切含めないでください。

## 入力データ

### 主要指数
{index_summary}

### セクター動向
{sector_summary}

### 最新ニュース見出し
{news_text}

### 固定追跡テーマ
{themes_text}

## 出力JSON形式
{{
  "market_summary": "本日の市場概況を3〜4文で簡潔にまとめる",
  "themes": [
    {{
      "title": "テーマ名",
      "description": "なぜ今このテーマに資金が向かうのか、背景を2〜3文で解説",
      "sentiment": "positive/negative/neutral"
    }}
  ],
  "macro_environment": "日米の金利・為替・海外市場の状況とリスク要因を3〜4文で解説",
  "upcoming_events": [
    {{
      "date": "日付や時期",
      "event": "イベント名",
      "impact": "市場への影響を1文で"
    }}
  ],
  "daily_learning": {{
    "term": "今日の用語・概念",
    "explanation": "{level_desc}で解説。具体例を1つ含める"
  }},
  "watchlist_comments": [
    {{
      "code": "銘柄コード",
      "comment": "現在の注目ポイントを1〜2文で"
    }}
  ]
}}

注意事項:
- テーマは固定テーマ（{themes_text}）を必ず含め、加えてトレンドテーマを2〜3個追加し、合計5〜6個にする
- upcoming_eventsは今後1〜2週間の重要イベントを3〜5個
- 客観的な事実ベースで記述し、投資推奨は行わない
- JSON形式のみ出力。```json などのマークダウン記法は不要
"""

    result, provider = call_llm(prompt)

    if result is None:
        return _fallback_analysis(data)

    try:
        # JSONを抽出（余分なテキストがある場合に対応）
        result = result.strip()
        if result.startswith("```"):
            lines = result.split("\n")
            result = "\n".join(lines[1:-1])

        # JSON部分を探す
        start = result.find("{")
        end = result.rfind("}") + 1
        if start >= 0 and end > start:
            result = result[start:end]

        analysis = json.loads(result)
        analysis["_provider"] = provider
        return analysis
    except json.JSONDecodeError as e:
        print(f"[WARN] JSON解析失敗: {e}")
        print(f"[DEBUG] LLM応答: {result[:500]}")
        return _fallback_analysis(data)


def _fallback_analysis(data):
    """LLMが使えない場合の最低限の分析"""
    return {
        "market_summary": "AI分析は現在利用できません。指数データとニュース見出しをご確認ください。",
        "themes": [
            {"title": t, "description": "データ取得中...", "sentiment": "neutral"}
            for t in data["config"].get("fixed_themes", [])
        ],
        "macro_environment": "AI分析サービスに接続できませんでした。次回更新時に再試行します。",
        "upcoming_events": [],
        "daily_learning": {
            "term": "—",
            "explanation": "AI分析サービス復旧後に生成されます。"
        },
        "watchlist_comments": [],
        "_provider": "fallback",
    }
