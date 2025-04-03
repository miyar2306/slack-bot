# Bottle API Server

軽量なPython Bottleフレームワークを使用したシンプルなAPIサーバー。

## セットアップ

### 必要条件
- Python 3.8以上
- uv（高速Pythonパッケージマネージャー）

### インストール

1. リポジトリをクローン
```bash
git clone <repository-url>
cd slack-bot
```

2. 仮想環境を作成して有効化
```bash
uv venv
source .venv/bin/activate  # macOS/Linux
```

3. 依存関係をインストール
```bash
uv pip install -r requirements.txt
```

## 実行方法

### 開発環境
```bash
python app.py
```

### 本番環境
```bash
gunicorn app:app -b 0.0.0.0:8080 -w 4 -k gevent
```

## APIエンドポイント

- `GET /` - APIステータス確認
- `GET /api/items` - すべてのアイテムを取得
- `GET /api/items/{id}` - 特定のアイテムを取得
- `POST /api/items` - 新しいアイテムを作成
