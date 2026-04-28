# Langfuse 集成说明

本项目支持使用 [Langfuse](https://langfuse.com/) 进行 LLM 监控和追踪。

## 功能特性

- **实时追踪**: 监控每个 LLM 调用和 API 响应
- **工作流可视化**: 追踪营销分析工作流的每个步骤
- **性能指标**: 查看延迟、token 使用量等关键指标
- **错误追踪**: 记录和追踪工作流中的错误
- **多步骤追踪**: 为 tags、persona、scenes 生成单独的追踪记录

## 配置步骤

### 1. 注册 Langfuse

访问 [Langfuse Cloud](https://cloud.langfuse.com/) 注册账号，或使用自托管版本。

### 2. 获取 API 密钥

在 Langfuse 仪表板中：

1. 进入 **Settings** → **API Keys**
2. 创建新的 API Key
3. 复制 **Public Key** 和 **Secret Key**
4. 获取 **Project ID**

### 3. 配置环境变量

在 `.env` 文件中添加以下配置：

```env
# Langfuse 配置
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxx-xxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxx-xxxxx
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_PROJECT_ID=your-project-id
```

### 4. 安装依赖

```bash
pip install langfuse>=0.28.0
```

### 5. 重启应用

```bash
# 开发环境
uvicorn app.main:app --reload

# Docker 环境
docker-compose up --build
```

## 验证配置

启动应用后，查看日志确认 Langfuse 是否启用：

```
INFO - Langfuse monitoring enabled
INFO - Langfuse health check passed
```

## 查看追踪数据

在 Langfuse 仪表板中查看：

1. **Traces**: 查看完整的工作流追踪
2. **Generations**: 查看每个 LLM 调用
3. **Spans**: 查看工作流中的各个步骤
4. **Sessions**: 按 task_id 分组的会话

## 同时使用 LangSmith 和 Langfuse

项目支持同时配置 LangSmith 和 Langfuse，两者会独立运行：

```env
# LangSmith
LANGSMITH_API_KEY=lsv2_xxx
LANGSMITH_PROJECT=langgraph-demo

# Langfuse
LANGFUSE_PUBLIC_KEY=pk-lf-xxx
LANGFUSE_SECRET_KEY=sk-lf-xxx
```

## 追踪的工作流步骤

| 步骤 | 追踪名称 | 说明 |
|------|---------|------|
| 生成标签 | `generate_tags` | 基于品牌和地区生成营销标签 |
| 生成人物画像 | `generate_persona` | 基于标签生成目标人群画像 |
| 生成场景 | `generate_scenes` | 基于人群画像生成营销场景 |

## 数据隐私

- `.env` 文件中的 API 密钥不会提交到 GitHub
- Langfuse 追踪数据存储在 Langfuse 服务器（云端或自托管）
- 可以配置自托管 Langfuse 以完全控制数据

## 故障排除

### Langfuse 未启用

检查日志中的警告信息：

```bash
# 确保环境变量正确加载
cat .env | grep LANGFUSE
```

### 健康检查失败

```bash
# 检查网络连接
curl https://cloud.langfuse.com/api/public/health

# 检查 API 密钥是否正确
python -c "from langfuse import Langfuse; l = Langfuse(public_key='pk-lf-xxx', secret_key='sk-lf-xxx'); print(l.health_check())"
```

### 追踪数据未显示

1. 确认应用已重启
2. 检查浏览器控制台是否有网络错误
3. 确认 `LANGFUSE_HOST` 配置正确
