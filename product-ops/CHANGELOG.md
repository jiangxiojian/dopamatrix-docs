# 文档变更日志

> 更新时间：2026-08-14
> 文档类型：变更日志  
> 状态：草案

## 2026-08-14

### Added

- RPA 示例脚本新增 `--generate-plan`，可从投放包目录、`矩阵投放文案对照表.csv`、`账号环境台账.csv` 和素材文件自动生成 `publish_plan.csv`。
- 发布计划生成器新增 `--plan-video-platforms`、`--plan-image-platforms`、`--plan-client-id`、`--plan-product-id`、`--plan-scheduled-start`、`--plan-interval-minutes` 等参数；默认视频生成 TikTok 任务、图片生成 Facebook 任务。
- 发布计划生成器默认拒绝覆盖已有 `publish_plan.csv`，需要显式传 `--overwrite-plan` 或使用 `--output-plan-csv` 输出到临时文件。
- 一键运行模式增强：找不到 READY 计划时，如果项目里只有一个安全投放包且尚未存在 `publish_plan.csv`，脚本会先自动生成计划表；已有计划表但没有 READY 时会停止并提示运营处理状态。
- RPA 执行日志和发布汇总新增 `duration_seconds`，用于排查上传慢、页面等待和账号验证导致的耗时。
- RPA 发布计划生成器新增 `--plan-repeat`，用于用同一素材生成多条唯一 `publish_id`/`attribution_token` 的内部彩排任务。
- RPA 异常分类补充 `PROXY_CONNECTION_FAILED` 和 `BROWSER_TARGET_CLOSED`，并修复 `facebook` 平台名误触发 `face` 人脸验证判断的问题。
- 将后续“简易报告页/人工确认台”统一命名为 `RPA 发布操作台 V1`，明确第一版读取本地计划表、JSONL、汇总 CSV 和截图。
- 新增 `scripts/publishing/rpa_operator_console.py`，可生成本地静态 `RPA 发布操作台` HTML，集中展示任务状态、截图预览、错误信息、人工备注和回填命令；没有 `publish_summary.csv` 时会尝试从 `publish_logs.jsonl` 读取最新记录。
- RPA 主脚本新增 `PlatformPublisher`、`TikTokPublisher`、`FacebookPublisher` 和平台注册表，主流程改为通过 `get_publisher(platform)` 调度平台准备逻辑。
- RPA 异常分类继续细化：补充 `MEDIA_FORMAT_UNSUPPORTED`、`PLATFORM_RATE_LIMIT_OR_RESTRICTION`、`FACEBOOK_FILE_CHOOSER_TIMEOUT`、`FACEBOOK_PAGE_ACCESS`、`TIKTOK_CONTENT_CHECK_SETTING`，并把部分成功结果细分为 TK/FB 上传或文案失败。

### Verified

- 使用真实投放包生成 `E:\project\dopaMatrix\output\publish-rpa\generated-plan-test.csv`，当前包内只有视频素材，因此生成 1 条 TikTok READY 任务。
- 对生成的计划表执行 `--print-plan --limit 1`，确认可正确解析素材路径、账号台账、caption、追踪短链和归因 token。
- 验证已有 `publish_plan.csv` 时默认拒绝覆盖，避免冲掉执行结果和人工回填状态。
- 使用临时投放包验证 `--one-click --print-plan`：没有现成计划表时可先自动生成 `publish_plan.csv`，再进入计划预览；测试任务已回填为 `REJECTED_MANUAL`，避免后续误跑。
- 验证没有 READY 且已有计划表时，一键模式会停止并提示运营把待跑行改为 `READY` 或显式重新生成计划表。
- 使用 `E:\project\dopaMatrix\output\publish-rpa\batch-sample-test\publish_plan.csv` 完成 3 条 TikTok + 3 条 Facebook 同窗口顺序彩排：代理开启后 6 条均 `uploaded=true`、`caption_filled=true`、`PREPARED`，脚本未点击最终发布。
- 首次批量彩排因代理未开启产生 6 条失败记录；开启代理后用 `--include-status FAILED,READY,PARTIAL` 成功重试，并导出 `E:\project\dopaMatrix\output\publish-rpa\batch-sample-test\publish_summary.csv`。
- 按“不发布”决定将 6 条批量彩排草稿统一人工回填为 `REJECTED_MANUAL`，避免误认为仍需人工发布。
- 使用批量彩排目录生成 `E:\project\dopaMatrix\output\publish-rpa\batch-sample-test\rpa_operator_console.html`，确认页面包含 6 条任务、`REJECTED_MANUAL` 状态筛选、截图 file 链接和 `PUBLISHED_MANUAL` / `REJECTED_MANUAL` 回填命令；同时验证缺少汇总 CSV 时可用 JSONL 兜底生成。
- 静态验证平台注册表和错误分类：`tiktok` 可调度到 `TikTokPublisher`，`facebook` 可调度到 `FacebookPublisher`，部分成功结果可返回平台级错误码；用 FB `--print-plan` 确认计划表解析仍正常，不打开浏览器、不发布。

## 2026-08-13

### Added

