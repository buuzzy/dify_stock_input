import os
import sys
import logging
import functools
from typing import Dict, Any, Callable

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from supabase import create_client, Client
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
# 【修复1】移除不再需要的 Response 导入
# from starlette.responses import Response 
from mcp.server.sse import SseServerTransport

# --- 1. 日志配置 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)

# --- 2. 错误处理装饰器 ---
def supabase_tool_handler(func: Callable) -> Callable:
    """统一处理 Supabase 查询的错误和日志"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logging.info(f"调用工具: {func.__name__}")
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logging.error(f"工具 {func.__name__} 执行出错: {e}", exc_info=True)
            return f"查询失败: {str(e)}"
    return wrapper

# --- 3. 初始化 ---
load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
PORT = int(os.environ.get("PORT", 8080))

# 环境变量检查
if not SUPABASE_URL or not SUPABASE_KEY:
    logging.error("环境变量 SUPABASE_URL 或 SUPABASE_KEY 未设置")
    sys.exit(1)

assert isinstance(SUPABASE_URL, str), "SUPABASE_URL 必须是字符串"
assert isinstance(SUPABASE_KEY, str), "SUPABASE_KEY 必须是字符串"

# Supabase 客户端初始化
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    logging.info("Supabase 客户端初始化成功")
except Exception as e:
    logging.error(f"Supabase 初始化失败: {e}", exc_info=True)
    sys.exit(1)

# FastAPI & MCP 初始化
app = FastAPI(
    title="股票筛选工具",
    version="1.0.0",
    description="根据特定条件筛选股票的工具"
)
mcp = FastMCP("Stock Filter Tool")

# --- 4. MCP 工具定义 ---
@mcp.tool()
@supabase_tool_handler
def get_strong_sentiment_low_pe_stocks() -> str:
    """
    查询并返回符合以下条件的股票代码列表:
    1. 市场情绪为强烈看涨 (is_strong_sentiment = true)
    2. 近三年PE历史分位数低于50% (pe_percentile_3y < 50)
    """
    response = supabase.table('stocks') \
        .select('stock_code') \
        .eq('is_strong_sentiment', True) \
        .lt('pe_percentile_3y', 50) \
        .execute()

    if not response.data:
        return "未找到符合条件的股票。"

    stock_codes: list[str] = []
    for item in response.data:
        if isinstance(item, dict):
            code = item.get('stock_code')
            if code and isinstance(code, str):
                stock_codes.append(code)
    
    if not stock_codes:
        return "查询到数据但无法提取有效的股票代码。"
        
    return f"查询成功，找到 {len(stock_codes)} 个符合条件的股票: {', '.join(stock_codes)}"

@app.get("/")
async def health_check() -> Dict[str, str]:
    """健康检查端点"""
    return {"status": "healthy"}

# --- 5. MCP SSE 集成 (关键修复) ---
MCP_BASE_PATH = "/sse"
try:
    messages_full_path = f"{MCP_BASE_PATH}/messages/"
    sse_transport = SseServerTransport(messages_full_path)

    # 【修复2】函数签名必须返回 -> None
    # SseServerTransport 会接管响应流，函数本身不应返回任何值。
    async def handle_mcp_sse_handshake(request: Request) -> None:
        """
        处理 MCP 的 SSE 握手。
        """
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as (read_stream, write_stream):
            await mcp._mcp_server.run(
                read_stream, write_stream, mcp._mcp_server.create_initialization_options()
            )
        # 【修复3】移除 "return Response(status_code=200)"
        # 这一行是导致 "Invalid content type" 错误的根源。
        # return Response(status_code=200) # <--- 已删除

    @mcp.prompt()
    def usage_guide() -> str:
        """提供使用指南"""
        return """欢迎使用股票筛选工具！
直接调用 `get_strong_sentiment_low_pe_stocks()` 即可开始查询。
"""

    # 【修复4】添加 # type: ignore
    # 告诉 Starlette/FastAPI 框架，我们知道这个路由不返回标准 Response，
    # 这是符合预期的，请不要报错。
    app.add_route(MCP_BASE_PATH, handle_mcp_sse_handshake, methods=["GET"])  # type: ignore
    app.mount(messages_full_path, sse_transport.handle_post_message)
    logging.info("MCP SSE 集成设置完成")

except Exception as e:
    logging.critical(f"应用 MCP SSE 设置时发生严重错误: {e}", exc_info=True)
    sys.exit(1)

# --- 6. 启动服务器 ---
if __name__ == "__main__":
    logging.info(f"启动服务器，监听端口: {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)