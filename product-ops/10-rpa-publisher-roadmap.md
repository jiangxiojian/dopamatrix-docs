# RPA 发布脚本建设计划

> 更新时间：2026-08-13  
> 文档类型：方案 / 待办拆解  
> 状态：实施中  
> 适用阶段：客户试点前  
> 相关文档：[08-tk-fb-launch-plan.md](./08-tk-fb-launch-plan.md), [09-bitbrowser-rpa-example.md](./09-bitbrowser-rpa-example.md), [TODO.md](./TODO.md)

## 目标

把当前的比特浏览器验证脚本，从“单条内容测试工具”推进到“运营可用的半自动发布工具”。

第一阶段目标仍然很克制：

```text
读取发布计划 -> 选择账号环境 -> 打开 TK/FB 发布页
-> 上传素材 -> 填文案 -> 截图和日志 -> 人工确认发布
```

脚本不追求全自动无人值守，不绕过验证码、安全验证或平台限制。最终发布按钮继续由人工确认，直到账号、素材、平台弹窗和日志回填都足够稳定。

## 当前已完成

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| 比特浏览器 Local API 连通 | 已验证 | `POST /health` 可用，`/browser/open` 可打开指定窗口。 |
| CDP 接管比特窗口 | 已验证 | 已通过返回的 `ws` 地址连接真实窗口。 |
| TikTok 视频上传 | 已验证计划模式 | 可打开上传页、上传 MP4、从 CSV/计划表拼接 caption，停在发布前；`PUB-TK-TEST-001` 已验证并按“不发布”回填为 `REJECTED_MANUAL`。 |
| TikTok 内容检查弹窗处理 | 已实现基础版 | 默认 `pause`，人工决定是否开启自动内容检查。 |
| Facebook Page 图片帖准备 | 已验证 | 在 `Bright Auto Picks` Page 上验证：单条命令和 `publish_plan.csv` 计划模式均可自动上传图片、填文案、截图，停在发布前。 |
| 交付 CSV 读取 | 已实现基础版 | 按 `视频文件名` 匹配 `矩阵投放文案对照表.csv`。 |
| 账号环境台账读取 | 已实现基础版 | 可按 `账号键`、平台或默认行读取窗口 ID。 |
| `publish_plan.csv` 模板 | 已完成 | 已在投放包目录创建 TK 视频和 FB 图片两条 READY 样例。 |
| 发布计划预览 | 已实现基础版 | 支持 `--plan-csv --limit --print-plan`，可不打开浏览器检查任务解析结果。 |
| 批量队列读取 | 已实现基础版 | 支持读取 READY 行，并用 `--limit`、`--only-publish-id`、`--only-platform` 限制执行范围。 |
| JSONL 汇总日志 | 已实现基础版 | 支持 `--log-jsonl` 追加 `PLANNED/PREPARED/FAILED` 记录。 |
| 发布汇总 CSV | 已实现基础版 | 支持 `--summarize-log-jsonl` 导出 `publish_summary.csv`，默认每个 `publish_id` 保留最新状态，并从 `plan_csv` 补齐客户、产品、短链和归因字段。 |
| 计划表状态回写 | 已实现基础版 | 显式传 `--write-plan-status` 后，可把 `PREPARED/PARTIAL/FAILED`、截图和错误信息写回 `publish_plan.csv`。 |
| 人工发布后回填 | 已实现基础版 | 支持 `--backfill-publish-id` 回填 `PUBLISHED_MANUAL/REJECTED_MANUAL`、帖子链接、发布时间、人工备注，并追加 JSONL。 |
| 异常分类 | 已实现基础版 | 已能把常见异常归类为 `BITBROWSER_CONNECTION`、`MEDIA_PATH_INVALID`、`ACCOUNT_VERIFICATION`、`LOGIN_REQUIRED`、`UPLOAD_NOT_CONFIRMED` 等。 |
| Tab 隔离 | 已实机验证 | 默认 `--tab-mode new`，每条任务新开 Tab；关闭窗口后重开、窗口已打开再次执行、TK 单条和 FB 单条草稿准备均确认不会覆盖原 Tab。 |
| Tab 诊断 | 已实现基础版 | 支持 `--trace-tabs`、`--stop-after-connect`、`--close-task-tab` 和 `--clean-blank-tabs`，可排查同窗口多平台时的页面隔离。 |
| Facebook 上传策略 | 已实机验证基础版 | 支持 `input-only/auto/file-chooser`；默认 `auto`，多轮实测通过受控 file chooser 完成上传，且不再裸点按钮。 |
| 一键运行入口 | 已实机验证基础版 | 直接运行脚本或双击 `run_publisher.cmd`，自动发现 READY 计划、读取台账、写日志/状态并停在人工发布前。 |
| 单次截图 | 已实现 | 每次 RPA 可保存发布前截图。 |
| 单次 JSON 日志 | 已实现基础版 | `--log-json` 可记录账号、素材、截图和执行结果。 |
| 计划预览 | 已实现 | `--print-plan` 可只解析台账/素材/文案，不打开浏览器。 |

