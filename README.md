# Slack Bot with Bottle

Bottleフレームワークを使用したSlackボットサーバー。

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

### 環境変数の設定

```bash
export SLACK_BOT_TOKEN=xoxb-your-token
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

## Slackイベント

このボットは以下のSlackイベントに応答します：

- `app_mention` - ボットがメンションされたとき
- `message.im` - ボットにDMが送信されたとき

どちらのイベントでも、ボットは「こんにちは」と返信します。

## 実装の特徴

- **イベント重複防止**: イベントIDを使用して重複処理を防止
- **ボットメッセージの無視**: ボット自身のメッセージには反応しない
- **非同期処理**: スレッドを使用してイベント処理を非同期で実行
- **即時応答**: Slackの要件（3秒以内に応答）を満たすための最適化
