# 徹底監査レポート — python-safe-coding

日付: 2026-06-04
手法: マルチレンズ監査（correctness / design / test-gaps / security の4観点）＋各発見を独立エージェントで敵対的検証（refute 前提）
規模: 24エージェント / 全発見を実コードで再検証
結果: **確認 14件 / 却下 6件**

> 注: 検証エージェントが原発見を補正した箇所（重大度の引き下げ・誤りの除外）は、補正後の内容を採用している。
> 例: `psc replace` の UnicodeDecodeError は ValueError のサブクラスで既にcatch済み → 誤り。OSError の穴のみが本物。

---

## 確認済み発見（14件）

### Critical（1件）

#### C-1. diff-aware モードがサブディレクトリ指定時に変更ファイルを全脱落させ、False PASS になる
- **箇所**: `src/python_safe_coding/cli.py:57-80`（`_changed_python_files`）
- **問題**: `git diff --name-only` はリポジトリトップからの相対パスを出力するが、`root = Path(args.target).resolve()` に結合している。`--target` がサブディレクトリ（例: `python-safe-coding`）の場合、`root/トップ相対パス` が二重パス（`.../python-safe-coding/python-safe-coding/...`）になり `.exists()` が False。結果、**変更ファイルが全て脱落** → `_resolve_gate_targets` が None を返し Ruff+AST を丸ごとスキップ、または `_cmd_ast` が EXIT_OK。未チェックの変更コードを黙って通す。
- **再現確認済**: このモノレポ（git トップ = `skills/`、スキルはサブディレクトリ）でまさに発生。CI の `--target .`（独立チェックアウト）では root==トップなので無害だが、ローカル開発のレイアウトで壊れる。
- **修正案**: `git diff` に `--relative` を付けて cwd 相対で出力させる（最小）。または `git rev-parse --show-toplevel` でトップを取得して結合。併せて `-c core.quotepath=false` で cp932 ファイル名脱落も防止。

### Important（5件）

#### I-1. Polars-First ルールが pandas サブモジュール import を見逃す（charter バイパス）
- **箇所**: `ast_checker.py:59-70`
- **問題**: 完全一致比較のため `import pandas.testing as tm`（alias.name=`pandas.testing`）や `from pandas.api.types import ...`（node.module=`pandas.api.types`）が `== "pandas"` に一致せず通過。標準形 `import pandas as pd` / `from pandas import X` は捕捉できるが、サブモジュール形が漏れる。
- **修正案**: `alias.name == "pandas" or alias.name.startswith("pandas.")` / `(node.module or "").startswith("pandas.")`（None ガード必須）。
- **⚠️ 注意**: AST ルール変更につき **`_CHECKER_VERSION` のバンプ必須**（さもないと `--cache-dir` が変更前の clean 判定を再利用）。

#### I-2. ツール不在・内部エラーが EXIT_VIOLATION(1) で報告される（contract 違反）
- **箇所**: `gate.py:70` / `cli.py:_cmd_gate`
- **問題**: 終了コード契約は 1=ポリシー違反 / 2=内部エラー。だが `uv`/`ruff`/`mypy`/`pytest` が不在・クラッシュしても全て exit 1 になり、「コードが悪い」と「ツールが壊れている」を区別できない。`StepResult.status` は `Passed|Failed|Error` の3値型なのに、終了コードでその区別を捨てている。
- **修正案**: ツール起動失敗を EXIT_INTERNAL(2) として浮上。run_command を3値化、_cmd_gate で error 時に EXIT_INTERNAL を返す。
- **⚠️ 要判断**: ツール不在は 2(内部) か 3(config/環境) か曖昧（CLAUDE.md は extras 不足を 3 と定義）。I-3 と合わせて設計すべき。

#### I-3. 文書化された exit code 2（内部エラー）が到達不能。未捕捉例外が生のトレースバックになる
- **箇所**: `cli.py:516-520`（`main()`）
- **問題**: `main()` にトップレベル try/except がなく、`EXIT_INTERNAL` を返すのは `_cmd_heal` の ImportError 分岐のみ。各 `_cmd_*` 内の想定外例外は `args.func(args)` を抜けて生トレースバックでクラッシュ。CI のアラートルーティング契約（1/2/3 の振り分け）が破綻。具体例: `psc heal --file <存在しないファイル>` で FileNotFoundError がそのまま貫通。
- **修正案**: `main()` で dispatch を try/except 包囲。`except SystemExit: raise` / `except Exception: logger.exception(...); sys.exit(EXIT_INTERNAL)`。

