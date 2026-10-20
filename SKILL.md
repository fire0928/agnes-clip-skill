---
name: agnes-clip
description: 用 Agnes 云端算力全自动做竖屏短剧/长视频——一句话创意 → 编剧（场景/动作/微表情/对白/口型）→ 分镜表 → 角色定妆图 → 道具图 → 场景板 → 逐镜首帧 → 批量提交 agnes-video-2.5-flash 出视频 → 质检 → 配乐/音效/转场/逐句字幕 → 拼成一条完整成片。含 15 阶段完整作业流程（references/full_pipeline.md）与多集共享角色库（同一系列第 2、3 集复用同一张脸，不重新生成）。当用户要用 Agnes 生成视频、要"从剧本到成片全自动"、要写有对白会说话的短剧、要锁住人物脸做多镜头连续剧/系列剧、要批量提交视频任务、问"这个 skill 怎么用/怎么配置/怎么启动/装完怎么跑"、要打开配置界面配出图或视频的端点和 Key、要给项目切换出图通道（Agnes / GPT Image / 自定义 OpenAI 兼容）时使用。模型：agnes-video-2.5-flash（视频）+ agnes-image-2.5-flash（图片）+ agnes-2.5-flash（编剧）。配乐两条通道可选：本地 ComfyUI（MiniMax Music3）或火山引擎 AI 音乐生成（豆包音乐模型，无显卡也能跑，0.002 元/秒）。
agent_created: true
version: 1.1.0
---

# Agnes Clip · 一句话到成片（平哥分享版）

## 装完怎么跑（用户第一次用，先看这段）

**别一上来就 `auto`。** 正确顺序是三步：

### 第 1 步：确认凭据已配好

先检查 `~/.workbuddy/agnes-clip.json` 是否存在且有 `agnes.key`。
没有就**先跑配置**（这一步是阻塞项，没配好后面全白跑）：

```bash
python ~/.workbuddy/skills/agnes-clip-平哥分享版/scripts/ac.py setup
```

或直接开图形化配置界面（推荐给不熟命令行的用户）：

```bash
python ~/.workbuddy/skills/agnes-clip-平哥分享版/scripts/ac.py config-ui
```

配置界面是**本机网页**（默认 `http://127.0.0.1:8765/`），7 个 TAB：总览 / 生图 / 推理编剧 / 生视频 / 配音 / 配乐 / 系统。
每个 TAB 管一条通道的端点、模型、Key。**终端窗口不能关，关了页面就断。**

### 第 2 步：告诉用户有快捷指令

本 skill 自带 `commands/` 目录，包含：

| 命令 | 干什么 |
|---|---|
| `/配置` | 打开配置界面 |
| `/出图通道` | 给单个项目选出一条图通道（Agnes / GPT Image / 自定义 OpenAI 兼容） |
| `/片子状态` | 看项目进度到哪一步 |
| `/做一条片子` | 从一句话创意一路做到成片 |
| `/配乐台` | 试听配乐、逐镜调音量 |
| `/装快捷指令` | 把这些命令复制到 WorkBuddy 命令目录（复制后需重启 WorkBuddy） |

**首次对话时主动告诉用户可以先跑 `/装快捷指令`**，之后输入 `/` 就能直接用。
如果用户没装 commands 目录，也可以在对话里直接说「打开 Agnes Clip 配置界面」，然后跑 `config-ui`。

### 第 3 步：开工

用户给创意 → 问清 3 件事（时长 / 人物 / 结尾感觉）→ 选好出图通道 → 按下面的 15 阶段走。

**每个项目开工前先定出图通道**（`pick-image`），这样同一个 skill 能同时跑不同通道的项目：

```bash
python scripts/ac.py pick-image <项目目录> --channel agnes      # 或 gpt-image / openai
```

不写通道名 = 清除项目级设置、跟随全局。

**Python 版本必须是 3.13**（3.14.3 环境已损坏，会报错）。

---

## 这个 skill 解决什么

把「一句话创意」变成一条**有场景、有对白、会说话**的竖屏短剧，全程不用手工切流程：

**编剧（场景/动作/微表情/对白/口型）→ 分镜表 → 角色定妆图 → 道具图 → 场景板（场景×机位）→ 逐镜首帧 → 批量出视频（3 路并发）→ 质检 → 配乐 → 音效 → 转场 → 逐句字幕 → 合成 → 验收 → 成片**

所有中间产物按固定目录归档，可以单步重跑、只重做某一镜、在任意一步停下来验收。视频走 Agnes 云端，不占本地显卡。

🔴 **一条完整视频不是 `auto` 一条命令就完事**。
`auto` 只到「首帧 + 视频 + 合成」，出的是毛片；转场、音效、逐句字幕、配乐选曲属于精修段，
必须按 `references/full_pipeline.md` 的 15 个阶段走完才算交付。**每一步都有验收门，上一关不过不进下一关。**

## 何时使用

- 要用 **Agnes** 生成视频（不是本地 ComfyUI / MiniMax-H3）
- 要从剧本一路自动做到成片（`auto` 一条命令）
- 要写有对白的短剧，人物要真的开口说话、对口型
- 要做多镜头片子且人物前后必须长得一样
- 要批量提交多个镜头任务再统一收片
- 已有真人照片，想让它演一段（`char-add` 导入锁脸）
- 要做**系列剧**：同一个项目下第 2 集、第 3 集沿用第 1 集的人物形象（`episode-new` / `cast`）

## 全流程总表（做一整条片子按这个顺序走）

