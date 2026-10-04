import os
import re

import httpx
from dotenv import load_dotenv
from google import genai

load_dotenv()

# --- Gemini ---
# API未取得時のデフォルト (2026-10-04 に models.list で実在確認)
GEMINI_DEFAULTS = {
    "Specialist": "gemini-3.1-pro-preview",
    "Primary": "gemini-3.8-flash",
    "Utility": "gemini-3.5-flash-lite",
}

# "gemini-<版>-<pro|flash|flash-lite>[-preview]" に完全一致するものだけをティア候補にする。
# 末尾まで一致を要求するので "gemini-3.8-flash-tts" や "gemini-3.1-pro-preview-customtools" のような
# テキスト生成用でない派生モデルは候補にならない
_GEMINI_VERSION_RE = re.compile(r"^gemini-(\d+)(?:\.(\d+))?-(pro|flash-lite|flash)(?:-(preview))?$")


def _gemini_tier_candidates(names: list[str]) -> dict[str, list[tuple[tuple[int, int, int], str]]]:
    """モデル名を (版数, 名前) の候補としてティアごとに集める。
    版数は (メジャー, マイナー, GA=1/preview=0) で比較し、同じ版ならGAを優先する。
    "gemini-flash-latest" のようなエイリアスは版数を持たないので候補にしない"""
    tier_of = {"pro": "Specialist", "flash": "Primary", "flash-lite": "Utility"}
    candidates: dict[str, list[tuple[tuple[int, int, int], str]]] = {t: [] for t in tier_of.values()}
    for name in names:
        m = _GEMINI_VERSION_RE.match(name)
        if not m:
            continue
        major, minor, family, preview = m.groups()
        version = (int(major), int(minor or 0), 0 if preview else 1)
        candidates[tier_of[family]].append((version, name))
    return candidates


def get_best_available_models() -> dict[str, str] | None:
    """利用可能なGeminiモデルから、各ティアで最も新しい版を返す"""
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    client = genai.Client(api_key=api_key, vertexai=False)

    try:
        names = [m.name.replace("models/", "") for m in client.models.list()]
    except Exception:
        return None

    best_models = dict(GEMINI_DEFAULTS)
    for tier, found in _gemini_tier_candidates(names).items():
        if found:
            best_models[tier] = max(found)[1]
    return best_models


def scout_models(keyword: str | None = None) -> str:
    """利用可能なGeminiモデルを偵察し、ティア分類したレポートを返す"""
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "⚠️ Error: API Key not found in environment variables."

    client = genai.Client(api_key=api_key, vertexai=False)

    try:
        models = list(client.models.list())

        names = [m.name.replace("models/", "") for m in models]
        best = dict(GEMINI_DEFAULTS)
        tier_of_name: dict[str, str] = {}
        for tier, found in _gemini_tier_candidates(names).items():
            for _, name in found:
                tier_of_name[name] = tier
            if found:
                best[tier] = max(found)[1]

        labels = {
            "Specialist": ("🏆 **Specialist**", "PSI analysis, Algorithms, Math"),
            "Primary": ("🚀 **Primary**", "Daily coding, Research"),
            "Utility": ("⚡ **Utility**", "Data cleaning, Log parsing"),
        }

        report = "## 📡 Gemini Model Scout Report\n\n"
        report += "| Model Category | Name | Status | Usage |\n"
        report += "| :--- | :--- | :--- | :--- |\n"

        found_count = 0
        for m in models:
            name = m.name.replace("models/", "")
            display = m.display_name or ""

            if keyword and keyword.lower() not in name.lower() and keyword.lower() not in display.lower():
                continue

            category, usage = labels.get(tier_of_name.get(name, ""), ("⚪ Other", "General use"))
            report += f"| {category} | `{name}` | ✅ Available | {usage} |\n"
            found_count += 1

        if found_count == 0:
            return f"❌ No models found matching keyword: '{keyword}'"

        if not keyword:
            report += "\n\n### 💡 Selected per tier\n"
            report += f"- **Specialist**: `{best['Specialist']}`\n"
            report += f"- **Primary**: `{best['Primary']}`\n"
            report += f"- **Utility**: `{best['Utility']}`\n"

        return report

    except Exception as e:
        return f"⚠️ Error during scouting: {e}"


# --- Grok (xAI) ---
XAI_BASE_URL = "https://api.x.ai/v1"

# API未取得時のデフォルト (2026-10-04 に /v1/language-models で実在確認)
GROK_DEFAULTS = {
    "Specialist": "grok-4.7",
    "Primary": "grok-4.3",
    "Utility": "grok-4.20-0309-non-reasoning",
}

