from bottle import Bottle, request, response
import json

class SlackAPI:
    """Bottleを使用したSlack APIエンドポイントを提供するクラス"""
    
    def __init__(self, slack_service):
        """
        SlackAPIの初期化
        
        Args:
            slack_service: SlackServiceインスタンス
        """
        self.slack_service = slack_service
        self.app = Bottle()
        self._setup_routes()
    
    def _setup_routes(self):
        """ルーティングの設定"""
        # CORSミドルウェア
        self.app.add_hook('after_request', self._enable_cors)
        
        # ルート設定
        self.app.route('/', method='GET', callback=self._index)
        self.app.route('/<:path>', method='OPTIONS', callback=self._options_handler)
        self.app.route('/default/slack-subscriptions', method='POST', callback=self._slack_events)
        
        # エラーハンドリング
        self.app.error(404)(self._error404)
        self.app.error(500)(self._error500)
    
    def _enable_cors(self):
        """CORSミドルウェア"""
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Origin, Accept, Content-Type, X-Requested-With, X-CSRF-Token'
    
    def _options_handler(self, path=None):
        """OPTIONSリクエストへの対応"""
        return {}
    
    def _index(self):
        """ルートエンドポイント"""
        return {'status': 'ok', 'message': 'API is running'}
    
    def _slack_events(self):
        """Slackイベントの処理"""
        try:
            data = request.json
            print(f"Received event: {json.dumps(data, indent=2)}")  # 詳細なデバッグ出力
            
            # Slack APIの検証チャレンジに応答
            if "challenge" in data:
                return {"challenge": data["challenge"]}
            
            # イベントコールバックの処理
            if data.get("type") == "event_callback":
                self.slack_service.handle_event(data)
            
            # 即座に成功レスポンスを返す
            return {}
            
        except Exception as e:
            response.status = 400
            return {'status': 'error', 'message': str(e)}
    
    def _error404(self, error):
        """404エラーハンドラ"""
        response.content_type = 'application/json'
        return json.dumps({'status': 'error', 'message': 'Not found'})
    
    def _error500(self, error):
        """500エラーハンドラ"""
        response.content_type = 'application/json'
        return json.dumps({'status': 'error', 'message': 'Internal server error'})
    
    def get_app(self):
        """Bottleアプリケーションインスタンスを取得"""
        return self.app
