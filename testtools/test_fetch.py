import asyncio
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test_fetch():
    # MCPサーバーのパラメータを設定
    server_params = StdioServerParameters(
        command="uvx",
        args=["mcp-server-fetch"]
    )
    
    print("MCPサーバーに接続中...")
    
    # MCPクライアントを作成
    client = stdio_client(server_params)
    read, write = await client.__aenter__()
    
    # セッションを作成
    session = ClientSession(read, write)
    await session.__aenter__()
    await session.initialize()
    
    print("MCPサーバーに接続しました")
    
    # 利用可能なツールを取得
    print("利用可能なツールを取得中...")
    tools_result = await session.list_tools()
    print(f"利用可能なツール: {tools_result}")
    
    # fetchツールを呼び出し
    print("fetchツールを呼び出し中...")
    try:
        # タイムアウトを設定（30秒）
        fetch_result = await asyncio.wait_for(
            session.call_tool(
                "fetch", 
                arguments={
                    "url": "https://www.nytimes.com",
                    "max_length": 1000
                }
            ),
            timeout=15.0
        )
        print("fetchツールの結果:")
        # CallToolResultオブジェクトの構造を調査
        print(f"結果の型: {type(fetch_result)}")
        print(f"結果のdir: {dir(fetch_result)}")
        
        # 一般的な属性を試してみる
        if hasattr(fetch_result, 'content'):
            print("Content属性があります:")
            print(f"Content型: {type(fetch_result.content)}")
            print(f"Content: {fetch_result.content}")
            
            # contentがリストの場合
            if isinstance(fetch_result.content, list):
                for i, item in enumerate(fetch_result.content):
                    print(f"Content[{i}]の型: {type(item)}")
                    print(f"Content[{i}]のdir: {dir(item)}")
                    if hasattr(item, 'text'):
                        print(f"Content[{i}].text: {item.text}")
    except asyncio.TimeoutError:
        print("fetchツールの呼び出しがタイムアウトしました")
    except Exception as e:
        print(f"fetchツールの呼び出し中にエラーが発生しました: {e}")
    
    # セッションとクライアントをクローズ
    await session.__aexit__(None, None, None)
    await client.__aexit__(None, None, None)
    
    print("テスト完了")

if __name__ == "__main__":
    asyncio.run(test_fetch())
