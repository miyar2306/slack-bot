import boto3
import json
import asyncio
from .tool_manager import ToolManager
from .logger import setup_logger

class BedrockClient:
    """Amazon Bedrockとの通信を担当するクラス"""
    
    def __init__(self, region_name, mcp_server_manager=None, logger=None):
        """
        BedrockClientの初期化
        
        Args:
            region_name (str): AWSリージョン名
            mcp_server_manager: MCPServerManagerインスタンス
            logger: Logger instance (optional)
        """
        self.logger = logger or setup_logger(__name__)
        self.logger.info(f"Initializing BedrockClient with region: {region_name}")
        
        # IAMロールを使用して認証（認証情報の明示的な指定は不要）
        self.client = boto3.client('bedrock-runtime', region_name=region_name)
        self.model_id = "us.amazon.nova-pro-v1:0"  # Novaモデル
        
        # MCP関連の設定
        self.mcp_server_manager = mcp_server_manager
        self.tool_manager = mcp_server_manager.get_tool_manager() if mcp_server_manager else ToolManager()
        self.logger.info("BedrockClient initialized")
    
    def generate_response(self, message_or_conversation):
        """
        メッセージまたは会話履歴に対する応答を生成
        
        Args:
            message_or_conversation: 単一のメッセージ（文字列）または会話履歴（辞書のリスト）
            
        Returns:
            str: 生成された応答
        """
        self.logger.debug("Generating response")
        
        # 非同期処理を同期的に実行
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # イベントループがない場合は新しく作成
            self.logger.debug("Creating new event loop")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(self._generate_response_async(message_or_conversation))
    
    async def _generate_response_async(self, message_or_conversation):
        """
        メッセージまたは会話履歴に対する応答を非同期で生成
        
        Args:
            message_or_conversation: 単一のメッセージ（文字列）または会話履歴（辞書のリスト）
            
        Returns:
            str: 生成された応答
        """
        # 入力が文字列の場合（単一のメッセージ）
        if isinstance(message_or_conversation, str):
            self.logger.debug("Processing single message input")
            messages = [{
                "role": "user",
                "content": [{"text": message_or_conversation}]
            }]
        # 入力がリストの場合（会話履歴）
        elif isinstance(message_or_conversation, list):
            self.logger.debug(f"Processing conversation history with {len(message_or_conversation)} messages")
            messages = message_or_conversation
        else:
            self.logger.error(f"Invalid input type: {type(message_or_conversation)}")
            return "Error: Invalid input format."
        
        # システムプロンプトの作成
        system_text = "You are a helpful AI assistant."
        
        # ツールの説明をシステムプロンプトに追加
        if hasattr(self, 'tool_manager') and self.tool_manager:
            # ツール情報を直接取得（内部の_toolsから）
            if self.tool_manager._tools:
                self.logger.debug(f"Adding {len(self.tool_manager._tools)} tools to system prompt")
                system_text += " You have access to the following tools:\n\n"
                for name, tool_info in self.tool_manager._tools.items():
                    system_text += f"- {name}: {tool_info['description']}\n"
        else:
            system_text += " You have access to the following tools: Speak in Japanese"
        
        system = [{"text": system_text}]
        self.logger.debug("System prompt prepared")
        
        try:
            # ツール設定を準備
            tool_config = {}
            if hasattr(self, 'tool_manager') and self.tool_manager:
                # get_toolsメソッドが直接正しい形式を返すようになったため、
                # そのまま使用できる
                tool_config = self.tool_manager.get_tools()
                self.logger.debug(f"Tool config prepared with {len(tool_config.get('tools', []))} tools")
            
            # converseメソッドを使用
            self.logger.info(f"Calling Bedrock with model: {self.model_id}")
            response = self.client.converse(
                modelId=self.model_id,
                messages=messages,
                system=system,
                inferenceConfig={
                    "maxTokens": 300,
                    "topP": 0.1,
                    "temperature": 0.3
                },
                toolConfig=tool_config
            )
            self.logger.debug("Received response from Bedrock")
            
            # 応答の理由に基づいて処理を分岐
            stop_reason = response.get('stopReason')
            self.logger.info(f"Response stop reason: {stop_reason}")
            
            if stop_reason in ['end_turn', 'stop_sequence']:
                # 通常の応答
                output_message = response['output']['message']
                response_text = ""
                for content in output_message['content']:
                    if 'text' in content:
                        response_text += content['text'] + "\n"
                
                # 応答テキストを抽出
                self.logger.debug("Extracted text response")
                return response_text.strip()
                
            elif stop_reason == 'tool_use':
                # ツール使用の場合
                self.logger.info("Model requested tool use")
                tool_response = []
                for content_item in response['output']['message']['content']:
                    if 'toolUse' in content_item:
                        tool_request = {
                            "toolUseId": content_item['toolUse']['toolUseId'],
                            "name": content_item['toolUse']['name'],
                            "input": content_item['toolUse']['input']
                        }
                        
                        # ツールを実行
                        try:
                            self.logger.info(f"Executing tool: {tool_request['name']}")
                            tool_result = await self.tool_manager.execute_tool(
                                tool_request['name'], 
                                tool_request['input']
                            )
                            
                            self.logger.debug(f"Tool execution successful")
                            tool_response.append({
                                'toolResult': {
                                    'toolUseId': tool_request['toolUseId'],
                                    'content': [{
                                        'text': str(tool_result)
                                    }],
                                    'status': 'success'
                                }
                            })
                        except Exception as e:
                            self.logger.error(f"Tool execution error: {e}", exc_info=True)
                            tool_response.append({
                                'toolResult': {
                                    'toolUseId': tool_request['toolUseId'],
                                    'content': [{
                                        'text': f"Tool execution error: {str(e)}"
                                    }],
                                    'status': 'error'
                                }
                            })
                
                # ツール結果を含めて再度リクエスト
                messages.append(response['output']['message'])
                messages.append({
                    "role": "user",
                    "content": tool_response
                })
                
                self.logger.info("Making recursive call with tool results")
                # 再帰的に呼び出し
                return await self._generate_response_async(messages)
                
            elif stop_reason == 'max_tokens':
                # トークン制限に達した場合
                self.logger.info("Max tokens reached, continuing generation")
                messages.append(response['output']['message'])
                messages.append({
                    "role": "user",
                    "content": [{"text": "Please continue."}]
                })
                
                # 再帰的に呼び出し
                return await self._generate_response_async(messages)
                
            else:
                self.logger.warning(f"Unknown stop reason: {stop_reason}")
                return f"Unknown stop reason: {stop_reason}"
                
        except Exception as e:
            self.logger.error(f"Error generating response: {e}", exc_info=True)
            return "Sorry, an error occurred while generating the response."
