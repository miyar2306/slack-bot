import time
import threading
import re

class SlackService:
    """Slackイベント処理のビジネスロジックを担当するクラス"""
    
    def __init__(self, slack_client, bedrock_client, event_retention_period=3600):
        """
        SlackServiceの初期化
        
        Args:
            slack_client: SlackClientインスタンス
            bedrock_client: BedrockClientインスタンス
            event_retention_period (int): イベントIDの保持期間（秒）
        """
        self.slack_client = slack_client
        self.bedrock_client = bedrock_client
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
                # メッセージのテキストとタイムスタンプを取得
                message_text = event.get("text", "")
                thread_ts = event.get("ts")
                
                # スレッドの親メッセージかスレッド内のメッセージかを判断
                parent_ts = event.get("thread_ts")
                
                if parent_ts:
                    # スレッド内のメッセージの場合、親のタイムスタンプを使用
                    thread_ts = parent_ts
                
                # スレッド内の全メッセージを取得
                thread_messages = self.slack_client.get_thread_messages(channel, thread_ts)
                
                # スレッド内のメッセージから会話の文脈を構築
                conversation_context = self._build_conversation_context(thread_messages)
                
                # Bedrockを使用して応答を生成（会話の文脈を含める）
                response = self.bedrock_client.generate_response(conversation_context)
                
                # スレッドで返信
                self.slack_client.send_message(channel, response, thread_ts=thread_ts)
            
            # DMメッセージイベントの処理
            elif event_type == "message" and event.get("channel_type") == "im":
                message_text = event.get("text", "")
                thread_ts = event.get("thread_ts")
                
                if thread_ts:
                    # スレッド内のメッセージの場合、スレッド内の全メッセージを取得
                    thread_messages = self.slack_client.get_thread_messages(channel, thread_ts)
                    conversation_context = self._build_conversation_context(thread_messages)
                    response = self.bedrock_client.generate_response(conversation_context)
                else:
                    # 通常のDMの場合、単一のメッセージのみを処理
                    response = self.bedrock_client.generate_response(message_text)
                
                # 返信（スレッド内のメッセージの場合はスレッドで返信）
                self.slack_client.send_message(channel, response, thread_ts=thread_ts)
        
        except Exception as e:
            print(f"Error processing event: {e}")
    
    def _build_conversation_context(self, messages):
        """
        スレッド内のメッセージから会話の文脈を構築
        
        Args:
            messages (list): スレッド内のメッセージのリスト
            
        Returns:
            list: Bedrock Converse APIに適した形式の会話履歴
        """
        conversation = []
        
        for message in messages:
            text = message.get("text", "")
            
            # メンション部分を削除
            clean_text = self._clean_mention(text)
            
            if clean_text:
                # ボットのメッセージかユーザーのメッセージかを判断
                if message.get("bot_id"):
                    conversation.append({
                        "role": "assistant",
                        "content": [{"text": clean_text}]
                    })
                else:
                    conversation.append({
                        "role": "user",
                        "content": [{"text": clean_text}]
                    })
        
        return conversation
    
    def _clean_mention(self, text):
        """
        メンション部分を削除してメッセージ内容を抽出
        
        Args:
            text (str): 元のメッセージテキスト
            
        Returns:
            str: メンション部分を削除したテキスト
        """
        # <@USERID> 形式のメンションを削除
        cleaned = re.sub(r'<@[A-Z0-9]+>', '', text).strip()
        return cleaned
