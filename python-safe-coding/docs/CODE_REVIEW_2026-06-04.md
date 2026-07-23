# コード品質レビュー — python-safe-coding

日付: 2026-06-04 / 範囲: `src/` + `tests/`（~1500行、全モジュール精読）
評価基準: このスキル自身が掲げる品質バー（Ruff + AST + MyPy strict + 80%カバレッジ + SKILL.md の10原則）

---

## 総評

コア設計は堅実。argvリスト（`shell=True`不使用）、AST置換でデコレータをスパンに含める、
mtime+sizeキャッシュ、行ハッシュベースのbaseline、healerの遅延import — いずれも
「なぜそうしたか」がコメント/ADRで裏取りされており、senior水準。

**ただし1点、見過ごせない発見がある。**

---

## 🔴 Critical — Guardian が自分のゲートに落ちている（SKILL.md 原則#10 違反）

`uv run psc gate --target .` を実行すると **MyPy strict で11件エラー、exit 1**。
「The skill must pass its own gate」を掲げるツールがそれを満たしていない。

根本原因は **2つ**（11件をバラバラに直すのではなく、原因単位で対処する）:

### 原因A: テストの型注釈について Ruff と MyPy が食い違っている
- `pyproject.toml` の `[tool.ruff.lint.per-file-ignores]` で `tests/**.py = [..., "ANN", ...]`
  と注釈を免除している。
- 一方 `[tool.mypy] strict = true`（= `disallow_untyped_defs`）は **全ファイル**に注釈を要求。
- 結果、`tests/test_cache.py:81` の `def test_store_swallows_io_errors(tmp_path, monkeypatch)`
  だけ `monkeypatch` に注釈が無く `no-untyped-def`。他のテストは `monkeypatch: pytest.MonkeyPatch`
  と付けているので、これは**単なる付け忘れ**＝既存の食い違いを露呈しただけ。

### 原因B: monkeypatch ターゲットが `no_implicit_reexport` に当たる
- `attr-defined` 10件は全て `cli.subprocess` / `cli.compileall` / `cache.Path` への
  `monkeypatch.setattr(...)`。
- `strict` に含まれる `no_implicit_reexport` が「import しただけで再公開していない属性」
  へのモジュール経由アクセスを弾いている。テスト側のアクセスパターンの問題であって、
  本体コードのバグではない。

### CIはこれを隠せていない（むしろ赤のはず）
CIワークフロー（`.github/workflows/quality-gate.yml`）は PR で `--since` により
Ruff/ASTを差分限定するが、**MyPyは常に全ツリー**。`--baseline` はAST専用でMyPyには効かない。
→ つまりこのエラーは**CIでも赤**になる。にもかかわらず入っている = ゲートを通さずに
テストがコミットされた長年のギャップ。

### 改善案（どちらか一方に統一する。推奨はA）

**案A（推奨）— テストもstrictを満たす（"strict everywhere"を貫く）**
1. `tests/test_cache.py:81` に `monkeypatch: pytest.MonkeyPatch` を追加（他テストと統一）。
2. monkeypatchターゲットを再公開で解決。一番素直なのはテスト側で対象モジュールを
   直接importしてsetattrする方式に変えること（例: `import subprocess` した上で
   `monkeypatch.setattr(subprocess, "run", ...)`）。あるいは `cli.py` 末尾に
   `__all__` を定義してメンバーを明示再公開。
   - メリット: スキルの「strict例外を作らない」姿勢と一致。テストコードもゲート対象という
     原則#10を最も忠実に守れる。

**案B — `[tool.mypy]` でもテストを免除（Ruffの除外と歩調を合わせる）**
```toml
[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false
implicit_reexport = true
```
   - メリット: 変更が`pyproject.toml`数行で済む。
   - デメリット: 「テストは品質ゲート対象」という原則がツール設定上は緩む。

> いずれを採るかは方針判断。原則#10を最重視するなら案A。

---

## 🟡 Important

### I-1. `editor.py` `replace_code` に検証が無い — psc自身の哲学と矛盾
`psc replace` は新コードを貼り付けた後、**構文・型・テストを一切検証しない**。
healer は `_full_quality_bar`（mypy+pytest）で貼り付け後を検証するのに、`replace` は素通し。
ログには `"run quality_gate.py to verify."` と出るが、これは旧名残（現在は `psc gate`）。
- 改善案: 貼り付け後に最低限 `ast.parse` で再パースし、壊れたら**自動ロールバック**する。
  （healerの `_healing_loop` が失敗時に `original_code` へ書き戻すのと同じ安全網を `replace` にも。）
- 補足: ログ文言 `quality_gate.py` → `psc gate` に更新（ドキュメントとの整合）。

### I-2. healer の `except Exception` が広すぎる + リトライ時に握りつぶす
`_generate_fix`（71行）と `_healing_loop`（231行）の `except Exception` が
`KeyboardInterrupt`以外の全例外（認証エラー・SDKバグ・プログラミングエラー含む）を
warning/breakで飲み込む。`pyproject.toml` で healer.py は `BLE001` 除外済みなので
ゲートは通るが、設定エラーとモデル一時障害が区別できず、デバッグが困難。
- 改善案: フォールバックは「APIエラー系」に絞り、想定外例外は再送出 or `[ERROR]`で明示。

### I-3. healer のモデルIDがプロジェクト標準とずれている
`FLASH_MODEL = "gemini-3-flash-preview"`。リポジトリのCLAUDE.md/GEMINI.md標準は
`gemini-3.0-flash`。`PRO_MODEL = "gemini-3.1-pro-preview"` は標準どおり。
- 改善案: Flashのモデル名をプロジェクト標準に合わせる（実在ID確認の上）。

---

## 🟢 Minor

- **M-1**: `gate.py` `step_results_to_dicts` は本体から呼ばれていない（テスト専用の可能性）。
  デッドコードなら削除候補だが、公開API意図なら残す — 要確認（私の変更ではないため削除はしない）。
- **M-2**: `ast_checker.py` の `workers` 引数は `check_target` にあるが CLI から渡せない。
  当面不要なら良いが、未使用の公開パラメータは将来の混乱の種。
- **M-3**: `cli.py` `_cmd_gate` の MyPy は常に `--ignore-missing-imports` 固定。
  消費側リポでサードパーティ型を厳密化したいケースで上書き不可。設定化の余地（YAGNIなら据置可）。
- **M-4**: baseline の `_classify` は未知メッセージを `"unknown"` にfallbackするが、
  `_RULE_PATTERNS` に新ルール追加を忘れると静かに `unknown` でfingerprintされ、
  ルール別の集計が崩れる。AST側に新ルールを足す際の連動を `_CHECKER_VERSION` 同様に明示したい。

---

## 結論

| 項目 | 判定 |
|------|------|
| マージ可能か | **Critical(自己ゲート失敗)の解消が前提**。コアロジックは健全 |
| 最優先 | 上記Critical（案Aを推奨） |
| 次点 | I-1（replaceの検証欠如）, I-2/I-3（healer） |

コア実装の品質は高い。問題は「品質ゲートツール自身が品質ゲートを通っていない」という
一点に集約され、しかもそれは2つの明確な原因に還元できる。まずそこを直すのが筋。
