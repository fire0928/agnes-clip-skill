# Provider: Agnes（视频 / 图片 / 文本）

> 实测日期：2026-10-18。以官方文档 `https://agnes-ai.com/en/docs/agnes-video-25-flash` 与 `agnes-image-25-flash` 为准，本文记录可直接照抄的调用方式。

## 端点

| 区域 | Base URL |
|---|---|
| 国内 | `https://apihub.agnes-ai.cn/v1` |
| 国际 | `https://apihub.agnes-ai.com/v1` |

鉴权：`Authorization: Bearer <key>`（key 形如 `cpk-...`）。

可用模型（`GET /v1/models` 实测）：

```
agnes-video-2.5-flash
agnes-image-2.5-flash
agnes-image-2.1-flash
agnes-image-2.0-flash
agnes-2.5-flash        # 文本
agnes-3.0-flash        # 文本
```

> `agnes-video-v2.0` 已于 2026-09-25 退役，必须用 2.5 系列。

---

## 一、视频：agnes-video-2.5-flash

### 创建任务

`POST /v1/videos`

```json
{
  "model": "agnes-video-2.5-flash",
  "prompt": "One continuous shot, no cuts. The woman stands by the window, rain outside, the camera slowly pushes in. 0-3s ... 3-6s ... 6-8s ...",
  "mode": "keyframe",
  "seconds": "8",
  "size": "720P",
  "aspect_ratio": "9:16",
  "first_frame": "data:image/jpeg;base64,...",
  "seed": 12345,
  "n": 1
}
```

| 参数 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `model` | ✅ | string | `agnes-video-2.5-flash` |
| `prompt` | ✅ | string | 英文描述；reference 模式用 `<Picture N>` / `<Audio N>` 指代素材 |
| `mode` | ✅ | string | `text` / `keyframe` / `reference` |
| `seconds` | | string | `"4"`–`"12"`，默认 `"5"`。**必须是字符串** |
| `size` | | string | **只能 `"720P"`**，其他值 400 |
| `aspect_ratio` | | string | 默认 `16:9`；竖屏用 `9:16` |
| `seed` | | int | 复现用 |
| `n` | | int | 只支持 `1` |
| `first_frame` | keyframe | string | 首帧图 URL 或 **base64 data URI** |
| `last_frame` | keyframe | string | 尾帧图（可选，至少给一个） |
| `images` | reference | string[] | 最多 5 张参考图 |
| `audios` | reference | string[] | 最多 3 段参考音频 |
| `videos` | reference | — | Flash **不支持**，传了 400 |

模式规则：

| mode | 用途 | 必须带 | 不能带 |
|---|---|---|---|
| `text` | 文生视频 | 无 | 所有媒体字段 |
| `keyframe` | 首帧 / 尾帧控制 | `first_frame` 或 `last_frame` | `images` / `audios` / `videos` |
| `reference` | 参考图/音频生成 | 至少一个 `images` 或 `audios` | `first_frame` / `last_frame` |

### 尺寸与比例

`size` 固定 `720P`，实际像素由 `aspect_ratio` 决定：

| aspect_ratio | 输出 |
|---|---|
| 21:9 | 1680×720 |
| 16:9 | 1280×704 |
| 4:3 | 960×720 |
| 1:1 | 720×720 |
| 3:4 | 720×960 |
| **9:16** | **720×1280** |

### 查询任务（轮询）

```
GET https://apihub.agnes-ai.cn/agnesapi?video_id=<VIDEO_ID>&model_name=agnes-video-2.5-flash
```

- 注意：轮询接口在**域名根下**，不在 `/v1` 下面。
- `model_name` 必须带，否则 keyframe / reference 任务查不到（只有 `text` 模式可以省略）。
- **本账号实测：30 秒只能查一次**（更快会 429），最多 3 路任务同时生成。官方文档写的 1–2 秒一次不适用当前账号。
- 完成时读顶层 `url` 下载 mp4；`status` 为 `completed` / `failed`。
- `internal_status` / `internal_progress` 是内部字段，看 `status` / `progress`。

