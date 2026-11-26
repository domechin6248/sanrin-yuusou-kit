# 山林パートナーズ　郵送キット自動生成システム

合同会社山林パートナーズ（不要山林の有料引き取り事業）専用の **独立した Streamlit アプリ** です。  
固定資産税書類などを郵送で受け取るための「郵送キット」同封書類と、**長形3号封筒**向け宛名ラベルを PDF で出力します。

> **重要：既存システムとの分離**  
> 本アプリは `sanrin_mail_kit/` フォルダ内に完結しています。他システムのファイル・フォルダ・設定・ポートを参照・共有しません。

---

## 必要環境

- Python 3.10 以上推奨
- macOS / Windows（日本語フォントが利用できること）
- Google スプレッドシート連携時: サービスアカウント JSON

## 初回セットアップ

```bash
cd sanrin_mail_kit

# （任意）仮想環境
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 依存パッケージ
pip install -r requirements.txt
```

### 日本語フォントの配置（推奨）

アプリは次の順でフォントを自動検出します。

1. `./fonts/` 内のフォントファイル
2. OS 標準の日本語フォント（Windows: メイリオ等 / Mac: Arial Unicode 等）

**確実に文字化けを防ぐには**、`NotoSansJP-Regular.ttf` を `fonts/` に配置してください。

> **Mac 注意**: ヒラギノ角ゴ（`.ttc`）は ReportLab 非対応です。`fonts/` の Noto を使ってください。

### フォント検出の確認

```bash
cd sanrin_mail_kit
python3 -c "from pdf_generator import get_font_status; print(get_font_status())"
```

サイドバー「日本語フォント」が「OK」なら成功です。

---

## Google スプレッドシート連携（サービスアカウント）

個人情報を扱うため、**公開リンクは使いません**。サービスアカウントのみでアクセスします。

### 1. Google Cloud でサービスアカウントを作成

1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクトを作成（または既存を選択）
2. **API とサービス → ライブラリ** で「Google Sheets API」を有効化
3. **API とサービス → 認証情報 → サービスアカウントを作成**
4. 作成したサービスアカウントの「キー」→ JSON を追加・ダウンロード

### 2. 認証ファイルを配置

ダウンロードした JSON を次の名前で保存します。

```
sanrin_mail_kit/data/google_service_account.json
```

（このファイルは `.gitignore` 対象です。リポジトリにコミットしないでください）

### 3. スプレッドシートを共有

1. 対象シートを開く  
   `https://docs.google.com/spreadsheets/d/1JpWsr7SoP7Tiq2ftsIgVlhP0RoddgaQgRsRgHN9iIh4/`
2. 「共有」でサービスアカウントのメール（`...@...iam.gserviceaccount.com`）を **編集者** として追加
3. **「リンクを知っている全員」などの公開設定は解除**（制限付きに戻す）

### 4. 列マッピング

`data/sheets_config.json` で定義済みです。

| シート列 | アプリ項目 |
|----------|------------|
| お客様番号 | 管理番号 |
| 発信者のお名前 | 氏名 |
| 郵便番号 | 郵便番号 |
| 住所 + 番地・建物名・部屋番号 | 住所 |
| お電話番号 | 電話 |
| 受付日時 | 受付日 |
| 備考・特記事項 | 備考 |
| 対応状況 / 案内ルート | フィルタ・書き戻し |

PDF 生成後、対応状況は **「郵送キット作成済」** に更新されます。

---

## 起動方法（既存アプリと衝突しないポート）

```bash
cd sanrin_mail_kit
source .venv/bin/activate
streamlit run app.py --server.port 8510
```

ブラウザ: `http://localhost:8510`

---

## 使い方の概要

### ① スプレッドシートから選択（推奨）

1. 「シートを読み込む」
2. 案内ルート「郵送」／対応状況で絞り込み
3. お客様を選択 → PDF 生成（対応状況も自動更新）

### ② 単件作成

手入力でも同様に PDF 生成できます。

### ③ 履歴・再読み込み / ④ CSV一括生成

従来どおりローカル履歴・CSV 一括にも対応しています。

### 宛名ラベル印刷モード

| モード | 用途 |
|--------|------|
| **長3（推奨・既定）** | 長形3号封筒（120×235mm）貼付用。95×55mm の往信・返信ラベル |
| **A** | A4ノーカット（上下2分割・切り取り線） |
| **B** | 市販マルチラベル A4 2面 / 4面 |

左右・上下オフセット（-10.0〜+10.0mm）と「枠線を表示する」でテスト印刷できます。

---

## フォルダ構成

```
sanrin_mail_kit/
├── app.py
├── pdf_generator.py
├── sheets_client.py
├── requirements.txt
├── README.md
├── data/
│   ├── company_info.json
│   ├── sheets_config.json
│   ├── google_service_account.json  # 手動配置・Git管理外
│   ├── history.csv                  # 自動生成
│   └── management_counter.json      # 自動生成
├── fonts/
└── output/
```

---

## トラブルシュート

| 症状 | 対処 |
|------|------|
| 認証ファイル未配置 | `data/google_service_account.json` を置く |
| シート読み込み失敗 | サービスアカウントへ「編集者」共有したか確認 |
| 日本語が文字化け | `fonts/NotoSansJP-Regular.ttf` を確認 |
| ラベル印刷がズレる | オフセットを 0.5mm 刻みで調整 |
| 公開リンクが怖い | **制限付きに戻し**、SAメールのみ共有する |

---

© 合同会社山林パートナーズ — 郵送キット自動生成システム（独立アプリ）