#### I-4. `psc replace` の書き込み時 OSError が未捕捉
- **箇所**: `cli.py:303-309`
- **問題**: `_cmd_replace` は `(FileNotFoundError, ValueError, SyntaxError)` のみ catch。`write_text()` の PermissionError/OSError（Windows の読み取り専用・ロックで頻出）が未捕捉 → 生トレースバック。
- **再現確認済**: 読み取り専用ファイルで PermissionError が貫通。
- **修正案**: except タプルに `OSError` を追加。
- **補正**: 原発見の「UnicodeDecodeError も未捕捉」は**誤り**（ValueError サブクラスで既に catch 済み）。報告・修正対象から除外。

#### I-5. `read_baseline` が非オブジェクト JSON で AttributeError クラッシュ（潜在バグ・未テスト）
- **箇所**: `baseline.py:136-137`
- **問題**: `data = json.loads(...)` 直後に `data.get("version")`。ファイルが `[]` や `"x"` 等の有効だが非オブジェクト JSON だと `.get` が AttributeError。呼び出し側は `(ValueError, OSError)` しか catch せず貫通。baseline は手編集・コミット対象の成果物なので、外部書き換え・切り詰めは起こりうる。
- **修正案**: `if not isinstance(data, dict): raise ValueError(...)` でガード（catch される型に）＋テスト追加。

### Minor（8件）

| ID | 箇所 | 問題 | 修正 |
|----|------|------|------|
| M-1 | `cli.py:389` | prepush の `compileall.compile_dir` が `.venv`/build/dist まで再帰コンパイル（AST checker の `_SKIP_PARTS` と不整合）。vendored の壊れた .py で誤失敗 | `rx=` 除外正規表現を `_SKIP_PARTS` と揃える |
| M-2 | `cli.py:324-329` | `psc heal --file` の読み込みが未捕捉。不正パスで生トレースバック | `try/except (OSError, UnicodeDecodeError) → EXIT_CONFIG` |
| M-3 | `healer.py:33` | `_FILE_RE` の文字クラスに空白なし。Windows の `C:\Program Files\...` 等のパスを途中で切る | 文字クラスに空白追加。失敗時は graceful（None で中断）なので minor |
| M-4 | `tests/test_cli.py` | `_cmd_gate` の成功/失敗パスがほぼ未テスト（None 分岐のみ）。`_step_ast` の Failed/Passed・EXIT_VIOLATION が無カバレッジ | 失敗ステップ統合テスト＋全パステスト追加 |
| M-5 | `ast_checker.py:83-84` | `except OSError` 分岐と baseline の `io-error` ルールがテストで死蔵 | ディレクトリパスを渡す等でテスト追加 |
| M-6 | `editor.py:77-78, 85-86` | new_code 不在・source パース不能の2分岐が未テスト | 2テスト追加 |
| M-7 | `cli.py:389-391, 407-409` | prepush の compile 失敗・不正 pyproject パスが未テスト。EXIT_CONFIG 経路未到達 | 2テスト追加 |
| M-8 | `baseline.py:96-97, 101-106` | `fingerprint_violation` の root外・file不在分岐が未テスト | 2テスト追加 |

---

## 却下された発見（6件）— 敵対的検証で refute

1. **[correctness] prepush の `uv lock` が encoding 欠落で cp932 クラッシュ** → `capture_output=True` のデコードエラーは reader スレッド内で発生し呼び出し側に伝播しない。`_cmd_prepush` は `returncode` のみ参照。クラッシュも誤判定もなし（cosmetic なトレースバックのみ）。encoding 欠落は規約上の軽微なクリーンアップ余地はある。
2. **[correctness] baseline fingerprint が行番号を省き、同一行の別違反が衝突** → 唯一の AST ルールは pandas import。同一内容の2行目 import は新たなポリシー違反を生まない（Ruff F811 でも検出）。内容ハッシュ identity は line-drift 耐性のための文書化済み設計判断。実害ほぼ皆無。
3. **[design] `resolve_target` が最初のトレースバックフレームを拾う** → `_FILE_RE` は `file.py:数字:` 形式（Ruff/MyPy 診断形式）を要求し、標準トレースバックには一致しない（None を返す）。前提が成立しない。失敗時は revert されるので破損もなし。
4. **[test-gaps] cache.load の format_version 不一致・非 list 分岐が未テスト** → 公開 write 経路から到達不能（format_version は常に 1 を書く）。同等の契約（不正キャッシュ→None）は既存テストでカバー済み。安全に degrade。
5. **[security] healer がエラーログ制御のパスに Gemini 出力を書き込み auto-commit（prompt injection）** → 信頼境界を越えていない。`psc heal` はローカル開発 CLI、error_log はオペレータ自身が供給。攻撃者が入力パイプラインと git を既に制御している前提で、ファイル直接編集と同等。auto-commit はデフォルト off。パス無制限は軽微な堅牢性課題ではある。
6. **[security] AST 結果キャッシュが on-disk JSON を信頼（キャッシュポイズニング）** → 権限昇格なし。cache_dir への書き込み権限を持つ者はソース・pyproject も書ける。JSON パースは安全（eval/pickle なし）。cache_dir はデフォルト off。発見自身が「現状維持で許容」と結論。

