# 开发环境与首批工具准备

## 1. 结论

不要把所有 AI 工具一次性装进来。第一阶段只准备三层：

1. 机器级运行环境：Git、Node.js、pnpm、Docker Desktop；
2. 项目级可复现工具：固定版本的 `uv`、版本文件、环境模板、Compose 配置；
3. 首个纵向切片依赖：等 Web/API 骨架建立后再通过锁文件安装。

现在的环境状态：

| 工具 | 当前状态 | 用途 |
| --- | --- | --- |
| Git 2.42 | 已有 | 版本控制与可审计变更 |
| Node.js 24.16 | 已有 | Next.js、Promptfoo、Playwright |
| pnpm 11.7 | 已有 | JS monorepo 与依赖锁定 |
| Python 3.12.13 | 由 uv 放进项目 `.tools/python` | FastAPI、LangGraph、解析与评测 |
| uv 0.11.28 | 项目本地安装 | Python、虚拟环境、依赖锁定 |
| Docker Engine 29.5.3 + Compose 5.1.4 | 已安装在 WSL2 Ubuntu | 本地 PostgreSQL/pgvector 与 Redis |

## 2. 哪些应装在电脑上

### 必须

- **Git**：机器级即可，不复制进项目。
- **Node.js 24 LTS 与 pnpm 11**：当前已满足。
- **Docker Engine + Compose**：当前已完整安装在 WSL2 Ubuntu，项目脚本会自动调用它；无需重复安装 Docker Desktop。

如将来换电脑，可以选择 Docker Desktop，也可以像当前电脑一样在 WSL2 内安装 Docker Engine。两者只选一种，不要重复安装。检查命令：

```powershell
.\scripts\doctor.ps1
```

### 可选

- VS Code/Cursor/Codex：属于开发入口，不是产品运行依赖。
- `psql`、Redis GUI、数据库 GUI：排障方便，但首期不要求。
- FFmpeg/Tesseract：等音频转写或扫描 PDF 进入范围再装。

## 3. 哪些放在项目里

项目内已经准备：

- `.node-version` 与 `.python-version`：明确运行时版本；
- `.tools/bin/uv.exe`：不污染系统 PATH 的项目本地 Python 工具；
- `.tools/python`：由 uv 管理的项目 Python，避免依赖 Codex 的内置运行时；
- `.env.example`：变量契约，不含真实密钥；
- `infra/compose.yaml`：固定 PostgreSQL/pgvector 与 Redis 服务；
- `scripts/doctor.ps1`：检查环境；
- `scripts/bootstrap.ps1`：幂等安装项目本地 uv；
- `scripts/infra.ps1`：统一启停本地基础设施；
- 未来的 `pnpm-lock.yaml` 与 `uv.lock`：真正锁定应用依赖。

`.tools`、虚拟环境、缓存、数据库数据和原始资料不会提交到 Git。

## 4. 现在不安装，但会进入锁文件的依赖

### Web 层

- Next.js + React + TypeScript
- Tailwind CSS 与少量无障碍 UI primitive
- TanStack Query、Zod
- Playwright、Vitest

### API、数据与后台任务

- FastAPI、Pydantic、SQLAlchemy、Alembic、psycopg
- Redis client 与轻量 Worker 库
- PyMuPDF、Docling、pandas/pyarrow
- boto3 或兼容 S3 client

### Agent Harness

- LangGraph 与 PostgreSQL checkpointer
- 模型供应商适配器
- Langfuse SDK 与 OpenTelemetry
- 官方 MCP Python/TypeScript SDK

### Evaluation

- pytest、pytest-asyncio
- Promptfoo
- RAG/引用的自定义确定性评分器

这些依赖等相应模块出现时再添加并锁定。提前安装只会制造一大批暂时没被代码使用、也无法验证兼容性的包。

## 5. 本地服务的边界

首期 Compose 只有：

- **PostgreSQL 16.14 + pgvector 0.8.2**：复用本机已有镜像并锁定 digest；作为唯一业务事实源、全文检索、向量检索和 LangGraph checkpoint；
- **Redis 7.4.9**：任务投递和短期协调，不保存权威业务状态。

对象存储先通过统一接口使用 `./var/blobs`，文件按内容哈希不可变保存。部署时把同一接口切到 S3/R2。暂不自托管 Langfuse，也暂不额外拉 Elasticsearch、Qdrant、Neo4j。

## 6. 首次使用

```powershell
cd D:\Monking_Peng\discovery-lab
.\scripts\bootstrap.ps1
Copy-Item .env.example .env
.\scripts\infra.ps1 up
```

`infra.ps1` 会优先使用 Windows PATH 中的 Docker；没有时自动回退到 WSL2 Ubuntu 内的 Docker。

## 7. 安全与可复现规则

- 不提交 `.env`、客户原文、访问令牌、模型密钥或数据库卷；
- 所有容器版本先使用明确 tag，首次成功拉取后再记录 image digest；
- 所有应用依赖通过 lockfile 进入项目，禁止只在个人电脑全局安装；
- Source 内容一律视为不可信数据，不能成为系统指令；
- Langfuse/OTel 默认只记录 ID、哈希、统计信息和脱敏摘要；
- Docker 服务只映射到 `127.0.0.1`，避免暴露到局域网。

## 8. 暂时明确不准备

- Dify、Flowise、Coze：会遮住需要展示的 Harness 设计；
- Neo4j：MVP 的证据关系用 PostgreSQL 足够；
- Qdrant/Weaviate/Elasticsearch：pgvector + PostgreSQL FTS 足够完成混合检索；
- Kubernetes 与微服务脚手架：当前规模没有收益；
- 本地大模型与 GPU 环境：会拖慢交付，且不是这个作品的差异点；
- 自托管 Langfuse 全家桶：先用可关闭的 SDK/OTel 接口，需要时再接云端或独立部署。
