# Agnes Clip · 一句话到成片

把「一句话创意」变成一条**有场景、有对白、会说话**的竖屏短剧。

视频走云端算力，不占本地显卡。**全程不需要你手动切流程**，但每一步都留了验收门 —— 出问题能立刻定位到是哪一环。

> 当前版本 **v1.6.1**：新增 GitHub 一键同步（push/pull/check），配乐支持带唱词与幂等跳过，角色与道具生成加幂等守卫（不再重复烧额度），修 ComfyUI Basic Auth 不生效。

---

## 三步装完就能用

### 第 1 步：装 skill

把整个 `agnes-clip-平哥分享版` 文件夹放进下面任意一个位置：

| 位置 | 作用范围 |
|---|---|
| `~/.workbuddy/skills/` | 这台电脑的所有项目都能用（推荐） |
| `<项目>/.workbuddy/skills/` | 只有这个项目能用，可分享给同事 |

Windows 实际路径就是 `C:\Users\<你的用户名>\.workbuddy\skills\`。

装完**重启一下 WorkBuddy**。

### 第 2 步：填密钥

在对话框里直接说：

> 用 agnes-clip skill 帮我配置一下

或者手动跑（Python 3.13）：

```bash
python ~/.workbuddy/skills/agnes-clip-平哥分享版/scripts/ac.py setup
```

它会逐项问你：Agnes 端点、Agnes key、视频模型、推理模型、生图模型……**直接回车就是保留原值**，所以可以只填你缺的那几项。

密钥最终存在 `~/.workbuddy/agnes-clip.json`（这个文件不要外传）。

### 第 3 步：开工

```
/做一条片子 一只不肯死的猫在雨里等了主人三年
```

或者直接说「用 agnes-clip 做一个催泪短剧，主题是 XXX」——AI 会加载这个 skill 走完全流程。

---

## 快捷指令（斜杠命令）

装完 skill 后，**建议先跑一次 `/装快捷指令`**，它会把下面这些命令复制到 WorkBuddy 的命令目录，之后在对话框输入 `/` 就能看到：

| 命令 | 干什么 | 什么时候用 |
|---|---|---|
| `/配置` | 打开配置界面（7 个 TAB） | 要改密钥、换模型、换出图通道 |
| `/出图通道` | 给单个项目选出一条图通道 | 每个新片子开工前 |
| `/片子状态` | 看项目进度到哪一步 | 不知道下一步该干啥时 |
| `/做一条片子` | 从创意一路做到成片 | 开工 |
| `/配乐台` | 试听配乐、逐镜调音量 | 精修阶段 |
| `/装快捷指令` | 一次性装好上面这些命令 | 刚装完 skill 时 |

> 复制完需要**重启 WorkBuddy** 才会出现在 `/` 列表里。

---

## 配置界面怎么用

`/配置` 会在本机起一个网页（默认 `http://127.0.0.1:8765/`），自动打开浏览器。

**注意**：这是一个后台常驻进程，**启动它的那个终端窗口不能关**，关了页面就断。

页面分 7 个 TAB：

| TAB | 管什么 |
|---|---|
| **总览** | 6 条通道的模型 / 端点 / Key 一张表看完 |
| **生图** | 切 Agnes / GPT Image / 自定义 OpenAI 兼容通道 |
| **推理编剧** | 写剧本用的模型和端点 |
| **生视频** | 视频模型、并发数、时长 |
| **配音** | 音色映射、语速 |
| **配乐** | 通道二选一（ComfyUI / 火山引擎）+ 各自参数、默认时长、默认提示词 |
| **系统** | 其它杂项 |

改完点「保存配置」写进全局配置，立刻生效。

### 出图通道：全局 vs 项目

**全局**（配置页「生图」TAB）影响所有没单独指定的项目。
**项目级**（`/出图通道`）只影响这一个项目，写在该项目的 `project.json` 里。

推荐做法：**每个项目开工前用 `/出图通道` 选一次**，这样同一个 skill 能同时跑 Agnes 和 GPT Image 两条线，不用反复改全局。

### 第三方中转（apibase.cc 之类）报 403？

**已经处理好了，不用管。** 这类中转会用 Cloudflare 检查浏览器签名，Python 默认发过去会被拦（报 `403 error code 1010`）。

本 skill 发请求时**自动带完整浏览器头**（User-Agent、Accept、Accept-Language、Sec-CH-UA、Origin、Referer 全部按目标域名拼），所以直接用就行。