## 仍未完成

| 模块 | 缺口 | 为什么重要 |
| --- | --- | --- |
| 批量发布队列 | 基础版已能读取多条 READY 行并顺序执行；还没有大样本连续彩排、单任务超时隔离、原生文件选择器防卡死策略和并发窗口调度。 | 运营需要一次导入多条任务，逐条执行和记录结果，同时不能误发或串号。 |
| TK + FB 顺序模式 | Tab 隔离已实机通过；同一命令连续跑 TK+FB 时曾因 FB 等待超时中断，还需优化单任务超时和批量继续策略。 | 一个素材包通常要同时发 TK 视频和 FB 图文，且必须保留前一条草稿给人工检查。 |
| 发布计划格式 | 模板已存在；还不是由 DopaMatrix 导出包自动生成，也没有内置状态字段模板。 | 运营手工整理容易出错，后续需要自动生成和回填。 |
| 发布结果总表 | JSONL 和汇总 CSV 基础版已完成；还没有网页看板和 post URL 自动采集。 | 需要看每条任务成功、失败、截图、人工处理状态。 |
| 发布后回填 | 手工回填命令已完成；还不能自动读取帖子 URL、发布时间、平台 post id。 | 报告、归因和客户交付都需要帖子链接和状态。 |
| Facebook 内容类型 | 只验证了 Page 图片帖。 | 后续还需要 FB 视频/Reels、快拍、个人主页测试入口。 |
| Facebook 上传稳定性 | 当前 Page 图片帖多轮 `auto` 测试已通过；仍需其他 Page、视频/Reels 和更多图片样本。 | FB 页面不稳定时容易弹系统文件选择器，必须确保脚本不会卡死整组任务。 |
| TikTok 多样本稳定性 | 已完成 1 条计划模式实机验证，还没有连续 3-5 条样本。 | 需要连续样本证明选择器和弹窗处理可靠。 |
| 异常分类细化 | 基础错误码已完成；还没有按 TK/FB 页面截图和弹窗做更细的判定。 | 运营需要知道是重试、换号、人工处理还是废弃任务。 |
| 人工确认台 | 现在只停在浏览器页面，没有统一任务列表。 | 批量运行时需要集中看截图、账号、客户、素材、文案。 |
| 平台弹窗库 | 只处理少数安全弹窗。 | 平台 UI 会频繁弹新提示，需要记录和逐步补规则。 |

## 优先级

### P0：把单条脚本变成可批量使用

