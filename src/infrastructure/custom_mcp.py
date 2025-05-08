from typing import List, Set, Dict, Any, Callable
from mcp import ListToolsResult
from mcp.shared.exceptions import McpError
from InlineAgent.tools.mcp import MCPStdio
from InlineAgent.types import FunctionDefination
from pydantic import validate_call

class CustomMCPStdio(MCPStdio):
    """
    MCPStdioのカスタム実装。
    パラメータが5つ以上のツールをスキップし、エラーハンドリングを改善します。
    """
    
    async def set_available_tools(self, tools_to_use: Set) -> List[FunctionDefination]:
        """
        パラメータが5つ以上のツールをスキップするようにオーバーライド
        """
        if not self.session:
            raise RuntimeError("Not connected to MCP server")

        tools: ListToolsResult = await self.session.list_tools()
        tools_list = tools.tools

        if "functions" not in self.function_schema:
            self.function_schema["functions"] = list()

        for tool in tools_list:
            if len(tools_to_use) != 0 and tool.name not in tools_to_use:
                continue

            function = {
                "description": tool.description,
                "name": tool.name,
                "parameters": {},
                "requireConfirmation": "DISABLED",
            }
            
            # Process input schema properties
            if "properties" in tool.inputSchema:
                for param_name, param_details in tool.inputSchema["properties"].items():
                    function["parameters"][param_name] = {
                        "description": param_details.get("description", param_name),
                        "type": param_details.get("type", "string"),
                        "required": param_name in tool.inputSchema.get("required", []),
                    }

                # パラメータが5つ以上の場合はスキップ（例外を発生させない）
                if len(function["parameters"]) >= 5:
                    print(f"Tool '{tool.name}' has {len(function['parameters'])} parameters (>= 5) and will be skipped.")
                    continue

            self.function_schema["functions"].append(function)
            
    @validate_call
    async def set_callable_tool(self, tools_to_use: set) -> Dict[str, Callable]:
        """
        エラーハンドリングを追加したcallable関数を作成
        """
        if not self.session:
            raise RuntimeError("Not connected to MCP server")

        tools = await self.session.list_tools()
        tools_list = tools.tools

        # エラーハンドリングを追加したcallable関数を作成
        def create_callable(tool_name):
            async def callable(*args, **kwargs):
                try:
                    response = await self.session.call_tool(
                        tool_name, arguments=kwargs
                    )
                    return response.content[0].text
                except McpError as e:
                    # MCPエラーオブジェクトを文字列に変換して返す
                    return f"Error: {str(e)}"
                except Exception as e:
                    # その他の例外も文字列に変換
                    return f"Error: {str(e)}"
            return callable

        for tool in tools_list:
            if len(tools_to_use) != 0:
                if tool.name in tools_to_use:
                    self.callable_tools[tool.name] = create_callable(tool.name)
            else:
                self.callable_tools[tool.name] = create_callable(tool.name)
