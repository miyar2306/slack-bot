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

# 特定アイテムの取得
@app.route('/api/items/<item_id:int>', method='GET')
def get_item(item_id):
    # サンプルデータ（実際のアプリケーションではデータベースなどから取得）
    items = {
        1: {'id': 1, 'name': 'Item 1', 'description': 'Description for item 1'},
        2: {'id': 2, 'name': 'Item 2', 'description': 'Description for item 2'},
        3: {'id': 3, 'name': 'Item 3', 'description': 'Description for item 3'}
    }
    
    if item_id in items:
        return {'status': 'success', 'data': items[item_id]}
    else:
        response.status = 404
        return {'status': 'error', 'message': f'Item with id {item_id} not found'}

# POSTリクエストの処理例
@app.route('/api/items', method='POST')
def create_item():
    try:
        data = request.json
        
        # バリデーション
        if not data or not 'name' in data:
            response.status = 400
            return {'status': 'error', 'message': 'Name is required'}
            
        # ここでデータを処理・保存（実際のアプリケーションではデータベースなどに保存）
        # サンプルレスポンス
        new_item = {
            'id': 4,  # 実際のアプリケーションでは自動生成
            'name': data['name'],
            'description': data.get('description', '')
        }
        
        return {'status': 'success', 'message': 'Item created', 'data': new_item}
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
