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
            bedrock_client: InlineBedrockClient instance
            event_retention_period (int): How long to retain event IDs (seconds)
            logger: Logger instance (optional)
        """
        self.slack_client = slack_client
        self.bedrock_client = bedrock_client
        self.event_retention_period = event_retention_period
        self.logger = logger or setup_logger(__name__)
        self.processed_events = set()
        self.converter = Convert()
        self.logger.info("SlackService initialized with InlineAgent")
    
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
        # シンプルなローディングブロックを作成
        loading_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":hourglass_flowing_sand: *処理中です...*"
                }
            }
        ]
        
        # 処理開始時にローディングメッセージを送信
        result = self.slack_client.send_message(
            channel=channel,
            text="処理中です...",  # フォールバックテキスト
            thread_ts=thread_ts,
            blocks=loading_blocks
        )
        
        # タイムスタンプを取得
        temp_ts = result.get("ts") if result.get("success") else None
        
        try:
            # スレッドメッセージを取得して会話コンテキストを構築
            thread_messages = self.slack_client.get_thread_messages(channel, thread_ts)
            conversation_context = self._build_conversation_context(thread_messages)
            
            self.logger.info("Generating response using Bedrock with InlineAgent")
            response = self.bedrock_client.generate_response(conversation_context)
            slack_response = self.converter.markdown_to_slack_format(response)
            
            # 処理完了後にメッセージを更新
            if temp_ts:
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
                        # 長いメッセージを更新
                        self.slack_client.update_long_message(
                            channel=channel,
                            ts=temp_ts,
                            text=slack_response
                        )
                    else:
                        # その他のエラーの場合
                        error_message = update_result.get("error")
                        self.logger.error(f"Error updating message: {error_message}")
                        
                        # エラーメッセージを表示
                        error_blocks = [
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": f":warning: *エラーが発生しました*\n{error_message}"
                                }
                            }
                        ]
                        
                        self.slack_client.update_message(
                            channel=channel,
                            ts=temp_ts,
                            text=f"エラーが発生しました: {error_code}",
                            blocks=error_blocks
                        )
            else:
                # 更新できない場合は新しいメッセージを送信
                self.slack_client.send_long_message(
                    channel=channel,
                    text=slack_response,
                    thread_ts=thread_ts
                )
        except Exception as e:
            self.logger.error(f"Error in _handle_mention: {e}", exc_info=True)
            
            # エラーが発生した場合、ローディングメッセージをエラーメッセージに更新
            if temp_ts:
                error_blocks = [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f":x: *エラーが発生しました*\n```{str(e)}```"
                        }
                    }
                ]
                
                self.slack_client.update_message(
                    channel=channel,
                    ts=temp_ts,
                    text=f"エラーが発生しました: {str(e)}",
                    blocks=error_blocks
                )
    
    def _handle_direct_message(self, channel, thread_ts, is_single_message):
        """Handle direct message events"""
        # シンプルなローディングブロックを作成
        loading_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":hourglass_flowing_sand: *処理中です...*"
                }
            }
        ]
        
        # 処理開始時にローディングメッセージを送信
        result = self.slack_client.send_message(
            channel=channel,
            text="処理中です...",  # フォールバックテキスト
            thread_ts=thread_ts,
            blocks=loading_blocks
        )
        
        # タイムスタンプを取得
        temp_ts = result.get("ts") if result.get("success") else None
        
        try:
            # 処理実行
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
            
            # 処理完了後にメッセージを更新
            if temp_ts:
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
                        # 長いメッセージを更新
                        self.slack_client.update_long_message(
                            channel=channel,
                            ts=temp_ts,
                            text=slack_response
                        )
                    else:
                        # その他のエラーの場合
                        error_message = update_result.get("error")
                        self.logger.error(f"Error updating message: {error_message}")
                        
                        # エラーメッセージを表示
                        error_blocks = [
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": f":warning: *エラーが発生しました*\n{error_message}"
                                }
                            }
                        ]
                        
                        self.slack_client.update_message(
                            channel=channel,
                            ts=temp_ts,
                            text=f"エラーが発生しました: {error_code}",
                            blocks=error_blocks
                        )
            else:
                # 更新できない場合は新しいメッセージを送信
                self.slack_client.send_long_message(
                    channel=channel,
                    text=slack_response,
                    thread_ts=thread_ts
                )
        except Exception as e:
            self.logger.error(f"Error in _handle_direct_message: {e}", exc_info=True)
            
            # エラーが発生した場合、ローディングメッセージをエラーメッセージに更新
            if temp_ts:
                error_blocks = [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f":x: *エラーが発生しました*\n```{str(e)}```"
                        }
                    }
                ]
                
                self.slack_client.update_message(
                    channel=channel,
                    ts=temp_ts,
                    text=f"エラーが発生しました: {str(e)}",
                    blocks=error_blocks
                )
    
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
