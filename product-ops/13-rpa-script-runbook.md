# RPA 脚本操作手册

> 更新时间：2026-11-22
> 文档类型：使用说明  
> 状态：实施中
> 相关脚本：[bitbrowser_rpa_example.py](../scripts/publishing/bitbrowser_rpa_example.py) 、[rpa_selftest.py](../scripts/publishing/rpa_selftest.py) 、[rpa_ledger_sync_selftest.py](../scripts/publishing/rpa_ledger_sync_selftest.py) 、[rpa_operator_console.py](../scripts/publishing/rpa_operator_console.py) 、[rpa_workbench_server.py](../scripts/publishing/rpa_workbench_server.py)

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

如果使用图形化 EXE，最少先准备这 4 项：

- `账号环境台账.csv`
- `矩阵投放文案对照表.csv`
- `videos/`
- `images/`

其中 `账号环境台账.csv` 现在可以先由 EXE 从 BitBrowser 同步窗口，再人工补缺字段保存回投放包根目录。

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

如果台账还没整理好，可以先在 EXE 里点“同步台账”，把窗口信息拉出来后再生成计划。

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

TK 上传入口兼容三种地址：优先 `https://www.tiktok.com/tiktokstudio/upload?from=webapp&tab=video`，未找到可用视频控件时尝试 `https://www.tiktok.com/tiktokstudio/upload?from=creator_center&tab=video`，再尝试旧 `/upload?lang=en`。普通运营无需配置，已有任务标签页和其他平台页面不被复用覆盖。2026-11-22 打包版已包含该更新。

切换只发生在视频附加前；页面出现登录、验证、访问限制、已有附加文件或多个视频输入框时停止，不盲点 Upload。视频控件明确且可用才附加素材，图片输入框被排除。上传超时不会再刷新去另一个入口，也不继续填写文案。错误 `TIKTOK_UPLOAD_ENTRY_UNAVAILABLE` 表示入口控件未找到，日志记录尝试过的地址与状态；它不同于文件上传过程中失败。此兼容逻辑已通过本地拦截页面测试，001 真实账号上的新一轮验证待补。

选择投放包后，可在“同步台账”窗口同步、补齐并保存账号资料。只有“保存到投放包”才会写入 CSV；保存后启动器自动刷新检查结果。同一个比特窗口支持分别维护 TK、FB 两行台账，窗口 ID 可以相同，平台和账号键需明确。

每条任务现在直接显示“目标账号”和“对应窗口”。账号下拉框只列出资料完整、账号键唯一的同平台记录；修改后点击“保存分配”，更新原计划表的账号键、窗口 ID 和名称。准备前必须先保存，窗口与台账不一致会阻止执行。生成计划仍沿用原有默认账号规则，没有新增按容量或排期智能分配。

草稿准备在后台执行，网页每秒查询一次阶段进度。准备中禁用重复启动和修改操作，服务器也拒绝重复请求；刷新同一个工作台页面可以继续查看。结束统计按计划表实际状态区分就绪和待处理，不把所有选中任务直接算作成功。该能力不等于 EXE 重启恢复、暂停/恢复或通知机制；这些仍未实现。账号选择只对应台账配置，实际网页账号与 FB Page 仍需人工核对。

工作台每次“准备选中草稿”前重新读取投放包根目录的 `矩阵投放文案对照表.csv`，按素材完整文件名刷新选中 READY/FAILED/PARTIAL 行的 `title`、`caption`、`hashtags`、`tracking_url`。不需要重开 EXE 或网页；这四项以文案表为准，包括清空的值。准备操作不重建计划，不改账号、客户信息或已准备/已发布任务。文案表缺失时，独立计划继续使用自身文案。

新增投放行和素材后，点击工作台的“刷新投放表”，通过 `POST /api/refresh-delivery` 将新任务合并到原计划，同时更新已有 READY/FAILED/PARTIAL 任务的四项文案。新行必须有唯一同名文件；缺文件、缺可用平台账号会持续显示具体提示，补齐后再刷新即可。格式错误、重复文件名或归属/入口不明确时不写入计划；合并采用临时文件替换，保留已有字段和历史结果。准备执行中拒绝同步。

新增规则按原计划同类素材的平台组合，每个素材/平台追加一条 READY；没有同类规则时默认视频 TK、图片 FB。按现有轮询规则从台账分配账号，继承唯一的客户、产品、操作人及 FB 入口；不自动复制 `--plan-repeat` 彩排次数或原排期。多客户/产品或多入口不能唯一确定时需拆分包。原 ID、账号、排期、状态、截图及发布链接保留，源行删除也不删历史；连续刷新不重复新增。F5 或重载页面仍只读取计划，新增需使用工作台按钮。同步本身不启动浏览器或发布。

