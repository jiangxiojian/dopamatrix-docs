# DopaMatrix Project Context

> 记录时间：2026-07-27
> 当前代码分支：`feature/v1.1-webhook-telegraf`
> 当前最新提交：`ca7c26f`（2026-07-27 10:10:22 +0800）

## 1. 当前结论

ClipFlow 已经从早期的“Prompt 生成短视频”演进为 DopaMatrix：一个本地优先的 AI 短视频矩阵生产与交付系统。

它的核心不是剪辑单条视频，而是把素材库、情绪标签、Story DSL、LLM 导演、FFmpeg 渲染、质检审批、交付导出串成一条生产线，用来批量制造可投放、可追踪、可审批的视频变体。

更准确地说，DopaMatrix 是一个“情绪 / 素材 / 脚本 / 图层”的矩阵裂变系统：通过标签、情绪、使用次数、素材锁定、随机抽卡和轻微防重滤镜，让同一个增长目标产出一组不同但可控的视频变体。

## 2. 当前主流程

1. 用户在 Vue + Tauri 桌面端登录，登录名通过 `X-Local-User` 传给后端。
2. 后端基于 `X-Local-User` 做本地多租户隔离，为每个用户创建独立 SQLite：`data/dopamatrix_<tenant>.db`。
3. 用户在 DAM 中导入本地素材，按 `video`、`image`、`audio_bgm`、`vfx`、`sfx`、`text_template` 等类型管理。
4. DAM 为素材维护 MD5 指纹、标签、疲劳度、实体隔离、素材名称、manifest 等信息。
5. 用户在工作台输入自然语言，可直接发起“盲裂变”，也可打开“编排战术板”手动把素材或语义标签拖入 Hook、Context、Build、CTA 等节拍。
6. 后端通过 `DirectorNode` 生成蓝图，再通过 `DSLParserNode` 执行 locked / smart 双轨寻址。
7. `dsl_adapter` 将 CompilationPlan 编译成 Timeline。
8. `FFmpegCompositorNode` 用 X 轴拼接主视频，用 Y 轴叠加贴纸、图片、文本，并通过 AudioTrack 混合 BGM、SFX、TTS。
9. `CoverNode` 抽取封面图，WebSocket 事件总线把任务进度和产物推给前端队列。
10. 成片进入历史记录和质检舱，人工执行 APPROVE / REJECT / DELETE。
11. 通过交付导出接口生成 ZIP，包含视频文件、CSV 投放文案和追踪短链。

## 3. 后端结构

### FastAPI 入口

`main.py` 是后端入口，负责：

- 创建 FastAPI 应用。
- 加载 `.env`。
- 初始化数据库表和自愈迁移。
- 注入 WebSocket 主事件循环。
- 挂载任务、DAM、DSL、历史、审批、矩阵导出、媒体预览、视频详情、Webhook 网关、设置、WebSocket 等路由。
- 在 Tauri 生产模式下提供 `/api/v1/system/shutdown` 给 sidecar 优雅退出。

### 多租户数据库

`src/api/database.py` 当前采用本地多租户 SQLite：

- 全局设置库：`dopamatrix.db`。
- 租户业务库：`data/dopamatrix_<tenant>.db`。
- 租户来源：HTTP 请求头 `X-Local-User`。
- 自动启用 SQLite WAL。
- `evolve_schema()` 只追加缺失列，不删除或重写已有结构。

### 任务与资产表

关键模型在 `src/api/models.py`：

- `VideoTask`：传统任务生命周期。
- `VideoAsset`：生成后的视频资产、文件指纹、manifest。
- `LocalAsset`：DAM 本地素材库。
- `TaskHistory`：成功任务历史归档。
- `VariantApproval`：视频变体审批状态机。
- `VariantStatusAudit`：审批状态审计记录。

## 4. 渲染核心

DopaMatrix 当前的渲染核心是 Timeline + FFmpeg Slot Filtergraph。

