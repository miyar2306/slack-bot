import pytest
import json
from unittest.mock import patch, MagicMock
from src.presentation.api import init_api
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

def test_slack_event_integration(integrated_client, real_slack_service, mock_slack_client):
    """SlackイベントのAPIからSlackServiceへの統合テスト"""
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
    
    # テスト実行
    resp = integrated_client.post_json('/default/slack-subscriptions', event_data)
    
    # 検証
    assert resp.status_code == 200
    assert "Ev12345" in real_slack_service.processed_events
    
    # スレッドが開始されるのを待つ
    import time
    time.sleep(0.1)

def test_slack_challenge_integration(integrated_client):
    """Slackチャレンジリクエストの統合テスト"""
    # テストデータ
    challenge_data = {
        "token": "test_token",
        "challenge": "test_challenge",
        "type": "url_verification"
    }
    
    # テスト実行
    resp = integrated_client.post_json('/default/slack-subscriptions', challenge_data)
    
    # 検証
    assert resp.status_code == 200
    assert resp.json == {"challenge": "test_challenge"}

@patch('src.presentation.api.signature_verifier')
def test_invalid_signature_integration(mock_verifier, integrated_client):
    """無効な署名の統合テスト"""
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
        'X-Slack-Request-Timestamp': '1234567890',
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

def test_error_handling_integration(integrated_client, real_slack_service, mock_slack_client):
    """エラーハンドリングの統合テスト"""
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
    
    # テスト実行
    resp = integrated_client.post_json(
        '/default/slack-subscriptions', 
        event_data,
        expect_errors=True
    )
    
    # 検証
    assert resp.status_code == 400
    assert resp.json['status'] == 'error'
    assert resp.json['message'] == 'Integration test error'
