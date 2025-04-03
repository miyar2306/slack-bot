from bottle import Bottle, run, request, response
import json
import os

# アプリケーションインスタンスの作成
app = Bottle()

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

# ルートエンドポイント
@app.route('/', method='GET')
def index():
    return {'status': 'ok', 'message': 'API is running'}

# サンプルAPIエンドポイント - GETリクエスト
@app.route('/api/items', method='GET')
def get_items():
    # サンプルデータ（実際のアプリケーションではデータベースなどから取得）
    items = [
        {'id': 1, 'name': 'Item 1', 'description': 'Description for item 1'},
        {'id': 2, 'name': 'Item 2', 'description': 'Description for item 2'},
        {'id': 3, 'name': 'Item 3', 'description': 'Description for item 3'}
    ]
    return {'status': 'success', 'data': items}

# POSTリクエストの処理例
@app.route('/default/slack-subscriptions', method='POST')
def create_item():
    try:
        data = request.json
        print(data)
        
        challenge = data.get("challenge","")
        return {challenge}
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
