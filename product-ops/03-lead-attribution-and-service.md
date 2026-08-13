# 询盘归因与客服中心

> 更新时间：2026-07-27  
> 状态：规划草案

## 目标

系统必须能向甲方证明：某条询盘来自我们运营发布的某条内容，并能把询盘分配到正确客户和产品。

最小证据链：

```text
video_id / creative_id
-> publish_id
-> platform account
-> platform post URL
-> product_id
-> client_id
-> attribution_token
-> lead_id
-> 客户反馈/成交状态
```

没有这条链，客户报告只能靠截图和信任，规模一大就会出问题。

## 归因 token

每一条发布记录都应生成唯一 `attribution_token`。token 要在发布计划阶段生成，而不是询盘来了以后再补。

同一个视频发到不同账号，也要有不同 token：

```text
视频 A 发到 TK-PH-001 -> token A1
视频 A 发到 TK-PH-002 -> token A2
```

因为账号、地区、发布时间和受众都会影响效果。

## 询盘来源与可信度

| 来源 | 归因方法 | 可信度 |
| --- | --- | --- |
| 平台原生 Lead Form | 表单/帖子/活动直接绑定 | 确定 |
| 产品目录页或询盘页 | URL token 和产品选择 | 高 |
| WhatsApp | 预填消息携带产品和来源码 | 高 |
| Telegram Bot | Bot 深链参数 | 高 |
| 平台评论 | 评论天然属于某条帖子 | 中高 |
| 帖子入口私信 | 平台提供相关帖子或入口上下文 | 中高 |
| 通用私信 | 需要用户确认产品/视频 | 确认前低 |
| 人工录入 | 运营填写来源证据 | 取决于证据 |

系统应同时保存来源和归因可信度。

## 共享账号下的模糊询盘

一个账号服务多个客户时，如果平台没有提供帖子上下文，用户只问“这个马桶多少钱”，系统不能自动猜是哪一款。

AI 应该澄清：

```text
可以帮您查价格。请问您指的是哪一款？
可以发送视频/截图，也可以从下面几个产品中选择。
价格会因配置和地区不同而变化，请同时告诉我所在国家或城市。
```

分配规则：

1. 平台上下文能确定帖子时，按 `post_id -> product_id -> client_id` 分配。
2. 用户选择产品时，按选择的 `product_id` 分配。
3. 用户发送截图或链接时，由 AI 或人工匹配产品。
4. 仍不明确时，进入共享待确认池。
5. 未确认前，不把询盘暴露给任何具体甲方。

## 客服中心范围

未来需要一个询盘/客服中心，至少包含：

- 统一收件箱：评论、私信、Lead Form、Telegram、WhatsApp、人工录入。
- 产品目录：SKU、图片、价格规则、地区、库存状态、FAQ、禁用说法。
- 客户隔离知识库。
- AI 意图识别和回复草稿。
- 人工接管：价格、库存、售后、投诉、法律和敏感承诺。
- 线索分配和状态跟踪。
- 客户反馈和成交结果回填。
- 归因证据查看。

## AI 客服边界

AI 可以：

- 问澄清问题。
- 根据帖子、图片、产品目录匹配候选产品。
- 基于已审核知识生成回复草稿。
- 提取地区、数量、联系方式和采购意图。
- 标记重复、垃圾、无效询盘。

AI 不可以：

- 编造价格、库存、发货时间、保修、认证或折扣。
- 承诺退款、赔偿、疗效、法律效果等敏感内容。
- 把客户 A 的产品资料发给客户 B 的询盘。
- 在来源不明确但会影响计费时强行分配。

RAG 或知识检索必须把 `client_id` 作为硬过滤条件。共享账号消息不能绕过客户隔离。

## 线索状态

```text
RAW
NEEDS_CLARIFICATION
QUALIFIED
ASSIGNED
CONTACTED
QUOTED
WON
LOST
DUPLICATE
INVALID
SPAM
```

线索表至少需要：

```text
lead_id
client_id
product_id
platform
account_id
publish_id
platform_post_id
source_channel
attribution_token
attribution_confidence
user_handle
raw_message
normalized_intent
country_region
contact_method
assigned_to
status
invalid_reason
deal_amount
created_at
updated_at
evidence_url_or_screenshot
```

## 如何向甲方证明价值

甲方能看到的每条线索应包含：

- 询盘时间。
- 来源平台和账号。
- 来源帖子链接。
- 视频缩略图或创意预览。
- 产品/SKU。
- 用户原始消息。
- 归因方式和可信度。
- 当前状态。
- 销售反馈。

商务上还应提前定义：

- 什么叫有效询盘。
- 重复客户按多少天判定。
- 首次触达还是最后触达归因。
- 模糊询盘如何处理。
- 甲方多久内反馈无效原因。
- 账号级流量能展示，但是否能计费。

## MVP

第一版不需要完整接入所有平台私信。至少要支持：

1. 发布时生成 `attribution_token`。
2. 人工录入或导入询盘。
3. 绑定询盘到 `publish_id`、`client_id`、`product_id`。
4. 记录归因可信度。
5. 标记有效、无效、重复、已报价、已成交。
6. 导出甲方专属线索报告。
