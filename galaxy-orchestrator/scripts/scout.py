import os

from dotenv import load_dotenv
from google import genai

load_dotenv()

def get_best_available_models() -> dict[str, str] | None:
    """現在利用可能なモデルの中から、各カテゴリの最新のものを返す"""
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    client = genai.Client(api_key=api_key, vertexai=False)

    try:
        models = client.models.list()

        # モデルを分類するためのキーワード
        # Proは3.1系がThinking対応の最新ティア。Flash/Flash-Liteは3.6/3.5系が最新ティア
        # (Proと Flash 系は別トラックでバージョンが進行するため、ティアごとに優先探索キーワードを分ける)
        REASONING_MODELS = ["3.1-pro", "3-pro", "pro-preview"]
        SPEED_MODELS = ["3.6-flash", "3.5-flash", "3.1-flash", "2.0-flash", "flash-latest"]
        LITE_MODELS = ["3.5-flash-lite", "3.1-flash-lite", "2.0-flash-lite", "flash-lite"]

        best_models = {
            "Specialist": "gemini-3.1-pro-preview",
            "Primary": "gemini-3.6-flash",
            "Utility": "gemini-3.5-flash-lite"
        }

        found = {"Specialist": False, "Primary": False, "Utility": False}

        # 各ティアの最新シリーズを最優先で探す (Proは3.1, Flashは3.6, Flash-Liteは3.5)
        for m in models:
            name = m.name.replace("models/", "")
            name_lower = name.lower()

            if not found["Specialist"] and "3.1-pro" in name_lower:
                best_models["Specialist"] = name
                found["Specialist"] = True
            elif not found["Utility"] and "3.5-flash-lite" in name_lower:
                best_models["Utility"] = name
                found["Utility"] = True
            elif not found["Primary"] and "3.6-flash" in name_lower and "lite" not in name_lower:
                best_models["Primary"] = name
                found["Primary"] = True

        # 最新シリーズが見つからなかった場合の次善策 (優先度降順のキーワードリストを順に探索)
        for m in models:
            name = m.name.replace("models/", "")
            name_lower = name.lower()
            if not found["Specialist"] and any(k in name_lower for k in REASONING_MODELS):
                best_models["Specialist"] = name
                found["Specialist"] = True
            elif not found["Utility"] and any(k in name_lower for k in LITE_MODELS):
                best_models["Utility"] = name
                found["Utility"] = True
            elif not found["Primary"] and any(k in name_lower for k in SPEED_MODELS):
                best_models["Primary"] = name
                found["Primary"] = True

        return best_models

    except Exception:
        return None

def scout_models(keyword: str | None = None) -> str:
    """利用可能なモデルを偵察し、最適な戦力を提案する"""
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "⚠️ Error: API Key not found in environment variables."

    client = genai.Client(api_key=api_key, vertexai=False)

    try:
        models = client.models.list()

        # モデルを分類するためのキーワード
        REASONING_MODELS = ["3.1-pro", "3.1-reasoning", "pro-preview"]
        SPEED_MODELS = ["3.6-flash", "3.5-flash", "2.0-flash", "3.1-flash", "flash-latest"]
        LITE_MODELS = ["lite-preview", "flash-lite"]

        report = "## 📡 Gemini Model Scout Report\n\n"
        report += "| Model Category | Name | Status | Usage |\n"
        report += "| :--- | :--- | :--- | :--- |\n"

        found_count = 0
        for m in models:
            name = m.name.replace("models/", "")
            display = m.display_name

            # フィルタリング
            if keyword and keyword.lower() not in name.lower() and keyword.lower() not in display.lower():
                continue

            # 分類
            category = "⚪ Other"
            usage = "General use"

            if any(k in name.lower() for k in REASONING_MODELS):
                category = "🏆 **Specialist**"
                usage = "PSI analysis, Algorithms, Math"
            elif any(k in name.lower() for k in LITE_MODELS):
                category = "⚡ **Utility**"
                usage = "Data cleaning, Log parsing"
            elif any(k in name.lower() for k in SPEED_MODELS):
                category = "🚀 **Primary**"
                usage = "Daily coding, Research"

            report += f"| {category} | `{name}` | ✅ Available | {usage} |\n"
            found_count += 1

        if found_count == 0:
            return f"❌ No models found matching keyword: '{keyword}'"

        report += "\n\n### 💡 SCM Consultant's Recommendation\n"
        report += "- **For Depth**: Use `gemini-3.1-pro-preview` for complex PSI/S&OP logic.\n"
        report += "- **For Speed**: Use `gemini-3.6-flash` for daily coding and research tasks.\n"
        report += "- **For Lite tasks**: Use `gemini-3.5-flash-lite` for quick data transformations.\n"

        return report

    except Exception as e:
        return f"⚠️ Error during scouting: {e}"

if __name__ == "__main__":
    import sys
    search_keyword = sys.argv[1] if len(sys.argv) > 1 else None
    print(scout_models(search_keyword))
