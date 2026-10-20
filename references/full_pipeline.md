# 全流程：一条视频从想法到成片的每一步

这是本 skill 的主干作业流程。**按顺序走，每一步都有产物和验收门**；上一关不过，不进下一关。
单条竖屏剧情片（20 镜 / 2–3 分钟）实测耗时约 3–4 小时，其中视频生成排队占 2/3。

```
立项 → 剧本定稿 → 镜头表 → 角色 → 道具 → 场景板 → 首帧 → 视频 → 质检
     → 配乐 → 音效 → 转场 → 字幕 → 合成 → 验收 → 交付
```

每个阶段都能单独重跑，不用从头再来。`auto` 只覆盖到「首帧 + 视频 + 合成」，
**转场、音效、逐句字幕、配乐台属于精修段，必须在 auto 之后单独做**（本片实测：auto 出的版本只能算毛片）。

---

## 阶段 0 · 立项

```bash
python scripts/ac.py init "<项目目录>" --title "片名"
```

产物：`project.json`、`script/shots.json`（空）、目录骨架。

`project.json` 是**创作参数**，不是运行参数（并发、轮询、超时都在全局 `~/.workbuddy/agnes-clip.json`）。
常用可写字段：

| 字段 | 作用 | 不写会怎样 |
|---|---|---|
| `title` | 片名 | 用目录名 |
| `scene_anchor` | 场景风格锚，可填 preset 名（`cn_noodle_shop` / `cn_apartment` / `cn_cafe`）或整句英文 | 用中性锚「真实中国场景」，不预设店铺类型 |
| `cast_dir` | 共享角色库路径（相对项目根或绝对） | 本集独立一套角色，不与其它集共用 |
| `agnes.seconds` | 默认单镜时长 | `"8"` |

> 🔴 **历史坑**：旧版本把「中式老街面馆」写死成全局场景锚，导致公寓、咖啡厅、公交站的场景板
> 全被塞进面锅、红塑料凳、菜单牌，首帧跟着一起错。现在默认锚只保留「真实中国场景」这一层，
> 具体气质靠 `scene.set` 陈设清单 + 场景描述来定。要面馆气质就显式写 `"scene_anchor": "cn_noodle_shop"`。

**验收**：`ac.py status "<dir>"` 能列出目录，不报错。

---

## 阶段 1 · 剧本（必须用户点头，不许抢跑）

```bash
python scripts/ac.py story "<dir>" --idea "一句话创意" --shots 8
```

但**推荐手写**：先让模型出骨架，人工改到满意再落 `script/shots.json`。
自动生成的剧本常见病是「十镜十个漂亮画面，没有欲望、没有阻碍、没有变化」。

必须有的六件东西（缺一件不写分镜）：

1. **logline**：谁 + 想要什么 + 遇到什么阻碍 + 最后变成什么
2. **人物心理档案**：性格成因、防御方式、说反话的模式（写进 `story.md`，不写进 shots）
3. **微表情系统**：3–7 个可复用的具体动作（例：压住的笑 = 嘴角先提又压平；他不是看你，是看你身后）
4. **母题**：一个物件或动作贯穿全片，首尾各出现一次（手机扣着 → 手机朝上）
5. **情绪曲线**：每镜一个 −5~+5，必须有最高点和最低点，禁止连续三镜同值
6. **分镜表**：每镜回答四问——作用（推进/停顿/转折）· 因为上一镜____所以这一镜____ · 具体动作 · 观众该想什么

**验收（删一镜测试）**：随便删掉一镜，故事不残缺 → 那镜是废镜，重写。

产物：`script/story.md`（人读）+ `script/shots.json`（机器读）。
`story.md` 要有：logline、人物、母题、情绪曲线、场景机位表、逐镜正文。

---

## 阶段 2 · 镜头表（shifts.json 全字段）

这一份文件驱动后面所有步骤，字段写全了，后面就少返工。

