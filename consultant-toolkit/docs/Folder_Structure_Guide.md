# マルチシステム導入プロジェクト フォルダ構成ガイド

## 1. はじめに

### 1.1 目的
本ドキュメントは、ERP（基幹システム）および関連する周辺システム導入プロジェクトにおける、電子ファイルの格納ルールおよびディレクトリ構成を定義するものである。
情報の検索性を高め、版数管理のミスによる手戻りを防ぎ、プロジェクトメンバー（ベンダーおよびユーザー企業）間の円滑な情報共有を実現することを目的とする。

### 1.2 対象読者
本プロジェクトに関わる全てのプロジェクトマネージャー、チームリーダー、メンバー。

---

## 2. ディレクトリ構造概観

```text
ERP_PMO/                        # プロジェクトルート (旧: erp)
├── 00_ProgramManagement/       # プログラム全体管理 (PMO)
├── 10_ERP_Core/                # 基幹ERPシステム導入 (Main)
│   ├── 00_Management/          # チーム内管理
│   ├── 01_Requirements/        # 要件定義
│   ├── 02_Design/              # 設計
│   ├── 03_Development/         # 開発
│   ├── 04_Testing/             # テスト
│   ├── 05_DataMigration/       # データ移行
│   ├── 06_Training/            # 教育
│   └── 07_Operation/           # 運用準備
├── 20_Logistics_System/        # 物流システム導入
├── 30_BI_System/               # BI/DWHシステム導入
└── 90_Architecture/            # 共通基盤・アーキテクチャ
```

---

## 3. 詳細定義

### 00_ProgramManagement (全体プログラム管理)
**責任者:** 全体PMO / **更新頻度:** 週次〜随時

| フォルダ名 | 格納ファイル例 | 説明 |
| :--- | :--- | :--- |
| **01_MasterPlan** | `Program_MasterSchedule_v1.0.xlsx`<br>`Organization_Chart_v2.1.pptx` | 全体マスタースケジュール、全体体制図、予算管理表、SOW（作業範囲記述書）。 |
| **02_CrossIssues** | `Cross_Issue_Log_v10.xlsx`<br>`Decision_Record_001.pptx` | **重要:** 複数システムに影響する課題（クロス課題）を管理。システム間の仕様調整結果もここに決定事項として残す。 |
| **03_SteerCo** | `20240121_SteerCo_Deck_v1.0.pptx`<br>`20240121_SteerCo_Minutes.docx` | ステアリングコミッティ（役員報告会）の発表資料および議事録。 |

### 10_ERP_Core (基幹ERP導入チーム)
**責任者:** ERPチームリーダー / **更新頻度:** 日次

#### 10_ERP_Core/00_Management
チーム単位の進捗・課題管理。
*   **01_Plan**: WBS詳細、チーム体制図。
*   **02_Progress**: 週次定例資料、進捗報告書。
*   **03_Issues_Risks**: チーム内課題管理表 (Backlog)。

#### 10_ERP_Core/01_Requirements (要件定義)
*   **01_BusinessFlow**:
    *   `AsIs_OrderToCash_v1.0.pptx` (現行受注プロセス)
    *   `ToBe_ProcureToPay_v1.0.pptx` (新購買プロセス)
*   **02_FitGap**:
    *   `FitGap_Sheet_SCM_v2.0.xlsx` (Fit&Gap分析シート)
    *   各モジュール（SCM/FIN/CRM）ごとにサブフォルダを作成し管理。

#### 10_ERP_Core/02_Design (設計)
*   **01_Functional**: アドオン機能設計書、帳票レイアウト定義。
    *   命名規則: `DS_{ID}_{機能名}_v{版数}.xlsx` (例: `DS_R001_請求書発行_v1.0.xlsx`)
*   **02_Parameter**: パッケージ標準機能の設定定義書（Configuration Sheet）。
*   **03_Authorization**: 業務ロール一覧、ユーザークラス定義、アクセス権限マトリクス。

#### 10_ERP_Core/04_Testing (テスト)
*   **01_IT (Integration Test)**: 結合テスト仕様書、テストデータ、エビデンス。
*   **02_UAT (User Acceptance Test)**: ユーザー受入テスト計画書、検収確認書。

#### 10_ERP_Core/05_DataMigration (移行)
*   **02_Mapping**: 新旧システム間の項目マッピング定義書（Mapping Rule）。
    *   `Map_CustomerMaster_v1.0.xlsx`
    *   `Map_OpenPO_v1.0.xlsx` (発注残データ)

### 90_Architecture (共通基盤・アーキテクチャ)
**責任者:** アーキテクト / **更新頻度:** 要件定義〜設計フェーズで頻繁に更新

| フォルダ名 | 格納ファイル例 | 説明 |
| :--- | :--- | :--- |
| **01_Integration** | `IF_List_v1.0.xlsx`<br>`IF_Spec_ERP_LOGI_001.xlsx` | **システム間連携基盤**。インターフェース一覧、各I/Fの詳細仕様書（フォーマット、プロトコル、頻度）。 |
| **02_DataGovernance** | `Code_Design_Item_v1.0.xlsx` | 全社コード設計（品目コード、取引先コード等の採番ルール）、データ辞書。 |
| **03_Infra** | `Network_Diagram_v1.0.pptx`<br>`Server_Spec_List.xlsx` | ネットワーク構成図、サーバー仕様書、クラウド構成定義（IaC設計図など）。 |

---

## 4. 運用ルール・命名規則

### 4.1 ファイル命名規則
原則として以下の形式で統一する。
`{識別子}_{内容記述}_{日付or版数}.{拡張子}`

*   **Bad**: `要件定義書.docx`, `最新_課題管理表.xlsx`, `コピー ～ 議事録.txt`
*   **Good**:
    *   `REQ_SalesProcess_v1.0.docx`
    *   `MGT_IssueList_20240121.xlsx`
    *   `MIN_WeeklyMeeting_20240121.docx`

### 4.2 バージョン管理 (Versioning)
*   **ドラフト版**: `v0.x` (例: `v0.1`, `v0.9`)
*   **初版承認済**: `v1.0`
*   **改訂版**: `v1.1`, `v1.2` (マイナー改訂), `v2.0` (メジャー改訂)
*   **「最新」「Final」等の名称使用禁止**: どれが本当に最新かわからなくなるため、必ず数字で管理する。

### 4.3 廃止・アーカイブ
不要になったファイルや古い版は、削除せずに各フォルダ直下の `_Old` フォルダ（必要に応じて作成）または `99_Archive` フォルダへ移動する。
