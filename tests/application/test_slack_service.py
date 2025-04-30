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
def test_dispatch_event_app_mention(mock_thread, service):
    """app_mentionイベントのディスパッチテスト"""
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
def test_dispatch_event_direct_message(mock_thread, service):
    """DMメッセージのディスパッチテスト"""
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
    mock_slack_client.get_thread_messages.return_value = [
        {"text": "<@U12345> こんにちは", "ts": "1234567890.123456"},
    ]
    mock_bedrock_client.generate_response.return_value = "こんにちは！何かお手伝いできることはありますか？"
    
    # _process_responseをモック化
    service._process_response = MagicMock()
    
    # テスト実行
    service._handle_mention("C12345", "1234567890.123456")
    
    # 検証
    mock_slack_client.get_thread_messages.assert_called_once_with("C12345", "1234567890.123456")
    mock_bedrock_client.generate_response.assert_called_once()
    service._process_response.assert_called_once()

def test_handle_direct_message_single(service, mock_slack_client, mock_bedrock_client):
    """単一DMメッセージ処理のテスト"""
    # モックの設定
    mock_bedrock_client.generate_response.return_value = "こんにちは！何かお手伝いできることはありますか？"
    
    # _process_responseをモック化
    service._process_response = MagicMock()
    service._remove_mention_tags = MagicMock(return_value="こんにちは")
    
    # テスト実行（単一メッセージ）
    service._handle_direct_message("D12345", "1234567890.123456", True)
    
    # 検証
    service._remove_mention_tags.assert_called_once_with("1234567890.123456")
    mock_bedrock_client.generate_response.assert_called_once()
    service._process_response.assert_called_once()

def test_handle_direct_message_thread(service, mock_slack_client, mock_bedrock_client):
    """スレッドDMメッセージ処理のテスト"""
    # モックの設定
    mock_slack_client.get_thread_messages.return_value = [
        {"text": "こんにちは", "ts": "1234567890.123456"},
    ]
    mock_bedrock_client.generate_response.return_value = "こんにちは！何かお手伝いできることはありますか？"
    
    # _process_responseをモック化
    service._process_response = MagicMock()
    service._create_conversation_history = MagicMock(return_value=[{"role": "user", "content": [{"text": "こんにちは"}]}])
    
    # テスト実行（スレッドメッセージ）
    service._handle_direct_message("D12345", "1234567890.123456", False)
    
    # 検証
    mock_slack_client.get_thread_messages.assert_called_once_with("D12345", "1234567890.123456")
    service._create_conversation_history.assert_called_once()
    mock_bedrock_client.generate_response.assert_called_once()
    service._process_response.assert_called_once()

def test_create_conversation_history(service):
    """会話履歴作成のテスト"""
    # テストデータ
    messages = [
        {"text": "<@U12345> こんにちは", "ts": "1234567890.123456"},
        {"text": "こんにちは！何かお手伝いできることはありますか？", "bot_id": "B12345", "ts": "1234567890.123457"},
        {"text": "天気を教えて", "ts": "1234567890.123458"}
    ]
    
    # テスト実行
    result = service._create_conversation_history(messages)
    
    # 検証
    assert len(result) == 3
    assert result[0]["role"] == "user"
    assert result[0]["content"][0]["text"] == "こんにちは"
    assert result[1]["role"] == "assistant"
    assert result[2]["role"] == "user"

def test_remove_mention_tags(service):
    """メンションタグ削除のテスト"""
    # テストデータ
    text = "<@U12345> こんにちは <@U67890> 元気ですか？"
    
    # テスト実行
    result = service._remove_mention_tags(text)
    
    # 検証
    assert result == "こんにちは  元気ですか？"

def test_process_response_success(service, mock_slack_client):
    """応答処理の成功テスト"""
    # モックの設定
    mock_slack_client.send_message.return_value = {"success": True, "ts": "1234567890.123456"}
    service._update_message_with_response = MagicMock()
    service.converter.markdown_to_slack_format = MagicMock(return_value="こんにちは！")
    
    # テスト実行
    result = service._process_response("C12345", "1234567890.123456", "こんにちは！")
    
    # 検証
    mock_slack_client.send_message.assert_called_once()
    service.converter.markdown_to_slack_format.assert_called_once_with("こんにちは！")
    service._update_message_with_response.assert_called_once()
    assert result["success"] is True
    assert result["temp_ts"] == "1234567890.123456"

