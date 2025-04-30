import json
import time
import pytest
from unittest.mock import patch, MagicMock
from bottle import response

def test_index_endpoint(test_client):
    """ルートエンドポイントのテスト"""
    resp = test_client.get('/')
    assert resp.status_code == 200
    assert resp.json == {'status': 'ok', 'message': 'API is running'}

@patch('src.presentation.api.signature_verifier')
def test_slack_events_challenge(mock_verifier, test_client, slack_event_challenge):
    """Slackチャレンジリクエストのテスト"""
    # 署名検証をモック
    mock_verifier.is_valid.return_value = True
    
    # 署名検証をバイパスするためのヘッダーを追加
    headers = {
        'X-Slack-Request-Timestamp': str(int(time.time())),
        'X-Slack-Signature': 'v0=dummy_signature'
    }
    
    resp = test_client.post_json('/default/slack-subscriptions', slack_event_challenge, headers=headers)
    assert resp.status_code == 200
    assert resp.json == {"challenge": "test_challenge"}

@patch('src.presentation.api.signature_verifier')
def test_slack_events_message(mock_verifier, test_client, slack_event_message, mock_slack_service):
    """Slackメッセージイベントのテスト"""
    # 署名検証をモック
    mock_verifier.is_valid.return_value = True
    
    headers = {
        'X-Slack-Request-Timestamp': str(int(time.time())),
        'X-Slack-Signature': 'v0=dummy_signature'
    }
    
    resp = test_client.post_json('/default/slack-subscriptions', slack_event_message, headers=headers)
    assert resp.status_code == 200
    assert resp.body == b'{}'  # 空のJSONオブジェクト
    
    # SlackServiceのhandle_eventメソッドが呼ばれたことを確認
    mock_slack_service.handle_event.assert_called_once_with(slack_event_message)

@patch('src.presentation.api.signature_verifier')
@patch('src.presentation.api.time')
def test_slack_events_invalid_request(mock_time, mock_verifier, test_client):
    """無効なリクエストのテスト（署名検証失敗とヘッダー不足を統合）"""
    # 現在時刻をモック
    current_time = int(time.time())
    mock_time.time.return_value = current_time
    
    # 1. 署名検証失敗のケース
    mock_verifier.is_valid.return_value = False
    
    headers = {
        'X-Slack-Request-Timestamp': str(current_time),
        'X-Slack-Signature': 'invalid_signature'
    }
    
    resp = test_client.post_json(
        '/default/slack-subscriptions', 
        {"type": "event_callback"}, 
        headers=headers,
        expect_errors=True
    )
    
    assert resp.status_code == 403
    assert resp.json['status'] == 'error'
    assert resp.json['message'] == 'Invalid request signature'
    
    # 2. ヘッダー不足のケース
    resp = test_client.post_json(
        '/default/slack-subscriptions', 
        {"type": "event_callback"}, 
        expect_errors=True
    )
    
    assert resp.status_code == 403
    assert resp.json['status'] == 'error'
    assert resp.json['message'] == 'Missing verification headers'

@patch('src.presentation.api.signature_verifier')
def test_error_handlers(mock_verifier, test_client, mock_slack_service):
    """エラーハンドラーのテスト（エラー処理を統合）"""
    # 署名検証をモック
    mock_verifier.is_valid.return_value = True
    
    # エラーハンドラーのテスト（例外発生ケース）
    mock_slack_service.handle_event.side_effect = Exception("Test error")
    
    # 署名検証をバイパスするためのヘッダーを追加
    headers = {
        'X-Slack-Request-Timestamp': str(int(time.time())),
        'X-Slack-Signature': 'v0=dummy_signature'
    }
    
    resp = test_client.post_json(
        '/default/slack-subscriptions', 
        {"type": "event_callback", "event": {"type": "message"}}, 
        headers=headers,
        expect_errors=True
    )
    
    assert resp.status_code == 400  # APIでは例外をキャッチして400を返す
    assert resp.json['status'] == 'error'
    assert resp.json['message'] == 'Test error'
