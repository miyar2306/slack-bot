import json
import pytest
from unittest.mock import patch, MagicMock
from bottle import response

def test_index_endpoint(test_client):
    """ルートエンドポイントのテスト"""
    resp = test_client.get('/')
    assert resp.status_code == 200
    assert resp.json == {'status': 'ok', 'message': 'API is running'}

def test_options_handler(test_client):
    """OPTIONSリクエストのテスト"""
    resp = test_client.options('/some/path')
    assert resp.status_code == 200
    assert resp.body == b'{}'  # 空のJSONオブジェクト

def test_slack_events_challenge(test_client, slack_event_challenge):
    """Slackチャレンジリクエストのテスト"""
    resp = test_client.post_json('/default/slack-subscriptions', slack_event_challenge)
    assert resp.status_code == 200
    assert resp.json == {"challenge": "test_challenge"}

def test_slack_events_message(test_client, slack_event_message, mock_slack_service):
    """Slackメッセージイベントのテスト"""
    resp = test_client.post_json('/default/slack-subscriptions', slack_event_message)
    assert resp.status_code == 200
    assert resp.body == b'{}'  # 空のJSONオブジェクト
    
    # SlackServiceのhandle_eventメソッドが呼ばれたことを確認
    mock_slack_service.handle_event.assert_called_once_with(slack_event_message)

@patch('src.presentation.api.signature_verifier')
def test_slack_events_invalid_signature(mock_verifier, test_client):
    """無効な署名のテスト"""
    # モックの設定
    mock_verifier.is_valid.return_value = False
    
    # テストデータ
    test_data = {"type": "event_callback"}
    
    # リクエストヘッダーの設定
    headers = {
        'X-Slack-Request-Timestamp': '1234567890',
        'X-Slack-Signature': 'invalid_signature'
    }
    
    # テスト実行
    resp = test_client.post_json(
        '/default/slack-subscriptions', 
        test_data, 
        headers=headers,
        expect_errors=True
    )
    
    # 検証
    assert resp.status_code == 403
    assert resp.json['status'] == 'error'
    assert resp.json['message'] == 'Invalid request signature'

@patch('src.presentation.api.signature_verifier')
def test_slack_events_missing_headers(mock_verifier, test_client):
    """ヘッダーが不足している場合のテスト"""
    # テストデータ
    test_data = {"type": "event_callback"}
    
    # テスト実行（ヘッダーなし）
    resp = test_client.post_json(
        '/default/slack-subscriptions', 
        test_data, 
        expect_errors=True
    )
    
    # 検証
    assert resp.status_code == 403
    assert resp.json['status'] == 'error'
    assert resp.json['message'] == 'Missing verification headers'

def test_error_404(test_client):
    """404エラーのテスト"""
    resp = test_client.get('/non-existent-path', expect_errors=True)
    assert resp.status_code == 404
    assert resp.json['status'] == 'error'
    assert resp.json['message'] == 'Not found'

def test_error_500(test_client, mock_slack_service):
    """500エラーのテスト"""
    # SlackServiceのhandle_eventメソッドが例外を発生させるようにモック
    mock_slack_service.handle_event.side_effect = Exception("Test error")
    
    # テストデータ
    test_data = {
        "type": "event_callback",
        "event": {"type": "message"}
    }
    
    # テスト実行
    resp = test_client.post_json(
        '/default/slack-subscriptions', 
        test_data, 
        expect_errors=True
    )
    
    # 検証
    assert resp.status_code == 400  # APIでは例外をキャッチして400を返す
    assert resp.json['status'] == 'error'
    assert resp.json['message'] == 'Test error'
