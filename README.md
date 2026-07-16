# DiscoveryLab

DiscoveryLab 是一个证据驱动的 AI 产品发现与决策工作台。它把访谈、工单、问卷、行为数据和竞品资料整理为可定位的原子证据，再形成支持与反对结论、产品机会、可证伪假设、实验、决策和带引用的 PRD。

> 核心价值不是更快地产出文档，而是更可靠地改变判断。

## 当前阶段

项目已经通过 Architecture Gate，并完成三个可演示切片：**Source → Evidence → 原文回跳**、**人工 Evidence Revision / Review → 持久化 Claim → Opportunity Draft**，以及 **Hybrid Retrieval → 不可变 Context Manifest → 精确 revision 回放**。真实 UI、FastAPI、PostgreSQL/pgvector、不可变 Blob、LangGraph、解析器、抽取器、引用校验与离线评测已经连通；工作台支持 English / 简体中文即时切换并记住选择。

Evidence、Review、Claim、Claim–Evidence Edge、Opportunity Draft 和 Context Manifest 都写入真实数据库。正式关系必须绑定当前、已人工接受、非合成且可确定性回放的 Evidence Revision；新 Evidence Revision 会让依赖旧版本的已审核 Claim 变为 `stale`。逐字引文、Source Revision、Locator 与哈希始终锁定，历史回放不会被“当前最新版”替换。客户端生成的建议仍被单独标为非持久化预览，不冒充已审核结论。

实施仍受以下架构门禁约束：

- 核心闭环、MVP 与非目标已经明确。
- Source、Locator、Evidence、Claim 的版本与溯源规则已经明确。
- LangGraph、后台 Worker 与 PostgreSQL 的职责边界已经明确。
- Tool 权限、Human-in-the-loop 和外部写入审批已经明确。
- Golden Dataset、Bad Case 与发布门禁已经明确。

## 核心闭环

```text
资料
→ 可定位原文
→ 原子证据
→ 支持/反对结论
→ 产品机会
→ 可证伪假设
→ 实验
→ 决策
→ 带引用 PRD
```

## 技术策略

- Next.js：产品界面。
- FastAPI：业务 API 与控制平面。
- Python Worker：解析、Embedding、批量抽取和异步任务。
- PostgreSQL + pgvector：唯一业务事实源和混合检索。
- Redis：任务投递与短期缓存，不保存权威状态。
- 本地不可变 Blob 适配器 / S3 / R2：原始文件和网页快照；首期本地运行，线上无缝切换对象存储。
- LangGraph：Agent Workflow、Checkpoint、暂停恢复与 HITL。
- Langfuse + OpenTelemetry：模型和工具 Trace。
- Typed Python Eval Runner + pytest：当前离线门禁；进入真实模型对比后再接 Promptfoo。
- MCP SDK：把证据检索和决策查询暴露给外部 Agent。

## 自研边界

项目不会重复实现通用框架。重点自研：

- Evidence–Claim–Decision 数据模型和来源谱系。
- 支持证据、反面证据和覆盖缺口检索。
- Prompt/Context 的版本化组装和可重放机制。
- Discovery Workflow、工具权限和审批策略。
- 产品发现专用的 Golden Dataset、评测器和 Bad Case 闭环。
- Evidence Explorer、Claim Inspector、Run Inspector 和 Eval Center。

## 架构文档

- [产品定义](docs/product-definition.md)
- [系统架构](docs/system-architecture.md)
- [领域与数据模型](docs/domain-model.md)
- [开发环境与工具准备](docs/development-environment.md)
- [纵向切片 01：Source to Evidence](docs/vertical-slice-01.md)
- [纵向切片 02：Evidence Review to Claim](docs/vertical-slice-02.md)
- [纵向切片 03：Hybrid Retrieval 与 Context Manifest](docs/vertical-slice-03.md)
- [Evaluation 与 Bad Case 闭环](docs/evaluation-and-bad-cases.md)

Agent Harness、评测与安全、实施路线图和 ADR 会伴随对应纵向切片固化，避免形成与真实代码脱节的“纸面架构”。

## 能力落地状态

