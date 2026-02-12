#!/usr/bin/env python3
"""
简化的PDF转Markdown API测试
提取核心功能，方便集成到其他项目
"""
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class TimeAnalysis:
    """时间分析结果"""
    total_time: float
    setup_time: float
    conversion_time: float
    page_times: List[Dict[str, float]]
    api_times: List[float]
    avg_page_time: float
    token_rate: float  # tokens per second

    def print_analysis(self):
        """打印详细的时间分析"""
        print("\n" + "=" * 60)
        print("⏱️  详细时间分析")
        print("=" * 60)
        print(f"📊 总耗时: {self.total_time:.2f} 秒")
        print(f"🔧 初始化时间: {self.setup_time:.2f} 秒 ({self.setup_time/self.total_time*100:.1f}%)")
        print(f"🚀 转换时间: {self.conversion_time:.2f} 秒 ({self.conversion_time/self.total_time*100:.1f}%)")

        print(f"\n📄 页面处理详情:")
        for i, page_info in enumerate(self.page_times, 1):
            print(f"  第{i}页: 渲染{page_info['render']:.2f}s + API{page_info['api']:.2f}s = 总计{page_info['total']:.2f}s")

        if self.api_times:
            print(f"\n🌐 API性能:")
            print(f"  平均响应时间: {sum(self.api_times)/len(self.api_times):.2f} 秒")
            print(f"  最快响应: {min(self.api_times):.2f} 秒")
            print(f"  最慢响应: {max(self.api_times):.2f} 秒")

        print(f"\n📈 处理效率:")
        print(f"  平均每页时间: {self.avg_page_time:.2f} 秒")
        print(f"  Token处理速率: {self.token_rate:.1f} tokens/秒")
        print("=" * 60)


