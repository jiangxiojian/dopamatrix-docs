# 运营产品化文档索引

> 更新时间：2026-08-12  
> 来源：事项清单截图之后的讨论  
> 状态：规划草案。用于记录当前决策、边界和待验证假设，不等同于已上线功能。

## 为什么拆成这一组文档

DopaMatrix 当前已经具备内容工厂底座：本地 DAM、Story DSL、FFmpeg 渲染、质检审批和 ZIP/CSV 交付。接下来最紧急的不是继续堆生成能力，而是把内容变成可运营、可归因、可汇报、可学习的闭环：

```text
素材接收 -> 内容生产 -> 质量审批 -> 发布执行 -> 数据回收
-> 询盘归因 -> 客户报告 -> 爆款基因 -> 下一批内容策略
```

这些内容如果全部放进一个文档，会很快失控。因此按产品边界拆开维护。

## 阅读顺序

先读维护类文档，再读方案类文档。

| 文档 | 用途 |
| --- | --- |
| [00-documentation-standard.md](./00-documentation-standard.md) | 文档状态、模板、决策记录和待办维护规则。 |
| [DECISIONS.md](./DECISIONS.md) | 已形成的关键产品和运营决策。 |
| [TODO.md](./TODO.md) | 下一步待办、待确认问题和暂不做事项。 |
| [CHANGELOG.md](./CHANGELOG.md) | 文档结构性变化记录。 |

方案类文档阅读顺序：

| 顺序 | 文档 | 解决的问题 |
| --- | --- | --- |
| 1 | [01-publishing-hub.md](./01-publishing-hub.md) | 如何通过指纹浏览器和脚本补齐半自动发布能力。 |
| 2 | [02-account-strategy.md](./02-account-strategy.md) | 账号分配、共享账号、客户账号风险、账号扩容和账号健康。 |
| 3 | [03-lead-attribution-and-service.md](./03-lead-attribution-and-service.md) | 怎么向甲方证明导流来自我们，怎么处理模糊询盘和 AI 客服。 |
| 4 | [04-material-intake-and-dam.md](./04-material-intake-and-dam.md) | 不先建上传服务器时，如何通过 Telegram/WhatsApp 接收素材并干净入库。 |
| 5 | [05-client-reporting-portal.md](./05-client-reporting-portal.md) | 客户随时查看的报告网页应该展示什么。 |
| 6 | [06-viral-gene-loop.md](./06-viral-gene-loop.md) | 怎么抓取自有和公网爆款视频的基因，反哺下一批生产。 |
| 7 | [07-implementation-roadmap.md](./07-implementation-roadmap.md) | 阶段拆解、优先级和跨模块数据主线。 |
| 8 | [08-tk-fb-launch-plan.md](./08-tk-fb-launch-plan.md) | TK 视频 + FB 图文第一阶段冲刺计划、时间表和资源清单。 |
| 9 | [09-bitbrowser-rpa-example.md](./09-bitbrowser-rpa-example.md) | 比特浏览器 RPA 示例脚本说明。 |
| 10 | [10-rpa-publisher-roadmap.md](./10-rpa-publisher-roadmap.md) | RPA 发布脚本从单条验证到批量半自动工具的建设计划和优先级。 |
| 11 | [TK_FB发布试点需求物品清单.xlsx](./TK_FB发布试点需求物品清单.xlsx) | 给负责人准备账号、IP、指纹环境、素材、权限和 RPA 验证项的 Excel 清单。 |

## 事项清单覆盖关系

| 事项清单区域 | 当前文档归属 |
| --- | --- |
| 重复度算法 | 已有负责人处理。本目录只把它视为内容变体和平台风险的上游依赖。 |
| 冷启动平台、账号、IP | 见 [02-account-strategy.md](./02-account-strategy.md)。现有 TikTok 10 账号方案只作为试点背景，不当作已验证 SOP。 |
| 标红的账号调研项 | 见 [02-account-strategy.md](./02-account-strategy.md) 和 [03-lead-attribution-and-service.md](./03-lead-attribution-and-service.md)。 |
| 桌面端 1.0 发布/交付 SOP | 见 [01-publishing-hub.md](./01-publishing-hub.md) 和 [08-tk-fb-launch-plan.md](./08-tk-fb-launch-plan.md)。 |
| 客户素材提交 | 见 [04-material-intake-and-dam.md](./04-material-intake-and-dam.md)。 |
| 客户通知和运营报告 | 见 [05-client-reporting-portal.md](./05-client-reporting-portal.md)。 |
| 爆款基因抓取 | 见 [06-viral-gene-loop.md](./06-viral-gene-loop.md)。 |
| 文娱 1.5 功能拆解 | 当前尚未展开讨论，后续需求清晰后单独建文档。 |

## 讨论中的关键纠偏

1. 事项清单里的“落地页”指 DopaMatrix 产品自己的宣传获客落地页，不是给每个甲方做商品落地页。客户导流目录页属于询盘归因和客服体系的可能组件，不能混进这个任务。
2. 发布第一版应该是“脚本辅助 + 人工兜底”，不是全自动无人值守。
3. 一个账号服务多个客户时，账号必须透明定位为垂直品类号、经销商号或媒体号，不能伪装成某个甲方的官方品牌号。
4. 客户把账号交给我们运营时，最稳的是平台正式授权，不是直接共享密码。即使试点阶段先用自有账号，账号数据模型也要提前记录所有权和授权类型。
5. 发布之前必须设计询盘归因，否则视频发出去后很难再证明某条询盘来自哪个客户、产品、账号和帖子。
6. 爆款学习不能只抓爆款，还要保存普通样本和失败样本，否则会产生幸存者偏差。

## 跨模块数据主线

后续每个模块都应尽量保存这条链：

```text
client_id
product_id
asset_batch_id
video_id / creative_id
gene_version
account_id
publish_id
platform_post_id / post_url
attribution_token
lead_id
report_snapshot_id
```

只要这条链从第一天存在，发布、询盘、报告和爆款基因分析都可以逐步演进。反过来，如果现在只是把视频发出去，以后很可能只剩分散截图和不可验证的数字。

## 维护规则

后续有新讨论时：

1. 更新最小相关方案文档。
2. 如果形成了关键取舍，同步写入 [DECISIONS.md](./DECISIONS.md)。
3. 如果产生了执行事项，同步写入 [TODO.md](./TODO.md)。
4. 如果文档结构发生变化，同步写入 [CHANGELOG.md](./CHANGELOG.md)。
5. 文档格式和状态按 [00-documentation-standard.md](./00-documentation-standard.md) 执行。
