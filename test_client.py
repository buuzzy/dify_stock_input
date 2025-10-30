# filepath: /Users/nakocai/Documents/Projects/AIagent比赛/dify_stock_input/test_client.py
import asyncio
import json
import sys
import httpx
from httpx_sse import aconnect_sse

BASE_URL = "http://localhost:8080"
SSE_ENDPOINT = "/sse"

async def main():
    """
    主函数，遵循最终确认的 MCP 握手协议。
    """
    session_post_url: str = "" # 初始化为空字符串以解决类型问题
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with aconnect_sse(client, "GET", f"{BASE_URL}{SSE_ENDPOINT}") as event_source:
                print("✅ SSE 连接已建立，等待协议握手...")
                
                async for sse in event_source.aiter_sse():
                    print(f"  [接收到事件] event='{sse.event}', data='{sse.data}'")

                    if sse.event == "endpoint":
                        session_post_url = f"{BASE_URL}{sse.data}"
                        print(f"✅ 已获取会话端点，正在发送 'initialize' 请求...")
                        
                        init_payload = {
                            "jsonrpc": "2.0",
                            "method": "initialize",
                            "params": {
                                "protocolVersion": "1.0",
                                "clientInfo": { "name": "test-client", "version": "0.1.0" },
                                "capabilities": {}
                            },
                            "id": "init-1"
                        }
                        await client.post(session_post_url, json=init_payload)

                    # 【最终修复】收到 initialize 的成功响应后，立即调用工具
                    elif sse.event == "message":
                        data = json.loads(sse.data)
                        if data.get("id") == "init-1" and "result" in data:
                            print("✅ 握手成功，服务器已就绪！正在发送 'tools/call' 请求...")
                            
                            tool_call_payload = {
                                "jsonrpc": "2.0",
                                "method": "tools/call",
                                "params": { 
                                    "name": "get_strong_sentiment_low_pe_stocks", 
                                    "args": [],
                                    "kwargs": {} # <--- 添加这个必需的字段
                                },
                                "id": "tool-call-1"
                            }
                            await client.post(session_post_url, json=tool_call_payload)

                    elif sse.event == "mcp-tool-result":
                        result_data = json.loads(sse.data)
                        final_result = result_data.get('result')
                        
                        print("\n--- ✅ 测试成功 ---")
                        print("最终结果:")
                        print(final_result)
                        print("------------------\n")
                        break

    except httpx.ConnectError:
        print(f"\n[错误] 连接服务器失败。请确保 server.py 正在运行。", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n[错误] 测试执行期间发生意外: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())