### Timeline

`src/core/timeline.py` 定义三层结构：

- `Clip`：单个素材片段，包含文件路径、开始时间、持续时间、特效、layout、manifest、beat_index。
- `Track`：视频或叠加图层轨道，按 z_index 排序。
- `AudioTrack`：音频轨道，用于 BGM、SFX、TTS 等混音。

### FFmpegCompositorNode

`src/nodes/compositor.py` 负责把 Timeline 编译为 FFmpeg 命令：

- 支持 `9:16`、`16:9`、`1:1` 三种 720P 级别画幅。
- X 轴主视频通过 concat 拼接。
- Y 轴 PNG / image / vfx 通过 overlay 叠加。
- `text_template` 通过 drawtext 作为虚拟文本资产渲染。
- BGM / SFX / TTS 通过 amix 混音。
- 支持 `-progress pipe:1` 实时解析进度并推送 WebSocket。
- 支持基于 beat_index 的真实时长 late-binding，使 overlay / text_overlay 与实际物理视频时长对齐。

### 防重与封面

- `AntiDupNode` 会向每个视频 Clip 注入轻微 `eq` 和 `setpts` 滤镜，制造肉眼不明显的变体差异。
- `CoverNode` 在最终视频生成后用 FFmpeg 抽帧生成封面图。

## 5. Story DSL 与导演系统

Story DSL 是当前最新分支的主心智。

### DirectorNode

`src/nodes/director_node.py` 通过 LLM 生成单轨融合蓝图：

- `meta`：社交标题、caption、hashtags、人性驱动、情绪标签等。
- `timeline`：每个 beat 含角色、寻址模式、语义标签、台词、画面描述、情绪、TTS 参数、预估时长。

当前架构已经从独立 `script_data` 转向“单轨线性”：每个 Beat 直接内聚 `script_text`，再聚合成 `tts_script` 供 TTS 使用。

### DSLParserNode

`src/api/dsl_parser.py` 负责将前端 DSL 解析为 CompilationPlan：

- locked 模式：按 `asset_hashes` 精确锁定素材。
- smart 模式：按 `semantic_tags` 查询素材，并结合标签命中、疲劳度、使用次数、随机因子排序。
- 支持硬约束标签一票否决。
- 支持“通用空镜 / B-Roll”兜底。
- 支持 X 轴主视频和 Y 轴叠加素材分拨。

### DSL 渲染入口

`src/api/routes_dsl.py` 提供：

- `POST /api/v1/tasks/draft-blueprint`
- `POST /api/v1/tasks/enhance-prompt`
- `POST /api/v1/tasks/submit-dsl`
- `POST /api/v1/tasks/submit-manual`
- `POST /api/v1/tasks/render-dsl`

其中 `submit-dsl` 支持“盲裂变”：非空 prompt + 空 timeline 时，真实蓝图生成和素材寻址推迟到后台 Worker 执行。

## 6. 前端结构

前端位于 `web_ui/`，技术栈是 Vue 3 + Pinia + Vue Router + Vite + Tauri。

主要页面：

- `/dashboard`：仪表盘。
- `/workspace`：主工作台，包含队列和底部 omnibox。
- `/assets`：DAM 本地素材库。
- `/approval`：矩阵质检舱。
- `/settings`：BYOK、输出目录、诊断日志。
- `/video/:id`：视频基因详情。

### 工作台

`WorkspaceView.vue` 是核心工作台：

- 支持自然语言输入。
- 支持 `@tag` 标签唤醒。
- 支持 AI 智能扩写。
- 支持 draft-blueprint。
- 支持盲裂变。
- 支持打开 `DslOrchestratorDrawer.vue` 进行手动编排。

### 队列

`useQueueStore.ts` + `queueWorker.ts` 形成前端事件队列：

