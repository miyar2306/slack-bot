import boto3
import asyncio
import json
import functools
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from typing import Dict, Any, List, Union, TypedDict
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
            if "tool_result" in func.__name__:
                tool_request = args[0] if args else kwargs.get("tool_request")
                return {
                    'toolResult': {
                        'toolUseId': tool_request['toolUseId'] if tool_request else "unknown",
                        'content': [{'text': f"Error: {str(e)}"}],
                        'status': 'error'
                    }
                }
            return f"Error: {str(e)}"
    return wrapper

class ToolInfo(TypedDict):
    description: str
    input_schema: Dict
    original_name: str
    server_name: str
    original_tool_name: str
    timeout: float

class BedrockClient:
    """Amazon Bedrockとの通信を処理するクライアント"""
    
    def __init__(self, region_name, config_file_path="config/mcp_servers.json", max_recursion_depth=5, logger=None):
        self.logger = logger or setup_logger(__name__)
        self.client = boto3.client('bedrock-runtime', region_name=region_name)
        self.model_id = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
        self.config_file_path = config_file_path
        self._tools = {}
        self.MAX_RECURSION_DEPTH = max_recursion_depth
        
        # 非同期ループを初期化
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
        # MCP設定を読み込み、サーバーを初期化
        self.mcp_config = self._load_mcp_config()
        self.loop.run_until_complete(self.initialize_mcp_servers())
    
    def _load_mcp_config(self):
        try:
            with open(self.config_file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Error loading MCP configuration: {e}")
            return {"mcp_servers": []}
    
    @error_handler
    async def initialize_mcp_servers(self):
        for server_config in self.mcp_config.get('mcp_servers', []):
            await self._initialize_server(server_config)
    
    @error_handler
    async def _initialize_server(self, server_config):
        name = server_config.get('name')
        command = server_config.get('command')
        args = server_config.get('args', [])
        env = server_config.get('env')
        
        if not name or not command:
            self.logger.error("Invalid server configuration")
            return
        
        # サーバーセッションを作成してツールを登録
        server_params = StdioServerParameters(command=command, args=args, env=env)
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                
                # ツールリストを取得
                tools = []
                if hasattr(tools_result, 'tools'):
                    tools = tools_result.tools
                elif isinstance(tools_result, dict) and 'tools' in tools_result:
                    tools = tools_result['tools']
                elif isinstance(tools_result, list):
                    tools = tools_result
                
                # ツールを登録
                for tool in tools:
                    try:
                        prefixed_name = f"{name}_{tool.name}"
                        self.register_tool(
                            name=prefixed_name,
                            description=f"[{name}] {tool.description}",
                            input_schema=tool.inputSchema,
                            server_name=name,
                            original_tool_name=tool.name
                        )
                    except Exception as e:
                        self.logger.error(f"Error registering tool: {e}")
    
    @ensure_async_loop
    async def generate_response(self, message_or_conversation):
        """メッセージまたは会話履歴に対するレスポンスを生成"""
        return await self._generate_response_async(message_or_conversation)
    
    @error_handler
    async def _generate_response_async(self, message_or_conversation):
        messages, system, tool_config = self._prepare_request_data(message_or_conversation)
        return await self._make_bedrock_request(messages, system, tool_config)
    
    def _prepare_request_data(self, message_or_conversation):
        # メッセージの準備
        if isinstance(message_or_conversation, str):
            messages = [{"role": "user", "content": [{"text": message_or_conversation}]}]
        elif isinstance(message_or_conversation, list):
            messages = message_or_conversation
        else:
            raise ValueError("Invalid input format")
        
        # システムプロンプトの準備
        system_text = "You are a helpful AI assistant. Speak in Japanese"
        if self._tools:
            system_text += " You have access to the following tools:\n\n"
            system_text += "\n".join(f"- {name}: {tool['description']}" for name, tool in self._tools.items())
        
        system = [{"text": system_text}]
        
        # ツール設定の準備
        tool_specs = []
        for name, tool in self._tools.items():
            safe_name = self._get_safe_tool_name(name)
            tool_specs.append({
                "toolSpec": {
                    "name": safe_name,
                    "description": tool['description'],
                    "inputSchema": {"json": tool['input_schema']}
                }
            })
        
        return messages, system, {"tools": tool_specs}
    
    def _get_safe_tool_name(self, name):
        safe_name = ''.join(c if c.isalnum() or c in ['_', '-'] else '_' for c in name)
        
        if len(safe_name) <= 64:
            return safe_name
            
        parts = safe_name.split('_', 1)
        if len(parts) > 1:
            server_prefix = parts[0][:20]
            remaining_space = 64 - len(server_prefix) - 1
            tool_part = parts[1][-remaining_space:] if len(parts[1]) > remaining_space else parts[1]
            return f"{server_prefix}_{tool_part}"
        
        return safe_name[:64]
    
    def _normalize_name(self, name):
        return name.replace('-', '_').replace('.', '_')
        
    def register_tool(self, name, description, input_schema, server_name, original_tool_name, timeout=30.0):
        """ツールを登録"""
        normalized_name = self._normalize_name(name)
        self._tools[normalized_name] = {
            'description': description,
            'input_schema': input_schema,
            'original_name': name,
            'server_name': server_name,
            'original_tool_name': original_tool_name,
            'timeout': timeout
        }
        self.logger.info(f"Registered tool: {name}")
    
    def _get_server_config(self, server_name):
        for srv in self.mcp_config.get('mcp_servers', []):
            if srv.get('name') == server_name:
                return srv
        raise ValueError(f"Server configuration not found for: {server_name}")
    
    @error_handler
    async def _make_bedrock_request(self, messages, system, tool_config, recursion_depth=0):
        if recursion_depth >= self.MAX_RECURSION_DEPTH:
            return await self._generate_final_response(messages, system)
        
        response = self.client.converse(
            modelId=self.model_id,
            messages=messages,
            system=system,
            inferenceConfig={"maxTokens": 5000, "topP": 0.1, "temperature": 0.3},
            toolConfig=tool_config
        )
        
        stop_reason = response.get('stopReason')
        
        if stop_reason in ['end_turn', 'stop_sequence']:
            return self._extract_text_response(response)
        elif stop_reason == 'tool_use':
            return await self._handle_tool_use(response, messages, recursion_depth)
        elif stop_reason == 'max_tokens':
            return await self._handle_max_tokens(response, messages, recursion_depth)
        else:
            return f"Unknown stop reason: {stop_reason}"
    
    def _extract_text_response(self, response):
        output_message = response['output']['message']
        response_text = ""
        for content in output_message['content']:
            if 'text' in content:
                response_text += content['text'] + "\n"
        
        return response_text.strip()
    
    @error_handler
    async def _handle_tool_use(self, response, messages, recursion_depth=0):
        if recursion_depth >= self.MAX_RECURSION_DEPTH:
            return await self._generate_final_response(messages, self._prepare_request_data(messages)[1])
            
        tool_response = []
        
        for content_item in response['output']['message']['content']:
            if 'toolUse' in content_item:
                tool_request = {
                    "toolUseId": content_item['toolUse']['toolUseId'],
                    "name": content_item['toolUse']['name'],
                    "input": content_item['toolUse']['input']
                }
                
                tool_result = await self._execute_tool(tool_request)
                tool_response.append(tool_result)
        
        messages.append(response['output']['message'])
        messages.append({"role": "user", "content": tool_response})
        
        _, system, tool_config = self._prepare_request_data(messages)
        return await self._make_bedrock_request(messages, system, tool_config, recursion_depth + 1)
    
    @error_handler
    async def _execute_tool(self, tool_request):
        tool_name = tool_request['name']
        
        normalized_name = self._normalize_name(tool_name)
        if normalized_name not in self._tools:
            raise ValueError(f"Unknown tool: {normalized_name}")
            
        tool_info = self._tools[normalized_name]
        server_name = tool_info.get('server_name')
        original_tool_name = tool_info.get('original_tool_name', tool_name)
        
        result = await self._call_tool_with_direct_session(
            server_name=server_name,
            tool_name=original_tool_name,
            arguments=tool_request['input']
        )
        
        return {
            'toolResult': {
                'toolUseId': tool_request['toolUseId'],
                'content': [{'text': str(result)}],
                'status': 'success'
            }
        }
    
    @error_handler
    async def _call_tool_with_direct_session(self, server_name, tool_name, arguments, timeout=30.0):
        server_config = self._get_server_config(server_name)
        
        server_params = StdioServerParameters(
            command=server_config.get('command'),
            args=server_config.get('args', []),
            env=server_config.get('env')
        )
        
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await asyncio.wait_for(
                    session.call_tool(tool_name, arguments=arguments),
                    timeout=timeout
                )
    
    @error_handler
    async def _generate_final_response(self, messages, system):
        final_instruction = {
            "role": "user",
            "content": [{"text": "Please generate a final response based on the information collected so far. Do not make additional tool calls."}]
        }
        messages.append(final_instruction)
        
        _, _, tool_config = self._prepare_request_data(messages)
        response = self.client.converse(
            modelId=self.model_id,
            messages=messages,
            system=system,
            inferenceConfig={"maxTokens": 5000, "topP": 0.1, "temperature": 0.3},
            toolConfig=tool_config
        )
        
        return self._extract_text_response(response)
    
    @error_handler
    async def _handle_max_tokens(self, response, messages, recursion_depth=0):
        messages.append(response['output']['message'])
        messages.append({
            "role": "user",
            "content": [{"text": "Please continue."}]
        })
        
        _, system, tool_config = self._prepare_request_data(messages)
        return await self._make_bedrock_request(messages, system, tool_config, recursion_depth + 1)
