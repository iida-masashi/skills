# タスク管理 (Task List)

## 完了したタスク (Completed)

*   **[2026-04-10] promo-forecast-skill の規約遵守徹底 (Refactoring)**
    *   `python-safe-coding` のルール（The Transcendental Engineering Code）を完全適用。
    *   `libs/` および `scripts/` 内の全関数に厳密な型ヒント（Type Hints）を付与。
    *   不要な `pandas` 依存を排除し、処理を `polars` 中心に移行。
    *   `print()` を撲滅し、`logging` モジュールによる構造化ロギングに置換。
    *   日付型のエラー修正。
*   **[2026-04-10] promo-forecast-skill のDRY原則適用と共通化**
    *   冗長なデータ読み込み・日付パースを `libs/data_utils.py` の `load_csv_with_date` に一元化。
    *   `pl.DataFrame` から Darts `TimeSeries` への変換を `libs/data_utils.py` の `to_time_series` に共通化。
    *   日付と商品IDの直積（Skeleton）生成ロジックを `libs/data_utils.py` に共通化。
    *   Streamlit UI (`step3`) に直書きされていたシミュレータ用モデルの学習ロジック (`get_tuned_sim_model`) を `libs/models.py` へカプセル化（分離）。
    *   **結果**: Pytest (23/23件) パス。Lintエラー 0件。Quality Gate 完璧通過。
*   **[2026-06-13] 信頼性修正(M1-M4) & CPG現実性機能(A1/A3/A4/A6) & 利用法タブ**
    *   **M1**: 信頼区間キャリブレーション（split-conformal）— 実カバレッジ 26% → 80%。`calibrate_bands()` 新設。
    *   **M2**: リフトを特売日のみに計上 — 偽リフト 4-5% → 0%、リフト総量比ほぼ100%。
    *   **M3**: シミュレーターのリスク幅を固定±10%ダミーから実分位点(0.1/0.9)に差し替え。
    *   **M4**: バイアス指標 `calculate_bias` を追加し、ダッシュボード精度パネルに表示（+=過剰在庫 / −=欠品）。
    *   **A1**: 買いだめ反動（forward-buying）を `step0` に注入。従来分解がリフトを実態の84-86%に過小評価していたことを定量化。
    *   **A3**: 欠品打ち切り補正 — `step0` で censoring、`step1` でベース推定から除外。
    *   **A4**: 販促飽和（wear-out）を `step0` に注入 — 高頻度期にリフト38%減衰。
    *   **A6**: walk-forward 検証スクリプト `scripts/validate_walkforward.py` 新設（複数origin）。
    *   **共変量リーク堅牢化**: 中立共変量の窓を末尾スライスから日付明示スライス（`_slice_forecast_window`）に変更。
    *   **ゼロ処理整合**: 全ゼロ実績で `(0.0, 0.0)`（=完璧と誤表示）を `NaN`（未定義）に修正。
    *   **利用法・解説タブ**: ダッシュボード先頭に追加（全9タブに）。
    *   分解精度検証スクリプト `scripts/validate_decomposition.py` 新設。
    *   **結果**: Pytest (42/42件) パス。
*   **[2026-04-15] ダッシュボード ビジュアル強化 & 4新機能追加**
    *   ランクマッピング一元化: `config.py` に `TIER_MAP`, `TIER_COLORS`, `map_promo_tier()` を集約。
    *   **Feature 1**: 需要分解タブ強化 — 販促イベントアノテーション + 日次/週次/月次集約切替。
    *   **Feature 2**: 価格弾力性カーブ（新タブ）— 10円刻みスイープ、最適価格自動表示。
    *   **Feature 3**: 品目横断ポートフォリオ（新タブ）— 全品目散布図、積み上げ棒、ROIマトリックス。
    *   **Feature 4**: 販促カレンダー入力UI（新タブ）— 既存カレンダー編集、新規プラン追加、ガントチャート。
    *   タブ名変更: 「LGBM分析」→「LGBM 360日展望」、「モデル対決」→「Hybrid予測」。
    *   全8タブにチャート解説文を追加。
    *   既存カレンダーの `st.data_editor` 編集 + 「保存 & 予測を再実行」ボタン（step1→step2自動実行）。
    *   Plotly `titlefont_color` 廃止対応（nested `title.font.color` に修正）。
    *   ダッシュボード: 5タブ → 8タブ、chart_builder: 7関数 → 11関数。
    *   **結果**: Pytest (26/26件) パス。ruff all checks passed。Gitコミット済み。
*   **[2026-04-15] 需要分解チャート（日次）の積み上げバグ修正**
    *   `libs/chart_builder.py` の `create_decomposition_chart` 関数を修正。
    *   日次データの描画時に Plotly の `stackgroup` が正しく積層されない問題（配列のインデックスずれが原因）を解決するため、事前に Polars で日付ソートし、`.to_list()` で純粋な Python リストとして座標データを渡すように修正。
    *   `fillcolor` を明示的に指定して塗りつぶしが確実に行われるように対応。

## 残タスク / 次のアクション (Backlog)

> 専門家レビューに基づく詳細な残作業（修正M2/M4・追加A1〜A6・既知の限界）は [BACKLOG.md](BACKLOG.md) を参照。

*   [ ] 2026-06-13 の信頼性修正・現実性機能の Git コミット
*   [ ] Streamlitダッシュボードの目視確認（全9タブ）
*   [ ] (将来 A1分解) 反動減を補正する非対称ベースライン（現状はデータに注入済み、分解側は未対応）
*   [ ] (将来 A5) 外部共変量の統合（天候・Google Trends — opendata-skill/darts-forecast-skill連携）
*   [ ] (将来 A2) カニバリゼーション分析（品目間のクロス影響定量化）
*   [ ] (将来) 階層的予測（カテゴリー・チャネル・店舗クラス単位）
