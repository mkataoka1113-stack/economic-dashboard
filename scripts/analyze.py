"""
AI分析モジュール
- Gemini Flash → Groq → Cerebras のフォールバック構成
"""

import os
import json
import time
import traceback

MAX_RETRIES = 3
RETRY_DELAY = 10


def _call_gemini(prompt):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY が設定されていません")
    from google import genai
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    return response.text


def _call_groq(prompt):
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY が設定されていません")
    import requests
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}],
              "temperature": 0.3, "max_tokens": 6000},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _call_cerebras(prompt):
    api_key = os.environ.get("CEREBRAS_API_KEY")
    if not api_key:
        raise ValueError("CEREBRAS_API_KEY が設定されていません")
    import requests
    response = requests.post(
        "https://api.cerebras.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": "llama-3.3-70b", "messages": [{"role": "user", "content": prompt}],
              "temperature": 0.3, "max_tokens": 6000},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def call_llm(prompt):
    providers = [("Gemini", _call_gemini), ("Groq", _call_groq), ("Cerebras", _call_cerebras)]
    for name, func in providers:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"[INFO] {name} に問い合わせ中... (試行 {attempt}/{MAX_RETRIES})")
                result = func(prompt)
                print(f"[INFO] {name} 応答取得成功")
                return result, name
            except ValueError:
                print(f"[WARN] {name}: APIキー未設定、スキップ")
                break
            except Exception as e:
                print(f"[WARN] {name} 失敗 (試行 {attempt}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES:
                    print(f"[INFO] {RETRY_DELAY}秒後にリトライ...")
                    time.sleep(RETRY_DELAY)
    print("[ERROR] 全LLMプロバイダーが失敗しました")
    return None, None


def analyze_market(data):
    news_titles = "\n".join(f"- [{n['source']}] {n['title']}" for n in data["news"][:30])

    index_summary = "\n".join(
        f"- {i['name']}: {i['price']:,.2f} ({'↑' if i['change'] >= 0 else '↓'}{abs(i['change_pct']):.2f}%)"
        for i in data["indices"] if i["price"] is not None
    )

    sector_summary = "\n".join(
        f"- {s['name']}: {'↑' if s['change_pct'] >= 0 else '↓'}{abs(s['change_pct']):.2f}%"
        for s in data["sectors"]
    )

    fang_summary = "\n".join(
        f"- {s['ticker']}: ${s['price']:,.2f} ({'↑' if s['change_pct'] >= 0 else '↓'}{abs(s['change_pct']):.2f}%)"
        for s in data["fang_plus"]
    )

    theme_summary = []
    for theme in data["investment_themes"]:
        items_text = ", ".join(
            f"{it['name']} {'+' if it['change_pct'] >= 0 else ''}{it['change_pct']:.2f}%"
            for it in theme["items"]
        )
        theme_summary.append(f"- {theme['label']}: {items_text}")
    theme_summary_text = "\n".join(theme_summary)

    fixed_themes = "、".join(data["config"].get("fixed_themes", []))
    level = data["config"].get("learning_level", "beginner")
    level_desc = {
        "beginner":     "投資初心者向け（専門用語には必ず平易な説明を添える）",
        "intermediate": "中級者向け（基本用語は説明不要）",
        "advanced":     "上級者向け（専門的な分析もOK）",
    }.get(level, "投資初心者向け")

    prompt = f"""あなたは日本の投資・経済の専門アナリストです。以下のデータを基に、投資学習ダッシュボード用コンテンツを日本語で生成してください。

【重要】必ず以下のJSON形式のみで出力してください。

## 入力データ

### 主要指数
{index_summary}

### FANG+銘柄
{fang_summary}

### 投資テーマ別値動き
{theme_summary_text}

### セクター動向
{sector_summary}

### 最新ニュース
{news_titles}

### 固定追跡テーマ
{fixed_themes}

## 出力JSON形式
{{
  "market_sentiment": {{
    "score": 0〜100の整数（0=極度の悲観、50=中立、100=極度の楽観）,
    "label": "市場の状態を一言で（例: 楽観、中立、悲観、慎重）",
    "summary": "本日の市場全体を2〜3文で。なぜその状態なのか原因も含める"
  }},
  "themes": [
    {{
      "title": "テーマ名",
      "description": "なぜ今このテーマに注目が集まるか2〜3文",
      "sentiment": "positive/negative/neutral"
    }}
  ],
  "fang_highlights": [
    {{
      "ticker": "銘柄コード",
      "highlight": "今日の注目ポイントを1文。株価変動の理由や注目材料"
    }}
  ],
  "theme_explanations": {{
    "commodities": {{
      "today": "今日のコモディティ市場の動きと背景（2文）",
      "what_is": "コモディティ投資とは何か、初心者向けに1〜2文"
    }},
    "crypto": {{
      "today": "今日の仮想通貨市場の動きと背景（2文）",
      "what_is": "仮想通貨投資とは何か、初心者向けに1〜2文"
    }},
    "emerging": {{
      "today": "今日の新興国市場の動きと背景（2文）",
      "what_is": "新興国株投資とは何か、初心者向けに1〜2文"
    }},
    "bonds": {{
      "today": "今日の債券市場の動きと背景（2文）",
      "what_is": "債券投資とは何か、初心者向けに1〜2文"
    }},
    "forex": {{
      "today": "今日の為替市場の動きと背景（2文）",
      "what_is": "為替と投資の関係を初心者向けに1〜2文"
    }}
  }},
  "nisa_commentary": "今日の市場状況をNISA長期投資家の視点から2〜3文でコメント。焦らず積立継続すべきか、注目点は何かなど",
  "trending_sectors": [
    {{
      "sector": "セクター名",
      "direction": "up/down",
      "reason": "なぜ今この業界が動いているか2〜3文"
    }}
  ],
  "daily_learning": {{
    "term": "今日の投資用語・概念",
    "explanation": "{level_desc}で解説。今日の実際の市場の動きと結びつけて説明する。具体例を1つ含める"
  }},
  "future_outlook": [
    {{
      "theme": "テーマ名",
      "horizon": "3ヶ月/6ヶ月/12ヶ月",
      "reason": "なぜ今後伸びると考えられるか、構造的な背景を2〜3文",
      "risk": "主なリスク要因を1文",
      "sentiment": "positive/cautious"
    }}
  ],
  "news_comments": [
    {{
      "index": 0,
      "comment": "このニュースの投資的な意味を1〜2文。推測・予想であることを明示する"
    }}
  ],
  "upcoming_events": [
    {{
      "date": "日付や時期",
      "event": "イベント名",
      "impact": "市場への影響を1文"
    }}
  ],
  "watchlist_comments": [
    {{
      "code": "銘柄コード",
      "comment": "現在の注目ポイントを1文"
    }}
  ]
}}

注意事項:
- themes: 固定テーマ（{fixed_themes}）を含め合計5〜6個
- future_outlook: 今後6〜12ヶ月で伸びそうなテーマを3〜5個。NISA長期投資家向け
- news_comments: 全ニュース（index 0〜{len(data["news"][:30])-1}）にコメント付与
- trending_sectors: 本日のセクター動向から3〜5個（上昇・下落両方含む）
- upcoming_events: 今後1〜2週間の重要イベント3〜5個
- 投資推奨は行わない。客観的な事実ベースで記述
- JSON形式のみ出力。```json などのマークダウン記法不要
"""

    result, provider = call_llm(prompt)
    if result is None:
        return _fallback_analysis(data)

    try:
        result = result.strip()
        if result.startswith("```"):
            lines = result.split("\n")
            result = "\n".join(lines[1:-1])
        start = result.find("{")
        end   = result.rfind("}") + 1
        if start >= 0 and end > start:
            result = result[start:end]
        analysis = json.loads(result)
        analysis["_provider"] = provider
        return analysis
    except json.JSONDecodeError as e:
        print(f"[WARN] JSON解析失敗: {e}")
        return _fallback_analysis(data)


def _fallback_analysis(data):
    return {
        "market_sentiment": {"score": 50, "label": "不明", "summary": "AI分析は現在利用できません。"},
        "themes": [{"title": t, "description": "データ取得中...", "sentiment": "neutral"}
                   for t in data["config"].get("fixed_themes", [])],
        "fang_highlights": [],
        "theme_explanations": {
            cat: {"today": "AI分析サービスに接続できませんでした。", "what_is": ""}
            for cat in ["commodities", "crypto", "emerging", "bonds", "forex"]
        },
        "nisa_commentary": "AI分析サービスに接続できませんでした。",
        "trending_sectors": [],
        "daily_learning": {"term": "—", "explanation": "AI分析サービス復旧後に生成されます。"},
        "future_outlook": [],
        "news_comments": [],
        "upcoming_events": [],
        "watchlist_comments": [],
        "_provider": "fallback",
    }
