import boto3
import asyncio
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from typing import Dict, Any, List
from .logger import setup_logger

class BedrockClient:
    """Handles communication with Amazon Bedrock"""
    
    # Define maximum recursion depth as class variable
    MAX_RECURSION_DEPTH = 5
    
    def __init__(self, region_name, config_file_path="config/mcp_servers.json", logger=None):

        self.logger = logger or setup_logger(__name__)
        self.logger.info(f"Initializing BedrockClient with region: {region_name}")
        
        self.client = boto3.client('bedrock-runtime', region_name=region_name)
        self.model_id = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
        
        self.config_file_path = config_file_path
        self._tools = {}
        self._load_mcp_config()
        
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

        self.loop.run_until_complete(self.initialize_mcp_servers())
        self.logger.info("BedrockClient initialized")
        
    def _load_mcp_config(self):
        try:
            self.logger.info(f"Loading MCP server configuration from {self.config_file_path}")
            with open(self.config_file_path, 'r') as f:
                self.mcp_config = json.load(f)
            
            server_count = len(self.mcp_config.get('mcp_servers', []))
            self.logger.info(f"Found {server_count} MCP servers in configuration")
        except FileNotFoundError:
            self.logger.error(f"MCP server configuration file not found: {self.config_file_path}")
            self.mcp_config = {"mcp_servers": []}
        except json.JSONDecodeError:
            self.logger.error(f"Invalid JSON in MCP server configuration file: {self.config_file_path}")
            self.mcp_config = {"mcp_servers": []}
        except Exception as e:
            self.logger.error(f"Error loading MCP configuration: {e}", exc_info=True)
            self.mcp_config = {"mcp_servers": []}
    
    async def initialize_mcp_servers(self):
        try:
            self.logger.info("Initializing MCP servers")
            for server_config in self.mcp_config.get('mcp_servers', []):
                await self._initialize_server(server_config)
            self.logger.info("MCP servers initialization completed")
        except Exception as e:
            self.logger.error(f"Error initializing MCP servers: {e}", exc_info=True)
    
    async def _initialize_server(self, server_config):
        name = server_config.get('name')
        command = server_config.get('command')
        args = server_config.get('args', [])
        env = server_config.get('env')
        
        if not name or not command:
            self.logger.error(f"Invalid server configuration: {server_config}")
            return
        
        try:
            self.logger.info(f"Initializing MCP server: {name}")
            
            server_params = StdioServerParameters(
                command=command,
                args=args,
                env=env
            )
            
            client = stdio_client(server_params)
            read, write = await client.__aenter__()
            
            session = ClientSession(read, write)
            await session.__aenter__()
            await session.initialize()
            

            self.logger.info(f"Getting available tools from server: {name}")
            tools_result = await session.list_tools()
            
            tools = []
            if hasattr(tools_result, 'tools'):
                tools = tools_result.tools
            elif isinstance(tools_result, dict) and 'tools' in tools_result:
                tools = tools_result['tools']
            elif isinstance(tools_result, list):
                tools = tools_result
            
            # ツールを登録
            self.logger.info(f"Found {len(tools)} tools in server: {name}")
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
                    self.logger.error(f"Error registering tool '{name}_{getattr(tool, 'name', 'unknown')}': {e}", exc_info=True)

            await session.__aexit__(None, None, None)
            await client.__aexit__(None, None, None)
            
            self.logger.info(f"Successfully initialized MCP server: {name}")
        except Exception as e:
            self.logger.error(f"Error initializing MCP server '{name}': {e}", exc_info=True)
    
    def generate_response(self, message_or_conversation):
        """
        Generate a response to a message or conversation history
        
        Args:
            message_or_conversation: Single message (string) or conversation history (list of dicts)
            
        Returns:
            str: Generated response
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(self._generate_response_async(message_or_conversation))
    
    async def _generate_response_async(self, message_or_conversation):
        messages = self._prepare_messages(message_or_conversation)
        system = self._prepare_system_prompt()
        tool_config = self._prepare_tool_config()
        
        try:
            return await self._make_bedrock_request(messages, system, tool_config)
        except Exception as e:
            self.logger.error(f"Error generating response: {e}", exc_info=True)
            return "Sorry, an error occurred while generating the response."
    
    def _prepare_messages(self, message_or_conversation):
        if isinstance(message_or_conversation, str):
            self.logger.debug("Processing single message input")
            return [{
                "role": "user",
                "content": [{"text": message_or_conversation}]
            }]
        elif isinstance(message_or_conversation, list):
            self.logger.debug(f"Processing conversation history with {len(message_or_conversation)} messages")
            return message_or_conversation
        else:
            self.logger.error(f"Invalid input type: {type(message_or_conversation)}")
            raise ValueError("Invalid input format")
    
    def _prepare_system_prompt(self):
        system_text = "You are a helpful AI assistant. Speak in Japanese"
        
        if self._tools:
            self.logger.debug(f"Adding {len(self._tools)} tools to system prompt")
            system_text += " You have access to the following tools:\n\n"
            for name, tool_info in self._tools.items():
                system_text += f"- {name}: {tool_info['description']}\n"
        
        return [{"text": system_text}]
    
    def _prepare_tool_config(self):
        tool_specs = []
        for normalized_name, tool in self._tools.items():
            safe_name = ''.join(c if c.isalnum() or c in ['_', '-'] else '_' for c in normalized_name)
            
            if len(safe_name) > 64:
                self.logger.warning(f"Tool name '{safe_name}' exceeds 64 characters, truncating")
                parts = safe_name.split('_', 1)
                if len(parts) > 1:
                    server_prefix = parts[0]
                    tool_part = parts[1]
                    max_server_len = 20
                    if len(server_prefix) > max_server_len:
                        server_prefix = server_prefix[:max_server_len]
                    remaining_space = 64 - len(server_prefix) - 1  # 1は'_'の分
                    tool_part = tool_part[-remaining_space:] if len(tool_part) > remaining_space else tool_part
                    safe_name = f"{server_prefix}_{tool_part}"
                else:
                    safe_name = safe_name[:64]
            
            tool_specs.append({
                "toolSpec": {
                    "name": safe_name,
                    "description": tool['description'],
                    "inputSchema": {
                        "json": tool['input_schema']
                    }
                }
            })
        
        tool_config = {"tools": tool_specs}
        self.logger.debug(f"Tool config prepared with {len(tool_config.get('tools', []))} tools")
        return tool_config
    
    async def _make_bedrock_request(self, messages, system, tool_config, recursion_depth=0):

        if recursion_depth >= self.MAX_RECURSION_DEPTH:
            self.logger.warning(f"Maximum recursion depth ({self.MAX_RECURSION_DEPTH}) reached")
            return await self._generate_final_response(messages, system)
        
        self.logger.info(f"Calling Bedrock with model: {self.model_id} (recursion depth: {recursion_depth})")
        response = self.client.converse(
            modelId=self.model_id,
            messages=messages,
            system=system,
            inferenceConfig={
                "maxTokens": 5000,
                "topP": 0.1,
                "temperature": 0.3
            },
            toolConfig=tool_config
        )
        
        stop_reason = response.get('stopReason')
        self.logger.info(f"Response stop reason: {stop_reason}")
        
        if stop_reason in ['end_turn', 'stop_sequence']:
            return self._extract_text_response(response)
        elif stop_reason == 'tool_use':
            return await self._handle_tool_use(response, messages, recursion_depth)
        elif stop_reason == 'max_tokens':
            return await self._handle_max_tokens(response, messages, recursion_depth)
        else:
            self.logger.warning(f"Unknown stop reason: {stop_reason}")
            return f"Unknown stop reason: {stop_reason}"
    
    def _extract_text_response(self, response):
        output_message = response['output']['message']
        response_text = ""
        for content in output_message['content']:
            if 'text' in content:
                response_text += content['text'] + "\n"
        
        return response_text.strip()
    
    async def _handle_tool_use(self, response, messages, recursion_depth=0):
        if recursion_depth >= self.MAX_RECURSION_DEPTH:
            self.logger.warning(f"Maximum tool recursion depth ({self.MAX_RECURSION_DEPTH}) reached")
            return await self._generate_final_response(messages, self._prepare_system_prompt())
            
        self.logger.info(f"Model requested tool use (recursion depth: {recursion_depth})")
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
        
        # Add tool results to conversation and make recursive call
        messages.append(response['output']['message'])
        messages.append({
            "role": "user",
            "content": tool_response
        })
        
        self.logger.info(f"Making recursive call with tool results (recursion depth: {recursion_depth})")
        system = self._prepare_system_prompt()
        tool_config = self._prepare_tool_config()
        return await self._make_bedrock_request(messages, system, tool_config, recursion_depth + 1)
    
    async def _call_tool_with_direct_session(self, server_name, tool_name, arguments, timeout=30.0):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        import json
        
        # Get server configuration
        server_config = None
        try:
            with open("config/mcp_servers.json", 'r') as f:
                config = json.load(f)
                for srv in config.get('mcp_servers', []):
                    if srv.get('name') == server_name:
                        server_config = srv
                        break
        except Exception as e:
            self.logger.error(f"Failed to load server config: {e}")
            raise ValueError(f"Server configuration not found for: {server_name}")
        
        if not server_config:
            raise ValueError(f"Server configuration not found for: {server_name}")
        
        # Set up MCP server parameters
        server_params = StdioServerParameters(
            command=server_config.get('command'),
            args=server_config.get('args', []),
            env=server_config.get('env')
        )
        
        self.logger.info(f"Creating new session for {server_name}")
        
        # Create MCP client
        client = None
        session = None
        
        try:
            # Create client and session
            client = stdio_client(server_params)
            read, write = await client.__aenter__()
            
            session = ClientSession(read, write)
            await session.__aenter__()
            await session.initialize()
            
            self.logger.info(f"Calling {tool_name} directly with new session")
            
            # Call the tool
            result = await asyncio.wait_for(
                session.call_tool(tool_name, arguments=arguments),
                timeout=timeout
            )
            
            return result
        finally:
            # Close session and client
            if session:
                try:
                    await session.__aexit__(None, None, None)
                except Exception as e:
                    self.logger.error(f"Error closing session: {e}")
            
            if client:
                try:
                    await client.__aexit__(None, None, None)
                except Exception as e:
                    self.logger.error(f"Error closing client: {e}")
    
    def _normalize_name(self, name: str) -> str:
        """Convert hyphenated and dotted names to underscore format"""
        return name.replace('-', '_').replace('.', '_')
        
    def register_tool(self, name: str, description: str, input_schema: Dict, 
                      server_name: str, original_tool_name: str, 
                      timeout: float = 30.0):
        """
        Register a new tool
        
        Args:
            name: Tool name
            description: Tool description
            input_schema: Tool input schema
            server_name: Name of the server this tool belongs to
            original_tool_name: Original name of the tool on the server
            timeout: Timeout for tool execution in seconds
        """
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

    async def _execute_tool(self, tool_request):
        """Execute a tool and format the result"""
        tool_name = tool_request['name']
        self.logger.info(f"Executing tool: {tool_name}")
        
        try:
            # Get server name and original tool name from the tool name
            normalized_name = self._normalize_name(tool_name)
            if normalized_name not in self._tools:
                raise ValueError(f"Unknown tool: {normalized_name}")
                
            tool_info = self._tools[normalized_name]
            server_name = tool_info.get('server_name')
            original_tool_name = tool_info.get('original_tool_name', tool_name)
            
            self.logger.info(f"Using direct session for tool: {tool_name}")
            self.logger.info(f"Server name: {server_name}, Original tool name: {original_tool_name}")
            
            # Use direct session for all tools
            result = await self._call_tool_with_direct_session(
                server_name=server_name,
                tool_name=original_tool_name,
                arguments=tool_request['input'],
                timeout=30.0
            )
            
            status = 'success'
            content_text = str(result)
            
            return {
                'toolResult': {
                    'toolUseId': tool_request['toolUseId'],
                    'content': [{'text': content_text}],
                    'status': status
                }
            }
        except asyncio.TimeoutError as te:
            self.logger.error(f"Tool execution timed out: {te}", exc_info=True)
            return {
                'toolResult': {
                    'toolUseId': tool_request['toolUseId'],
                    'content': [{'text': f"Tool execution timed out"}],
                    'status': 'error'
                }
            }
        except Exception as e:
            self.logger.error(f"Tool execution error: {e}", exc_info=True)
            return {
                'toolResult': {
                    'toolUseId': tool_request['toolUseId'],
                    'content': [{'text': f"Tool execution error: {str(e)}"}],
                    'status': 'error'
                }
            }
    
    async def _generate_final_response(self, messages, system):
        """
        Generate a final response based on collected information when tool execution limit is reached
        
        Args:
            messages: Current message history
            system: System prompt
            
        Returns:
            str: Generated final response
        """
        # Add instruction to generate final response based on collected information
        final_instruction = {
            "role": "user",
            "content": [{"text": "Please generate a final response based on the information collected so far. Do not make additional tool calls."}]
        }
        messages.append(final_instruction)
        
        # Generate final response with tool configuration (but instruct not to use tools)
        self.logger.info("Generating final response based on collected information")
        tool_config = self._prepare_tool_config()  # Get normal tool configuration
        response = self.client.converse(
            modelId=self.model_id,
            messages=messages,
            system=system,
            inferenceConfig={
                "maxTokens": 5000,
                "topP": 0.1,
                "temperature": 0.3
            },
            toolConfig=tool_config  # Include tool configuration
        )
        
        return self._extract_text_response(response)
    
    async def _handle_max_tokens(self, response, messages, recursion_depth=0):
        """
        Handle max tokens reached in Bedrock response
        
        Args:
            response: Bedrock response
            messages: Current message history
            recursion_depth: Current recursion depth
        """
        self.logger.info(f"Max tokens reached, continuing generation (recursion depth: {recursion_depth})")
        messages.append(response['output']['message'])
        messages.append({
            "role": "user",
            "content": [{"text": "Please continue."}]
        })
        
        system = self._prepare_system_prompt()
        tool_config = self._prepare_tool_config()
        return await self._make_bedrock_request(messages, system, tool_config, recursion_depth + 1)
