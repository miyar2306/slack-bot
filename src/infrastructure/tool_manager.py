from typing import Any, Dict, List, Callable
import inspect
import json

class ToolManager:
    """ツールの管理と実行を担当するクラス"""
    
    def __init__(self):
        """ToolManagerの初期化"""
        self._tools = {}
        self._name_mapping = {}  # 正規化された名前から元の名前へのマッピング
    
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
        
        if normalized_name not in self._tools:
            raise ValueError(f"不明なツール: {normalized_name}")
        
        try:
            tool_func = self._tools[normalized_name]['function']
            # 実際の関数を呼び出す際には元の名前を使用
            original_name = self._tools[normalized_name]['original_name']
            result = await tool_func(original_name, tool_input)
            return result
        except Exception as e:
            raise ValueError(f"ツールの実行エラー: {str(e)}")

    def clear_tools(self):
        """登録されたすべてのツールをクリア"""
        self._tools.clear()
        self._name_mapping.clear()
