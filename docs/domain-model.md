# 领域与数据模型

## 核心思想

系统的核心不是聊天记录，也不是最终报告，而是一条版本化、可审核、可重放的来源链：

```text
Source Revision
→ Segment + Locator
→ Evidence Revision
→ Theme / Claim Revision
→ Opportunity
→ Hypothesis
→ Experiment + Result
→ Decision Revision
→ PRD Revision
```

## 双 ID 与不可变 Revision

重要对象使用稳定身份和不可变版本两个 ID：

```text
claim_id           # 逻辑身份
claim_revision_id  # 某个不可变内容版本
```

页面可以显示 current revision，但以下对象必须引用具体 revision：

- Evidence–Claim 关系。
- Workflow Input Snapshot。
- Review 和 Approval。
- Experiment、Decision 和 PRD。
- Eval Case 的输入和期望结果。

人工修改不覆盖历史，只创建新 revision。新资料或人工修改使下游依赖变化时，下游产物标记为 `stale`，由用户选择保留、局部更新、全量重算或版本对比。

## 领域聚合

### Workspace

```text
Workspace
├── Members
├── Roles
├── Access Policies
├── Connector Credentials
└── Retention Policy
```

### Study

```text
Project
└── Study
    ├── Decision Brief Revisions
    ├── Research Questions
    ├── Cohort Definition Revisions
    ├── Candidate Options
    ├── Constraints
    └── Success Metrics
```

`Study` 表示业务阶段，不能从最后一次 Run 的状态推断。

### Source

```text
Source
└── Source Revision
    ├── Documents
    ├── Segments
    ├── Locators
    ├── Redaction Records
    └── Duplicate Links
```

Source Revision 保存：

- 内容哈希、原文件地址和 MIME 类型。
- 文件或网页版本、抓取时间和数据有效时间。
- 解析器与解析 Schema 版本。
- 来源账户、用户群和权限范围。
- 处理状态、错误和重试信息。

### Evidence

一条 Evidence Revision 至少包含：

- 精确 Quote 或确定性指标。
- Source Revision 和 Locator。
- Observation：原文直接支持的观察事实。
- Interpretation：对事实的业务解释。
- Inference：需要进一步验证的推断。
- Cohort、场景、时间和实体标签。
- 提取它的 Step Attempt、Prompt、模型和 Schema 版本。
- 审核状态与人工修订。

示例：

```text
Quote：用户说“我每周花两小时做周报”
Observation：用户存在手工制作周报的行为
Interpretation：报告过程存在效率问题
Inference：可能存在报告自动化机会
```

### Discovery

```text
Theme Revision
├── Theme Memberships → Evidence Revisions
└── Claim Revisions
    ├── Claim Evidence Edges
    ├── Opportunities
    └── Hypotheses
        ├── Experiments
        ├── Experiment Results
        └── Decisions
            └── PRD Revisions
```

`ClaimEvidenceEdge` 引用具体 Evidence Revision，并包含：

- `supports`
- `contradicts`
- `contextualizes`
- `insufficient_for`
- 关系说明和相关度。
- 边本身的生成与审核来源。

Persona/Simulation 使用独立表。数据库约束和应用规则禁止 Simulation Output 作为 `supports` 边连接正式 Claim。

### Workflow

```text
Workflow Definition Version
└── Run
    ├── Input Snapshot
    ├── Run Steps
    │   └── Step Attempts
    ├── Checkpoints
    ├── Context Manifests
    ├── Tool Calls
    ├── Reviews
    ├── Approvals
    └── Run Events
```

Run 必须绑定不可变 Input Snapshot，至少冻结：

- Decision Brief Revision。
- Source/Evidence Revisions。
- Prompt、Agent、Model Profile 版本。
- Retrieval 和 Context Policy 版本。
- Tool Contract 与 Workflow Definition 版本。
- 代码 commit 或镜像 digest。

规范化后的 Input Snapshot 计算哈希。相同 Run 不能静默混入新数据；需要继续旧快照或 Fork 新 Run。

### Evaluation