```jsonc
{
  "title": "老位置",
  "logline": "…",
  "characters": [
    {"name": "girl", "desc": "28岁女性，齐肩黑发，浅灰蓝针织开衫",
     "desc_en": "…", "outfit_en": "light gray-blue knit cardigan, white tee, dark jeans",
     "voice": "zh-CN-XiaoxiaoNeural"}
  ],
  "props": [{"name": "soymilk", "desc": "一杯热豆浆", "desc_en": "…"}],
  "shots": [
    {
      "id": "S01",
      "duration": 10,
      "scene": {"id": "居民楼楼下", "time": "深夜", "place": "居民楼楼下", "weather": "无雨",
                "light": "暖黄路灯", "interior": false,
                "set": ["a Chinese residential building entrance with a steel security door", "…"],
                "angles": {"wide": "wide street-level view, building entrance and sidewalk"}},
      "angle": "wide",
      "char": "girl",
      "cast": ["girl", "chenyu"],
      "faces": ["girl"],
      "action": "她双手插兜走在回楼路上，被叫住",
      "micro": "瞳孔先缩一下，肩膀后仰半寸；接杯时指尖避开他手指",
      "speaker": "chenyu",
      "line": "趁热喝，不加糖。",
      "frame": {"mode": "swap", "prompt": "English still prompt…"},
      "video_prompt": "English video prompt… speaks in Mandarin with precise lip-sync: \"…\"",
      "x": {"kind": "fade", "dur": 0.8},
      "subs": [{"t": 0.19, "d": 1.40, "text": "趁热喝，不加糖。"}],
      "sfx": [{"at": 6.60, "kind": "sip", "gain": -13}],
      "bgm": 0.26,
      "tighten": false
    }
  ]
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | ✅ | `S01` 递增，决定文件名与排序 |
| `duration` | ✅ | 4–12 秒整数；有台词按 `字数/4.2 + 0.9`，封顶 8 |
| `scene.id` | ✅ | 同场景必须同名，场景板与陈设按它分组 |
| `scene.set` | ✅ | 5–8 条具体陈设（材质+颜色）。**不写就会被模型自由发挥** |
| `scene.angles` | ✅ | 机位名 → 英文机位描述；同场景只换机位不换布景 |
| `scene.interior` | 建议 | `false` 时不再强加「这是室内」子句（室外戏必须写） |
| `char` | ✅ | 主角（用于取脸）；空镜填 `null` 且 `frame.mode="plate"` |
| `cast` | 双人镜必填 | 画面里**所有人**，人数锁和参考图都按它来 |
| `faces` | 过肩镜必填 | 只喂露脸的人；前景背对镜头的人别喂，否则会凭空多画一个人 |
| `line` / `speaker` | 有对白 | ≤18 字；`VO` 表示旁白 |
| `frame.mode` | ✅ | `source`（用定妆图）/ `swap`（按提示词换景换装）/ `plate`（空镜裁场景板） |
| `video_prompt` | ✅ | 必须含台词原句 + 口型指令 + 2–3 段运镜 + 环境声 |
| `link: "prev"` | 可选 | 接力上一镜尾帧。**只在同场景同机位用，且不许连传三段** |
| `x` | 精修 | 进入本镜的转场：`{"kind":"fade","dur":0.8}`，`cut` 表示硬切 |
| `subs` | 精修 | 本镜内**相对**时间的逐句字幕；超过 14 字在标点处拆两条 |
| `sfx` | 精修 | `{"at": 相对秒, "kind": 音效名, "gain": dB}` |
| `bgm` | 精修 | 0–1，本镜配乐音量；不写沿用上一镜 |
| `tighten` | 精修 | `false` = 不按人声裁尾，保留台词后的表演（关键镜必关） |
| `tts` | 可选 | `true` = 这一镜只混 TTS 配音（模型没出声或念糊时用） |

> `subs` / `sfx` / `x` / `bgm` 都是**相对本镜起点**的时间，合成时会跟转场一起重排到绝对时间轴。
> 千万别自己写绝对秒数——加了转场后总时长会变，写死就会全片错位。

**验收**：镜头时长加起来在目标区间（2–3 分钟 ≈ 150–175 秒）；每镜都有具体动作；没有连续两镜「站着看」。

---

## 阶段 3 · 角色（脸是全片的地基）

```bash
python scripts/ac.py char-gen "<dir>" --name girl          # 从 shots.json 读描述与服装
python scripts/ac.py char-add "<dir>" "C:/photos/me.jpg" --name hero   # 真人照片锁脸
```

产物：`assets/characters/<name>/` 下 `source.jpg` + `face_ref.jpg`（+ `turnaround.jpg` 三视图）。

规则：
- `char-gen` 的提示词里**必须带 `outfit_en`**，否则定妆图穿的和你片里要穿的不是一套，首帧会照抄错衣服。
- 生成后**亲眼看一下** `face_ref.jpg`：脸型、年龄、气质是否贴人设。这张图错了，后面 20 镜全错。
- 主要人物一律 `East Asian Chinese`（代码会补），否则英文角色名容易出欧美脸。

### 一集接一集：人物形象复用

同一系列做第 2、3 集时，**不要重新生成角色**——重生成就是换演员。用共享角色库：

```bash
# 方式一：一条命令新建第 2 集，自动把第 1 集的角色收进共享库并绑定
python scripts/ac.py episode-new "<第1集目录>" --name ep02 --title "第二集"

