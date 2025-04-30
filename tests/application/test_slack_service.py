import pytest
import threading
import time
from unittest.mock import MagicMock, patch, call
from src.application.slack_service import SlackService

@pytest.fixture
def service(mock_slack_client, mock_bedrock_client):
    """SlackServiceのインスタンスを作成するフィクスチャ"""
    return SlackService(
        slack_client=mock_slack_client,
        bedrock_client=mock_bedrock_client,
        event_retention_period=60,
        logger=MagicMock()
    )

def test_handle_event_basic(service):
    """基本的なイベント処理のテスト"""
    # テストデータ
    event_data = {
        "event_id": "test_event_1",
        "event": {
            "type": "app_mention",
            "channel": "C12345",
            "ts": "1234567890.123456"
        }
    }
    
    # テスト実行
    result = service.handle_event(event_data)
    
    # 検証
    assert result is True
    assert "test_event_1" in service.processed_events
    
    # スレッドが開始されるのを待つ
    time.sleep(0.1)

def test_handle_event_duplicate(service):
    """重複イベントのテスト"""
    # テストデータ
    event_data = {
        "event_id": "test_event_2",
        "event": {
            "type": "app_mention",
            "channel": "C12345",
            "ts": "1234567890.123456"
        }
    }
    
    # 1回目の実行
    service.handle_event(event_data)
    
    # 2回目の実行（重複）
    result = service.handle_event(event_data)
    
    # 検証
    assert result is True
    assert len(service.processed_events) == 1

def test_handle_event_bot_message(service):
    """ボットメッセージのテスト"""
    # テストデータ（ボットメッセージ）
    event_data = {
        "event_id": "test_event_3",
        "event": {
            "type": "message",
            "channel": "C12345",
            "ts": "1234567890.123456",
            "bot_id": "B12345"
        }
    }
    
    # テスト実行
    result = service.handle_event(event_data)
    
    # 検証
    assert result is True
    # ボットメッセージは処理されないが、イベントIDは記録される
    assert "test_event_3" in service.processed_events

def test_handle_event_exception(service):
    """例外発生時のテスト"""
    # テストデータ
    event_data = None  # Noneを渡して例外を発生させる
    
    # テスト実行
    result = service.handle_event(event_data)
    
    # 検証
    assert result is False

@patch('threading.Thread')
def test_process_event_app_mention(mock_thread, service):
    """app_mentionイベントの処理テスト"""
    # テストデータ
    event = {
        "type": "app_mention",
        "channel": "C12345",
        "ts": "1234567890.123456"
    }
    
    # テスト実行
    service.handle_event({"event_id": "test_event_4", "event": event})
    
    # 検証
    mock_thread.assert_called_once()
    mock_thread.return_value.start.assert_called_once()

@patch('threading.Thread')
def test_process_event_direct_message(mock_thread, service):
    """DMメッセージの処理テスト"""
    # テストデータ
    event = {
        "type": "message",
        "channel_type": "im",
        "channel": "D12345",
        "ts": "1234567890.123456"
    }
    
    # テスト実行
    service.handle_event({"event_id": "test_event_5", "event": event})
    
    # 検証
    mock_thread.assert_called_once()
    mock_thread.return_value.start.assert_called_once()

def test_handle_mention(service, mock_slack_client, mock_bedrock_client):
    """メンション処理のテスト"""
    # モックの設定
    mock_slack_client.send_message.return_value = {"success": True, "ts": "1234567890.123456"}
    mock_slack_client.get_thread_messages.return_value = [
        {"text": "<@U12345> こんにちは", "ts": "1234567890.123456"},
    ]
    mock_bedrock_client.generate_response.return_value = "こんにちは！何かお手伝いできることはありますか？"
    
    # テスト実行
    service._handle_mention("C12345", "1234567890.123456")
    
    # 検証
    mock_slack_client.send_message.assert_called_once()
    mock_slack_client.get_thread_messages.assert_called_once_with("C12345", "1234567890.123456")
    mock_bedrock_client.generate_response.assert_called_once()
    mock_slack_client.update_message.assert_called_once()

def test_handle_direct_message(service, mock_slack_client, mock_bedrock_client):
    """DMメッセージ処理のテスト"""
    # モックの設定
    mock_slack_client.send_message.return_value = {"success": True, "ts": "1234567890.123456"}
    mock_slack_client.get_thread_messages.return_value = [
        {"text": "こんにちは", "ts": "1234567890.123456"},
    ]
    mock_bedrock_client.generate_response.return_value = "こんにちは！何かお手伝いできることはありますか？"
    
    # テスト実行（単一メッセージ）
    service._handle_direct_message("D12345", "1234567890.123456", True)
    
    # 検証
    mock_slack_client.send_message.assert_called_once()
    mock_bedrock_client.generate_response.assert_called_once()
    mock_slack_client.update_message.assert_called_once()

def test_build_conversation_context(service):
    """会話コンテキスト構築のテスト"""
    # テストデータ
    messages = [
        {"text": "<@U12345> こんにちは", "ts": "1234567890.123456"},
        {"text": "こんにちは！何かお手伝いできることはありますか？", "bot_id": "B12345", "ts": "1234567890.123457"},
        {"text": "天気を教えて", "ts": "1234567890.123458"}
    ]
    
    # テスト実行
    result = service._build_conversation_context(messages)
    
    # 検証
    assert len(result) == 3
    assert result[0]["role"] == "user"
    assert result[0]["content"][0]["text"] == "こんにちは"
    assert result[1]["role"] == "assistant"
    assert result[2]["role"] == "user"

def test_clean_mention(service):
    """メンションタグ削除のテスト"""
    # テストデータ
    text = "<@U12345> こんにちは <@U67890> 元気ですか？"
    
    # テスト実行
    result = service._clean_mention(text)
    
    # 検証
    assert result == "こんにちは  元気ですか？"