def convert_pdf_to_markdown_api(pdf_path: str, output_md: str = None, output_assets: str = None, enable_timing: bool = True):
    """
    使用API模式将PDF转换为Markdown

    Args:
        pdf_path: PDF文件路径
        output_md: 输出Markdown文件路径（可选）
        output_assets: 资源文件夹路径（可选）
        enable_timing: 是否启用详细时间分析（可选）

    Returns:
        dict: 包含转换结果和时间分析的字典
    """
    # 步骤1: 初始化和文件检查
    step_start = time.time()
    print("🔧 步骤1: 初始化和文件检查...")

    from pdf_craft import transform_markdown

    # 设置默认输出路径
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")

    if output_md is None:
        output_md = pdf_file.stem + "_output.md"
    if output_assets is None:
        output_assets = pdf_file.stem + "_assets"

    print(f"📄 输入文件: {pdf_file}")
    print(f"📁 文件大小: {pdf_file.stat().st_size / 1024:.1f} KB")
    step1_time = time.time() - step_start
    print(f"⏱️  步骤1耗时: {step1_time:.3f}秒")

    # 步骤2: API配置加载
    step_start = time.time()
    print("\n🔧 步骤2: API配置加载...")
    try:
        from pdf_craft.ai_api import load_config
        config = load_config()
        print(f"📡 API端点: {config.base_url}")
        print(f"🤖 模型: {config.default_model}")
        step2_time = time.time() - step_start
        print(f"⏱️  步骤2耗时: {step2_time:.3f}秒")
    except Exception as e:
        print(f"❌ API配置加载失败: {e}")
        raise

    # 记录开始时间
    start_time = time.time()
    setup_start = start_time

    # 时间分析数据
    page_times = []
    api_times = []
    current_page = {}

    # 进度回调函数（增强版）
    def on_progress(event):
        from pdf_craft.pdf import OCREventKind
        nonlocal current_page

        if event.kind == OCREventKind.START:
            current_page = {
                'page': event.page_index,
                'start_time': time.time(),
                'render_time': 0,
                'api_time': 0
            }
            print(f"📄 开始处理第 {event.page_index}/{event.total_pages} 页")

        elif event.kind == OCREventKind.RENDERED:
            if enable_timing:
                current_page['render_time'] = event.cost_time_ms / 1000.0
            print(f"🖼️  第 {event.page_index} 页渲染完成 ({event.cost_time_ms}ms)")

        elif event.kind == OCREventKind.COMPLETE:
            if enable_timing:
                # 计算API时间（总时间 - 渲染时间）
                total_page_time = time.time() - current_page['start_time']
                api_time = total_page_time - current_page['render_time']
                current_page['api_time'] = api_time
                current_page['total'] = total_page_time

                page_times.append({
                    'render': current_page['render_time'],
                    'api': api_time,
                    'total': total_page_time
                })
                api_times.append(api_time)

            print(f"✅ 第 {event.page_index} 页识别完成 (输入:{event.input_tokens}, 输出:{event.output_tokens} tokens)")
            if enable_timing:
                print(f"   ⏱️  页面耗时: 渲染{current_page['render_time']:.2f}s + API{api_time:.2f}s = 总计{total_page_time:.2f}s")

        elif event.kind == OCREventKind.FAILED:
            print(f"❌ 第 {event.page_index} 页识别失败: {event.error}")

    # 步骤3: 执行转换
    step_start = time.time()
    conversion_start = step_start
    setup_time = conversion_start - setup_start
    print(f"\n🔧 步骤3: 执行PDF转换{'（含时间分析）' if enable_timing else ''}...")
    result = transform_markdown(
        pdf_path=str(pdf_file),
        markdown_path=output_md,
        markdown_assets_path=output_assets,
        use_remote_api=True,  # 启用API模式
        includes_cover=True,
        includes_footnotes=True,
        dpi=200,
        ignore_pdf_errors=True,
        ignore_ocr_errors=False,
        on_ocr_event=on_progress,
    )

    step3_time = time.time() - step_start
    print(f"⏱️  步骤3耗时: {step3_time:.3f}秒")

    # 步骤4: 后处理和文件检查
    step_start = time.time()
    print("\n🔧 步骤4: 后处理和文件检查...")

    # 计算总耗时
    end_time = time.time()
    elapsed = end_time - start_time
    conversion_time = end_time - conversion_start

    # 检查输出文件
    output_path = Path(output_md)
    output_size = output_path.stat().st_size if output_path.exists() else 0
    print(f"📄 Markdown文件: {output_size / 1024:.1f} KB")

    # 统计资源文件
    assets_path = Path(output_assets)
    asset_count = len(list(assets_path.glob("*"))) if assets_path.exists() else 0
    print(f"📁 资源文件数量: {asset_count} 个")

    step4_time = time.time() - step_start
    print(f"⏱️  步骤4耗时: {step4_time:.3f}秒")

    # 步骤时间总结
    print(f"\n📊 各步骤时间分析:")
    print(f"  步骤1 (初始化): {step1_time:.3f}秒 ({step1_time/elapsed*100:.1f}%)")
    print(f"  步骤2 (API配置): {step2_time:.3f}秒 ({step2_time/elapsed*100:.1f}%)")
    print(f"  步骤3 (PDF转换): {step3_time:.3f}秒 ({step3_time/elapsed*100:.1f}%)")
    print(f"  步骤4 (后处理): {step4_time:.3f}秒 ({step4_time/elapsed*100:.1f}%)")

    print(f"\n🎉 转换完成!")
    print(f"⏱️  总耗时: {elapsed:.2f} 秒")
    print(f"📊 Token使用: 输入={result.input_tokens:,}, 输出={result.output_tokens:,}, 总计={result.input_tokens + result.output_tokens:,}")
    print(f"📄 输出文件: {output_md} ({output_size / 1024:.1f} KB)")
    print(f"📁 资源文件: {asset_count} 个")

    # 创建时间分析对象
    time_analysis = None
    if enable_timing and page_times:
        avg_page_time = sum(p['total'] for p in page_times) / len(page_times)
        total_tokens = result.input_tokens + result.output_tokens
        token_rate = total_tokens / elapsed if elapsed > 0 else 0

        time_analysis = TimeAnalysis(
            total_time=elapsed,
            setup_time=setup_time,
            conversion_time=conversion_time,
            page_times=page_times,
            api_times=api_times,
            avg_page_time=avg_page_time,
            token_rate=token_rate
        )

        # 打印详细分析
        time_analysis.print_analysis()

    return {
        "success": True,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "total_tokens": result.input_tokens + result.output_tokens,
        "elapsed_seconds": elapsed,
        "output_file": output_md,
        "output_size_kb": output_size / 1024,
        "assets_folder": output_assets,
        "assets_count": asset_count,
        "time_analysis": time_analysis,
        "step_times": {
            "step1_init": step1_time,
            "step2_api_config": step2_time,
            "step3_conversion": step3_time,
            "step4_postprocess": step4_time,
            "total": elapsed
        }
    }