# 如果第 1 集本身就是项目根（没有 ep01/ 这一层），加 --inside，新集落在它里面：
python scripts/ac.py episode-new "<第1集目录>" --name ep02 --title "第二集" --inside

# 方式二：手动
python scripts/ac.py cast "<第1集目录>" init      # 项目内建 cast/ 并写 cast_dir
python scripts/ac.py cast "<第1集目录>" push --name girl   # 收入共享库（--all 收全部）
python scripts/ac.py cast "<第2集目录>" list      # 看本集 / 共享库各有哪些角色
```

目录长这样：

```
我的系列/
├── cast/            # 共享角色库：girl / chenyu 的 face_ref、source、turnaround
├── ep01/            # project.json 无 cast_dir
└── ep02/            # project.json → "cast_dir": "../cast"
```

- 读取一律「本集优先，其次共享库」：`ep02` 自己 `assets/characters/` 是空的也能直接用 `girl`、`chenyu`。
- 写入（`char-gen` / `char-add`）永远写本集，不会污染共享库；要收进库得显式 `cast push`。
- `ep02` 的首帧、视频、质检全部自动读共享库的脸，**不会重新生成、也不会变脸**。
- 换装/换年龄段（比如第 2 集过去了五年）要新建一个角色名（`girl_5y`），别覆盖 `girl`。

**验收**：`cast <ep02> list` 里目标角色标「共享」；`frame --dry-run` 的「参考图 N 张」含人脸。

---

## 阶段 4 · 道具

```bash
python scripts/ac.py prop-gen "<dir>" --name soymilk
```

只做**近景会被看清**的道具：会反复出现、要被手指碰到、要作为母题的。
背景里的杯子碗碟不要单独建设道具，交给场景板。

---

## 阶段 5 · 场景板（按「场景 × 机位」，不按镜头）

```bash
python scripts/ac.py scene-gen "<dir>" [--force]
```

一个场景先定陈设清单（`scene.set`）和机位表（`scene.angles`），每个机位一张空板，同机位所有镜头共用。

**验收（必看）**：逐张看 7–8 张板，确认三件事——① 是这个地点（不是面馆/居酒屋）；② 没有剧本里没有的道具；③ 同一场景不同机位的墙、家具、窗位置一致。

> 这一步偷懒，后面 20 镜全部换场景。发现板错了就 `--force` 重出，别指望首帧能纠正。

---

## 阶段 6 · 首帧

```bash
python scripts/ac.py frame "<dir>" --only S01 --dry-run --force   # 先看提示词，不花钱
python scripts/ac.py frame "<dir>" --force                        # 全量
```

代码强制四件事（见 SKILL.md「首帧提示词的四个硬保证」）：锁人脸、带参考图、人数锁死、人物位置。

自检看三个数字：

| 看什么 | 应该是什么 |
|---|---|
| `Headcount in this frame is exactly N` | N = `cast` 人数（空镜 0） |
| `参考图 N 张：人脸 X + 场景 1` | 双人镜 3 张、单人 2 张、过肩按 `faces` 收窄 |
| 提示词里有没有 `left third` / `right third` | 双人镜必须有，缺了会跳轴 |

**空镜**：`char: null` + `frame.mode: "plate"`，直接用场景板裁切当首帧。

### 空镜也要有戏：用 `gen` 模式生成「空镜 + 关键道具」

`plate` 模式只是把场景板裁一刀，**桌上是空的、道具不会自己出现**。
如果某个空镜承担叙事任务（结尾的"两副碗筷都盛满了"是全片母题的落点），
裁切出来的空镜等于母题落空。这时改用 `gen` 模式：

```json
"frame": {
  "mode": "gen",
  "prompt": "Interior of ... On the square table in the foreground sit TWO complete place settings, clearly visible from above: two white ceramic bowls, BOTH of them filled with hot porridge ... There is nobody in this room: no person, no face, no photograph of a person on the wall ..."
}
```

`gen` 模式与 `swap` 的区别：

| | `gen` | `swap` |
|---|---|---|
| 人物 | 无（不锁脸、不加人物白名单） | 有 |
| 参考图 | 只喂场景板 | 人脸 + 场景板 |
| 用途 | 空镜但要摆特定道具 | 有人物的镜头 |
| 人数 | 0 | `cast` 人数 |

场景板仍会当参考喂进去，保证布景/光线/陈设和全片一致；
提示词里要**明确写出要出现的道具**（`TWO complete place settings`、`BOTH of them filled`），
并**明确排除不该有的东西**（`no photograph of a person on the wall`）。

> 坑：场景板**旧版本**可能带人像（挂历人像、相框里有人脸）。
> 空镜裁切出来就会穿帮。改用 `gen` 模式能顺手把这类东西排除掉。

**接力**：`link: "prev"` 只在同场景同机位之间用，且**一段只接一次**（S07→S08 可以，S07→S08→S09 不行，会累积漂移）。
跨场景、换机位、跳时间一律独立出首帧。

**验收**：抽 3–5 张关键镜（第一镜、情绪最低点、情绪最高点、结尾）逐张看构图、轴线、服装、人数。

### 首帧提示词自检（出图前先读一遍，别等出完才发现矛盾）

出图慢（每张 1–10 分钟），提示词有矛盾就是白等。生成前先跑一遍 `--dry-run` 读最终提示词，重点看：

| 检查 | 说明 |
|---|---|
| 景别自洽 | 过肩镜写「只露肩、半身」，就**不能**同时写「两人并排、都是从腰往上完整可见」 |
| 人数声明一致 | 前面写 `exactly N`，后面又写 `side by side` 换人，就矛盾了 |
| 站位声明只有一套 | 只能有一套左右描述，出现两套（哪怕意思相同）模型会各画一半 |

**「过肩镜被画成两个人」的典型现场**：提示词前面写「男人背对镜头，只见肩和侧脸」，
后面跟了一句通用兜底「两人并排站在同一张桌子前，两人都完整可见」——
模型为了满足「都完整可见」，会在别处再放一个完整的人，于是同一镜里出现两个同一个人。

**根因在代码兜底逻辑**：`_position_clause` 只在提示词**完全没写左右**时才补站位。
判断"写了没有"如果只认 `on the left`、不认 `in the LEFT third`，
就会在已有站位的提示词后面**再追加一遍**通用站位句，与景别设定打架。

> 已修（本 skill 版本）：`_position_clause` 现在同时认
> `left third` / `right third` / `in the left` / `in the right` / `left third of` 等写法。
> 但**你手写提示词时**仍要保证自洽——代码只管追加，不管你写的内容有没有打架。

**防坑做法**：景别是「过肩」「蹲姿」「俯视背影」这类特殊构图时，
**不要**在提示词里再写「两人并排、完整可见」这种通用兜底句。
写清楚谁在画面哪个位置、露出多少、什么姿势就够了。

---

## 阶段 7 · 视频

```bash
python scripts/ac.py video "<dir>" --wait              # 提交并等（3 路并发，30 秒轮询）
python scripts/ac.py video "<dir>" --only S17 --wait --force   # 单镜重跑
python scripts/ac.py fetch "<dir>"                     # 断线续查，不重复提交
```

- 账号硬限：**3 路并发、轮询 30 秒**。20 镜约 4–6 轮，1–2 小时。
- 单镜偶发失败（云端 5xx / 超时）→ 单独 `--only <id> --wait --force` 重跑，不要全片重来。
- 提交前确认 `clips/_pending.json` 没有残留的旧任务。

**验收**：`ls clips/*.mp4 | wc -l` = 镜头数。

### 视频提示词也要写死四件事（最容易漏）

首帧写对了不等于视频也写对了。**`video_prompt` 是独立字段，管线不会自动继承首帧的约束**。
只写动作、不写约束，模型就会在运动中换位、换脸、多出人。

每个镜头的 `video_prompt` 末尾（`No on-screen text...` 之前）必须自带：

| 约束 | 模板 | 空镜 |
|---|---|---|
| 锁人脸 | `The two faces must stay exactly as in the reference first frame — identical bone structure, identical age, identical hair and clothing, no morphing, no identity drift, no face swap, no beautification, no change of face shape between them and the first frame.` | 不加 |
| 锁脸（单人版） | `The face must stay exactly as in the reference first frame — ...` | 不加 |
| 人数 | `The headcount in this shot is exactly N — no extra people, no third person in the background, no silhouette in the doorway, no figure passing behind, no reflection of another person.` | 不加 |
| 站位 | `both on the same side of the axis, the woman on the left and the man on the right, they never swap sides.` | 不加 |

**轴线是双向的**：剧本定了「A 画左、B 画右」，那**首帧和视频提示词都要写反不得**。
只改首帧不改视频提示词，等于白改——视频阶段照样会换边。
写完用脚本扫一遍两处是否一致：

```bash
python -c "
import json,re
d=json.load(open('script/shots.json',encoding='utf-8'))
for s in d['shots']:
    p=s.get('video_prompt','')
    for sent in re.split(r'(?<=[.]) ', p):
        if 'axis' in sent.lower() and ('left' in sent.lower() or 'right' in sent.lower()):
            print(s['id'], '::', sent.strip()[:120])
"
```

**同框两人的站位顺序要和剧本一致**。举例：母子同框定「母亲画左、儿子画右」，
那首帧和视频提示词都得是 `the woman on the left and the man on the right`——
写成 `the man on the left and the woman on the right` 就是跳轴，模型会把人物换到对面。

**空镜**（`cast: []`）不加锁脸、不加人数——"两张脸保持一致"在没人镜里是自相矛盾的指令。

---

## 阶段 7.5 · 回忆集：把上一集的画面当闪回用

第二集做"回忆/闪回/独白"时，**不要重新生成回忆画面**——重生成就是另一段回忆。
直接剪上一集的片段，做旧成"记忆的样子"，观众才会认出"这是当时那件事"。

```bash
# 1) 镜头表里给回忆镜写 reuse（不写真会去调 Agnes，白花额度）
# 2) 剪出来（不调接口、不花额度，一条 2–3 秒）
python scripts/ac.py recall <本集目录>
python scripts/ac.py recall <本集目录> --dry-run        # 只看每条取哪段、多长
python scripts/ac.py recall <本集目录> --only S04,S09 --force
```

```json
{
  "id": "S04",
  "duration": 5.0,
  "reuse": {"from": "../clips/S01.mp4", "in": 0.0, "dur": 5.0,
            "speed": 1.0, "grade": "warm"}
}
```

| 字段 | 含义 |
|---|---|
| `from` | 相对本集根目录（也吃绝对路径） |
| `in` / `dur` | 源片段入点；`dur` 是**成片要的长度**，不是源片段长度 |
| `speed` | `<1` 放慢（回忆感，0.7–0.9）；`>1` 加快 |
| `grade` | `warm`（温柔回忆）/ `cold`（疼的那几段）/ `neutral` |

调色内置：降饱和 + 柔光 + 颗粒 + 暗角，原声一律去掉——**回忆里只该听见"她现在的声音"**，不该听见当时的现场声。

三条硬规矩：

1. **`dur` 要够装下人声**。回忆片段的长度是剪死的，旁白超了就会压到下一镜去。先跑 `voice`，
   再用配音实际时长反推 `duration`（见阶段 12 的自动排字幕脚本）。
2. **查"烧进去的字"**：抽 6 帧看画面纵向 56%–72% 字幕带。旧片段里如果有模型画上去的台词，
   回忆一露就穿帮（本 skill 已把它写进速查表）。有字就避开那几秒，或推近 1.12 倍把字挤出画外。
3. **同一段不要用两遍**。两条回忆取同一镜的重叠区间，观众会看成"卡了"；
   要两个不同的表演点，就取不重叠的两段（或把其中一段放慢到 0.7 倍，让重复看起来是"回放"）。

`assemble` 不区分新拍和回忆——回忆片段已经是 `clips/<id>.mp4`，走同一条时间轴。

---

## 阶段 8 · 质检（这步不能省）

不能只看日志说"完成"。两个动作：

```bash
# 1) 每镜抽 3 帧拼图看画面
ffmpeg -y -ss <每镜 25%/55%/80%> -i clips/S01.mp4 -frames:v 1 qa/S01_a.jpg
ffmpeg -y -pattern_type glob -i "qa/S*.jpg" -vf "scale=210:-1,tile=6x5" -frames:v 1 qa/sheet.jpg

# 2) 对有台词的镜头抽音轨转写，确认真的念了、念对了
ffmpeg -y -i clips/S16.mp4 -vn -ac 1 -ar 16000 audio/_p_S16.wav
# 然后交给 ASR 转写，核对台词
```

**画面要看的四类错**（实测最常出现的）：

| 类型 | 症状 | 根因 | 修法 |
|---|---|---|---|
| 多出道具 | 桌上多一碗面、墙上多一块菜单牌 | 首帧提示词里写过 / `scene.set` 漏了 / 旧的全局面馆锚 | 改 prompt 明确「只有 X，禁止食物」，重跑 frame + video |
| 人数错 | 两人镜出现第三个人、过肩镜前景人变两个 | `faces` 把背对镜头的人喂进去了 | `faces` 只留露脸的人，重跑首帧 |
| 跳轴 | 上一镜她在左，下一镜跑到右 | 提示词没写左右 / 换了机位侧 | 补 `left third / right third`，重跑 |
| 脸漂移 | 同一角色前后不像 | 用了尾帧连传接力 | 删 `link`，独立出首帧 |

**声音要验的**：人声是否真的出现（转写有内容）、是否念糊（关键词对不对）、有没有双重人声（模型 + TTS 同时响）。

有问题的镜**先只重跑那一镜**，别整片重来。

---

## 阶段 9 · 配乐

```bash
python scripts/ac.py music "<dir>" --duration 172 --caption "warm felt piano, slow, restrained"
# 没显卡 / ComfyUI 在排队：临时走火山引擎（0.002 元/秒，>60s 自动分段拼接）
python scripts/ac.py music "<dir>" --provider volc --duration 172 --caption "..."
```

两条通道（`music.provider` = `comfyui` / `volc`）出口都是 `audio/bgm.mp3`，后面步骤完全一样。
火山这条的细节与踩坑见 `providers/volc_music.md`：纯音乐单次上限 60 秒、两个计费入口不互通、签名中间密钥用二进制。

时长要 ≥ 成片总时长（含转场前的原始总和），否则结尾没音乐。生成后**先做响度归一化**（火山通道脚本内部已自动做）：

```bash
ffmpeg -y -i audio/bgm.mp3 -af "loudnorm=I=-23:TP=-2:LRA=7" -c:a libmp3lame -b:a 192k audio/bgm_new.mp3
mv audio/bgm_new.mp3 audio/bgm.mp3      # 不能原地覆盖
```

### 配乐台（推荐，别盲调数字）

```bash
python scripts/ac.py music-ui "<dir>" --port 8788
```

本地网页，四件事一起做：试听 `audio/music/` 曲库、选曲写 `project.json.bgm_file`、逐镜拖音量写 `shot.bgm`、看情绪曲线；调完「保存并应用」自动后台合成。

AI 生成的配乐只认标签，跟每一镜的情绪无关——**要贴片就换真人写的曲子**，曲库放 `audio/music/*.mp3` 即可。

逐镜音量（0–1）参考：

| 剧情位置 | bgm | 相对原声 |
|---|---|---|
| 开场日常 | 0.26 | −12.6dB |
| 情绪下沉 | 0.22 | −17.3dB |
| 判决那一刻 | 0.08 | −16.6dB |
| 完全撤空 | 0.0 | 静音 |
| 主题段 / 对白密集 | 0.60 | −15.5dB |
| 结尾（最亮） | 0.30–0.46 | 视混音而定 |

---

## 阶段 10 · 音效

两种来源，**优先真素材**（合成音效一听就假）：

| 来源 | 放哪 | 用法 |
|---|---|---|
| 真实素材（Mixkit 等免费商用库） | `audio/sfx/<name>.wav` | `sfx` 的 `kind` 直接写文件名（不带扩展名） |
| `scripts/sfx.py` 现场合成 | 自动生成 | `glass / notify / tick / whoosh / thud / rain / drone` |

素材统一转成 44.1k 立体声 wav、去头静音：

```bash
ffmpeg -y -i raw/ding.mp3 -af "silenceremove=start_periods=1:start_silence=0.05:start_threshold=-45dB" \
       -ar 44100 -ac 2 -c:a pcm_s16le audio/sfx/ding_soft.wav
```

落点原则：

- 情绪转折处放**一声轻铃 / 一记气声**，不要连续铺满。
- 环境声缺失时用 `rain` 之类拉长当底（`stream_loop -1` + 首尾 fade，做 30 秒左右的 bed）。
- 音效对白段要压得比人声低 15dB 以上，峰值 ≈ −16dB 才「听得见但不抢戏」。
- 别卡在演员微动作上（动作时刻不可控），优先卡镜头切点前后。

**验收**：对比有无音效两版同点位的 `max_volume`，该响的点抬起来 3–6dB，对白段只抬 1–2dB。

---

## 阶段 11 · 转场

写在 `shot.x`，进入该镜时生效：

```json
{"id": "S02", "x": {"kind": "fade", "dur": 0.8}}
{"id": "S05", "x": {"kind": "cut"}}
```

| 位置 | 做法 |
|---|---|
| 换场景 / 跳时间 | `fade` 0.8–1.2s |
| 同场景正反打 | `cut`（硬切），不要叠化，会拖 |
| 结尾空镜 | `fade` 1.2s |

> 🔴 **致命坑**：`xfade` 的 `duration` **不能短于一帧**。硬切曾用 0.04s（24fps 一帧 = 0.0417s），
> 整条滤镜链静默失败，172 秒的片子被截成 33 秒，日志还不报错。
> **硬切统一用 0.1s**（肉眼仍是硬切），并且合成后必须核对成片时长。

> 🔴 转场会缩短总时长（`总长 − Σ转场时长`）。字幕、音效、配乐都必须用**相对本镜**的时间，
> 让合成阶段按新的起点重排；写成绝对秒数必然全错位。

---

## 阶段 12 · 字幕

两个写法，按需要选：

1. **自动**（`assemble --subs`）：做人声检测（VAD），把字幕卡到真实说话区间。
   问题：轻声台词检不到（"我只是……怕。"这种气声会被漏掉），一镜多句会挤成一行。
2. **逐句手写**（推荐，写 `shot.subs`）：精度最高，可控制断句与停留。

```json
"subs": [
  {"t": 0.19, "d": 1.40, "text": "趁热喝，不加糖。"},
  {"t": 3.60, "d": 1.08, "text": "……下次别买了。"}
]
```

- `t` 相对本镜起点，`d` 显示时长。
- **单排不超过 14 个汉字**。长句在标点处拆成两条先后出现，不要靠播放器自动折行
  （ASS 里设 `WrapStyle=2` 禁止自动换行，宁可拆两条）。
- 字幕样式固定：底部居中、白字黑边、字号适中，别加花字。

**验收**：抽帧看 3–5 个时间点，确认每条字幕只有一排、出现在对应台词的位置。

---

## 阶段 13 · 合成

```bash
python scripts/ac.py assemble "<dir>" --subs --voice
```

合成顺序（脚本内部）：逐镜规范化 → 转场拼接（视频+音频同步交叉淡化）→ 配乐分段混音 → 音效叠加 → TTS 混合 → 烧字幕。

音频规则：

| 情况 | 处理 |
|---|---|
| 有配乐、无 TTS | 原声 ×0.82（台词在原声轨上，压狠了人声一起小） |
| 有配乐 + 有 TTS | 原声 ×0.22，TTS 单独铺 |
| **TTS 只补某几镜** | 原声不压（TTS 是补充不是替代） |
| 某镜 TTS 与模型人声重复 | 该镜音轨换静音，只留 TTS（`anullsrc` 替换） |

> 🔴 **收紧（tighten）坑**：默认按「人声结束 + 0.9 秒」裁尾，会把台词之后的表演全砍掉
> （她背对他喝那一口、听到"我尊重你"僵住、红着眼正视）。
> 凡是「台词说完还有戏」的镜头，必须 `"tighten": false`；拿不准就全片关掉，宁可长两秒。

---

## 阶段 14 · 验收

```bash
python scripts/ac.py audit "<dir>"     # 出 AUDIT.md
python scripts/ac.py status "<dir>"
```

硬指标：

| 项 | 标准 | 怎么测 |
|---|---|---|
| 时长 | 落在用户要求区间（±10s） | `ffmpeg -i out/final.mp4` 看 Duration |
| 画幅 | 704×1280 竖屏 | 同上 |
| 响度 | −16 ~ −17 LUFS，峰值 ≤ −1 dBTP | `ffmpeg -af loudnorm=I=-16:TP=-1.5:print_format=summary -f null -` |
| 字幕 | 每句单排、在对应台词处 | 抽帧 |
| 人声 | 每句台词都真实出现 | 抽音轨转写 |
| 转场 | 该叠化的地方有过渡，不是硬切 | 抽转场中间帧 |
| 穿帮 | 无多余人物 / 道具 / 乱码字 | 全片缩略图墙 + 逐镜三帧 |

**缩略图墙**是效率最高的验收方式：一片 30 帧拼一张图，扫一眼就知道哪几镜要重跑。

---

## 阶段 15 · 交付

```bash
cp out/final.mp4 out/<中文片名>.mp4
```

交付时一起给：成片、`script/story.md`（剧本）、`AUDIT.md`（核对表）。
临时文件（`_p_*.wav`、`_q_*.jpg`、`qa/`、`_test_*.mp4`）清掉，别混进产物目录。

---

## 常见失败速查

| 现象 | 根因 | 修法 |
|---|---|---|
| 成片只有 30 秒 | xfade 时长 < 1 帧 | 硬切改 0.1s，重合成 |
| 字幕全片错位 | 用了绝对时间 | 改成 `shot.subs` 相对时间 |
| 字幕永远是旧版 | 滤镜写死 `ass=_subs.ass` | 已修：用实际字幕文件名 |
| 一镜两句挤成一行 | 用了 VAD 合并字幕 | 改逐句 `shot.subs`，14 字拆行 |
| 旁白双重人声 | 模型念了 + TTS 又混 | 该镜音轨静音，只留 TTS，或关 `--voice` |
| 关键表演被剪掉 | tighten 按人声裁尾 | `"tighten": false` |
| 桌上多出食物 | 提示词写过 / 旧面馆锚 | 改 prompt 明令禁止，重跑该镜 |
| 同一镜出现两个同一人 | 过肩镜把前景人脸喂进去了 | `faces` 只留露脸的人 |
| 同一镜出现三个人 | 提示词里否定句堆太多（每句都在强化"人"） | 改成正面陈述：点名 N 个人 + 说空位是空的 |
| 墙上凭空出现陌生人像 | `no photograph of a person` 反而激活了"人" | 说「挂历是空白的、相框内容看不见」 |
| 每镜都换一间店 | 场景板按镜头出，不是按机位 | 写 `scene.set` + `angles`，`scene-gen --force` |
| 结尾没音乐 | bgm 短于成片 | 重新生成 ≥ 总时长的曲子 |
| 音效听不见 | gain 太低（−26dB） | 提到峰值 ≈ −16dB |
| 第二集换脸了 | 重新 char-gen | 用 `cast` 共享库 + `episode-new` |
| 视频里两人换边站 | 视频提示词漏了站位约束 | `video_prompt` 也要写死左右位置，见阶段 7 |
| 视频里凭空多出人 | 视频提示词漏了人数约束 | 加 `The headcount in this shot is exactly N ...` |
| 视频里人脸变形 | 视频提示词漏了锁脸约束 | 加 `must stay exactly as in the reference first frame ...` |
| 改了首帧但视频没变 | 视频用的是 `video_prompt`，不继承首帧 | 两处都要改，改完必须重出该镜 |
| 出图报 403 / 超时 | 中转站拦 Python UA 或排队过久 | 本 skill 已自动带完整浏览器头；仍失败会自动回退 Agnes |
| 同一镜出现两个同一人 | 提示词里景别和通用兜底句打架 | 删掉「并排、完整可见」这类通用句，只写清位置和姿势 |
| 出图慢得离谱 | 服务端排队（正常 1–2 分钟，超过 10 分钟就是卡了） | `--only <id> --force` 单镜重跑，别等整批 |
| 画面里烧进了台词字幕 | `video_prompt` 里带了引号对白，模型把台词画成了屏幕字 | 对白别写进引号喂给视频模型；已生成的在成片上会被自家字幕盖住，但**复用素材时会暴露**（查画面纵向 56%–72% 的字幕带） |

---

## 成本与时长的经验值

| 项 | 20 镜 / 2.5 分钟的一部片 |
|---|---|
| 图片（定妆 + 道具 + 场景板 + 首帧） | 约 30 张 |
| 视频 | 20 段，3 路并发，1–2 小时 |
| 配乐 | 1 首（本地 ComfyUI 不占额度；火山通道约 0.002 元/秒，2.5 分钟 ≈ 0.3 元） |
| 重跑率 | 首轮约 15–25%（穿帮/失败镜） |
| 全流程人工介入点 | 剧本定稿、场景板验收、首帧验收、质检、精修五处 |
