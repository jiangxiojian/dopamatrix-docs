# 比特浏览器 RPA 示例说明

> 更新时间：2026-08-14
> 文档类型：技术示例  
> 状态：草案  
> 相关脚本：[bitbrowser_rpa_example.py](../scripts/publishing/bitbrowser_rpa_example.py)

## 目的

这个示例用于验证 DopaMatrix/ClipFlow 如何通过比特浏览器实现第一版半自动发布：

```text
打开指定指纹环境 -> 连接浏览器 -> 打开平台发布页
-> 上传媒体 -> 填写文案 -> 截图 -> 人工确认发布
```

示例不会自动点击最终发布按钮。这样可以降低误发、错账号、错产品和平台弹窗带来的风险。

## 一键运行

把投放包放在项目目录中，并准备好 `账号环境台账.csv`、`矩阵投放文案对照表.csv` 和素材文件后，运营人员可以直接运行：

```powershell
python docs/scripts/publishing/bitbrowser_rpa_example.py
```

也可以双击：

```text
docs\scripts\publishing\run_publisher.cmd
```

一键模式会自动：

1. 优先找到项目中唯一包含 `READY` 任务的 `publish_plan.csv`。
2. 如果没有 READY 计划，且只有一个安全的投放包没有计划表，则先自动生成 `publish_plan.csv`。
3. 读取账号环境台账，按 `account_key` 找到比特浏览器窗口。
4. 自动打开或连接指纹环境。
5. 每条任务新开独立 Tab。
6. 自动上传媒体、填写文案、截图并写入 JSONL。
7. 把结果状态写回计划表。
8. 停在最终发布前，保留任务 Tab 给人工检查。

一键模式不会点击 TikTok 发布或 Facebook 发布按钮。已有计划表但没有 `READY` 行时，脚本不会覆盖重建；需要运营把要跑的行改回 `READY`，或者显式用 `--generate-plan --overwrite-plan` 重新生成。找到多个含 `READY` 任务的计划表，或平台需要人工验证码/人脸验证时，脚本会停止并输出原因。

## 自动生成发布计划

运营不需要手写 `publish_plan.csv`。准备好投放包后，可以先让脚本生成计划表：

```powershell
python docs/scripts/publishing/bitbrowser_rpa_example.py `
  --generate-plan `
  --delivery-dir "E:\project\dopaMatrix\dopamatrix_delivery_1781700321(1)" `
  --plan-client-id DMX `
  --plan-product-id SHOCK-ABSORBER-001 `
  --plan-operator operator
```

生成器会读取：

1. `矩阵投放文案对照表.csv`
2. `账号环境台账.csv`
3. `videos/` 里的视频文件
4. `images/` 里的图片文件

默认规则：

| 素材 | 默认生成平台 | 说明 |
| --- | --- | --- |
| 视频 | TikTok | `--plan-video-platforms tiktok` |
| 图片 | Facebook | `--plan-image-platforms facebook` |

如果交付包里只有视频，保持默认就只会生成 TikTok；如果目录里有图片但本批不想发 Facebook，可以传 `--plan-image-platforms none`。如果只想生成 Facebook 图片任务，可以传 `--plan-video-platforms none`。后续如果要测试 FB 视频/Reels，再显式改生成规则。

内部彩排可以用同一个素材重复生成多条任务，用来验证批量队列、Tab 隔离、日志和状态回写：

```powershell
--plan-repeat 3
```

重复任务会共享同一个 `media_path`，但 `publish_id` 和 `attribution_token` 会保持不同。这个参数只建议用于不发布的内部测试，不建议直接用于真实投放。

默认输出到投放包里的：

```text
publish_plan.csv
```

如果文件已存在，脚本不会覆盖，避免把已经执行、回填或人工标记过的计划表冲掉。需要覆盖时必须显式加：

```powershell
--overwrite-plan
```

更安全的测试方式是输出到临时文件：

```powershell
python docs/scripts/publishing/bitbrowser_rpa_example.py `
  --generate-plan `
  --delivery-dir "E:\project\dopaMatrix\dopamatrix_delivery_1781700321(1)" `
  --output-plan-csv "E:\project\dopaMatrix\output\publish-rpa\generated-plan-test.csv" `
  --overwrite-plan `
  --plan-client-id DMX `
  --plan-product-id SHOCK-ABSORBER-001
