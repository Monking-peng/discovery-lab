# HelpHub 可复现演示数据

HelpHub 是一个完全虚构的 B2B 客服产品案例，适合公开作品集。原始访谈、工单、研究结论和审阅者都不代表真实用户或真实公司。

## 演示数据包含什么

- `interviews.md`：虚构的访谈记录，包含不同客群的冲突需求。
- `tickets.csv`：12 条虚构工单，包含 SLA、重开、升级和风险标签。
- `decision-brief.json`：虚构的产品决策背景与约束。
- `curated-evidence.json`：人工编写的 Evidence Revision、Evidence Review 和 Claim 清单。

数据故意同时包含：

- 高频但低风险的自动回复诉求；
- 数量较少、影响更高的企业升级失败；
- 同一账号的相关工单；
- 已升级但仍然 SLA 违约的限制性证据；
- 分类路由等替代机会；
- 一条作为不可信数据处理的 prompt-injection 字符串。

因此，脚本不是把“正确答案”直接写进数据库。系统先从原始文件生成明确标记为 `synthetic_demo` 的提案；随后通过公开 HTTP API 创建人工 Evidence Revision，保留原始逐字引用、Locator、Source Revision 和 Segment，再记录人工审阅，最后创建并审阅绑定到这些精确 revision 的 Claim。

> “人工”表示内容由仓库维护者预先策展，而不是模型自动生成；“审阅”表示虚构演示夹具的内容审阅，不是真实客户研究。API provenance 和 review note 会一直保留这层说明。

## 一键导入

先用项目根目录的 `双击启动 DiscoveryLab.cmd` 启动服务，然后在 PowerShell 中运行：

```powershell
.\scripts\seed-helphub.ps1
```

脚本默认连接一键启动入口：Web `http://127.0.0.1:3010`、API `http://127.0.0.1:8010`。如果使用 `scripts/dev.ps1` 的默认 3000/8000 端口，请显式传入：

```powershell
.\scripts\seed-helphub.ps1 `
  -ApiUrl http://127.0.0.1:8000 `
  -WebUrl http://127.0.0.1:3000
```

需要一份全新的隔离副本时使用：

```powershell
.\scripts\seed-helphub.ps1 -ForceNew
```

## 可恢复与幂等保证

脚本只调用产品公开 API，不直接连接或写入数据库。每一步都有 Study 范围内的确定性 `client_request_id`，服务端会校验同一幂等键的请求内容；相同脚本可安全重跑，内容变化却复用旧键时会明确返回冲突。

进度原子地保存在 `.cache/helphub-seed.json`，包括：

- Study 与 Source ID；
- 每个工单对应的 Evidence Unit、原始 revision、人工 revision 和 review ID；
- Claim、Claim Revision 和 Claim Review ID；
- Opportunity Draft ID 与绑定的精确 Claim Revision ID。

即使本地状态文件丢失，脚本也会从 Study 的 Source/Evidence API 重建未完成的上传与处理状态。它以 `source_name + ticket_id` 查找候选，并把 Evidence 的 JSON 逐字引用与 `tickets.csv` 的全部列逐一比对；匹配不唯一、引用不完整或哈希/Locator 回放失败时立即停止，不会“猜一个”继续。

如果有人已经在同一 Study 上创建了非夹具人工 revision、追加了拒绝审阅，或使已审阅 Claim 失效，脚本会保护这些人工操作并要求使用 `-ForceNew`，不会静默覆盖。

## 完成后的可演示状态

成功输出意味着：

- 6 个目标工单都有保留原始引用的人工 Evidence Revision；
- 6 个精确 Evidence Revision 的最新审阅均为 `ACCEPT`；
- 一个 Claim 同时包含支持、限制性反证和上下文边；
- Claim Revision 的最新审阅为 `ACCEPT`，且没有 publication blocker；
- 一个 `DRAFT` Opportunity 绑定到该精确 Claim Revision，并明确保留 `OPPORTUNITY_DRAFT_NOT_PUBLISHED` 门禁；
- 任意 Claim edge 都能回放到固定的 Evidence Revision、Source Revision 和 CSV 行。

Opportunity 也只通过公开 API 创建，且必须在 Claim 为当前、已审阅、非 stale 时才会成功。它只是可追溯草稿，不会被脚本包装成已发布的产品决策。

修改策展内容时，请同步升级 manifest 的 `profile` 和相关 `client_request_id` 版本；已有演示数据建议通过 `-ForceNew` 重新生成，以保留不可变 revision 的历史语义。