| # | 阶段 | 命令 | 产物 | 验收门（不过不许进下一步） |
|---|---|---|---|---|
| 0 | 立项 | `init` | `project.json` | `status` 不报错；需要多集共用角色就先定 `cast_dir` |
| 1 | 剧本骨架 | `story`（建议手改） | `script/story.md` | logline 四要素 + 情绪曲线有高低点 + 母题首尾回环 + 删一镜测试 |
| 2 | 镜头表 | 手写 `shots.json` | 全片字段表 | 每镜有具体动作、有 `scene.set`、双人镜有 `cast`、总时长落在目标区间 |
| 3 | 角色 | `char-gen` / `char-add` / `cast` | `assets/characters/<name>/` | 亲眼看过 `face_ref.jpg`，脸和年龄贴人设 |
| 4 | 道具 | `prop-gen` | `assets/props/*.jpg` | 只建近景会被看清的；母题道具必须在 |
| 5 | 场景板 | `scene-gen` | `assets/scenes/<场景>__<机位>.jpg` | 逐张看：是这个地点、没有多余道具、同场景各机位墙与家具一致 |
| 6 | 首帧 | `frame`（先 `--dry-run`） | `frames/S*.jpg` | 人数锁 N 对、参考图张数对、双人镜有 left/right；抽 3–5 张关键镜看 |
| 7 | 视频 | `video --wait` | `clips/S*.mp4` | 段数 = 镜数；失败镜 `--only` 单跑 |
| 8 | 质检 | 抽帧 + 抽音轨转写 | `qa/` | 无多余人/道具、无跳轴、无漂移；每句台词真的念出来且没念糊 |
| 9 | 配乐 | `music` → `music-ui` | `audio/bgm.mp3` | 先 loudnorm 归一化；时长 ≥ 成片；逐镜音量写进 `shot.bgm`；火山通道 >60s 会自动分段 |
| 10 | 音效 | 真素材 → `audio/sfx/` | 13 个左右音效 | 落点卡转折处；峰值 ≈ −16dB，对白段只抬 1–2dB |
| 11 | 转场 | 写 `shot.x` | 合成时生效 | 换场景叠化 0.8–1.2s、正反打硬切 0.1s；合成后核对总时长没被截断 |
| 12 | 字幕 | 写 `shot.subs`（推荐）或 `--subs` | `out/_subs_shots.ass` | 每句只有一排（≤14 字）、出现在对应台词处 |
| 13 | 合成 | `assemble --subs --voice` | `out/final.mp4` | 关掉不该有的 tighten；S12 类旁白不能双重人声 |
| 14 | 验收 | `audit` + 响度 + 缩略图墙 | `AUDIT.md` | 时长/画幅/响度达标，全片扫一遍无穿帮 |
| 15 | 交付 | 复制成 `out/<片名>.mp4` | 成片 + 剧本 + 审计 | 清掉 `_p_*`、`qa/`、`_test_*` 等临时文件 |

逐步的命令、字段、踩坑与验证方法写在 **`references/full_pipeline.md`**，那是主作业手册；本文件给规则与硬约束。

**人工介入只有五处**：剧本定稿、场景板验收、首帧验收、质检、精修（配乐/音效/转场/字幕）。其余都可以批量跑。

## 一集接一集：人物形象复用（同一系列不换脸）

第 2 集**不要重新 `char-gen`**，重生成就是换演员。用共享角色库：

```bash
# 一条命令：在系列目录下新建 ep02，自动把 ep01 的角色收进 cast/ 并绑定
python scripts/ac.py episode-new "<第1集目录>" --name ep02 --title "第二集"

# 或者手动
python scripts/ac.py cast "<dir>" init                  # 项目内建 cast/，写 project.json 的 cast_dir
python scripts/ac.py cast "<dir>" push --name girl      # 收录（--all 收全部）
python scripts/ac.py cast "<dir>" list                  # 看哪些角色是本集、哪些来自共享库
```

```
系列/
├── cast/          # girl / chenyu 的 face_ref、source、turnaround（一套脸）
├── ep01/
└── ep02/          # project.json → "cast_dir": "../cast"
```

- 读取规则：**本集优先，其次共享库**。`ep02` 的 `assets/characters/` 是空的也能直接用 `girl`、`chenyu`。
- 写入规则：`char-gen` / `char-add` 只写本集，不污染共享库；进库要显式 `cast push`。
- 换装/换年龄（第 2 集过了五年）要新建角色名（`girl_5y`），不要覆盖 `girl`。
- 道具、场景板目前不跨集共享（各集独立），只有人物脸是长期资产。

## 编剧能力（这是本 skill 的核心）



`story` 命令产出一份**能拍的剧本**，不是解说词。每一镜都包含：

| 字段 | 内容 | 例子 |
|---|---|---|
| `scene` | 场景四要素：时间 / 地点 / 天气 / 光源 | 深夜 / 面馆内 / 无雨 / 暖黄吊灯 |
| `action` | 这一镜唯一的主要动作 | 老板娘把一碗面放在女孩对面 |
| `micro` | 微表情**过程**（肌肉与眼神的顺序） | 嘴角先提了一下，笑意才慢慢漫到眼底 |
| `speaker` | 谁在说（角色名，或 `VO` 旁白） | boss |
| `line` | 真正说出口的台词，≤18 字 | 还是不要葱对吧？ |
| `frame.prompt` | 英文首帧提示词（场景/服装/光线/构图） | … |
| `video_prompt` | 英文视频提示词，含**台词原句 + 口型同步指令** + 微表情 + 2–3 段运镜 + 环境声 | … |

编剧规则：

1. **至少一半镜头有台词**，第一镜就有人开口，最后一镜用一句台词收尾。
2. 有台词的镜头用 **waist-up medium shot / medium close-up**，嘴部必须可见；不要远景说话。
3. 口型指令固定写法：`The character speaks in Mandarin Chinese with precise lip-sync: "…" — mouth shapes each syllable clearly, jaw and lips move naturally.`
4. 台词前后各留 0.5 秒不说话，口型才有呼吸感。
5. 微表情只在腰以上景别写，一镜最多 2 个。
6. 台词口语化、有潜台词，不要念说明书。

产出两份文件：
- `script/story.md`：人读剧本（角色、道具、分镜表、逐镜正文）
- `script/shots.json`：机器读镜头表（驱动后面所有步骤）

## 模型与端点

| 用途 | 模型 | 接口 |
|---|---|---|
| 视频（免费额度） | `agnes-video-2.5-flash` | `POST /v1/videos` 创建 → `GET /agnesapi?video_id=…&model_name=…` 轮询 |
| 视频（付费/有余额） | `agnes-video-2.5` | 同上，接口完全一致，只换 model 名 |
| 图片 | `agnes-image-2.5-flash` | `POST /v1/images/generations`（文生图 / 图生图） |
| 编剧 | `agnes-2.5-flash` | `POST /v1/chat/completions` |
| 配音 | edge-tts（本机合成，免费） | `python -m edge_tts` |

端点：`https://apihub.agnes-ai.cn/v1`（国内）/ `https://apihub.agnes-ai.com/v1`（国际）。
详细参数、错误码、实测见 `providers/agnes.md`。

## 关键约束（模型硬限制，不是建议）

| 约束 | 数值 | 说明 |
|---|---|---|
| 单段时长 | **4–12 秒**（字符串） | 超过 12 秒必须拆镜头；脚本自动 clamp |
| 输出分辨率 | 固定 **720P** | 传别的值直接 400；尺寸由 `aspect_ratio` 决定 |
| 竖屏 | `aspect_ratio: "9:16"` → 704×1280 | 默认就是竖屏 |
| 首帧图 | keyframe 模式传 `first_frame` | 本地图用 base64 data URI 直接传，无需图床 |
| 并发 | **最多 3 路同时生成** | 3 槽位排队，完成一个补一个；**额度是账号级、不分模型** |
| 轮询 | **30 秒一次**（全局节流） | 多任务轮转查询 |
| 音轨 | 视频**自带环境音轨**（实测 aac） | 台词口型靠提示词；担心没出声可加 TTS 兜底（见下） |