如果你自己改了 `scripts/ac.py` 里的 `BROWSER_HEADERS` 又开始报 403，把那几行恢复回去就行。

---

## 配乐：两条通道，按有没有显卡选

配乐是本 skill 里唯一「必须有算力」的一环。现在有两条路，出口都是 `audio/bgm.mp3`，后面的逐镜调音量、配乐台、合成都一模一样。

| 通道 | 走什么 | 什么时候用 | 成本 |
|---|---|---|---|
| **ComfyUI**（默认） | 本地/远程 ComfyUI + MiniMax Music3，一条片子一次出完 | 有显卡、卡空着 | 0（自己的电） |
| **火山引擎** | AI 音乐生成（豆包音乐模型）OpenAPI | 没卡、卡在排队、赶时间 | **0.002 元/秒**，100 秒约两毛 |

### 切到火山只要三步

1. 去火山控制台右上角「密钥管理」新建一对 **AccessKey / SecretKey**（建议用子账号），顺便在「AI 音乐生成」控制台把**按时长后付费**开关打开。
2. 打开 `/配置` → 「配乐」TAB → 通道选 **火山引擎** → 填 AK/SK → 点**测试连接**（显示「签名通过」就对了）。
3. 照常 `music` 或 `auto --music`。

只想试一次、不改全局：

```bash
python scripts/ac.py music <项目目录> --provider volc --duration 104 --caption "felt piano, low strings, 58bpm, minor"
```

### 三件必须先知道的事

- **纯音乐单次最多 60 秒**。片子更长时脚本会自动切段（每段留 2 秒交叉淡化重叠）再拼回一条，最后统一做响度归一化。代价是段与段之间能听出"换段"——**能用 ComfyUI 一次出整条，就别分段**。
- **两个计费入口不互通**：`GenBGMForTime`（按时长后付费）和 `GenBGM`（套餐包）。本 skill 默认走前者。走错会报 `200028 没有可用资源包`。
- **描述用中文写具体**。v5.0 不再支持"曲风/情绪/乐器"这类打勾选项，全靠一段文字；写"温暖治愈"这种通用词容易撞版权校验（`50000001`），写清乐器、节奏、场景、情绪反而稳。

报错对照表、签名细节、接口字段都在 [`providers/volc_music.md`](providers/volc_music.md)。

---

## 完整工作流（15 步）

| # | 阶段 | 命令 | 产出 | 验收门 |
|---|---|---|---|---|
| 0 | 立项 | `init` | `project.json` | `status` 不报错 |
| 1 | 剧本骨架 | `story`（建议手改） | `script/story.md` | 有高低点、母题回环、做过删一镜测试 |
| 2 | 镜头表 | 手写 `shots.json` | 全片字段表 | 每镜有动作、有布景、双人镜有人数 |
| 3 | 角色 | `char-gen` / `char-add` | `assets/characters/` | **亲眼看定妆图**，脸不能撞；设定卡每一格都得是同一个人 |
| 4 | 道具 | `prop-gen` | `assets/props/` | 只建近景看得清的 |
| 5 | 场景板 | `scene-gen` | `assets/scenes/` | 同场景各机位墙和家具一致 |
| 6 | 首帧 | `frame` | `frames/S*.jpg` | 人数对、无多余人、左右站位对 |
| 7 | 视频 | `video --wait` | `clips/S*.mp4` | 段数 = 镜数 |
| 8 | 质检 | 抽帧 + 音轨转写 | `qa/` | 台词真念了、没穿帮、没跳轴 |
| 9 | 配乐 | `music` → `music-ui` | `audio/bgm.mp3` | loudnorm 归一化、时长够；火山通道 >60s 自动分段 |
| 10 | 音效 | 真素材 | `audio/sfx/` | 落点卡转折处，峰值 ≈ −16dB |
| 11 | 转场 | 写 `shot.x` | 合成时生效 | 硬切统一 0.1s |
| 12 | 字幕 | 写 `shot.subs` | `out/_subs_shots.ass` | 每句一排、≤14 字 |
| 13 | 合成 | `assemble --subs --voice` | `out/final.mp4` | 总时长没被截断 |
| 14 | 验收 | `audit` | `AUDIT.md` | 响度 −16~−17 LUFS |
| 15 | 交付 | 复制成 `out/<片名>.mp4` | 成片 | 清掉临时文件 |

