from bottle import Bottle, request, response
import json
from src.infrastructure.logger import setup_logger

class SlackAPI:
    """Provides Slack API endpoints using Bottle framework"""
    
    def __init__(self, slack_service, logger=None):
        """
        Initialize SlackAPI
        
        Args:
            slack_service: SlackService instance
            logger: Logger instance (optional)
        """
        self.slack_service = slack_service
        self.logger = logger or setup_logger(__name__)
        self.app = Bottle()
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