### flash 排不上队？换付费模型

`agnes-video-2.5-flash` 走免费额度，热门时段提交会连续 `HTTP 429 / 503`，一镜排十几分钟很正常（`submit_rounds` 打满 40 轮才放弃）。**账号里有余额就直接用付费版**，接口和参数完全一样，只改 model 名：

```bash
python scripts/ac.py setup            # 交互里把「视频模型」改成 agnes-video-2.5
# 或直接改 ~/.workbuddy/agnes-clip.json：
#   agnes.video_model = "agnes-video-2.5"
#   video.model       = "agnes-video-2.5"
```

实测同一账号：flash 提交 6 次全 429；付费版**立即入队**，8 秒镜头约 3 分钟出片。

⚠️ **并发额度是账号级的，不分模型**。同时开两个 `ac.py video` 进程（每个内部 3 路）就会互相抢槽，付费版照样 429。要跑批量就**只开一个进程**，用 `--only` 一次把镜头列全。

## ⛔ 开工前置：先有骨架，再写分镜

**直接从一句概念跳到 shots.json = 流程违规。** 实测教训：这样写出来的十镜是十个并列的漂亮画面，没有欲望、没有阻碍、没有变化；等视频跑完才发现剧本是空的，几十秒额度全废。

### 编剧六步（每步都要用户点头，不许抢跑）

| 步骤 | 交付物 | 要求 |
|---|---|---|
| 1 | **logline** | 谁 + 想要什么 + 遇到什么阻碍 + 最后变成什么。缺任何一项都不算 |
| 2 | **情绪曲线** | 每镜一个 -5~+5 的值，必须有一个最高点、一个最低点，不能连续三镜同值 |
| 3 | **母题** | 一个具体物件/动作贯穿全片，首尾各出现一次（开头空手，结尾手里多了它） |
| 4 | **场景与机位表** | 每个场景 ≤5 个机位，写明 A 主镜头 / B、C 过肩；**写死轴线：谁在画左、谁在画右** |
| 5 | **分镜表** | 每镜标 `scene` + `angle`，并回答四问：作用（推进/停顿/转折）· 因为上一镜____所以这一镜____ · 她做什么动作 · 观众该想什么 |
| 6 | 才允许 `frame` / `video` | 前五步没确认，不许动生成 |

**四条硬规则**：禁止连续两镜都是「站着看」；每镜必须有一个动作；用户说「绝对不能出现」的一个都不许出现；写完做「删一镜测试」——删掉一镜故事不残缺，那它就是废镜。

### 机位系统（解决"一会儿左一会儿右"）

| 代号 | 名称 | 作用 | 焦段 |
|---|---|---|---|
| **A** | 主镜头 Master | 交代空间、两人站位、轴线 | 35mm |
| **B** | 过肩看甲 | 乙的视角，甲在画左三分之一 | 50–85mm |
| **C** | 过肩看乙 | 甲的视角，乙在画右三分之一 | 50–85mm |

- 两人连线就是轴线，A/B/C 必须在同一侧；定好后**全场景不许换边**。
- 每镜提示词必须写清「景别 + 机位关系 + 人物在画面哪一侧」，缺了"哪一侧"模型就自由发挥，一发挥就跳轴。
- 运动镜头只放在 A 上；B/C 保持固定或极缓推，否则两个过肩镜头的空间感对不上。
- 第一镜用 A：必须交代清楚「这是什么地方、谁在哪、两人什么关系、谁在左谁在右」。
- 详见 `references/camera_setups.md`（机位模板、越轴症状、自查清单）。

### 没有对白的写真片怎么排

写真/形象片不靠台词，靠**动作链 + 情绪曲线 + 母题**：
- 每镜一个具体动作（推门、抬手触镜、赤脚踩进水里），不要"站着看镜头"；
- 转场按情绪走：同场景 dissolve、穿越/闪回 fadewhite；
- BGM 推成背景音（`--bgm-volume 1.35 --bgm-lowpass 3200`），不要盖过环境。

## 对白节奏：别让一句台词撑 7 秒

**症状**：一镜只有一句台词，却给了 7 秒；前 6 秒干站着，最后一秒才开口，拼起来又拖又假。

**根因有三层**，三层都要治：

| 层 | 问题 | 修法（已内置） |
|---|---|---|
| 时长 | 按"动作 + 空间"算时长，一句 13 字的台词也能撑到 7–10 秒 | 有台词的镜头改为**以台词为锚**：`字数/4.2 + 0.9`，封顶 8 秒；无台词镜头才按动作算 |
| 提示词 | 只写"说话 + 口型"，模型自然把台词拖到镜头末尾 | 写死**开口窗口**：`starts speaking at about 0.5s and finishes by 2.8s; after that only a silent reaction — never delay the line to the end` |
| 合成 | 整段拼接，开播前的静音全留着 | `assemble` 默认按**真实人声**收紧：砍掉开口前的死等，尾部留 0.9 秒反应；`--no-tighten` 可关 |

**Agnes 的硬下限**：`seconds` 只能是字符串 `"4"`–`"12"`（默认 `"5"`，`size` 只能是 `"720P"`）。
所以**一镜最短 4 秒**，规划时不要出现 2–3 秒的镜头；`calc_duration` 已经钳在 4–8 秒。

**短句不单独成镜**（这是关键）：≤6 个汉字的回应（「陈屿。」「我知道。」「嗯。」）由管线自动并进上一镜，
变成双人对话镜头——接话的人会被补进 `cast`、提示词改写成 two-shot。合并条件：同场景、上一镜还没并过、
合并后不超过 2 人、两句合起来装得进 8 秒。装不下就老实单独成镜（4 秒起）。

一句话：**长台词一镜一句，短回应并进上一镜；宁可少一镜，不要多两秒空等。**

**验收标准**：每镜台词起点应落在镜头前 45%，`audit` 会把超过的逐条标出来（"台词到 4.2s 才开口（占 58%），前段空等"）。

**节奏建议**：对话正反打不要一个镜头塞两句。一句一个镜头，说话人 2.5–4 秒，听话人反应镜 1.5–2.5 秒，交替；这样既有停顿又不拖。

## 首帧提示词的四个硬保证（可自检）

每次生成首帧，代码都会强制补齐这四件事，不依赖模型自觉：

