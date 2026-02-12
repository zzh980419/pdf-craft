#!/bin/bash
# 快速启动生产环境脚本

set -e

echo "=== PDF Craft 生产环境启动 ==="

# 检查环境文件
if [ ! -f ".env" ]; then
    echo "❌ .env 文件不存在，请先配置环境变量"
    echo "参考 .env.example 创建 .env 文件"
    exit 1
fi

# 检查Python版本
python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "Python版本: $python_version"

if [ ! $(python3 -c 'import sys; print(sys.version_info >= (3, 10))') = "True" ]; then
    echo "❌ 需要Python 3.10或更高版本"
    exit 1
fi

# 创建虚拟环境（如果不存在）
if [ ! -d "venv" ]; then
    echo "创建Python虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate

# 升级pip
pip install --upgrade pip

# 安装依赖
echo "安装依赖..."
if [ -f "poetry.lock" ] && command -v poetry &> /dev/null; then
    echo "使用Poetry安装依赖..."
    poetry install --no-dev
else
    echo "使用pip安装依赖..."
    pip install -r requirements-prod.txt
    pip install pdf2image pypdf doc-page-extractor==1.0.12 \
        epub-generator pylatexenc pyahocorasick pillow
fi

# 创建输出目录
mkdir -p outputs

# 检查API配置
echo "检查API配置..."
python3 -c "
from pdf_craft.ai_api.config import load_config
try:
    config = load_config()
    print(f'✅ API配置正常: {config.base_url}')
    print(f'   模型: {config.default_model}')
except Exception as e:
    print(f'❌ API配置错误: {e}')
    exit(1)
"

if [ $? -ne 0 ]; then
    exit 1
fi

# 健康检查
echo "启动健康检查服务器..."
python3 -c "
from app import app
try:
    with app.test_client() as client:
        response = client.get('/health')
        if response.status_code == 200:
            print('✅ 应用健康检查通过')
        else:
            print(f'❌ 健康检查失败: {response.status_code}')
            exit(1)
except Exception as e:
    print(f'❌ 应用启动失败: {e}')
    exit(1)
"

if [ $? -ne 0 ]; then
    exit 1
fi

# 选择启动方式
echo ""
echo "选择启动方式:"
echo "1) 开发模式 (Flask dev server)"
echo "2) 生产模式 (Gunicorn)"
echo "3) 后台运行 (Gunicorn daemon)"

read -p "请选择 (1-3): " choice

case $choice in
    1)
        echo "启动开发模式..."
        export FLASK_ENV=development
        python3 app.py
        ;;
    2)
        echo "启动生产模式..."
        workers=$(nproc)
        if [ $workers -gt 4 ]; then
            workers=4
        fi
        echo "使用 $workers 个工作进程"
        gunicorn --bind 0.0.0.0:1157 \
                 --workers $workers \
                 --timeout 300 \
                 --access-logfile - \
                 --error-logfile - \
                 app:app
        ;;
    3)
        echo "启动后台模式..."
        workers=$(nproc)
        if [ $workers -gt 4 ]; then
            workers=4
        fi
        gunicorn --bind 0.0.0.0:1157 \
                 --workers $workers \
                 --timeout 300 \
                 --daemon \
                 --pid pdf-craft.pid \
                 --access-logfile logs/access.log \
                 --error-logfile logs/error.log \
                 app:app
        echo "✅ 服务已在后台启动"
        echo "PID文件: pdf-craft.pid"
        echo "访问: http://localhost:1157"
        echo "停止服务: kill \$(cat pdf-craft.pid)"
        ;;
    *)
        echo "无效选择"
        exit 1
        ;;
esac