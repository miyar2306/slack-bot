import pytest
import json
import time
from unittest.mock import patch, MagicMock
from src.presentation.slack_controller import init_api
from src.application.slack_service import SlackService

@pytest.fixture
def real_slack_service(mock_slack_client, mock_bedrock_client):
    """実際のSlackServiceインスタンスを作成するフィクスチャ"""
    return SlackService(
        slack_client=mock_slack_client,
        bedrock_client=mock_bedrock_client,
        event_retention_period=60,
        logger=MagicMock()
    )

@pytest.fixture
def integrated_app(real_slack_service):
    """SlackServiceを使用した実際のアプリケーションを作成するフィクスチャ"""
    return init_api(real_slack_service, signing_secret="test_secret")

@pytest.fixture
def integrated_client(integrated_app):
    """統合テスト用のテストクライアントを作成するフィクスチャ"""
    from webtest import TestApp
    return TestApp(integrated_app)

@patch('src.presentation.slack_controller.signature_verifier')
@patch('src.presentation.slack_controller.time')
def test_slack_event_integration(mock_time, mock_verifier, integrated_client, real_slack_service, mock_slack_client):
    """SlackイベントのAPIからSlackServiceへの統合テスト"""
    # 現在時刻をモック
    current_time = 1234567890
    mock_time.time.return_value = current_time
    
    # 署名検証をモック
    mock_verifier.is_valid.return_value = True
    
    # モックの設定
    mock_slack_client.send_message.return_value = {"success": True, "ts": "1234567890.123456"}
    
    # テストデータ
    event_data = {
        "token": "test_token",
        "team_id": "T12345",
        "api_app_id": "A12345",
        "event": {
            "type": "app_mention",
            "channel": "C12345",
            "user": "U12345",
            "text": "<@U12345> こんにちは",
            "ts": "1234567890.123456"
        },
        "type": "event_callback",
        "event_id": "Ev12345",
        "event_time": 1234567890
    }
    
    # リクエストヘッダーの設定
    headers = {
        'X-Slack-Request-Timestamp': str(current_time),
        'X-Slack-Signature': 'v0=dummy_signature'
    }
    
    # テスト実行
    resp = integrated_client.post_json('/default/slack-subscriptions', event_data, headers=headers)
    
    # 検証
    assert resp.status_code == 200
    assert "Ev12345" in real_slack_service.processed_events
    
    # スレッドが開始されるのを待つ
    import time
    time.sleep(0.1)

@patch('src.presentation.slack_controller.signature_verifier')
@patch('src.presentation.slack_controller.time')
def test_slack_challenge_integration(mock_time, mock_verifier, integrated_client):
    """Slackチャレンジリクエストの統合テスト"""
    # 現在時刻をモック
    current_time = 1234567890
    mock_time.time.return_value = current_time
    
    # 署名検証をモック
    mock_verifier.is_valid.return_value = True
    
    # テストデータ
    challenge_data = {
        "token": "test_token",
        "challenge": "test_challenge",
        "type": "url_verification"
    }
    
    # リクエストヘッダーの設定
    headers = {
        'X-Slack-Request-Timestamp': str(current_time),
        'X-Slack-Signature': 'v0=dummy_signature'
    }
    
    # テスト実行
    resp = integrated_client.post_json('/default/slack-subscriptions', challenge_data, headers=headers)
    
    # 検証
    assert resp.status_code == 200
    assert resp.json == {"challenge": "test_challenge"}

@patch('src.presentation.slack_controller.signature_verifier')
@patch('src.presentation.slack_controller.time')
def test_invalid_signature_integration(mock_time, mock_verifier, integrated_client):
    """無効な署名の統合テスト"""
    # 現在時刻をモック
    current_time = int(time.time())
    mock_time.time.return_value = current_time
    
    # モックの設定
    mock_verifier.is_valid.return_value = False
    
    # テストデータ
    event_data = {
        "token": "test_token",
        "event": {
            "type": "app_mention",
            "channel": "C12345",
            "user": "U12345",
            "text": "<@U12345> こんにちは",
            "ts": "1234567890.123456"
        },
        "type": "event_callback",
        "event_id": "Ev12345",
        "event_time": 1234567890
    }
    
    # リクエストヘッダーの設定
    headers = {
        'X-Slack-Request-Timestamp': str(current_time),
        'X-Slack-Signature': 'invalid_signature'
    }
    
    # テスト実行
    resp = integrated_client.post_json(
        '/default/slack-subscriptions', 
        event_data, 
        headers=headers,
        expect_errors=True
    )
    
    # 検証
    assert resp.status_code == 403
    assert resp.json['status'] == 'error'
    assert resp.json['message'] == 'Invalid request signature'

@patch('src.presentation.slack_controller.signature_verifier')
@patch('src.presentation.slack_controller.time')
def test_error_handling_integration(mock_time, mock_verifier, integrated_client, real_slack_service, mock_slack_client):
    """エラーハンドリングの統合テスト"""
    # 現在時刻をモック
    current_time = 1234567890
    mock_time.time.return_value = current_time
    
    # 署名検証をモック
    mock_verifier.is_valid.return_value = True
    
    # SlackServiceのhandle_eventメソッドが例外を発生させるようにモック
    real_slack_service.handle_event = MagicMock(side_effect=Exception("Integration test error"))
    
    # テストデータ
    event_data = {
        "token": "test_token",
        "team_id": "T12345",
        "api_app_id": "A12345",
        "event": {
            "type": "app_mention",
            "channel": "C12345",
            "user": "U12345",
            "text": "<@U12345> こんにちは",
            "ts": "1234567890.123456"
        },
        "type": "event_callback",
        "event_id": "Ev12345",
        "event_time": 1234567890
    }
    
    # リクエストヘッダーの設定
    headers = {
        'X-Slack-Request-Timestamp': str(current_time),
        'X-Slack-Signature': 'v0=dummy_signature'
    }
    
    # テスト実行
    resp = integrated_client.post_json(
        '/default/slack-subscriptions', 
        event_data,
        headers=headers,
        expect_errors=True
    )
    
    # 検証
    assert resp.status_code == 400
    assert resp.json['status'] == 'error'
    assert resp.json['message'] == 'Integration test error'
