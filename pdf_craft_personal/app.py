"""
Flask API 接口 - PDF 分页解析服务

提供 RESTful API 接口用于分页解析 PDF 文件
"""

import os
import json
import time
from pathlib import Path
from typing import Dict, Any, List
from flask import Flask, request, jsonify
from pdf_craft.functions import transform_pages_markdown
from pdf_craft.ai_api.config import load_config

app = Flask(__name__)
app.config['OUTPUT_FOLDER'] = 'outputs'

# 确保输出文件夹存在
Path(app.config['OUTPUT_FOLDER']).absolute().mkdir(parents=True, exist_ok=True)


def validate_pdf_path(pdf_path: str) -> tuple[bool, str]:
    """验证PDF文件路径"""
    if not pdf_path:
        return False, "PDF path is required"

    path = Path(pdf_path)

    if not path.exists():
        return False, f"PDF file not found: {pdf_path}"

    if not path.is_file():
        return False, f"Path is not a file: {pdf_path}"

    if path.suffix.lower() != '.pdf':
        return False, f"File is not a PDF: {pdf_path}"

    return True, ""


@app.route('/health', methods=['GET'])
def health_check():
    """健康检查接口，包含远程AI API连接测试"""
    start_time = time.time()

    try:
        # 基础健康状态
        result = {
            'status': 'healthy',
            'service': 'pdf-craft-api',
            'version': '1.0.0',
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        }

        # 测试远程AI API连接
        try:
            from pdf_craft.ai_api import AIAPIClient
            config = load_config()
            client = AIAPIClient(config)

            # 发送简单测试请求
            test_response = client.recognize_text(
                images=["测试连接"],  # 简单测试文本
                prompt="请回复'连接成功'",
                model=config.default_model
            )

            result.update({
                'api_status': 'connected',
                'api_test': 'success',
                'api_response': test_response[:100] if test_response else 'Empty response',
                'api_model': config.default_model,
                'api_base_url': config.base_url
            })

        except Exception as api_error:
            result.update({
                'api_status': 'disconnected',
                'api_test': 'failed',
                'api_error': str(api_error)[:200],  # 限制错误信息长度
                'api_base_url': getattr(load_config(), 'base_url', 'Unknown')
            })

        # 计算响应时间
        duration_seconds = round(time.time() - start_time, 3)
        result['duration_seconds'] = duration_seconds

        return jsonify(result)

    except Exception as e:
        duration_seconds = round(time.time() - start_time, 3)
        return jsonify({
            'status': 'error',
            'service': 'pdf-craft-api',
            'error': str(e),
            'duration_seconds': duration_seconds
        }), 500


