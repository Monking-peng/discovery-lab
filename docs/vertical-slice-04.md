# 纵向切片 04：Agent → Experiment → Decision → PRD

## 目标

这一切片证明 DiscoveryLab 不只是“把资料总结成文档”，而是能把一条已审核 Claim 安全地推进为可证伪假设、受控实验、人工产品决策和可逐项追溯的 PRD。

## 可运行闭环

```text
Reviewed Claim Revision
→ LangGraph start
→ retrieve_reviewed_evidence
→ immutable Context Manifest
→ falsifiable Hypothesis proposal
→ create_experiment_draft Tool Call
→ exact arguments SHA-256 approval gate
→ LangGraph resume
→ immutable Hypothesis + Experiment
→ append-only Product Decision
→ immutable, non-publishable, exactly cited PRD
```

HelpHub seed 脚本会通过公开 API 生成整条链路。浏览器中的 Agent Run Center 可以检查每个 Run Step、Prompt/Context profile、工具参数、哈希、审批和结果；Decision & PRD Center 可以检查实验、人工决策、PRD 章节、发布阻断项和精确 citation。

## Agent Harness

工作流使用 LangGraph 表达两个服务端阶段：

1. `plan`：冻结目标、Claim Revision 与 Claim Review。
2. `retrieve_context`：调用 allowlisted 只读检索工具，创建不可变 Context Manifest。
3. `draft_hypothesis`：生成包含目标群体、主要指标、成功阈值和 falsification criterion 的假设。
4. `approval_gate`：为写工具保存精确参数和 SHA-256，随后中断。
5. `finalize`：只有服务端确认工具、参数哈希和策略契约都未变化后才能恢复。

LangGraph 负责流程和中断；PostgreSQL 中的 Agent Run、Run Step、Tool Call、Tool Approval 才是长期审计事实。来源内容被标记为 untrusted data，不能增加工具、修改 Prompt profile 或绕过审批。

## Tool Policy

| Tool | 类型 | 自动执行 | MCP | 作用 |
| --- | --- | --- | --- | --- |
| `retrieve_reviewed_evidence` | read / low | 是 | 是 | 只检索当前、已接受、非合成 Evidence Revision，并冻结 Context Manifest |
| `create_experiment_draft` | write / medium | 否 | 否 | 在本系统内创建不可变 Hypothesis 与 Experiment Draft |

写工具的 Approval 绑定 `tool_call_id + tool_name + tool_version + arguments_hash`。任何参数或策略变化都会 fail closed。执行结果明确保存 `external_system_written=false`；项目没有用本地写入冒充 Linear/Jira 等外部副作用。

## Product Artifact Chain

- Hypothesis：可证伪陈述、预期结果、falsification criterion。
- Experiment：目标群体、主要指标、成功阈值、精确 Claim Revision、Context Manifest 与 approved Tool Call。
- Product Decision：`PROCEED`、`ITERATE` 或 `STOP`，包含观察结果、理由和决策人；只追加不覆盖。
- PRD：冻结生成时所用 Decision 和全部 citation；固定为 `DRAFT` 与 `publishable=false`。

PRD 固定包含十个章节：problem、evidence summary、hypothesis、experiment、decision、scope、non-goals、success metrics、risks & guardrails、rollout。

每个 PRD citation 至少保存：

- Claim Revision、Claim Review decision/reviewer 和内容哈希。
- Context Manifest 中每条 Evidence Revision 与 Source Revision。
- Evidence Review decision/reviewer。
- quote、observation、Locator、Evidence/Source 内容哈希和精确 context URL。

发布阻断项固定包含 `PRD_REQUIRES_FINAL_REVIEW` 和 `EXTERNAL_PUBLICATION_NOT_IMPLEMENTED`。

## 公开 API

```text
POST /v1/studies/{study_id}/agent-runs
GET  /v1/studies/{study_id}/agent-runs
GET  /v1/agent-runs/{run_id}
POST /v1/tool-calls/{tool_call_id}/approvals

GET  /v1/studies/{study_id}/product-artifacts
POST /v1/experiments/{experiment_id}/decisions
POST /v1/decisions/{decision_id}/prds
GET  /v1/prds/{prd_id}
```

所有创建接口使用 client request ID 保证幂等。不可变产物在 PostgreSQL 还具有拒绝 UPDATE/DELETE 的数据库触发器。

## 只读 MCP

`discovery_lab.mcp_server` 是 stdio FastMCP Server，但所有语义操作都经由应用公开 HTTP API，不接收 SQLAlchemy Session，也不导入业务表。它提供 Study、Claim、检索 Context、Product Chain 与 PRD 查询，不暴露审批、Decision/PRD 写入、删除或外部发布。

## 评测与真实性边界

- 26 个 Golden Cases 覆盖引用回放、Prompt Injection 隔离、Evidence 资格、反证、旧 revision 与多 blocker。
- Agent 页面会显示 `model_called=false` 和 `deterministic-portfolio-harness`；当前流程用于稳定展示 harness 与治理，不声称发生真实 LLM 推理。
- RAG 向量为可重建 feature-hash vector，并与 BM25 通过 RRF 融合；不冒充训练得到的语义 embedding。
- HelpHub Product Decision 使用明确标记的 synthetic offline fixture result；它用于演示产品链路，不是生产实验结果。
- 没有外部发布工具，PRD 不能发布。
