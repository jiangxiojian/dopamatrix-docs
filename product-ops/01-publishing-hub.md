# 发布中台

> 更新时间：2026-07-27  
> 状态：规划草案

## 定位

DopaMatrix 当前已经能生产、审批和导出视频。紧急缺口是发布中台：

```text
交付目录/CSV -> 发布计划 -> 打开指定指纹环境
-> 上传内容 -> 填标题/描述/标签 -> 人工检查
-> 记录发布结果 -> 回收数据
```

第一版不追求全自动无人值守，而是“脚本辅助 + 人工检查点”。脚本负责机械步骤，人负责登录、验证码、安全验证、版权/商业内容声明、最终确认和异常处理。

## MVP 范围

第一阶段建议同时做 TikTok + Facebook Page，但只做最小内容形态：TikTok 发竖屏视频，Facebook Page 发图文帖。账号数量先控制在每个平台 2-5 个，跑通后再扩到 10 个级别。

包含：

- 读取 DopaMatrix 交付目录和 `矩阵投放文案对照表.csv`。
- 解析当前 CSV 字段：视频文件名、社交平台标题、情绪化描述、黄金标签、追踪短链接。
- 维护账号台账和浏览器环境 ID。
- 生成发布计划。
- 打开对应指纹浏览器环境。
- 进入平台上传页。
- TikTok 上传视频文件。
- Facebook Page 上传图片并填写图文帖。
- 填写标题、描述、标签和平台允许的链接字段。
- 在不可逆发布动作前按需要暂停，交给人工确认。
- 保存截图、状态、异常原因和帖子链接。

第一版不做：

- 自动注册账号。
- 通过模拟行为“养号”。
- 绕过验证码或安全验证。
- 全平台全自动无人值守发布。
- 以坐标点击 RPA 作为长期主方案。
- 把私信抓取当作发布模块的前置依赖。

## 模块拆分

| 模块 | 职责 |
| --- | --- |
| Delivery Importer | 读取交付 ZIP/文件夹和 CSV，整理待发布内容。 |
| Account Registry | 管理平台账号、所有权、浏览器环境、代理、状态和发布限制。 |
| Publish Planner | 决定哪个内容、哪个账号、什么时间发布。 |
| Browser Adapter | 对接比特浏览器或其他指纹浏览器 Local API。 |
| Platform Publisher | TikTok、Facebook Page、Instagram 等平台各自的上传流程。 |
| Human Checkpoint | 登录、验证码、异常弹窗、版权声明、最终确认等暂停点。 |
| Publish Log | 记录截图、状态、帖子链接、失败原因、重试历史。 |
| Metrics Sync | 发布后回收或导入平台表现数据。 |

发布中台应独立于渲染链路。渲染链路产出已审批素材，发布中台消费已审批素材。

## 最小发布计划表

```csv
platform,account_code,browser_profile_id,video_filename,title,caption,hashtags,tracking_url,scheduled_at,status,operator,note
tiktok,TK-PH-001,bit_profile_xxx,Tk01_CoreTag_极度渴望_32f22a.mp4,让你的驾驶更舒适！,不再忍受颠簸...,#汽车减震器 #驾驶舒适,https://dopa.mx/t/7979b0,2026-07-28 10:30,READY,,
facebook,FB-PH-001,bit_profile_fb_xxx,FB01_减震器_图文.jpg,让驾驶更稳,这款减震器适合日常通勤和长途驾驶...,#汽车配件 #驾驶舒适,https://dopa.mx/t/fb001,2026-07-28 11:00,READY,,
```

内部数据库不能只靠文件名关联。每条发布记录至少需要：

```text
publish_id
client_id
product_id
creative_id / video_id
gene_version
platform
account_id
browser_profile_id
scheduled_at
published_at
platform_post_id
post_url
attribution_token
status
operator
error_code
error_message
evidence_screenshot_path
```

## 状态机

```text
DRAFT
READY
OPENING_BROWSER
WAITING_LOGIN
UPLOADING
WAITING_HUMAN_CHECK
PUBLISHED
FAILED_RETRYABLE
FAILED_FINAL
CANCELLED
```

人工检查点应该是明确状态，而不是隐藏在异常里。这样后续才能统计验证码频率、登录异常、平台弹窗和操作耗时。

## 浏览器自动化方案

优先路径：

1. 通过比特浏览器 Local API 打开固定浏览器环境。
2. 确认打开后的窗口是否能暴露调试端口。
3. 用 Playwright/CDP 控制页面。
4. 尽量使用 DOM selector 和页面状态，不依赖屏幕坐标。

如果比特浏览器无法提供可控端点，只能退化成坐标点击式 RPA。这个方案维护成本高，只适合短期内部验证，不适合作为长期产品能力。

## 平台风险

指纹浏览器只能做环境隔离，不是免检通行证。自动化仍可能被平台识别，或被 UI 改版、登录验证、上传失败、账号限制、音乐版权声明、地区政策弹窗打断。

操作原则：

- 不绕过验证码。
- 不模拟虚假互动。
- 不批量同步发布完全重复内容。
- 账号身份、地区、代理、语言和发布节奏保持稳定。
- 所有异常提示都截图记录原因。

## 第一里程碑

第一里程碑不是大规模发布，而是：

1. 导入一个 DopaMatrix 交付目录。
2. 绑定 2-3 个已登录的 TikTok 指纹浏览器环境和 2-3 个 Facebook Page 管理环境。
3. 通过脚本辅助流程发布 3-5 条 TikTok 视频。
4. 通过脚本辅助流程发布 3-5 条 Facebook Page 图文帖。
5. 记录截图、帖子链接、状态和失败原因。
6. 次日复登，确认账号仍可登录、帖子仍可见。

完成这个闭环后，再扩到每个平台 10 个账号级别和更多内容形态。

## 示例脚本

比特浏览器 RPA 示例见：

- [09-bitbrowser-rpa-example.md](./09-bitbrowser-rpa-example.md)
- [bitbrowser_rpa_example.py](../scripts/publishing/bitbrowser_rpa_example.py)
