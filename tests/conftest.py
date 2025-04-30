import pytest
from unittest.mock import MagicMock
from bottle import Bottle
from src.presentation.api import init_api
from src.application.slack_service import SlackService

@pytest.fixture
def mock_slack_client():
    """SlackClientのモックを作成するフィクスチャ"""
    mock = MagicMock()
    return mock

@pytest.fixture
def mock_bedrock_client():
    """BedrockClientのモックを作成するフィクスチャ"""
    mock = MagicMock()
    # 必要に応じてモックの振る舞いを設定
    return mock

@pytest.fixture
def mock_slack_service():
    """SlackServiceのモックを作成するフィクスチャ"""
    mock = MagicMock(spec=SlackService)
    # 必要に応じてモックの振る舞いを設定
    return mock

@pytest.fixture
def test_app(mock_slack_service):
    """テスト用のBottleアプリケーションを作成するフィクスチャ"""
    app = init_api(mock_slack_service, signing_secret="test_secret")
    return app

@pytest.fixture
def test_client(test_app):
    """テスト用のBottleテストクライアントを作成するフィクスチャ"""
    from webtest import TestApp
    return TestApp(test_app)

@pytest.fixture
def slack_event_challenge():
    """Slackのチャレンジイベントを作成するフィクスチャ"""
    return {
        "token": "test_token",
        "challenge": "test_challenge",
        "type": "url_verification"
    }

@pytest.fixture
def slack_event_message():
    """Slackのメッセージイベントを作成するフィクスチャ"""
    return {
        "token": "test_token",
        "team_id": "T12345",
        "api_app_id": "A12345",
        "event": {
            "type": "message",
            "channel": "C12345",
            "user": "U12345",
            "text": "Hello, bot!",
            "ts": "1234567890.123456"
        },
        "type": "event_callback",
        "event_id": "Ev12345",
        "event_time": 1234567890
    }
