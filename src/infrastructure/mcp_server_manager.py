import json
import asyncio
from typing import Dict
from mcp import StdioServerParameters
from .mcp_client import MCPClient
from .tool_manager import ToolManager
from .logger import setup_logger

class MCPServerManager:
    """Manages multiple MCP servers"""
    
    def __init__(self, config_file_path: str = "config/mcp_servers.json", logger=None):
        """
        Initialize MCPServerManager
        
        Args:
            config_file_path: Path to MCP server configuration file
            logger: Logger instance (optional)
        """
        self.config_file_path = config_file_path
        self.logger = logger or setup_logger(__name__)
        self.servers = {}  # Map of server name -> MCPClient
        self.tool_manager = ToolManager(logger=self.logger)
        self.logger.info(f"MCPServerManager initialized with config file: {config_file_path}")
        
    async def initialize(self):
        """Initialize MCP servers from configuration file"""
        try:
            self.logger.info(f"Loading MCP server configuration from {self.config_file_path}")
            with open(self.config_file_path, 'r') as f:
                config = json.load(f)
            
            server_count = len(config.get('mcp_servers', []))
            self.logger.info(f"Found {server_count} MCP servers in configuration")
            
            for server_config in config.get('mcp_servers', []):
                await self._initialize_server(server_config)
                
            self.logger.info(f"Successfully initialized {len(self.servers)} MCP servers")
        except FileNotFoundError:
            self.logger.error(f"MCP server configuration file not found: {self.config_file_path}")
        except json.JSONDecodeError:
            self.logger.error(f"Invalid JSON in MCP server configuration file: {self.config_file_path}")
        except Exception as e:
            self.logger.error(f"Error initializing MCP servers: {e}", exc_info=True)
    
    async def _initialize_server(self, server_config: Dict):
        """
        Initialize a single MCP server
        
        Args:
            server_config: Server configuration dictionary
        """
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
            
            mcp_client = MCPClient(server_params)
            await mcp_client.connect()
            
            self.servers[name] = mcp_client
            self.logger.info(f"Successfully connected to MCP server: {name}")
            
            tools = await mcp_client.get_available_tools()
            
            if tools:
                self.logger.info(f"Found {len(tools)} tools in server: {name}")
                for tool in tools:
                    try:
                        prefixed_name = f"{name}_{tool.name}"
                        timeout = 15.0 if tool.name == "fetch" else 30.0
                        
                        self.tool_manager.register_tool(
                            name=prefixed_name,
                            func=lambda tool_name, arguments, client=mcp_client, original_name=tool.name, timeout=timeout: client.call_tool(original_name, arguments, timeout=timeout),
                            description=f"[{name}] {tool.description}",
                            input_schema=tool.inputSchema
                        )
                    except Exception as e:
                        self.logger.error(f"Error registering tool '{name}_{getattr(tool, 'name', 'unknown')}': {e}", exc_info=True)
            else:
                self.logger.info(f"No tools found in server: {name}")
            
            self.logger.info(f"Successfully initialized MCP server '{name}' with {len(tools) if tools else 0} tools")
        except Exception as e:
            self.logger.error(f"Error initializing MCP server '{name}': {e}", exc_info=True)
    
    def get_tool_manager(self) -> ToolManager:
        """Get the tool manager instance"""
        return self.tool_manager
