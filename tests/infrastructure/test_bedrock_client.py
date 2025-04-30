import pytest
import json
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch, mock_open
from src.infrastructure.bedrock_client import BedrockClient, ensure_async_loop, error_handler

@pytest.fixture
def mock_logger():
    """ロガーのモックを作成するフィクスチャ"""
    return MagicMock()

@pytest.fixture
def mock_boto3_client():
    """boto3クライアントのモックを作成するフィクスチャ"""
    with patch('boto3.client') as mock_client:
        yield mock_client.return_value

@pytest.fixture
def mock_mcp_config():
    """MCP設定のモックを作成するフィクスチャ"""
    return {
        "test_server": {
            "command": "test_command",
            "args": ["arg1", "arg2"],
            "env": {"ENV_VAR": "value"}
        }
    }

@pytest.fixture
def bedrock_client(mock_logger, mock_boto3_client):
    """BedrockClientのインスタンスを作成するフィクスチャ"""
    with patch('src.infrastructure.bedrock_client.open', mock_open(read_data='{}')):
        client = BedrockClient(
            region_name="us-west-2",
            config_file_path="test_config.json",
            max_recursion_depth=5,
            profile="test_profile",
            logger=mock_logger
        )
        client._get_or_create_event_loop = MagicMock(return_value=asyncio.new_event_loop())
        return client

