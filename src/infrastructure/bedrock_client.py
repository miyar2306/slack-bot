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
        self.model_id = "us.amazon.nova-pro-v1:0"  # Novaモデル
    
    def generate_response(self, message_or_conversation):
        """
        メッセージまたは会話履歴に対する応答を生成
        
        Args:
            message_or_conversation: 単一のメッセージ（文字列）または会話履歴（辞書のリスト）
            
        Returns:
            str: 生成された応答
        """
        
        # 入力が文字列の場合（単一のメッセージ）
        if isinstance(message_or_conversation, str):
            messages = [{
                "role": "user",
                "content": [{"text": message_or_conversation}]
            }]
        # 入力がリストの場合（会話履歴）
        elif isinstance(message_or_conversation, list):
            messages = message_or_conversation
        else:
            return "エラー: 無効な入力形式です。"
        
        system = [
            {
                "text": "You are a helpful AI assistant. You have access to the following tools: Speak in Japanese"
            }
        ]
        
        try:
            # converseメソッドを使用
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
            
            output_message = response['output']['message']
            response_text = ""
            for content in output_message['content']:
                if 'text' in content:
                    response_text += content['text'] + "\n"
            
            # 応答テキストを抽出
            return response_text.strip()
        except Exception as e:
            print(f"Error generating response: {e}")
            return "すみません、応答の生成中にエラーが発生しました。"
