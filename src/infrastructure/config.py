import os
import logging

class Config:
    """アプリケーション設定を管理するクラス"""
    
    def __init__(self):
        # Slack APIトークンの設定
        self.slack_bot_token = os.environ.get("SLACK_BOT_TOKEN", "xoxb-your-token")
        
        # サーバー設定
        self.port = int(os.environ.get('PORT', 8080))
        self.debug = os.environ.get('DEBUG', 'True').lower() == 'true'
        
        # イベント設定
        self.event_retention_period = 3600  # 1時間
        
        # AWS設定
        self.aws_region = os.environ.get("AWS_REGION", "us-west-2")
        
        # MCP設定
        self.mcp_config_file = os.environ.get("MCP_CONFIG_FILE", "config/mcp_servers.json")
        
        # ログ設定
        self.log_level = self._get_log_level()
    
    def _get_log_level(self):
        """
        Get log level from environment variable
        
        Returns:
            int: Logging level (from logging module)
        """
        level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
        return getattr(logging, level_name, logging.INFO)
