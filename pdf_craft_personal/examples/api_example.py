#!/usr/bin/env python3
"""
PDF Craft API 模式使用示例

展示如何使用远程AI API进行PDF转换
"""

from pdf_craft import transform_markdown, transform_epub
from pdf_craft.ai_api import AIAPIClient, load_config

def main():
    # 方式1：使用默认配置（自动加载.env文件）
    print("=== 方式1：使用默认配置 ===")
    result1 = transform_markdown(
        pdf_path="input.pdf",
        markdown_path="output_api.md", 
        markdown_assets_path="images_api",
        use_remote_api=True,  # 启用API模式
    )
    print(f"转换完成，使用tokens: input={result1.input_tokens}, output={result1.output_tokens}")
    
    # 方式2：手动创建API客户端
    print("\n=== 方式2：手动创建API客户端 ===")
    config = load_config()
    api_client = AIAPIClient(config)
    
    result2 = transform_epub(
        pdf_path="input.pdf",
        epub_path="output_api.epub",
        use_remote_api=True,
        api_client=api_client,  # 使用自定义客户端
    )
    print(f"转换完成，使用tokens: input={result2.input_tokens}, output={result2.output_tokens}")
    
    # 方式3：混合模式 - 根据条件选择
    print("\n=== 方式3：智能选择模式 ===")
    use_api = True  # 可以根据文件大小、网络状况等条件决定
    
    result3 = transform_markdown(
        pdf_path="input.pdf",
        markdown_path="output_smart.md",
        use_remote_api=use_api,
        # 如果API调用失败，可以手动fallback到本地模式
        ignore_ocr_errors=True,
    )
    print(f"转换完成，使用tokens: input={result3.input_tokens}, output={result3.output_tokens}")

def test_api_connection():
    """测试API连接"""
    try:
        from PIL import Image
        import numpy as np
        
        # 创建一个测试图像
        test_image = Image.fromarray(
            np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        )
        
        client = AIAPIClient()
        response = client.recognize_image(test_image)
        print("API连接测试成功")
        print(f"响应: {response}")
        
    except Exception as e:
        print(f"API连接测试失败: {e}")

if __name__ == "__main__":
    # 首先测试API连接
    test_api_connection()
    
    # 然后运行转换示例
    # main()  # 取消注释以运行实际转换