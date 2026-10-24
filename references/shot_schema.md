# 镜头表 schema（script/shots.json）

## 完整示例

```json
{
  "title": "对面那碗面",
  "logline": "深夜面馆，女孩追问对面那碗面是给谁的",
  "genre": "剧情 / 温情",
  "characters": [
    {
      "name": "girl",
      "desc": "25岁女性，齐肩黑发，米白针织开衫，气质安静",
      "desc_en": "25-year-old woman, shoulder-length black hair, cream knit cardigan",
      "voice": "zh-CN-XiaoxiaoNeural"
    }
  ],
  "props": [
    {"name": "bowls", "desc": "两只白瓷面碗，一只空碗架着筷子", "desc_en": "two white ceramic bowls, one empty with chopsticks"}
  ],
  "shots": [
    {
      "id": "S01",
      "duration": 7,
      "scene": {
        "slug": "面馆内·夜",
        "time": "深夜",
        "place": "面馆内",
        "weather": "无雨",
        "light": "暖黄吊灯，桌面有明显光晕，背景偏暗"
      },
      "char": "girl",
      "action": "老板娘把一碗面放在女孩对面，转身欲回厨房",
      "micro": "嘴角先轻轻提了一下，笑意才慢慢漫到眼底",
      "speaker": "boss",
      "line": "还是不要葱对吧？",
      "frame": {
        "mode": "swap",
        "prompt": "Interior of a small noodle shop at night, warm pendant light. A middle-aged woman in a dark blue apron sets a bowl on the table, medium-wide shot. Do NOT describe facial features. Keep the face, identity and hairstyle exactly as in the reference image."
      },
      "video_prompt": "One continuous shot, no cuts. 0-3s: she walks in and sets the bowl down. 3-6s: she places an empty bowl opposite. 6-7s: she pauses and looks over her shoulder. The character speaks in Mandarin Chinese with precise lip-sync: \"还是不要葱对吧？\" — mouth shapes each syllable clearly, jaw and lips move naturally; keep the face turned toward the listener so the mouth stays visible. Audio: ambient shop sounds."
    }
  ]
}
```

## 字段说明

| 字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `id` | ✅ | string | 镜头编号，同时是文件名（S01 → frames/S01.jpg、clips/S01.mp4） |
| `duration` | ✅ | int | **4–12 秒**（Agnes 单段上限 12s） |
| `scene` | ✅ | object | 场景：`id`（场景分组，同场景必须同 id）/ `slug` / `time` / `place` / `weather` / `light` |
| `char` | ✅ | string | 本镜参考的角色（决定用哪张 face_ref） |
| `action` | ✅ | string | 这一镜唯一的主要动作（中文，给人读） |
| `micro` | | string | 微表情过程（中文，给人读；英文已写进 video_prompt） |
| `speaker` | | string | 说台词的角色 name，或 `VO` 旁白；无台词留空 |
| `line` | | string | 真正说出口的台词，≤18 汉字；无台词留空 |
| `frame.mode` | ✅ | `source` \| `swap` | `source` 直接用角色定妆图；`swap` 按 prompt 换场景/服装 |
| `frame.prompt` | swap 必填 | string | **英文**首帧提示词：场景、服装、光线、构图、景别；不写五官 |
| `video_prompt` | ✅ | string | **英文**视频提示词：连续长镜头 + 台词原句 + 口型指令 + 微表情 + 2–3 段运镜 |
| `seed` | 可选 | int | 固定种子便于复现 |
| `characters[].voice` | 可选 | string | 该角色的 edge-tts 音色；不填会自动分配不同音色 |
| `props[]` | 可选 | array | 道具参考图描述 |

## 可拍性规则

| 规则 | 数值 | 违反后果 |
|---|---|---|
| 单镜时长 | 4–12 秒 | 超 12s 直接 400 |
| 单镜动作数 | 1 个 | 多动作必崩（抽搐/瞬移） |
| 同框人数 | ≤ 2 | 3 人以上串脸 |
| 台词长度 | ≤ 18 汉字 | 念不完，口型对不上 |
| 台词镜头景别 | waist-up medium / medium close-up | 远景说话看不到口型 |
| 台词覆盖 | ≥ 一半镜头 | 全片变默片/旁白片 |
| 景别跨度 | 中远景 ↔ 腰以上中景 | 直怼脸部特写必崩 |
| 运镜 | 一个连续长镜头 | 切镜导致鬼脸 |
| 服装变化 | 换镜头 | 同镜头换装会变形 |