| 保证 | 具体内容 | 怎么验 |
|---|---|---|
| **锁人脸** | 末尾必有 `Keep the face, identity, hairstyle and body proportions exactly as in the reference image; same person, no morphing, no identity drift.`（判断词是 `identity drift`，避免被模型自己那句 "keep the face" 挡掉） | 日志 / `--dry-run` |
| **带参考图** | `faces`（默认等于 `cast`）里每个人的 `face_ref.jpg` + 本机位场景板，base64 放进 `extra_body.image`；单人 2 张、双人 3 张 | 日志会写「参考图 N 张：人脸 X + 场景 1」 |
| **人数锁死** | 自动写 `Headcount in this frame is exactly N, and these are the only bodies visible: 1) … 2) …`，空位用陈述句交代「其它座位是空的」。**不要用 no other people / no duplicated person 这类否定句**，越写越容易画出来 | `--dry-run` 直接看 |
| **人物位置** | 提示词没写左右时自动补 `Composition: A 在画左三分之一、B 在画右三分之一、不许过轴`；单人则略偏左、视线方向留空 | `--dry-run` 直接看 |

> 🔴 **过肩镜头必看**：前景那人背对镜头、不露脸，就一定要 `"faces": ["露脸的那位"]`。
> 把他的正脸参考图一起喂进去，模型会在窗边/门口另画一个完整的人——同一镜里出现两个同一个人。
> 本 skill 已经踩过这个坑（S06 窗边凭空多出一个男主），代码层没有强制，只能靠 `faces` 收窄。

### 🔴🔴 否定句是最大的穿帮来源：写一次是防护，写十次是召唤

**扩散模型读不懂否定。** 读到 `no third person`，它激活的是 `person` 这个概念——
不是"排除人"，而是"这里有人"。

**实测事故**（本片 S14）：提示词里为了保险，把否定句堆了 15 处——
`no third person` ×2、`no extra man`、`no extra woman`、`no visitor`、`no neighbour`、
`no background figure`、`no person in the doorway`、`no mirror reflection of another person`、
`no photograph of a person on the wall`、`no picture frame showing a face`……

结果模型画出**三个建华**。同一个镜头里又出现了完整的人。
每多写一遍否定，就多强化一遍"人"这个概念。

**正确写法：正面点名 + 把空位说成是空**

| ❌ 否定式（越写越糟） | ✅ 正面式 |
|---|---|
| `no third person, no extra man, no extra woman` | `This picture contains exactly two people: the two named above.` |
| `no visitor, no neighbour, no background figure` | `The doorway is empty, the wall is empty, the far corner of the room is empty, the floor is empty.` |
| `no photograph of a person on the wall` | `The wall carries one blank paper calendar and one small old wooden picture frame whose content cannot be seen.` |
| `no reflection of another person` | `The wall behind them is bare plaster.` |
| `no third person, no silhouette in the doorway` | `Everywhere else in the frame is empty space.` |

**自检**：数一下最终提示词里有多少个 `no ` 开头的人相关否定句。
**超过 2 处就该改**。改成正面陈述后通常还能顺带缩短 300–1000 字符，
提示词越短，模型越听话。

**唯一例外**：`no on-screen text` / `no watermark` / `no readable writing` 这类
「禁止画面元素」类的否定是安全的，因为它们指向的是**文字/图形**而不是**人脸**。

自检命令（不调用 API、不花钱）：

```bash
python scripts/ac.py frame "<项目>" --only S03 --dry-run --force
```

## 九条铁律（照做才不崩）

1. **一镜一个连续长镜头**。禁止 `cut to` / `jump cut`，只写 one continuous shot。硬切会让模型重建人脸。
2. **首帧锁人，提示词只写动作**。脸的形状由 `face_ref.jpg` 决定，提示词不要描述五官。
3. **接力只在同场景同机位之间用**。紧接的两镜如果是同一机位、同一组人在说话（正反打、接话），
   后一镜标 `"link": "prev"`，首帧直接取上一镜**最后一帧**，场景/站位/碗的位置全部接上。
   跨场景、换机位、跳时间**禁止**接力，否则会换人换景。
   ⚠️ Agnes 视频接口只吃**一张首帧**，没有 H3 那种"人物参考 + 尾帧双输入（Ref2VA）"，单靠尾帧接力会一步步漂。
   对策：**只接一段**（不许 A→B→C→D 连传），并且接力镜提示词必须逐件锁服装（`keep exactly the same clothing as the reference frame: cream knit cardigan, dark navy dress`）；人物锚点仍由定妆图长期维护。
4. **景别跨度不超过 2 倍**。安全区：中远景 ↔ 腰以上中景；不要直接怼脸特写。
5. **微表情写成过程**。`she smiles` 会得到定格假笑；写「嘴角先起，再漫到眼底」才是活的。
6. **双人镜头写清第二个人的服装**。参考图只锁主角的脸；同框的第二人不写发型服装会自己换衣服。
7. **场景按「场景 × 机位」出板，不按镜头出板**。一个场景先写陈设清单 + 机位表（wide / counter / table / entrance / door），
   每个机位一张空板；同一机位的所有镜头共用这张板。首帧只换机位，不换布景，画面才不会每镜换一间店。
8. **环视镜头偶尔用**。全片 1–2 次 `slow arc / orbit`，用在情绪落点或三人同框；台词特写别环视，会晃。
9. **人物一律是东亚/中国人长相**。角色名是英文时（xiao-man、chen-yu），模型很容易做成欧美人；每条人物/首帧/视频提示词都要写 `East Asian Chinese with East Asian facial features, black hair, dark eyes`。

## 目录结构

```
<project>/
├── project.json              # 项目配置（不含密钥）；可写 scene_anchor / cast_dir
├── script/
│   ├── story.md              # 人读剧本（场景/动作/微表情/对白）
│   └── shots.json            # 机器读镜头表（含 characters / props / 精修字段）
├── assets/
│   ├── characters/<name>/    # source.jpg + face_ref.jpg + turnaround.jpg（三视图）
│   ├── props/<name>.jpg      # 道具参考图
│   └── scenes/<场景>__<机位>.jpg  # 场景板：一个场景×一个机位一张，同机位所有镜头共用
├── frames/                   # S01.jpg … 每镜首帧
├── clips/                    # S01.mp4 … 每镜视频（_pending.json 记录在途任务）
├── audio/
│   ├── vo/S01.mp3            # 每句台词的配音（可选）
│   ├── sfx/*.wav             # 音效素材：真实素材放这里，sfx.py 合成的也在这里
│   ├── music/*.mp3           # 配乐曲库，配乐台从这个目录试听与选曲
│   └── bgm.mp3               # 当前使用的配乐
├── qa/                       # 质检抽帧、缩略图墙（交付前可删）
├── out/final.mp4             # 成片
├── AUDIT.md                  # 审计报告（逐镜核对 + 质检 + 成本）
└── audit.json                # 审计原始数据
```

同一系列多集时：

```
系列/
├── cast/<角色名>/            # 共享角色库（face_ref + source + turnaround），各集共用一张脸
├── ep01/                     # 一集 = 一个完整 project 目录
└── ep02/                     # project.json 里 cast_dir 指回 ../cast
```

## 命令