| 能力 | 当前可运行内容 | 后续切片 |
| --- | --- | --- |
| Agent Workflow | LangGraph `parse → extract → verify`，Run/Step 输入快照、哈希、失败恢复与运行检查器 | Discovery HITL 暂停/恢复与条件分支 |
| Tool Calling | 当前工作流没有任意工具选择或副作用工具，注入文本只能作为数据 | Tool Registry、Policy、参数绑定 Approval |
| Prompt / Context Engineering | 结构化输出、版本化 profile、上下文预算、untrusted-data 边界；检索结果冻结为 Context Manifest | Prompt/Context 对照运行 |
| RAG | PostgreSQL `vector(256)` + HNSW、BM25、确定性 feature-hash cosine、RRF、相关性 fail-closed 与精确回放；UI 明确说明本地向量不是训练语义模型 | 可选真实 embedding adapter 与 Claim counter-search workflow |
| Evaluation | 26 个可执行 Golden Cases，Source→Evidence 11/11、Evidence→Claim 15/15，无 skipped；引用、反证门禁、旧 revision、注入与多 blocker 聚合 | Decision/PRD 评测 |
| Bad Case Analysis | 严格 Bad Case schema、根因/修复/回归链接、整箱 fail-closed 与只读 Reporting API | UI Failure Inbox 与聚类 |
| MCP | 架构与只读权限边界已定义 | Evidence/Decision MCP Server |
| PRD | 持久化、已审核 Claim 与 revision-bound Opportunity Draft 已完成 | Hypothesis → Experiment → Decision → cited PRD |

界面层还提供 English / 简体中文模式。切换只翻译产品界面、状态和无障碍标签；来源原文、逐字引文和研究资料不会被改写或机器翻译。

这张表区分“已经能现场演示”与“已经设计但尚未实现”，避免用静态页面冒充技术能力。

## 本地运行

### Windows 一键进入

在项目根目录双击 **`双击启动 DiscoveryLab.cmd`**。它会自动启动所需服务、等待页面就绪，然后打开浏览器；如果服务已经运行，会直接复用。默认入口是 `http://127.0.0.1:3010`，API 使用 `8010` 端口。

下面的命令适合需要手动管理服务时使用。

首次准备依赖：

```powershell
.\scripts\bootstrap.ps1
pnpm install --frozen-lockfile
```

启动数据库、执行迁移，并在后台启动 API 与 Web：

```powershell
.\scripts\dev.ps1 start
```

开发服务只会管理 `.cache/dev` 中记录的本项目进程；如果 3000 或 8000 端口已被其他程序占用，脚本会停止并提示，不会结束那个程序。常用管理命令：

```powershell
.\scripts\dev.ps1 status
.\scripts\dev.ps1 logs
.\scripts\dev.ps1 restart
.\scripts\dev.ps1 stop
```

导入可重复运行的 HelpHub 演示 Study：

```powershell
.\scripts\seed-helphub.ps1
```

脚本只通过公开 HTTP API 创建 Study、上传 Markdown/CSV、运行证据抽取，再创建人工 Evidence Revision、Evidence Review、revision-pinned Claim/Review 和 Opportunity Draft，并抽查原文定位与哈希完整性。进度保存在 `.cache/helphub-seed.json`，中断后可直接重跑；如需创建一份全新的副本，使用 `-ForceNew`。

运行离线 Golden Evaluation：

```powershell
.\scripts\eval.ps1
```

报告写入 `.cache/evals/source-to-evidence.json`、`.cache/evals/evidence-to-claim.json` 和 `.cache/evals/bad-cases.json`。当前 26 个 case 全部执行，门禁覆盖精确引用、CSV 稳定行定位、Prompt Injection 隔离、Locator 回放、Evidence 资格、反证状态、旧 revision 精确回放和多 blocker 聚合；任何失败或 skipped 都会阻断检查。

## 明确不做

首版不做通用知识库、微服务、图数据库、连接器市场、多 Agent 自由辩论、企业级实时协作或自动路线图决策。MVP 用一个 HelpHub 种子 Study 做深，并主动展示脏数据、反面证据、权限、失败与恢复。
