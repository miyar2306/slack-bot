import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from mcp.shared.exceptions import McpError
from src.infrastructure.custom_mcp import CustomMCPStdio
from InlineAgent.tools.mcp import MCPStdio


@pytest.fixture
def custom_mcp_stdio():
    """CustomMCPStdioのインスタンスを作成するフィクスチャ"""
    mcp = CustomMCPStdio()
    mcp.session = AsyncMock()
    mcp.callable_tools = {}
    return mcp


class TestCustomMCPStdio:
    """CustomMCPStdioクラスのテスト"""
    
    @pytest.mark.asyncio
    async def test_set_callable_tool_success(self, custom_mcp_stdio):
        """set_callable_toolメソッドの成功ケースのテスト"""
        # ツールリストのモック
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        
        # list_toolsの戻り値を設定
        mock_list_tools = MagicMock()
        mock_list_tools.tools = [mock_tool]
        custom_mcp_stdio.session.list_tools = AsyncMock(return_value=mock_list_tools)
        
        # call_toolの戻り値を設定
        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "成功結果"
        mock_response.content = [mock_content]
        custom_mcp_stdio.session.call_tool = AsyncMock(return_value=mock_response)
        
        # テスト対象メソッドを呼び出し
        await custom_mcp_stdio.set_callable_tool(set())
        
        # 検証
        assert "test_tool" in custom_mcp_stdio.callable_tools
        result = await custom_mcp_stdio.callable_tools["test_tool"](param="value")
        assert result == "成功結果"
        custom_mcp_stdio.session.call_tool.assert_called_once_with("test_tool", arguments={"param": "value"})
    
    @pytest.mark.asyncio
    async def test_set_callable_tool_mcp_error(self, custom_mcp_stdio):
        """set_callable_toolメソッドのMCPエラーケースのテスト"""
        # ツールリストのモック
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        
        # list_toolsの戻り値を設定
        mock_list_tools = MagicMock()
        mock_list_tools.tools = [mock_tool]
        custom_mcp_stdio.session.list_tools = AsyncMock(return_value=mock_list_tools)
        
        # McpErrorを作成
        error = MagicMock()
        error.message = "MCPエラー"
        
        # call_toolの例外を設定
        custom_mcp_stdio.session.call_tool = AsyncMock(side_effect=McpError(error))
        
        # テスト対象メソッドを呼び出し
        await custom_mcp_stdio.set_callable_tool(set())
        
        # 検証
        assert "test_tool" in custom_mcp_stdio.callable_tools
        result = await custom_mcp_stdio.callable_tools["test_tool"](param="value")
        assert result == "Error: MCPエラー"
        custom_mcp_stdio.session.call_tool.assert_called_once_with("test_tool", arguments={"param": "value"})
    
    @pytest.mark.asyncio
    async def test_set_callable_tool_general_error(self, custom_mcp_stdio):
        """set_callable_toolメソッドの一般エラーケースのテスト"""
        # ツールリストのモック
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        
        # list_toolsの戻り値を設定
        mock_list_tools = MagicMock()
        mock_list_tools.tools = [mock_tool]
        custom_mcp_stdio.session.list_tools = AsyncMock(return_value=mock_list_tools)
        
        # call_toolの例外を設定
        custom_mcp_stdio.session.call_tool = AsyncMock(side_effect=Exception("一般エラー"))
        
        # テスト対象メソッドを呼び出し
        await custom_mcp_stdio.set_callable_tool(set())
        
        # 検証
        assert "test_tool" in custom_mcp_stdio.callable_tools
        result = await custom_mcp_stdio.callable_tools["test_tool"](param="value")
        assert result == "Error: 一般エラー"
        custom_mcp_stdio.session.call_tool.assert_called_once_with("test_tool", arguments={"param": "value"})
    
    @pytest.mark.asyncio
    async def test_set_available_tools_skip_large_params(self):
        """set_available_toolsメソッドでパラメータが5つ以上のツールをスキップするテスト"""
        # CustomMCPStdioのインスタンスを作成
        custom_mcp = CustomMCPStdio()
        custom_mcp.session = AsyncMock()
        custom_mcp.function_schema = {"functions": []}
        
        # ツールリストのモック
        mock_tool1 = MagicMock()
        mock_tool1.name = "tool1"
        mock_tool1.description = "Tool 1 description"
        mock_tool1.inputSchema = {
            "properties": {
                "param1": {"description": "Param 1", "type": "string"},
                "param2": {"description": "Param 2", "type": "string"},
                "param3": {"description": "Param 3", "type": "string"},
                "param4": {"description": "Param 4", "type": "string"},
                "param5": {"description": "Param 5", "type": "string"}
            },
            "required": ["param1", "param2"]
        }
        
        mock_tool2 = MagicMock()
        mock_tool2.name = "tool2"
        mock_tool2.description = "Tool 2 description"
        mock_tool2.inputSchema = {
            "properties": {
                "param1": {"description": "Param 1", "type": "string"},
                "param2": {"description": "Param 2", "type": "string"}
            },
            "required": ["param1"]
        }
        
        # list_toolsの戻り値を設定
        mock_list_tools = MagicMock()
        mock_list_tools.tools = [mock_tool1, mock_tool2]
        custom_mcp.session.list_tools = AsyncMock(return_value=mock_list_tools)
        
        # テスト対象メソッドを呼び出し
        await custom_mcp.set_available_tools(set())
        
        # 検証
        assert len(custom_mcp.function_schema["functions"]) == 1
        assert custom_mcp.function_schema["functions"][0]["name"] == "tool2"
