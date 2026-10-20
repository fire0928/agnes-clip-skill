# Provider: 火山引擎 AI 音乐生成（豆包音乐模型）

> 核查日期：2026-10-20。文档在「音视频理解与处理」下（`volcengine.com/docs/84992`），不在方舟里——方舟只管文本/图片/视频，音乐是独立产品。
> 本文里的签名算法已按官方示例反推验证过一遍，中间值和最终签名都对得上。

## 一、它是什么、什么时候用

| 项 | 值 |
|---|---|
| 产品 | AI 音乐生成大模型（豆包音乐模型） |
| 能力 | 按一段中文描述生成纯器乐 BGM（人声歌曲是另一个入口） |
| 计费 | **0.002 元/秒**（后付费）；100 秒成片约 0.2 元 |
| 单次上限 | **纯音乐 60 秒**；人声歌曲 30–240 秒 |
| 出口 | 一个临时 URL（实测返回 **WAV**，44.1kHz 立体声，别信 `Content-Type: video/mp4`） |

用途就一句话：**本机没显卡、或者 ComfyUI 在排队时，用它顶一条配乐出来**，别为了等一首曲子把整条片子卡住。

## 二、接口

| 项 | 值 |
|---|---|
| Host | `https://open.volcengineapi.com`（POST，`Action`/`Version` 放 query） |
| Service | `imagination` |
| Region | `cn-beijing` |
| OpenAPI Version | `2024-08-12` |
| 模型 Version | `v5.0` |
| 提交（后付费） | `Action=GenBGMForTime` |
| 提交（套餐包） | `Action=GenBGM`　**两个入口不互通，走错报 200028** |
| 查询 | `Action=QuerySong`，body `{"TaskID": "..."}` |
| 鉴权 | 火山自有 V4 签名，AK/SK，HMAC-SHA256 |

### 提交请求体

```json
{"Text": "轻柔的钢琴与低音弦乐，慢速，小调，无鼓无人声", "Duration": 60, "Version": "v5.0"}
```

- `Text`：**中文描述驱动**，v5.0 已经不支持 `Genre`/`Mood`/`Instrument` 这类结构化枚举。写具体（乐器、情绪、场景、节奏）比写"温暖治愈"这种通用词通过率高。
- `Duration`：整数秒，纯音乐别超过 60。
- `EnableInputRewrite`：可选，true 时让模型改写扩写 prompt；撞版权校验时开。

### 返回

提交后只返回 `Result.TaskID`，音频要轮询：

| `Result.Status` | 含义 |
|---|---|
| 0 | 等待 |
| 1 | 处理中 |
| 2 | 成功 → `Result.SongDetail.AudioUrl` / `.Duration` |
| 3 | 失败 → `Result.FailureReason.{Code,Msg}` |

## 三、签名（最容易错的一步）

```
kDate    = HMAC(SK,        YYYYMMDD)      ← SK 直接当密钥，没有 "VOLC" 前缀
kRegion  = HMAC(kDate,     cn-beijing)
kService = HMAC(kRegion,   imagination)
kSigning = HMAC(kService,  "request")
```

- **中间密钥用二进制，不是十六进制**。官方文档那句"使用转换为十六进制字符串的哈希值"容易读反；按官方给出的中间值反推，二进制才对得上。
- `CanonicalRequest` 的 Header 按字母序：`content-type;host;x-content-sha256;x-date`，且 `CanonicalHeaders` 自身以换行结尾，与 `SignedHeaders` 之间会自然出现一个空行。
- `Host` 只参与签名，**不要**自己塞进请求头（urllib 会自己补，值一致）。
- 校验办法：拿官方文档里那个 `ListBill` 的示例跑一遍，`CanonicalRequest` 哈希应为 `27383e3b56d03850f5634483527fbddcbf06cf98de1bc8a6679ef2300bff3b15`，签名应为 `5e8480ceea12d000a23c054151c50dd02c1a7dec835004057d19f13d53a7658`。对上了就说明实现没问题。

## 四、常见错误码

| 码 | 含义 | 处理 |
|---|---|---|
| `200028` | 没有可用资源包 / 后付费没开 | 控制台打开「按时长计费」，或确认用的是 `GenBGMForTime` |
| `50000001` | 版权/相似度校验没过 | `Text` 写具体；开 `EnableInputRewrite` 重试 |
| `InvalidAccessKey` | AK 不存在 | 核对 AK |
| `SignatureDoesNotMatch` | 签名不对 | SK 填错，或本机时间偏差 > 5 分钟 |

## 五、超过 60 秒怎么办

官方单次上限 60 秒，长片必须切段。`ac.py` 的做法：

1. 按 `(总时长 + 2×(n−1)) / n ≤ 60` 解出段数 n（102.6 秒 → 2 段 × 52.3 秒）。
2. 每段在 `Text` 后面追一句"这是同一首曲子的第 k/n 段，保持相同乐器编制与调性"——不加这句，每段都像重新开头。
3. 逐段下载后 `acrossfade` 交叉淡化 2 秒拼回一条。
4. **拼接完再统一做 loudnorm**（`I=-23:TP=-2:LRA=7`），不能先归一化再拼。

代价说清楚：**分段就有"换段"感**，段与段之间能听出调性跳。能用 ComfyUI 一次出整条就别分段；分段是没卡时的权宜之计。

## 六、在 ac.py 里怎么用

```bash
# 全局切通道（配置界面「配乐」TAB 选 volc，填 AK/SK，点「测试连接」）
python scripts/ac.py config-ui

# 单次命令临时走火山，不改全局配置
python scripts/ac.py music "<dir>" --provider volc --duration 104 --caption "..."

# 之后照旧：配乐台调音量、assemble 合成
python scripts/ac.py music-ui "<dir>"
```

配置文件结构（`~/.workbuddy/agnes-clip.json`）：

```json
{
  "music": {
    "provider": "volc",
    "duration": 100,
    "caption": "...",
    "volc": {
      "ak": "AKLT...", "sk": "...",
      "action": "GenBGMForTime",
      "api_version": "2024-08-12",
      "model_version": "v5.0",
      "region": "cn-beijing",
      "service": "imagination",
      "chunk_max": 60,
      "rewrite": false
    }
  }
}
```
