import threading
import re
import json
from src.infrastructure.logger import setup_logger
from markdown2slack.app import Convert

class SlackService:
    """Slackイベント処理のビジネスロジック"""
    
    def __init__(self, slack_client, bedrock_client, event_retention_period=3600, logger=None):
        """SlackServiceの初期化"""
        self.slack_client = slack_client
        self.bedrock_client = bedrock_client
        self.event_retention_period = event_retention_period
        self.logger = logger or setup_logger(__name__)
        self.processed_events = set()
        self.converter = Convert()
        self.logger.info("SlackService initialized with InlineAgent")
    
    def handle_event(self, event_data):
        """Slackイベントを処理"""
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
            
            # スレッドを使用せず、直接イベントを処理
            self._dispatch_event(event)
            return True
            
        except Exception as e:
            self.logger.error(f"Error handling event: {e}", exc_info=True)
            return False
    
    def _dispatch_event(self, event):
        """イベントタイプに基づいて適切なハンドラに振り分け"""
        try:
            event_type = event.get("type")
            channel = event.get("channel")
            
            self.logger.info(f"Processing event type: {event_type} in channel: {channel}")
            
            # スレッドのタイムスタンプを取得（直接またはペアレントから）
            thread_ts = event.get("thread_ts") or event.get("ts")
            
            if event_type == "app_mention":
                self._handle_mention(channel, thread_ts)
            elif event_type == "message" and event.get("channel_type") == "im":
                self._handle_direct_message(channel, thread_ts, event.get("thread_ts") is None)
        
        except Exception as e:
            self.logger.error(f"Error processing event: {e}", exc_info=True)
    
    def _handle_mention(self, channel, thread_ts):
        """メンションイベントを処理"""
        try:
            # スレッドメッセージを取得
            thread_messages = self.slack_client.get_thread_messages(channel, thread_ts)
            
            # メンションタグを削除
            cleaned_messages = self._clean_messages(thread_messages)
            
            self.logger.info("Generating response using Bedrock with InlineAgent")
            # クリーニングしたメッセージを直接BedrockClientに渡す
            self.logger.debug(f"BedrockClientに渡すメッセージ(メンション): {json.dumps(cleaned_messages, ensure_ascii=False, indent=2)}")
            response = self.bedrock_client.generate_response(cleaned_messages)
            
            # 共通の応答処理メソッドを使用
            self._process_response(channel, thread_ts, response)
        except Exception as e:
            self.logger.error(f"Error in _handle_mention: {e}", exc_info=True)
    
    def _handle_direct_message(self, channel, thread_ts, is_single_message):
        """ダイレクトメッセージイベントを処理"""
        try:
            # 処理実行
            if is_single_message:
                self.logger.debug("Processing single DM message")
                # スレッドタイムスタンプではなく、メッセージを取得する必要がある
                messages = self.slack_client.get_thread_messages(channel, thread_ts)
                if messages and len(messages) > 0:
                    message = messages[0]  # 最初のメッセージを取得
                    
                    # 通常のテキストを処理
                    text = message.get("text", "")
                    clean_text = self._process_slack_formatting(text)
                    
                    # blocksフィールドから追加情報を抽出
                    blocks_text = self._extract_text_from_blocks(message.get("blocks", []))
                    if blocks_text:
                        self.logger.debug(f"単一DMのblocksから抽出したテキスト: {blocks_text}")
                        if clean_text:
                            clean_text = f"{clean_text}\n\n{blocks_text}"
                        else:
                            clean_text = blocks_text
                    
                    # ユーザー名情報を追加
                    user_id = message.get("user")
                    if user_id:
                        user_info = self.slack_client.get_user_info(user_id)
                        if user_info.get("success"):
                            user_name = user_info.get("display_name")
                            clean_text = f"{user_name}: {clean_text}"
                    
                    self.logger.debug(f"BedrockClientに渡すメッセージ(単一DM): {clean_text}")
                    response = self.bedrock_client.generate_response(clean_text)
                else:
                    self.logger.error("No messages found in thread")
                    return
            else:
                thread_messages = self.slack_client.get_thread_messages(channel, thread_ts)
                # メンションタグを削除
                cleaned_messages = self._clean_messages(thread_messages)
                # クリーニングしたメッセージを直接BedrockClientに渡す
                self.logger.debug(f"BedrockClientに渡すメッセージ(スレッドDM): {json.dumps(cleaned_messages, ensure_ascii=False, indent=2)}")
                response = self.bedrock_client.generate_response(cleaned_messages)
            
            # 共通の応答処理メソッドを使用
            self._process_response(channel, thread_ts, response)
        except Exception as e:
            self.logger.error(f"Error in _handle_direct_message: {e}", exc_info=True)
    
    def _clean_messages(self, messages):
        """メッセージリストの各テキストからメンションタグを削除し、ユーザー名情報を追加する"""
        self.logger.debug(f"元のメッセージ: {json.dumps(messages, ensure_ascii=False, indent=2)}")
        
        cleaned_messages = []
        for message in messages:
            # 通常のテキストを処理
            text = message.get("text", "")
            clean_text = self._process_slack_formatting(text)
            
            # blocksフィールドから追加情報を抽出
            blocks_text = self._extract_text_from_blocks(message.get("blocks", []))
            if blocks_text:
                self.logger.debug(f"blocksから抽出したテキスト: {blocks_text}")
                if clean_text:
                    clean_text = f"{clean_text}\n\n{blocks_text}"
                else:
                    clean_text = blocks_text
            
            if clean_text:
                # 元のメッセージをコピーして、テキストだけ置き換える
                cleaned_message = message.copy()
                cleaned_message["text"] = clean_text
                
                # ユーザー名情報を追加
                user_id = message.get("user")
                if user_id and not message.get("bot_id"):
                    user_info = self.slack_client.get_user_info(user_id)
                    if user_info.get("success"):
                        cleaned_message["user_name"] = user_info.get("display_name")
                        self.logger.debug(f"ユーザー名を追加: user_id={user_id}, user_name={user_info.get('display_name')}")
                
                cleaned_messages.append(cleaned_message)
        
        self.logger.debug(f"クリーニング後のメッセージ: {json.dumps(cleaned_messages, ensure_ascii=False, indent=2)}")
        return cleaned_messages
    
    def _extract_text_from_blocks(self, blocks):
        """blocksフィールドからテキスト情報を抽出する"""
        extracted_texts = []
        
        for block in blocks:
            block_type = block.get("type")
            
            # sectionブロックの処理
            if block_type == "section" and "text" in block:
                text_obj = block["text"]
                if text_obj.get("type") == "mrkdwn":
                    extracted_texts.append(self._process_slack_formatting(text_obj.get("text", "")))
            
            # contextブロックの処理
            elif block_type == "context" and "elements" in block:
                for element in block["elements"]:
                    if element.get("type") == "mrkdwn":
                        extracted_texts.append(self._process_slack_formatting(element.get("text", "")))
            
            # rich_textブロックの処理
            elif block_type == "rich_text" and "elements" in block:
                for section in block["elements"]:
                    if section.get("type") == "rich_text_section" and "elements" in section:
                        for element in section["elements"]:
                            if element.get("type") == "text":
                                extracted_texts.append(element.get("text", ""))
        
        return "\n".join(extracted_texts) if extracted_texts else ""
    
    def _process_response(self, channel, thread_ts, response_text):
        """応答テキストを処理してSlackに送信する共通ロジック"""
        # ローディングメッセージの送信
        loading_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":hourglass_flowing_sand: *処理中です...*"
                }
            }
        ]
        
        result = self.slack_client.send_message(
            channel=channel,
            text="処理中です...",
            thread_ts=thread_ts,
            blocks=loading_blocks
        )
        
        temp_ts = result.get("ts") if result.get("success") else None
        
        try:
            # 応答をSlack形式に変換
            slack_response = self.converter.markdown_to_slack_format(response_text)
            
            # メッセージを更新
            if temp_ts:
                self._update_message_with_response(channel, temp_ts, slack_response)
            else:
                # 更新できない場合は新しいメッセージを送信
                self.slack_client.send_long_message(
                    channel=channel,
                    text=slack_response,
                    thread_ts=thread_ts
                )
                
            return {"success": True, "temp_ts": temp_ts}
        except Exception as e:
            self._handle_response_error(channel, temp_ts, e)
            return {"success": False, "error": str(e)}
    
    def _update_message_with_response(self, channel, temp_ts, slack_response):
        """生成した応答でメッセージを更新"""
        update_result = self.slack_client.update_message(
            channel=channel,
            ts=temp_ts,
            text=slack_response
        )
        
        if not update_result.get("success"):
            error_code = update_result.get("error_code")
            
            # メッセージ長超過エラーの場合
            if error_code == "msg_too_long":
                self.logger.info("Message too long, splitting into multiple messages")
                self.slack_client.update_long_message(
                    channel=channel,
                    ts=temp_ts,
                    text=slack_response
                )
            else:
                # その他のエラーの場合
                error_message = update_result.get("error")
                self.logger.error(f"Error updating message: {error_message}")
                
                self._show_error_message(channel, temp_ts, f"エラーが発生しました: {error_code}", error_message)
    
    def _handle_response_error(self, channel, temp_ts, exception):
        """応答処理中のエラーを処理"""
        self.logger.error(f"Error processing response: {exception}", exc_info=True)
        
        if temp_ts:
            self._show_error_message(channel, temp_ts, f"エラーが発生しました: {str(exception)}", str(exception))
    
    def _show_error_message(self, channel, ts, text, error_detail):
        """エラーメッセージを表示"""
        error_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":x: *エラーが発生しました*\n```{error_detail}```"
                }
            }
        ]
        
        self.slack_client.update_message(
            channel=channel,
            ts=ts,
            text=text,
            blocks=error_blocks
        )
    
    def _process_slack_formatting(self, text):
        """Slackの特殊フォーマットを処理する"""
        # メンションタグを削除
        text = re.sub(r'<@[A-Z0-9]+>', '', text)
        
        # URLタグを処理 (<https://example.com|表示テキスト> → https://example.com (表示テキスト))
        text = re.sub(r'<(https?://[^|>]+)\|([^>]+)>', r'\1 (\2)', text)
        
        # リンクテキストのないURLタグを処理 (<https://example.com> → https://example.com)
        text = re.sub(r'<(https?://[^>]+)>', r'\1', text)
        
        return text.strip()
    
    def _remove_mention_tags(self, text):
        """メッセージテキストからメンションタグを削除（後方互換性のため残す）"""
        return self._process_slack_formatting(text)
