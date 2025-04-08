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
        self.model_id = "amazon.titan-text-express-v1"  # Novaモデル
    
    def generate_response(self, message):
        """
        メッセージに対する応答を生成
        
        Args:
            message (str): 入力メッセージ
            
        Returns:
            str: 生成された応答
        """
        
        messages = [{
                        "role": "user",
                        "content": [{"text": message}]
                    }]
        
        system = [
                {
                    "text": "You are a helpful AI assistant. You have access to the following tools: Speak in Japanese"
                }
            ]
        
        try:
            # invoke_modelメソッドを使用
            response = self.client.converse(
                        modelId=self.model_id,
                        messages=messages,
                        system=system,
                        inferenceConfig={
                            "maxTokens": 300,
                            "topP": 0.1,
                            "temperature": 0.3
                        },
            )
            
            # レスポンスのボディを解析
            response_body = json.loads(response.get('body').read())
            
            # 応答テキストを抽出
            return response_body.get('results')[0].get('outputText')
        except Exception as e:
            print(f"Error generating response: {e}")
            return "すみません、応答の生成中にエラーが発生しました。"
