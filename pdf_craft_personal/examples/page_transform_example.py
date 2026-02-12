"""
按页转换PDF为Markdown的使用示例
"""

from pathlib import Path
from pdf_craft import transform_pages_markdown


def basic_page_transform_example():
    """基本的按页转换示例"""
    print("=== 按页转换PDF示例 ===")
    
    # PDF文件路径
    pdf_path = "document.pdf"
    
    # 执行按页转换
    page_markdowns, metering = transform_pages_markdown(
        pdf_path=pdf_path,
        use_remote_api=True,         # 使用远程API加速
        ocr_size="base",             # 使用base模型平衡速度和质量
        dpi=200,                     # 降低DPI提升速度
        markdown_assets_path="assets", # 图片资源输出目录
    )
    
    print(f"✅ 转换完成!")
    print(f"📄 总页数: {len(page_markdowns)}")
    print(f"🔢 输入tokens: {metering.input_tokens}")
    print(f"🔢 输出tokens: {metering.output_tokens}")
    
    # 处理每页内容
    for page_num, markdown_content in enumerate(page_markdowns, 1):
        print(f"\n📖 第{page_num}页 ({len(markdown_content)}字符):")
        
        # 显示前100字符作为预览
        preview = markdown_content[:100].replace('\n', ' ')
        print(f"   预览: {preview}...")
        
        # 可以在这里对每页内容进行处理
        # 例如：保存到单独文件、发送到API、分析内容等
    
    return page_markdowns, metering


def save_pages_to_files_example():
    """将每页保存为单独文件的示例"""
    print("\n=== 保存每页为单独文件示例 ===")
    
    pdf_path = "document.pdf"
    
    # 转换PDF
    page_markdowns, metering = transform_pages_markdown(
        pdf_path=pdf_path,
        use_remote_api=True,
        ocr_size="small",            # 快速模式
        keep_temp_files=False,       # 不保留临时文件
    )
    
    # 创建输出目录
    output_dir = Path("pages_output")
    output_dir.mkdir(exist_ok=True)
    
    # 保存每页为单独的markdown文件
    for page_num, markdown_content in enumerate(page_markdowns, 1):
        page_file = output_dir / f"page_{page_num:03d}.md"
        page_file.write_text(markdown_content, encoding="utf-8")
        print(f"✅ 已保存第{page_num}页到: {page_file}")
    
    # 创建索引文件
    index_content = "# 页面索引\n\n"
    for page_num in range(1, len(page_markdowns) + 1):
        index_content += f"- [第{page_num}页](page_{page_num:03d}.md)\n"
    
    index_file = output_dir / "index.md"
    index_file.write_text(index_content, encoding="utf-8")
    print(f"📋 已创建索引文件: {index_file}")


def process_specific_pages_example():
    """处理特定页面的示例"""
    print("\n=== 处理特定页面示例 ===")
    
    pdf_path = "document.pdf"
    
    # 转换PDF
    page_markdowns, metering = transform_pages_markdown(
        pdf_path=pdf_path,
        use_remote_api=True,
        ocr_size="base",
    )
    
    # 分析每页内容，查找包含特定关键词的页面
    keywords = ["目录", "摘要", "参考文献", "附录"]
    
    for page_num, markdown_content in enumerate(page_markdowns, 1):
        for keyword in keywords:
            if keyword in markdown_content:
                print(f"🔍 第{page_num}页包含关键词 '{keyword}'")
                
                # 可以对特定页面进行额外处理
                # 例如：提取标题、整理格式、单独保存等
                break
    
    # 合并前几页作为摘要
    if len(page_markdowns) >= 3:
        summary_pages = page_markdowns[:3]  # 前3页
        summary_content = "\n\n---\n\n".join(summary_pages)
        
        summary_file = Path("document_summary.md")
        summary_file.write_text(summary_content, encoding="utf-8")
        print(f"📝 已保存前3页摘要到: {summary_file}")


def batch_process_example():
    """批量处理多个PDF的示例"""
    print("\n=== 批量处理示例 ===")
    
    # 获取所有PDF文件
    pdf_files = list(Path(".").glob("*.pdf"))
    
    if not pdf_files:
        print("未找到PDF文件")
        return
    
    for pdf_file in pdf_files:
        print(f"\n📄 处理文件: {pdf_file}")
        
        try:
            # 转换PDF
            page_markdowns, metering = transform_pages_markdown(
                pdf_path=pdf_file,
                use_remote_api=True,
                ocr_size="small",  # 快速模式适合批量处理
                keep_temp_files=False,
            )
            
            # 创建以PDF文件名命名的输出目录
            output_dir = Path(pdf_file.stem + "_pages")
            output_dir.mkdir(exist_ok=True)
            
            # 保存每页
            for page_num, markdown_content in enumerate(page_markdowns, 1):
                page_file = output_dir / f"page_{page_num:03d}.md"
                page_file.write_text(markdown_content, encoding="utf-8")
            
            print(f"✅ 完成 {pdf_file}，共{len(page_markdowns)}页")
            
        except Exception as e:
            print(f"❌ 处理 {pdf_file} 失败: {e}")


def main():
    """主函数"""
    print("🚀 按页转换PDF示例程序")
    
    # 检查是否有测试文件
    if not any(Path(".").glob("*.pdf")):
        print("⚠️  当前目录下没有找到PDF文件")
        print("   请将要转换的PDF文件放到当前目录下")
        return
    
    # 运行各种示例
    try:
        basic_page_transform_example()
        save_pages_to_files_example()
        process_specific_pages_example()
        batch_process_example()
    except Exception as e:
        print(f"❌ 运行示例时出错: {e}")
        print("   请检查API配置和PDF文件是否正确")


if __name__ == "__main__":
    main()