def check_api_connection():
    """检查API连接是否正常"""
    try:
        from pdf_craft.ai_api import load_config, AIAPIClient
        from PIL import Image
        import numpy as np

        # 加载配置
        config = load_config()
        print(f"📡 API端点: {config.base_url}")
        print(f"🤖 模型: {config.default_model}")

        # 创建测试客户端
        client = AIAPIClient(config)

        # 创建简单测试图像
        test_array = np.ones((100, 300, 3), dtype=np.uint8) * 255
        test_array[40:60, 50:250] = [0, 0, 0]
        test_image = Image.fromarray(test_array)

        print("🧪 测试API连接...")
        api_start_time = time.time()
        response = client.recognize_image(test_image)
        api_elapsed = time.time() - api_start_time

        text_content = client.extract_text_content(response)
        usage = client.get_usage_info(response)

        print("✅ API连接成功!")
        print(f"📤 响应长度: {len(text_content)} 字符")
        print(f"🏷️  Token使用: 输入={usage['input_tokens']}, 输出={usage['output_tokens']}")
        print(f"⏱️  响应时间: {api_elapsed:.3f} 秒")

        return True, {
            "response_length": len(text_content),
            "input_tokens": usage['input_tokens'],
            "output_tokens": usage['output_tokens'],
            "response_time": api_elapsed
        }

    except Exception as e:
        print(f"❌ API连接失败: {e}")
        return False, {"error": str(e)}


def test_with_timing():
    """带时间分析的测试函数"""
    print("🚀 PDF转Markdown API - 时间分析测试")
    print("=" * 60)

    try:
        # 使用test.pdf进行测试
        pdf_file = "test_report.pdf"
        if not Path(pdf_file).exists():
            pdf_file = "test3.pdf"  # 备选文件

        if not Path(pdf_file).exists():
            print(f"❌ 找不到测试PDF文件")
            print("请在当前目录放置一个PDF文件进行测试")
            return

        result = convert_pdf_to_markdown_api(
            pdf_path=pdf_file,
            output_md="timing_test_output.md",
            output_assets="timing_test_assets",
            enable_timing=True  # 启用时间分析
        )

        print("\n" + "=" * 60)
        print("✅ 时间分析测试完成!")
        if result['time_analysis']:
            print("📊 时间分析数据已包含在返回结果中")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


def main():
    """主函数示例"""
    print("🚀 PDF转Markdown API简化测试")
    print("=" * 50)

    # 检查API连接
    print("1. 检查API连接...")
    connected, conn_result = check_api_connection()
    if not connected:
        print("API连接失败，请检查配置")
        return

    print("\n" + "=" * 50)

    # 转换PDF文件
    print("2. 转换PDF文件...")
    try:
        # 使用当前目录下的test3.pdf（根据修改后的测试文件）
        pdf_file = "test.pdf"
        if not Path(pdf_file).exists():
            pdf_file = "test.pdf"  # 备选文件

        if not Path(pdf_file).exists():
            print(f"❌ 找不到测试PDF文件: {pdf_file}")
            print("请在当前目录放置一个PDF文件进行测试")
            return

        result = convert_pdf_to_markdown_api(
            pdf_path=pdf_file,
            output_md="simple_output.md",
            output_assets="simple_assets"
        )

        print("\n" + "=" * 50)
        print("✅ 测试完成!")
        print(f"详细结果: {result}")

    except Exception as e:
        print(f"❌ 转换失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--timing":
        test_with_timing()
    else:
        main()
