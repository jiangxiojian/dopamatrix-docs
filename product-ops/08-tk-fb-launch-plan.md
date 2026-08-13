# TK + FB 发布能力冲刺计划

> 更新时间：2026-07-27  
> 文档类型：执行计划  
> 状态：草案  
> 适用阶段：客户试点前
> 相关文档：[01-publishing-hub.md](./01-publishing-hub.md), [02-account-strategy.md](./02-account-strategy.md), [07-implementation-roadmap.md](./07-implementation-roadmap.md)

## 目标

当前最小商业目标不是等完整增长闭环做完，而是尽快具备可演示、可试点的两件事：

```text
能生成 -> 能发布 -> 能拿到帖子链接/截图 -> 能开始谈客户
```

第一版只锁定两个平台和两种内容：

| 平台 | 内容形态 | 目标 |
| --- | --- | --- |
| TikTok | 竖屏短视频 | DopaMatrix 生成视频，脚本辅助上传发布。 |
| Facebook Page | 图文帖 | DopaMatrix 生成图文素材，脚本辅助发布到 Page。 |

这里的 Facebook 优先走 Page / Meta Business Suite，不把个人号主页当主生产单元。

## 客户试点前验收标准

一个产品素材包进入 DopaMatrix 后，应能完成：

1. 生成 1 条 TikTok 竖屏视频。
2. 生成 1 条 Facebook 图文帖素材。
3. 从交付目录导入标题、描述、标签、短链或归因 token。
4. 打开指定 TikTok 指纹浏览器环境。
5. 半自动上传 TikTok 视频，人工确认后发布。
6. 打开指定 Facebook 指纹浏览器环境。
7. 半自动创建 Facebook Page 图文帖，人工确认后发布或排期。
8. 保存两个平台的截图、帖子链接、发布时间、账号和状态。

不要求第一版完成：

- 自动注册账号。
- 自动养号。
- 绕过验证码。
- 全自动无人值守发布。
- 完整客户报告网页。
- 全渠道客服中心。
- 爆款模型自动学习。

这些后续都重要，但不能阻塞第一批客户沟通。

## 时间规划表

按 10 个工作日冲刺规划。前提是现有视频生成链路可用，FB 图文生成先做最小模板。

| 天数 | 目标 | 具体事项 | 产出 |
| --- | --- | --- | --- |
| Day 1 | 平台口径定稿 | 确认 TK 视频 + FB Page 图文为第一阶段；确定账号命名、客户/产品/发布字段。 | 发布字段表、账号命名规则。 |
| Day 2 | 资源准备 | 准备 2 个 TK 账号、2 个 FB Page、2-4 个代理、比特浏览器环境。 | 账号台账、代理台账、浏览器环境 ID。 |
| Day 3 | BitBrowser 连通 | 调通 `/health`、`/browser/open`，确认返回 `http/ws/driver`。 | 本地 API 验证记录。 |
| Day 4 | Playwright/CDP 接管 | 用脚本接管打开后的浏览器，完成打开页面、截图、定位上传 input。 | RPA 技术验证 Demo。 |
| Day 5 | 发布计划导入 | 读取 DopaMatrix 交付 CSV，结合账号台账，生成 `publish_plan`。 | 可导入的发布计划 JSON/CSV。 |
| Day 6 | TikTok 上传流 | 完成 TK 视频上传、填 caption、停在人工确认点。 | TK 发布脚本 MVP、截图日志。 |
| Day 7 | Facebook 图文生成 | 做最小图文模板：产品图/封面 + 标题/卖点/CTA，输出 JPG/PNG 和 caption。 | FB 图文素材输出。 |
| Day 8 | Facebook 发布流 | 完成 FB Page 图文帖上传、填文字、停在人工确认或排期点。 | FB 发布脚本 MVP、截图日志。 |
| Day 9 | 端到端彩排 | 同一产品跑完整链路：生成 TK 视频 + FB 图文，双平台发布。 | 两个平台帖子链接、发布日志。 |
| Day 10 | 客户演示包 | 整理 SOP、风险提示、演示素材、报价前说明。 | 可谈客户演示包。 |

如果中途发现 Facebook Business Suite UI 自动化不稳定，可以先退到人工打开 composer，脚本只负责上传媒体、填文案、截图记录。目标是尽快可用，不在第一周追求完美。

## 需要准备的东西

### 账号

| 资源 | 数量 | 说明 |
| --- | --- | --- |
| TikTok 账号 | 2-5 个 | 先用少量账号验证，不一次性跑 10 个。 |
| Facebook 个人号 | 2 个 | 用于管理 Page，不作为主要内容发布主体。 |
| Facebook Page | 2-5 个 | 试点优先发 Page 图文，便于客户和品牌承接。 |
| 登录邮箱/手机号 | 每账号 1 套 | 可接验证码，可恢复。 |
| 二次验证方式 | 每账号 1 套 | 记录负责人，不能无人可接。 |
| 账号台账 | 1 份 | 记录账号、地区、平台、负责人、状态、浏览器环境。 |

