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
            
            # デバッグ情報を出力
            print(f"list_tools結果の型: {type(result)}")
            
            # ListToolsResult型の場合（ログから判断）
            if hasattr(result, 'tools'):
                print(f"ListToolsResult.tools属性からツールリスト取得: {len(result.tools)}個のツールが見つかりました")
                return result.tools
            
            # 以下は前回の実装のフォールバック処理
            try:
                # 参考リポジトリと同じアンパック方法を試す
                _, tools_list = result
                _, tools_list = tools_list
                
                # 成功した場合、ツールリストの情報を出力
                print(f"ツールリスト取得成功: {len(tools_list)}個のツールが見つかりました")
                return tools_list
                
            except ValueError as e:
                # アンパックに失敗した場合、応答の構造を詳細に調査
                print(f"標準的なアンパックに失敗: {e}")
                print(f"応答の構造: {result}")
                
                # 応答がタプルの場合、異なるアンパック方法を試す
                if isinstance(result, tuple) and len(result) == 2:
                    _, content = result
                    if isinstance(content, tuple) and len(content) >= 1:
                        # 最初の要素を取得
                        tools_list = content[0]
                        print(f"代替方法でツールリスト取得: {len(tools_list) if isinstance(tools_list, list) else 'リストではありません'}")
                        return tools_list
                
                # 応答が辞書の場合
                elif isinstance(result, dict) and 'tools' in result:
                    tools_list = result['tools']
                    print(f"辞書からツールリスト取得: {len(tools_list)}")
                    return tools_list
                
                # 応答がリストの場合、そのまま返す
                elif isinstance(result, list):
                    print(f"応答がリスト: {len(result)}個の要素")
                    return result
                
                # その他の場合、空のリストを返す
                print("未知の応答形式、空のリストを返します")
                return []
                
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