```

生成后先用 `--print-plan` 预览，确认账号、素材路径、caption、短链和归因 token 都正确，再运行一键发布准备。

## 前置条件

1. 本机已安装并登录比特浏览器。
2. 比特浏览器 Local API 已开启。
3. 已创建浏览器环境，并绑定代理。
4. 目标平台账号已在对应环境中登录。
5. Python 环境安装：

```bash
pip install requests playwright
python -m playwright install chromium
```

比特浏览器 Local API 默认常见地址为：

```text
http://127.0.0.1:54345
```

实际端口、鉴权和返回字段以本机客户端和官方文档为准。

## 运行 TikTok 视频示例

```powershell
python docs/scripts/publishing/bitbrowser_rpa_example.py `
  --platform tiktok `
  --profile-id "YOUR_TK_PROFILE_ID" `
  --media "E:\project\dopaMatrix\dopamatrix_delivery_1781700321(1)\videos\Tk01_CoreTag_极度渴望_32f22a.mp4" `
  --delivery-csv "E:\project\dopaMatrix\dopamatrix_delivery_1781700321(1)\矩阵投放文案对照表.csv" `
  --screenshot "E:\project\dopaMatrix\output\publish-rpa\tiktok-demo.png" `
  --content-check-action pause `
  --pause
```

脚本会：

1. 用 `POST /health` 检查比特浏览器本地服务。
2. 调用 `/browser/open` 打开指定环境。
3. 优先通过返回的 `ws` 地址连接浏览器；没有 `ws` 时再兼容 `http` / `debuggingAddress`。
4. 打开 TikTok 上传页。
5. 尝试找到文件上传控件并上传视频。
6. 如果出现 TikTok 自动内容检查弹窗，默认暂停，不替账号做开启/关闭决定。
7. 安全关闭 `Got it`、`Not now`、`Maybe later` 这类非发布弹窗。
8. 尝试填写 caption。
9. 截图。
10. 停下来让人工检查并发布。

如果给了 `--delivery-csv`，脚本会按 `media` 的文件名去匹配 CSV 里的 `视频文件名`，并自动拼接 caption。TikTok 会默认去掉 `追踪短链接`，避免把归因链接直接塞进视频描述；Facebook 则会保留或补上链接，方便归因和回收。

`--content-check-action` 可选：

| 值 | 行为 | 建议 |
| --- | --- | --- |
| `pause` | 默认值。遇到自动内容检查弹窗时停止脚本，让人工决定。 | 正式账号推荐 |
| `enable` | 点击 `Turn on`，开启自动内容检查。 | 账号初始化时可显式使用 |
| `cancel` | 点击 `Cancel`，本次不启用。 | 只适合临时测试 |

`--account-ledger` 可选 CSV 约定：

```csv
账号键,平台,窗口ID,窗口名称,内容检查处理,备注
tk_ph_001,tiktok,82b4fd0926b9469f830c6c4e2dc4e589,12-TK-PH-001-工作台,pause,测试号
```

脚本会优先用 `--profile-id`；如果没传，再尝试从台账里按 `--account-key`、平台或默认行找窗口 ID。`内容检查处理` 可以填 `pause`、`enable` 或 `cancel`。

## 运行 Facebook 图文示例

```powershell
python docs/scripts/publishing/bitbrowser_rpa_example.py `
  --platform facebook `
  --profile-id "YOUR_FB_PROFILE_ID" `
  --media "E:\project\dopaMatrix\output\fb-posts\demo.jpg" `
  --caption "这款产品适合工程采购和家装升级，欢迎留言咨询。" `
  --screenshot "E:\project\dopaMatrix\output\publish-rpa\facebook-demo.png" `
  --log-json "E:\project\dopaMatrix\output\publish-rpa\facebook-demo.json" `
  --pause