脚本：`scripts/ac.py`（标准库 + ffmpeg；配音需要 `pip install edge-tts`）

```bash
# 全自动一条龙（最常用）
python scripts/ac.py auto "<项目目录>" --idea "深夜面馆，女孩每晚都来吃面" --shots 8

# 首次配置（本地网页）
python scripts/ac.py config-ui

# 分步执行
python scripts/ac.py init  "<dir>" --title "片名"
python scripts/ac.py story "<dir>" --idea "..." --shots 8 --seconds 7
python scripts/ac.py char-gen "<dir>" --name girl            # 从 shots.json 读角色描述
python scripts/ac.py char-gen "<dir>" --name boss --desc "50岁女性，盘发，深蓝围裙"
python scripts/ac.py char-add "<dir>" "C:/photos/me.jpg" --name hero   # 真人照片锁脸
python scripts/ac.py cast "<dir>" [list|init|push] [--name girl] [--all]  # 共享角色库（多集复用同一张脸）
python scripts/ac.py episode-new "<第1集目录>" --name ep02 --title "第二集"  # 新建一集并继承全部角色形象
python scripts/ac.py prop-gen "<dir>" --name umbrella        # 从 shots.json 读道具描述
python scripts/ac.py scene-gen "<dir>" [--force]              # 按场景四要素生成空场景图
python scripts/ac.py frame "<dir>" [--only S01] [--force]
python scripts/ac.py video "<dir>" [--only S01] [--wait] [--force]
python scripts/ac.py fetch "<dir>"            # 续查已提交任务（不重复提交）
python scripts/ac.py voice "<dir>" [--force]  # 按台词生成配音（按角色分配音色）
python scripts/ac.py music "<dir>" --duration 90 --caption "雨夜，钢琴"
python scripts/ac.py music "<dir>" --provider volc --duration 90 --caption "..."   # 火山引擎（无卡可跑，>60s 自动分段）
python scripts/ac.py assemble "<dir>" [--subs] [--voice]
python scripts/ac.py audit "<dir>"            # 出 AUDIT.md（逐镜核对 + 质检 + 成本）
python scripts/ac.py status "<dir>"
```

> **字幕默认关闭**。AI 生成的画面里不烘任何文字；需要字幕时加 `--subs`，脚本会在最后 ffmpeg 合成阶段先做**人声检测（VAD）**，把每句字幕卡到真实说话的时间段，而不是按镜头开头硬放。

### 全自动推荐用法

```bash
# 1) 先跑一镜验收（只出 S01，不合成）
python scripts/ac.py auto "<dir>" --idea "..." --only-first

# 2) 验收通过后整片跑（已有素材自动跳过）
python scripts/ac.py auto "<dir>"

# 3) 配乐 / 配音 / 字幕（按需）
python scripts/ac.py auto "<dir>" --music                       # 走配置里的配乐通道
python scripts/ac.py music "<dir>" --provider volc --duration 104   # 临时改走火山，不影响全局配置
python scripts/ac.py voice "<dir>" && python scripts/ac.py assemble "<dir>" --voice
python scripts/ac.py assemble "<dir>" --subs     # 只在合成阶段加字幕，按真实人声对齐
```

`auto` 是幂等的：已存在的角色图、道具图、首帧、片段都会跳过，中断后重跑只补缺的。

## 镜头表格式（script/shots.json）

```json
{
  "title": "对面那碗面",
  "logline": "一句话故事",
  "genre": "剧情 / 温情",
  "characters": [
    {"name": "girl", "desc": "25岁女性，齐肩黑发，米白针织开衫", "desc_en": "...", "voice": "zh-CN-XiaoxiaoNeural"}
  ],
  "props": [{"name": "bowls", "desc": "两只白瓷面碗", "desc_en": "..."}],
  "shots": [
    {
      "id": "S01",
      "duration": 7,
      "scene": {"slug": "面馆内·夜", "time": "深夜", "place": "面馆内", "weather": "无雨", "light": "暖黄吊灯"},
      "char": "girl",
      "action": "老板娘把一碗面放在女孩对面",
      "micro": "嘴角先提了一下，笑意才慢慢漫到眼底",
      "speaker": "boss",
      "line": "还是不要葱对吧？",
      "frame": {"mode": "swap", "prompt": "English still prompt… Keep the face … as in the reference image."},
      "video_prompt": "English video prompt… speaks in Mandarin with precise lip-sync: \"还是不要葱对吧？\"…"
    }
  ]
}
```

- `frame.mode = "source"`：直接用角色定妆图（纯人物镜头）
- `frame.mode = "swap"`：用 `face_ref.jpg` 作参考，按 prompt 换场景/服装生成首帧
- `frame.mode = "plate"`：空镜，直接裁场景板当首帧（配合 `char: null`）
- `duration`：4–12 的整数

**精修阶段才用、但必须提前留位的字段**（全部是相对本镜的时间）：

| 字段 | 作用 |
|---|---|
| `cast` | 画面里所有人，人数锁与参考图按它来；双人镜必须写 |
| `faces` | 只喂露脸的人（过肩镜必写，否则前景脸会被复制成第二个人） |
| `scene.set` / `scene.angles` / `angle` | 陈设清单 + 机位表；缺了场景板就乱 |
| `scene.interior` | 室外戏写 `false`，否则会强加"这是室内" |
| `x` | 进入本镜的转场 `{kind, dur}`，`cut` 硬切 |
| `subs` | 逐句字幕 `{t, d, text}`，14 字拆两条 |
| `sfx` | 音效 `{at, kind, gain}` |
| `bgm` | 本镜配乐音量 0–1 |
| `tighten` | `false` = 保留台词后的表演，不按人声裁尾 |
| `tts` | `true` = 这一镜只混 TTS（模型念糊时用） |

完整字段表与每个字段的取值规则见 `references/full_pipeline.md` 阶段 2。

## 配音与字幕

- **字幕默认关闭**，AI 画面里不出现任何文字（`video_prompt` 会强制加 `No on-screen text, no subtitles...`）。
- **字幕两种写法，优先第二种**：
  1. `assemble --subs`：做人声检测（VAD），每句字幕对齐真实说话区间。缺点：**轻声台词检不到**
     （"我只是……怕。"这类气声会被漏掉），一镜多句会合并成一行。
  2. **逐句写 `shot.subs`（推荐）**：精度最高、可控断句。`t` 是本镜内相对秒，`d` 是显示时长：

```json
"subs": [
  {"t": 0.19, "d": 1.40, "text": "趁热喝，不加糖。"},
  {"t": 3.60, "d": 1.08, "text": "……下次别买了。"}
]
```

- **单排不超过 14 个汉字**。长句在标点处拆成两条先后出现；ASS 里 `WrapStyle=2` 禁止自动换行，
  宁可拆两条，也不要让播放器折成两排（标题式字幕折行最出戏）。
