import os
import logging
from bottle import run
from dotenv import load_dotenv
from src.infrastructure.logger import setup_logger
from src.infrastructure.slack_client import SlackClient
from src.infrastructure.bedrock_client import BedrockClient
from src.application.slack_service import SlackService
from src.presentation.api import SlackAPI

def main():
    """Application entry point"""
    load_dotenv()
    
    # Load configuration from environment variables
    slack_bot_token = os.environ.get("SLACK_BOT_TOKEN", "xoxb-your-token")
    slack_signing_secret = os.environ.get("SLACK_SIGNING_SECRET", "")
    port = int(os.environ.get('PORT', 8080))
    debug = os.environ.get('DEBUG', 'True').lower() == 'true'
    event_retention_period = 3600  # 1 hour
    aws_region = os.environ.get("AWS_REGION", "us-west-2")
    mcp_config_file = os.environ.get("MCP_CONFIG_FILE", "config/mcp_servers.json")
    
    # Bedrock設定
    bedrock_max_recursion_depth = int(os.environ.get("BEDROCK_MAX_RECURSION_DEPTH", 10))
    
    # Set up logging
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, level_name, logging.INFO)
    logger = setup_logger("slack_bot", log_level)
    logger.info("Application starting...")
    
    # Set up services
    slack_client = SlackClient(slack_bot_token, logger)
    bedrock_client = BedrockClient(
        region_name=aws_region,
        config_file_path=mcp_config_file,
        max_recursion_depth=bedrock_max_recursion_depth,
        logger=logger
    )
    slack_service = SlackService(
        slack_client=slack_client,
        bedrock_client=bedrock_client,
        event_retention_period=event_retention_period,
        logger=logger
    )
    slack_api = SlackAPI(slack_service, signing_secret=slack_signing_secret, logger=logger)
    
    # Get and run the application
    app = slack_api.get_app()
    logger.info(f"Starting server on port {port}")
    run(app, host='0.0.0.0', port=port, debug=debug)

if __name__ == '__main__':
    main()