完成响应示例：

```json
{
  "status": "completed",
  "progress": 100,
  "video_id": "...",
  "seconds": "8",
  "size": "720P",
  "url": "https://.../xxx.mp4"
}
```

### 错误

| HTTP | body | 原因 | 处理 |
|---|---|---|---|
| 400 | `{"detail":"size must be 720P"}` | size 写错 | 固定 `"720P"` |
| 400 | `images length must not exceed 5` | 参考图超限 | ≤5 |
| 400 | `audios length must not exceed 3` | 参考音频超限 | ≤3 |
| 400 | `videos is not supported` | Flash 不支持参考视频 | 去掉 |
| 503 | `{"code":"video_queue_full",...}` | 队列满 | **指数退避重试**（脚本内置） |
| 429 | `Too Many Requests` | 查询接口限流：**30 秒只能查一次** | 全局节流，多任务轮转查询（脚本内置） |

> 账号限制：**最多 3 路视频同时生成**，轮询 **30 秒一次**。`ac.py` 默认 `jobs=3`、`poll_interval=30`，按槽位排队、完成一个补一个。

### 计费

当前限时免费（`$0/秒`），标价 `$0.025/秒`。按输出秒数计费。

---

## 二、图片：agnes-image-2.5-flash

`POST /v1/images/generations`

```json
{
  "model": "agnes-image-2.5-flash",
  "prompt": "Character reference portrait: ...",
  "size": "2K",
  "ratio": "9:16",
  "return_base64": true
}
```

图生图（锁脸/换装）：

```json
{
  "model": "agnes-image-2.5-flash",
  "prompt": "...",
  "size": "2K",
  "ratio": "9:16",
  "extra_body": {
    "image": ["data:image/jpeg;base64,..."],
    "response_format": "b64_json"
  }
}
```

| 参数 | 说明 |
|---|---|
| `size` | 档位：`1K` / `2K` / `3K` / `4K`（推荐档位式） |
| `ratio` | `1:1` `3:4` `4:3` `16:9` `9:16` `2:3` `3:2` `21:9`，默认 `1:1` |
| `return_base64` | 文生图时置 `true`，直接拿 base64 |
| `extra_body.image` | 参考图数组（URL 或 **data URI base64**），多张即多图合成 |
| `extra_body.response_format` | `url` 或 `b64_json`；**必须放在 extra_body 里** |

输出：`data[0].b64_json` 或 `data[0].url`。9:16 的 2K = 1472×2624。
当前免费。

---

## 三、文本：agnes-2.5-flash

`POST /v1/chat/completions`，OpenAI 兼容。

```json
{
  "model": "agnes-2.5-flash",
  "messages": [{"role":"system","content":"..."},{"role":"user","content":"..."}],
  "temperature": 0.8
}
```

用于 `ac.py story` 写剧本分镜。输出要求纯 JSON，脚本会剥离 ``` 代码块并做 schema 归一化。

---

## 实测结论（2026-10-18）

| 项 | 结果 |
|---|---|
| `/v1/models` | 正常，返回 6 个模型（含视频/图片/文本） |
| 图片 2K 9:16 文生图 | 成功，约 30–60s，返回 PNG base64 |
| 图生图（base64 参考图锁脸） | 成功，人物一致性良好 |
| 视频 keyframe + data URI 首帧 | **通过格式校验**（返回 503 队列满而非参数错误），说明无需图床 |
| 视频队列 | 高峰期会 `video_queue_full`，需退避重试 |
| 视频音轨 | 2.5 flash 输出无音轨，配乐靠 assemble 后期铺 |
| 轮询 | `video_id + model_name` 组合稳定；单 `video_id` 仅 text 模式可用 |

> 如果后续服务端开始拒收 data URI（报 `400 first_frame`），配置 `agnes.frame_upload`：
> 一个 shell 命令模板，`{file}` 会被替换成本地路径，stdout 最后一行输出公网 URL。
> 例如：`scp -i ~/.ssh/key {file} ubuntu@host:/var/www/frames/ && echo https://host/frames/$(basename {file})`
