# 文档变更日志

> 更新时间：2026-08-13  
> 文档类型：变更日志  
> 状态：草案

## 2026-08-13

### Added

- RPA 示例脚本新增 `--only-publish-id` 和 `--only-platform`，便于从计划表中只选择指定任务或平台实测。
- RPA 示例脚本新增 `--write-plan-status`，真实执行后可显式把 `PREPARED/PARTIAL/FAILED`、截图和错误信息写回 `publish_plan.csv`。
- RPA 示例脚本新增 `--backfill-publish-id`、`--backfill-status`、`--post-url` 等人工回填参数，人工发布或拒绝后可把帖子链接、发布时间和备注写回计划表并追加 JSONL。
- RPA 示例脚本新增 `--summarize-log-jsonl`、`--summary-csv` 和 `--summary-include-history`，可把 `publish_logs.jsonl` 导出为运营可读的 `publish_summary.csv`。
- RPA 示例脚本新增基础异常分类，失败和部分成功会写入稳定 `error_type`，便于运营判断重试、换号或人工处理。

### Changed

- Facebook Page 图片帖已完成 `publish_plan.csv` 计划模式真实执行验证：自动上传图片、填文案、截图并写入 `publish_logs.jsonl`，仍停在最终发布前。
- TikTok 视频已完成 `publish_plan.csv` 计划模式真实执行验证：`PUB-TK-TEST-001` 自动上传视频、填文案、截图、追加 `publish_logs.jsonl`，并通过 `--write-plan-status` 将真实计划表状态写回 `PREPARED`。
- [09-bitbrowser-rpa-example.md](./09-bitbrowser-rpa-example.md)、[10-rpa-publisher-roadmap.md](./10-rpa-publisher-roadmap.md) 和 [TODO.md](./TODO.md) 已同步当前 RPA 状态：批量队列、JSONL、发布汇总 CSV、计划表状态回写、人工回填和基础异常分类均已完成；TK/FB 同窗口顺序执行和多样本彩排仍待实机验证。

### Verified

- 使用临时 `publish_plan_status_test.csv` 验证 `--print-plan` 安全预览、人工 `PUBLISHED_MANUAL` 回填、失败状态回写和 JSONL 追加。
- 使用真实投放包 `publish_plan.csv` 验证 `PUB-TK-TEST-001`，脚本停在最终发布前，截图保存到 `E:\project\dopaMatrix\output\publish-rpa\PUB-TK-TEST-001-tiktok-20260813-162823.png`。
- 使用真实 `publish_logs.jsonl` 导出 `E:\project\dopaMatrix\output\publish-rpa\publish_summary.csv`，当前包含 TK/FB 两条最新任务，并补齐客户、产品、短链和归因字段。
- 使用临时 `publish_plan_error_test.csv` 和坏 API 地址验证异常分类，连接失败会写回 `BITBROWSER_CONNECTION`。

## 2026-07-27

### Added

- 新增 [10-rpa-publisher-roadmap.md](./10-rpa-publisher-roadmap.md)，记录 RPA 发布脚本从单条验证到批量半自动工具的建设计划、优先级和验收标准。
- 新增投放包 `publish_plan.csv` 模板，并在 RPA 示例脚本中支持 `--plan-csv --limit --print-plan`。
- RPA 示例脚本新增 `--log-jsonl`，支持计划任务按行追加 `PLANNED/PREPARED/FAILED` 汇总日志。
- 新增 `product-ops` 文档组，用于沉淀事项清单截图之后的产品运营化讨论。
- 新增 [README.md](./README.md)，作为专题索引和阅读入口。
- 新增 [01-publishing-hub.md](./01-publishing-hub.md)，记录发布中台和半自动发布 MVP。
- 新增 [02-account-strategy.md](./02-account-strategy.md)，记录账号分配、共享账号、客户账号和账号扩容策略。
- 新增 [03-lead-attribution-and-service.md](./03-lead-attribution-and-service.md)，记录询盘归因、AI 客服边界和线索状态机。
- 新增 [04-material-intake-and-dam.md](./04-material-intake-and-dam.md)，记录 Telegram/WhatsApp 接收素材后的本地入库 SOP。
- 新增 [05-client-reporting-portal.md](./05-client-reporting-portal.md)，记录客户报告网页的页面结构和指标口径。
- 新增 [06-viral-gene-loop.md](./06-viral-gene-loop.md)，记录爆款基因、自有内容学习和公网参考采集边界。
- 新增 [07-implementation-roadmap.md](./07-implementation-roadmap.md)，记录阶段路线图和跨模块数据主线。
- 新增 [00-documentation-standard.md](./00-documentation-standard.md)，定义文档状态、模板和维护规则。
- 新增 [DECISIONS.md](./DECISIONS.md)，把当前关键判断转成可追溯决策记录。
- 新增 [TODO.md](./TODO.md)，把规划拆成 P0/P1/P2 待办队列。
- 新增 [08-tk-fb-launch-plan.md](./08-tk-fb-launch-plan.md)，记录 TikTok 视频 + Facebook 图文的第一阶段冲刺计划、时间表和资源清单。
- 新增 [09-bitbrowser-rpa-example.md](./09-bitbrowser-rpa-example.md)，说明比特浏览器 RPA 示例脚本。
- 新增 `docs/scripts/publishing/bitbrowser_rpa_example.py`，作为 TK/FB 半自动发布技术验证脚本，并由 docs 目录统一版本管理。
- 新增 [TK_FB发布试点需求物品清单.xlsx](./TK_FB发布试点需求物品清单.xlsx)，用于负责人准备账号、IP、指纹浏览器环境、素材、权限和 RPA 验证项。

### Changed

- 将文档正文统一为中文，保留必要的英文模块名、字段名和状态枚举。
- 将“落地页”任务边界明确为 DopaMatrix 产品宣传页，不混同客户商品导流页。
- 将 TikTok 10 账号方案标记为试点背景，而不是正式 SOP。
- 将发布 V1 从 TikTok 单平台调整为 TikTok + Facebook 双平台。
- 将 RPA 发布脚本从 `dopamatrix-desktop` 主项目迁移到 `docs/scripts/publishing`，避免污染当前不由我们负责开发的主项目。

### Notes

- 当前全部文档仍是规划草案，不代表功能已经实现。
- 后续当某个模块进入开发，应把相关文档状态从“草案”改为“实施中”，并在本文件记录。
