# PE Market Research Skill

PEファンドの投資先候補調査・成長戦略検討向けの、業界横断リサーチワークフロー。「プレイヤー発見→基礎情報→資本構造→M&A適性→ファクトチェック」の型を、対象業界を問わず一次資料ベースで回す。

| Document | Purpose |
|----------|---------|
| [SKILL.md](SKILL.md) | 使用場面・実行方法・学んだ実践知・よくある間違い |
| [market_map_workflow.js](market_map_workflow.js) | Workflowツールに渡す4フェーズ（Discover/Profile/Assess/Verify）の実装 |

## Quick Start

このスキルは追加のインストール手順を持たない。`market_map_workflow.js` をWorkflowツールに、以下の形の引数を渡して実行する。

```js
{
  industry: "糖アルコール(sugar alcohol) manufacturers",
  knownPlayers: ["Roquette", "Cargill", "ADM"],        // 既知プレイヤー。再発見の重複を防ぐ
  regions: ["Turkey", "Nigeria", "Russia", "Brazil"],   // 発見スイープ対象の地域リスト
  assessAxis: "independent OEM candidate with no capital ties to Cargill or Mitsubishi group",
}
```

## When to Use

- 既存のプレイヤーマップに新規企業を追加すべきか判断する（「この会社もプレイヤーでは？」）
- ある地域・カテゴリの調査網羅性を確認する（「他の国にもメーカーはないか」）
- 企業の資本構造（上場/非上場、株主、外資比率、既存M&A履歴）を検証する
- M&A/OEM先としての適性を、確認済み事実だけから評価する
- 既存の調査資料群に矛盾・未検証の断定がないかファクトチェックする

使わない場面: 単発で1社だけ調べれば済む質問（WebSearch/WebFetchを直接使えば十分）。業界構造の理解が既にあり、単に文章を書くだけの作業。

## Workflow（4フェーズ）

`market_map_workflow.js` は以下を自動で流す。

1. **Discover** — 地域ごとに`agent()`を並列実行（`parallel()`）し新規プレイヤーを探索。各地域は新規ゼロが2ラウンド連続するまで続ける（loop-until-dry）。既知社（`knownPlayers`）は再発見しても報告させない。
2. **Profile** — 発見した各社を`pipeline()`で一次資料調査（上場/非上場、株主構成、売上、資本提携、事業比重、輸出実績）。企業ごとに他社の完了を待たないパイプライン実行。
3. **Assess** — Profile結果を`assessAxis`に照らしてフィット判定（`strong_fit`/`partial_fit`/`poor_fit`/`insufficient_data`）。未確認項目は楽観補完しない。
4. **Verify** — `phase('Verify')`。confidenceが`要検証`のまま、または`assess.fit_verdict`が`insufficient_data`のプロファイルだけを対象に、対抗仮説で独立再検証（`parallel()`）。

戻り値は `{ discovered_count, players: [...], verification_followups: [...] }`。各playerに `confidence`タグ（`一次`/`一次寄り`/`要検証`）と出典URLが付く。

## Highlights

- **一次資料でしか主張しない** — 全項目に確度タグ（[一次]/[一次寄り]/[要検証]）を付与。Profile/Assess段階のプロンプトは「未確認」を弱みとして扱うよう既定されている。
- **結果は経緯を書かず最終形だけ** — 出力は現在の事実のみ。「当初X社としていたが訂正」といった調査の紆余曲折は書かない設計（Assessフェーズのプロンプトにも明記）。
- **製造業と資本構造は別軸で調べる** — 「原料は何か」と「資本的に紐がついているか」は別の調査。本ワークフローはProfile段階で両方カバーするが、範囲を広げすぎると1社あたりの調査が浅くなる。
- **利用上限エラーは失敗として確定終了** — Workflow内の`agent()`呼び出しが組織の支出上限で落ちても再試行やハングはしない。大量並列は連鎖失敗しうるため、`regions`やdiscoveredのバッチサイズを絞る。
- **動作確認済み**（2026-07時点、糖アルコール業界・エジプト1地域で実行）— Discover→Profile→Assess→Verifyが一次資料ベースで機能し、支配株主構成・過去のM&A競合まで掘り出した実績あり。

## Common Mistakes

| 症状 | 原因 | 対処 |
|---|---|---|
| 同じ会社が複数地域から重複発見される | `knownPlayers`に既存社を全て入れていない | Discover前に既存資料から企業名を全部抽出してseedに渡す |
| 「輸出商社」を製造企業として報告 | 検索結果のみで判定、公式サイト未確認 | PROFILE段階で必ずWebFetch確認を強制する文言を入れる（スクリプトに既定済み） |
| M&A適性の判定が楽観的すぎる | 未確認項目を「たぶん良好」で補完 | ASSESS_SCHEMAのreasoningは「未確認」を弱みとして扱うようプロンプトで明示（既定済み） |
| 資料に反映すると経緯だらけになる | Workflow出力をそのまま資料に転記 | 出力の`profile`/`reasoning`から結論のみ抽出し、資料側で経緯語彙（当初/訂正/撤回等）を使わない |
| `industry`に複数品目を並べると存在しない品目まで前提視される | 品目を広く書くと、実際は1品目しか作っていない企業にも他品目の言及を誘発しがち | Discover段階は広く倒してよいが、Profile段階で`core_business_share`が前提の一部を否定した場合はそれを正として扱う |
