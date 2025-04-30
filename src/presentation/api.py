from bottle import Bottle, request, response
import json
import time
import os
from slack_sdk.signature import SignatureVerifier
from src.infrastructure.logger import setup_logger

class SlackAPI:
    
    def __init__(self, slack_service, signing_secret=None, logger=None):
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
        self.app.add_hook('after_request', self._enable_cors)
        
        self.app.route('/', method='GET', callback=self._index)
        self.app.route('/<:path>', method='OPTIONS', callback=self._options_handler)
        self.app.route('/default/slack-subscriptions', method='POST', callback=self._slack_events)
        
        self.app.error(404)(self._error404)
        self.app.error(500)(self._error500)
    
    def _enable_cors(self):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Origin, Accept, Content-Type, X-Requested-With, X-CSRF-Token'
    
    def _options_handler(self, path=None):
        return {}
    
    def _index(self):
        return {'status': 'ok', 'message': 'API is running'}
    
    def _verify_slack_request(self):
        if not self.signature_verifier:
            return request.json
            
        body_raw = request.body.read()
        body = body_raw.decode('utf-8')
        
        timestamp = request.headers.get("X-Slack-Request-Timestamp") or request.headers.get("x-slack-request-timestamp")
        signature = request.headers.get("X-Slack-Signature") or request.headers.get("x-slack-signature")
        
        if not timestamp or not signature:
            return self._error_response(
                403, 
                'Missing verification headers',
                f"Missing Slack verification headers: timestamp={bool(timestamp)}, signature={bool(signature)}"
            )
        
        current_time = int(time.time())
        if abs(current_time - int(timestamp)) > 60 * 5:
            return self._error_response(
                403, 
                'Request expired',
                f"Expired Slack request: timestamp={timestamp}, current={current_time}"
            )
        
        if not self.signature_verifier.is_valid(
            body=body,
            timestamp=timestamp,
            signature=signature
        ):
            return self._error_response(
                403, 
                'Invalid request signature',
                f"Invalid Slack request signature detected. Remote IP: {request.remote_addr}, Timestamp: {timestamp}"
            )
        
        return json.loads(body)
    
    def _slack_events(self):
        try:
            data = self._verify_slack_request()
            
            if isinstance(data, dict) and 'status' in data and data['status'] == 'error':
                return data
            
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
            return self._error_response(400, str(e), f"Error processing Slack event: {e}", exc_info=True)
    
    def _error_response(self, status_code, message, log_message=None, exc_info=False):
        if log_message:
            if status_code >= 500:
                self.logger.error(log_message, exc_info=exc_info)
            else:
                self.logger.warning(log_message)
                
        response.status = status_code
        response.content_type = 'application/json'
        return json.dumps({'status': 'error', 'message': message})
    
    def _error404(self, error):
        return self._error_response(404, 'Not found', f"404 error: {request.url}")
    
    def _error500(self, error):
        return self._error_response(500, 'Internal server error', f"500 error: {error}", exc_info=True)
    
    def get_app(self):
        return self.app
