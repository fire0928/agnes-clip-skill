# Provider: 火山引擎 Ark · Seedance 2.5（视频生成）

> 核查日期：2026-11-13。以火山方舟官方文档与实测提交/轮询返回为准。
> 凭据来自 `reelgen_cn_01` 项目，**24 小时有效**（当天 key，过期全档 401，换 key 即可）。

## 一、它是什么、什么时候用

| 项 | 值 |
|---|---|
| 产品 | 火山引擎 Ark · Seedance 2.5（豆包视频生成） |
| 端点 | `https://ark.cn-beijing.volces.com/api/v3` |
| 鉴权 | `Authorization: Bearer <ARK_API_KEY>`（key 形如 `ark-...`，单账号 180 RPM / 个人 3 并发，但本项目**硬约束 1 路并发**） |
| 提交 | `POST /contents/generations/tasks`，body 含 `model` / `content[]` / `duration` / `ratio` / `resolution` / `generate_audio` / `watermark` |
| 轮询 | `GET /contents/generations/tasks/{id}`，`status ∈ {queued, running, succeeded, failed}` |
| 下载 | `content.video_url`（TOS 临时签名，**24 小时有效**，最多 100 次下载，下载无需鉴权） |
| 计费 | 按 `usage.completion_tokens`（≈时长×宽×高×24fps/1024） |

**和 Agnes 通道的关键区别**（写代码前必须看清）：

| 维度 | Agnes video | Ark Seedance 2.5 |
|---|---|---|
| 模型字段 | `agnes-video-2.5`（模型名） | `ep-...`（推理接入点 id） |
| 请求体 | `prompt` + `mode` + `first_frame`/`last_frame` + `images[]` + `audios[]` | `content[]`（多模态数组，每项 `{type, text/image_url/video_url/audio_url, role}`） |
| 首帧控制 | `mode: "keyframe"` + `first_frame` 独立字段 | 在 `content[]` 里追加 `{type:"image_url", role:"first_frame"}` |
| ratio | `aspect_ratio: "9:16"` 直接写 | 🔴 **带首帧必须 `ratio: "adaptive"`**（保持图片比例），写死 9:16 会 400 |
| 时长 | 4–12s（`seconds` 字符串） | 4–30s（`duration` 整数） |
| 分辨率 | 720P / 1080P（大写） | `480p` / `720p` / `1080p`（小写），1080p 是 10-bit H.265 |
| seed | 支持 | 🔴 **2.5 明确禁了 seed**，传了直接 400 |
| 音频 | 不带 | `generate_audio: true` 默认开，出片带同步环境音 |
| 参考素材 | `images[]` 上限 5 张 | `content[]` 里可塞 30 图 + 10 视频 + 10 音频（2.5 总上限 50 项） |
| 并发 | 账号配额（3/10/50 路不等） | 🔴 **本项目 1 路**（平台硬约束） |
| 结果保留 | 24h（Agnes 默认） | 24h（Ark 默认），任务记录保留 7 天 |
| 扣费风险 | 同 Agnes | 🔴 **create 5xx/超时 = 结果未知**，可能已建任务并扣费；`_submit_one` 里必须走 `SubmitUncertain` 不重提 |

## 二、本 skill 的接法（v2.2.0）

### 档位配置（`~/.workbuddy/agnes-clip.json`）

```json
{
  "video": {
    "tiers": [
      {"name":"付费·国际版50线程","endpoint":"https://apihub.agnes-ai.com/v1","key":"sk-...","model":"agnes-video-2.5"},
      ...
      {"name":"Ark·Seedance2.5","provider":"ark","endpoint":"https://ark.cn-beijing.volces.com/api/v3",
       "key":"ark-ab58230e-...","model":"ep-20261106154430-877sp",
       "ratio":"adaptive","resolution":"720p","generate_audio":true,"watermark":false},
      {"name":"Ark·Seedance2.0","provider":"ark","endpoint":"...","key":"ark-...","model":"ep-20261106200850-bvdmq", ...},
      {"name":"Ark·Seedance-mini","provider":"ark","endpoint":"...","key":"ark-...","model":"ep-20261106201055-w2kzs", ...},
      {"name":"Ark·Seedance-fast","provider":"ark","endpoint":"...","key":"ark-...","model":"ep-20261106201004-5hls8", ...}
    ],
    "tier_slots": {"0":50,"1":3,"2":3,"7":1,"8":1,"9":1,"10":1}
  }
}
```