```

脚本会打开 Meta Business Suite composer，尝试填文案和上传图片。当前已在 `Bright Auto Picks` Page 上验证：脚本可以进入 composer、通过受控 file chooser 上传图片、填写文案、截图，并停在最终发布按钮前。

Facebook 上传有三种模式；普通运行不需要传这个参数，默认使用 `auto`：

| 参数 | 用途 |
| --- | --- |
| `--facebook-upload-mode auto` | 默认值。先尝试页面内 file input；失败后尝试 Playwright 能接管的 file chooser。当前 FB Page 图片帖多轮实测可成功。 |
| `--facebook-upload-mode input-only` | 只尝试页面内 `input[type=file]`，不会打开系统文件选择器；当前页面会稳定返回 `UPLOAD_NOT_CONFIRMED`。 |
| `--facebook-upload-mode file-chooser` | 只走受控 file chooser，适合排查 FB 上传按钮。 |

不要设计“裸点上传按钮后人工文件管理器弹出来再处理”的流程。Windows 原生文件选择器不属于网页 DOM，脚本接管失败时会卡住整条任务；当前脚本已移除这类裸点 fallback。

如果只想检查脚本会读取哪个账号、哪个媒体、生成什么文案，而不打开比特浏览器，可以先跑：

```powershell
python docs/scripts/publishing/bitbrowser_rpa_example.py `
  --platform facebook `
  --account-key "fb_test_sg_001" `
  --media "E:\project\dopaMatrix\output\publish-rpa\fb-upload-test-image-20260812.png" `
  --account-ledger "E:\project\dopaMatrix\dopamatrix_delivery_1781700321(1)\账号环境台账.csv" `
  --caption "DopaMatrix内部测试：仅验证Facebook Page图片上传和文案填充流程，不发布。" `
  --print-plan
```

`--log-json` 会在浏览器准备动作完成后写入结构化日志，建议每次正式测试都带上，方便回看 `uploaded`、`caption_filled`、`screenshot` 和账号窗口信息。

## 运行发布计划预览

投放包目录现在可以放一份 `publish_plan.csv`，脚本支持按计划表读取任务。先用 `--print-plan --limit 1` 做安全预览，不会打开比特浏览器：

```powershell
python docs/scripts/publishing/bitbrowser_rpa_example.py `
  --plan-csv "E:\project\dopaMatrix\dopamatrix_delivery_1781700321(1)\publish_plan.csv" `
  --limit 1 `
  --log-jsonl "E:\project\dopaMatrix\output\publish-rpa\publish_logs.preview.jsonl" `
  --print-plan
```

当前模板字段：

```csv
publish_id,client_id,product_id,platform,content_type,account_key,browser_profile_id,media_path,title,caption,hashtags,tracking_url,attribution_token,scheduled_at,status,operator,note
```

脚本只处理 `status` 为空或 `READY` 的行。相对路径会按 `publish_plan.csv` 所在目录解析，所以计划表建议放在投放包目录内；如果复制到别的目录测试，`media_path` 最好改成绝对路径。账号优先通过 `account_key` 从 `账号环境台账.csv` 查找，`browser_profile_id` 只建议临时测试时使用。

脚本默认使用 `--tab-mode new`，每条发布任务都会在同一个比特浏览器环境里新开一个 Tab，再进入对应平台页面。这个默认值很重要：如果同一个窗口同时登录 TK 和 FB，连续跑计划表时不能复用第一个已有 Tab，否则后一条 FB 任务可能把前一条 TK 草稿页 `goto` 覆盖掉。旧行为只保留给调试：

```powershell
python docs/scripts/publishing/bitbrowser_rpa_example.py `
  --plan-csv "E:\project\dopaMatrix\dopamatrix_delivery_1781700321(1)\publish_plan.csv" `
  --only-publish-id PUB-SEQUENCE-TK-001,PUB-SEQUENCE-FB-001 `
  --tab-mode new `
  --log-jsonl "E:\project\dopaMatrix\output\publish-rpa\publish_logs.jsonl"
```

只有在明确想复用第一个 Tab 做兼容性排查时，才临时传 `--tab-mode reuse-first`。

排查 Tab 行为时可加：

| 参数 | 用途 |
| --- | --- |
| `--trace-tabs` | 打印并写入脱敏后的 Tab 快照，能看到连接前、选中任务页后、上传填文案后的 Tab URL。 |
| `--stop-after-connect` | 只打开比特窗口并连接 CDP，打印 Tab 快照后退出，不进入上传或 composer。 |
| `--close-task-tab` | 运行结束后只关闭脚本新开的任务 Tab，保留指纹浏览器环境；仅用于诊断或清理测试，不用于正式人工审核草稿。 |
| `--clean-blank-tabs` | 打开并连接指定 profile，关闭 `about:blank` 空白 Tab，不执行发布任务。 |

正式运营时不要加 `--close-task-tab`，因为脚本新开的任务 Tab 就是留给人工检查和发布/放弃的草稿页。

比特浏览器环境的默认打开页可以简化。由于脚本每条任务都会新开自己的 Tab 并进入对应平台，默认页不必预置 TK 和 FB；建议最多保留一个工作台/空白页，或者关闭“恢复上次会话/默认打开多个平台页”的配置，避免窗口越开越乱。

如果不带 `--print-plan`，脚本会按计划表顺序执行。建议实测时先加 `--limit 1`，并写入 JSONL 汇总日志：

```powershell
python docs/scripts/publishing/bitbrowser_rpa_example.py `
  --plan-csv "E:\project\dopaMatrix\dopamatrix_delivery_1781700321(1)\publish_plan.csv" `
  --only-publish-id PUB-FB-TEST-001 `
  --log-jsonl "E:\project\dopaMatrix\output\publish-rpa\publish_logs.jsonl"
```

