# 文档变更日志

> 更新时间：2026-11-22
> 文档类型：变更日志  
> 状态：草案

## 2026-11-22

### Packaged

- 按用户要求重新打包当前发布工具，包含 TK Studio 两种来源入口/旧入口回退、发布预设、本地封面预览和批次内容确认；最终仍需人工在平台应用设置并点击发布。
- 构建命令显式收集 `tzdata` 时区数据，随包提供图片依赖及最新版纯文本说明；产物仍统一在 `scripts/publishing/dist/DopaMatrixPublisher/`，便携压缩包使用日期命名，避免与旧包混淆。
- 不修改投放包输入和历史任务，不发布新 GitHub Release；新入口真实账号上的复核继续标为待验收。

### Verified

- `rpa_selftest.py` 全部通过；正式 EXE 启动检查 `--help` 正常退出。检查打包归档，确认包含两个 TK Studio 视频入口、入口检查和发布预设模块、Pillow 图片依赖、`tzdata` 时区数据及最新版 `README.txt`。
- `DopaMatrixPublisher-20261122.zip` 已生成并通过完整性检查，包含完整程序目录和使用说明；解压后运行 EXE，无需安装 Python。

## 2026-11-21

### Fixed

- TK 主发布器和入口诊断改用统一视频入口兼容逻辑：优先 Studio `from=webapp&tab=video`，上传前按需回退 `from=creator_center&tab=video`，旧 `/upload?lang=en` 最后兜底；普通运营无需填写地址或参数。
- 等待唯一、启用且接受视频的 file input 后才附加视频，排除图片和禁用控件；已有附加文件、登录/验证/访问限制或输入框歧义直接停止。附加视频一旦开始，失败或超时不换入口、不继续填写，防止刷新正在上传的草稿。新增入口错误码和尝试记录。

### Verified

- `rpa_selftest.py` 增加 3 组入口回归并通过；`rpa_workbench_ui_selftest.py` 在本地拦截全部请求，验证两种新入口、旧入口回退、延迟控件、视频/图片区分、已附加文件保护和登录/验证判断，原工作台及预设回归通过。
- BitBrowser Local API 当时未监听，本轮未连接 001/002，未向平台上传或发布。新入口在真实账号上的实机复核待补。按约定提交源码/文档，不重新打包 EXE。

## 2026-11-20

### Publishing Presets And Content Review

- 工作台新增发布模式、日期/时区、可见范围及商业/AI 声明预设；用 IANA 时区换算 UTC，拒绝过去时间及夏令时歧义。预设不会写成平台已排期，不启动定时器，不应用到浏览器。
- 新增本地 JPG/PNG/WebP 封面导入、格式/大小校验、预览和任务绑定；文件复制到 `covers/`，共用素材扫描排除封面，避免误生成图文任务。
- 新增批次内容预览与后台指纹确认，结果自动存入 `rpa_work/publish_options.json`；整批校验后写入，错误不部分确认。校验最新文案行、任务/账号/设置及文件状态，变更后失效；完整 SHA-256 核验函数为后续执行接入保留。历史汇总不能覆盖当前计划的待确认素材或目标信息。
- 离线回归增加封面与排除扫描、时区/DST、确认失效、同大小/时间文件强校验、整批失败和互斥；本地浏览器验证封面预览、设置保存、确认清单、后台进度/刷新恢复及移动布局，全程临时数据，无真实上传发布。
- 本轮完成后提交源码和文档，按用户要求不重新打包 EXE。实际平台封面应用、自动提交、原生定时、跨 EXE 互斥及执行恢复仍未实现。

### Added

- 工作台任务详情新增“检查发布入口”：后台连接已保存的账号窗口，读取现有同平台页面的上传、封面、定时、发布控件线索；支持进度查询、网页刷新恢复、结果持久化、任务/窗口绑定及与草稿准备互斥。多个编辑页/Page 提示核对，身份和自动发布始终未核验；不导航、上传、填写、提交或改发布记录。
- 新增 `rpa_entry_check.py` 和 4 组离线回归；开发诊断 CLI 可按指定窗口保存证据，显式选项可新开空白编辑页。连接失败有超时和失败记录，CDP 连接失败时释放 Playwright 资源。

### Entry Check Verification

