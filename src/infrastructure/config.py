import os

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
