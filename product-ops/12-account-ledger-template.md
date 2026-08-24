# 账号环境台账模板

> 更新时间：2026-08-20  
> 文档类型：模板  
> 状态：草案

## 用途

这份模板给运营和负责人准备 `账号环境台账.csv` 用。  
现在 EXE 可以先从 BitBrowser 拉窗口，再自动生成或合并台账；人工主要补齐缺字段。  
当前发布脚本实际会读取的最小字段只有：

- `account_key`
- `platform`
- `profile_id`
- `profile_name`
- `content_check_action`
- `default`
- `notes`

其余列是建议扩展项，方便后面做账号风险、代理和归因管理。

## 现在怎么用

1. 在 EXE 里点“同步台账”。
2. 让它拉出 BitBrowser 里的窗口信息。
3. 只补缺失的账号键、平台归属、客户归属和健康备注。
4. 保存后，文件会回写到投放包根目录的 `账号环境台账.csv`。
5. 发布脚本会优先读这份文件，不需要再手工维护别的台账副本。

## 建议字段

| 字段 | 是否必填 | 含义 |
| --- | --- | --- |
| `account_key` | 是 | 脚本和计划表里引用的稳定账号键。 |
| `platform` | 是 | `tiktok` 或 `facebook`。 |
| `profile_id` | 是 | 比特浏览器环境 ID。 |
| `profile_name` | 否 | 方便人工识别的窗口名称。 |
| `content_check_action` | 否 | 内容检查弹窗处理方式，例 `pause` / `enable` / `cancel`。 |
| `default` | 否 | 是否是该平台的默认可用环境，例 `Y` / `N`。 |
| `notes` | 否 | 备注。 |
| `owner_type` | 否 | `self` / `client` / `shared`。 |
| `owner_client_id` | 否 | 如果是客户账号，填客户 ID。 |
| `authorization_type` | 否 | 授权方式，例 `direct_login` / `business_role` / `managed`。 |
| `region` | 否 | 账号归属地区。 |
| `proxy_region` | 否 | 代理地区。 |
| `proxy_provider` | 否 | 代理供应商。 |
| `daily_publish_limit` | 否 | 每日发布上限。 |
| `health_status` | 否 | `OK` / `WATCH` / `BLOCKED` / `LOGIN_REQUIRED` / `PROXY_ISSUE`。 |
| `health_note` | 否 | 账号健康说明。 |
| `last_checked_at` | 否 | 最近一次复检时间。 |

## 字段说明

- `account_key`：账号的稳定主键。发布计划、回填日志、报告都用它串同一个账号，不建议随便改。
- `platform`：平台名，只填 `tiktok` 或 `facebook`。
- `profile_id`：BitBrowser 窗口 ID，脚本用它去打开环境。
- `profile_name`：给人看的窗口名，方便在台账里快速辨认。
- `content_check_action`：遇到 TikTok 内容检查弹窗时怎么处理。
- `default`：是否作为该平台默认环境。
- `owner_type`：账号归属是自有、客户还是共享。
- `owner_client_id`：账号归属到哪个客户。
- `authorization_type`：账号是直登、业务权限还是托管。
- `health_status`：当前账号健康状态。
- `health_note`：健康状态的补充说明。

## CSV 头

```csv
account_key,platform,profile_id,profile_name,content_check_action,default,notes,owner_type,owner_client_id,authorization_type,region,proxy_region,proxy_provider,daily_publish_limit,health_status,health_note,last_checked_at
```

## 示例行

```csv
fb_test_sg_001,facebook,82b4fd0926b9469f830c6c4e2dc4e589,fb-sg-main,pause,Y,主测 FB 环境,self,,direct_login,SG,SG,bitbrowser,3,OK,已登录并可发 Page,2026-08-20T10:00:00
tk_test_sg_001,tiktok,82b4fd0926b9469f830c6c4e2dc4e589,tk-sg-main,pause,Y,主测 TK 环境,self,,direct_login,SG,SG,bitbrowser,3,OK,已登录并可发视频,2026-08-20T10:00:00
```

## 使用规则

1. `account_key` 要稳定，不要因为窗口重建就改。
2. `profile_id` 可以随环境变化，但要和 `account_key` 对上。
3. `content_check_action` 先按当前脚本支持的值填，别随意自造。
4. 如果一个账号同时服务多个客户，`owner_type` 和 `owner_client_id` 一定要显式写。
5. 台账和 `publish_plan.csv` 要能互相回查，避免只知道窗口不知道账号。

## 当前脚本匹配方式

- `--account-key` 可从台账查窗口。
- `--profile-id` 可以直接覆盖台账。
- `--clean-blank-tabs` 和 `--detect-post-url` 都会优先使用台账里的窗口信息。