- 仅在用户指定的 001 实机检查，002 未操作。确认 TK Studio 视频选择入口，未上传；FB Bright Auto Picks 的“设置日期和时间”展开后出现日期文本框和小时/分钟字段，检查后恢复关闭。未提交排期或发布；完整封面、身份核验、时区和排期回执仍待验证。
- 离线回归覆盖域名过滤、查询信息去除、禁用入口、部分读取失败、结果持久化、窗口变更不复用及后台互斥；本地浏览器回归覆盖真实 DOM 只读采集、后台检查、页面刷新恢复、结果链接、失败释放和移动布局。自动提交 A1、原生定时 A2 均未启用。

### Planned

- 新增 [16-rpa-auto-publishing-plan.md](./16-rpa-auto-publishing-plan.md)，登记受批次批准的自动立即发布、封面/发布设置、平台原生定时、结果确认、防重复、队列恢复、异常通知、投放包自动接收和本地定时备用。
- 明确 P0/P1、A0-A3 实施顺序、支持入口、内容变更使批准失效、排期/审核/发布的不同状态，以及断网和重启后先核查再重试的验收要求。
- 同步总计划、待办和目录，把原“暂不做自动发布”改为现行版本边界与后续计划的区别。本次只改文档，未启用自动提交、定时、通知或修改主产品。

### Fixed

- 原“刷新”仅重读已生成的计划，投放表新增行无法出现。改为“刷新投放表”，从根目录文案表和素材文件增量追加 READY 任务，并更新待处理任务文案；不必重启 EXE 或页面。
- 按素材路径和平台去重，保留原 ID、分配、排期、发布状态、截图、链接和额外列；缺文件/可用账号显示原因，重复文件名、错列或客户/产品/入口不明确时停止写入。原表删行不删历史，执行准备时禁止同步。
- 新素材沿用原计划同类平台规则，每个素材/平台一条；无同类规则时视频 TK、图片 FB。不自动延续彩排次数或排期；同步只合并计划，不上传或发布。

### Verified

- `rpa_selftest.py` 通过；新增 3 → 4 条任务、连续刷新去重、文案更新、历史字段保留、图片新增、缺文件补齐、重复文件/CSV 错误拦截、中文列名和 FB Reels 入口回归。
- `rpa_workbench_ui_selftest.py` 通过：页面打开后追加文件和投放行、点击刷新后新增 TK/FB 任务、再次刷新不重复、缺文件提示及移动布局；使用临时数据和模拟发布器，未真实上传或发布。

## 2026-11-19

### Fixed

- CSV 数据行多于表头时，旧读取器将额外单元格解析为列表，再调用 `.strip()` 导致崩溃。新增统一 CSV 校验，兼容多余空列，非空错列、错误引号等提示文件路径和行号；写回前先完整校验，避免丢字段。
- 确认工作台每次准备前读取最新投放文案表，按素材文件名同步选中待处理任务的标题、文案、标签和短链；支持清空旧值，保留账号、客户和其他任务记录。只需保存文案表，不必重开 EXE/网页。
- 取消“只有一行文案时复用到其他素材”的兜底，缺失/重复文件名或重复任务 ID 在准备前提示并停止。执行器使用已同步的计划内容，不重复读取原表覆盖任务；已打开草稿不会自动更新。

### Verified

- 用户提供的文案表第 3 行可复现原问题：含逗号的描述未引用，5 列变为 7 列。另生成修正版并确认 3 条记录完整、第二条描述和标签准确；原文件未修改。
- `rpa_selftest.py` 增加 CSV 回归及“工作台打开后改文案表，再准备第二条任务”的端到端参数测试；覆盖两次修改、标签清空、状态保留、错列/缺失/重复匹配拦截。使用模拟发布器，未真实上传或发布。
- `rpa_workbench_ui_selftest.py` 验证网页不重开时更新文案，账号分配、进度、刷新恢复和移动布局继续通过。

## 2026-11-17

### Changed

- 台账“保存到投放包”后自动刷新启动器检查，不再要求重选目录；未选择目录时先提示选择投放包。
- 确认工作台新增每条任务的同平台目标账号选择和窗口展示，保存到原计划 CSV；兼容中文列名。同窗口 TK/FB 可独立配置，准备前校验重复账号键、缺字段及台账窗口冲突，已有草稿/已发布任务禁止直接改账号。历史汇总不再覆盖当前计划分配。
- 草稿准备改为后台执行，网页查询真实阶段进度并持续显示当前任务和等待时间；同一工作台服务内阻止重复启动和执行中修改。刷新网页继续查看进度，结束按实际草稿就绪/待处理数量反馈。
- 同步更新运营快速说明、脚本手册、计划和待办；完整夜间批次、暂停/恢复、通知和 EXE 重启恢复继续保留在后续规划。

