import boto3
import asyncio
import json
import functools
from typing import Dict, Any, List, Union, Optional, Set

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from InlineAgent.tools import MCPStdio
from InlineAgent.action_group import ActionGroup
from InlineAgent.agent import InlineAgent

from .logger import setup_logger

def ensure_async_loop(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(func(self, *args, **kwargs))
    return wrapper

def error_handler(func):
    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except Exception as e:
            self.logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
            return f"Error: {str(e)}"
    return wrapper

class InlineBedrockClient:
    """InlineAgentを使用してAmazon Bedrockとの通信を処理するクライアント"""
    
    def __init__(self, region_name, config_file_path="config/mcp_servers.json", max_recursion_depth=5, profile="default", logger=None):
        self.logger = logger or setup_logger(__name__)
        self.client = boto3.client('bedrock-runtime', region_name=region_name)
        self.profile = profile
        self.model_id = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
        self.config_file_path = config_file_path
        self.MAX_RECURSION_DEPTH = max_recursion_depth
        self.action_groups = []
        self.mcp_clients = {}
        
        # 非同期ループを初期化
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
        # MCP設定を読み込み
        self.mcp_config = self._load_mcp_config()
    
    def _load_mcp_config(self):
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
    
    async def initialize_inline_agent(self):
        """InlineAgentの初期化"""
        # MCPクライアントとActionGroupの初期化
        for server_name, server_config in self.mcp_config.items():
            if isinstance(server_config, dict) and 'command' in server_config:
                await self._initialize_mcp_client_and_create_action_group(server_name, server_config)
    
    @error_handler
    async def _initialize_mcp_client_and_create_action_group(self, server_name, server_config):
        """MCPクライアントの初期化とActionGroupの作成を一括で行う"""
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
            
            
            # クライアントを保存
            self.mcp_clients[server_name] = mcp_client
            
            # ActionGroupを作成
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
        except Exception as e:
            self.logger.error(f"Error initializing MCP client for {server_name}: {e}")
    
    
    @ensure_async_loop
    async def generate_response(self, message_or_conversation):
        """メッセージまたは会話履歴に対するレスポンスを生成"""
        # システムプロンプトの準備
        system_text = self._load_system_prompt()
        
        # 入力テキストの準備
        if isinstance(message_or_conversation, str):
            input_text = message_or_conversation
        elif isinstance(message_or_conversation, list):
            # 会話履歴をテキストに変換
            input_text = self._convert_conversation_to_text(message_or_conversation)
        else:
            raise ValueError("Invalid input format")
        
        # InlineAgentの作成と実行
        agent = InlineAgent(
            # モデルを指定
            foundation_model=self.model_id,
            # システムプロンプトを指定
            instruction=system_text,
            # エージェント名とプロファイルを指定
            agent_name="slack_bot_agent",
            profile=self.profile,
            # ActionGroupを指定
            action_groups=self.action_groups
        )

        agent.profile = None
        
        # エージェントを実行
        response = await agent.invoke(input_text=input_text)
        return response
    
    def _convert_conversation_to_text(self, conversation):
        """会話履歴をテキストに変換"""
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
