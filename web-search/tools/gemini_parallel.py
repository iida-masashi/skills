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
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from gemini_webfetch import resolve_redirect  # noqa: E402

REDIRECT_RE = re.compile(r"https://vertexaisearch\.cloud\.google\.com/grounding-api-redirect/[\w\-]+")

GUARD = """あなたはWeb調査エージェントです。Google検索とWebページ取得ツールを使って次の調査を行ってください。
規律:
- 検索結果・取得ページに書かれている事実だけを書く。推測・補完・事前知識での穴埋めは禁止。見つからない項目は「記載なし」と書く。
- 各事実の直後に出典の完全なURL（ドメインだけは不可）を付ける。
- 前置き・経緯・締めの挨拶は書かない。結論を先頭に、{max_lines}行以内の箇条書きで答える。
- 今日の日付は{today}。「最新」「現在」はこの日付基準で判断する。

調査内容:
{query}
"""


def run_one(idx: int, query: str, out_dir: Path, args) -> dict:
    exe = shutil.which("gemini")
    prompt = GUARD.format(max_lines=args.max_lines, today=date.today().isoformat(), query=query)
    cmd = [exe, "--approval-mode", "plan", "-p", "上記の指示に従って調査し回答してください。"]
    if args.model:
        cmd += ["-m", args.model]
    out_path = out_dir / f"q{idx:02d}.md"
    err_path = out_dir / f"q{idx:02d}.stderr.log"
    t0 = time.time()
    try:
        # プロンプトはstdin経由（Windowsの.cmdシム経由で日本語・記号を引数に渡すと壊れるため）
        p = subprocess.run(cmd, input=prompt.encode("utf-8"), capture_output=True,
                           timeout=args.timeout, cwd=out_dir)
        text, ec = p.stdout.decode("utf-8", "replace").strip(), p.returncode
        err_path.write_bytes(p.stderr)
    except subprocess.TimeoutExpired:
        text, ec = "", "timeout"
    # 長いgrounding転送URLを実URLへ置換（Claude側の流入量削減＋出典として記録可能にする）
    redirects = set(REDIRECT_RE.findall(text))
    if redirects:
        with ThreadPoolExecutor(max_workers=8) as ex:
            resolved = dict(zip(redirects, ex.map(resolve_redirect, redirects)))
        for u, real in resolved.items():
            text = text.replace(u, real or "(出典URL解決失敗)")
    out_path.write_text(f"# {query}\n\n{text}\n", encoding="utf-8")
    return {"idx": idx, "query": query, "ec": ec, "text": text,
            "path": out_path, "sec": round(time.time() - t0)}


def main() -> None:
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
        queries += [l.strip() for l in Path(args.file).read_text(encoding="utf-8").splitlines()
                    if l.strip() and not l.strip().startswith("#")]
    if not queries:
        ap.error("調査内容を指定してください")
    if not shutil.which("gemini"):
        sys.exit("ERROR: gemini CLI が見つかりません（npm i -g @google/gemini-cli）")

    out_dir = Path(args.out_dir or f"gemini_research_{time.strftime('%Y%m%d_%H%M%S')}").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        results = list(ex.map(lambda iq: run_one(iq[0], iq[1], out_dir, args), enumerate(queries, 1)))

    sys.stdout.reconfigure(encoding="utf-8")
    failed = 0
    for r in results:
        ok = r["ec"] == 0 and r["text"]
        failed += not ok
        print(f"[q{r['idx']:02d}] {'OK' if ok else 'FAIL(' + str(r['ec']) + ')'} {r['sec']}s {r['path']}")
        if args.preview and r["text"]:
            body = r["text"][:args.preview]
            print("  " + body.replace("\n", "\n  ") + (" …" if len(r["text"]) > args.preview else ""))
    print(f"done: {len(results) - failed}/{len(results)} ok, out_dir={out_dir}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
