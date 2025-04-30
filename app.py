import os
import logging
import asyncio
from bottle import run
from dotenv import load_dotenv
from src.infrastructure.logger import setup_logger
from src.infrastructure.slack_client import SlackClient
from src.infrastructure.inline_bedrock_client import InlineBedrockClient
from src.application.slack_service import SlackService
from src.presentation.slack_controller import init_api

load_dotenv()

slack_bot_token = os.environ.get("SLACK_BOT_TOKEN", "xoxb-your-token")
slack_signing_secret = os.environ.get("SLACK_SIGNING_SECRET", "")
port = int(os.environ.get('PORT', 8080))
debug = os.environ.get('DEBUG', 'True').lower() == 'true'
event_retention_period = 3600
aws_region = os.environ.get("AWS_REGION", "us-west-2")
aws_profile = os.environ.get("AWS_PROFILE", "default")
mcp_config_file = os.environ.get("MCP_CONFIG_FILE", "config/mcp_servers.json")

bedrock_max_recursion_depth = int(os.environ.get("BEDROCK_MAX_RECURSION_DEPTH", 10))

level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, level_name, logging.INFO)
logger = setup_logger("slack_bot", log_level)

slack_client = SlackClient(slack_bot_token, logger)
bedrock_client = InlineBedrockClient(
    region_name=aws_region,
    config_file_path=mcp_config_file,
    max_recursion_depth=bedrock_max_recursion_depth,
    profile=aws_profile,
    logger=logger
)

# InlineAgentの初期化（非同期処理を同期的に実行）
logger.info("Initializing InlineAgent...")
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

loop.run_until_complete(bedrock_client.initialize_inline_agent())
logger.info("InlineAgent initialized")

slack_service = SlackService(
    slack_client=slack_client,
    bedrock_client=bedrock_client,
    event_retention_period=event_retention_period,
    logger=logger
)
app = init_api(slack_service, signing_secret=slack_signing_secret, custom_logger=logger)

def cleanup():
    """アプリケーション終了時のクリーンアップ処理"""
    logger.info("Cleaning up resources...")
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    loop.run_until_complete(bedrock_client.cleanup_mcp_clients())

def main():
    try:
        logger.info("Application starting...")
        logger.info(f"Starting server on port {port}")
        run(app, host='0.0.0.0', port=port, debug=debug)
    finally:
        cleanup()

if __name__ == '__main__':
    main()