**人工介入只有五处**：剧本定稿、场景板验收、首帧验收、质检、精修。其余都能批量跑。

---

## 常用命令速查

```bash
AC="python ~/.workbuddy/skills/agnes-clip-平哥分享版/scripts/ac.py"

$AC setup                              # 首次配置密钥
$AC config-ui                          # 打开配置界面
$AC pick-image <项目目录> --channel gpt-image   # 换出图通道
$AC init <项目目录> --title "片名"      # 立项
$AC char-gen <项目目录> --name 小林 --desc "..."   # 角色定妆（正脸 + 设定卡）
$AC char-gen <项目目录> --name 小林 --card-style turnaround   # 换设定卡版式
$AC char-gen <项目目录> --name 小林 --no-card         # 只出正脸
$AC char-gen <项目目录> --name 小林 --channel gpt-image # 指定通道（两段必须同通道）
$AC views <项目目录>                          # 从设定卡重切角度参考图
$AC prop-gen <项目目录> --name 药盒 --desc "..."   # 道具图
$AC scene-gen <项目目录>                # 场景板
$AC frame <项目目录> --dry-run          # 先看提示词
$AC frame <项目目录>                    # 出首帧
$AC video <项目目录> --wait             # 出视频
$AC video <项目目录> --only S07 --wait  # 单镜重跑
$AC voice <项目目录>                    # 配音（豆包 TTS，默认按镜头时长自动适配）
$AC voice <项目目录> --no-fit          # 关掉时长适配
$AC music <项目目录>                    # 配乐（走配置里的通道）
$AC music <项目目录> --provider volc --duration 104   # 临时改走火山引擎
$AC music-ui --dir <项目目录>            # 配乐台
$AC assemble <项目目录> --subs --voice  # 合成
$AC audit <项目目录>                    # 审计报告
$AC status <项目目录>                   # 进度
$AC fetch <项目目录>                    # 续查已提交的视频任务并下载
$AC recall <项目目录>                  # 把别集的片段剪成本集的「回忆」镜头，零额度
$AC cast list|init|push                 # 多集共享角色库
$AC episode-new <新集目录>               # 同系列新一集，角色不换脸
```

---

## 项目目录长什么样

```
projects/我的片子/
├── project.json          项目配置（含 image_channel 出图通道）
├── script/
│   ├── story.md          人读剧本
│   └── shots.json        机器读镜头表（驱动全部后续步骤）
├── assets/
│   ├── characters/<名>/face_ref.jpg   角色正脸（首帧锁脸锚点，必须用它）
│   ├── characters/<名>/char_card.jpg  多格设定稿（大头+三视图+表情+细节，给人看）
│   ├── characters/<名>/views/{front,side,back}.jpg  从设定卡裁的角度图，首帧按机位自动取
│   ├── props/*.jpg                    道具图
│   └── scenes/<场景>__<机位>.jpg      场景板
├── frames/S01.jpg ...    逐镜首帧
├── clips/S01.mp4 ...     逐镜视频
├── audio/                bgm.mp3 + sfx/*.wav
├── out/                  成片 + 字幕
└── AUDIT.md              验收报告
```

---

## 环境要求

- **Python 3.13**（`3.14.3` 那个环境已损坏，务必用 3.13）
- **ffmpeg**（合成、响度归一化、转场都要它）
- **ffprobe**（质检抽帧要它）
- 依赖：`requests`、`Pillow`、`imageio-ffmpeg`、`edge-tts`

装依赖：

```bash
python -m pip install requests Pillow imageio-ffmpeg edge-tts
```

ffmpeg 没装的话，脚本会自动用 `imageio-ffmpeg` 自带的那个；但系统里装了 ffmpeg 更好（能单独做响度处理）。

---

## 常见问题

**Q：配置页面打不开 / 点了没反应**
A：三个原因，按顺序查——
1. 端口被占：换个端口启动 `config-ui --port 8899`
2. 浏览器没自动弹：手动访问命令行里打印的那个地址
3. 页面白屏或按钮点不动：按 F12 看控制台有没有 JS 报错

**Q：出图报 403**
A：如果是第三方中转（apibase.cc 之类），**本 skill 已经自动带完整浏览器头**，正常不会遇到。真报 403 就检查是不是改过 `scripts/ac.py` 里的 `BROWSER_HEADERS`。
另外 `gpt-image-2` 这个模型在中转上可能没有可用账号（报 503 "No available compatible accounts"），换成 `gpt-image-2.5-flare` 或 `gpt-image-2.5-sunburst`。

