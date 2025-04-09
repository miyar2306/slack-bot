import json
import asyncio
from typing import Dict, List, Any
from mcp import StdioServerParameters
from .mcp_client import MCPClient
from .tool_manager import ToolManager
from .logger import setup_logger

class MCPServerManager:
    """複数のMCPサーバーを管理するクラス"""
    
    def __init__(self, config_file_path: str = "config/mcp_servers.json", logger=None):
        """
        MCPServerManagerの初期化
        
        Args:
            config_file_path: MCPサーバー設定ファイルのパス
            logger: Logger instance (optional)
        """
        self.config_file_path = config_file_path
        self.logger = logger or setup_logger(__name__)
        self.servers = {}  # サーバー名 -> MCPClientのマッピング
        self.tool_manager = ToolManager(logger=self.logger)
        self.logger.info(f"MCPServerManager initialized with config file: {config_file_path}")
        
    async def initialize(self):
        """設定ファイルからMCPサーバーを初期化"""
        try:
            self.logger.info(f"Loading MCP server configuration from {self.config_file_path}")
            with open(self.config_file_path, 'r') as f:
                config = json.load(f)
            
            # 各サーバーを初期化
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
        単一のMCPサーバーを初期化
        
        Args:
            server_config: サーバー設定の辞書
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
            self.logger.debug(f"Server command: {command}, args: {args}")
            
            server_params = StdioServerParameters(
                command=command,
                args=args,
                env=env
            )
            
            mcp_client = MCPClient(server_params)
            self.logger.debug(f"Connecting to MCP server: {name}")
            await mcp_client.connect()
            
            # サーバーを登録
            self.servers[name] = mcp_client
            self.logger.info(f"Successfully connected to MCP server: {name}")
            
            # 利用可能なツールを取得して登録
            self.logger.debug(f"Getting available tools from server: {name}")
            tools = await mcp_client.get_available_tools()
            
            if tools:  # ツールリストが空でない場合のみ処理
                self.logger.info(f"Found {len(tools)} tools in server: {name}")
                for tool in tools:
                    try:
                        # ツール名にサーバー名をプレフィックスとして追加（ドットの代わりにアンダースコアを使用）
                        prefixed_name = f"{name}_{tool.name}"
                        self.logger.debug(f"Registering tool: {prefixed_name}")
                        self.tool_manager.register_tool(
                            name=prefixed_name,
                            func=lambda tool_name, arguments, client=mcp_client, original_name=tool.name: client.call_tool(original_name, arguments),
                            description=f"[{name}] {tool.description}",
                            input_schema=tool.inputSchema
                        )
                    except Exception as e:
                        self.logger.error(f"Error registering tool '{name}_{getattr(tool, 'name', 'unknown')}': {e}", exc_info=True)
            else:
                self.logger.info(f"No tools found in server: {name}")
            
            self.logger.info(f"Successfully initialized MCP server '{name}' with {len(tools)} tools")
        except Exception as e:
            self.logger.error(f"Error initializing MCP server '{name}': {e}", exc_info=True)
    
    def get_tool_manager(self) -> ToolManager:
        """ツールマネージャーを取得"""
        return self.tool_manager
