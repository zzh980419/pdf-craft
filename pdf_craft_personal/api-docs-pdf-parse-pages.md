# PDF 分页解析 API 文档

## 接口概述

**接口路径**: `/api/pdf/parse-pages`  
**请求方法**: `POST`  
**功能描述**: 分页解析 PDF 文件，将指定页面或全部页面转换为 Markdown 格式

## 输入参数

### 请求头
```
Content-Type: application/json
```
或
```
Content-Type: application/x-www-form-urlencoded
```

### 请求参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `pdf_path` | string | 是 | PDF 文件的绝对路径或相对路径 |
| `pages` | array[int] | 否 | 需要解析的页码数组，从1开始。如不提供则解析全部页面 |

### 请求示例

#### JSON 格式请求
```json
{
  "pdf_path": "/path/to/document.pdf",
  "pages": [1, 3, 5]
}
```

#### 表单格式请求
```
pdf_path=/path/to/document.pdf
pages=[1,3,5]
```

#### 解析全部页面
```json
{
  "pdf_path": "/path/to/document.pdf"
}
```

## 输出格式

### 成功响应 (HTTP 200)

```json
{
  "success": true,
  "pdf_path": "/path/to/document.pdf",
  "total_pages": 10,
  "processed_pages": 3,
  "pages": [
    {
      "page_number": 1,
      "markdown_content": "# 第一页内容\n\n这是第一页的Markdown内容..."
    },
    {
      "page_number": 3,
      "markdown_content": "# 第三页内容\n\n这是第三页的Markdown内容..."
    },
    {
      "page_number": 5,
      "markdown_content": "# 第五页内容\n\n这是第五页的Markdown内容..."
    }
  ],
  "metering": {
    "input_tokens": 1024,
    "output_tokens": 2048
  },
  "assets_path": "/outputs/document_assets",
  "duration_seconds": 15.42,
  "message": "解析指定页面成功: 3 页"
}
```

### 响应字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `success` | boolean | 请求是否成功 |
| `pdf_path` | string | 处理的PDF文件路径 |
| `total_pages` | int | PDF文件总页数 |
| `processed_pages` | int | 实际处理的页数 |
| `pages` | array | 解析结果数组 |
| `pages[].page_number` | int | 页码（从1开始） |
| `pages[].markdown_content` | string | 该页的Markdown内容 |
| `metering` | object | API调用计量信息 |
| `metering.input_tokens` | int | 输入token数量 |
| `metering.output_tokens` | int | 输出token数量 |
| `assets_path` | string | 图片资源存储路径 |
| `duration_seconds` | float | 处理耗时（秒） |
| `message` | string | 处理结果描述 |

### 错误响应 (HTTP 4xx/5xx)

#### 参数错误 (HTTP 400)
```json
{
  "error": "pdf_path is required"
}
```

#### 文件不存在 (HTTP 400)
```json
{
  "error": "PDF file not found: /path/to/nonexistent.pdf"
}
```

#### 页码无效 (HTTP 400)
```json
{
  "error": "No valid pages specified. PDF has 10 pages.",
  "invalid_pages": [15, 20]
}
```

#### 服务器错误 (HTTP 500)
```json
{
  "success": false,
  "error": "Internal server error message",
  "error_type": "Exception",
  "traceback": "Traceback details...",
  "duration_seconds": 1.23
}
```

## 文件输出路径

### 资源文件存储
- **路径格式**: `outputs/{PDF文件名}_assets/`
- **内容**: 解析过程中提取的图片等资源文件
- **示例**: 处理 `/docs/report.pdf` 时，资源文件存储在 `outputs/report_assets/`

### 路径说明
- 输出目录基于应用配置的 `OUTPUT_FOLDER`（默认为 `outputs`）
- 资源目录名格式：`{PDF文件基名}_assets`
- 所有路径均为绝对路径

## 使用说明

1. **页码范围**: 页码从1开始，超出范围的页码会被忽略
2. **文件格式**: 仅支持 `.pdf` 格式文件
3. **并发处理**: 每次请求独立处理，支持并发调用
4. **资源管理**: 图片资源自动保存到指定目录
5. **错误处理**: 详细的错误信息和堆栈跟踪（开发环境）

## cURL 调用示例

```bash
# 解析指定页面
curl -X POST http://localhost:1157/api/pdf/parse-pages \
  -H "Content-Type: application/json" \
  -d '{
    "pdf_path": "/path/to/document.pdf",
    "pages": [1, 2, 3]
  }'

# 解析全部页面
curl -X POST http://localhost:1157/api/pdf/parse-pages \
  -H "Content-Type: application/json" \
  -d '{
    "pdf_path": "/path/to/document.pdf"
  }'
```