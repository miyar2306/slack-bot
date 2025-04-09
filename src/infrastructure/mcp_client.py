from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from typing import Any, List
import asyncio
from .logger import setup_logger

class MCPClient:
    """MCPサーバーとの通信を担当するクラス"""
    
    def __init__(self, server_params: StdioServerParameters, logger=None):
        """
        MCPClientの初期化
        
        Args:
            server_params: MCPサーバーのパラメータ
            logger: Logger instance (optional)
        """
        self.server_params = server_params
        self.logger = logger or setup_logger(__name__)
        self.session = None
        self._client = None
        self.logger.debug("MCPClient instance created")
        
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
        self.logger.info("Connecting to MCP server")
        try:
            self._client = stdio_client(self.server_params)
            self.read, self.write = await self._client.__aenter__()
            self.logger.debug("Stdio client connection established")
            
            session = ClientSession(self.read, self.write)
            self.session = await session.__aenter__()
            await self.session.initialize()
            self.logger.info("MCP server connection initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to connect to MCP server: {e}", exc_info=True)
            raise

    async def get_available_tools(self) -> List[Any]:
        """利用可能なツールのリストを取得"""
        if not self.session:
            self.logger.error("Cannot get tools: Not connected to MCP server")
            raise RuntimeError("Not connected to MCP server")
            
        try:
            self.logger.info("Getting available tools from MCP server")
            # list_toolsの結果を取得
            result = await self.session.list_tools()
            
            # デバッグ情報を出力
            self.logger.debug(f"list_tools result type: {type(result)}")
            
            # ListToolsResult型の場合（ログから判断）
            if hasattr(result, 'tools'):
                tool_count = len(result.tools)
                self.logger.info(f"Retrieved tool list from ListToolsResult.tools: found {tool_count} tools")
                return result.tools
            
            # 以下は前回の実装のフォールバック処理
            try:
                # 参考リポジトリと同じアンパック方法を試す
                self.logger.debug("Trying standard unpacking method")
                _, tools_list = result
                _, tools_list = tools_list
                
                # 成功した場合、ツールリストの情報を出力
                tool_count = len(tools_list)
                self.logger.info(f"Successfully retrieved tool list: found {tool_count} tools")
                return tools_list
                
            except ValueError as e:
                # アンパックに失敗した場合、応答の構造を詳細に調査
                self.logger.warning(f"Standard unpacking failed: {e}")
                self.logger.debug(f"Response structure: {result}")
                
                # 応答がタプルの場合、異なるアンパック方法を試す
                if isinstance(result, tuple) and len(result) == 2:
                    self.logger.debug("Trying alternative tuple unpacking")
                    _, content = result
                    if isinstance(content, tuple) and len(content) >= 1:
                        # 最初の要素を取得
                        tools_list = content[0]
                        if isinstance(tools_list, list):
                            self.logger.info(f"Retrieved tool list using alternative method: found {len(tools_list)} tools")
                        else:
                            self.logger.warning("Retrieved object is not a list")
                        return tools_list
                
                # 応答が辞書の場合
                elif isinstance(result, dict) and 'tools' in result:
                    self.logger.debug("Extracting tools from dictionary")
                    tools_list = result['tools']
                    self.logger.info(f"Retrieved tool list from dictionary: found {len(tools_list)} tools")
                    return tools_list
                
                # 応答がリストの場合、そのまま返す
                elif isinstance(result, list):
                    self.logger.info(f"Response is a list with {len(result)} elements")
                    return result
                
                # その他の場合、空のリストを返す
                self.logger.warning("Unknown response format, returning empty list")
                return []
                
        except Exception as e:
            self.logger.error(f"Error retrieving tool list: {e}", exc_info=True)
            return []

    async def call_tool(self, tool_name: str, arguments: dict, timeout: float = 30.0) -> Any:
        """
        指定されたツールを引数と共に呼び出す
        
        Args:
            tool_name: ツール名
            arguments: ツールの引数
            timeout: ツール呼び出しのタイムアウト秒数（デフォルト: 30秒）
            
        Returns:
            Any: ツールの実行結果
        """
        if not self.session:
            self.logger.error("Cannot call tool: Not connected to MCP server")
            raise RuntimeError("Not connected to MCP server")
        
        try:    
            self.logger.info(f"Calling tool: {tool_name}")
            self.logger.debug(f"Tool arguments: {arguments}")
            
            try:
                # タイムアウト付きでツールを呼び出す
                self.logger.debug(f"Setting timeout of {timeout} seconds for tool call")
                result = await asyncio.wait_for(
                    self.session.call_tool(tool_name, arguments=arguments),
                    timeout=timeout
                )
                self.logger.debug("Tool call successful")
                return result
            except asyncio.TimeoutError:
                self.logger.error(f"Tool call timed out after {timeout} seconds: {tool_name}")
                raise TimeoutError(f"Tool call timed out after {timeout} seconds: {tool_name}")
        except Exception as e:
            self.logger.error(f"Error calling tool {tool_name}: {e}", exc_info=True)
            if isinstance(e, TimeoutError):
                # タイムアウトエラーの場合は特別なメッセージを返す
                return {"error": f"Tool call timed out: {tool_name}"}
            else:
                # その他のエラーの場合
                return {"error": f"Tool execution error: {str(e)}"}
