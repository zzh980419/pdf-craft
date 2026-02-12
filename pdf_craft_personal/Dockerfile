# 基础镜像（Python 3.11-slim，Debian 12 版本）
FROM python:3.11-slim

# 移除无效的 Debian 源修改命令（核心修复）

# 安装核心系统依赖（直接安装，无需修改源）
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    libpoppler-cpp-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 配置国内 PyPI 源（不受 Debian 源影响，保留）
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 安装 Python 依赖
COPY requirements-prod.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements-prod.txt && \
    rm -rf /root/.cache/pip

# 复制项目代码
COPY . /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    FLASK_APP=app.py \
    PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1

# 创建输出目录 + 非 root 用户
RUN mkdir -p outputs && \
    groupadd -r appuser && useradd -r -g appuser appuser && \
    chown -R appuser:appuser /app

USER appuser

# 暴露端口
EXPOSE 1157

# 运行应用
CMD ["gunicorn", "--bind", "0.0.0.0:1157", "--workers", "1", "--timeout", "300", "app:app"]