### Verified

- `rpa_selftest.py` 离线回归通过，新增账号分配/中文列名、共享窗口、旧汇总覆盖、重复执行拦截、失败统计和异常退出释放的检查。
- `rpa_workbench_ui_selftest.py` 通过：实际 Tk 保存台账后更新检查，Playwright 验证账号分配落盘、进度显示、网页刷新恢复和 390px 移动布局；截图存于开发构建目录。
- 以上界面测试使用临时数据和模拟发布器；本次未在 TK/FB 上传或发布真实素材，未验收长批次或跨 EXE 实例互斥。

## 2026-08-24

### Changed

- `DopaMatrixPublisher.exe` 的台账同步窗口补了 Treeview 选中回调防重入，避免同步后刷新第一行时反复触发行选中，导致窗口假死或“未响应”。
- `DopaMatrixPublisher.exe` 的台账同步进一步改为独立子进程拉取 BitBrowser 窗口，避免同步按钮把主窗口拖成“未响应”。
- `DopaMatrixPublisher.exe` 的台账同步窗口改成可滚动布局，BitBrowser 窗口同步改为后台执行，避免大窗口卡住或“未响应”。
- `DopaMatrixPublisher.exe` 新增“同步台账”入口：可从 BitBrowser 拉取窗口列表、合并到 `账号环境台账.csv`，再让人工补缺字段并保存回投放包根目录。
- 新增 `rpa_ledger_sync_selftest.py`，用于离线回归 BitBrowser 窗口解析、台账归一化、台账合并和 `/browser/list` 响应兼容。
- `DopaMatrixPublisher.exe` 启动器补充投放包检查：选择文件夹后会提示文案表、账号台账、`videos/`、`images/`、素材数量和已有 `publish_plan.csv` 是否存在。
- `DopaMatrixPublisher.exe` 如果发现已有 `rpa_work/publish_plan.csv`，会把启动器里后来填写的客户 ID、产品 ID、操作人补到计划表空字段；已有非空字段不会覆盖。
- TikTok 发布后 URL 自动识别改为保守写回：只接受 `@账号/video/ID` 或 `@账号/photo/ID` 公开链接；`player/v1/ID`、Studio `item_id/video_id` 只作为诊断候选，发现多个不同 TikTok ID 时返回 `POST_URL_CONFLICT` 并拒绝自动写回。
- 针对 TikTok 发布后跳转到 `tiktokstudio/content` 内容列表页的情况，URL 识别会优先取最上方作品行的公开链接；列表下方历史视频不再单独触发多 ID 冲突，最上方作品不是 `Public` 时会返回 `TIKTOK_STUDIO_LATEST_NOT_PUBLIC`。
- 确认工作台的“识别帖子 URL”失败提示会显示 `POST_URL_CONFLICT`、`TIKTOK_POST_URL_NOT_PUBLIC` 等具体原因和冲突 ID，方便运营手动粘贴正确公开视频链接。
- 普通运营说明和发布前准备清单明确投放包选择口径：选择 `dopamatrix_delivery_xxx` 这一层，不选择 `videos/`、`images/` 或单个素材文件。
- 素材目录规范固定为视频放 `videos/`，图片放 `images/`，文案表里的素材文件名需要能在这两个目录中找到。
- 新投放包默认把脚本产物集中到 `rpa_work/`：`publish_plan.csv`、`publish_logs.jsonl`、`publish_summary.csv`、客户报告 CSV/HTML 和账号健康记录不再散落在投放包根目录。
- 计划生成器会忽略 `rpa_work/` 里的素材类文件，并把计划表素材路径写成相对路径，例如 `../videos/demo.mp4`、`../images/demo.jpg`，方便整个投放包迁移。
- 启动器和确认工作台兼容旧测试包根目录里的 `publish_plan.csv`，但新包会优先使用 `rpa_work/publish_plan.csv`。

## 2026-08-21

### Added

