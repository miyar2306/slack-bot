from typing import Any, Dict, List, Callable
import inspect
import json
from .logger import setup_logger

class ToolManager:
    """ツールの管理と実行を担当するクラス"""
    
    def __init__(self, logger=None):
        """
        ToolManagerの初期化
        
        Args:
            logger: Logger instance (optional)
        """
        self._tools = {}
        self._name_mapping = {}  # 正規化された名前から元の名前へのマッピング
        self.logger = logger or setup_logger(__name__)
        self.logger.info("ToolManager initialized")
    
    def _normalize_name(self, name: str) -> str:
        """
        ハイフン付きの名前をアンダースコア形式に変換
        
        Args:
            name: 元のツール名
            
        Returns:
            str: 正規化されたツール名
        """
        return name.replace('-', '_')
    
    def register_tool(self, name: str, func: Callable, description: str, input_schema: Dict):
        """
        新しいツールをシステムに登録
        
        Args:
            name: ツール名
            func: ツール実行関数
            description: ツールの説明
            input_schema: ツールの入力スキーマ
        """
        normalized_name = self._normalize_name(name)
        self._name_mapping[normalized_name] = name
        self._tools[normalized_name] = {
            'function': func,
            'description': description,
            'input_schema': input_schema,
            'original_name': name
        }
        self.logger.info(f"Registered tool: {name} (normalized: {normalized_name})")

    def get_tools(self) -> Dict[str, List[Dict]]:
        """
        Bedrockの形式に合わせたツール仕様を生成
        
        Returns:
            Dict: ツール仕様の辞書
        """
        tool_specs = []
        for normalized_name, tool in self._tools.items():
            # toolSpecキーの下にツール情報をネスト
            # inputSchemaはjsonキーの下にネスト
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

    async def execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> Any:
        """
        エージェントのリクエストに基づいてツールを実行
        
        Args:
            tool_name: ツール名
            tool_input: ツールの入力パラメータ
            
        Returns:
            Any: ツールの実行結果
            
        Raises:
            ValueError: ツールが見つからない場合や実行エラーの場合
        """
        normalized_name = self._normalize_name(tool_name)
        self.logger.debug(f"Executing tool: {tool_name} (normalized: {normalized_name})")
        
        if normalized_name not in self._tools:
            self.logger.error(f"Unknown tool: {normalized_name}")
            raise ValueError(f"Unknown tool: {normalized_name}")
        
        try:
            tool_func = self._tools[normalized_name]['function']
            # 実際の関数を呼び出す際には元の名前を使用
            original_name = self._tools[normalized_name]['original_name']
            self.logger.debug(f"Calling tool function with original name: {original_name}")
            result = await tool_func(original_name, tool_input)
            self.logger.debug("Tool execution successful")
            return result
        except Exception as e:
            self.logger.error(f"Tool execution error: {e}", exc_info=True)
            raise ValueError(f"Tool execution error: {str(e)}")

    def clear_tools(self):
        """登録されたすべてのツールをクリア"""
        tool_count = len(self._tools)
        self._tools.clear()
        self._name_mapping.clear()
        self.logger.info(f"Cleared {tool_count} tools")
