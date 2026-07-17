# DiscoveryLab

DiscoveryLab 是一个证据驱动的 AI 产品发现与决策工作台。它把访谈、工单、问卷、行为数据和竞品资料整理为可定位的原子证据，再形成支持与反对结论、产品机会、可证伪假设、实验、决策和带引用的 PRD。

> 核心价值不是更快地产出文档，而是更可靠地改变判断。

## 当前阶段

项目已经形成一条可以现场演示的完整纵向链路：

```text
Source → Evidence → Human Review → Claim → Opportunity
→ Hybrid RAG Context → LangGraph Agent → Exact Tool Approval
→ Hypothesis → Experiment → Product Decision → Exactly Cited PRD
```

五个双语工作区均连接真实 FastAPI 与 PostgreSQL 数据：Evidence Explorer、Claims & Opportunities、Agent Runs、Eval & Bad Cases、Decisions & PRDs。一键启动会迁移数据库并准备 HelpHub 作品集样例；首页会优先打开证据最完整的 Study，避免空测试项目干扰演示。

Evidence、Review、Claim、Claim–Evidence Edge、Opportunity、Context Manifest、Agent Run、Tool Call、Approval、Hypothesis、Experiment、Product Decision 和 PRD 都是持久化记录。正式关系必须绑定当前、已人工接受、非合成且可确定性回放的 revision。新 Evidence Revision 会让依赖旧版本的已审核 Claim 变为 `stale`；逐字引文、Source Revision、Locator、Review 与内容哈希始终锁定，历史回放不会被“当前最新版”替换。

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
- [纵向切片 04：Agent → Experiment → Decision → PRD](docs/vertical-slice-04.md)
- [Evaluation 与 Bad Case 闭环](docs/evaluation-and-bad-cases.md)

文档描述当前可运行边界；未来能力会明确标为未实现，避免形成与真实代码脱节的“纸面架构”。

## 能力落地状态

| 能力 | 当前可运行内容 | 真实性边界 |
| --- | --- | --- |
| Agent Workflow | LangGraph 两阶段工作流：计划、受控检索、可证伪假设、审批中断、恢复与收尾；Run/Step 全量落库 | 当前模型适配器为确定性作品集 Harness，`model_called=false` 会在 UI 明示 |
| Tool Calling | 服务端 Tool Registry、只读工具自动执行、写工具精确参数哈希审批、approve/reject 恢复 | 写工具只创建本地 Experiment Draft，明确记录 `external_system_written=false` |
| Prompt / Context Engineering | 版本化 system profile、输入快照、untrusted-data 边界、不可变 Context Manifest 与 replay URL | 来源文字永远不能改写工具表、Prompt profile 或审批策略 |
| RAG | PostgreSQL `vector(256)` + HNSW、BM25、确定性 feature-hash cosine、RRF、相关性 fail-closed 与精确回放 | 本地向量是可重建 hash vector，不冒充训练语义 embedding |
| Evaluation | 26 个可执行 Golden Cases，Source→Evidence 11/11、Evidence→Claim 15/15，无 skipped | 任何 failed 或 skipped 都会阻断质量检查 |
| Bad Case Analysis | 严格 schema、根因/修复/fixture/回归测试链接、只读 API 与双语 Bad Case Inbox | 当前内置 1 个已修复案例，不伪造线上事故数量 |
| MCP | 6 个只读 MCP Tools，通过公开 HTTP API 查询 Study、Claim、Context、Product Chain 和 PRD | 无数据库直连，无审批、决策写入、删除或发布工具 |
| PRD | 审批产出真实 Hypothesis/Experiment；人工追加 Decision；生成冻结 Claim/Evidence/Source/Review/Hash 的不可变 PRD | PRD 固定为 `DRAFT`、`publishable=false`，外部发布未实现 |

界面层还提供 English / 简体中文模式。切换只翻译产品界面、状态和无障碍标签；来源原文、逐字引文和研究资料不会被改写或机器翻译。

这张表区分“已经能现场演示”与“已经设计但尚未实现”，避免用静态页面冒充技术能力。

## 本地运行

### Windows 一键进入

在项目根目录双击 **`双击启动 DiscoveryLab.cmd`**。它会启动 PostgreSQL/Redis、执行 Alembic 迁移、启动 API/Web、幂等准备完整 HelpHub 演示链路，然后打开浏览器；如果服务和样例已经就绪，会直接复用。默认入口是 `http://127.0.0.1:3010`，API 文档是 `http://127.0.0.1:8010/docs`。

下面的命令适合需要手动管理服务时使用。

首次准备依赖：

```powershell
.\scripts\bootstrap.ps1
pnpm install --frozen-lockfile
```

启动数据库、执行迁移，并在后台启动 API 与 Web：

```powershell
.\scripts\dev.ps1 start -ApiPort 8010 -WebPort 3010
```

开发服务只会管理 `.cache/dev` 中记录的本项目进程；如果 3000 或 8000 端口已被其他程序占用，脚本会停止并提示，不会结束那个程序。常用管理命令：

```powershell
.\scripts\dev.ps1 status -ApiPort 8010 -WebPort 3010
.\scripts\dev.ps1 logs -ApiPort 8010 -WebPort 3010
.\scripts\dev.ps1 restart -ApiPort 8010 -WebPort 3010
.\scripts\dev.ps1 stop -ApiPort 8010 -WebPort 3010
```

导入可重复运行的 HelpHub 演示 Study：

```powershell
.\scripts\seed-helphub.ps1
```

脚本只通过公开 HTTP API 创建 Study、上传 Markdown/CSV、运行证据抽取，再创建人工 Evidence Revision/Review、revision-pinned Claim/Review、Opportunity、审批后的 Agent Run、Hypothesis、Experiment、Product Decision 和带精确引用的 PRD。进度保存在 `.cache/helphub-seed.json`，中断后可直接重跑；如需创建一份全新的副本，使用 `-ForceNew`。样例的离线实验结果明确标为 synthetic fixture，不冒充生产结果。

### 只读 MCP Server

先保持 API 运行，然后执行：

```powershell
$env:DISCOVERY_LAB_API_URL = "http://127.0.0.1:8010"
.\.tools\bin\uv.exe run discovery-lab-mcp
```

可直接复用 [MCP 配置样例](mcp/discovery-lab.mcp.json)。Server 仅调用公开 HTTP API，不导入数据库模型；暴露 `list_studies`、`list_reviewed_claims`、`retrieve_reviewed_evidence`、`get_context_manifest`、`get_product_artifacts` 和 `get_prd` 六个只读工具。

运行离线 Golden Evaluation：

```powershell
.\scripts\eval.ps1
```

报告写入 `.cache/evals/source-to-evidence.json`、`.cache/evals/evidence-to-claim.json` 和 `.cache/evals/bad-cases.json`。当前 26 个 case 全部执行，门禁覆盖精确引用、CSV 稳定行定位、Prompt Injection 隔离、Locator 回放、Evidence 资格、反证状态、旧 revision 精确回放和多 blocker 聚合；任何失败或 skipped 都会阻断检查。

## 明确不做

首版不做通用知识库、微服务、图数据库、连接器市场、多 Agent 自由辩论、企业级实时协作或自动路线图决策。也没有实现 Linear/Jira 等真实外部发布：当前写工具只在本系统内创建 Experiment Draft，PRD 始终需要最终人工审核。MVP 用一个 HelpHub 种子 Study 做深，并主动展示合成数据标签、脏数据、反面证据、Prompt Injection、权限、失败与恢复。
