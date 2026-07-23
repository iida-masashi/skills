# 強化案・改善案ロードマップ (P0/P1/P2)

> 「Guardian of Quality」として他 Skill (darts-forecast /
> consultant-toolkit / opendata 等) が依存できる再利用可能な品質ゲートに昇格させるためのロードマップ。

---

## 完了済み (2026-04-28)

### P0 — 基盤整備
- [x] **#1** インストーラブル化 — `[project.scripts] psc=...:main` で `uv pip install -e .` だけでCLI公開。`scripts/*.py`は撤去、`src/python_safe_coding/cli.py`に集約。
- [x] **#2** 終了コード契約 — `0=pass / 1=violation / 2=internal-error / 3=config-error` に固定し SKILL.md と `docs/reference/exit-codes.md` に明記。`--github-summary` でmarkdownレポート。
- [x] **#3 (部分)** ポリシー設計 — Ruff-first 原則を採用し、独自AST rule は Polars First のみに集約 (ADR 0001)。`PSC001-008` のような独自ルール拡張は #4 で扱う。

### P1 — 差別化
- [x] **#5** CI 統合パッケージ — `.github/workflows/quality-gate.yml`、`.pre-commit-hooks.yaml`、`templates/.pre-commit-config.example.yaml`、`docs/ci-integration.md`。actions/cache@v4 で `.psc-cache` 永続化。
- [x] **#6** Self-healer ハードニング — `--dry-run` / `--patch-only PATH` でHITL運用、`auto-commit` 前に Ruff+MyPy+pytest 全通過必須、`[heal]` extras 化で本体から分離 (ADR 0003)。
- [x] **#8** パフォーマンス — `ThreadPoolExecutor` で並列AST走査、`(path, mtime_ns, size, _CHECKER_VERSION)` キーの opt-in キャッシュ (ADR 0004)。

### その他完了 (P0/P1相当)
- [x] **A-3** diff-aware (`--since <ref>`) — Ruff/AST のみ、MyPyは全体走査。
- [x] **A-4** ベースライン (`.psc-baseline.json`) — fingerprint = `(file, rule_id, sha1(line)[:16])`、stale entry警告 (ADR 0002)。
- [x] **A-5** healer プレビューモード (`--dry-run` / `--patch-only`)。
- [x] **B-1** mutmut削除 (Windows未対応で無価値だった)。
- [x] **B-2** `google-genai` を `[heal]` extras に分離 + 遅延 import。

### #10 ドキュメント整備 (部分)
- [x] SKILL.md を「哲学/憲章」に集中。
- [x] `docs/reference/{cli,rules,exit-codes}.md` 分割。
- [x] `docs/adr/{0001..0004}.md` (Ruff-first / AST-only baseline / healer optional / ThreadPool+cache)。
- [ ] `docs/cookbook/` — Skill 別統合レシピは #11 と一緒に対応予定 (今は適切な検証先がないため defer)。

---

## 残件 (P2 — 中長期)

### #4 プラグインモデル [Effort: M]
`entry_points` group `python_safe_coding.ast_rules` で外部ルールを登録。
- 各 Skill 固有ルール (例: darts で `pl.merge(how=...)` 必須) を本体改修なしで追加可能に。
- `Rule` プロトコル + `pluggy` 採用検討。
- `_CHECKER_VERSION` (ADR 0004) と整合する形でプラグインのバージョン管理が必要。

### #7 Observability [Effort: S]
- `structlog` 移行 — SKILL.md 規定通り。`PSC_LOG_FORMAT=json|console`、`PSC_LOG_LEVEL` env 切替。
- `junitparser` で JUnit XML emitter — `--format junit` で CI ダッシュボード連携。

### #11 クロス Skill 採用プレイブック [Effort: S]
- `docs/migration.md` で「既存 Skill を 30 分で psc 化する手順」 (pre-commit → CI yml → ルール段階有効化)。
- path 依存での取り込み:
  ```toml
  [tool.uv.sources]
  python-safe-coding = { path = "../python-safe-coding", editable = true }
  ```
- `docs/cookbook/{darts-forecast,consultant-toolkit,opendata}.md` — 採用先が確定したら順次。

### A-6 テスト成熟 [Effort: M]
- **Hypothesis** で AST チェッカ不変条件 (「同 AST に何度かけても同結果」「コメント追加で結果不変」) を property test 化。
- `editor.replace_code` の golden file テスト。
- カバレッジ floor 80 → 90 へ段階的。

### A-7 / #12 セキュリティ姿勢 (SLSA 寄り) [Effort: L]
- `cyclonedx-py` で SBOM 自動生成 (`make sbom`)。
- GitHub Actions OIDC + `sigstore-python` で wheel 署名。
- `gitleaks` を pre-commit + CI 組込。
- `pip-audit` を週次 CI (`uv audit` GA 後に差替)。

---

## 実装順 (推奨)
1. **#11 採用プレイブック** — 軽量で他Skillへの売り込みに直結。
2. **#7 structlog + JUnit** — CIダッシュボード連携の地ならし。
3. **#4 プラグインモデル** — 採用先が増えてから固有ルールニーズが顕在化する想定。
4. **A-6 Hypothesis** — テスト成熟は採用先のフィードバックを受けてから。
5. **A-7 / #12 SLSA** — 配布先が安定したら。
