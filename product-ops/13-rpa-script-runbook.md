# RPA 脚本操作手册

> 更新时间：2026-08-24
> 文档类型：使用说明  
> 状态：实施中
> 相关脚本：[bitbrowser_rpa_example.py](../scripts/publishing/bitbrowser_rpa_example.py) 、[rpa_selftest.py](../scripts/publishing/rpa_selftest.py) 、[rpa_operator_console.py](../scripts/publishing/rpa_operator_console.py) 、[rpa_workbench_server.py](../scripts/publishing/rpa_workbench_server.py)

## 这套脚本做什么

它的目标不是全自动发帖，而是把“准备草稿、记录状态、回填结果、导出报告”这几步统一起来。

能做的事：

- 生成 `rpa_work/publish_plan.csv`
- 连接 BitBrowser 环境，打开 TK / FB 草稿页
- 上传媒体、填写文案、截图、记录日志
- 停在人工确认点，不点最终发布按钮
- 识别发布后的帖子 URL 和帖子 ID
- 导出汇总 CSV、操作台 HTML、客户报告页

不会做的事：

- 不会自动注册账号
- 不会绕过验证码、人脸或安全验证
- 不会自动点击最终发布
- 不会代替人工判断 Page 是否正确

## 普通运营怎么打开

现在已经有一个图形化启动入口，不必先记命令：

1. 优先双击 `scripts/publishing/dist/DopaMatrixPublisher/DopaMatrixPublisher.exe`（打包后产物）。
2. 如果还没有打包产物，双击 `scripts/publishing/run_dopamatrix_publisher.cmd`。
3. 在窗口里选择投放包文件夹，再点击“生成计划并打开操作台”。

普通运营只需要在操作台里选择任务、准备草稿、人工确认发布和回填结果。Python、CSV 字段和命令行参数属于维护人员使用范围。

纯文本版操作说明见：[15-rpa-operator-quickstart.txt](./15-rpa-operator-quickstart.txt)。

## 推荐使用顺序

1. 先准备好素材、账号台账和交付 CSV。
2. 让脚本生成 `rpa_work/publish_plan.csv`。
3. 用 `--print-plan` 先预览一条。
4. 用 `--limit 1` 跑单条草稿。
5. 确认无误后再跑批量。
6. 人工发布或拒绝后，用回填命令补帖子 URL 和状态。
7. 需要给运营看时，导出汇总或生成操作台。
8. 需要检查稳定性时，跑 `rpa_selftest.py`。

## 最小准备

运行前至少要有：

- BitBrowser 已安装并登录
- Local API 已开启
- 对应平台账号已经在环境里登录
- `账号环境台账.csv`
- `矩阵投放文案对照表.csv`
- 素材文件
- Python + Playwright

其中 Python + Playwright 只是在尚未打包的开发/维护机器上需要；交给普通运营时，应提供完整的 `DopaMatrixPublisher` 打包文件夹。

建议先安装：

```powershell
pip install requests playwright
python -m playwright install chromium
```

## 常用命令

### 生成发布计划

```powershell
python .\scripts\publishing\bitbrowser_rpa_example.py `
  --generate-plan `
  --delivery-dir "E:\project\dopaMatrix\dopamatrix_delivery_1781700321(1)" `
  --plan-client-id DMX `
  --plan-product-id SHOCK-ABSORBER-001
```

适合第一次把交付包转成 `rpa_work/publish_plan.csv`。

### 先预览，不打开浏览器

```powershell
python .\scripts\publishing\bitbrowser_rpa_example.py `
  --plan-csv "E:\project\dopaMatrix\dopamatrix_delivery_1781700321(1)\rpa_work\publish_plan.csv" `
  --print-plan `
  --limit 1
```

适合检查账号、素材路径、短链、caption 和归因 token 是否都对。

### 跑一条草稿

```powershell
python .\scripts\publishing\bitbrowser_rpa_example.py `
  --plan-csv "E:\project\dopaMatrix\dopamatrix_delivery_1781700321(1)\rpa_work\publish_plan.csv" `
  --only-publish-id PUB-FB-TEST-001 `
  --log-jsonl "E:\project\dopaMatrix\dopamatrix_delivery_1781700321(1)\rpa_work\publish_logs.jsonl" `
  --write-plan-status
```

适合第一次正式验证上传、填文案、截图和状态回写。

### 识别发布后的帖子 URL

```powershell
python .\scripts\publishing\bitbrowser_rpa_example.py `
  --plan-csv "E:\project\dopaMatrix\dopamatrix_delivery_1781700321(1)\rpa_work\publish_plan.csv" `
  --backfill-publish-id PUB-FB-TEST-001 `
  --detect-post-url
```

如果当前窗口里已经是公开帖子，可以先识别，再决定是否写回。

### 导出汇总

