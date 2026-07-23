---
name: pe-market-research
description: Use when researching an industry for PE-style due diligence — building a player/competitor map, checking a company's capital structure and ownership, screening M&A or OEM targets, or sweeping regions for manufacturers not yet on a player list. Symptoms: "this company might be a player too", "does anyone in [country] make this", "is this an independent target or does a competitor have a stake in it", "check if this M&A target list is complete".
---

# PE Market Research

## Overview

PEファンドの投資先候補調査・成長戦略検討に使う、業界横断の汎用リサーチワークフロー。対象業界を問わず「プレイヤー発見→基礎情報→資本構造→M&A適性→ファクトチェック」の型で回す。

**核心原則**: 一次資料でしか主張しない。確度タグ（[一次]/[一次寄り]/[要検証]）を全項目に付ける。結果には最終事実だけを書き、調査の経緯（「当初〜としていたが訂正」等）は書かない——読み手が知りたいのは今の事実であり、調査の紆余曲折ではない。

## When to Use

- 既存のプレイヤーマップに新規企業を追加すべきか判断する（「この会社もプレイヤーでは？」）
- ある地域・カテゴリの調査網羅性を確認する（「他の国にもメーカーはないか」）
- 企業の資本構造（上場/非上場、株主、外資比率、既存M&A履歴）を検証する
- M&A/OEM先としての適性を、確認済み事実だけから評価する
- 既存の調査資料群に矛盾・未検証の断定がないかファクトチェックする

**使わない場面**: 単発で1社だけ調べれば済む質問（WebSearch/WebFetchを直接使えば十分）。業界構造の理解が既にあり、単に文章を書くだけの作業。

## How to Run

`market_map_workflow.js` をWorkflowツールに渡す。args は以下の形:

```js
{
  industry: "糖アルコール(sugar alcohol) manufacturers",
  knownPlayers: ["Roquette", "Cargill", "ADM", ...],   // 既知プレイヤー。再発見の重複を防ぐ
  regions: ["Turkey", "Nigeria", "Russia", "Brazil"],   // 発見スイープ対象の地域リスト
  assessAxis: "independent OEM candidate with no capital ties to Cargill or Mitsubishi group",
}
```

4フェーズが自動で流れる:
1. **Discover** — 地域ごとに新規プレイヤーを探索。各地域は「2ラウンド連続で新規ゼロ」まで続ける（loop-until-dry）。既知社を再発見しても報告させない。
2. **Profile** — 発見した各社を一次資料で調査（上場/非上場、株主構成、売上、既存資本提携、事業比重、輸出実績）。パイプライン実行なので、企業ごとに他社の完了を待たない。
3. **Assess** — `assessAxis`に照らしたフィット判定。Profileで確認できなかった項目は「未確認」のまま楽観補完しない。
4. **Verify** — [要検証]や矛盾が残った項目だけ、対抗仮説で独立再検証。

出力は `{ discovered_count, players: [...], verification_followups: [...] }`。各playerに確度タグ・出典URLが付く。

## Key Practices (learned the hard way)

- **原料と資本構造は別軸で調べる**——「原料がコーンか」と「資本的に紐がついているか独立系か」は全く別の調査で、一方が分かっても他方は分からない。両方必要なら2段階で調査する（本ワークフローはProfile段階で両方カバーするが、範囲を広げすぎると1社あたりの調査が浅くなる。深掘りが要る時はPROFILE_SCHEMAのプロンプトを絞る）。
- **「製造業か販売業か」を毎回区別する**——ソルビトール等のB2B原料は輸入・卸売業者がSEOで「manufacturer」を自称するケースが非常に多い。公式サイトで製造工程・工場の記述を確認してから[一次]と判定する。
- **用語衝突に注意**——業界特有の多義語（例:「ポリオール」が食品用糖アルコールと工業用ウレタン原料の両方を指す）があると、無関係な企業を誤って同じリストに混ぜやすい。カテゴリ名だけでなく製法・用途で二重確認する。
- **地域スコープが違う資料に無理に追加しない**——「アジア限定」と明記された資料にアジア外の企業を追加すると資料の一貫性が壊れる。スコープ外の発見は別資料に置く。
- **結果は経緯を書かず最終形だけ**——「当初X社としていたが誤りのため訂正」ではなく、訂正後の事実だけを書く。監査ログが必要なら別途Git履歴に委ねる。
- **利用上限エラーはハングではない**——Workflow内のagent()呼び出しが組織の支出上限で落ちても、それは失敗として確定終了する（再試行やハングではない）。同時に大量並列を投げると連鎖的に失敗するので、regionsやdiscoveredのバッチサイズを絞る、または時間を置いて再実行する。

## Common Mistakes

| 症状 | 原因 | 対処 |
|---|---|---|
| 同じ会社が複数地域から重複発見される | `knownPlayers`に既存社を全て入れていない | Discover前に既存資料から企業名を全部抽出してseedに渡す |
| 「輸出商社」を製造企業として報告 | 検索結果のみで判定、公式サイト未確認 | PROFILE段階で必ずWebFetch確認を強制する文言を入れる（スクリプトに既定済み） |
| M&A適性の判定が楽観的すぎる | 未確認項目を「たぶん良好」で補完 | ASSESS_SCHEMAのreasoningは「未確認」を弱みとして扱うようプロンプトで明示（既定済み） |
| 資料に反映すると経緯だらけになる | Workflow出力をそのまま資料に転記 | 出力の`profile`/`reasoning`から結論のみ抽出し、資料側で経緯語彙（当初/訂正/撤回等）を使わない |
| `industry`に複数品目を並べると存在しない品目まで前提視される | `"sorbitol/xylitol/maltitol..."`のように広く書くと、実際は1品目しか作っていない企業にも他品目の言及を誘発しがち | Discover段階は広く倒してよいが、Profile段階で`core_business_share`が「前提の一部は不正確」と気づいた場合はそれを正として扱う（本ワークフローは未確認を楽観補完しない設計なので、こう気づいた時点で信頼してよい） |

**動作確認済み**（2026-07時点、糖アルコール業界・エジプト1地域で実行）: Discover→Profile→Assess→Verifyの4フェーズが一次資料ベースで機能し、支配株主構成・過去のM&A競合（敗退した対抗買収提案）まで掘り出した。未確認項目は「未確認」のまま`partial_fit`判定に反映され、楽観補完は起きなかった。
