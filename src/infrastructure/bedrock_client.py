import boto3
import asyncio
import json
import functools
import re
from typing import Dict, Any, List, Union, Optional, Set

from mcp import StdioServerParameters
from InlineAgent.tools import MCPStdio
from InlineAgent.action_group import ActionGroup
from InlineAgent.agent import InlineAgent

from .logger import setup_logger

def ensure_async_loop(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        loop = self._get_or_create_event_loop()
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

class BedrockClient:
    def __init__(self, region_name: str, config_file_path: str = "config/mcp_servers.json", logger = None):
        self.logger = logger or setup_logger(__name__)
        self.model_id = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
        self.config_file_path = config_file_path
        self.action_groups = []
        self.mcp_clients = {}
        
        self.mcp_config = self._load_mcp_config()
    
    def _get_or_create_event_loop(self):
        try:
            return asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop
    
    def _load_mcp_config(self) -> Dict:
        try:
            with open(self.config_file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Error loading MCP configuration: {e}")
            return {}
    
    def _load_system_prompt(self) -> str:
        system_prompt_file = "system_prompt.md"
        try:
            with open(system_prompt_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            self.logger.warning(f"Failed to load system prompt file: {e}")
            return "You are a helpful AI assistant. Speak in Japanese"
    
    @ensure_async_loop
    async def initialize_mcp_services(self):
        """MCPサービス（クライアントとアクショングループ）を初期化する"""
        for server_name, server_config in self.mcp_config.items():
            if isinstance(server_config, dict) and 'command' in server_config:
                await self._initialize_mcp_client_and_create_action_group(server_name, server_config)
    
    @error_handler
    async def _initialize_mcp_client_and_create_action_group(self, server_name: str, server_config: Dict):
        command = server_config.get('command')
        args = server_config.get('args', [])
        env = server_config.get('env')
        
        if not command:
            self.logger.error(f"Invalid server configuration for {server_name}")
            return
        
        server_params = StdioServerParameters(command=command, args=args, env=env)
        
        try:
            mcp_client = await MCPStdio.create(server_params=server_params)
            self.mcp_clients[server_name] = mcp_client
            await self._create_action_group(server_name, mcp_client)
        except Exception as e:
            self.logger.error(f"Error initializing MCP client for {server_name}: {e}")
    
    def _sanitize_action_group_name(self, name: str) -> str:
        """
        ActionGroupNameを正規表現パターン ([0-9a-zA-Z][_-]?){1,100} に合わせて加工する
        """
        # 英数字、アンダースコア、ハイフン以外の文字を削除
        sanitized_name = re.sub(r'[^0-9a-zA-Z_\-]', '', name)
        
        # 名前が空の場合はデフォルト名を使用
        if not sanitized_name:
            sanitized_name = "DefaultActionGroup"
            
        # 100文字を超える場合は切り詰める
        if len(sanitized_name) > 100:
            sanitized_name = sanitized_name[:100]
            
        return sanitized_name
    
    def _truncate_description(self, description: str, max_length: int = 1200) -> str:
        """
        説明文を指定された最大長に制限する
        """
        if len(description) <= max_length:
            return description
            
        # 最大長を超える場合は切り詰めて「...」を追加
        return description[:max_length-3] + "..."
    
    def _process_function_schema(self, function_schema: Dict) -> Dict:
        """
        関数スキーマの説明文を制限する
        """
        if "functions" in function_schema:
            for function in function_schema["functions"]:
                if "description" in function:
                    function["description"] = self._truncate_description(function["description"])
                    
                if "parameters" in function:
                    for param_name, param_details in function["parameters"].items():
                        if "description" in param_details:
                            param_details["description"] = self._truncate_description(param_details["description"])
                            
        return function_schema
    
    async def _create_action_group(self, server_name: str, mcp_client):
        try:
            # server_nameを正規表現パターンに合わせて加工
            sanitized_name = self._sanitize_action_group_name(server_name)
            
            action_group = ActionGroup(
                name=f"{sanitized_name}ActionGroup",
                description=self._truncate_description(f"Tools provided by {server_name} MCP server"),
                mcp_clients=[mcp_client]
            )
            
            # MCPクライアントから取得した関数スキーマを処理
            if hasattr(mcp_client, "function_schema"):
                mcp_client.function_schema = self._process_function_schema(mcp_client.function_schema)
                
            self.action_groups.append(action_group)
            self.logger.info(f"Created action group for {server_name}")
        except Exception as e:
            self.logger.error(f"Error creating action group for {server_name}: {e}")
            await mcp_client.cleanup()
            self.mcp_clients.pop(server_name, None)
    
    @ensure_async_loop
    async def generate_response(self, input_data: Union[str, List[Dict]]) -> str:
        system_text = self._load_system_prompt()
        input_text = self._process_input_data(input_data)
        
        agent = InlineAgent(
            foundation_model=self.model_id,
            instruction=system_text,
            agent_name="slack_bot_agent",
            profile=None,
            action_groups=self.action_groups
        )
        
        return await agent.invoke(input_text=input_text)
    
    def _process_input_data(self, input_data: Union[str, List[Dict]]) -> str:
        if isinstance(input_data, str):
            return input_data
        elif isinstance(input_data, list):
            if all(isinstance(item, dict) and "text" in item for item in input_data):
                conversation = self.create_conversation_history_from_messages(input_data)
                return self._convert_conversation_to_text(conversation)
            elif all(isinstance(item, dict) and "role" in item for item in input_data):
                return self._convert_conversation_to_text(input_data)
            else:
                raise ValueError("Invalid message format")
        else:
            raise ValueError("Invalid input format")
    
    def create_conversation_history_from_messages(self, messages: List[Dict]) -> List[Dict]:
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
    
    def _convert_conversation_to_text(self, conversation: List[Dict]) -> str:
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
            
            prefix = "User: " if role == "user" else "Assistant: "
            result.append(f"{prefix}{text}")
        
        return "\n\n".join(result)
    
    @ensure_async_loop
    async def cleanup_mcp_clients(self):
        for server_name, mcp_client in list(self.mcp_clients.items()):
            try:
                await mcp_client.cleanup()
                self.logger.info(f"Cleaned up MCP client for {server_name}")
            except Exception as e:
                self.logger.error(f"Error cleaning up MCP client for {server_name}: {e}")
            finally:
                self.mcp_clients.pop(server_name, None)