- **配音**：`voice` 用 edge-tts 把每句台词念成 `audio/vo/<sid>.mp3`，按 `speaker` 分配音色（`voices` 配置或角色 `voice` 字段）。
- **默认不混 TTS**：模型自己会出人声时，再叠 TTS 会双重人声。只有确认模型没开口才用 `assemble --voice`；
  此时字幕会对齐 TTS 的时长。
- **某一镜模型念糊了**（关键词错、含糊）：该镜音轨换静音（`anullsrc` 替换），只留干净的 TTS，标 `"tts": true`。
  别在同一镜里既留模型人声又混 TTS——两重声音一听就露。
- 音色表（`~/.workbuddy/agnes-clip.json` 的 `voices`）：`default`、`VO`、`rate`、`volume`，也可以按角色名逐个指定。
  旁白（`VO`）默认音色可能是男声，内心独白要女声时按镜单独合成。

## 配乐通道：有卡走 ComfyUI，没卡走火山

两条通道出口都是 `audio/bgm.mp3`，后面的逐镜音量、配乐台、合成完全一样，换通道不影响流程。

| provider | 走什么 | 什么时候用 | 成本 |
|---|---|---|---|
| `comfyui` | 本地/远程 ComfyUI + MiniMax Music3，整条一次出 | 有显卡、卡空着 | 0 |
| `volc` | 火山引擎「AI 音乐生成」（豆包音乐模型）OpenAPI | 没卡、卡在排队、赶时间 | 0.002 元/秒（100 秒约两毛） |

```bash
python scripts/ac.py music "<dir>" --provider volc --duration 104 --caption "..."
# 也可以写进全局配置：配置界面「配乐」TAB 选通道，之后 music / auto 都跟着走
```

### 火山这条的三个硬事实（不写清楚必踩）

1. **纯音乐单次上限 60 秒**。片子更长时脚本自动切段（每段多留 2 秒做交叉淡化），逐段生成后 `acrossfade` 拼回一条，最后统一 loudnorm。
   代价是段与段之间能听出"换段"——**能用 ComfyUI 一次出整条就别分段**。
2. **两个计费入口不互通**：`GenBGMForTime`（按时长后付费）与 `GenBGM`（套餐包）。默认后付费；走错报 `200028 没有可用资源包`。
3. **签名是火山自有 V4**：中间密钥用**二进制**不是十六进制，Host 只参与签名不单独发。算错会报 `SignatureDoesNotMatch`（多半 SK 填错或本机时间偏 >5 分钟）。
   配置界面「测试连接」打的是 `QuerySong` 空任务——能返回业务错误（任务不存在）就说明签名通了。

| 错误码 | 意思 | 怎么办 |
|---|---|---|
| `200028` | 无可用资源包 / 后付费没开 | 控制台打开「按时长计费」；确认用的是 GenBGMForTime |
| `50000001` | 版权相似度校验没过 | Text 写具体（乐器/情绪/场景/节奏），或开 `music.volc.rewrite` |
| `InvalidAccessKey` | AK 不存在 | 核对 AK |
| `SignatureDoesNotMatch` | 签名不匹配 | 核对 SK、校准系统时间 |

## 配乐：按镜头控制音量，不要整条铺平

生成：`python scripts/ac.py music "<dir>" --duration 104 --caption "..."`（ComfyUI 走 MiniMax Music3，`lyrics` 固定 `[Instrumental]`；`--provider volc` 走火山引擎）。

**第一步必须先做响度归一化**，否则同一首曲子里各段本身差 10dB 以上，后面设的系数完全没有意义：

```bash
ffmpeg -y -i audio/bgm.mp3 -af "loudnorm=I=-23:TP=-2:LRA=7" -c:a libmp3lame -b:a 192k audio/bgm.mp3
```

**第二步逐镜写 `bgm` 音量**（0–1，不写就沿用上一镜）：

```json
{"id": "S07", "bgm": 0.0}
```

合成时 `assemble` 会：

| 行为 | 说明 |
|---|---|
| 相邻同值合并成段 | 16 镜通常只剩 6–7 段，不会每镜都切一次 |
| 段间 0.45s 淡入淡出 | 边界正好落在镜头切换点，听感像换气 |
| 尾段 3s 淡出 | 结尾不硬切 |
| 音乐按原时间轴切片 | 段是同一首曲子的不同时间片，拼回去仍连贯，不是重复播放 |
| 原声只降到 0.82 | **台词也在原声这条轨上**，压到 0.4 会把人声一起压小 |

**电平标准**（实测校准过的，照抄即可）：配乐比对白低 12–17dB。

| 剧情位置 | bgm 值 | 相对原声 |
|---|---|---|
| 开场日常、环境声为主 | 0.26 | −12.6dB |
| 情绪下沉、准备留白 | 0.22 | −17.3dB |
| **完全撤空**（叙事的重音） | 0.0 | 静音 |
| 主题段、对白密集 | 0.60 | −15.5dB |
| 判决/打击那一刻 | 0.08 | −16.6dB |
| 最孤独的一镜 | 0.40 | −11.7dB |

合成日志会打印实际分段，例如 `配乐分段：7 段，音量 0.00s起0.26 / 32.94s起0.22 / 38.12s起0.00 …`，可以直接核对。

**验证方法**：把带配乐版和无配乐版反相相减，残差就是纯配乐轨，逐段测响度即可确认"该响的地方响了、该静的地方真静了"。


## 音效：叠在成片上，不重混（`sfx` 字段）

音效素材不用去找，`scripts/sfx.py` 现场合成（纯标准库，无 numpy、无版权问题）：glass / notify / notify2 / tick / tap / whoosh / thud / rain / tinnitus / drone。

**先写镜头表**（`at` 是本镜内秒数，`gain` 是 dB，相对素材本身 −3dBFS 峰值）：

```json
{"id": "S09", "sfx": [{"at": 0.55, "kind": "notify", "gain": -17}]}
{"id": "S01", "sfx": [{"at": 0.30, "kind": "rain", "dur": 42.0, "gain": -28}]}
```

带 `dur` 的三种（rain / tinnitus / drone）才需要写时长，其余是固定短音。

**两种用法**：

```bash
# 只生成素材到 audio/sfx/（不叠加）
python scripts/ac.py sfx "<dir>"

# 叠到已有成片上 —— 视频流直接复制，不重编码；音频重混一条
python scripts/ac.py sfx "<dir>" --into out/final.mp4 --out out/final-sfx.mp4
```

`assemble` 也会自动读 `sfx` 字段，从头合成时一起混进去。**但同一版不要叠两次**——`--into` 的源要用不带音效的那版（本项目是 `out/final-bgm.mp4`），否则音效会翻倍。

**选音原则**（心理/写实片，别当综艺剪）：