| 优先级 | 任务 | 验收标准 |
| --- | --- | --- |
| P0-1 | 定义 `publish_plan.csv` 模板 | 已完成。支持 TK 视频和 FB 图片；包含平台、账号键、窗口 ID、素材路径、文案、短链、排期、状态字段。 |
| P0-2 | 实现批量队列读取 | 已实现基础版。脚本可读取 READY 任务，按顺序逐条执行，并支持 `--limit`。 |
| P0-3 | 实现结果日志汇总 | 已实现基础版。每条任务可写入 JSONL，记录 `PLANNED/PREPARED/FAILED` 等状态。 |
| P0-4 | 增加计划表状态回写 | 已实现基础版。显式 `--write-plan-status` 后写回执行状态、截图和错误信息。 |
| P0-5 | 增加发布后手工回填命令 | 已实现基础版。人工发布或拒绝后可回填帖子 URL、发布时间和备注。 |
| P0-6 | 导出发布汇总 CSV | 已实现基础版。可从 JSONL 生成运营可读 CSV，并补齐计划表里的归因字段。 |
| P0-7 | 支持同一窗口跨平台顺序执行 | Tab 隔离已通过实机验证；下一步处理连续计划执行里的单任务超时隔离。 |
| P0-8 | 完成 TK/FB 各 3 条样本彩排 | 每条都有截图、日志、人工确认结果和异常记录。 |
| P0-9 | 一键运行模式 | 已完成基础版。直接运行脚本即可自动发现 READY 计划、准备草稿、写日志和状态，停在人工确认点。 |

### P1：提高稳定性和可运营性

| 优先级 | 任务 | 验收标准 |
| --- | --- | --- |
| P1-1 | 拆分 `TikTokPublisher` / `FacebookPublisher` | 平台选择器、弹窗处理、上传逻辑分开维护。 |
| P1-2 | 细化平台异常分类 | 基础版已完成；下一步按 TK/FB 弹窗、账号验证、Page 选择错误和素材格式做更细分类。 |
| P1-3 | 生成简易报告页 | 从 JSONL/计划表里查看每条任务的状态、截图、人工结果和帖子链接。 |
| P1-4 | 增强截图命名规则 | 截图按 `publish_id/platform/account_key/timestamp` 自动命名，后续可按账号归档。 |
| P1-5 | 支持 Facebook Reels/视频 | 至少验证 1 条视频上传到 FB Page，并停在发布前。 |

### P2：从脚本走向小工具

| 优先级 | 任务 | 验收标准 |
| --- | --- | --- |
| P2-1 | 做人工确认工作台 | 能列表展示任务、截图、账号、平台、文案和当前状态。 |
| P2-2 | 对接 DopaMatrix 导出包 | 从交付目录自动生成 `publish_plan.csv`，不要求接主产品数据库。 |
| P2-3 | 对接报告和归因 | 发布日志可被客户报告和询盘归因读取。 |
| P2-4 | 自动更新账号健康字段 | 根据验证码、封禁、登录失效等记录账号状态。 |

## 建议执行顺序

1. 用 `--print-plan` 预览真实投放包，确认账号、素材路径、caption 和短链都正确。
2. 用 `--only-publish-id` 每次只跑 1 条，必要时加 `--write-plan-status` 回写计划表。
3. 人工确认发布后，用 `--backfill-publish-id` 回填帖子链接和发布时间。
4. 导出 `publish_summary.csv`，确认客户、产品、账号、素材、状态、截图和归因字段完整。
5. 再做 TK/FB 同窗口顺序彩排，使用默认 `--tab-mode new`，先顺序，不并发。
6. 最后补平台发布器拆分、异常分类和人工确认页面。

这样做的原因是：现在单条动作已经验证过，下一步最容易失控的不是“按钮点不到”，而是运营批量跑的时候不知道哪条任务用了哪个账号、哪个素材、卡在哪里、有没有误发风险。

## 数据文件规划

### 账号环境台账

现有文件：

```text
E:\project\dopaMatrix\dopamatrix_delivery_1781700321(1)\账号环境台账.csv
```

继续作为账号和比特窗口的对应表。脚本已支持读取 `账号键`、`平台`、`窗口ID`、`窗口名称`、`内容检查处理`、`默认`、`备注` 等字段。

### 发布计划

建议新增：

```text
publish_plan.csv
```

推荐字段：

```csv
publish_id,client_id,product_id,platform,content_type,account_key,browser_profile_id,media_path,title,caption,hashtags,tracking_url,attribution_token,scheduled_at,status,operator,note,last_result_status,last_result_at,result_screenshot,error_type,error_message,post_url,published_at,manual_operator,manual_checked_at,manual_note
```

其中 `browser_profile_id` 可以为空，脚本优先用 `account_key` 从账号台账查；只有临时测试才直接填窗口 ID。`media_path` 的相对路径按 `publish_plan.csv` 所在目录解析，所以计划表应保存在投放包目录内。