- WebSocket 通过一次性 ticket 连接 `/ws/events`。
- 后端事件统一用 `{ type, payload }` 信封协议。
- Worker 在独立线程维护 tasks、stats、ETA。
- QueueView 页面刷新后会通过 `/api/v1/tasks/today` 做今日任务水合。

### 质检与交付

`ApprovalView.vue` 读取历史和审批状态：

- 支持 PENDING / APPROVED / REJECTED / DELETED。
- 支持批量审批。
- 支持导出 APPROVED 且未交付的视频。
- 导出后通过全局通知轮询 `/api/v1/matrix/export/status`。

## 7. Tauri 桌面端

`web_ui/src-tauri/` 是桌面端外壳：

- 生产模式启动 Python 后端 sidecar：`backend.exe`。
- 打包资源包括 `ffmpeg.exe`、`ffprobe.exe`、`.env`。
- 窗口关闭时先调用 `/api/v1/system/shutdown`，再用 Windows `taskkill` 兜底清理后端进程树。
- Tauri 配置中产品名仍是 `ClipFlow`，说明品牌迁移尚未完全完成。

## 8. Telegram 与全渠道网关

`src/api/routes_gateway.py` 和 `src/services/messaging/` 已经搭起统一 IM 网关：

- Webhook 入口：`POST /api/v1/webhook/{platform}/receive`。
- Adapter 负责把平台原始 payload 转成 `UniversalMessage`。
- Dispatcher 处理平台无关的业务响应。
- Telegram adapter 已存在。

当前它更像“全渠道消息基础设施”已经搭好，后续可继续承接 Telegram / WhatsApp / 企微等入口。

## 9. 已实现与路线图边界

### 已经真实落地

- Vue + Tauri 桌面端。
- FastAPI 本地后端。
- 多租户 SQLite。
- DAM 本地素材库。
- Story DSL 编排。
- LLM 导演蓝图。
- TTS / 字幕 / FFmpeg 渲染。
- X/Y 轴 Timeline。
- WebSocket 事件总线。
- 前端任务队列与 ETA。
- 历史记录。
- 审批状态机。
- ZIP + CSV 交付包。
- Cloudflare KV 短链适配器的 Mock / 预留真实接入。
- Telegram / Omnichannel gateway 基础设施。

### 仍主要是路线图或过渡态

- GrowthOS 云端增长中枢。
- NeuroFlow 情绪营销大模型。
- ROI 自学习闭环。
- 评论区情绪劫持和自动重写 DSL。
- Playable Ads 互动广告生成。
- 云端 PostgreSQL / pgvector。
- 多业务线拆分成独立 Content / UA 客户端。

## 10. 当前风险点与不一致

1. 品牌未完全统一：README 和 UI 已大量使用 DopaMatrix，但 Tauri 配置、FastAPI 标题仍是 ClipFlow。
2. 文档愿景明显领先代码，阅读时需要区分“已实现能力”和“路线图叙事”。
3. DAM 前端会调用 `/api/v1/assets/tags` 和 `/api/v1/assets/{id}/emotion`，但当前 `routes_assets.py` 未实现这两个端点。
4. 短链导出默认运行在 Mock 模式；只有配置 Cloudflare 环境变量后才会真实写入 KV。
5. WebSocket 压测路由仍挂在 `main.py`，代码中也标注了生产前应注释。
6. `/api/v1/tasks/submit` 旧管线和 `/api/v1/tasks/submit-dsl` 新 DSL 管线并存，产品主心智已经明显转向 DSL/Tauri/DAM/审批闭环。
7. 普通任务管线中部分 WebSocket 推送未显式传入 `user_id`，与多租户定向推送设计不完全一致，后续需要复查是否会跨用户广播。

## 11. 一句话定义

DopaMatrix 是 ClipFlow 最新分支中成型的产品方向：一个由本地桌面端驱动、以 Story DSL 和 DAM 为核心、面向短视频矩阵生产、审批和交付的 AI 内容工厂。
