from bottle import Bottle, request, response
import json
import time
import os
from slack_sdk.signature import SignatureVerifier
from src.infrastructure.logger import setup_logger

# グローバル変数
app = Bottle()
logger = None
slack_service = None
signature_verifier = None

def error_response(status_code, message, log_message=None, exc_info=False):
    """エラーレスポンスを生成する共通関数"""
    if log_message:
        if status_code >= 500:
            logger.error(log_message, exc_info=exc_info)
        else:
            logger.warning(log_message)
            
    response.status = status_code
    response.content_type = 'application/json'
    return json.dumps({'status': 'error', 'message': message})

@app.hook('after_request')
def enable_cors():
    """CORSを有効にする"""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Origin, Accept, Content-Type, X-Requested-With, X-CSRF-Token'

@app.route('/', method='GET')
def index():
    """ルートエンドポイント"""
    return {'status': 'ok', 'message': 'API is running'}

@app.route('/<:path>', method='OPTIONS')
def options_handler(path=None):
    """OPTIONSリクエストのハンドラ"""
    return {}

@app.route('/default/slack-subscriptions', method='POST')
def slack_events():
    """Slackイベントを処理するエンドポイント"""
    try:
        # リクエスト検証
        if not signature_verifier:
            data = request.json
        else:
            body_raw = request.body.read()
            body = body_raw.decode('utf-8')
            
            timestamp = request.headers.get("X-Slack-Request-Timestamp") or request.headers.get("x-slack-request-timestamp")
            signature = request.headers.get("X-Slack-Signature") or request.headers.get("x-slack-signature")
            
            if not timestamp or not signature:
                return error_response(
                    403, 
                    'Missing verification headers',
                    f"Missing Slack verification headers: timestamp={bool(timestamp)}, signature={bool(signature)}"
                )
            
            current_time = int(time.time())
            if abs(current_time - int(timestamp)) > 60 * 5:
                return error_response(
                    403, 
                    'Request expired',
                    f"Expired Slack request: timestamp={timestamp}, current={current_time}"
                )
            
            if not signature_verifier.is_valid(
                body=body,
                timestamp=timestamp,
                signature=signature
            ):
                return error_response(
                    403, 
                    'Invalid request signature',
                    f"Invalid Slack request signature detected. Remote IP: {request.remote_addr}, Timestamp: {timestamp}"
                )
            
            data = json.loads(body)
        
        # イベント処理
        logger.info(f"Received Slack event type: {data.get('type')}")
        logger.debug(f"Event details: {json.dumps(data, indent=2)}")
        
        if "challenge" in data:
            logger.info("Responding to Slack verification challenge")
            return {"challenge": data["challenge"]}
        
        if data.get("type") == "event_callback":
            logger.info(f"Processing event callback: {data.get('event', {}).get('type')}")
            slack_service.handle_event(data)
        
        return {}
        
    except Exception as e:
        return error_response(400, str(e), f"Error processing Slack event: {e}", exc_info=True)

@app.error(404)
def error404(error):
    """404エラーハンドラ"""
    return error_response(404, 'Not found', f"404 error: {request.url}")

@app.error(500)
def error500(error):
    """500エラーハンドラ"""
    return error_response(500, 'Internal server error', f"500 error: {error}", exc_info=True)

def init_api(slack_service_instance, signing_secret=None, custom_logger=None):
    """APIを初期化する関数"""
    global slack_service, signature_verifier, logger
    
    slack_service = slack_service_instance
    logger = custom_logger or setup_logger(__name__)
    
    if signing_secret:
        signature_verifier = SignatureVerifier(signing_secret)
        logger.info("Slack request signature verification enabled")
    else:
        logger.warning("Slack request signature verification DISABLED - not secure for production!")
        # 本番環境では署名検証を必須にする
        if os.environ.get('ENVIRONMENT', 'development').lower() == 'production':
            raise ValueError("Slack signing secret is required in production environment")
    
    logger.info("API initialized")
    return app