@app.route('/api/pdf/parse-pages', methods=['POST'])
def parse_pdf_pages():
    """
    分页解析 PDF 接口

    接受 PDF 文件路径和可选的页码数组，返回按页解析的 Markdown 内容
    """
    start_time = time.time()

    try:
        # 获取请求数据（支持 JSON 和 form 格式）
        if request.is_json:
            data = request.get_json()
        elif request.form:
            data = request.form.to_dict()
            # 处理form数据中的数组
            if 'pages' in data:
                try:
                    data['pages'] = json.loads(data['pages'])
                except (json.JSONDecodeError, TypeError):
                    data['pages'] = []
        else:
            return jsonify({'error': 'Request must contain JSON data or form data'}), 400

        if not data:
            return jsonify({'error': 'Request data is empty'}), 400

        # 获取PDF路径
        pdf_path = data.get('pdf_path')
        if not pdf_path:
            return jsonify({'error': 'pdf_path is required'}), 400

        # 验证PDF路径
        is_valid, error_msg = validate_pdf_path(pdf_path)
        if not is_valid:
            return jsonify({'error': error_msg}), 400

        # 获取页码数组参数
        pages = data.get('pages', [])
        if not isinstance(pages, list):
            return jsonify({'error': 'pages must be an array'}), 400

        # 设置输出路径
        output_name = Path(pdf_path).stem
        assets_path = Path(app.config['OUTPUT_FOLDER']).absolute() / f"{output_name}_assets"

        # 获取PDF总页数
        from pdf_craft.pdf import DefaultPDFHandler
        handler = DefaultPDFHandler()
        document = handler.open(Path(pdf_path))
        try:
            total_pdf_pages = document.pages_count
        finally:
            document.close()

        # 处理页码逻辑
        if pages:
            # 过滤有效页码
            valid_pages = []
            invalid_pages = []

            for page_num in pages:
                try:
                    page_num = int(page_num)
                    if 1 <= page_num <= total_pdf_pages:
                        valid_pages.append(page_num)
                    else:
                        invalid_pages.append(page_num)
                except (ValueError, TypeError):
                    invalid_pages.append(page_num)

            if not valid_pages:
                return jsonify({
                    'error': f'No valid pages specified. PDF has {total_pdf_pages} pages.',
                    'invalid_pages': invalid_pages
                }), 400

            # 只处理有效页面
            page_markdowns, metering = transform_pages_markdown(
                pdf_path=pdf_path,
                pages=valid_pages,
                markdown_assets_path=assets_path,
                use_remote_api=True,
                max_ocr_tokens=4096,  # 为DeepSeek-OCR设置合适的token数
                max_ocr_output_tokens=4096
            )

            # 构建选定页面列表
            selected_pages = [
                {
                    'page_number': valid_pages[i],
                    'markdown_content': content
                }
                for i, content in enumerate(page_markdowns)
            ]

            message_parts = []
            if valid_pages:
                message_parts.append(f"解析指定页面成功: {len(valid_pages)} 页")

            if invalid_pages:
                message_parts.append(f"忽略了无效页码: {invalid_pages}")

        else:
            # 处理全部页面
            page_markdowns, metering = transform_pages_markdown(
                pdf_path=pdf_path,
                pages=None,
                markdown_assets_path=assets_path,
                use_remote_api=True,
                max_ocr_tokens=4096,  # 为DeepSeek-OCR设置合适的token数
                max_ocr_output_tokens=4096
            )

            selected_pages = [
                {
                    'page_number': i + 1,
                    'markdown_content': content
                }
                for i, content in enumerate(page_markdowns)
            ]
            message_parts = ["解析全部页面成功"]

        # 计算用时
        duration_seconds = round(time.time() - start_time, 2)

        # 构建返回结果
        result = {
            'success': True,
            'pdf_path': pdf_path,
            'total_pages': total_pdf_pages,
            'processed_pages': len(selected_pages),
            'pages': selected_pages,
            'metering': {
                'input_tokens': metering.input_tokens,
                'output_tokens': metering.output_tokens
            },
            'assets_path': str(assets_path),
            'duration_seconds': duration_seconds,
            'message': '; '.join(message_parts)
        }

        return jsonify(result)

    except Exception as e:
        import traceback
        duration_seconds = round(time.time() - start_time, 2)
        
        # 记录详细的错误信息
        error_details = {
            'error': str(e),
            'error_type': type(e).__name__,
            'traceback': traceback.format_exc(),
            'success': False,
            'duration_seconds': duration_seconds
        }
        
        # 打印到服务器日志
        print(f"API Error: {error_details}")
        
        return jsonify(error_details), 500






@app.route('/api/config', methods=['GET'])
def get_config():
    """获取当前配置信息"""
    try:
        config = load_config()
        return jsonify({
            'success': True,
            'config': {
                'base_url': config.base_url,
                'default_model': config.default_model,
                'api_key_configured': bool(config.api_key),
                'timeout': getattr(config, 'timeout', 30),
                'max_retries': getattr(config, 'max_retries', 3),
            },
            'supported_ocr_sizes': ['tiny', 'small', 'base', 'large', 'gundam']
        })
    except Exception as e:
        return jsonify({
            'error': f'Failed to load config: {str(e)}',
            'success': False
        }), 500




if __name__ == '__main__':
    # 开发模式运行
    app.run(host='0.0.0.0', port=1157)
