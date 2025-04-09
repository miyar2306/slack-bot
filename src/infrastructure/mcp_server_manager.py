import json
from typing import Dict
from mcp import StdioServerParameters
from .mcp_tool_client import MCPToolClient
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
        self.servers = {}  # Map of server name -> MCPToolClient
        self.main_tool_client = MCPToolClient(logger=self.logger)  # Central tool client for all tools
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
            
            # Create and connect the tool client
            tool_client = MCPToolClient(server_params, logger=self.logger)
            await tool_client.connect()
            
            # Register the server
            self.servers[name] = tool_client
            
            # Get and register tools
            await tool_client.get_and_register_tools(name)
            
            # Copy all tools to the main tool client
            for normalized_name, tool in tool_client._tools.items():
                self.main_tool_client._tools[normalized_name] = tool
                self.main_tool_client._name_mapping[normalized_name] = tool['original_name']
                
            self.logger.info(f"Successfully initialized MCP server '{name}' with tools")
        except Exception as e:
            self.logger.error(f"Error initializing MCP server '{name}': {e}", exc_info=True)
    
    def get_tool_manager(self):
        """Get the main tool client instance"""
        return self.main_tool_client
