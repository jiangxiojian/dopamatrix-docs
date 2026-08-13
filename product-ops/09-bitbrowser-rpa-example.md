# 比特浏览器 RPA 示例说明

> 更新时间：2026-08-12  
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

脚本会打开 Meta Business Suite composer，尝试填文案和上传图片。当前已在 `Bright Auto Picks` Page 上验证一次：脚本可以进入 composer、通过文件选择器自动上传图片、填写文案、截图，并停在最终发布按钮前。

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

脚本只处理 `status` 为空或 `READY` 的行。相对路径会按 `publish_plan.csv` 所在目录解析；账号优先通过 `account_key` 从 `账号环境台账.csv` 查找，`browser_profile_id` 只建议临时测试时使用。

如果不带 `--print-plan`，脚本会按计划表顺序执行。建议实测时先加 `--limit 1`，并写入 JSONL 汇总日志：

```powershell
python docs/scripts/publishing/bitbrowser_rpa_example.py `
  --plan-csv "E:\project\dopaMatrix\dopamatrix_delivery_1781700321(1)\publish_plan.csv" `
  --limit 1 `
  --log-jsonl "E:\project\dopaMatrix\output\publish-rpa\publish_logs.jsonl"
```

`--log-jsonl` 是追加写入，每一行是一条任务记录。预览模式写 `PLANNED`，执行成功准备好草稿后写 `PREPARED`，失败时写 `FAILED` 和错误类型。

## 示例脚本的边界

当前脚本只适合技术验证：

- 没有读取 DopaMatrix 数据库。
- 没有生成 `publish_id`。
- 已支持写入单次 JSON 日志，但还没有接入产品数据库。
- 已支持读取 `publish_plan.csv` 的 READY 行和追加 `publish_logs.jsonl`，但还没有回写计划表状态。
- 没有处理所有平台弹窗。
- 没有自动确认 Page 是否正确。
- 没有自动点击最终发布按钮。

生产化时需要补：

```text
publish_plan 导入
account_registry 查询
发布状态机
截图和日志入库
平台弹窗识别
人工确认 UI
失败重试
post_url 回填
```

## 需要实机验证的问题

| 问题 | 结果记录 |
| --- | --- |
| `POST /health` 是否可用 | 本机已验证，返回 `success=true` |
| `/browser/open` 返回的是 `http`、`ws` 还是其他字段 | 已用真实 TK 测试窗口验证返回 `ws` |
| 返回的 CDP 地址能否被 Playwright `connect_over_cdp` 连接 | 已验证 |
| TikTok 上传页是否能稳定找到 `input[type=file]` | 已验证一次：视频上传成功 |
| TikTok caption 是否能自动填写 | 已验证一次：从 CSV 自动拼接并写入 description |
| Facebook Business Suite 是否能稳定找到文本框和文件上传控件 | 已验证一次：通过文件选择器自动上传图片，文案填充成功，停在发布前 |
| 平台是否出现登录、安全验证、商业声明或版权弹窗 | TikTok 首次上传出现内容检查和编辑功能提示弹窗；Facebook 首次进入 composer 出现浏览器通知权限弹窗，建议屏蔽；自动内容检查弹窗默认暂停，教程类弹窗会安全关闭 |

## 下一步

1. 用真实比特环境跑一遍 TikTok。
2. 补 Facebook Page 视频/Reels 和个人主页测试入口。
3. 将脚本输出的 JSON 和截图整理为批量 `publish_logs`。
4. 把硬编码页面逻辑拆成 `TikTokPublisher` 和 `FacebookPublisher`。
5. 在桌面端做“运行发布任务/等待人工确认/回填结果”的最小界面。

## 外部资料

- 比特浏览器 API 文档：[浏览器接口](https://doc.bitbrowser.net/zh/api-jie-kou-wen-dang/liu-lan-qi-jie-kou)
- TikTok 官方文档：[Content Posting API](https://developers.tiktok.com/products/content-posting-api/)
- Facebook 官方帮助：[Schedule a post and manage scheduled posts for your Facebook Page](https://www.facebook.com/help/389849807718635)