### 发布日志

建议新增：

```text
publish_logs.jsonl
```

每行一条执行记录，至少包含：

```json
{
  "publish_id": "PUB-001",
  "platform": "facebook",
  "account_key": "fb_test_sg_001",
  "profile_id": "82b4fd0926b9469f830c6c4e2dc4e589",
  "media_path": "...",
  "caption_source": "plan_csv",
  "uploaded": true,
  "caption_filled": true,
  "status": "PREPARED",
  "screenshot": "...",
  "error_type": "",
  "error_message": "",
  "started_at": "2026-08-12T16:00:00",
  "finished_at": "2026-08-12T16:01:00"
}
```

状态回写和人工回填目前都写 `publish_plan.csv`，并可同时追加 JSONL；后续做看板时，优先从 JSONL 建汇总，再反向检查计划表是否漏回填。

当前脚本已经支持把 JSONL 导出为：

```text
E:\project\dopaMatrix\output\publish-rpa\publish_summary.csv
```

这个 CSV 是报告网页前的过渡产物，不替代后续数据库和看板。

## 状态维护规则

1. 每次脚本新增能力后，同步更新本文件的“当前已完成”和“仍未完成”。
2. 每次真实平台验证后，同步更新 [09-bitbrowser-rpa-example.md](./09-bitbrowser-rpa-example.md) 的“需要实机验证的问题”。
3. 每次待办状态改变后，同步更新 [TODO.md](./TODO.md)。
4. 每次提交前，在 [CHANGELOG.md](./CHANGELOG.md) 记录新增能力、验证结果和仍未覆盖的风险。

## 状态机

| 状态 | 含义 |
| --- | --- |
| `READY` | 已生成发布计划，等待脚本处理。 |
| `RUNNING` | 脚本正在打开窗口、上传素材或填写文案。 |
| `PREPARED` | 脚本已准备好草稿，等待人工检查发布。 |
| `FAILED` | 脚本执行失败，需要人工判断是否重试。 |
| `SKIPPED` | 主动跳过，例如账号不可用或排期未到。 |
| `PUBLISHED_MANUAL` | 人工确认并发布，已记录帖子链接或截图。 |
| `REJECTED_MANUAL` | 人工检查后决定不发布。 |

## 平台安全边界

1. 不自动点击最终发布按钮，除非后续明确做“人工确认后脚本点击”的独立版本。
2. 不绕过验证码、人脸验证、安全检查或平台限制。
3. 不做刷粉、刷赞、刷评论、账号互导等动作。
4. 新号测试控制频率，先一条一条跑，不连续高频重试。
5. 平台弹窗涉及账号级设置时默认暂停，例如 TikTok 自动内容检查。
6. 同一个比特窗口可以测试 TK + FB，但批量执行时只顺序跑，不并发操作。
7. 同窗口多平台时必须保持 Tab 隔离，默认每条任务新开 Tab；复用已有 Tab 只用于临时调试，避免后一条任务覆盖前一条草稿。

## 第一批验收清单

| 验收项 | 目标 |
| --- | --- |
| TK 样本 | 3 条视频自动上传并填文案，停在发布前。 |
| FB 样本 | 3 条图片帖自动上传并填文案，停在发布前。 |
| 日志 | 每条样本有 JSON/JSONL 记录。 |
| 截图 | 每条样本有发布前确认截图。 |
| 账号台账 | 每条任务能追溯到账号键、平台、窗口 ID、代理地区。 |
| 失败记录 | 至少记录失败类型和截图，不静默失败。 |

## 暂不做

- 自动注册账号。
- 自动养号。
- 绕过验证码或人脸验证。
- 无人值守批量发布。
- 自动点击最终发布。
- 接入 TikTok / Facebook 官方发布 API。
- 改 DopaMatrix 主产品代码或数据库。

## 下一步

下一步建议继续 `P0-7` 和 `P0-8`：先用新版 `--tab-mode new` 重新做 TK + FB 同窗口顺序彩排，再补足 TK/FB 各 3 条样本记录。完成后补平台发布器拆分和异常分类，避免脚本继续堆成一个大函数。
