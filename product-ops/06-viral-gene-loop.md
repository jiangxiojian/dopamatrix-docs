# 爆款基因闭环

> 更新时间：2026-07-27  
> 状态：规划草案

## 目的

DopaMatrix 不能只像一个盲目生成器。它应该从已发布结果里学习：

```text
生产 -> 发布 -> 指标回收 -> 基因分析 -> 受控实验 -> 下一批生产
```

目标不是抄爆款，而是提取结构化创意特征，并测试哪些特征会提升播放、留存、询盘和成交。

## 什么叫基因

所谓爆款基因，是指可以被追踪、复用和变体化的结构化创意特征。

| 基因类型 | 例子 |
| --- | --- |
| Hook | 提问、反差、前后对比、痛点、好奇缺口、价格揭示。 |
| 情绪 | 渴望、焦虑、释然、嫉妒、信任、紧迫感。 |
| 叙事 | 问题-解决、对比、证明、演示、失败后反转。 |
| 视觉 | 首帧、人物、产品特写、字幕密度、镜头运动、镜头节奏。 |
| 剪辑 | 视频长度、镜头数、平均镜头时长、字幕密度、节拍。 |
| 音频 | BGM、音色、语速、SFX、留白点。 |
| CTA | 评论引导、私信引导、链接引导、报价引导、产品选择。 |
| 产品角度 | 价格、质量、安装、耐用、设计、舒适、地区可得性。 |
| 发布环境 | 平台、账号阶段、地区、语言、时间、标签、账号成熟度。 |

DopaMatrix 已经有 Story DSL 和 DAM 标签，所以可以在生成时存一份 `gene_snapshot`。

## 自有内容学习

每个创意都应记录：

```text
creative_id / video_id
gene_version
story_dsl
asset_ids
hook_type
emotion_tags
product_angle
cta_type
duration
shot_count
subtitle_density
voice_style
bgm_id
parent_creative_id
mutation_reason
```

发布后再绑定指标：

```text
publish_id
platform_post_id
platform
account_id
published_at
2h_metrics
24h_metrics
72h_metrics
7d_metrics
lead_metrics
sales_feedback
```

还要记录谱系：

```text
parent_creative_id
child_creative_id
kept_genes
changed_genes
generation_number
mutation_reason
```

这样才能看出某个赢家是持续变强、开始衰退，还是只在某一轮偶然有效。

## 需要看的指标

播放量不够。

应该看分层指标：

- 早期反馈：2h/24h 播放、互动速度。
- 注意力：2 秒/3 秒留存、平均观看时长、完播率、重播。
- 社交价值：评论、分享、收藏。
- 商业价值：主页访问、链接点击、私信、原始询盘、有效询盘。
- 销售价值：报价、成交、成交额。
- 风险：审核失败、删帖、负反馈、账号警告。

一条播放量低但有效询盘很多的视频，可能比纯娱乐高播放更有价值。

## 避免幸存者偏差

不要只收集爆款，也要收集同账号、同品类、同时间范围内的普通视频和失败视频。

可以使用相对指标：

```text
relative_72h_views = video_72h_views / account_recent_72h_median
relative_valid_leads = video_valid_leads / account_recent_valid_leads_median
```

这样系统才不会把“大账号优势”误判成“创意优势”。

## 公网爆款情报

公网参考当然有价值，但必须合规处理。

优先来源：

1. 官方趋势/创意中心。
2. 平台广告库。
3. 运营人员提交的公开链接。
4. 授权的数据服务。
5. 在平台条款允许范围内采集公开元数据。

对外部视频，建议保存：

```text
source_url
platform
author_handle
post_id
published_at
metric_snapshot
captured_at
category
region
language
hook_summary
visual_structure
caption_text
ocr_text
cta
gene_tags
notes
```

不应默认下载、长期保存或直接复用原视频。更稳妥的做法是保存链接、元数据、允许范围内的截图、转写/OCR 和结构化基因；如果后续真的要复用原素材，再单独确认授权。

## 分析流程

```text
1. 发现候选爆款或高转化帖子。
2. 与同账号、同品类、同时间范围的普通帖子对比。
3. 用人工或 VLM/LLM 提取基因标签。
4. 只改一到两个变量，生成 3-5 个受控变体。
5. 通过受控账号池发布。
6. 比较 24h/72h/7d 指标。
7. 将验证过的基因固化为 Story DSL 模板。
8. 冷冻或淘汰已经疲劳的基因和素材。
```

## 洞察标记

每条洞察都应带标签：

```text
OBSERVED: 观察到相关性，但未证明因果
TESTING: 仍在做受控实验
VALIDATED: 重复结果足够稳定
REJECTED: 测试未带来改进
STALE: 以前有效，现在已疲劳
```

这样就不会把个案经验太早上升成产品规则。

## MVP

第一版可以很朴素：

1. 给每个创意保存生成时的 `gene_snapshot`。
2. 把创意和发布结果绑定起来。
3. 允许运营手工标记“为什么这条好/为什么这条差”。
4. 按播放、有效询盘和转化输出 Top 内容表。
5. 保存外部参考链接和结构化笔记。
6. 给下一批内容输出实验建议。

等数据积累到一定程度后，再考虑更重的预测模型。
