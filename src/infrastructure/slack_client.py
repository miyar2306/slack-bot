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
            dict: Response data with success status and error information if applicable
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
            return {"success": True, "response": response, "ts": response.get("ts")}
        except SlackApiError as e:
            error_code = getattr(e.response, "data", {}).get("error", "unknown_error")
            self.logger.error(f"Error sending message: {e}")
            return {"success": False, "error": str(e), "error_code": error_code}
    
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
            dict: Response data with success status and error information if applicable
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
            return {"success": True, "response": response}
        except SlackApiError as e:
            error_code = getattr(e.response, "data", {}).get("error", "unknown_error")
            self.logger.error(f"Error updating message: {e}")
            return {"success": False, "error": str(e), "error_code": error_code}
    
    def _split_message(self, text, max_length=3900):
        """
        Split a message into parts that fit within Slack's message length limit
        
        Args:
            text (str): Message text to split
            max_length (int): Maximum length of each part
            
        Returns:
            list: List of message parts
        """
        parts = []
        while text:
            if len(text) <= max_length:
                parts.append(text)
                break
            
            # 最大長で区切り、できれば改行で分割
            split_point = text.rfind('\n', 0, max_length)
            if split_point == -1:  # 改行がない場合は単純に最大長で分割
                split_point = max_length
            
            parts.append(text[:split_point])
            text = text[split_point:].lstrip()
        
        return parts
    
    def send_long_message(self, channel, text, thread_ts=None, blocks=None):
        """
        Send a message that might exceed Slack's message length limit
        
        Args:
            channel (str): Channel ID to send message to
            text (str): Message text to send
            thread_ts (str, optional): Thread timestamp (for replies)
            blocks (list, optional): Block Kit blocks
            
        Returns:
            dict: Response data with success status and timestamps of sent messages
        """
        # テキストが短い場合は通常の送信を試みる
        if len(text) <= 3900:
            return self.send_message(channel, text, thread_ts, blocks)
        
        # 長いメッセージを分割
        message_parts = self._split_message(text)
        sent_messages = []
        
        # 分割したメッセージを順番に送信
        for i, part in enumerate(message_parts):
            prefix = f"[{i+1}/{len(message_parts)}] " if len(message_parts) > 1 else ""
            result = self.send_message(
                channel=channel,
                text=prefix + part,
                thread_ts=thread_ts
            )
            
            if not result.get("success"):
                return {
                    "success": False, 
                    "error": f"Failed to send part {i+1}/{len(message_parts)}: {result.get('error')}",
                    "error_code": result.get("error_code"),
                    "sent_messages": sent_messages
                }
            
            sent_messages.append(result.get("ts"))
        
        return {
            "success": True,
            "message": f"Sent {len(message_parts)} message parts",
            "sent_messages": sent_messages
        }
    
    def update_long_message(self, channel, ts, text, blocks=None):
        """
        Update a message that might exceed Slack's message length limit
        
        Args:
            channel (str): Channel ID
            ts (str): Timestamp of the message to update
            text (str): New message text
            blocks (list, optional): New Block Kit blocks
            
        Returns:
            dict: Response data with success status
        """
        # テキストが短い場合は通常の更新を試みる
        if len(text) <= 3900:
            return self.update_message(channel, ts, text, blocks)
        
        # 長いメッセージの場合、元のメッセージを更新して分割メッセージを送信
        update_result = self.update_message(
            channel=channel,
            ts=ts,
            text="メッセージが長いため、複数のメッセージに分割します。"
        )
        
        if not update_result.get("success"):
            return update_result
        
        # スレッド情報を取得
        thread_ts = ts
        
        # 長いメッセージを送信
        return self.send_long_message(channel, text, thread_ts)
