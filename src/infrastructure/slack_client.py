from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from src.infrastructure.logger import setup_logger

class SlackClient:
    """Handles communication with Slack API"""
    
    def __init__(self, token, logger=None):
        """
        Initialize SlackClient
        
        Args:
            token (str): Slack API token
            logger: Logger instance (optional)
        """
        self.client = WebClient(token=token)
        self.logger = logger or setup_logger(__name__)
    
    def send_message(self, channel, text, thread_ts=None):
        """
        Send a message to a specified channel
        
        Args:
            channel (str): Channel ID to send message to
            text (str): Message text to send
            thread_ts (str, optional): Thread timestamp (for replies)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.logger.info(f"Sending message to channel {channel}")
            self.client.chat_postMessage(
                channel=channel,
                text=text,
                thread_ts=thread_ts
            )
            return True
        except SlackApiError as e:
            self.logger.error(f"Error sending message: {e}")
            return False
    
    def get_thread_messages(self, channel, thread_ts):
        """
        Get all messages in a thread
        
        Args:
            channel (str): Channel ID
            thread_ts (str): Thread timestamp
            
        Returns:
            list: List of messages in the thread (chronological order)
        """
        try:
            self.logger.debug(f"Getting thread messages from channel {channel}, thread {thread_ts}")
            response = self.client.conversations_replies(
                channel=channel,
                ts=thread_ts
            )
            
            messages = response.get('messages', [])
            self.logger.debug(f"Retrieved {len(messages)} messages from thread")
            return messages
        except SlackApiError as e:
            self.logger.error(f"Error getting thread messages: {e}")
            return []