**Q：视频任务提交失败 / 一直 pending**
A：Agnes 账号有频率限制（**30 秒一次、最多 3 路并发**）。用 `fetch` 命令续查已提交的任务：
```bash
$AC fetch <项目目录>
```

**Q：合成后没声音 / 片子被截断**
A：转场 xfade 的 `duration` 不能短于一帧。24fps 下 `0.04s` 会让整条音轨静默截断。**硬切统一用 `0.1s`**。

**Q：成片太小声**
A：目标响度是 **−16 ~ −17 LUFS**。检查：
```bash
ffmpeg -i out/final.mp4 -af ebur128=peak=true -f null -
ffmpeg -i audio/bgm.mp3 -af loudnorm=I=-23:TP=-2:LRA=7 fixed.mp3
```

**Q：火山配乐报 `200028`**
A：不是代码问题，是账号侧。两个原因：① 控制台没打开「按时长后付费」；② 调错了入口——本 skill 默认 `GenBGMForTime`（后付费），如果你买的是套餐包要改成 `GenBGM`，两个入口额度不互通。

**Q：火山配乐报 `50000001`**
A：版权/相似度校验没过。把提示词写具体（乐器 + 节奏 + 情绪 + 场景，用中文），或在配置里打开 `rewrite`（`EnableInputRewrite`）。提示词只写"温暖治愈的钢琴"这种通用描述，命中率最高。

**Q：火山配乐超过 60 秒怎么出的**
A：脚本按公式算出段数（102.6 秒 → 2 段 × 52.3 秒），逐段生成后交叉淡化 2 秒拼回一条。**段与段之间会有"换段"感**，这是接口 60 秒上限带来的，不是 bug；能一次出整条就别分段。

**Q：字幕和台词对不上**
A：用 `shot.subs` 逐句写（相对时间 `t`/`d`），比 VAD 自动字幕准得多。合成时加 `--subs`。

**Q：同一系列第 2 集人物换脸了**
A：不要重新 `char-gen`。用共享角色库：
```bash
$AC cast init        # 首次建立共享库
$AC cast push <集目录>   # 把本集角色推进共享库
$AC episode-new <新集目录>  # 新建集，自动复用
```

---

## 目录结构

```
agnes-clip-平哥分享版/
├── SKILL.md                主规则与硬约束（AI 读这个）
├── README.md               本文件，给人看
├── commands/               斜杠快捷指令
├── references/
│   ├── full_pipeline.md    15 阶段完整作业手册
│   ├── pipeline.md         管线参数说明
│   ├── shot_schema.md      镜头表字段定义
│   ├── screenplay.md       剧本写法
│   ├── story_design.md     故事结构设计
│   ├── prompt_template.md  提示词模板
│   └── camera_setups.md    12 种运镜语言
├── providers/
│   ├── agnes.md            Agnes 平台说明
│   └── volc_music.md       火山引擎音乐生成（签名 / 接口 / 错误码）
└── scripts/
    ├── ac.py               主程序（所有命令都在这）
    ├── sfx.py              音效合成库
    └── music_ui.html       配乐台页面
```

---

## 版本记录

### v1.6.1（2026-10-21）

- **GitHub 一键同步**：`tools/git_sync.py` 四个子命令 ——
  `push`（安全体检 → 打包 → 提交 → 打 tag → 推）、`pull`（拉远端最新）、
  `check`（只看有没有新版本）、`status`（本地/远端对照）。
  `push` 前自动全库扫密钥、本机路径、缓存文件，**有问题直接中止不推**。
- **新增 `tools/create_repo.py`**：给新 skill 一键建 GitHub 仓库（只需一个带 repo 权限的 token）。

### v1.6.0（2026-10-21）

- **修 ComfyUI Basic Auth 不生效**：配了 `music.auth` 但提交 `/prompt` 时没带头，配了认证的 ComfyUI 一定 401。现在提交、轮询、下载三处都带。
- **角色与道具生成加幂等守卫**：`char-gen` / `prop-gen` 之前每次跑都重新出图（**重复烧额度**）。
  现在资产已存在且描述/服装/通道没变就跳过，要重做加 `--force`。
- **配乐支持带唱词**：`music --lyrics "..."` 可以生成有唱词的歌；不传就是纯器乐。
  同 seed 同长度的配乐已存在就跳过（不再重复生成）。
