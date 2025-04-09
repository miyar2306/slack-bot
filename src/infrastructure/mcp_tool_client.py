from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from typing import Any, List, Dict, Callable
import asyncio
from .logger import setup_logger

class MCPToolClient:
    """Handles MCP server communication and tool management"""
    
    def __init__(self, server_params: StdioServerParameters = None, logger=None):
        """
        Initialize MCPToolClient
        
        Args:
            server_params: MCP server parameters
            logger: Logger instance (optional)
        """
        self.server_params = server_params
        self.logger = logger or setup_logger(__name__)
        self.session = None
        self._client = None
        self._tools = {}
        self._name_mapping = {}  # Maps normalized names to original names
        
    async def __aenter__(self):
        """Async context manager entry"""
        if self.server_params:
            await self.connect()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.__aexit__(exc_type, exc_val, exc_tb)
        if self._client:
            await self._client.__aexit__(exc_type, exc_val, exc_tb)

    async def connect(self):
        """Establish connection to MCP server"""
        if not self.server_params:
            self.logger.error("Cannot connect: No server parameters provided")
            raise ValueError("No server parameters provided")
            
        self.logger.info("Connecting to MCP server")
        try:
            self._client = stdio_client(self.server_params)
            self.read, self.write = await self._client.__aenter__()
            
            session = ClientSession(self.read, self.write)
            self.session = await session.__aenter__()
            await self.session.initialize()
            self.logger.info("MCP server connection initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to connect to MCP server: {e}", exc_info=True)
            raise

    def _normalize_name(self, name: str) -> str:
        """Convert hyphenated names to underscore format"""
        return name.replace('-', '_')
    
    def register_tool(self, name: str, func: Callable, description: str, input_schema: Dict):
        """
        Register a new tool
        
        Args:
            name: Tool name
            func: Tool execution function
            description: Tool description
            input_schema: Tool input schema
        """
        normalized_name = self._normalize_name(name)
        self._name_mapping[normalized_name] = name
        self._tools[normalized_name] = {
            'function': func,
            'description': description,
            'input_schema': input_schema,
            'original_name': name
        }
        self.logger.info(f"Registered tool: {name}")

    def get_tools(self) -> Dict[str, List[Dict]]:
        """
        Generate tool specifications in Bedrock format
        
        Returns:
            Dict: Tool specifications dictionary
        """
        tool_specs = []
        for normalized_name, tool in self._tools.items():
            tool_specs.append({
                "toolSpec": {
                    "name": normalized_name,
                    "description": tool['description'],
                    "inputSchema": {
                        "json": tool['input_schema']
                    }
                }
            })
        
        return {"tools": tool_specs}

    async def get_available_tools(self) -> List[Any]:
        """Get list of available tools from the server"""
        if not self.session:
            self.logger.error("Cannot get tools: Not connected to MCP server")
            raise RuntimeError("Not connected to MCP server")
            
        try:
            self.logger.info("Getting available tools from MCP server")
            result = await self.session.list_tools()
            
            # Handle different response formats
            if hasattr(result, 'tools'):
                self.logger.info(f"Retrieved {len(result.tools)} tools from ListToolsResult.tools")
                return result.tools
            
            if isinstance(result, dict) and 'tools' in result:
                self.logger.info(f"Retrieved {len(result['tools'])} tools from dictionary")
                return result['tools']
                
            if isinstance(result, list):
                self.logger.info(f"Retrieved {len(result)} tools from list")
                return result
                
            if isinstance(result, tuple) and len(result) == 2:
                try:
                    _, content = result
                    if isinstance(content, tuple) and len(content) >= 1:
                        tools_list = content[0]
                        if isinstance(tools_list, list):
                            self.logger.info(f"Retrieved {len(tools_list)} tools from tuple unpacking")
                            return tools_list
                except ValueError:
                    pass
            
            self.logger.warning("Unknown response format, returning empty list")
            return []
                
        except Exception as e:
            self.logger.error(f"Error retrieving tool list: {e}", exc_info=True)
            return []

    async def call_tool(self, tool_name: str, arguments: dict, timeout: float = 30.0) -> Any:
        """
        Call a tool directly on the server
        
        Args:
            tool_name: Tool name
            arguments: Tool arguments
            timeout: Tool call timeout in seconds (default: 30s)
            
        Returns:
            Any: Tool execution result
        """
        if not self.session:
            self.logger.error("Cannot call tool: Not connected to MCP server")
            raise RuntimeError("Not connected to MCP server")
        
        try:    
            self.logger.info(f"Calling tool on server: {tool_name}")
            
            try:
                result = await asyncio.wait_for(
                    self.session.call_tool(tool_name, arguments=arguments),
                    timeout=timeout
                )
                self.logger.debug("Tool call successful")
                return result
            except asyncio.TimeoutError:
                error_msg = f"Tool call timed out after {timeout} seconds: {tool_name}"
                self.logger.error(error_msg)
                return {"error": error_msg}
        except Exception as e:
            error_msg = f"Tool execution error: {str(e)}"
            self.logger.error(f"Error calling tool {tool_name}: {e}", exc_info=True)
            return {"error": error_msg}

    async def execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> Any:
        """
        Execute a registered tool
        
        Args:
            tool_name: Tool name
            tool_input: Tool input parameters
            
        Returns:
            Any: Tool execution result
            
        Raises:
            ValueError: If tool not found or execution fails
        """
        normalized_name = self._normalize_name(tool_name)
        
        if normalized_name not in self._tools:
            self.logger.error(f"Unknown tool: {normalized_name}")
            raise ValueError(f"Unknown tool: {normalized_name}")
        
        try:
            tool_func = self._tools[normalized_name]['function']
            original_name = self._tools[normalized_name]['original_name']
            result = await tool_func(original_name, tool_input)
            self.logger.debug("Tool execution successful")
            return result
        except Exception as e:
            self.logger.error(f"Tool execution error: {e}", exc_info=True)
            raise ValueError(f"Tool execution error: {str(e)}")

    async def get_and_register_tools(self, server_name: str, timeout: float = 30.0):
        """
        Get tools from server and register them automatically
        
        Args:
            server_name: Name of the server for tool prefixing
            timeout: Default timeout for tool calls
            
        Returns:
            int: Number of tools registered
        """
        tools = await self.get_available_tools()
        
        if not tools:
            self.logger.info(f"No tools found in server: {server_name}")
            return 0
            
        self.logger.info(f"Found {len(tools)} tools in server: {server_name}")
        registered_count = 0
        
        for tool in tools:
            try:
                prefixed_name = f"{server_name}_{tool.name}"
                tool_timeout = 15.0 if tool.name == "fetch" else timeout
                
                self.register_tool(
                    name=prefixed_name,
                    func=lambda tool_name, arguments, client=self, original_name=tool.name, timeout=tool_timeout: 
                          client.call_tool(original_name, arguments, timeout=timeout),
                    description=f"[{server_name}] {tool.description}",
                    input_schema=tool.inputSchema
                )
                registered_count += 1
            except Exception as e:
                self.logger.error(f"Error registering tool '{server_name}_{getattr(tool, 'name', 'unknown')}': {e}", exc_info=True)
                
        self.logger.info(f"Successfully registered {registered_count} tools from server: {server_name}")
        return registered_count

    def clear_tools(self):
        """Clear all registered tools"""
        tool_count = len(self._tools)
        self._tools.clear()
        self._name_mapping.clear()
        self.logger.info(f"Cleared {tool_count} tools")
