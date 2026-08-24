# 发布数据结构草案

> 更新时间：2026-08-20  
> 文档类型：表结构草案  
> 状态：草案

## 目的

这份草案只管一件事：把发布计划和发布日志先定成稳定的数据主线，后面无论是 CSV、JSONL 还是数据库，都尽量沿着同一套字段演进。

当前脚本里已经在用的现实形态是：

- `rpa_work/publish_plan.csv` 作为运营计划表
- `rpa_work/publish_logs.jsonl` 作为执行事件日志
- `rpa_work/publish_summary.csv` 作为汇总视图

`rpa_work/` 是当前 CSV/JSONL 文件的物理落点；未来上数据库时，建议保持同样的语义。

## `publish_plans`

一行代表一个待发布或已发布的任务。

### 主键

- `publish_id`

### 建议字段

| 字段 | 含义 |
| --- | --- |
| `publish_id` | 稳定任务 ID。 |
| `client_id` | 客户 ID。 |
| `product_id` | 产品 ID。 |
| `platform` | `tiktok` / `facebook`。 |
| `content_type` | `video` / `image`。 |
| `facebook_content_mode` | FB 入口模式，例 `post` / `reel` / `story`。 |
| `composer_url` | 平台发布入口。 |
| `account_key` | 账号台账里的账号键。 |
| `browser_profile_id` | 比特浏览器环境 ID。 |
| `media_path` | 素材路径。 |
| `title` | 标题或文案标题。 |
| `caption` | 发布文案。 |
| `hashtags` | 标签。 |
| `tracking_url` | 追踪短链。 |
| `attribution_token` | 归因 token。 |
| `scheduled_at` | 计划发布时间。 |
| `status` | `READY` / `PREPARED` / `FAILED` / `PUBLISHED_MANUAL` / `REJECTED_MANUAL` 等。 |
| `operator` | 计划操作者。 |
| `note` | 计划备注。 |
| `last_result_status` | 最近一次执行结果。 |
| `last_result_at` | 最近一次结果时间。 |
| `result_screenshot` | 最近一次截图。 |
| `error_type` | 稳定错误类型。 |
| `error_action` | 处置建议码。 |
| `error_action_label` | 处置建议中文说明。 |
| `error_message` | 错误信息。 |
| `post_url` | 公开帖子链接。 |
| `platform_post_id` | 平台帖子 ID。 |
| `published_at` | 公开发布时间。 |
| `manual_operator` | 人工回填人。 |
| `manual_checked_at` | 人工确认时间。 |
| `manual_note` | 人工备注。 |
| `created_at` | 记录创建时间。 |
| `updated_at` | 记录更新时间。 |

### 建议索引

- `publish_id` 唯一索引
- `status`
- `platform, status`
- `client_id, product_id`
- `account_key`
- `scheduled_at`

## `publish_logs`

一行代表一次执行事件或状态快照，建议追加写入，不覆盖历史。

### 主键

- `log_id`

### 建议字段

| 字段 | 含义 |
| --- | --- |
| `log_id` | 日志主键。 |
| `publish_id` | 关联的发布任务。 |
| `event_type` | `PLANNED` / `RUNNING` / `PREPARED` / `FAILED` / `POST_URL_DETECTED` / `POST_URL_NOT_FOUND` 等。 |
| `platform` | 平台。 |
| `client_id` | 客户 ID。 |
| `product_id` | 产品 ID。 |
| `account_key` | 账号键。 |
| `profile_id` | 浏览器环境 ID。 |
| `profile_name` | 浏览器环境名称。 |
| `status` | 当时状态。 |
| `uploaded` | 是否确认上传。 |
| `caption_filled` | 是否确认填文案。 |
| `media_processing_required` | 是否需要媒体处理等待。 |
| `media_processing_confirmed` | 是否确认媒体处理完成。 |
| `media_processing_signal` | 媒体处理信号。 |
| `processing_wait_seconds` | 等待耗时。 |
| `post_url` | 识别到的帖子链接。 |
| `platform_post_id` | 识别到的平台帖子 ID。 |
| `published_at` | 识别或回填的发布时间。 |
| `candidate_count` | 命中的候选数。 |
| `candidate_sources` | 候选来源摘要。 |
| `scanned_tab_count` | 扫描页签数。 |
| `scanner_error_count` | 页面扫描错误数。 |
| `scanner_errors` | 扫描错误摘要。 |
| `screenshot` | 相关截图路径。 |
| `error_type` | 错误类型。 |
| `error_action` | 处置建议码。 |
| `error_action_label` | 处置建议中文说明。 |
| `error_message` | 错误信息。 |
| `duration_seconds` | 任务耗时。 |
| `started_at` | 开始时间。 |
| `finished_at` | 结束时间。 |
| `checkpoint` | 当前检查点。 |
| `payload_json` | 原始事件载荷。 |
| `created_at` | 日志写入时间。 |

### 建议索引

- `log_id` 唯一索引
- `publish_id, created_at`
- `event_type`
- `status`
- `platform, created_at`

## 关系

- `publish_plans` 是计划源表。
- `publish_logs` 是追加事件表。
- `rpa_work/publish_summary.csv` 是从日志和计划拼出来的运营视图，不建议当源表。

## 状态流

```text
READY -> RUNNING -> PREPARED -> PUBLISHED_MANUAL
READY -> RUNNING -> FAILED -> READY/RETRY
PREPARED -> REJECTED_MANUAL
PREPARED -> POST_URL_NOT_FOUND -> RETRY_OR_MANUAL_CHECK
```

## 迁移原则

1. 先保证 `publish_id` 稳定。
2. 先保证日志可追加，不要丢历史。
3. 计划表负责“该发什么”，日志负责“实际发生了什么”。
4. 报告页和操作台只读这两层，不直接依赖临时截图命名。
