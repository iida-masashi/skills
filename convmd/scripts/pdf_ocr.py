#!/usr/bin/env python
"""PDF の指定ページを画像化して Gemini で OCR し、ページごとに Markdown を保存する。

文字層のない（スキャン）PDF や、文字化けして抽出できない PDF（官報・関税表など）向け。
通常の PDF は `convmd` の URL/ファイル取込を先に試すこと。

使い方（convMD リポジトリの uv 環境で実行する。pymupdf と google-genai が必要）:
    cd C:/Users/iidam/gemini/convMD
    uv run python -X utf8 C:/Users/iidam/claude-gemini-skills/convmd/scripts/pdf_ocr.py \
        <PDF> --pages 76-84 --out-dir <出力先> --prompt-file <プロンプト.txt>

- --pages は `5`、`1-3`、`1,4,7-9` の形式（1始まり）。
- 出力は `<out-dir>/<PDF名>_p<ページ>.md`。同じ入力（PDF・ページ・倍率・モデル・プロンプト）は
  キャッシュ（既定 `<out-dir>/.ocr_cache`）を再利用する。
- --prompt を省略すると汎用の「原文どおりに書き起こす」プロンプトを使う。表を含む場合は
  列名・値の写し方を --prompt-file に書くと精度が上がる。
- 出力は OCR 結果であり原典ではない。数値は原本と突き合わせてから根拠に使う（確度は ⚠️ 扱い）。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# convMD の src を import できるようにする（環境変数で上書き可）
CONVMD_SRC = Path(os.environ.get("CONVMD_SRC", r"C:\Users\iidam\gemini\convMD\src"))
if CONVMD_SRC.exists() and str(CONVMD_SRC) not in sys.path:
    sys.path.insert(0, str(CONVMD_SRC))

DEFAULT_MODEL = "gemini-3.1-pro-preview"
DEFAULT_PROMPT = (
    "OCR transcription of ONE page of a scanned document. Transcribe VERBATIM into Markdown, "
    "keeping the original language and reading order. Render tables as Markdown tables with one "
    "output row per source row. Copy numbers exactly. If a character or cell is illegible write "
    "[illegible]. Do not translate, summarize, invent or complete. Output ONLY the transcription."
)


def parse_pages(spec: str, n_pages: int) -> list[int]:
    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            pages.extend(range(int(a), int(b) + 1))
        else:
            pages.append(int(part))
    bad = [p for p in pages if p < 1 or p > n_pages]
    if bad:
        raise SystemExit(f"ページ範囲外: {bad}（PDF は {n_pages} ページ）")
    return sorted(set(pages))


def render(pdf: Path, pno: int, zoom: float) -> bytes:
    import pymupdf

    with pymupdf.open(pdf) as d:
        pix = d[pno - 1].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csGRAY)
        return pix.tobytes("png")


def ocr_page(pdf: Path, pno: int, prompt: str, zoom: float, model: str, cache_dir: Path, retries: int = 3) -> str:
    from google.genai import types
    from convmd.core.gemini import get_client, strip_code_fence

    key = hashlib.sha1(f"{pdf.stat().st_size}|{pno}|{zoom}|{model}|{prompt}".encode("utf-8")).hexdigest()[:16]
    cache = cache_dir / f"{pdf.stem}_p{pno}_{key}.txt"
    if cache.exists():
        return cache.read_text(encoding="utf-8")

    client = get_client()
    if client is None:
        raise SystemExit("API キーが未設定（GEMINI_API_KEY または GOOGLE_API_KEY）")
    part = types.Part.from_bytes(data=render(pdf, pno, zoom), mime_type="image/png")
    cfg = types.GenerateContentConfig(max_output_tokens=32768, http_options=types.HttpOptions(timeout=300_000))
    last: Exception | None = None
    for _ in range(retries):
        try:
            r = client.models.generate_content(model=model, contents=[prompt, part], config=cfg)
            text = strip_code_fence(r.text or "")
            if text.strip():
                cache_dir.mkdir(parents=True, exist_ok=True)
                cache.write_text(text, encoding="utf-8")
                return text
        except Exception as e:  # noqa: BLE001 - 再試行後に失敗として報告する
            last = e
    return f"[OCR FAILED: {last}]"


def main() -> None:
    ap = argparse.ArgumentParser(description="PDF の指定ページを Gemini で OCR して Markdown 保存")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--pages", required=True, help="例: 5 / 1-3 / 1,4,7-9（1始まり）")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--prompt", help="OCR プロンプト（省略時は汎用の書き起こし）")
    ap.add_argument("--prompt-file", type=Path, help="プロンプトをファイルから読む（--prompt より優先）")
    ap.add_argument("--zoom", type=float, default=2.5, help="画像化の倍率（既定 2.5。小さい文字は 3 以上）")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--cache-dir", type=Path, help="既定は <out-dir>/.ocr_cache")
    args = ap.parse_args()

    import pymupdf

    with pymupdf.open(args.pdf) as d:
        n_pages = len(d)
    pages = parse_pages(args.pages, n_pages)
    prompt = args.prompt_file.read_text(encoding="utf-8") if args.prompt_file else (args.prompt or DEFAULT_PROMPT)
    cache_dir = args.cache_dir or (args.out_dir / ".ocr_cache")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    with ThreadPoolExecutor(args.workers) as ex:
        results = list(ex.map(lambda p: ocr_page(args.pdf, p, prompt, args.zoom, args.model, cache_dir), pages))

    failed = []
    for p, text in zip(pages, results):
        out = args.out_dir / f"{args.pdf.stem}_p{p}.md"
        out.write_text(text, encoding="utf-8")
        if text.startswith("[OCR FAILED"):
            failed.append(p)
        print(f"p{p}: {len(text)} chars -> {out.name}")
    if failed:
        print(f"失敗ページ: {failed}（再実行すれば成功分はキャッシュから再利用）", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