```text
Eval Dataset
└── Eval Dataset Revision
    └── Eval Case Revisions
        ├── Expected Assertions
        ├── Eval Scores
        └── Failure / Regression Links
```

线上人工纠正先进入 Failure Inbox。经过脱敏、根因分析和人工定义期望行为后，才能进入 Golden Dataset。

## Locator 设计

Locator 是可追溯性的最低层契约。

### 文本 / Markdown

- Source Revision ID。
- Segment ID。
- 字符起止位置。
- 原文内容哈希。

### PDF

MVP：页码、页内文本、字符偏移和内容哈希。

后续：页面 bounding box 和渲染坐标。

### CSV

- Source Revision ID。
- 稳定行 ID，而不只依赖易变化的行号。
- 原始行号。
- 使用的列名。
- 行内容哈希。

### 网页

- Canonical URL。
- 抓取时间和快照 ID。
- DOM Path 或文本锚点。
- 网页内容哈希。

### 行为指标

- Dataset Revision。
- 只读查询或确定性计算 ID。
- 时间范围和过滤条件。
- 聚合结果哈希。

## 推荐关系表

MVP 使用 PostgreSQL 普通表和关系表，不引入图数据库。

核心表：

```text
workspaces, workspace_members
projects, studies, decision_brief_revisions
sources, source_revisions, documents, segments, locators
evidence_units, evidence_revisions, evidence_reviews
entities, cohorts
themes, theme_revisions, theme_memberships
claims, claim_revisions, claim_evidence_edges
opportunities, hypotheses
experiments, experiment_results
decisions, decision_revisions, prd_revisions
runs, input_snapshots, run_steps, step_attempts, checkpoints
context_manifests, tool_calls, reviews, approvals, run_events
prompt_versions, model_profile_versions, policy_versions
eval_datasets, eval_cases, eval_runs, eval_scores
failure_cases, root_cause_analyses, regression_groups
outbox_events
```

pgvector 和全文索引是 Evidence Revision 的可重建投影，不承载审核、版本或权限真相。

## 状态模型

### Study

```text
DRAFT
→ SCOPED
→ COLLECTING
→ EVIDENCE_REVIEW
→ SYNTHESIZING
→ HYPOTHESIS_REVIEW
→ EXPERIMENTING
→ DECISION_REVIEW
→ DECIDED
→ ARCHIVED
```

### Run

```text
QUEUED
→ RUNNING
→ WAITING_APPROVAL / PAUSED
→ SUCCEEDED / PARTIALLY_SUCCEEDED / FAILED / CANCELLED
```

### Step

```text
PENDING → READY → RUNNING
                     ├→ WAITING_HUMAN
                     ├→ SUCCEEDED
                     ├→ FAILED
                     ├→ SKIPPED
                     └→ CANCELLED
```

每次重试创建新的 Step Attempt，不覆盖原日志。

## Review 与 Approval

- Review：判断内容是否正确，例如审核 Evidence 或 Theme。
- Approval：授权执行动作，例如向 Linear 写入或发布 PRD。

Approval 必须绑定：

- 具体 Artifact/Decision Revision。
- 具体动作和 Tool Contract 版本。
- 工具参数哈希和数据范围。
- 费用估计、有效期和批准者。

参数、输入 revision、权限或策略变化时，原 Approval 自动失效。

## 删除与失效

删除 Source 时：

1. 删除原文内容、对象存储文件和 embedding。
2. 保留不可反推内容的 Tombstone 和审计元数据。
3. 找到所有依赖的 Evidence、Claim、Decision 和 PRD。
4. 将依赖产物标记为 `stale` 或 `invalidated`。
5. 阻止这些产物继续发布。

## 关键不变量

- ACL 过滤必须在检索前生效。
- 正式 Evidence 必须关联有效 Locator。
- 正式 Claim 必须关联至少一条有效 Evidence Revision。
- PRD 只能引用已批准 Decision Revision。
- `stale` 或 `invalidated` 产物不能发布。
- 统计需求规模时按独立账户/用户计数。
- Persona Output 不能成为正式支持证据。
- 所有派生结果必须能回到 Input Snapshot、Config Bundle 和 Step Attempt。