- 新增 [13-rpa-script-runbook.md](./13-rpa-script-runbook.md)，把脚本的运行顺序、常用命令、输出物和常见问题整理成操作手册。
- 新增 [14-rpa-preflight-checklist.md](./14-rpa-preflight-checklist.md)，列出发布前人工要准备的账号、素材、环境和文件，并给出交付 CSV 模板。
- 新增 `scripts/publishing/dopa_matrix_publisher.py` 图形化启动入口，普通运营可以选择投放包、自动生成计划并打开本地操作台。
- RPA 确认工作台新增“选择任务并准备草稿”流程；默认使用新 Tab、Facebook `auto` 上传策略，并停在最终发布按钮前。
- 新增 `run_dopamatrix_publisher.cmd`、`build_publisher.cmd`、`requirements.txt`，用于开发机启动和 PyInstaller Windows 打包。
- 新增 [15-rpa-operator-quickstart.txt](./15-rpa-operator-quickstart.txt)，提供不依赖 Markdown 工具的普通运营快速说明。
- RPA 确认工作台做运营可用性改版：顶部路径默认收起，新增四步操作提示，任务列表上移，任务详情和回填表单默认折叠。

### Verified

- 在 Windows 10 + Python 3.10.6 + PyInstaller 6.20.0 环境成功生成 `dist/DopaMatrixPublisher/DopaMatrixPublisher.exe` 及其完整依赖目录；该打包目录未纳入 Git。
- Python 语法检查、RPA URL/报告/操作台/弹窗稳定性离线自测全部通过，其中新增“选择任务并准备草稿”参数链自测通过。
- 目标运营电脑上的首次 GUI 启动、BitBrowser CDP 连接和真实上传仍需单独验收；当前不会把这一步伪装成已完成。

## 2026-08-20

### Added

- 新增 [11-publish-data-schema.md](./11-publish-data-schema.md)，草拟 `publish_plans` / `publish_logs` 的字段、索引和状态流。
- 新增 [12-account-ledger-template.md](./12-account-ledger-template.md)，把账号环境台账的最小必填字段和扩展字段定下来。
- 新增 `scripts/publishing/rpa_operator_console_selftest.py`，用于离线检查静态操作台的处理建议筛选、回填命令和确认工作台筛选 UI。
- Facebook 发布后 URL 识别补充公开图片路径 `/photos/.../<id>`，并在页面文本/内嵌 HTML 中扫描 Facebook 公开链接和 Business Suite `content_id` 链接。
- 发布后 URL 识别结果新增 `candidate_count`、`candidate_sources`、`scanned_tab_count`、`scanner_error_count` 和 `scanner_errors` 诊断字段，便于排查 `POST_URL_NOT_FOUND`。
- `rpa_operator_console_selftest.py` 和 `rpa_stability_selftest.py` 补充了诊断字段的离线回归，覆盖摘要导出和静态页面展示。

### Verified

- `rpa_selftest.py` 现已串起 URL 识别、客户报告页、操作台/工作台和弹窗/异常分类四组离线回归。
- URL 识别自测新增 Facebook 图片路径和页面内嵌链接候选样本。
- URL 识别自测新增命中/未命中诊断字段样本。

## 2026-08-19

### Added

