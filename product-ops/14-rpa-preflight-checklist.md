# RPA 发布前准备清单与模板

> 更新时间：2026-08-24  
> 文档类型：准备清单  
> 状态：草案

## 你需要先准备什么

这份清单是给“开跑前的人”看的。  
如果这些东西没准备好，脚本就只能等，或者直接停下来。

## 手工准备清单

| 项目 | 必要 | 说明 | 模板 / 参考 |
| --- | --- | --- | --- |
| BitBrowser 已安装 | 是 | 本机要能打开指定环境。 | 见 [09-bitbrowser-rpa-example.md](./09-bitbrowser-rpa-example.md) |
| Local API 已开启 | 是 | `POST /health` 和 `/browser/open` 要通。 | 同上 |
| 平台账号已登录 | 是 | TK / FB Page 账号先登录好。 | [12-account-ledger-template.md](./12-account-ledger-template.md) |
| 代理已配置 | 是 | 环境要绑定可用代理。 | 账号台账里记录代理地区和供应商 |
| `账号环境台账.csv` | 是 | 记录账号键、窗口 ID 和默认处理方式。 | [12-account-ledger-template.md](./12-account-ledger-template.md) |
| `矩阵投放文案对照表.csv` | 是 | 一次投放的文案、标签和追踪短链对照表。 | 本文模板 |
| 素材目录 | 是 | 视频放 `videos/`，图片放 `images/`；两个目录和文案表、台账放在同一个投放包下。 | 见下方目录结构 |
| `rpa_work/publish_plan.csv` | 否 | 可以手工准备，也可以让脚本自动生成；默认放在 `rpa_work/`，不要和输入文件混在根目录。 | [11-publish-data-schema.md](./11-publish-data-schema.md) |
| Facebook 入口 URL | 视情况 | FB 视频/Reels/快拍建议手工确认入口再填。 | [09-bitbrowser-rpa-example.md](./09-bitbrowser-rpa-example.md) |
| `rpa_work/` | 自动 | 用来放计划表、日志、汇总、客户报告和账号健康记录。 | 启动器会自动创建 |
| 操作人名称 | 建议 | 写入工作台、日志和回填记录。 | `--operator` / `--manual-operator` |
| 测试说明 | 建议 | 哪条任务是测试、哪条是正式跑批。 | `note` / `manual_note` |

## 推荐目录结构

```text
delivery-package/
  videos/
    demo_video_001.mp4
  images/
    demo_image_001.jpg
  矩阵投放文案对照表.csv
  账号环境台账.csv
  rpa_work/
    publish_plan.csv
    publish_logs.jsonl
    publish_summary.csv
    customer_report_seed.csv
    customer_report_overview.csv
    customer_report.html
    rpa_account_health.csv
```

启动器选择文件夹时，要选 `delivery-package` / `dopamatrix_delivery_xxx` 这一层。
不要选 `videos/`、`images/`，也不要选单个素材文件。

真实投放包例子：

```text
E:\project\dopaMatrix\dopamatrix_delivery_1781700321(1)
```

图片素材放 `images/`，视频素材放 `videos/`。
脚本会递归扫描投放包里的素材，但运营交接时按这两个固定目录整理，后续查找、复盘和补素材最清楚。

根目录只放人工输入和素材目录；脚本产物统一进 `rpa_work/`。
旧测试包如果已经把 `publish_plan.csv`、`publish_logs.jsonl`、报告 CSV/HTML 放在根目录，脚本仍然能兼容打开，但新包按 `rpa_work/` 整理。

## 客户 ID 和产品 ID 怎么填

`客户 ID` 和 `产品 ID` 是 DopaMatrix 自己的运营归因字段，不是 TikTok / Facebook 的账号 ID。

设计它们的初衷是：

1. 发布后能按客户筛选报告。
2. 同一个客户有多个产品或活动时，能分开统计。
3. 一条帖子、一个素材、一条询盘能回查到客户和产品。
4. 后面做客户报告、归因、复盘和爆款基因分析时，不靠人工猜。

来源可以是：

| 字段 | 推荐来源 | 示例 |
| --- | --- | --- |
| `客户 ID` | 客户台账、合同编号、CRM 编号、内部项目编号 | `CUST-ACME-001`、`HT202608-003` |
| `产品 ID` | 产品台账、SKU、活动编号、投放项目编号 | `PROD-TOILET-A01`、`CAMPAIGN-SG-0824` |

脚本目前不会校验它们的格式，所以填 `1234` 也能运行。  
但正式使用不建议随手填，因为后续报告和回查会很难看懂。建议从第一天就用稳定、有含义、不会重复的编号。

## `矩阵投放文案对照表.csv` 模板

这是脚本生成 caption 时最重要的人工输入之一。

### CSV 头

```csv
视频文件名,社交平台标题,情绪化描述,黄金标签,追踪短链接
```

### 说明

| 字段 | 说明 |
| --- | --- |
| `视频文件名` | 素材文件名。脚本用它去匹配 `media`。图片也可以放在这里，只要文件名能对上。 |
| `社交平台标题` | 计划里的标题。 |
| `情绪化描述` | 主要文案。 |
| `黄金标签` | 标签或 hashtags。 |
| `追踪短链接` | 用于归因和回收。 |

### 示例行

```csv
视频文件名,社交平台标题,情绪化描述,黄金标签,追踪短链接
Tk01_CoreTag_极度渴望_32f22a.mp4,极度渴望核心款,本条仅用于内部测试，请勿公开发布,#DopaMatrix #Test,https://trk.example/tk-001
Fb01_CoreTag_极度渴望_9ac11d.jpg,极度渴望图文测试,本条仅用于内部测试，请勿公开发布,#DopaMatrix #Test,https://trk.example/fb-001
```

## `rpa_work/publish_plan.csv` 模板

如果你不想手工拼计划表，可以直接看这份结构草案：

- [11-publish-data-schema.md](./11-publish-data-schema.md)

如果你想先看脚本实际会怎么读，优先看：

- [09-bitbrowser-rpa-example.md](./09-bitbrowser-rpa-example.md)

## `账号环境台账.csv` 模板

账号台账的字段已经单独整理成模板：

- [12-account-ledger-template.md](./12-account-ledger-template.md)

## 发布前检查

跑正式任务前，最好再核一次：

1. `account_key` 和 `profile_id` 是否对上。
2. `media_path` 是否真能找到文件。
3. `tracking_url` 是否要保留。
4. Facebook 视频/Reels 的入口 URL 是否已人工确认。
5. `rpa_work/publish_plan.csv` 里的 `status` 是否是 `READY`。
6. `rpa_work/` 是否有写权限。
7. 这一批是否只准备做草稿，不点最终发布。

## 哪些东西可以晚点补

- 账号健康备注
- `publish_summary.csv`
- 客户报告页
- 人工回填后的 `manual_note`

这些可以在第一轮草稿跑完后再补，但不要把最基础的台账和交付 CSV 省掉。