## 动作估时

| 动作 | 约需 |
|---|---|
| 走三步 | 3–4 秒 |
| 抬手 / 转头 | 1–1.5 秒 |
| 转身 180° | 1.5–2 秒 |
| 说一句 12 字台词 | 3–4 秒 |
| 坐下 / 起身 | 2–3 秒 |

## 长视频怎么排

Agnes 单段最多 12 秒，长视频 = 多段拼接：

| 目标成片 | 镜头数（8 秒/镜） |
|---|---|
| 30 秒 | 4 镜 |
| 60 秒 | 8 镜 |
| 90 秒 | 11–12 镜 |
| 3 分钟 | 22–24 镜 |

## 台词分布检查

- 8 镜：至少 4 镜有台词，第一镜开口，最后一镜收尾。
- 6 镜：至少 3 镜有台词。
- 不要把台词全堆在最后两镜，前 30 秒必须有人说话。

## 新增字段（场景圣经 / 机位 / 接力）

### 角色：固定服装
```json
{"name": "girl", "desc": "中文形象", "desc_en": "East Asian Chinese, ...",
 "outfit_en": "cream knit cardigan over a dark navy dress, black flat shoes",
 "voice": "zh-CN-XiaoxiaoNeural"}
```
`outfit_en` 是**全片唯一一套服装**，所有镜头复用，写进首帧提示词，防止中途换衣服。

### 场景：陈设清单 + 机位表
```json
"scene": {
  "id": "shop",
  "slug": "老街面馆·夜",
  "time": "深夜十一点半",
  "place": "老街面馆店内",
  "weather": "无风",
  "light": "三盏暖黄吊灯 + 窗外冷蓝街灯",
  "interior": true,
  "set": ["白瓷砖墙", "不锈钢煮面大锅冒热气", "红底塑料菜单牌",
          "木方桌配红色塑料凳", "玻璃门饮料冷柜", "暖黄吊灯"],
  "angles": {
    "wide":       "wide view from just inside the entrance looking toward the counter",
    "counter":    "camera beside the counter looking across it",
    "table":      "camera across the window-side table facing the window seat",
    "table-wide": "wider view of the table from the aisle, all seats in frame",
    "entrance":   "camera just inside the doorway looking along the shop",
    "door":       "camera on the street looking through the open doorway"
  }
}
```
- `set`：5–8 条陈设，写到材质和颜色；同一场景所有镜头共用。
- `angles`：机位表。管线按「场景 × 机位」出空板，文件名 `shop__table.jpg`。
- `interior: true`：首帧会强制加“室内，不要街道/灯笼/招牌”的约束，防止飘到街上去。

### 分镜：机位 / 人物白名单 / 接力
```json
{
  "id": "S02",
  "angle": "table",
  "cast": ["girl", "boss"],
  "faces": ["girl"],
  "link": "prev",
  "frame": {"mode": "swap", "prompt": "..."},
  "video_prompt": "..."
}
```
- `angle`：引用 `scene.angles` 里的键。同一场景只换机位，不换布景。
- `cast`：这一镜画面里**所有**人物（含只露背影/肩膀的）。首帧会写成“人数 + 正面点名”的白名单。
- `faces`：**只喂「画面里真露脸」的角色参考图**，默认等于 `cast`。
  🔴 过肩/背身镜头必须收窄（例：`"faces": ["girl"]`）。前景那人背对镜头看不见脸，把他的 face_ref 一起喂进去，
  模型会在画面别处按参考图**再画一个完整的人** —— 同一镜出现两个同一个人（本 skill 实测事故：S06 窗边凭空多出一个男主）。
- `link: "prev"`：首帧取上一镜视频的**最后一帧**。
  适用：同场景、同机位、紧接的正反打/接话。管线会自动等上一镜出片再提交，不会并发抢跑。
  不适用：跨场景、换机位、时间跳跃。