- 新增 `scripts/publishing/rpa_report_export.py`，可把 `publish_summary.csv` 进一步导出为客户报告种子文件：`customer_report_seed.csv` 和 `customer_report_overview.csv`。
- `rpa_workbench_server.py` 新增“导出客户报告种子”按钮和对应接口，可在确认工作台里先刷新汇总，再一键生成报告明细和总览。
- 新增 `scripts/publishing/rpa_customer_report_page.py`，可从客户报告种子 CSV 生成本地静态 HTML，展示发布概览、内容明细、帖子链接、状态分布和待补指标。
- `rpa_workbench_server.py` 新增“生成客户报告网页”按钮和接口，可一键刷新汇总、导出报告种子并生成 `customer_report.html`。
- 新增 `scripts/publishing/rpa_url_detection_selftest.py`，用于离线回归检查 TK/FB post id 解析、Business Suite `content_id` 推导和 FB 内容日历多候选排序。
- 新增 `scripts/publishing/rpa_customer_report_page_selftest.py`，用于离线检查客户报告页概览区、批量样本页和单条已发布页。
- 新增 `scripts/publishing/rpa_selftest.py`，用于一条命令串起 URL 回收、客户报告页和弹窗/异常分类三组离线回归。
- 新增 `scripts/publishing/rpa_stability_selftest.py`，用于离线检查安全弹窗、内容检查弹窗和异常分类规则。
- RPA 发布脚本新增 `error_action` 处置建议字段，按 `error_type/status` 派生 `CHECK_PROXY`、`HUMAN_ACCOUNT_CHECK`、`RETRY_TASK`、`FIX_PLAN` 等运营动作，并带入计划表、汇总 CSV、操作台、确认工作台和客户报告页。
- 弹窗库收紧 `Cancel` 处理：不再把普通 `Cancel` 当作全局安全按钮，只在已知安全弹窗上下文中尝试点击，降低误关发布编辑器的风险。
- 发布后 URL 识别未命中时新增 `POST_URL_NOT_FOUND` 事件记录，并写入 `RETRY_OR_MANUAL_CHECK` 处置建议；检测命令和确认工作台现在未命中也会追加 JSONL，便于后续复盘。
- 客户报告网页 V1 新增“待回收链接”概览指标，突出已发布但缺少公开帖子 URL 的任务。
- RPA 处置建议新增 `error_action_label` 中文说明，操作台、确认工作台和客户报告页会优先显示可读标签，同时保留稳定机器码。
- RPA 静态操作台和确认工作台新增“处理建议”筛选，方便运营集中查看需要检查代理、人工检查账号或重试的任务。
- URL 识别自测补充 TikTok photo/player 和 Facebook reels/story/photo/watch 样本，覆盖更多常见发布后链接变体。
- TikTok 发布后 URL 识别补充 Studio / Creator Center 查询参数场景：脚本现在能从 `item_id`、`video_id`、`aweme_id` 等参数提取 post id，并在缺少用户名时回退到 `player/v1/<post_id>` 可定位链接。
- 真实 TikTok Studio / Creator Center 发布后页面样本仍待补充，用于确认查询参数回收规则在实机环境下稳定生效。

### Verified

- 2026-08-19 实机发布并回收 TikTok 公开视频：`PUB-TK-TEST-001` 从 `tiktokstudio/content` 页面识别并回填 `https://www.tiktok.com/@xiojian9527/video/7675641440810093844`，随后页面状态变为 `Public`。
- 2026-08-19 实机发布并回收 Facebook Page 视频/Reels：`PUB-FB-20260814-002-63893D` 从 Business Suite 内容日历识别并回填 `https://www.facebook.com/1237975296070200/posts/122106457737435838`。
- 2026-08-19 生成单条 Facebook 图片帖计划 `PUB-FB-20260819-001-402E5C`，读取同窗口账号 `fb_test_sg_001`，新开任务 Tab 上传图片、填入文案和短链，46.84 秒完成并回写 `PREPARED`；截图当时写入历史临时输出目录，新包统一写入 `rpa_work/screenshots/`。
- 人工发布 `PUB-FB-20260819-001-402E5C` 后，脚本从 Facebook Business Suite 内容日历按最近发布时间候选回收并回填正确公开帖子：`https://www.facebook.com/1237975296070200/posts/122106554229435838`。
- URL 识别自测已通过 3 组规则：TikTok 公开视频/Studio 查询参数、Facebook 公开帖/Business Suite `content_id`、FB 内容日历最近发布时间候选排序。
- 使用目标窗口 `82b4fd0926b9469f830c6c4e2dc4e589` 跑 `--detect-post-url` 真机扫描，当前只看到 `console.bitbrowser.net`、Facebook composer 和 TikTok upload 三个页签，未识别到公开帖子 URL；脚本能干净返回 `POST_URL_NOT_FOUND`。
- 启动本地确认工作台并调用 `/api/tasks`、`/api/detect-post-url`，验证工作台能读取计划表和账号台账，也能通过接口扫描同一 BitBrowser 窗口并返回 `POST_URL_NOT_FOUND`。
- 人工点击 Facebook Page 发布后，Business Suite 跳到内容日历；脚本从 `object_insights?content_id=122106457737435838` 推导并回填公开帖子 URL：`https://www.facebook.com/1237975296070200/posts/122106457737435838`。

### Changed

- 发布后 URL 识别补充 Facebook Business Suite 内容日历场景：当页面只有 `business.facebook.com/latest/insights/object_insights/?content_id=...` 链接时，脚本会结合当前页 `asset_id` 推导 `facebook.com/<page_id>/posts/<content_id>`。
- Facebook 识别规则过滤 `business.facebook.com/latest/posts/...` 这类 Business Suite 导航 URL，避免把 `published_posts`、`ab_testing` 等栏目路径误判为平台 post id。
- Facebook Business Suite 内容日历可能同时暴露多条历史帖子候选；候选排序新增发布时间文本优先级，优先选择最接近当前检查时间且不晚于当前时间的候选，避免误回填旧帖。
- RPA 专项范围收敛为两个重点：客户报告网页 V1，以及发布后 URL 回收、异常分类、弹窗库稳定性；询盘中心、AI 客服、客户权限系统和爆款基因明确标为非本专项。

