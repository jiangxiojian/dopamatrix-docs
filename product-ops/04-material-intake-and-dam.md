# 素材接收与 DAM

> 更新时间：2026-07-27  
> 状态：规划草案

## 定位

如果一开始就做客户上传门户，会马上遇到服务器、带宽、存储、OSS、权限和维护成本。早期阶段，通过 Telegram、WhatsApp 等渠道接收素材是可行的，但这些聊天工具只能作为“接收入口”，不能作为正式素材库。

真正的系统记录应该是本地入库清单 + DopaMatrix DAM。

## 主要风险

| 风险 | 为什么重要 |
| --- | --- |
| 压缩 | 聊天软件可能压缩图片和视频，导致质量下降。 |
| 元数据丢失 | 聊天消息不可靠地保存产品、权利、地区、使用限制。 |
| 客户混淆 | 运营人员可能把文件下载到错误目录。 |
| 文件过期或被撤回 | 聊天记录不能当长期存储。 |
| 授权缺口 | 音乐、肖像、商标、产品使用权可能不清楚。 |
| 安全 | 压缩包或未知文件可能带恶意内容。 |
| 只有一份 | “不上云”不等于可以只有一份副本。 |

## 入库 SOP

```text
客户发送素材 -> 运营下载到 INBOX -> 病毒/格式/MD5 检查
-> 补齐素材清单 -> 归一化处理 -> 导入 DAM
-> 审批通过/退回补充 -> 备份
```

详细步骤：

1. 客户尽量以原文件或“文件/文档”方式发送素材。
2. 客户同时提供产品/SKU、用途、目标地区、目标平台、语言、授权期限和禁用内容。
3. 运营先把文件下载到本地 `INBOX`，不要直接丢进 DAM。
4. 扫描文件、检查格式、分辨率、时长和基础质量。
5. 计算 MD5 做去重。
6. 补齐或导入入库清单。
7. 合格文件导入 DopaMatrix DAM，并写入客户/产品/类型/标签/权利信息。
8. 不合格文件放到 `REJECTED`，写明原因。
9. 原始文件只读保留，标准化或编辑后的版本作为派生资产。
10. 本地素材必须再备份到另一块磁盘或 NAS。

## 推荐目录结构

```text
material_intake/
  INBOX/
    2026-07-27/
      CLIENT-001/
        BATCH-003/
  LIBRARY/
    CLIENT-001/
      PRODUCT-TOILET-001/
        originals/
        normalized/
        approved/
  REJECTED/
  ARCHIVE/
```

这个结构能减少明显错误，但还不够。数据库或清单才是最终事实来源。

## 命名规则

系统生成的文件名：

```text
CLIENT001_TOILET001_20260727_B003_0001.mp4
```

同时保留原始文件名元数据：

```text
original_filename
stored_filename
source_channel
source_message_id
```

不要把所有含义都硬塞进文件名里。

## 最小入库清单

```csv
client_id,product_id,batch_id,original_filename,source_channel,source_message_id,received_at,operator,asset_type,rights_until,allowed_regions,allowed_platforms,status,md5,note
```

建议额外字段：

```text
language
shooting_location
model_release_status
music_rights_status
brand_usage_status
prohibited_claims
quality_score
dam_asset_id
```

## 客户发送模板

建议客户每次发素材时至少提供：

```text
客户名称：
产品/SKU：
素材用途：
目标国家/地区：
目标平台：
语言：
是否允许二创/剪辑：
版权/肖像/音乐授权期限：
不能出现的说法：
备注：
```

这个模板可以固定在聊天里重复使用。

## 运营规则

- 尽量使用公司管理的 Telegram/WhatsApp 账号，不要长期用个人账号接素材。
- 开启双重验证。
- 不接收可执行文件。
- 压缩包先扫描再解压。
- 不混用不同客户的目录。
- 素材下载后尽快入库。
- 不依赖聊天记录当备份。
- 原始文件只读保留。
- 在生产前先记录权利和限制。

## 产品建议

V1 不必先做完整客户上传门户，可以先做一个本地“素材收件箱”功能：

```text
拖入本地文件夹 -> 自动列出文件 -> MD5 去重 -> 填写批次/客户/产品
-> 检查缺失字段 -> 导入 DAM
```

这样能先把流程跑顺，同时保留未来接 OSS、企业网盘或客户门户的扩展路径。
