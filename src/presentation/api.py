from bottle import Bottle, request, response
import json
import time
import os
from slack_sdk.signature import SignatureVerifier
from src.infrastructure.logger import setup_logger

class SlackAPI:
    """Provides Slack API endpoints using Bottle framework"""
    
    def __init__(self, slack_service, signing_secret=None, logger=None):
        """
        Initialize SlackAPI
        
        Args:
            slack_service: SlackService instance
            signing_secret: Slack Signing Secret for request verification
            logger: Logger instance (optional)
        """
        self.slack_service = slack_service
        self.logger = logger or setup_logger(__name__)
        self.app = Bottle()
        self.signature_verifier = None
        
        if signing_secret:
            self.signature_verifier = SignatureVerifier(signing_secret)
            self.logger.info("Slack request signature verification enabled")
        else:
            self.logger.warning("Slack request signature verification DISABLED - not secure for production!")
            # 本番環境では署名検証を必須にする
            if os.environ.get('ENVIRONMENT', 'development').lower() == 'production':
                raise ValueError("Slack signing secret is required in production environment")
                
        self._setup_routes()
        self.logger.info("SlackAPI initialized")
    
    def _setup_routes(self):
        """Set up API routes"""
        self.app.add_hook('after_request', self._enable_cors)
        
        self.app.route('/', method='GET', callback=self._index)
        self.app.route('/<:path>', method='OPTIONS', callback=self._options_handler)
        self.app.route('/default/slack-subscriptions', method='POST', callback=self._slack_events)
        
        self.app.error(404)(self._error404)
        self.app.error(500)(self._error500)
    
    def _enable_cors(self):
        """Enable CORS middleware"""
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Origin, Accept, Content-Type, X-Requested-With, X-CSRF-Token'
    
    def _options_handler(self, path=None):
        """Handle OPTIONS requests"""
        return {}
    
    def _index(self):
        """Root endpoint"""
        return {'status': 'ok', 'message': 'API is running'}
    
    def _slack_events(self):
        """Process Slack events"""
        try:
            # リクエスト検証を実装
            if self.signature_verifier:
                # リクエストボディを一度だけ読み込む
                body_raw = request.body.read()
                body = body_raw.decode('utf-8')
                
                # リクエストヘッダーからタイムスタンプと署名を取得
                timestamp = request.headers.get("X-Slack-Request-Timestamp") or request.headers.get("x-slack-request-timestamp")
                signature = request.headers.get("X-Slack-Signature") or request.headers.get("x-slack-signature")
                
                if not timestamp or not signature:
                    self.logger.warning(f"Missing Slack verification headers: timestamp={bool(timestamp)}, signature={bool(signature)}")
                    response.status = 403
                    return {'status': 'error', 'message': 'Missing verification headers'}
                
                # タイムスタンプの検証（5分以上経過したリクエストは拒否）
                current_time = int(time.time())
                if abs(current_time - int(timestamp)) > 60 * 5:
                    self.logger.warning(f"Expired Slack request: timestamp={timestamp}, current={current_time}")
                    response.status = 403
                    return {'status': 'error', 'message': 'Request expired'}
                
                # 署名を検証
                if not self.signature_verifier.is_valid(
                    body=body,
                    timestamp=timestamp,
                    signature=signature
                ):
                    self.logger.warning(
                        f"Invalid Slack request signature detected. "
                        f"Remote IP: {request.remote_addr}, "
                        f"Timestamp: {timestamp}"
                    )
                    response.status = 403
                    return {'status': 'error', 'message': 'Invalid request signature'}
                
                # ボディからJSONをパース
                data = json.loads(body)
            else:
                # 署名検証なしの場合は直接request.jsonを使用
                data = request.json
            
            self.logger.info(f"Received Slack event type: {data.get('type')}")
            self.logger.debug(f"Event details: {json.dumps(data, indent=2)}")
            
            if "challenge" in data:
                self.logger.info("Responding to Slack verification challenge")
                return {"challenge": data["challenge"]}
            
            if data.get("type") == "event_callback":
                self.logger.info(f"Processing event callback: {data.get('event', {}).get('type')}")
                self.slack_service.handle_event(data)
            
            return {}
            
        except Exception as e:
            self.logger.error(f"Error processing Slack event: {e}", exc_info=True)
            response.status = 400
            return {'status': 'error', 'message': str(e)}
    
    def _error404(self, error):
        """Handle 404 errors"""
        self.logger.warning(f"404 error: {request.url}")
        response.content_type = 'application/json'
        return json.dumps({'status': 'error', 'message': 'Not found'})
    
    def _error500(self, error):
        """Handle 500 errors"""
        self.logger.error(f"500 error: {error}", exc_info=True)
        response.content_type = 'application/json'
        return json.dumps({'status': 'error', 'message': 'Internal server error'})
    
    def get_app(self):
        """Get Bottle application instance"""
        return self.app