`--log-jsonl` 是追加写入，每一行是一条任务记录。预览模式写 `PLANNED`，执行成功准备好草稿后写 `PREPARED`，失败时写 `FAILED` 和错误类型。真实执行记录会包含 `duration_seconds`，用于判断上传慢、页面卡住还是账号验证拖慢任务。

当前 `error_type` 已做基础分类，常见值包括：

| 错误类型 | 含义 |
| --- | --- |
| `BITBROWSER_CONNECTION` | 比特浏览器本地 API 不通或端口不对。 |
| `BITBROWSER_PROFILE_OPEN` | 窗口打开失败，或没有返回 CDP 地址。 |
| `PROXY_CONNECTION_FAILED` | 指纹窗口代理未开启、代理不可用，或平台页面无法通过代理访问。 |
| `BROWSER_TARGET_CLOSED` | 页面、浏览器上下文或窗口在任务中途被关闭。 |
| `MEDIA_PATH_INVALID` | 素材路径为空或文件不存在。 |
| `PLAN_CONFIG_INVALID` | 发布计划或账号台账缺关键字段。 |
| `ACCOUNT_SETTING_CHECK` | 平台要求确认账号级设置，例如 TikTok 自动内容检查。 |
| `ACCOUNT_VERIFICATION` | 疑似验证码、人脸、身份或安全验证。 |
| `LOGIN_REQUIRED` | 疑似登录失效或需要重新登录。 |
| `UPLOAD_NOT_CONFIRMED` | 页面未确认素材上传成功。 |
| `CAPTION_NOT_FILLED` | 文案没有成功填入。 |
| `PLATFORM_TIMEOUT` | 平台页面或控件等待超时。 |

如果希望真实执行后同步更新计划表状态，显式加 `--write-plan-status`：

```powershell
python docs/scripts/publishing/bitbrowser_rpa_example.py `
  --plan-csv "E:\project\dopaMatrix\dopamatrix_delivery_1781700321(1)\publish_plan.csv" `
  --only-publish-id PUB-FB-TEST-001 `
  --log-jsonl "E:\project\dopaMatrix\output\publish-rpa\publish_logs.jsonl" `
  --write-plan-status
```

`--write-plan-status` 默认关闭，避免预览或误跑时改动运营表。开启后会按 `publish_id` 更新或追加这些字段：

```csv
status,last_result_status,last_result_at,result_screenshot,error_type,error_message
```

常用筛选参数：

| 参数 | 用途 |
| --- | --- |
| `--limit 1` | 只跑前 1 条 READY 任务，适合首次验证。 |
| `--only-publish-id PUB-FB-TEST-001` | 只跑指定发布任务，避免误跑其他平台。 |
| `--only-platform facebook` | 只跑某个平台的 READY 任务。 |

## 导出发布汇总

如果要给运营快速看每条任务的当前状态，可以把 `publish_logs.jsonl` 导出为 CSV：

```powershell
python docs/scripts/publishing/bitbrowser_rpa_example.py `
  --summarize-log-jsonl "E:\project\dopaMatrix\output\publish-rpa\publish_logs.jsonl" `
  --summary-csv "E:\project\dopaMatrix\output\publish-rpa\publish_summary.csv"
```

默认每个 `publish_id` 只保留最新状态，并会尽量从日志里的 `plan_csv` 反查补齐 `client_id`、`product_id`、`tracking_url`、`attribution_token`、素材路径、截图和 `duration_seconds` 等字段。如果要排查历史过程，可以加：

```powershell
python docs/scripts/publishing/bitbrowser_rpa_example.py `
  --summarize-log-jsonl "E:\project\dopaMatrix\output\publish-rpa\publish_logs.jsonl" `
  --summary-csv "E:\project\dopaMatrix\output\publish-rpa\publish_summary.history.csv" `
  --summary-include-history