```powershell
python .\scripts\publishing\bitbrowser_rpa_example.py `
  --summarize-log-jsonl "E:\project\dopaMatrix\dopamatrix_delivery_1781700321(1)\rpa_work\publish_logs.jsonl" `
  --summary-csv "E:\project\dopaMatrix\dopamatrix_delivery_1781700321(1)\rpa_work\publish_summary.csv"
```

### 生成静态操作台

```powershell
python .\scripts\publishing\rpa_operator_console.py `
  --plan-csv "E:\project\dopaMatrix\dopamatrix_delivery_1781700321(1)\rpa_work\publish_plan.csv" `
  --log-jsonl "E:\project\dopaMatrix\dopamatrix_delivery_1781700321(1)\rpa_work\publish_logs.jsonl" `
  --summary-csv "E:\project\dopaMatrix\dopamatrix_delivery_1781700321(1)\rpa_work\publish_summary.csv" `
  --output-html "E:\project\dopaMatrix\dopamatrix_delivery_1781700321(1)\rpa_work\rpa_operator_console.html"
```

### 启动确认工作台

```powershell
python .\scripts\publishing\rpa_workbench_server.py `
  --plan-csv "E:\project\dopaMatrix\dopamatrix_delivery_1781700321(1)\rpa_work\publish_plan.csv" `
  --log-jsonl "E:\project\dopaMatrix\dopamatrix_delivery_1781700321(1)\rpa_work\publish_logs.jsonl" `
  --summary-csv "E:\project\dopaMatrix\dopamatrix_delivery_1781700321(1)\rpa_work\publish_summary.csv" `
  --operator "operator-name" `
  --open-browser
```

### 图形化启动入口

```powershell
python .\scripts\publishing\dopa_matrix_publisher.py
```

图形入口会选择投放包、自动生成 `rpa_work/publish_plan.csv`，并打开确认工作台。工作台中的“准备选中草稿”会调用已有发布器，默认新开任务 Tab、使用 Facebook `auto` 上传策略、写日志和回写状态，仍停在最终发布按钮前。

### 跑本地回归

```powershell
python .\scripts\publishing\rpa_selftest.py
```

## 常用参数

| 参数 | 用法 |
| --- | --- |
| `--generate-plan` | 从投放包生成 `rpa_work/publish_plan.csv`。 |
| `--print-plan` | 只预览，不打开浏览器。 |
| `--limit 1` | 只跑一条，适合先验收流程。 |
| `--only-publish-id` | 只跑指定任务。 |
| `--only-platform tiktok/facebook` | 只跑某个平台。 |
| `--write-plan-status` | 把结果写回计划表。 |
| `--detect-post-url` | 扫当前 BitBrowser 标签页，回收帖子 URL。 |
| `--detect-write-back` | 识别成功后自动写回。 |
| `--tab-mode new` | 每条任务新开 Tab，默认值。 |
| `--clean-blank-tabs` | 清理空白页，不执行发布。 |
| `--summary-include-history` | 导出完整历史，不只保留最新状态。 |

## 产出文件

这些文件默认都在投放包的 `rpa_work/` 里：

- `rpa_work/publish_plan.csv`：运营计划表
- `rpa_work/publish_logs.jsonl`：执行日志
- `rpa_work/publish_summary.csv`：运营汇总
- `rpa_work/screenshots/`：草稿截图
- `rpa_work/rpa_operator_console.html`：静态检查页
- `rpa_work/customer_report_seed.csv`：客户报告明细种子
- `rpa_work/customer_report_overview.csv`：客户报告概览种子
- `rpa_work/customer_report.html`：客户报告网页

旧测试包如果已经把这些文件放在投放包根目录，脚本仍然可以打开；新包统一按 `rpa_work/` 整理。

## 常见问题

| 问题 | 先看什么 |
| --- | --- |
| 没有 READY 任务 | 计划表状态是否还是 `READY`。 |
| 找不到账号环境 | `账号环境台账.csv` 的 `account_key` / `platform` / `profile_id` 是否对上。 |
| 找不到素材 | `media_path` 是否和投放包目录匹配。 |
| 抓不到帖子 URL | 先看 `POST_URL_NOT_FOUND`，再看候选数和扫描页签数。 |
| 上传卡住 | 是否弹了系统文件选择器或平台安全验证。 |
| FB 入口不对 | `facebook_content_mode` 和 `composer_url` 是否写对。 |

## 使用边界

1. 先把“能稳定准备草稿”当成目标，不要先追求无人值守。
2. 每次真实跑批前，最好先跑 `--print-plan`。
3. `rpa_work/publish_plan.csv` 是任务源，`rpa_work/publish_logs.jsonl` 是结果源，报告只是视图。
4. FB 视频/Reels 只有在入口 URL 已经人工确认时才建议启用。
5. 当前图形入口已完成源码级和离线自测；`exe` 需要在目标 Windows 机器上完成一次打包和实机验证后再交给普通运营。
