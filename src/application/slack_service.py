import threading
import re
from src.infrastructure.logger import setup_logger
from markdown2slack.app import Convert

class SlackService:
    """Business logic for processing Slack events"""
    
    def __init__(self, slack_client, bedrock_client, event_retention_period=3600, logger=None):
        """
        Initialize SlackService
        
        Args:
            slack_client: SlackClient instance
            bedrock_client: BedrockClient instance
            event_retention_period (int): How long to retain event IDs (seconds)
            logger: Logger instance (optional)
        """
        self.slack_client = slack_client
        self.bedrock_client = bedrock_client
        self.event_retention_period = event_retention_period
        self.logger = logger or setup_logger(__name__)
        self.processed_events = set()
        self.converter = Convert()
        self.logger.info("SlackService initialized")
    
    def handle_event(self, event_data):
        """
        Process a Slack event
        
        Args:
            event_data (dict): Slack event data
            
        Returns:
            bool: True if processing successful, False otherwise
        """
        try:
            event_id = event_data.get("event_id")
            
            if event_id in self.processed_events:
                self.logger.info(f"Duplicate event detected: {event_id}")
                return True
            
            self.processed_events.add(event_id)
            
            if len(self.processed_events) > 1000:
                self.logger.info("Clearing processed events cache (size > 1000)")
                self.processed_events.clear()
            
            event = event_data.get("event", {})
            
            if "bot_id" in event:
                self.logger.info(f"Ignoring bot message: {event.get('bot_id')}")
                return True
            
            threading.Thread(target=self._process_event, args=(event,)).start()
            return True
            
        except Exception as e:
            self.logger.error(f"Error handling event: {e}", exc_info=True)
            return False
    
    def _process_event(self, event):
        """
        Process event based on type (runs in separate thread)
        
        Args:
            event (dict): Slack event
        """
        try:
            event_type = event.get("type")
            channel = event.get("channel")
            
            self.logger.info(f"Processing event type: {event_type} in channel: {channel}")
            
            # Get thread timestamp (either direct or from parent)
            thread_ts = event.get("thread_ts") or event.get("ts")
            
            if event_type == "app_mention":
                self._handle_mention(channel, thread_ts)
            elif event_type == "message" and event.get("channel_type") == "im":
                self._handle_direct_message(channel, thread_ts, event.get("thread_ts") is None)
        
        except Exception as e:
            self.logger.error(f"Error processing event: {e}", exc_info=True)
    
    def _handle_mention(self, channel, thread_ts):
        """Handle app_mention events"""
        thread_messages = self.slack_client.get_thread_messages(channel, thread_ts)
        conversation_context = self._build_conversation_context(thread_messages)
        
        self.logger.info("Generating response using Bedrock")
        response = self.bedrock_client.generate_response(conversation_context)
        slack_response = self.converter.markdown_to_slack_format(response)
        
        self.slack_client.send_message(channel, slack_response, thread_ts=thread_ts)
    
    def _handle_direct_message(self, channel, thread_ts, is_single_message):
        """Handle direct message events"""
        if is_single_message:
            self.logger.debug("Processing single DM message")
            message_text = self._clean_mention(thread_ts)
            response = self.bedrock_client.generate_response(message_text)
            slack_response = self.converter.markdown_to_slack_format(response)
        else:
            thread_messages = self.slack_client.get_thread_messages(channel, thread_ts)
            conversation_context = self._build_conversation_context(thread_messages)
            response = self.bedrock_client.generate_response(conversation_context)
            slack_response = self.converter.markdown_to_slack_format(response)
        
        self.slack_client.send_message(channel, slack_response, thread_ts=thread_ts)
    
    def _build_conversation_context(self, messages):
        """
        Build conversation context from thread messages
        
        Args:
            messages (list): List of messages in thread
            
        Returns:
            list: Conversation history formatted for Bedrock Converse API
        """
        conversation = []
        
        for message in messages:
            text = message.get("text", "")
            clean_text = self._clean_mention(text)
            
            if clean_text:
                role = "assistant" if message.get("bot_id") else "user"
                conversation.append({
                    "role": role,
                    "content": [{"text": clean_text}]
                })
        
        return conversation
    
    def _clean_mention(self, text):
        """
        Remove mention tags from message text
        
        Args:
            text (str): Original message text
            
        Returns:
            str: Text with mentions removed
        """
        return re.sub(r'<@[A-Z0-9]+>', '', text).strip()
