import time
import threading

class SlackService:
    """Slackイベント処理のビジネスロジックを担当するクラス"""
    
    def __init__(self, slack_client, event_retention_period=3600):
        """
        SlackServiceの初期化
        
        Args:
            slack_client: SlackClientインスタンス
            event_retention_period (int): イベントIDの保持期間（秒）
        """
        self.slack_client = slack_client
        self.event_retention_period = event_retention_period
        
        # 処理済みイベントを追跡するためのセット
        self.processed_events = set()
    
    def handle_event(self, event_data):
        """
        Slackイベントを処理
        
        Args:
            event_data (dict): Slackイベントデータ
            
        Returns:
            bool: 処理成功時はTrue、失敗時はFalse
        """
        try:
            # イベントIDを取得
            event_id = event_data.get("event_id")
            
            # 既に処理したイベントかチェック
            if event_id in self.processed_events:
                print(f"Duplicate event: {event_id}")
                return True
            
            # 処理済みイベントとして記録
            self.processed_events.add(event_id)
            
            # メモリ使用量を制限するため、セットのサイズを制限
            if len(self.processed_events) > 1000:
                # 古いイベントIDを削除（簡易的な実装）
                self.processed_events.clear()
            
            event = event_data.get("event", {})
            
            # ボットメッセージは処理しない
            if "bot_id" in event:
                print(f"Ignoring bot message: {event.get('bot_id')}")
                return True
            
            # 別スレッドでイベント処理を行う
            threading.Thread(target=self._process_event, args=(event,)).start()
            return True
            
        except Exception as e:
            print(f"Error handling event: {e}")
            return False
    
    def _process_event(self, event):
        """
        イベントの種類に応じた処理を実行（別スレッドで実行）
        
        Args:
            event (dict): Slackイベント
        """
        try:
            event_type = event.get("type")
            channel = event.get("channel")
            
            # app_mentionイベントの処理（ボットがメンションされた場合）
            if event_type == "app_mention":
                # メッセージのタイムスタンプを取得してスレッドで返信
                thread_ts = event.get("ts")
                self.slack_client.send_message(channel, "こんにちは", thread_ts=thread_ts)
            
            # DMメッセージイベントの処理
            elif event_type == "message" and event.get("channel_type") == "im":
                self.slack_client.send_message(channel, "こんにちは")
        
        except Exception as e:
            print(f"Error processing event: {e}")
