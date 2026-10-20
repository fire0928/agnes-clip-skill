# Agnes Clip · 一句话到成片

把「一句话创意」变成一条**有场景、有对白、会说话**的竖屏短剧。

视频走云端算力，不占本地显卡。**全程不需要你手动切流程**，但每一步都留了验收门 —— 出问题能立刻定位到是哪一环。

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
| **配乐** | 配乐模型和授权 |
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

## 完整工作流（15 步）

| # | 阶段 | 命令 | 产出 | 验收门 |
|---|---|---|---|---|
| 0 | 立项 | `init` | `project.json` | `status` 不报错 |
| 1 | 剧本骨架 | `story`（建议手改） | `script/story.md` | 有高低点、母题回环、做过删一镜测试 |
| 2 | 镜头表 | 手写 `shots.json` | 全片字段表 | 每镜有动作、有布景、双人镜有人数 |
| 3 | 角色 | `char-gen` / `char-add` | `assets/characters/` | **亲眼看定妆图**，脸不能撞 |
| 4 | 道具 | `prop-gen` | `assets/props/` | 只建近景看得清的 |
| 5 | 场景板 | `scene-gen` | `assets/scenes/` | 同场景各机位墙和家具一致 |
| 6 | 首帧 | `frame` | `frames/S*.jpg` | 人数对、无多余人、左右站位对 |
| 7 | 视频 | `video --wait` | `clips/S*.mp4` | 段数 = 镜数 |
| 8 | 质检 | 抽帧 + 音轨转写 | `qa/` | 台词真念了、没穿帮、没跳轴 |
| 9 | 配乐 | `music` → `music-ui` | `audio/bgm.mp3` | loudnorm 归一化、时长够 |
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
$AC char-gen <项目目录> --name 小林 --desc "..."   # 角色定妆
$AC prop-gen <项目目录> --name 药盒 --desc "..."   # 道具图
$AC scene-gen <项目目录>                # 场景板
$AC frame <项目目录> --dry-run          # 先看提示词
$AC frame <项目目录>                    # 出首帧
$AC video <项目目录> --wait             # 出视频
$AC video <项目目录> --only S07 --wait  # 单镜重跑
$AC voice <项目目录>                    # 配音
$AC music <项目目录>                    # 配乐
$AC music-ui --dir <项目目录>            # 配乐台
$AC assemble <项目目录> --subs --voice  # 合成
$AC audit <项目目录>                    # 审计报告
$AC status <项目目录>                   # 进度
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
│   ├── characters/<名>/face_ref.jpg   角色定妆图
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
├── providers/agnes.md      Agnes 平台说明
└── scripts/
    ├── ac.py               主程序（所有命令都在这）
    ├── sfx.py              音效处理
    └── music_ui.html       配乐台页面
```

---

## 许可与免责

- Agnes 平台的调用需要你自己的 API Key，费用走你自己的账号。
- 生成的图片/视频版权归属请遵循所用平台的条款。
- 本 skill 是工具封装，成片质量取决于你给的创意和验收是否认真。