- `no_plate: true`：极近景时不吃场景板参考（板是中景，模型会照抄它的构图）。代价是背景陈设要自己写进 prompt。
- `no_faces: true`：**极近景不露脸**（只拍爪子/前臂/食材）。这一镜的人物脸不入画。
  🔴 不加这个标记，特写会被顶成站立人物镜（实测 ep05 S06）：
  提示词里明明写了「Tight close-up…only his forearms and paws visible」，
  但 skill 自动追加的「Headcount exactly 2, these are the only bodies visible」
  +「The two characters face each other…their eyes meet on each other's face」
  跟它直接打架——模型最后照着**后写的那句**画，成了两人站着对话的中景，
  特写彻底没了。
  加上 `no_faces: true` 之后，skill 会：
  - **不喂人脸参考图**（没有脸要锁，喂了反而把模型往人物照上带）
  - **不追加人数白名单和两人站位句**
  - 换成极近景白名单：「画面里只有爪子、前臂、挖出来的植株、泥土和草，
    没有脸、没有头、没有身体，人在手腕和手肘处被裁切」
  - 道具参考图的编号自动从 1 开始（没人脸图占位）
  > 注意：`no_faces` 和 `no_plate` 是两件事。`no_plate` 管**背景**参考（场景板），
  > `no_faces` 管**人物**参考（人脸图）。极近景通常两个都要开。
  > 判定标准很简单：**这一镜能不能看见脸**——能看见就别开，会破坏锁脸。


### 配乐音量：`bgm`（0–1，可选）
```json
{"id": "S07", "bgm": 0.0}
```
- 逐镜指定这一镜配乐的音量；**不写就沿用上一镜**，所以只需要在音量变化的那一镜写。
- 相邻同值会自动合并成段（16 镜通常只剩 6–7 段），段间 0.45s 淡入淡出，尾段 3s 淡出。
- 素材必须先做 `loudnorm=I=-23` 归一化，否则曲子自身响度不均，系数不可控。
- 参考值：日常 0.26 / 情绪下沉 0.22 / **撤空 0.0** / 主题对白段 0.60 / 打击那一刻 0.08 / 孤独特写 0.40。目标是配乐低于对白 12–17dB。


### 音效：`sfx`（数组，可选）
```json
{"id": "S09", "sfx": [{"at": 0.55, "kind": "notify", "gain_db": -17}]}
{"id": "S01", "sfx": [{"at": 0.30, "kind": "rain", "dur": 42.0, "gain_db": -28}]}
```
- `at`：**本镜内**的秒数（不是全片时间轴）。镜头重出/收紧后不用改。
- `kind`：`glass` / `notify` / `notify2` / `tick` / `tap` / `whoosh` / `thud` / `rain` / `tinnitus` / `drone` /
  `chop` / `clang` / `sizzle` / `woktoss` / `flame` / `plate` / `paper` / `footstep` / `cheer`（见 `scripts/sfx.py`，现场合成）。
- `gain_db`：dB，相对素材本身的 −3dBFS 峰值。短音效 −14 ~ −22，连续的 rain/tinnitus/drone 用 −26 ~ −38。
  🔴 **字段名写错不报错，只是音效力度全废**（skill v1.19.0 前只认 `gain`，
  镜头表写 `gain_db` 会被静默读成默认 −12dB，所有音效力度归零、炒菜声和火焰声都不够响，
  而成片照常出，肉眼很难发现）。
  现在 **`gain_db` 和 `gain` 两个名字都认，`gain_db` 优先**——写哪个都行，但**全片要统一**。
- `dur`：只有 rain / tinnitus / drone 需要写时长（秒）；不写默认 4s。
- 简写 `"sfx": ["tick", "whoosh"]` 等价于都落在镜头开头、−12dB（不推荐，容易盖住台词）。
- 落点优先挑**镜头切点前后**或**对方开口前 0.6–1s**，别卡演员微动作——模型片段的动作时刻不可控。
- 叠加：`ac.py sfx <dir> --into out/final-bgm.mp4 --out out/final.mp4`（视频流复制、只重混音频）。同一版不要叠两次。
- 🔴 **野外做菜的音效要更响**：火焰 `flame` −8dB 起、油爆 `sizzle` −7dB 起、
  颠勺 `woktoss` −10dB、切菜 `chop` −13dB（见 `food_show.md` 野外做菜段）。
  锅气是美食号的灵魂，音效压太轻就只剩画面在动。


### 环视镜头
`video_prompt` 里写 `the camera slowly arcs around the table/subject`，全片 1–2 次即可，别用在台词特写。
