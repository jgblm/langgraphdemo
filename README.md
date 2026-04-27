# LangGraph Marketing Analysis POC

基于LangGraph的营销三步分析链：品牌地区 -> Tags -> Persona -> 场景

## 功能特性

- 🔗 **三步分析链**: 品牌地区 → Tags → Persona → 场景
- 🧠 **LLM驱动**: 使用大语言模型生成分析结果
- 📊 **LangSmith追踪**: 完整的链路追踪和监控
- 🚀 **API接口**: RESTful API支持任务触发和进度查询
- 🐳 **Docker部署**: 一键启动完整环境

## 快速启动

```bash
# 1. 复制环境配置文件
cp .env.example .env

# 2. 编辑 .env 填入必要的API密钥
# - OPENAI_API_KEY: OpenAI API密钥
# - LANGSMITH_API_KEY: LangSmith密钥（可选）

# 3. 初始化数据库表
psql $SYNC_DATABASE_URL -f init_db.sql

# 4. 启动所有服务
docker-compose up -d

# 5. 访问API文档
open http://localhost:8000/docs
```

### 单独启动 Docker 服务

如果只需要启动 PostgreSQL（本地运行应用），使用以下命令：

**PostgreSQL：**
```bash
docker run -d --name postgres -p 5432:5432 -e POSTGRES_PASSWORD=123456 -e POSTGRES_DB=langgraphdb postgres:16
```

### 本地启动应用

确保 PostgreSQL 已运行后，执行以下命令启动应用：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

启动后访问：
- API 服务：http://localhost:8000
- API 文档：http://localhost:8000/docs

## API使用示例

### 创建分析任务

```bash
curl -X POST "http://localhost:8000/api/v1/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "brand": "星巴克",
    "region": "上海"
  }'
```

### 查询任务进度

```bash
curl "http://localhost:8000/api/v1/tasks/{task_id}"
```

### 获取任务结果

```bash
curl "http://localhost:8000/api/v1/tasks/{task_id}/result"
```

## 项目结构

```
langgraphdemo/
├── app/
│   ├── main.py              # FastAPI应用入口
│   ├── config.py            # 配置管理
│   ├── database.py          # 数据库连接
│   ├── models.py            # SQLAlchemy模型
│   ├── schemas.py           # Pydantic schemas
│   ├── graph/
│   │   ├── workflow.py      # LangGraph工作流定义
│   │   └── prompts.py       # 提示词模板
│   ├── api/
│   │   └── routes.py        # API路由
│   └── services/
│       ├── langsmith_service.py  # LangSmith集成
│       └── task_service.py      # 任务服务
├── docker-compose.yml
├── init_db.sql            # 数据库表初始化脚本
├── .env.example
└── requirements.txt
```

## 三步分析链详解

1. **Tags生成**: 根据品牌名称和地区信息，生成相关的营销标签
2. **Persona生成**: 基于Tags生成目标用户画像
3. **场景生成**: 基于Persona生成具体的营销场景

## 环境变量

| 变量名 | 必填 | 说明 |
|--------|------|------|
| OPENAI_API_KEY | 是 | OpenAI API密钥 |
| LANGSMITH_API_KEY | 否 | LangSmith API密钥 |
| LANGSMITH_PROJECT | 否 | LangSmith项目名 |
| DATABASE_URL | 否 | PostgreSQL连接字符串 |

## 技术栈

- **LangGraph**: 工作流编排
- **PostgreSQL**: 数据存储
- **LangSmith**: LLM可观测性
- **FastAPI**: API框架
- **SQLAlchemy**: ORM
- **Docker**: 容器化
