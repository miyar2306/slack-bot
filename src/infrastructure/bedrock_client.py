import boto3
import json
import asyncio
from mcp import StdioServerParameters
from .mcp_client import MCPClient
from .tool_manager import ToolManager

class BedrockClient:
    """Amazon Bedrockとの通信を担当するクラス"""
    
    def __init__(self, region_name, mcp_server_command=None, mcp_server_args=None, mcp_server_env=None):
        """
        BedrockClientの初期化
        
        Args:
            region_name (str): AWSリージョン名
            mcp_server_command (str, optional): MCPサーバーコマンド
            mcp_server_args (list, optional): MCPサーバー引数
            mcp_server_env (dict, optional): MCPサーバー環境変数
        """
        # IAMロールを使用して認証（認証情報の明示的な指定は不要）
        self.client = boto3.client('bedrock-runtime', region_name=region_name)
        self.model_id = "us.amazon.nova-pro-v1:0"  # Novaモデル
        
        # MCP関連の設定
        self.mcp_server_command = mcp_server_command
        self.mcp_server_args = mcp_server_args
        self.mcp_server_env = mcp_server_env
        self.tool_manager = ToolManager()
        self.mcp_client = None
        
        # MCPサーバーが設定されている場合は初期化
        if self.mcp_server_command and self.mcp_server_args:
            # 非同期タスクを作成（実際の初期化は別のスレッドで行う）
            asyncio.create_task(self._initialize_mcp())
    
    async def _initialize_mcp(self):
        """MCPクライアントを初期化し、利用可能なツールを登録"""
        try:
            server_params = StdioServerParameters(
                command=self.mcp_server_command,
                args=self.mcp_server_args,
                env=self.mcp_server_env
            )
            
            self.mcp_client = MCPClient(server_params)
            await self.mcp_client.connect()
            
            # 利用可能なツールを取得して登録
            tools = await self.mcp_client.get_available_tools()
            for tool in tools:
                self.tool_manager.register_tool(
                    name=tool.name,
                    func=self.mcp_client.call_tool,
                    description=tool.description,
                    input_schema=tool.inputSchema
                )
            
            print(f"MCPサーバーに接続し、{len(tools)}個のツールを登録しました")
        except Exception as e:
            print(f"MCPサーバーの初期化エラー: {e}")
    
    def generate_response(self, message_or_conversation):
        """
        メッセージまたは会話履歴に対する応答を生成
        
        Args:
            message_or_conversation: 単一のメッセージ（文字列）または会話履歴（辞書のリスト）
            
        Returns:
            str: 生成された応答
        """
        # 非同期処理を同期的に実行
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # イベントループがない場合は新しく作成
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
            messages = [{
                "role": "user",
                "content": [{"text": message_or_conversation}]
            }]
        # 入力がリストの場合（会話履歴）
        elif isinstance(message_or_conversation, list):
            messages = message_or_conversation
        else:
            return "エラー: 無効な入力形式です。"
        
        # システムプロンプトの作成
        system_text = "You are a helpful AI assistant."
        
        # ツールの説明をシステムプロンプトに追加
        if hasattr(self, 'tool_manager') and self.tool_manager:
            tools = self.tool_manager.get_tools()
            if tools:
                system_text += " You have access to the following tools:\n\n"
                for tool in tools:
                    system_text += f"- {tool['name']}: {tool['description']}\n"
        else:
            system_text += " You have access to the following tools: Speak in Japanese"
        
        system = [{"text": system_text}]
        
        try:
            # ツール設定を準備
            tool_config = {}
            if hasattr(self, 'tool_manager') and self.tool_manager:
                tools = self.tool_manager.get_tools()
                if tools:
                    tool_config = {"tools": tools}
            
            # converseメソッドを使用
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
            
            # 応答の理由に基づいて処理を分岐
            stop_reason = response.get('stopReason')
            
            if stop_reason in ['end_turn', 'stop_sequence']:
                # 通常の応答
                output_message = response['output']['message']
                response_text = ""
                for content in output_message['content']:
                    if 'text' in content:
                        response_text += content['text'] + "\n"
                
                # 応答テキストを抽出
                return response_text.strip()
                
            elif stop_reason == 'tool_use':
                # ツール使用の場合
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
                            tool_result = await self.tool_manager.execute_tool(
                                tool_request['name'], 
                                tool_request['input']
                            )
                            
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
                            tool_response.append({
                                'toolResult': {
                                    'toolUseId': tool_request['toolUseId'],
                                    'content': [{
                                        'text': f"ツール実行エラー: {str(e)}"
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
                
                # 再帰的に呼び出し
                return await self._generate_response_async(messages)
                
            elif stop_reason == 'max_tokens':
                # トークン制限に達した場合
                messages.append(response['output']['message'])
                messages.append({
                    "role": "user",
                    "content": [{"text": "続けてください。"}]
                })
                
                # 再帰的に呼び出し
                return await self._generate_response_async(messages)
                
            else:
                return f"不明な停止理由: {stop_reason}"
                
        except Exception as e:
            print(f"Error generating response: {e}")
            return "すみません、応答の生成中にエラーが発生しました。"
