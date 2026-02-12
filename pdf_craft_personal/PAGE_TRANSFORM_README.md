# 按页转换PDF功能

这是PDF-Craft的新功能，支持将PDF按页解析，每页作为独立的Markdown字符串返回。

## 功能特点

- ✅ **页面独立**: 每页作为独立单元处理，不进行跨页拼接
- ✅ **返回列表**: 返回`List[str]`，每个元素是一页的Markdown内容
- ✅ **保持顺序**: 页面按原始顺序排列
- ✅ **完整功能**: 支持图片、表格、脚注等所有元素
- ✅ **高性能**: 支持并发处理，与原有功能性能一致
- ✅ **灵活配置**: 支持所有原有的配置选项

## 基本用法

```python
from pdf_craft import transform_pages_markdown

# 按页转换PDF
page_markdowns, metering = transform_pages_markdown(
    pdf_path="document.pdf",
    use_remote_api=True,  # 推荐使用远程API
    ocr_size="base",      # 平衡速度和质量
)

print(f"转换了 {len(page_markdowns)} 页")
for i, page_content in enumerate(page_markdowns, 1):
    print(f"第{i}页: {len(page_content)}字符")
```

## 高级用法

### 保存每页为单独文件

```python
from pathlib import Path

page_markdowns, _ = transform_pages_markdown("document.pdf")

# 创建输出目录
output_dir = Path("pages")
output_dir.mkdir(exist_ok=True)

# 保存每页
for i, content in enumerate(page_markdowns, 1):
    page_file = output_dir / f"page_{i:03d}.md"
    page_file.write_text(content, encoding="utf-8")
```

### 处理特定页面

```python
page_markdowns, _ = transform_pages_markdown("document.pdf")

# 查找包含特定关键词的页面
for i, content in enumerate(page_markdowns, 1):
    if "目录" in content:
        print(f"第{i}页包含目录")
    if "参考文献" in content:
        print(f"第{i}页是参考文献")
```

### 批量处理

```python
from pathlib import Path

pdf_files = Path(".").glob("*.pdf")

for pdf_file in pdf_files:
    page_markdowns, _ = transform_pages_markdown(pdf_file)
    
    # 为每个PDF创建独立目录
    output_dir = Path(pdf_file.stem + "_pages")
    output_dir.mkdir(exist_ok=True)
    
    for i, content in enumerate(page_markdowns, 1):
        (output_dir / f"page_{i:03d}.md").write_text(content)
```

## API参数

`transform_pages_markdown()` 支持与 `transform_markdown()` 相同的所有参数：

### 基本参数
- `pdf_path`: PDF文件路径
- `use_remote_api`: 是否使用远程API（推荐True）
- `ocr_size`: OCR模型大小 ("tiny", "small", "base", "large", "gundam")

### 性能优化参数
- `dpi`: 图像DPI，默认300，可降到200提升速度
- `use_concurrent`: 是否并发处理，默认True
- `max_workers`: 并发线程数，默认3
- `batch_size`: 批处理大小，默认3

### 内容控制参数
- `includes_cover`: 是否包含封面
- `includes_footnotes`: 是否包含脚注
- `markdown_assets_path`: 图片资源输出路径

### 调试参数
- `keep_temp_files`: 是否保留临时文件
- `analysing_path`: 临时文件存储路径

## 返回值

函数返回一个元组：`(List[str], OCRTokensMetering)`

- `List[str]`: 每页的Markdown内容列表
- `OCRTokensMetering`: OCR使用统计（输入/输出token数）

## 与原有功能对比

| 特性 | 原有 `transform_markdown()` | 新增 `transform_pages_markdown()` |
|------|---------------------------|-----------------------------------|
| 输出格式 | 单个完整Markdown文件 | 页面Markdown列表 |
| 跨页处理 | ✅ 自动拼接跨页段落 | ❌ 保持页面边界 |
| 章节分析 | ✅ 识别目录和章节 | ❌ 每页独立处理 |
| 使用场景 | 完整文档转换 | 页面级处理、分析 |
| 性能 | 相同 | 相同 |

## 应用场景

1. **页面级分析**: 需要对每页内容进行独立分析
2. **分段处理**: 将大文档按页分割处理
3. **质量检查**: 逐页检查OCR质量
4. **内容提取**: 从特定页面提取信息
5. **批量处理**: 处理多个PDF时需要页面级控制

## 性能建议

### 快速模式（适合批量处理）
```python
page_markdowns, _ = transform_pages_markdown(
    pdf_path="document.pdf",
    use_remote_api=True,
    ocr_size="small",     # 使用小模型
    dpi=200,              # 降低DPI
)
```

### 高质量模式（适合重要文档）
```python
page_markdowns, _ = transform_pages_markdown(
    pdf_path="document.pdf",
    use_remote_api=True,
    ocr_size="gundam",    # 使用最大模型
    dpi=300,              # 高DPI
    includes_footnotes=True,
)
```

## 注意事项

1. **页面边界**: 此功能不会合并跨页的段落，每页内容严格独立
2. **资源共享**: 图片等资源仍会统一管理，避免重复
3. **目录处理**: 不进行目录分析，原始页面内容按OCR结果输出
4. **内存使用**: 所有页面内容会同时存在内存中，处理大文档时注意内存占用

## 示例文件

- `examples/page_transform_example.py`: 完整使用示例
- `test_page_transform.py`: 功能测试脚本