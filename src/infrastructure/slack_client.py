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
            self.client.chat_postMessage(
                channel=channel,
                text=text,
                thread_ts=thread_ts
            )
            return True
        except SlackApiError as e:
            print(f"Error sending message: {e}")
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
            # conversations.repliesエンドポイントを使用してスレッド内のメッセージを取得
            response = self.client.conversations_replies(
                channel=channel,
                ts=thread_ts
            )
            
            # メッセージのリストを返す（最初のメッセージを含む）
            return response.get('messages', [])
        except SlackApiError as e:
            print(f"Error getting thread messages: {e}")
            return []