🔴 4 个 Ark 档全部 `tier_slots=1`（平台并发硬约束）。调度器 `_run_scheduler` 会按
`tier_slots` 强制该档只用 1 个槽位，不会撞 `InflightBatchsizeExceeded`。

### 路由判定（`_tier_is_ark`）

档里满足以下任一条件就走 Ark 分支：
- `provider` 字段 = `ark` / `volcengine` / `seedance` / `ark-seedance`（小写）
- `model` 以 `ep-` 或 `cgt-` 开头
- `endpoint` 包含 `ark.cn-beijing.volces.com` 或 `ark.ap-southeast.bytepluses.com`

其它档仍走原 Agnes 分支（`_submit_on_tier` 第一行就分流）。

### 提交与轮询（`_ark_submit` / `ark_video_status`）

- 提交：`POST {endpoint}/contents/generations/tasks`，返回 `{"id": "cgt-..."}`；
  `tier` 字段塞回返回体（`_tier = tier["_idx"]`），供调度器后续查状态路由。
- 轮询：`GET {endpoint}/contents/generations/tasks/{id}`，`status` 归一化成 Agnes 的
  `queued/running/completed/failed`；`content.video_url` 映射到 `url`，交给
  `download_file` 直接落盘（Ark 下载**不需要鉴权**）。
- 429 限流 / 5xx 队列满的退避策略沿用 Agnes 那套：`force_max_attempts=1` 时快速失败，
  调度器换下一档或进 `tier_cooldown`。
- **结果未知**（超时/连接中断）：抛 `SubmitUncertain`，写 `clips/_uncertain.json`
  停下，**绝不重提**（服务端可能已经建任务并扣费）。

### 首帧强制 adaptive

`_ark_video_payload` 里只要 `first_frame` 或 `last_frame` 非空，就无条件把 `ratio`
设成 `"adaptive"`。这样 9:16 首帧（720×1280）出来的视频就是 9:16，不会 400。

## 三、踩坑清单

1. **🔴 seed 不支持**：Seedance 2.5 的 create 接口明确拒 seed（文档：「Both included
   2.5 models disable seed; an explicit seed is rejected before create」）。
   现有 `_submit_one` 会把 `shot.seed` 透传到 payload，Ark 档必须把 seed 字段丢掉。
   （`_ark_video_payload` 已经做了：seed 参数收着但不塞进 body。）
2. **🔴 1 并发是平台硬约束**：个人账号 3 并发是账号维度，本 skill 给 Ark 档
   写 `tier_slots=1`，调度器只投 1 个。想跑 2 路就要换企业账号（10 并发）。
3. **🔴 24h key 过期**：`ark-ab58230e-...` 当天有效，过期后所有 Ark 档 401，
   去方舟控制台新建 key。key 里带了 `key_valid_until` 字段提醒。
4. **🔴 1080p 是 10-bit H.265/HEVC**：浏览器/QuickTime 可能不播，下载后别
   转码（preserve bytes），用 `ffprobe -show_streams` 确认 codec。
5. **🔴 结果 URL 24h 过期 + 最多 100 次下载**：`download_file` 一拿到就立刻
   落盘到 `clips/<sid>.mp4`，别等 `assemble` 再取。
6. **🔴 首帧 + ratio 9:16 会 400**：必须 adaptive。写死 `9:16` 只适用于
   text-only 请求（不带首帧）。
7. **🔴 扣费风险**：create 5xx/超时/连接中断 = 结果未知。`_ark_submit` 抛
   `SubmitUncertain`（同 Agnes 行为），调度器写 `_uncertain.json` 停下，
   人工去方舟后台看任务列表，确认没有再补提。

## 四、实测记录（2026-11-13 20:30）

- `GET /models` 返回 55 个模型（kimi / deepseek / glm / qwen / seedance / seedream 等），
  key 有效。
- 提交 4s 9:16 text-only 视频，0.6s 拿到 `id=cgt-20261113203046-ej2ie`；
  8 次轮询（每次 8s）后 `status=completed`，`video_url` 返回 TOS 签名 URL（有效期
  86400s）。整条链路 1 分钟内出片。