---

## 推奨対応プラン（要承認）

リスク別にグループ化し、契約変更は明示承認後に実施することを推奨:

- **Phase 1（低リスク・ガード追加）**: I-4, I-5, M-1, M-2, M-3 — 局所的な except 追加・ガード・正規表現修正。
- **Phase 2（テスト追加）**: M-4〜M-8 — カバレッジ向上。挙動変更なし。
- **Phase 3（ロジック修正）**: C-1（diff-aware）, I-1（pandas サブモジュール＋`_CHECKER_VERSION` バンプ）。
- **Phase 4（contract 変更・要判断）**: I-2, I-3 — exit code 契約に関わる。ツール不在を 2 か 3 か要決定。

全 Phase で「`psc gate` がこのスキル自身に対して green を維持」「カバレッジ ≥80%」を制約とする。

---

## 実装結果（2026-06-04 同日）

ユーザー承認: 全14件実装 / ツール不在は **exit 3（config/環境）** で統一。

| Phase | 対応 | 主な変更ファイル |
|-------|------|------------------|
| 1 | I-4, I-5, M-1, M-2 | `cli.py`(replace OSError / heal --file ガード / compileall 除外rx), `baseline.py`(非object JSONガード) |
| 3 | C-1, I-1 | `cli.py`(`git diff --relative` + `core.quotepath=false`), `ast_checker.py`(`_is_pandas`ヘルパ + `_CHECKER_VERSION` 1→2) |
| 4 | I-2, I-3 | `gate.py`(`ToolUnavailableError`, 起動失敗をraise), `cli.py`(`main()` try/except 包囲 → exit 3 / exit 2) |
| 2 | M-4〜M-8 | `test_cli.py`, `test_gate.py`, `test_ast_checker.py`, `test_baseline.py`, `test_editor.py` にテスト追加 |

### 検証
- **`psc gate --target .` → EXIT 0**（Ruff / MyPy strict / AST / pytest 全通過）
- **カバレッジ 93%**（floor 80%）
- **`psc prepush` → EXIT 0**
- **C-1 実機再現確認**: スキルサブディレクトリから `_changed_python_files('main', root)` を呼び、返却9ファイルが全て `.exists()`=True。旧方式（トップ相対をサブディレクトリに結合）では23件中0件しか存在せず全脱落 → 修正が決定的に有効。

### 設計上の判断（記録）
- **I-2 のスコープ**: 検出可能なのは launcher（`uv`）不在のみ。sub-tool（ruff/mypy/pytest）不在は `uv run` の非ゼロ終了として現れ、本物のポリシー違反と区別不能なため、意図的に exit 1 のまま（stderr パースはしない）。
- **I-5 の `# noqa: TRY004`**: Ruff は型チェックに TypeError を推奨するが、両呼び出し側が `except (ValueError, OSError)` で捕捉するため ValueError でなければならない（TypeError だと未捕捉で escape）。理由をコメントで明記。
- **M-3 は見送り（revert）**: `_FILE_RE` の文字クラスに空白を加える素朴な修正は、最頻出の Ruff `--> <path>` 形式で回帰する（`re.search` が先頭の空白や直前の語まで取り込み、`Path(...).exists()` が False になる）。1つの正規表現で「先頭の語＋空白に続くパス」と「空白入り絶対パス」を両立できないため、graceful（マッチ失敗時は healing 中断・破損なし）かつ既存の軽微な制約である M-3 は据え置く。コードに NOTE コメントを残置。
- **却下6件は未着手**（敵対的検証で refute 済み）。
