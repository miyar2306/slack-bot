import boto3
import asyncio
from .mcp_tool_client import MCPToolClient
from .logger import setup_logger

class BedrockClient:
    """Handles communication with Amazon Bedrock"""
    
    def __init__(self, region_name, mcp_server_manager=None, logger=None):
        """
        Initialize BedrockClient
        
        Args:
            region_name (str): AWS region name
            mcp_server_manager: MCPServerManager instance
            logger: Logger instance (optional)
        """
        self.logger = logger or setup_logger(__name__)
        self.logger.info(f"Initializing BedrockClient with region: {region_name}")
        
        self.client = boto3.client('bedrock-runtime', region_name=region_name)
        self.model_id = "us.amazon.nova-pro-v1:0"
        
        self.mcp_server_manager = mcp_server_manager
        self.tool_client = mcp_server_manager.get_tool_manager() if mcp_server_manager else MCPToolClient(logger=self.logger)
        self.logger.info("BedrockClient initialized")
    
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
        """
        Generate a response asynchronously
        
        Args:
            message_or_conversation: Single message (string) or conversation history (list of dicts)
            
        Returns:
            str: Generated response
        """
        messages = self._prepare_messages(message_or_conversation)
        system = self._prepare_system_prompt()
        tool_config = self._prepare_tool_config()
        
        try:
            return await self._make_bedrock_request(messages, system, tool_config)
        except Exception as e:
            self.logger.error(f"Error generating response: {e}", exc_info=True)
            return "Sorry, an error occurred while generating the response."
    
    def _prepare_messages(self, message_or_conversation):
        """Prepare messages for Bedrock API"""
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
        """Prepare system prompt with tool descriptions"""
        system_text = "You are a helpful AI assistant."
        
        if hasattr(self, 'tool_client') and self.tool_client and self.tool_client._tools:
            self.logger.debug(f"Adding {len(self.tool_client._tools)} tools to system prompt")
            system_text += " You have access to the following tools:\n\n"
            for name, tool_info in self.tool_client._tools.items():
                system_text += f"- {name}: {tool_info['description']}\n"
        else:
            system_text += " You have access to the following tools: Speak in Japanese"
        
        return [{"text": system_text}]
    
    def _prepare_tool_config(self):
        """Prepare tool configuration for Bedrock API"""
        if hasattr(self, 'tool_client') and self.tool_client:
            tool_config = self.tool_client.get_tools()
            self.logger.debug(f"Tool config prepared with {len(tool_config.get('tools', []))} tools")
            return tool_config
        return {}
    
    async def _make_bedrock_request(self, messages, system, tool_config, recursion_depth=0):
        """
        Make request to Bedrock API and handle response
        
        Args:
            messages: Messages to send to Bedrock
            system: System prompt
            tool_config: Tool configuration
            recursion_depth: Current recursion depth (for limiting tool call recursion)
        """
        # Maximum recursion depth to prevent infinite loops
        MAX_RECURSION_DEPTH = 5
        
        if recursion_depth >= MAX_RECURSION_DEPTH:
            self.logger.warning(f"Maximum recursion depth ({MAX_RECURSION_DEPTH}) reached")
            return f"I've reached the maximum number of tool calls. Here's what I know so far based on the tools I've used."
        
        self.logger.info(f"Calling Bedrock with model: {self.model_id} (recursion depth: {recursion_depth})")
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
        """Extract text from Bedrock response"""
        output_message = response['output']['message']
        response_text = ""
        for content in output_message['content']:
            if 'text' in content:
                response_text += content['text'] + "\n"
        
        return response_text.strip()
    
    async def _handle_tool_use(self, response, messages, recursion_depth=0):
        """
        Handle tool use in Bedrock response
        
        Args:
            response: Bedrock response
            messages: Current message history
            recursion_depth: Current recursion depth
        """
        # Maximum recursion depth to prevent infinite loops
        MAX_RECURSION_DEPTH = 5
        
        if recursion_depth >= MAX_RECURSION_DEPTH:
            self.logger.warning(f"Maximum tool recursion depth ({MAX_RECURSION_DEPTH}) reached")
            return "I've reached the maximum number of tool calls. Here's what I know so far based on the tools I've used."
            
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
    
    async def _execute_tool(self, tool_request):
        """Execute a tool and format the result"""
        self.logger.info(f"Executing tool: {tool_request['name']}")
        try:
            tool_result = await self.tool_client.execute_tool(
                tool_request['name'], 
                tool_request['input']
            )
            
            status = 'error' if isinstance(tool_result, dict) and 'error' in tool_result else 'success'
            content_text = tool_result['error'] if status == 'error' else str(tool_result)
            
            return {
                'toolResult': {
                    'toolUseId': tool_request['toolUseId'],
                    'content': [{'text': content_text}],
                    'status': status
                }
            }
        except TimeoutError as te:
            self.logger.error(f"Tool execution timed out: {te}", exc_info=True)
            return {
                'toolResult': {
                    'toolUseId': tool_request['toolUseId'],
                    'content': [{'text': f"Tool execution timed out: {str(te)}"}],
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
