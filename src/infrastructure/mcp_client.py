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
            
        try:
            # list_toolsの結果を取得
            result = await self.session.list_tools()
            
            # 応答からツールリストを抽出する汎用的な関数
            def extract_tools(obj):
                """
                応答オブジェクトからツールリストを再帰的に抽出
                
                Args:
                    obj: 応答オブジェクト（リスト、タプル、辞書など）
                    
                Returns:
                    List: ツールのリスト
                """
                # リストまたはタプルの場合、各要素を再帰的に処理
                if isinstance(obj, (list, tuple)):
                    for item in obj:
                        tools = extract_tools(item)
                        if tools:
                            return tools
                
                # 辞書の場合、キーに'tools'があればその値を返す
                # または各値を再帰的に処理
                elif isinstance(obj, dict):
                    if 'tools' in obj:
                        return obj['tools']
                    
                    for value in obj.values():
                        tools = extract_tools(value)
                        if tools:
                            return tools
                
                # objがツールのリストである場合（各要素にname, description, inputSchemaを持つ）
                if isinstance(obj, list) and all(isinstance(item, object) and 
                                                hasattr(item, 'name') and 
                                                hasattr(item, 'description') for item in obj):
                    return obj
                
                return None
            
            # 応答からツールリストを抽出
            tools_list = extract_tools(result)
            
            # ツールリストが見つからない場合は空のリストを返す
            if tools_list is None:
                print("警告: ツールリストが見つかりませんでした")
                return []
                
            return tools_list
            
        except Exception as e:
            print(f"ツール一覧の取得エラー: {e}")
            return []

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
