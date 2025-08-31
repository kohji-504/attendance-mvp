
# attendance-mvp

**Python + Flask + SQLite で“最短1日で立ち上げる”勤怠管理MVP**  
出勤・退勤・休憩の打刻、当日ログ、個人サマリ、CSVエクスポート、簡易管理画面を備えた最小構成です。  
ローカルで即日導入し、そのままクラウド（Render / Railway 等）へ展開できます。

---

## ✨ 特長

- **最短1日で立ち上げ**：依存は最小（Flask / SQLAlchemy / SQLite）
- **必要十分な機能**：出勤 / 退勤 / 休憩開始 / 休憩終了、当日ログ、個人サマリ、CSV出力、簡易管理
- **堅牢な集計ロジック**：打刻の抜け・順序ミス（例：出勤せず退勤）でも落ちない
- **タイムゾーン安全**：JST（Asia/Tokyo）を基準に naive/aware を吸収（Jinja フィルタ `|tolocal` 付き）
- **そのままデプロイ**：SQLite→PostgreSQL に差し替え可能、WAF不要の軽量構成

---

## 📦 ディレクトリ構成

```
attendance-mvp/
├─ app.py
├─ requirements.txt
├─ .gitignore
├─ .env               # 任意（公開しない）
├─ templates/
│   ├─ base.html
│   ├─ index.html
│   ├─ my.html
│   └─ admin.html
└─ static/
    └─ style.css
```

---

## 🚀 クイックスタート

### 0) 事前準備
- Python 3.10+ を推奨
- Windows の方は [Git for Windows](https://gitforwindows.org/) を入れておくと便利

### 1) 仮想環境 & 依存インストール
```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows
# .venv\Scripts\activate

pip install -r requirements.txt
```

### 2) DB初期化（どちらか）
**A. CLIで作成（推奨）**
```bash
flask --app app.py init-db
```
**B. 自動作成**
`app.py` に `with app.app_context(): db.create_all()` が入っていれば、起動時に自動作成されます。

### 3) 起動
```bash
flask --app app.py run
# http://127.0.0.1:5000/
```

### 4) 使い方
- トップ `/`：名前を入力して **出勤 / 休憩開始 / 休憩終了 / 退勤** を記録  
- 個人サマリ `/me?name=山田太郎`：直近7日分の勤務時間と打刻履歴  
- 管理 `/admin?p=<ADMIN_PASSWORD>`：当日サマリと **CSVエクスポート**

> `.env` に `ADMIN_PASSWORD` を設定しておくと管理画面が保護されます（後述）。

---

## 🔑 環境変数（`.env`）

```env
ADMIN_PASSWORD=change-me   # 管理画面パスワード（任意）
TZ=Asia/Tokyo              # タイムゾーン（既定は Asia/Tokyo）
SECRET_KEY=dev-key         # Flask SECRET_KEY（セッション/flash 用）
```

> `.env` は **公開しない** でください（`.gitignore` で除外済み）。

---

## 🗃️ データモデル

- **User**
  - `id` (int, PK)
  - `name` (str, unique, required)

- **Punch**
  - `id` (int, PK)
  - `user_id` (FK → User.id)
  - `kind` (str) … `in` | `out` | `break_in` | `break_out`
  - `ts` (datetime, index) … JST換算で保存・表示

---

## 🧮 集計ロジック（堅牢版）

- **状態機械**で計算：
  - 出勤中かつ休憩でない区間のみ加算
  - 休憩開始で直前までを加算し、休憩終了で再開
  - 順序ミス（出勤前の退勤等）は **無視**（例外を出さない）
  - 開きっぱなしの実働は日末（または現在時刻）で締める
- 時刻は `to_local()` と Jinja フィルタ `|tolocal` で **JST aware** に統一

---

## 🧪 開発用コマンド（任意）

`app.py` 末尾に CLI を追加している場合、以下が使えます。

```bash
# テーブル作成
flask --app app.py init-db

# DBを丸ごと作り直す（開発用）
flask --app app.py reset-db

# デモユーザーを投入
flask --app app.py seed
```

---

## 📤 CSVエクスポート

管理画面 `/admin?p=...` で期間を指定すると、  
`attendance_YYYY-MM-DD_YYYY-MM-DD.csv` をダウンロードできます（UTF-8 BOM）。

---

## 🛡️ よくあるエラーと対処

- **TemplateNotFound: index.html**  
  → `templates/` の場所・ファイル名・拡張子（`.html`）を確認。`app.py` で `template_folder` を明示すると堅牢。

- **TypeError: can't subtract offset-naive and offset-aware datetimes**  
  → `to_local()` と `|tolocal` を使い、計算・表示前に **JST aware** へ統一。

- **OperationalError: no such table: ...**  
  → `flask --app app.py init-db` を実行。`with app.app_context(): db.create_all()` でもOK。

- **DBが壊れた/消したい**（開発時）  
  → `attendance.db`, `attendance.db-wal`, `attendance.db-shm` を削除 → `init-db` で再作成。

---

## ☁️ デプロイ（例）

- **Render / Railway**：
  1. リポジトリを接続して自動デプロイ
  2. 環境変数を設定（`SECRET_KEY`, `ADMIN_PASSWORD`, `TZ` など）
  3. 必要に応じて DB を **PostgreSQL** に変更：
     ```python
     app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql+psycopg2://USER:PASSWORD@HOST:PORT/DBNAME'
     ```

- **Gunicorn + Waitress/uvicorn** などの本番WSGI/ASGIサーバーを利用すると安定します。

---

## 🤝 コントリビューション

Issue / PR 歓迎です！バグ報告や改善提案、機能追加のアイデアがあればぜひ。

---

## 📄 ライセンス

MIT License

---

## 📝 ブログ用の案内（学習ログ風）

```markdown
コード全文はここでは長くなるので割愛しました。  
私の GitHub に一式アップしてありますので、もし「そのまま動かしてみたい」という方は参考にしてみてください。  

👉 [GitHubリポジトリを見る](https://github.com/<YOUR_USERNAME>/attendance-mvp)
```