| 场景 | 用什么 | 电平 |
|---|---|---|
| 手机来消息、对方回话前 0.6–1s | `notify`（判决那条用更闷的 `notify2`） | −14 ~ −18dB |
| 打字、删、按住说话、手指触屏 | `tick` / `tap` | −16 ~ −20dB |
| 语音发出去、镜头切换前 | `whoosh` | −17 ~ −18dB |
| 碰杯、玻璃落在桌上 | `glass` | −20dB |
| 手机扣下、扔在床上 | `thud` | −16 ~ −18dB |
| 场景本身没环境声（模型漏了雨/街道） | `rain`（可拉长到几十秒当底） | −26 ~ −30dB |
| 她"听不进去"的那层膜 | `tinnitus`（耳鸣，3.4–5kHz 窄带） | −32 ~ −38dB |
| 压在心口的"嗡" | `drone`（55Hz + 泛音，手机上靠 110/165Hz 出声） | −27 ~ −30dB |

**三条经验**

1. **纯正弦的耳鸣听起来像测试音**。必须混一层窄带噪声 + ±4Hz 慢漂移（`_tinnitus` 里已实现），才是"耳朵在响"。
2. **55Hz 手机放不出来**。`drone` 的 110/165/220Hz 泛音不能省，否则短视频客户端上等于没有。
3. **音效落点优先挑镜头切点前后**，不要卡在演员微动作上——模型生成的片段里动作时刻不可控，卡错比不卡更出戏。

**验证方法**：新成片与旧成片反相相减，残差就是纯音效层；再逐点测响度，确认"该响的点抬起来了、对白段只抬 1–2dB（没盖人声）"。总电平不应变化（本项目 mean −22.7dB、max −1.5dB，与加音效前一致）。


## 转场：别一路硬切，也别逢切必叠

写在镜头表的 `shot.x`，表示**进入这一镜**时怎么过渡：

```json
{"id": "S02", "x": {"kind": "fade", "dur": 0.8}}
{"id": "S05", "x": {"kind": "cut"}}
```

| 位置 | 做法 | 理由 |
|---|---|---|
| 换场景、跳时间、跳空间 | `fade` 0.8–1.2s | 硬切会让人觉得"很干"，像 PPT 翻页 |
| 同场景正反打、连续动作 | `cut`（硬切） | 叠化会拖，破坏对话节奏 |
| 结尾空镜 | `fade` 1.2s | 收得住 |

> 🔴 **xfade 的 duration 不能短于一帧**。曾用 0.04s 当"硬切"（24fps 一帧 = 0.0417s），
> 整条滤镜链**静默失败**，172 秒的片子被截成 33 秒，日志还不报错。
> **硬切统一写 0.1s**（肉眼仍是硬切），合成后必须核对成片时长。

> 🔴 **转场会缩短总时长**（`总长 − Σ转场时长`）。所以字幕、音效、配乐一律用**相对本镜的时间**
> （`subs.t` / `sfx.at` 都是相对值），由合成阶段按新起点重排。写绝对秒数必然全片错位。

## 首次使用：配置凭据

密钥不写在 skill 包里，放在本机 `~/.workbuddy/agnes-clip.json`（与 `ai-video-pipeline` 完全隔离）。

```bash
# 配置界面（推荐，首次启用跑一次）
python scripts/ac.py config-ui
```

会打开 `http://127.0.0.1:8765/` 的本地配置页，**全部可配项都在这一个页面**：

| 模块 | 可配置内容 | 说明 |
|---|---|---|
| 推理 / 编剧 | 来源（WorkBuddy 默认 / 外部文本 API）、端点、key、模型 | WorkBuddy 默认不用 key，剧本走当前会话模型 |
| 生图 | 渠道、端点、key、模型、尺寸、比例 | 角色定妆 / 三视图 / 场景板 / 首帧都吃这一份 |
| 生视频 | 通道（免费 apihub / 付费 api / 自定义）、端点、key、模型、并发路数、轮询秒数、默认时长、画幅 | 视频独立 key，不用于图片和剧本 |
| 生视频·高级 | 单次超时、每轮重试次数、总重试轮数、首帧上传命令 | 队列满时的行为都在这里调 |
| 配音 | 默认音色、旁白音色、语速、音量 | 音色可下拉选也可自定义，**带试听按钮**（当场合成一句 MP3 播放） |
| 配乐 | **通道二选一**（ComfyUI / 火山引擎）+ 各自的参数 + 默认时长、默认提示词 | 不填也能出片，只是没背景音乐；火山只需 AK/SK |
| 系统 | ffmpeg 路径、配置文件位置 | 填 `ffmpeg` 表示用 PATH 里的，装了 imageio-ffmpeg 会自动找到 |

每块都有「测试连接」：推理/生图/生视频会拉一次模型列表并核对指定模型是否存在；配乐看通道——ComfyUI 探 `/system_stats`，火山用 `QuerySong` 打一个空任务验 AK/SK 签名；配音是直接试听。

保存后写入 `~/.workbuddy/agnes-clip.json`，图片/剧本/视频三条通道互相隔离：视频 key 不会用于生图和剧本。

### 出图通道：全局 vs 项目级

**全局**（配置页「生图」TAB）影响所有没单独指定的项目。

**项目级**用 `pick-image` 指定，**只影响这一个项目**，写在该项目的 `project.json`：

```bash
python scripts/ac.py pick-image <项目目录> --channel agnes      # Agnes 云端（默认，稳）
python scripts/ac.py pick-image <项目目录> --channel gpt-image  # OpenAI 兼容中转
python scripts/ac.py pick-image <项目目录> --channel openai     # 同上，语义别名
python scripts/ac.py pick-image <项目目录> --channel banana     # Nano Banana（Gemini 原生，锁脸/服装最准）
python scripts/ac.py pick-image <项目目录>                     # 清除设置，跟随全局
```

三条通道的实测差别（2026-10-20）：

| 通道 | 协议 | 带参考图的耗时 | 适用 |
|---|---|---|---|
| `agnes` | OpenAI `/images/generations` + `extra_body.image` | 30–40s | 稳、快，人多镜头默认用它 |
| `gpt-image` | OpenAI `/images/generations` + `input[]` | 无参考图 25s；**带参考图常挂满 480s 超时** | 只在生图网关正常时用 |
| `banana` | Gemini 原生 `/v1beta/models/<model>:generateContent` | 60–90s（nano-banana-pro 2K） | 服装/道具/手部这些"写进提示词就要照做"的细节最听话 |

优先级：**项目级 > 全局**。这样同一个 skill 能同时跑不同通道的项目，不用反复改全局配置。

**每个项目开工前先跑一次 `pick-image`** —— 这是本 skill 的推荐习惯。

配置页「生图」TAB 里也有同一个下拉框，可以直接改全局；改了全局不影响已经设了项目级的项目。