def test_process_response_no_timestamp(service, mock_slack_client):
    """タイムスタンプなしの応答処理テスト"""
    # モックの設定
    mock_slack_client.send_message.return_value = {"success": False}
    mock_slack_client.send_long_message = MagicMock()
    service.converter.markdown_to_slack_format = MagicMock(return_value="こんにちは！")
    
    # テスト実行
    result = service._process_response("C12345", "1234567890.123456", "こんにちは！")
    
    # 検証
    mock_slack_client.send_message.assert_called_once()
    service.converter.markdown_to_slack_format.assert_called_once_with("こんにちは！")
    mock_slack_client.send_long_message.assert_called_once()
    assert result["success"] is True
    assert result["temp_ts"] is None

def test_process_response_exception(service, mock_slack_client):
    """応答処理の例外テスト"""
    # モックの設定
    mock_slack_client.send_message.return_value = {"success": True, "ts": "1234567890.123456"}
    service.converter.markdown_to_slack_format = MagicMock(side_effect=Exception("テストエラー"))
    service._handle_response_error = MagicMock()
    
    # テスト実行
    result = service._process_response("C12345", "1234567890.123456", "こんにちは！")
    
    # 検証
    mock_slack_client.send_message.assert_called_once()
    service.converter.markdown_to_slack_format.assert_called_once_with("こんにちは！")
    service._handle_response_error.assert_called_once()
    assert result["success"] is False
    assert "テストエラー" in result["error"]

def test_update_message_with_response_success(service, mock_slack_client):
    """メッセージ更新の成功テスト"""
    # モックの設定
    mock_slack_client.update_message.return_value = {"success": True}
    
    # テスト実行
    service._update_message_with_response("C12345", "1234567890.123456", "こんにちは！")
    
    # 検証
    mock_slack_client.update_message.assert_called_once_with(
        channel="C12345",
        ts="1234567890.123456",
        text="こんにちは！"
    )

def test_update_message_with_response_too_long(service, mock_slack_client):
    """長すぎるメッセージの更新テスト"""
    # モックの設定
    mock_slack_client.update_message.return_value = {"success": False, "error_code": "msg_too_long"}
    mock_slack_client.update_long_message = MagicMock()
    
    # テスト実行
    service._update_message_with_response("C12345", "1234567890.123456", "こんにちは！" * 1000)
    
    # 検証
    mock_slack_client.update_message.assert_called_once()
    mock_slack_client.update_long_message.assert_called_once_with(
        channel="C12345",
        ts="1234567890.123456",
        text="こんにちは！" * 1000
    )

def test_update_message_with_response_error(service, mock_slack_client):
    """メッセージ更新のエラーテスト"""
    # モックの設定
    mock_slack_client.update_message.return_value = {"success": False, "error_code": "invalid_ts", "error": "タイムスタンプが無効です"}
    service._show_error_message = MagicMock()
    
    # テスト実行
    service._update_message_with_response("C12345", "1234567890.123456", "こんにちは！")
    
    # 検証
    mock_slack_client.update_message.assert_called_once()
    service._show_error_message.assert_called_once()

def test_handle_response_error(service):
    """応答エラー処理のテスト"""
    # モックの設定
    service._show_error_message = MagicMock()
    exception = Exception("テストエラー")
    
    # テスト実行
    service._handle_response_error("C12345", "1234567890.123456", exception)
    
    # 検証
    service._show_error_message.assert_called_once_with(
        "C12345", 
        "1234567890.123456", 
        "エラーが発生しました: テストエラー", 
        "テストエラー"
    )

def test_show_error_message(service, mock_slack_client):
    """エラーメッセージ表示のテスト"""
    # テスト実行
    service._show_error_message("C12345", "1234567890.123456", "エラーが発生しました", "詳細なエラー情報")
    
    # 検証
    mock_slack_client.update_message.assert_called_once()
    # 呼び出し引数を確認
    args, kwargs = mock_slack_client.update_message.call_args
    assert kwargs["channel"] == "C12345"
    assert kwargs["ts"] == "1234567890.123456"
    assert kwargs["text"] == "エラーが発生しました"
    assert len(kwargs["blocks"]) == 1
    assert "詳細なエラー情報" in kwargs["blocks"][0]["text"]["text"]