素材没有唯一匹配行、文案表格式错误或计划任务 ID 重复时，准备前停止并显示原因；不再用“唯一一条文案”兜底其他素材。更新文案后，已经打开的浏览器草稿不会自动改动，需要处理原草稿、加入重试队列后重新准备。直接运行命令行计划仍使用计划快照；此自动同步入口是确认工作台。

CSV 统一通过结构校验读取：支持正确引用的逗号、双引号、换行和行尾多余空列；多出的非空列、重复表头、无列名内容或引号错误会显示文件路径和行号，不静默拼接或丢失内容。新建计划时启动器也会预先验证文案表和台账。

### 检查发布入口

在任务详情中点击“检查发布入口”，后台连接任务已保存的比特窗口，读取当前已打开的 TK 或 FB 页面。检查不会导航、上传、填写或点击平台控件；若窗口关闭，BitBrowser 打开它时可能恢复自己的默认/历史标签页。没有对应平台的编辑页时，先人工打开再检查。

工作台显示后台检查进度，刷新网页可以继续等待；检查期间禁用重复检查、草稿准备和修改操作，结束后恢复。结果显示“发现入口，未验证”“当前禁用”或“未发现（不代表不支持）”；同窗口多个发布页或 Page 候选提示人工核对。身份与实际自动发布均保持未核验，不能把入口存在当作排期成功或账号正确。

结果独立保存到计划目录的 `entry_checks/`（新包为 `rpa_work/entry_checks/`），不改计划状态、链接或发布日志。任务详情可查看原始检查记录；账号/窗口/内容类型/发布入口变更后不复用旧结果。连接失败会保存失败记录，并释放按钮。

开发人员可运行 `python .\scripts\publishing\rpa_entry_check.py --profile-id <指定窗口ID> --output-dir <本地诊断目录>` 只读检查；`--capture-pages` 额外保存本地发布页截图与控件线索，`--open-entries` 会在指定窗口新开空白 TK 上传页及唯一 Page 候选的 FB 编辑页，不上传或提交。普通运营使用工作台按钮即可。

### 发布预设、封面与内容确认

2026-11-22 打包版已包含本组能力。任务详情新增“发布设置与封面”，可保存人工模式、自动立即发布预设或平台定时预设，以及可见范围、商业/AI 内容声明。日期按选定的时区解释，保存后显示 UTC，过去时间和夏令时跳时/重复时段会被拦截。

这些设置当前仅为预设：不会应用到 TK/FB，也不会启动定时器。准备草稿仍只上传素材并填写文案，封面、声明、时间和最终发布需人工在平台操作；保存时间不表示已排期，报表不会因此增加发布数量。

视频任务可导入不超过 8 MB 的静态 JPG/PNG/WebP，预览后选择“本地图片”并保存；导入只复制到投放包的 `covers/`，不会发送给平台，图片帖无需另设封面。`covers/` 已从所有共用素材扫描中排除，避免误生成图文任务。指定视频帧及平台封面应用尚未实现。

保存目标账号和设置后，勾选任务并点击“确认选中内容”。弹窗显示素材、文案、标签、短链、账号、封面及预设时间，核对后填写确认人并记录；后台计算素材/封面 SHA-256，一条失败则本批不部分确认。核对期间禁止并行修改或准备，网页刷新可以恢复进度；不会打开浏览器或发帖。

设置及确认自动存到计划目录的 `publish_options.json`（新包位于 `rpa_work/`），无需人工维护新表。任务进入已有草稿/已发布状态后锁定设置，重试前先处理原页面。修改设置会使旧确认失效；计划/账号/窗口、对应文案行或文件状态变化也会显示需要重新确认。文案表更新后先刷新投放表再确认，其他新增素材不影响原确认。

列表使用文件路径、大小和修改时间快速核对；后台确认保存完整 SHA-256，未来执行器必须接入 `verify_confirmation` 的完整校验，不能只看列表状态。当前确认目的为内容审核，不代表真实账号已核验或自动提交已启用；跨 EXE 互斥、执行中断恢复和完整审核历史仍在后续计划。

### 跑本地回归

```powershell
python .\scripts\publishing\rpa_selftest.py
```

另可运行 `python .\scripts\publishing\rpa_workbench_ui_selftest.py`，使用临时台账和模拟发布器验证启动器、账号、进度、投放表、入口检查，以及封面导入/预览、时间预设、批次确认/刷新恢复/失效和移动布局。需要开发机具备 Playwright Chromium；不连接真实平台或上传素材。测试截图放在 `scripts/publishing/build/workbench-ui-check/`。新增加的图片/时区依赖已写入 `requirements.txt`。

TK 入口回归已接入以上两组自测：离线模拟尝试顺序、错误分类及上传后不切换；本地浏览器拦截所有请求，覆盖 `webapp`/`creator_center`/旧入口、延迟视频控件、图片/禁用控件排除及已有文件保护，不向真实 TK 上传。

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
- `账号环境台账.csv`：BitBrowser 窗口同步后的账号台账，保存回投放包根目录

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