- RPA 示例脚本新增 `--only-publish-id` 和 `--only-platform`，便于从计划表中只选择指定任务或平台实测。
- RPA 示例脚本新增 `--write-plan-status`，真实执行后可显式把 `PREPARED/PARTIAL/FAILED`、截图和错误信息写回 `publish_plan.csv`。
- RPA 示例脚本新增 `--backfill-publish-id`、`--backfill-status`、`--post-url` 等人工回填参数，人工发布或拒绝后可把帖子链接、发布时间和备注写回计划表并追加 JSONL。
- RPA 示例脚本新增 `--summarize-log-jsonl`、`--summary-csv` 和 `--summary-include-history`，可把 `publish_logs.jsonl` 导出为运营可读的 `publish_summary.csv`。
- RPA 示例脚本新增基础异常分类，失败和部分成功会写入稳定 `error_type`，便于运营判断重试、换号或人工处理。
- RPA 示例脚本新增 `--tab-mode new|reuse-first`，默认每条任务新开 Tab，避免同一比特窗口里 TK/FB 顺序任务互相覆盖草稿。
- RPA 示例脚本新增 `--trace-tabs`、`--stop-after-connect` 和 `--close-task-tab`，用于诊断同一指纹窗口内多个 Tab 的隔离情况。
- RPA 示例脚本新增 `--facebook-upload-mode input-only|auto|file-chooser`，默认使用 `auto`；同时新增 `--clean-blank-tabs` 清理测试产生的 `about:blank`。
- RPA 示例脚本新增一键运行模式：直接运行脚本或双击 `run_publisher.cmd`，自动发现 READY 计划、读取台账、写日志/状态并停在人工发布前。

### Changed

- Facebook Page 图片帖已完成 `publish_plan.csv` 计划模式真实执行验证：自动上传图片、填文案、截图并写入 `publish_logs.jsonl`，仍停在最终发布前。
- TikTok 视频已完成 `publish_plan.csv` 计划模式真实执行验证：`PUB-TK-TEST-001` 自动上传视频、填文案、截图、追加 `publish_logs.jsonl`，先通过 `--write-plan-status` 写回 `PREPARED`，后按“不发布”决定人工回填为 `REJECTED_MANUAL`。
- [09-bitbrowser-rpa-example.md](./09-bitbrowser-rpa-example.md)、[10-rpa-publisher-roadmap.md](./10-rpa-publisher-roadmap.md) 和 [TODO.md](./TODO.md) 已同步当前 RPA 状态：批量队列、JSONL、发布汇总 CSV、计划表状态回写、人工回填和基础异常分类均已完成；TK/FB 同窗口顺序执行和多样本彩排仍待实机验证。
- 记录 2026-08-13 TK/FB 同窗口顺序彩排问题：旧脚本复用已有 Tab，导致 FB composer 覆盖 TK 草稿；脚本已改为默认 Tab 隔离，等待重新实机复测。

### Verified

- 使用临时 `publish_plan_status_test.csv` 验证 `--print-plan` 安全预览、人工 `PUBLISHED_MANUAL` 回填、失败状态回写和 JSONL 追加。
- 使用真实投放包 `publish_plan.csv` 验证 `PUB-TK-TEST-001`，脚本停在最终发布前，截图保存到 `E:\project\dopaMatrix\output\publish-rpa\PUB-TK-TEST-001-tiktok-20260813-162823.png`；该测试草稿不发布，已回填 `REJECTED_MANUAL`。
- 使用真实 `publish_logs.jsonl` 导出 `E:\project\dopaMatrix\output\publish-rpa\publish_summary.csv`，当前包含 TK/FB 两条最新任务，并补齐客户、产品、短链和归因字段。
- 使用临时 `publish_plan_error_test.csv` 和坏 API 地址验证异常分类，连接失败会写回 `BITBROWSER_CONNECTION`。
- 使用目标窗口 `82b4fd0926b9469f830c6c4e2dc4e589` 验证 Tab 隔离：关闭窗口后由脚本重新打开、窗口已打开后再次执行，均会保留原有 Tab 并新建任务 Tab。
- 使用默认 `--tab-mode new` 验证 TikTok 冷启动完整草稿准备，截图 `E:\project\dopaMatrix\output\publish-rpa\PUB-SEQUENCE-TK-001-tiktok-20260813-182536.png`；脚本未点击发布。
- 使用默认 `--tab-mode new` 验证 Facebook 已打开窗口完整草稿准备，截图 `E:\project\dopaMatrix\output\publish-rpa\PUB-SEQUENCE-FB-001-facebook-20260813-182007.png`；脚本未点击发布。
- 验证 Facebook `input-only` 模式不会弹出原生文件管理器，但当前页面不暴露可直接设置的 file input，因此返回 `UPLOAD_NOT_CONFIRMED`。
- 验证 Facebook `auto` 模式通过 Playwright 受控 file chooser 上传成功，截图 `E:\project\dopaMatrix\output\publish-rpa\PUB-SEQUENCE-FB-001-facebook-20260813-185116.png`；脚本未点击发布。
- 使用 `--clean-blank-tabs` 清理目标窗口 `82b4fd0926b9469f830c6c4e2dc4e589` 中测试产生的 1 个 `about:blank` Tab。
- 多轮验证 Facebook 上传策略：`auto` 窗口已打开连续 3 次、冷启动 1 次、零上传参数 1 次均完成上传和文案填充；`file-chooser` 直连连续 3 次也成功，但默认采用兼容性更好的 `auto`。
- 直接无参数运行脚本验证一键模式：自动发现临时 READY 计划、打开环境、使用默认 `auto` 上传、写回 `PREPARED`，未点击最终发布。

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
