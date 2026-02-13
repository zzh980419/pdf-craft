# 表格识别问题排查指南

基于你的测试结果（返回内容为空，只有2个output_tokens），这里是问题排查步骤：

## 🔍 问题现象
- API调用成功（status 200）
- 但返回的markdown内容几乎为空（只有页面标题）
- output_tokens 很少（只有2个）
- 表明API没有识别出有效内容

## 🛠️ 排查步骤

### 1. 检查API配置
确认 `.env` 文件中的配置：
```bash
# 检查这些配置是否正确
DEEPSEEK_OCR_BASE_URL=http://100.64.0.177:19002
DEEPSEEK_OCR_MODEL=deepseek-ai/DeepSeek-OCR
OCR_DEBUG=true
```

### 2. 运行调试脚本
```bash
python debug_api_connection.py
python check_api_response.py
```

### 3. 检查API响应
观察调试输出，关注：
- API响应格式是否正确
- choices[0].message.content 是否为空
- 是否有错误信息

## 🔧 可能的解决方案

### 方案1: 模型名称问题
DeepSeek本地部署的模型名称可能不是 `deepseek-ai/DeepSeek-OCR`，尝试修改为：
```bash
# 在 .env 文件中尝试这些模型名称：
DEEPSEEK_OCR_MODEL=deepseek-ocr
DEEPSEEK_OCR_MODEL=DeepSeek-OCR
DEEPSEEK_OCR_MODEL=deepseek-reasoner
```

### 方案2: API格式问题
如果API响应格式与标准OpenAI不同，修改 `client.py` 中的响应解析部分。

### 方案3: 图像质量问题
在 `client.py` 中已经改进了图像处理：
- 提高了图像质量（90% JPEG质量）
- 增加了分辨率（2048px for tables）
- 添加了调试输出

### 方案4: 提示词问题
当前使用的是中文提示词，如果API偏好英文，可以修改为英文提示词。

## 🧪 测试建议

### 测试1: 简单文本识别
先测试一个简单的图像，确认API基本功能：
```python
python check_api_response.py
```

### 测试2: 特定页面
测试包含明显表格的页面（如第8页的油藏数据表）：
```python
# 使用API测试特定页面
curl -X POST http://localhost:1157/api/pdf/parse-pages \
  -H "Content-Type: application/json" \
  -d '{
    "pdf_path": "test_table.pdf",
    "pages": [8],
    "enhanced_table_mode": true,
    "use_hybrid_mode": false
  }'
```

### 测试3: 不同模式对比
比较不同模式的结果：
- 纯远程API模式 (`use_hybrid_mode: false`)
- 混合模式 (`use_hybrid_mode: true`)

## 📝 常见问题

### Q: 为什么返回的内容几乎为空？
A: 可能原因：
1. API模型名称错误
2. 图像格式不被支持
3. API配额或限制
4. 提示词语言不匹配

### Q: 如何确认API是否正常工作？
A: 运行 `check_api_response.py` 查看：
1. 简单文本请求是否成功
2. API响应格式是否正确
3. 错误信息（如果有）

### Q: hybrid模式和普通模式有什么区别？
A: 
- 普通模式：纯远程API识别
- Hybrid模式：结合原项目的结构检测+远程API识别
- Hybrid模式理论上对表格识别更好

## 🎯 下一步行动

1. **立即执行**: 运行调试脚本确认API状态
2. **配置调整**: 根据调试结果调整模型名称
3. **功能测试**: 使用不同页面和模式进行测试
4. **结果对比**: 比较不同配置的识别效果

记住启用调试模式 (`OCR_DEBUG=true`) 来获得详细的执行信息！