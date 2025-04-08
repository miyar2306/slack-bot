from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

class SlackClient:
    """Slack APIとの通信を担当するクラス"""
    
    def __init__(self, token):
        """
        SlackClientの初期化
        
        Args:
            token (str): Slack APIトークン
        """
        self.client = WebClient(token=token)
    
    def send_message(self, channel, text):
        """
        指定したチャンネルにメッセージを送信
        
        Args:
            channel (str): メッセージ送信先のチャンネルID
            text (str): 送信するメッセージテキスト
            
        Returns:
            bool: 送信成功時はTrue、失敗時はFalse
        """
        try:
            self.client.chat_postMessage(
                channel=channel,
                text=text
            )
            return True
        except SlackApiError as e:
            print(f"Error sending message: {e}")
            return False