# 汎用チャットに向かない派生モデル (並列エージェント版・コーディング特化版・画像/動画生成)
GROK_EXCLUDE_MARKERS = ("multi-agent", "build", "code", "imagine")


def fetch_grok_models(api_key: str) -> list[dict]:
    """xAI の /v1/language-models を取得する。各要素は id・created・料金フィールドを持つ。
    料金の単位は「100万トークンあたりUSD × 10000」(例: 20000 = $2.00/1M)"""
    response = httpx.get(
        f"{XAI_BASE_URL}/language-models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("models", [])


def grok_pricing(models: list[dict]) -> dict[str, dict[str, float]]:
    """/v1/language-models の結果から {モデルID/エイリアス: {"in": $, "out": $}} (1Mトークンあたり) を作る"""
    pricing: dict[str, dict[str, float]] = {}
    for m in models:
        if "prompt_text_token_price" not in m or "completion_text_token_price" not in m:
            continue
        rate = {"in": m["prompt_text_token_price"] / 10000, "out": m["completion_text_token_price"] / 10000}
        for model_id in [m["id"], *m.get("aliases", [])]:
            pricing[model_id] = rate
    return pricing


def select_grok_tiers(models: list[dict]) -> dict[str, str]:
    """xAIのモデル一覧からティアを選ぶ。
    xAIの版番号は "4.20" の後に "4.3" が出るなど数値順と発売順が一致しないため、
    新しさは版番号でなく created (登録時刻) で判定する。
    - Specialist: 最新の汎用モデル
    - Primary: 出力単価が最も安い汎用モデル (同額なら新しい方)
    - Utility: 最新の non-reasoning モデル (無ければPrimaryと同じ)"""
    general = [
        m for m in models
        if m.get("id", "").startswith("grok-")
        and not any(marker in m["id"] for marker in GROK_EXCLUDE_MARKERS)
        and "completion_text_token_price" in m
    ]
    reasoning = [m for m in general if "non-reasoning" not in m["id"]]
    non_reasoning = [m for m in general if "non-reasoning" in m["id"]]

    tiers = dict(GROK_DEFAULTS)
    if reasoning:
        tiers["Specialist"] = max(reasoning, key=lambda m: m.get("created", 0))["id"]
        tiers["Primary"] = min(reasoning, key=lambda m: (m["completion_text_token_price"], -m.get("created", 0)))["id"]
        tiers["Utility"] = tiers["Primary"]
    if non_reasoning:
        tiers["Utility"] = max(non_reasoning, key=lambda m: m.get("created", 0))["id"]
    return tiers


def get_best_grok_models() -> tuple[dict[str, str], dict[str, dict[str, float]]] | None:
    """利用可能なGrokモデルのティアと料金表を返す。
    キー未設定ならNone、一覧取得に失敗したらデフォルトのティアと空の料金表を返す"""
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        return None
    try:
        models = fetch_grok_models(api_key)
    except Exception:
        return dict(GROK_DEFAULTS), {}
    return select_grok_tiers(models), grok_pricing(models)


def scout_grok_models(keyword: str | None = None) -> str:
    """利用可能なGrokモデルを偵察し、料金付きのレポートを返す"""
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        return "⚠️ Error: XAI_API_KEY not found in environment variables."
    try:
        models = fetch_grok_models(api_key)
    except Exception as e:
        return f"⚠️ Error during Grok scouting: {e}"

    tiers = select_grok_tiers(models)
    pricing = grok_pricing(models)
    tier_of = {v: k for k, v in tiers.items()}

    report = "## 📡 Grok Model Scout Report\n\n"
    report += "| Model Category | Name | In $/1M | Out $/1M |\n"
    report += "| :--- | :--- | ---: | ---: |\n"
    found_count = 0
    for m in models:
        model_id = m.get("id", "")
        if keyword and keyword.lower() not in model_id.lower():
            continue
        rate = pricing.get(model_id, {"in": 0.0, "out": 0.0})
        category = f"**{tier_of[model_id]}**" if model_id in tier_of else "⚪ Other"
        report += f"| {category} | `{model_id}` | {rate['in']:.2f} | {rate['out']:.2f} |\n"
        found_count += 1

    if found_count == 0:
        return f"❌ No Grok models found matching keyword: '{keyword}'"
    return report


if __name__ == "__main__":
    import sys
    search_keyword = sys.argv[1] if len(sys.argv) > 1 else None
    print(scout_models(search_keyword))
    if os.getenv("XAI_API_KEY"):
        print()
        print(scout_grok_models(search_keyword))
