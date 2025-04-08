from bottle import Bottle, run, request, response
import json
import os
import threading
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# アプリケーションインスタンスの作成
app = Bottle()

# Slack APIトークンの設定
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "xoxb-your-token")
slack_client = WebClient(token=SLACK_BOT_TOKEN)

# CORSミドルウェア
@app.hook('after_request')
def enable_cors():
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Origin, Accept, Content-Type, X-Requested-With, X-CSRF-Token'

# OPTIONSリクエストへの対応
@app.route('/<:path>', method='OPTIONS')
def options_handler(path=None):
    return {}

# イベント処理関数（別スレッドで実行）
def process_slack_event(event):
    try:
        event_type = event.get("type")
        channel = event.get("channel")
        
        # app_mentionイベントの処理（ボットがメンションされた場合）
        if event_type == "app_mention":
            try:
                slack_client.chat_postMessage(
                    channel=channel,
                    text="こんにちは"
                )
            except SlackApiError as e:
                print(f"Error sending message: {e}")
        
        # DMメッセージイベントの処理
        elif event_type == "message" and event.get("channel_type") == "im":
            try:
                slack_client.chat_postMessage(
                    channel=channel,
                    text="こんにちは"
                )
            except SlackApiError as e:
                print(f"Error sending message: {e}")
    
    except Exception as e:
        print(f"Error processing event: {e}")

# Slackイベントの処理
@app.route('/default/slack-subscriptions', method='POST')
def slack_events():
    try:
        data = request.json
        print(data)  # デバッグ用
        
        # Slack APIの検証チャレンジに応答
        if "challenge" in data:
            return {"challenge": data["challenge"]}
        
        # イベントコールバックの処理
        if data.get("type") == "event_callback":
            event = data.get("event", {})
            
            # 別スレッドでイベント処理を行う
            threading.Thread(target=process_slack_event, args=(event,)).start()
        
        # 即座に成功レスポンスを返す
        return {}
        
    except Exception as e:
        response.status = 400
        return {'status': 'error', 'message': str(e)}

# エラーハンドリング
@app.error(404)
def error404(error):
    response.content_type = 'application/json'
    return json.dumps({'status': 'error', 'message': 'Not found'})

@app.error(500)
def error500(error):
    response.content_type = 'application/json'
    return json.dumps({'status': 'error', 'message': 'Internal server error'})

# サーバー起動
if __name__ == '__main__':
    # 環境変数からポート取得（デプロイ環境用）
    port = int(os.environ.get('PORT', 8080))
    
    # 開発環境ではBottleの内蔵サーバーを使用
    run(app, host='0.0.0.0', port=port, debug=True)
