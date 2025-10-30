# --- 1. 构建阶段 ---
# 使用官方 Python 镜像作为构建器
FROM python:3.10-slim as builder

# 设置并激活虚拟环境
# 这可以确保我们的依赖与系统 Python 隔离
ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# 复制依赖文件
WORKDIR /app
COPY requirements.txt .

# 安装依赖
# 使用 --no-cache-dir 保持镜像层更小
RUN pip install --no-cache-dir -r requirements.txt


# --- 2. 运行阶段 ---
# 使用一个干净的、相同版本的 slim 镜像
FROM python:3.10-slim

# 【Cloud Run 优化】安装 curl，用于健康检查
# 保持容器整洁
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 创建非特权用户和组
RUN groupadd -r appuser && useradd --no-create-home -r -g appuser appuser

# 从构建器阶段复制已安装的虚拟环境
COPY --from=builder /opt/venv /opt/venv

# 复制应用程序代码
WORKDIR /app
COPY . .

# 更改文件所有权为非特权用户
RUN chown -R appuser:appuser /app

# 切换到非特权用户
USER appuser

# 设置环境变量
ENV PATH="/opt/venv/bin:$PATH" 
ENV PYTHONUNBUFFERED=1         

# 暴露端口 (主要用于文档目的，Cloud Run 会覆盖它)
EXPOSE 8080

# 启动 uvicorn 生产服务器
# 1. 'server:app': 指向 server.py 文件中的 'app' FastAPI 实例
# 2. '--host 0.0.0.0': 监听所有网络接口 (Cloud Run 要求)
# 3. '--port $PORT': 使用 Cloud Run 注入的环境变量 $PORT (最关键！)
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "$PORT"]