class TestBedrockClient:
    """BedrockClientのテストクラス"""
    
    def test_init(self, bedrock_client, mock_logger, mock_boto3_client):
        """初期化のテスト"""
        assert bedrock_client.logger == mock_logger
        assert bedrock_client.profile == "test_profile"
        assert bedrock_client.model_id == "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
        assert bedrock_client.config_file_path == "test_config.json"
        assert bedrock_client.max_recursion_depth == 5
        assert bedrock_client.action_groups == []
        assert bedrock_client.mcp_clients == {}
        assert bedrock_client.mcp_config == {}
    
    def test_load_mcp_config(self, mock_logger):
        """MCP設定読み込みのテスト"""
        mock_config = {"test_server": {"command": "test_command"}}
        
        with patch('src.infrastructure.bedrock_client.open', mock_open(read_data=json.dumps(mock_config))):
            client = BedrockClient(region_name="us-west-2", logger=mock_logger)
            assert client.mcp_config == mock_config
    
    def test_load_mcp_config_error(self, mock_logger):
        """MCP設定読み込みエラーのテスト"""
        with patch('src.infrastructure.bedrock_client.open', side_effect=Exception("Test error")):
            client = BedrockClient(region_name="us-west-2", logger=mock_logger)
            assert client.mcp_config == {}
            mock_logger.error.assert_called_once()
    
    def test_load_system_prompt(self, bedrock_client):
        """システムプロンプト読み込みのテスト"""
        test_prompt = "Test system prompt"
        
        with patch('src.infrastructure.bedrock_client.open', mock_open(read_data=test_prompt)):
            result = bedrock_client._load_system_prompt()
            assert result == test_prompt
    
    def test_load_system_prompt_error(self, bedrock_client, mock_logger):
        """システムプロンプト読み込みエラーのテスト"""
        with patch('src.infrastructure.bedrock_client.open', side_effect=Exception("Test error")):
            result = bedrock_client._load_system_prompt()
            assert result == "You are a helpful AI assistant. Speak in Japanese"
            bedrock_client.logger.warning.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_initialize_mcp_client_and_create_action_group(self, bedrock_client, mock_logger):
        """MCPクライアント初期化とActionGroup作成のテスト"""
        # MCPStdioのモック
        mock_mcp_client = MagicMock()
        
        with patch('src.infrastructure.bedrock_client.MCPStdio.create', return_value=mock_mcp_client):
            with patch.object(bedrock_client, '_create_action_group') as mock_create_action_group:
                server_config = {
                    "command": "test_command",
                    "args": ["arg1"],
                    "env": {"TEST": "value"}
                }
                
                await bedrock_client._initialize_mcp_client_and_create_action_group("test_server", server_config)
                
                # 検証
                assert bedrock_client.mcp_clients["test_server"] == mock_mcp_client
                mock_create_action_group.assert_called_once_with("test_server", mock_mcp_client)
    
    @pytest.mark.asyncio
    async def test_initialize_mcp_client_error(self, bedrock_client, mock_logger):
        """MCPクライアント初期化エラーのテスト"""
        with patch('src.infrastructure.bedrock_client.MCPStdio.create', side_effect=Exception("Test error")):
            server_config = {
                "command": "test_command",
                "args": ["arg1"],
                "env": {"TEST": "value"}
            }
            
            await bedrock_client._initialize_mcp_client_and_create_action_group("test_server", server_config)
            
            # 検証
            assert "test_server" not in bedrock_client.mcp_clients
            bedrock_client.logger.error.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_action_group(self, bedrock_client):
        """ActionGroup作成のテスト"""
        mock_mcp_client = MagicMock()
        
        with patch('src.infrastructure.bedrock_client.ActionGroup') as MockActionGroup:
            mock_action_group = MagicMock()
            MockActionGroup.return_value = mock_action_group
            
            await bedrock_client._create_action_group("test_server", mock_mcp_client)
            
            # 検証
            MockActionGroup.assert_called_once()
            assert bedrock_client.action_groups == [mock_action_group]
            bedrock_client.logger.info.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_action_group_error(self, bedrock_client):
        """ActionGroup作成エラーのテスト"""
        mock_mcp_client = AsyncMock()
        bedrock_client.mcp_clients["test_server"] = mock_mcp_client
        
        with patch('src.infrastructure.bedrock_client.ActionGroup', side_effect=Exception("Test error")):
            await bedrock_client._create_action_group("test_server", mock_mcp_client)
            
            # 検証
            assert bedrock_client.action_groups == []
            bedrock_client.logger.error.assert_called_once()
            mock_mcp_client.cleanup.assert_called_once()
            assert "test_server" not in bedrock_client.mcp_clients
    
    def test_process_input_data_string(self, bedrock_client):
        """文字列入力処理のテスト"""
        input_data = "テスト入力"
        result = bedrock_client._process_input_data(input_data)
        assert result == input_data
    
    def test_process_input_data_slack_messages(self, bedrock_client):
        """Slackメッセージリスト入力処理のテスト"""
        input_data = [
            {"text": "こんにちは", "ts": "1234567890.123456"},
            {"text": "お元気ですか？", "bot_id": "B12345", "ts": "1234567890.123457"}
        ]
        
        # モックの設定
        mock_conversation = [
            {"role": "user", "content": [{"text": "こんにちは"}]},
            {"role": "assistant", "content": [{"text": "お元気ですか？"}]}
        ]
        bedrock_client.create_conversation_history_from_messages = MagicMock(return_value=mock_conversation)
        bedrock_client._convert_conversation_to_text = MagicMock(return_value="テスト会話")
        
        result = bedrock_client._process_input_data(input_data)
        
        # 検証
        bedrock_client.create_conversation_history_from_messages.assert_called_once_with(input_data)
        bedrock_client._convert_conversation_to_text.assert_called_once_with(mock_conversation)
        assert result == "テスト会話"
    
    def test_process_input_data_conversation(self, bedrock_client):
        """会話履歴入力処理のテスト"""
        input_data = [
            {"role": "user", "content": [{"text": "こんにちは"}]},
            {"role": "assistant", "content": [{"text": "お元気ですか？"}]}
        ]
        
        bedrock_client._convert_conversation_to_text = MagicMock(return_value="テスト会話")
        
        result = bedrock_client._process_input_data(input_data)
        
        # 検証
        bedrock_client._convert_conversation_to_text.assert_called_once_with(input_data)
        assert result == "テスト会話"
    
    def test_process_input_data_invalid_format(self, bedrock_client):
        """無効な入力形式のテスト"""
        with pytest.raises(ValueError, match="Invalid message format"):
            bedrock_client._process_input_data([{"invalid": "format"}])
        
        with pytest.raises(ValueError, match="Invalid input format"):
            bedrock_client._process_input_data(123)
    
    def test_create_conversation_history_from_messages(self, bedrock_client):
        """会話履歴作成のテスト"""
        messages = [
            {"text": "こんにちは", "ts": "1234567890.123456"},
            {"text": "お元気ですか？", "bot_id": "B12345", "ts": "1234567890.123457"},
            {"text": "はい、元気です", "ts": "1234567890.123458"}
        ]
        
        result = bedrock_client.create_conversation_history_from_messages(messages)
        
        # 検証
        assert len(result) == 3
        assert result[0]["role"] == "user"
        assert result[0]["content"][0]["text"] == "こんにちは"
        assert result[1]["role"] == "assistant"
        assert result[1]["content"][0]["text"] == "お元気ですか？"
        assert result[2]["role"] == "user"
        assert result[2]["content"][0]["text"] == "はい、元気です"
    
    def test_convert_conversation_to_text(self, bedrock_client):
        """会話履歴テキスト変換のテスト"""
        conversation = [
            {"role": "user", "content": [{"text": "こんにちは"}]},
            {"role": "assistant", "content": [{"text": "お元気ですか？"}]},
            {"role": "user", "content": [{"text": "はい、元気です"}]}
        ]
        
        result = bedrock_client._convert_conversation_to_text(conversation)
        
        # 検証
        expected = "ユーザー: こんにちは\n\nアシスタント: お元気ですか？\n\nユーザー: はい、元気です"
        assert result == expected
    
    def test_convert_conversation_to_text_complex(self, bedrock_client):
        """複雑な会話履歴テキスト変換のテスト"""
        conversation = [
            {"role": "user", "content": [{"text": "こんにちは"}, {"text": "今日の天気は？"}]},
            {"role": "assistant", "content": "晴れです"},
            {"role": "user", "content": [{"text": "ありがとう"}]}
        ]
        
        result = bedrock_client._convert_conversation_to_text(conversation)
        
        # 検証
        expected = "ユーザー: こんにちは\n今日の天気は？\n\nアシスタント: 晴れです\n\nユーザー: ありがとう"
        assert result == expected
    
    @pytest.mark.asyncio
    async def test_cleanup_mcp_clients(self, bedrock_client):
        """MCPクライアントクリーンアップのテスト"""
        # モックのMCPクライアントを設定
        mock_client1 = AsyncMock()
        mock_client2 = AsyncMock()
        bedrock_client.mcp_clients = {
            "server1": mock_client1,
            "server2": mock_client2
        }
        
        # ensure_async_loopデコレータをバイパス
        await bedrock_client.cleanup_mcp_clients.__wrapped__(bedrock_client)
        
        # 検証
        mock_client1.cleanup.assert_called_once()
        mock_client2.cleanup.assert_called_once()
        assert bedrock_client.mcp_clients == {}
    
    @pytest.mark.asyncio
    async def test_cleanup_mcp_clients_error(self, bedrock_client):
        """MCPクライアントクリーンアップエラーのテスト"""
        # モックのMCPクライアントを設定
        mock_client = AsyncMock()
        mock_client.cleanup.side_effect = Exception("Cleanup error")
        bedrock_client.mcp_clients = {"server": mock_client}
        
        # ensure_async_loopデコレータをバイパス
        await bedrock_client.cleanup_mcp_clients.__wrapped__(bedrock_client)
        
        # 検証
        mock_client.cleanup.assert_called_once()
        bedrock_client.logger.error.assert_called_once()
        assert bedrock_client.mcp_clients == {}
