from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from typing import Any, List
import asyncio

class MCPClient:
    """MCPサーバーとの通信を担当するクラス"""
    
    def __init__(self, server_params: StdioServerParameters):
        """
        MCPClientの初期化
        
        Args:
            server_params: MCPサーバーのパラメータ
        """
        self.server_params = server_params
        self.session = None
        self._client = None
        
    async def __aenter__(self):
        """非同期コンテキストマネージャーのエントリー"""
        await self.connect()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """非同期コンテキストマネージャーの終了"""
        if self.session:
            await self.session.__aexit__(exc_type, exc_val, exc_tb)
        if self._client:
            await self._client.__aexit__(exc_type, exc_val, exc_tb)

    async def connect(self):
        """MCPサーバーへの接続を確立"""
        self._client = stdio_client(self.server_params)
        self.read, self.write = await self._client.__aenter__()
        session = ClientSession(self.read, self.write)
        self.session = await session.__aenter__()
        await self.session.initialize()

    async def get_available_tools(self) -> List[Any]:
        """利用可能なツールのリストを取得"""
        if not self.session:
            raise RuntimeError("MCPサーバーに接続されていません")
            
        tools = await self.session.list_tools()
        _, tools_list = tools
        _, tools_list = tools_list
        return tools_list

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """
        指定されたツールを引数と共に呼び出す
        
        Args:
            tool_name: ツール名
            arguments: ツールの引数
            
        Returns:
            Any: ツールの実行結果
        """
        if not self.session:
            raise RuntimeError("MCPサーバーに接続されていません")
            
        result = await self.session.call_tool(tool_name, arguments=arguments)
        return result