- **修 `frame_upload` 的命令注入风险**：改成 `shlex.split` + `shell=False` 执行，不再走 shell。
- **补齐配置分区**：`image` / `banana` / `voices.doubao` / `video.tiers` 等原先只能手写 JSON，现在进 `DEFAULT_CFG`。
- **补四篇方法论文档**：`camera_language`（12 运镜 + 6 组合公式）、`micro_expression`（微表情库）、
  `face_lock`（锁脸与尾帧桥接）、`troubleshooting`（崩坏排查表）。
- **接缝报告补「最跳 6 处」摘要**（原来是空循环）。

### v1.5.0（2026-10-21）

- **视频提交支持分档降级**：按 `video.tiers` 的优先级依次尝试（订阅额度 → 免费额度 → 付费），
  某一档排上了就记住它，后续镜头优先走这一档，不重复撞墙。
- **付费档默认需要人工确认**：免费通道都排不上时，不会偷偷降级去烧钱，而是停下来提示。
  要放行就在本次命令加 `--allow-paid`，或把 `video.paid_requires_confirm` 设为 false。
- **区分 429 与 503**：429（速率限制）退避重试，503（队列满）在免费档上直接换下一档——
  队列满时死磕没有意义，只会白等。
- 配套开关：`video.free_tier_max_attempts`（免费档单次最多试几轮，默认 1）、
  `video.paid_requires_confirm`（付费档是否需确认，默认确认）。

### v1.2.0（2026-10-20）

- **配音换成豆包 TTS**：`voice` 走火山引擎语音合成，中文音色更自然；按角色自动分配音色，支持语速与音调微调。
- **配音按镜头时长自动适配**：`voice` 默认开启「超镜长自动提语速」——台词念完镜头还没结束就自动提速；提速后仍超长才裁掉句首句尾多余的停顿。台词不会被下个镜头切断，加 `--no-fit` 可关掉。
- **新增 `recall` 命令**：把别集（通常是第 1 集）的片段剪成本集的「回忆」镜头——支持指定入点与时长、变速、调色（暖/冷）、自动去原声。**不调 Agnes、不花额度**，系列剧做闪回最省的一招。镜头表里写 `"reuse": {"from": "../clips/S01.mp4", "in": 0.0, "dur": 5.0, "speed": 0.85, "grade": "warm"}` 即可。
- **合成阶段自动做响度归一**：`assemble` 结束会跑一次 loudnorm（目标 −16 LUFS、峰值 −1.5 dBTP）并打印实测值，取代以前要手工跑 ffmpeg 检查的做法。
- **叠化转场自动统一画面尺寸**：同一片里混了 flash（704×1280）和付费版（720×1280）时，转场前按出现最多的尺寸统一缩放裁切，不再报 `size does not match`。
- 文档补充两条排查项：叠化尺寸不一致、flash 额度耗尽导致持续 429/503。

### v1.1.0（2026-10-20）

- **配乐新增火山引擎通道**：`music --provider volc`，无显卡也能出配乐（0.002 元/秒）。含 V4 签名实现、提交/轮询、JSON 转 WAV、超 60 秒自动切段 + `acrossfade` 拼接 + 统一 loudnorm。
- 配置界面「配乐」TAB 拆成「通道 / ComfyUI 参数 / 火山参数 / 通用」四块，切换通道自动收起无关项；「测试连接」按通道分流（火山用 `QuerySong` 空任务验签名）。
- `setup` 支持 `--music-provider` / `--volc-ak` / `--volc-sk`，交互式向导也会问。
- 新增 `providers/volc_music.md`：接口字段、签名推导（中间密钥二进制）、错误码对照、分段策略。

### v1.0.0（2026-10-20 之前）

- 首个可分发版本：15 阶段全流程、共享角色库、配乐台、音效合成、转场、逐句字幕。

---

## 许可与免责

- Agnes 平台的调用需要你自己的 API Key，费用走你自己的账号。
- 生成的图片/视频版权归属请遵循所用平台的条款。
- 本 skill 是工具封装，成片质量取决于你给的创意和验收是否认真。

---

## 关于我们

**广州爱莱客智能科技有限公司**

| | |
|---|---|
| 联系人 | 平哥 |
| 邮箱 | 4530375@qq.com |
| 产品线 | AI 视频生成、达人建联、数字员工盒子（ilikeai.cc / aibox.ilikeai.cc） |

业务合作、技术咨询、定制开发欢迎来信。