```

## 生成 RPA 发布操作台

如果要把计划表、执行日志、汇总 CSV 和截图放到一个本地页面里给运营检查，可以生成静态 HTML 操作台：

```powershell
python docs/scripts/publishing/rpa_operator_console.py `
  --plan-csv "E:\project\dopaMatrix\output\publish-rpa\batch-sample-test\publish_plan.csv" `
  --log-jsonl "E:\project\dopaMatrix\output\publish-rpa\batch-sample-test\publish_logs.jsonl" `
  --summary-csv "E:\project\dopaMatrix\output\publish-rpa\batch-sample-test\publish_summary.csv" `
  --output-html "E:\project\dopaMatrix\output\publish-rpa\batch-sample-test\rpa_operator_console.html"
```

第一版操作台不需要服务器，也不改 DopaMatrix 主项目。它会展示任务状态、平台、账号、客户、产品、素材路径、截图预览、错误信息、人工备注，并为每条任务生成 `PUBLISHED_MANUAL` / `REJECTED_MANUAL` 回填命令。即使没有提前导出 `publish_summary.csv`，也会尝试直接从 `publish_logs.jsonl` 读取每个 `publish_id` 的最新记录。

## 人工发布后回填

脚本不会点最终发布按钮。人工检查并发布后，可以用回填命令把帖子链接和人工状态写回 `publish_plan.csv`，同时追加到 JSONL：

```powershell
python docs/scripts/publishing/bitbrowser_rpa_example.py `
  --plan-csv "E:\project\dopaMatrix\dopamatrix_delivery_1781700321(1)\publish_plan.csv" `
  --backfill-publish-id PUB-FB-TEST-001 `
  --backfill-status PUBLISHED_MANUAL `
  --post-url "https://www.facebook.com/..." `
  --published-at "2026-08-13T16:30:00" `
  --manual-operator "operator-name" `
  --manual-note "人工检查无误后发布" `
  --log-jsonl "E:\project\dopaMatrix\output\publish-rpa\publish_logs.jsonl"
