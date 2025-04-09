import asyncio
from bottle import run
from dotenv import load_dotenv
from src.infrastructure.config import Config
from src.infrastructure.slack_client import SlackClient
from src.infrastructure.bedrock_client import BedrockClient
from src.infrastructure.mcp_server_manager import MCPServerManager
from src.application.slack_service import SlackService
from src.presentation.api import SlackAPI

async def initialize_mcp_servers(config):
    """MCPサーバーを初期化"""
    mcp_server_manager = MCPServerManager(config.mcp_config_file)
    await mcp_server_manager.initialize()
    return mcp_server_manager

def main():
    """アプリケーションのエントリーポイント"""
    
    # .envファイルから環境変数を読み込む
    load_dotenv()
    
    # 設定の読み込み
    config = Config()
    
    # MCPサーバーの初期化
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    mcp_server_manager = loop.run_until_complete(initialize_mcp_servers(config))
    
    # 依存関係の構築
    slack_client = SlackClient(config.slack_bot_token)
    bedrock_client = BedrockClient(
        region_name=config.aws_region,
        mcp_server_manager=mcp_server_manager
    )
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
