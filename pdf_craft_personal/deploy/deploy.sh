#!/bin/bash
# 生产环境部署脚本

set -e

# 配置
APP_NAME="pdf-craft"
APP_DIR="/opt/$APP_NAME"
SERVICE_NAME="$APP_NAME.service"
USER="www-data"

echo "=== PDF Craft 生产环境部署 ==="

# 创建应用目录
sudo mkdir -p $APP_DIR
sudo chown $USER:$USER $APP_DIR

# 停止现有服务（如果存在）
if systemctl is-active --quiet $SERVICE_NAME; then
    echo "停止现有服务..."
    sudo systemctl stop $SERVICE_NAME
fi

# 复制应用文件
echo "复制应用文件..."
sudo cp -r pdf_craft/ $APP_DIR/
sudo cp app.py $APP_DIR/
sudo cp pyproject.toml $APP_DIR/
sudo cp poetry.lock $APP_DIR/
sudo cp requirements-prod.txt $APP_DIR/
sudo cp .env $APP_DIR/

# 创建虚拟环境
echo "创建Python虚拟环境..."
cd $APP_DIR
sudo -u $USER python3 -m venv venv
sudo -u $USER ./venv/bin/pip install --upgrade pip

# 安装依赖
echo "安装Python依赖..."
if command -v poetry &> /dev/null; then
    sudo -u $USER ./venv/bin/pip install poetry
    sudo -u $USER ./venv/bin/poetry config virtualenvs.create false
    sudo -u $USER PATH=$APP_DIR/venv/bin:$PATH ./venv/bin/poetry install --no-dev
else
    sudo -u $USER ./venv/bin/pip install -r requirements-prod.txt
    sudo -u $USER ./venv/bin/pip install pdf2image pypdf doc-page-extractor==1.0.12 \
        epub-generator pylatexenc pyahocorasick pillow
fi

# 创建输出目录
sudo -u $USER mkdir -p $APP_DIR/outputs

# 安装systemd服务
echo "安装systemd服务..."
sudo cp deploy/$SERVICE_NAME /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME

# 启动服务
echo "启动服务..."
sudo systemctl start $SERVICE_NAME

# 检查服务状态
echo "检查服务状态..."
sudo systemctl status $SERVICE_NAME

# 等待服务启动
sleep 5

# 健康检查
echo "执行健康检查..."
if curl -f http://localhost:1157/health > /dev/null 2>&1; then
    echo "✅ 服务部署成功！"
    echo "API地址: http://localhost:1157"
    echo "健康检查: http://localhost:1157/health"
else
    echo "❌ 服务启动失败，请检查日志："
    echo "sudo journalctl -u $SERVICE_NAME -f"
    exit 1
fi

echo ""
echo "=== 常用命令 ==="
echo "查看日志: sudo journalctl -u $SERVICE_NAME -f"
echo "重启服务: sudo systemctl restart $SERVICE_NAME"
echo "停止服务: sudo systemctl stop $SERVICE_NAME"
echo "服务状态: sudo systemctl status $SERVICE_NAME"