from bottle import run
from src.infrastructure.config import Config
from src.infrastructure.slack_client import SlackClient
from src.infrastructure.bedrock_client import BedrockClient
from src.application.slack_service import SlackService
from src.presentation.api import SlackAPI

def main():
    """アプリケーションのエントリーポイント"""
    
    # 設定の読み込み
    config = Config()
    
    # 依存関係の構築
    slack_client = SlackClient(config.slack_bot_token)
    bedrock_client = BedrockClient(region_name=config.aws_region)
    slack_service = SlackService(
        slack_client=slack_client,
        bedrock_client=bedrock_client,
        event_retention_period=config.event_retention_period
    )
    slack_api = SlackAPI(slack_service)
    
    # アプリケーションの取得
    app = slack_api.get_app()
    
    # サーバー起動
    run(app, host='0.0.0.0', port=config.port, debug=config.debug)

if __name__ == '__main__':
    main()
