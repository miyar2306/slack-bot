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
    
    def send_message(self, channel, text, thread_ts=None, blocks=None):
        """
        Send a message to a specified channel
        
        Args:
            channel (str): Channel ID to send message to
            text (str): Message text to send
            thread_ts (str, optional): Thread timestamp (for replies)
            blocks (list, optional): Block Kit blocks
            
        Returns:
            dict or False: Response data if successful, False otherwise
        """
        try:
            self.logger.info(f"Sending message to channel {channel}")
            params = {
                "channel": channel,
                "text": text,
            }
            
            if thread_ts:
                params["thread_ts"] = thread_ts
                
            if blocks:
                params["blocks"] = blocks
                
            response = self.client.chat_postMessage(**params)
            return response
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
    
    def update_message(self, channel, ts, text=None, blocks=None):
        """
        Update an existing message
        
        Args:
            channel (str): Channel ID
            ts (str): Timestamp of the message to update
            text (str, optional): New message text
            blocks (list, optional): New Block Kit blocks
            
        Returns:
            dict or False: Response data if successful, False otherwise
        """
        try:
            self.logger.info(f"Updating message in channel {channel}")
            params = {
                "channel": channel,
                "ts": ts,
            }
            
            if text:
                params["text"] = text
                
            if blocks:
                params["blocks"] = blocks
                
            response = self.client.chat_update(**params)
            return response
        except SlackApiError as e:
            self.logger.error(f"Error updating message: {e}")
            return False