也可以继续用命令行：

```bash
python scripts/ac.py setup \
  --agnes-endpoint "https://apihub.agnes-ai.cn/v1" \
  --agnes-key "cpk-xxxx" \
  --check

# 可选：视频专用通道（独立 key / 独立入口，只用于视频；图片和剧本仍用上面的主 key）
python scripts/ac.py setup \
  --agnes-video-endpoint "https://api.agnes-ai.cn/v1" \
  --agnes-video-key "sk-xxxx"
```

`--check` 会分别检查主通道和视频通道，确认 `agnes-video-2.5-flash` 可用。视频 key 只用于 `/videos` 提交与轮询，不会用于图片或剧本。

## 发布 / 分享

### 分享给朋友（发 zip）

在本 skill 目录下运行打包脚本，会自动过滤缓存与凭据文件：

```bash
python tools/package_skill.py
```

产出 `dist/agnes-clip-<版本>.zip`（仓库根目录名统一为 `agnes-clip`）与同名 `.sha256`。

**包内结构**（目录名必须用英文 `agnes-clip`，中文名过不了 WorkBuddy 的发布校验）：

```
agnes-clip/
├── 安装卡.md          ← 给对方看这个，5 分钟装完
├── README.md          完整说明：15 步工作流、命令速查、常见问题
├── SKILL.md           给 AI 读的工作手册
├── commands/          6 个斜杠快捷指令
├── references/        7 份深度参考
├── providers/agnes.md Agnes 平台参数说明
└── scripts/           ac.py 主程序 + sfx.py + music_ui.html
```

**对方怎么装**：

1. 解压到 `~/.workbuddy/skills/agnes-clip`（或项目 `.workbuddy/skills/agnes-clip`）
2. 复制 `commands/*.md` 到 `~/.workbuddy/commands/`（用 `/装快捷指令` 也能一键装）
3. 跑 `ac.py setup` 填自己的 key（或说「用 agnes-clip 配置一下」走图形界面）
4. 说创意开工

密钥、项目目录都不在包里，互不影响。

### 做成插件发布（带 `/插件名:命令名` 形式）

如果要走 WorkBuddy 插件市场，把发布件包成插件结构：

```
agnes-clip/
├── .codebuddy-plugin/plugin.json
├── commands/          ← 现有 6 个命令直接放这
└── skills/
    └── agnes-clip/    ← 整个 skill 目录放这
```

插件里的命令注册后是 `/agnes-clip:配置` 这种带前缀的形式。

### 发布前自检

```bash
python <skill-creator>/scripts/quick_validate.py <skill目录>   # 必须输出 Skill is valid!
```

**注意**：`SKILL.md` frontmatter 的 `name` 必须是纯英文连字符（`agnes-clip`），不能用中文。
本机安装目录名可以保留中文（不影响运行），但**发布包里的目录名要用英文**。

## 已知限制与对策

| 现象 | 原因 | 对策 |
|---|---|---|
| `HTTP 503 video_queue_full` | 云端队列满 | 自动退避 + 回队列补位（最多 10 轮），不丢任务 |
| 轮询 `HTTP 429` | 查询限流：**30 秒一次** | 全局节流，多任务轮转 |
| 中断后不想重跑 | 任务已在云端排队 | `ac.py fetch <dir>` 续查 `clips/_pending.json` |
| 任务排队久 | 账号最多 **3 路并发** | 3 槽位排队；8 个镜头约 3 轮 |
| 首帧报 `400 first_frame` | 服务端拒收 data URI | 配 `agnes.frame_upload` 上传命令换公网 URL |
| 口型对不上 | 模型口型能力有限 | 提示词写死台词 + 口型指令；字幕保证信息不丢；必要时 TTS 兜底 |
| 模型没出声 | 视频音轨可能只有环境声 | `voice` + `assemble --voice` 补真人声（口型可能对不上） |
| 单段最多 12 秒 | 模型限制 | 拆镜头；8 个 7 秒镜头 ≈ 56 秒 |
| 人物不像 | 首帧参考图不对 | 检查 `face_ref.jpg`；不要尾帧接力 |
| **成片只剩 30 秒** | xfade 转场时长 < 1 帧，滤镜链静默截断 | 硬切写 0.1s，重合成后核对 Duration |
| **字幕全是旧版** | 烧制滤镜写死 `ass=_subs.ass`，外部字幕不生效 | 已修；仍未生效就查 `out/_subs_shots.ass` 是否被重新生成 |
| **一句台词显示成两排** | 播放器自动折行 | 改 `shot.subs` 逐句手写，14 字拆两条，`WrapStyle=2` |
| **旁白有两重人声** | 模型念了一遍 + TTS 又混一遍 | 该镜音轨换静音只留 TTS，或去掉 `--voice` |
| **台词后的表演被剪掉** | tighten 按「人声结束+0.9s」裁尾 | 该镜 `"tighten": false`（拿不准就全片关） |
| **桌上多出剧本没有的食物** | 首帧提示词写过 / `scene.set` 漏 / 旧的全局面馆锚 | 改 prompt 明令禁止该道具，重跑该镜 frame+video |
| **同一镜出现两个同一人** | 过肩镜把前景那张脸也喂进参考图 | `faces` 只留露脸的人 |
| **每镜都换一间店** | 场景板按镜头出而非按机位 | 写 `scene.set` + `scene.angles` 后 `scene-gen --force` |
| **结尾突然没音乐** | bgm 短于成片总时长 | 按 ≥ 总时长重新生成，再做 loudnorm |
| **音效几乎听不见** | gain 给到 −26dB 以下 | 提到峰值 ≈ −16dB；对白段只抬 1–2dB |
| **第二集换脸了** | 重新跑了 `char-gen` | 用 `cast` 共享库；`episode-new` 会直接继承 |
| **文件夹里全是临时文件** | 抽帧/转写产物没清 | 交付前删 `_p_*`、`_q_*`、`_test_*`、`qa/` |

## 详细资料

| 文件 | 内容 |
|---|---|
| **`references/full_pipeline.md`** | **主作业手册**：15 个阶段的命令、字段、验收门、踩坑与验证命令 |
| `providers/agnes.md` | 视频/图片/文本三套 API 的完整参数、错误码、实测结论 |
| `references/screenplay.md` | 编剧方法：场景写法、动作、微表情、对白、口型、镜头语言 |
| `references/shot_schema.md` | 镜头表字段、可拍性规则、动作估时 |
| `references/story_design.md` | 为什么 AI 写的剧本没逻辑：logline / 情绪曲线 / 母题回环 |
| `references/camera_setups.md` | 三机位法、轴线、越轴症状、分镜自查清单 |
| `references/prompt_template.md` | 首帧图与视频提示词模板（含对白口型写法） |