## 2026-08-18

### Added

- 新增 `scripts/publishing/rpa_workbench_server.py`，可启动本地 `127.0.0.1` 确认工作台，读取 `publish_plan.csv`、JSONL、汇总 CSV 和截图。
- 新增 `scripts/publishing/run_workbench.cmd`，支持双击后粘贴计划表路径，或把 `publish_plan.csv` 拖到脚本上启动确认工作台。
- 确认工作台支持在页面里写回 `PUBLISHED_MANUAL/REJECTED_MANUAL/FAILED/READY`，追加 JSONL，记录账号健康备注，并从 JSONL 导出 `publish_summary.csv`。
- `bitbrowser_rpa_example.py` 新增 `--detect-post-url` 基础能力，可从当前 BitBrowser 标签页识别帖子 URL 和 platform post id；手工回填也支持写入 `platform_post_id`。
- `rpa_workbench_server.py` 新增“识别帖子 URL”按钮，识别成功后可先填回 `post_url / platform_post_id / published_at`，再由运营手动点“写回状态”。

### Verified

- 使用历史批量彩排测试包启动本地确认工作台，验证 `/api/tasks` 可读取任务，`/api/export-summary` 可导出 6 行汇总 CSV。
- 使用 `--task-timeout-seconds 1 --debug-task-sleep-seconds 3` 模拟慢任务，验证批量计划模式会强杀超时子进程并继续收尾，且不会被带 emoji 文案触发的 GBK 编码问题卡住。
- 使用本地样本 URL 解析脚本，验证 TikTok `@user/video/<id>`、Facebook `posts/reel/permalink` 场景都能抽取 `platform_post_id`，并能过滤掉 `business.facebook.com/latest/composer` 这类非帖子页。

### Changed

- 批量计划模式新增单任务硬超时隔离：`--task-timeout-seconds` 大于 0 时，每条任务会进入独立子进程，超时后强杀该任务并继续下一条；一键模式默认 600 秒。
- Windows 子进程补充 UTF-8 标准流初始化，避免带 emoji 的文案在批量隔离模式下触发 `gbk` 编码错误。

## 2026-08-17

### Added

- Facebook 视频/Reels 草稿准备已完成实机验证：脚本会等待页面出现视频尺寸/时长或 Reels 编辑入口等媒体处理完成信号，再回写 `PREPARED`，全过程不点击最终发布。
- Facebook 上传按钮的 file chooser 等待做了上限收敛，避免某些按钮命中但未弹出文件选择器时长时间空等。

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
- RPA 发布操作台新增搜索、状态/平台组合筛选、复制按钮、`--log-jsonl` 回填参数和失败/部分成功重试命令，便于运营从静态页完成检查后的下一步动作。
- RPA 发布计划和运行时新增 Facebook 视频/Reels 脚本层支持：计划表新增 `facebook_content_mode`、`composer_url`，生成器新增 `--plan-facebook-video-mode`、`--plan-facebook-video-composer-url`，运行时新增 `--facebook-content-mode`、`--facebook-composer-url`。
- Facebook 上传按钮选择器补充 `Add video`、`Upload video`、`Add media`、`Create reel`、`添加视频`、`添加媒体` 等文案，为 Page 视频/Reels 入口做准备。

### Verified

