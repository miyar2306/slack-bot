from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from typing import Any, List
import asyncio
from .logger import setup_logger

class MCPClient:
    """Handles communication with MCP servers"""
    
    def __init__(self, server_params: StdioServerParameters, logger=None):
        """
        Initialize MCPClient
        
        Args:
            server_params: MCP server parameters
            logger: Logger instance (optional)
        """
        self.server_params = server_params
        self.logger = logger or setup_logger(__name__)
        self.session = None
        self._client = None
        
    async def __aenter__(self):
        """Async context manager entry"""
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

    async def get_available_tools(self) -> List[Any]:
        """Get list of available tools"""
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
        Call a tool with arguments
        
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
            self.logger.info(f"Calling tool: {tool_name}")
            
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
