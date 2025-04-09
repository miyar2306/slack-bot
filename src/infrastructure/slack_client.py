from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from src.infrastructure.logger import setup_logger

class SlackClient:
    """Slack APIとの通信を担当するクラス"""
    
    def __init__(self, token, logger=None):
        """
        SlackClientの初期化
        
        Args:
            token (str): Slack APIトークン
            logger: Logger instance (optional)
        """
        self.client = WebClient(token=token)
        self.logger = logger or setup_logger(__name__)
    
    def send_message(self, channel, text, thread_ts=None):
        """
        指定したチャンネルにメッセージを送信
        
        Args:
            channel (str): メッセージ送信先のチャンネルID
            text (str): 送信するメッセージテキスト
            thread_ts (str, optional): スレッドのタイムスタンプ（スレッドに返信する場合）
            
        Returns:
            bool: 送信成功時はTrue、失敗時はFalse
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
        指定したスレッド内の全メッセージを取得
        
        Args:
            channel (str): チャンネルID
            thread_ts (str): スレッドのタイムスタンプ
            
        Returns:
            list: スレッド内のメッセージのリスト（古い順）
        """
        try:
            self.logger.debug(f"Getting thread messages from channel {channel}, thread {thread_ts}")
            # conversations.repliesエンドポイントを使用してスレッド内のメッセージを取得
            response = self.client.conversations_replies(
                channel=channel,
                ts=thread_ts
            )
            
            # メッセージのリストを返す（最初のメッセージを含む）
            messages = response.get('messages', [])
            self.logger.debug(f"Retrieved {len(messages)} messages from thread")
            return messages
        except SlackApiError as e:
            self.logger.error(f"Error getting thread messages: {e}")
            return []