### 网络和浏览器

| 资源 | 数量 | 说明 |
| --- | --- | --- |
| 比特浏览器客户端 | 1 套 | 开启 Local API，本机保持登录。 |
| 指纹浏览器环境 | 每账号 1 个 | 命名如 `TK-PH-001`、`FB-PH-001`。 |
| 代理 IP | 每环境 1 条 | 目标地区一致；优先长会话，至少覆盖登录和发布过程。 |
| 代理检测记录 | 每代理 1 条 | 记录地区、速度、稳定性、是否能访问平台。 |
| 固定运营电脑 | 1 台 | 初期不要频繁换设备。 |

比特浏览器官方文档显示 Local API 默认本地地址通常是 `http://127.0.0.1:54345`，接口包括 `/health`、`/browser/update`、`/browser/open`、`/browser/close`、`/browser/list` 等；打开窗口会返回浏览器调试地址和 driver 路径。实际端口和 token 仍以本机客户端设置为准。

### 内容和素材

| 资源 | 说明 |
| --- | --- |
| 产品素材包 | 产品图、实拍视频、卖点、价格范围、禁用说法。 |
| TK 视频输出 | MP4，竖屏 9:16，优先 720x1280。 |
| FB 图文输出 | JPG/PNG，建议 1080x1080 或 1080x1350；配套 caption。 |
| 标题/描述/标签 | 从交付 CSV 或发布计划生成。 |
| 归因 token | 每条发布记录唯一。 |
| 截图目录 | 保存发布前确认截图和发布后帖子截图。 |

### 操作与合规

| 资源 | 说明 |
| --- | --- |
| 密码/验证码保管规则 | 不能写在明文表格里。 |
| 人工确认人 | 发布前检查账号、客户、产品、文案和素材是否匹配。 |
| 异常记录表 | 验证码、登录失败、上传失败、平台弹窗、审核失败。 |
| 平台规则确认 | 不绕验证、不刷互动、不发重复内容。 |
| 客户授权材料 | 客户素材版权、肖像、音乐、商标、产品描述授权。 |

## TK 和 FB 的发布路径差异

| 项目 | TikTok | Facebook Page |
| --- | --- | --- |
| 第一内容形态 | 视频 | 图文帖 |
| 首选入口 | 网页上传页或 TikTok Studio | Meta Business Suite/Page composer |
| API 路径 | Content Posting API 可选，但审核和限制较多 | Graph API 可选，但 Page 权限、App Review、token 管理较重 |
| MVP 路径 | 指纹浏览器 + 半自动上传 | 指纹浏览器 + 半自动创建 Page 帖 |
| 人工检查 | 隐私、商业内容、音乐/版权、最终发布 | Page 是否正确、图片/文案预览、是否发布或排期 |

TikTok 官方 Content Posting API 支持 Direct Post 和 Upload，但未审核应用会有私密发布、用户数量等限制；所以当前客户试点不建议等官方 API 审核后再启动。

Facebook 如果走 Graph API，需要 Page access token、`pages_manage_posts` 等权限和应用审核。为了尽快谈客户，第一版先用已登录的 Business Suite/Page 浏览器环境做半自动发布，同时保留未来 API 化的路径。

## 发布计划字段

第一版发布计划建议支持视频和图文：

```csv
publish_id,client_id,product_id,platform,content_type,account_code,browser_profile_id,media_path,title,caption,hashtags,tracking_url,attribution_token,scheduled_at,status,operator,note
PUB-001,CLIENT-001,TOILET-001,tiktok,video,TK-PH-001,bit_tk_001,videos/a.mp4,标题,描述,#tag,https://dopa.mx/t/a,DM-TK-001,,READY,,
PUB-002,CLIENT-001,TOILET-001,facebook,image_text,FB-PH-001,bit_fb_001,images/a.jpg,标题,正文,#tag,https://dopa.mx/t/b,DM-FB-001,,READY,,
```

## 风险提示

- 能发布不等于能长期稳定发布，第一批客户应按“试点代运营/内测发布能力”沟通。
- 不承诺绕过平台风控。
- 不承诺每条内容都公开视频成功。
- 不把客户账号密码作为默认交付条件。
- 不把未经授权的素材发布到客户或自有账号。

## 外部资料

- 比特浏览器 API 文档：[浏览器接口](https://doc.bitbrowser.net/zh/api-jie-kou-wen-dang/liu-lan-qi-jie-kou)
- TikTok 官方文档：[Content Posting API](https://developers.tiktok.com/products/content-posting-api/)
- TikTok 官方文档：[Content Sharing Guidelines](https://developers.tiktok.com/doc/content-sharing-guidelines/)
- Facebook 官方帮助：[Schedule a post and manage scheduled posts for your Facebook Page](https://www.facebook.com/help/389849807718635)
- Facebook 官方帮助：[See insights for your Facebook Page posts](https://www.facebook.com/help/131809553587433)
