import boto3
import json

class BedrockClient:
    """Amazon Bedrockとの通信を担当するクラス"""
    
    def __init__(self, region_name):
        """
        BedrockClientの初期化
        
        Args:
            region_name (str): AWSリージョン名
        """
        # IAMロールを使用して認証（認証情報の明示的な指定は不要）
        self.client = boto3.client('bedrock-runtime', region_name=region_name)
        self.model_id = "us.amazon.nova-pro-v1:0"
    
    def generate_response(self, message):
        """
        メッセージに対する応答を生成（Converse API使用）
        
        Args:
            message (str): 入力メッセージ
            
        Returns:
            str: 生成された応答
        """
        # Converse APIのリクエスト形式
        request_body = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "text": message
                        }
                    ]
                }
            ],
            "anthropic_version": "bedrock-2023-05-31"
        }
        
        try:
            response = self.client.converse(
                modelId=self.model_id,
                messages=request_body["messages"]
            )
            
            # レスポンスから応答テキストを抽出
            response_text = response['messages'][0]['content'][0]['text']
            return response_text
        except Exception as e:
            print(f"Error generating response: {e}")
            return "すみません、応答の生成中にエラーが発生しました。"