- 使用真实投放包生成临时测试计划表，当前包内只有视频素材，因此生成 1 条 TikTok READY 任务。
- 对生成的计划表执行 `--print-plan --limit 1`，确认可正确解析素材路径、账号台账、caption、追踪短链和归因 token。
- 验证已有 `publish_plan.csv` 时默认拒绝覆盖，避免冲掉执行结果和人工回填状态。
- 使用临时投放包验证 `--one-click --print-plan`：没有现成计划表时可先自动生成 `publish_plan.csv`，再进入计划预览；测试任务已回填为 `REJECTED_MANUAL`，避免后续误跑。
- 验证没有 READY 且已有计划表时，一键模式会停止并提示运营把待跑行改为 `READY` 或显式重新生成计划表。
- 使用历史批量彩排计划表完成 3 条 TikTok + 3 条 Facebook 同窗口顺序彩排：代理开启后 6 条均 `uploaded=true`、`caption_filled=true`、`PREPARED`，脚本未点击最终发布。
- 首次批量彩排因代理未开启产生 6 条失败记录；开启代理后用 `--include-status FAILED,READY,PARTIAL` 成功重试，并导出汇总 CSV。
- 按“不发布”决定将 6 条批量彩排草稿统一人工回填为 `REJECTED_MANUAL`，避免误认为仍需人工发布。
- 使用批量彩排目录生成操作台 HTML，确认页面包含 6 条任务、`REJECTED_MANUAL` 状态筛选、截图 file 链接和 `PUBLISHED_MANUAL` / `REJECTED_MANUAL` 回填命令；同时验证缺少汇总 CSV 时可用 JSONL 兜底生成。
- 静态验证平台注册表和错误分类：`tiktok` 可调度到 `TikTokPublisher`，`facebook` 可调度到 `FacebookPublisher`，部分成功结果可返回平台级错误码；用 FB `--print-plan` 确认计划表解析仍正常，不打开浏览器、不发布。
- 重新生成批量彩排操作台 HTML，确认 6 条任务仍完整，页面包含搜索框、平台筛选、复制回填按钮、失败/部分成功重试命令和 JSONL 日志参数。
- 用 `--plan-video-platforms tiktok,facebook --plan-facebook-video-mode reel` 生成 FB 视频计划，确认 `publish_plan.csv` 带出 `facebook_content_mode=reel` 和 `composer_url`；用 `--print-plan` 确认运行时计划会保留这些字段，不打开浏览器、不发布。
- 生成 FB 视频/Reels 计划-only 操作台，确认静态页面展示 `内容：video`、`FB模式：reel` 和入口 URL；导出汇总 CSV 时表头保留 `facebook_content_mode`、`composer_url`。

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
- [09-bitbrowser-rpa-example.md](./09-bitbrowser-rpa-example.md)、[10-rpa-publisher-roadmap.md](./10-rpa-publisher-roadmap.md) 和 [TODO.md](./TODO.md) 已同步当前 RPA 状态：批量队列、JSONL、发布汇总 CSV、计划表状态回写、人工回填和基础异常分类均已完成；TK/FB 同窗口顺序执行、多样本彩排以及 FB 视频/Reels 草稿准备也已完成基础验证。
- 记录 2026-08-13 TK/FB 同窗口顺序彩排问题：旧脚本复用已有 Tab，导致 FB composer 覆盖 TK 草稿；脚本已改为默认 Tab 隔离，等待重新实机复测。

### Verified

- 使用临时 `publish_plan_status_test.csv` 验证 `--print-plan` 安全预览、人工 `PUBLISHED_MANUAL` 回填、失败状态回写和 JSONL 追加。
- 使用真实投放包 `publish_plan.csv` 验证 `PUB-TK-TEST-001`，脚本停在最终发布前，截图当时写入历史临时输出目录；该测试草稿不发布，已回填 `REJECTED_MANUAL`。
- 使用真实 `publish_logs.jsonl` 导出汇总 CSV，当前包含 TK/FB 两条最新任务，并补齐客户、产品、短链和归因字段。
- 使用临时 `publish_plan_error_test.csv` 和坏 API 地址验证异常分类，连接失败会写回 `BITBROWSER_CONNECTION`。
- 使用目标窗口 `82b4fd0926b9469f830c6c4e2dc4e589` 验证 Tab 隔离：关闭窗口后由脚本重新打开、窗口已打开后再次执行，均会保留原有 Tab 并新建任务 Tab。
- 使用默认 `--tab-mode new` 验证 TikTok 冷启动完整草稿准备，截图当时写入历史临时输出目录；脚本未点击发布。
- 使用默认 `--tab-mode new` 验证 Facebook 已打开窗口完整草稿准备，截图当时写入历史临时输出目录；脚本未点击发布。
- 验证 Facebook `input-only` 模式不会弹出原生文件管理器，但当前页面不暴露可直接设置的 file input，因此返回 `UPLOAD_NOT_CONFIRMED`。
- 验证 Facebook `auto` 模式通过 Playwright 受控 file chooser 上传成功，截图当时写入历史临时输出目录；脚本未点击发布。
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
