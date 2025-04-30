import boto3
import asyncio
import json
import functools
from typing import Dict, Any, List, Union, Optional, Set

from mcp import StdioServerParameters
from InlineAgent.tools import MCPStdio
from InlineAgent.action_group import ActionGroup
from InlineAgent.agent import InlineAgent

from .logger import setup_logger

def ensure_async_loop(func):
    """非同期関数を同期的に実行するためのデコレータ"""
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        loop = self._get_or_create_event_loop()
        return loop.run_until_complete(func(self, *args, **kwargs))
    return wrapper

def error_handler(func):
    """非同期関数のエラーハンドリングを行うデコレータ"""
    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except Exception as e:
            self.logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
            return f"Error: {str(e)}"
    return wrapper

class BedrockClient:
    """Amazon Bedrockとの通信を処理するクライアント"""
    
    def __init__(self, region_name, config_file_path="config/mcp_servers.json", max_recursion_depth=5, profile="default", logger=None):
        """
        BedrockClientの初期化
        
        Args:
            region_name (str): AWS リージョン名
            config_file_path (str): MCP設定ファイルのパス
            max_recursion_depth (int): 最大再帰深度
            profile (str): AWSプロファイル名
            logger: ロガーインスタンス
        """
        self.logger = logger or setup_logger(__name__)
        self.client = boto3.client('bedrock-runtime', region_name=region_name)
        self.profile = profile
        self.model_id = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
        self.config_file_path = config_file_path
        self.max_recursion_depth = max_recursion_depth
        self.action_groups = []
        self.mcp_clients = {}
        
        # MCP設定を読み込み
        self.mcp_config = self._load_mcp_config()
    
    def _get_or_create_event_loop(self):
        """イベントループを取得または作成"""
        try:
            return asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop
    
    def _load_mcp_config(self):
        """MCP設定ファイルを読み込む"""
        try:
            with open(self.config_file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Error loading MCP configuration: {e}")
            return {}
    
    def _load_system_prompt(self):
        """マークダウンファイルからシステムプロンプトを読み込む"""
        system_prompt_file = "system_prompt.md"  # 固定ファイル名
        try:
            with open(system_prompt_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            self.logger.warning(f"システムプロンプトファイルの読み込みに失敗しました: {e}")
            return "You are a helpful AI assistant. Speak in Japanese"
    
    @ensure_async_loop
    async def initialize_inline_agent(self):
        """MCPクライアントとActionGroupの初期化"""
        for server_name, server_config in self.mcp_config.items():
            if isinstance(server_config, dict) and 'command' in server_config:
                await self._initialize_mcp_client_and_create_action_group(server_name, server_config)
    
    @error_handler
    async def _initialize_mcp_client_and_create_action_group(self, server_name, server_config):
        """MCPクライアントの初期化とActionGroupの作成を行う"""
        command = server_config.get('command')
        args = server_config.get('args', [])
        env = server_config.get('env')
        
        if not command:
            self.logger.error(f"Invalid server configuration for {server_name}")
            return
        
        # MCPサーバーのパラメータを設定
        server_params = StdioServerParameters(command=command, args=args, env=env)
        
        try:
            # MCPクライアントを作成
            mcp_client = await MCPStdio.create(server_params=server_params)
            self.mcp_clients[server_name] = mcp_client
            
            # ActionGroupを作成
            await self._create_action_group(server_name, mcp_client)
        except Exception as e:
            self.logger.error(f"Error initializing MCP client for {server_name}: {e}")
    
    async def _create_action_group(self, server_name, mcp_client):
        """ActionGroupを作成"""
        try:
            action_group = ActionGroup(
                name=f"{server_name}ActionGroup",
                description=f"Tools provided by {server_name} MCP server",
                mcp_clients=[mcp_client]
            )
            self.action_groups.append(action_group)
            self.logger.info(f"Created action group for {server_name}")
        except Exception as e:
            self.logger.error(f"Error creating action group for {server_name}: {e}")
            # ActionGroup作成に失敗した場合はクライアントをクリーンアップ
            await mcp_client.cleanup()
            self.mcp_clients.pop(server_name, None)
    
    @ensure_async_loop
    async def generate_response(self, input_data):
        """
        メッセージまたは会話履歴に対するレスポンスを生成
        
        Args:
            input_data: 文字列、メッセージリスト、または会話履歴
            
        Returns:
            str: 生成されたレスポンス
            
        Raises:
            ValueError: 入力データの形式が無効な場合
        """
        # システムプロンプトの準備
        system_text = self._load_system_prompt()
        
        # 入力データを処理してテキストに変換
        input_text = self._process_input_data(input_data)
        
        # InlineAgentの作成と実行
        agent = InlineAgent(
            foundation_model=self.model_id,
            instruction=system_text,
            agent_name="slack_bot_agent",
            profile=self.profile,
            action_groups=self.action_groups
        )
        agent.profile = None
        
        # エージェントを実行
        response = await agent.invoke(input_text=input_text)
        return response
    
    def _process_input_data(self, input_data):
        """
        入力データを処理してテキストに変換
        
        Args:
            input_data: 文字列、メッセージリスト、または会話履歴
            
        Returns:
            str: 変換されたテキスト
            
        Raises:
            ValueError: 入力データの形式が無効な場合
        """
        if isinstance(input_data, str):
            # 文字列の場合はそのまま使用
            return input_data
        elif isinstance(input_data, list):
            if all(isinstance(item, dict) and "text" in item for item in input_data):
                # Slackメッセージリストの場合は会話履歴に変換
                conversation = self.create_conversation_history_from_messages(input_data)
                return self._convert_conversation_to_text(conversation)
            elif all(isinstance(item, dict) and "role" in item for item in input_data):
                # 既に会話履歴形式の場合はテキストに変換
                return self._convert_conversation_to_text(input_data)
            else:
                raise ValueError("Invalid message format")
        else:
            raise ValueError("Invalid input format")
    
    def create_conversation_history_from_messages(self, messages):
        """
        Slackメッセージから会話履歴を作成
        
        Args:
            messages (List[Dict]): Slackメッセージのリスト
            
        Returns:
            List[Dict]: 会話履歴
        """
        conversation = []
        
        for message in messages:
            text = message.get("text", "")
            
            if text:
                role = "assistant" if message.get("bot_id") else "user"
                conversation.append({
                    "role": role,
                    "content": [{"text": text}]
                })
        
        return conversation
    
    def _convert_conversation_to_text(self, conversation):
        """
        会話履歴をテキストに変換
        
        Args:
            conversation (List[Dict]): 会話履歴
            
        Returns:
            str: 変換されたテキスト
        """
        result = []
        for message in conversation:
            role = message.get("role", "")
            content = message.get("content", [])
            
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and "text" in item:
                        text_parts.append(item["text"])
                text = "\n".join(text_parts)
            else:
                text = str(content)
            
            prefix = "ユーザー: " if role == "user" else "アシスタント: "
            result.append(f"{prefix}{text}")
        
        return "\n\n".join(result)
    
    @ensure_async_loop
    async def cleanup_mcp_clients(self):
        """MCPクライアントのクリーンアップ"""
        for server_name, mcp_client in list(self.mcp_clients.items()):
            try:
                await mcp_client.cleanup()
                self.logger.info(f"Cleaned up MCP client for {server_name}")
            except Exception as e:
                self.logger.error(f"Error cleaning up MCP client for {server_name}: {e}")
            finally:
                # クリーンアップ後は辞書から削除
                self.mcp_clients.pop(server_name, None)
