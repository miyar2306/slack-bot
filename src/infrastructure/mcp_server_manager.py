import json
import asyncio
from typing import Dict, List, Any
from mcp import StdioServerParameters
from .mcp_client import MCPClient
from .tool_manager import ToolManager

class MCPServerManager:
    """複数のMCPサーバーを管理するクラス"""
    
    def __init__(self, config_file_path: str = "config/mcp_servers.json"):
        """
        MCPServerManagerの初期化
        
        Args:
            config_file_path: MCPサーバー設定ファイルのパス
        """
        self.config_file_path = config_file_path
        self.servers = {}  # サーバー名 -> MCPClientのマッピング
        self.tool_manager = ToolManager()
        
    async def initialize(self):
        """設定ファイルからMCPサーバーを初期化"""
        try:
            with open(self.config_file_path, 'r') as f:
                config = json.load(f)
            
            # 各サーバーを初期化
            for server_config in config.get('mcp_servers', []):
                await self._initialize_server(server_config)
                
            print(f"{len(self.servers)}個のMCPサーバーを初期化しました")
        except Exception as e:
            print(f"MCPサーバーの初期化エラー: {e}")
    
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
            print(f"無効なサーバー設定: {server_config}")
            return
        
        try:
            server_params = StdioServerParameters(
                command=command,
                args=args,
                env=env
            )
            
            mcp_client = MCPClient(server_params)
            await mcp_client.connect()
            
            # サーバーを登録
            self.servers[name] = mcp_client
            
            # 利用可能なツールを取得して登録
            tools = await mcp_client.get_available_tools()
            for tool in tools:
                # ツール名にサーバー名をプレフィックスとして追加
                prefixed_name = f"{name}.{tool.name}"
                self.tool_manager.register_tool(
                    name=prefixed_name,
                    func=lambda tool_name, arguments, client=mcp_client, original_name=tool.name: client.call_tool(original_name, arguments),
                    description=f"[{name}] {tool.description}",
                    input_schema=tool.inputSchema
                )
            
            print(f"MCPサーバー '{name}' に接続し、{len(tools)}個のツールを登録しました")
        except Exception as e:
            print(f"MCPサーバー '{name}' の初期化エラー: {e}")
    
    def get_tool_manager(self) -> ToolManager:
        """ツールマネージャーを取得"""
        return self.tool_manager
