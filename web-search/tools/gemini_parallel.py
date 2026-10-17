"""複数のWeb調査をGemini CLI（headless）で並列実行し、結果をファイルに書き出す。

Claude側サブエージェントの代わりにGemini CLIエージェントへ検索・ページ取得・要約を任せ、
Claude側コンテキストには各調査の結論（先頭N文字）とファイルパスだけを流す。

使い方:
  python tools/gemini_parallel.py "調査1" "調査2" ...
  python tools/gemini_parallel.py -f queries.txt      # 1行1調査（空行・#行は無視）
"""
import argparse
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Final

sys.path.insert(0, str(Path(__file__).parent))
from gemini_webfetch import configure_utf8_stdio, resolve_redirect

_JST: Final[timezone] = timezone(timedelta(hours=9))
REDIRECT_RE: Final[re.Pattern[str]] = re.compile(
    r"https://vertexaisearch\.cloud\.google\.com/grounding-api-redirect/[\w\-]+"
)

GUARD: Final[str] = """あなたはWeb調査エージェントです。Google検索とWebページ取得ツールを使って次の調査を行ってください。
規律:
- 検索結果・取得ページに書かれている事実だけを書く。推測・補完・事前知識での穴埋めは禁止。見つからない項目は「記載なし」と書く。
- 各事実の直後に出典の完全なURL（ドメインだけは不可）を付ける。
- 前置き・経緯・締めの挨拶は書かない。結論を先頭に、{max_lines}行以内の箇条書きで答える。
- 今日の日付は{today}。「最新」「現在」はこの日付基準で判断する。

調査内容:
{query}
"""


def run_one(idx: int, query: str, out_dir: Path, args: argparse.Namespace) -> dict:
    exe = shutil.which("gemini")
    if not exe:
        return {
            "idx": idx,
            "query": query,
            "ec": "no_cli",
            "text": "",
            "path": out_dir / f"q{idx:02d}.md",
            "sec": 0,
        }
    today_str = datetime.now(timezone.utc).astimezone(_JST).date().isoformat()  # noqa: UP017
    prompt = GUARD.format(max_lines=args.max_lines, today=today_str, query=query)
    # Windowsの.cmdシム経由でマルチバイト文字を引数に渡すと文字化けするため、-pにはASCIIのみを渡し本文はstdinで渡す
    cmd = [exe, "--approval-mode", "plan", "-p", "Follow the instructions provided via stdin."]
    if args.model:
        cmd += ["-m", args.model]
    out_path = out_dir / f"q{idx:02d}.md"
    err_path = out_dir / f"q{idx:02d}.stderr.log"
    t0 = time.time()
    try:
        p = subprocess.run(
            cmd,
            input=prompt.encode("utf-8"),
            capture_output=True,
            timeout=args.timeout,
            cwd=out_dir,
            check=False,
        )
        text, ec = p.stdout.decode("utf-8", "replace").strip(), p.returncode
        err_path.write_bytes(p.stderr)
    except subprocess.TimeoutExpired:
        text, ec = "", "timeout"
    # 長いgrounding転送URLを実URLへ置換（Claude側の流入量削減＋出典として記録可能にする）
    redirects = set(REDIRECT_RE.findall(text))
    if redirects:
        with ThreadPoolExecutor(max_workers=min(8, len(redirects))) as ex:
            resolved = dict(zip(redirects, ex.map(resolve_redirect, redirects)))
        for u, real in resolved.items():
            text = text.replace(u, real or "(出典URL解決失敗)")
    out_path.write_text(f"# {query}\n\n{text}\n", encoding="utf-8")
    return {
        "idx": idx,
        "query": query,
        "ec": ec,
        "text": text,
        "path": out_path,
        "sec": round(time.time() - t0),
    }


def main() -> None:
    configure_utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("queries", nargs="*", help="調査内容（複数可）")
    ap.add_argument("-f", "--file", help="1行1調査のテキストファイル")
    ap.add_argument("-o", "--out-dir", help="出力先（既定: カレント下 gemini_research_<時刻>）")
    ap.add_argument("-j", "--jobs", type=int, default=4, help="並列数（既定4）")
    ap.add_argument("-m", "--model", help="Geminiモデル（既定: Gemini CLIの既定）")
    ap.add_argument("--max-lines", type=int, default=10, help="各回答の最大行数の指示（既定10）")
    ap.add_argument("--preview", type=int, default=400, help="標準出力に出す各回答の先頭文字数。0で非表示（既定400）")
    ap.add_argument("--timeout", type=int, default=300, help="1調査あたりのタイムアウト秒（既定300）")
    args = ap.parse_args()

    queries = list(args.queries)
    if args.file:
        queries += [
            line.strip()
            for line in Path(args.file).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    if not queries:
        ap.error("調査内容を指定してください")
    if not shutil.which("gemini"):
        sys.exit("ERROR: gemini CLI が見つかりません（npm i -g @google/gemini-cli）")

    ts = datetime.now(timezone.utc).astimezone(_JST).strftime("%Y%m%d_%H%M%S")  # noqa: UP017
    out_dir = Path(args.out_dir or f"gemini_research_{ts}").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        results = list(ex.map(lambda iq: run_one(iq[0], iq[1], out_dir, args), enumerate(queries, 1)))

    failed = 0
    for r in results:
        ok = r["ec"] == 0 and bool(r["text"])
        failed += not ok
        print(f"[q{r['idx']:02d}] {'OK' if ok else 'FAIL(' + str(r['ec']) + ')'} {r['sec']}s {r['path']}")
        if args.preview and r["text"]:
            body = r["text"][:args.preview]
            print("  " + body.replace("\n", "\n  ") + (" ..." if len(r["text"]) > args.preview else ""))
    print(f"done: {len(results) - failed}/{len(results)} ok, out_dir={out_dir}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