```

当前支持的人工回填状态：

| 状态 | 用途 |
| --- | --- |
| `PUBLISHED_MANUAL` | 人工已发布，需要带 `--post-url`。 |
| `REJECTED_MANUAL` | 人工检查后决定不发布。 |
| `PREPARED` | 人工确认草稿已准备好，但暂不发布。 |
| `FAILED` | 人工确认本条任务失败。 |

## 示例脚本的边界

当前脚本只适合技术验证：

- 没有读取 DopaMatrix 数据库。
- 没有生成 `publish_id`。
- 已支持写入单次 JSON 日志，但还没有接入产品数据库。
- 已支持读取 `publish_plan.csv` 的 READY 行、追加 `publish_logs.jsonl`、显式回写计划表状态、人工回填帖子链接、导出 `publish_summary.csv`，以及生成本地 RPA 发布操作台 HTML。
- 默认每条任务新开 Tab，避免 TK/FB 同窗口顺序执行时后一条任务覆盖前一条草稿。
- 已把 TikTok / Facebook 的平台入口拆成 `TikTokPublisher` / `FacebookPublisher` 注册表，后续增加 FB Reels、快拍或其他平台时不再继续堆主流程分支。
- 没有处理所有平台弹窗。
- 没有自动确认 Page 是否正确。
- 没有自动读取发布后的 post URL。
- 没有自动点击最终发布按钮。

生产化时需要补：

```text
publish_plan 导入
account_registry 查询
发布状态机
截图和日志入库
平台弹窗识别
操作台状态直接回写
失败重试
post_url 自动识别
```

## 需要实机验证的问题

| 问题 | 结果记录 |
| --- | --- |
| `POST /health` 是否可用 | 本机已验证，返回 `success=true` |
| `/browser/open` 返回的是 `http`、`ws` 还是其他字段 | 已用真实 TK 测试窗口验证返回 `ws` |
| 返回的 CDP 地址能否被 Playwright `connect_over_cdp` 连接 | 已验证 |
| TikTok 上传页是否能稳定找到 `input[type=file]` | 已验证多轮：单条上传、`publish_plan.csv` 计划模式、以及 2026-08-14 三条重复视频批量彩排均可上传成功；脚本停在最终发布前 |
| TikTok caption 是否能自动填写 | 已验证多轮：可从交付 CSV 或计划表自动拼接并写入 description；TikTok 默认去掉追踪短链 |
| Facebook Business Suite 是否能稳定找到文本框和文件上传控件 | 已验证：`auto` 连续多轮通过受控 file chooser 上传图片、填文案、截图，停在发布前；2026-08-14 三条重复图片批量彩排均完成 `uploaded=true`、`caption_filled=true` |
| 关闭指纹窗口后由脚本重新打开是否会串 Tab | 已验证：`--stop-after-connect --trace-tabs` 看到默认/历史页面保留，脚本新开任务 Tab；日志 `E:\project\dopaMatrix\output\publish-rpa\tab-trace-cold-start.jsonl` |
| 指纹窗口已打开时再执行脚本是否会串 Tab | 已验证：脚本不会复用已有 TK/FB 页面，会继续新开任务 Tab；日志 `E:\project\dopaMatrix\output\publish-rpa\tab-trace-already-open.jsonl` |
| TK + FB 同窗口顺序执行是否会串 Tab | Tab 隔离已验证：TK 单条、FB 单条、以及 2026-08-14 3 条 TK + 3 条 FB 同窗口顺序彩排均在独立任务 Tab 完成草稿准备，未点击最终发布 |
| 冷启动 TikTok 完整草稿准备 | 已验证：视频上传和 caption 填充成功，停在发布前；截图 `E:\project\dopaMatrix\output\publish-rpa\PUB-SEQUENCE-TK-001-tiktok-20260813-182536.png` |
| 已打开窗口 Facebook 完整草稿准备 | 已验证：图片上传和 caption 填充成功，停在发布前；截图 `E:\project\dopaMatrix\output\publish-rpa\PUB-SEQUENCE-FB-001-facebook-20260813-182007.png` |
| Facebook 文件选择器弹出风险 | 已确认：系统原生文件管理器会导致脚本等待超时；已移除裸点 fallback，后续只允许页面 input 或受控 file chooser |
| Facebook `auto` 多轮稳定性 | 已验证：窗口已打开连续 3 次、`file-chooser` 直连 3 次、冷启动 1 次、完全不传上传参数 1 次均完成上传和文案填充 |
| `--plan-repeat` 重复任务彩排 | 已验证：同一个视频生成 3 条 TK、同一张图片生成 3 条 FB；代理开启后 6 条均回写 `PREPARED`，汇总 CSV 行数为 6 |
| 代理未开启时的失败记录 | 已验证：首次批量彩排因代理未开启出现 `ERR_PROXY_CONNECTION_FAILED`；后续分类器已补 `PROXY_CONNECTION_FAILED`，重试后成功 |
| 平台发布器拆分 | 已静态验证：`get_publisher('tiktok')` 返回 `TikTokPublisher`，`get_publisher('facebook')` 返回 `FacebookPublisher`；FB `--print-plan` 仍可正常解析计划表 |
| 平台异常分类细化 | 已静态验证：部分成功结果会按平台返回 `TIKTOK_UPLOAD_NOT_CONFIRMED`、`FACEBOOK_UPLOAD_NOT_CONFIRMED`、`TIKTOK_CAPTION_NOT_FILLED`、`FACEBOOK_CAPTION_NOT_FILLED` 等错误码 |
| 一键运行模式 | 已验证：直接运行脚本会自动发现 READY 计划、打开环境、使用默认 `auto` 上传、写回 `PREPARED`，停在发布前 |
| 平台是否出现登录、安全验证、商业声明或版权弹窗 | TikTok 首次上传出现内容检查和编辑功能提示弹窗；Facebook 首次进入 composer 出现浏览器通知权限弹窗，建议屏蔽；自动内容检查弹窗默认暂停，教程类弹窗会安全关闭 |

## 下一步

1. 用真实多素材再跑一轮 6-10 条彩排，验证不是同素材缓存带来的偶然稳定。
2. 补 Facebook Page 视频/Reels 和个人主页测试入口。
3. 继续细化异常分类，按 TK/FB 页面弹窗、账号验证、Page 选择错误和素材格式补规则。
4. 增强 `RPA 发布操作台 V1`：从只读 HTML 进化到能辅助状态回填、失败重试选择和账号健康备注。

## 外部资料

- 比特浏览器 API 文档：[浏览器接口](https://doc.bitbrowser.net/zh/api-jie-kou-wen-dang/liu-lan-qi-jie-kou)
- TikTok 官方文档：[Content Posting API](https://developers.tiktok.com/products/content-posting-api/)
- Facebook 官方帮助：[Schedule a post and manage scheduled posts for your Facebook Page](https://www.facebook.com/help/389849807718635)
