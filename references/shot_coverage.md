# 对话覆盖与镜头调度（shot coverage）

> 这份文件解决的是**「讲得清、接得住、不死板」**三件事，和 `camera_setups.md`（机位表/轴线）、
> `camera_language.md`（运镜词库）是同一套东西的三个面：
> `camera_setups` 定"站在哪"，`camera_language` 定"怎么动"，**这份定"这场戏一共要哪几个镜头、按什么顺序给"**。
> 只定机位不定覆盖，出来的就是一整集同一个角度；只定运镜不定覆盖，出来的就是"推来推去还是那两张脸"。

---

## 零、先看一份真实体检（ep11 实测，31 镜）

单看每一条都合理，连起来就出事。把 31 镜的机位句抽出来统计：

| 指标 | 实测 | 应该 |
|---|---|---|
| 景别种类 | **只有 medium 一种**（medium two-shot ×22、medium wide ×2、medium ×1） | 一集里 wide / medium / medium close-up / insert 都要有 |
| 特写镜数 | **0 / 31** | 对话戏至少每 3–4 镜一个近景或大近景 |
| 机位种类 | **只有 "across the counter" 一个** | 一个场景 3–5 个机位轮换 |
| 运镜 | **30 / 31 镜没有运动描述** | 每镜要么一个运动，要么明写 static |
| 谁在画左 | 兔/松鼠/狼/金毛轮流在左，**S31 猫哥突然从右跳到左** | 同一场景内谁在左永远不变 |

观众的三句原话，逐条对上表：

> 「对话的时候要有特写镜头来展现表情细节」 ← 特写 0 镜
> 「场景还是变化太多，角度一会儿又变了一会儿又变了」 ← 机位只有一种，但缺焦段/高度/朝向锚点，模型每次自己换
> 「镜头语言还是过于死板」 ← 30/31 镜静态，景别单一

**关键认知：机位只有一种，不等于角度稳定。** 写一句 `medium two-shot across the counter`，
没有焦段、没有机位高度、没有"相机贴在柜台上"这种物理锚点，模型每生成一次就自己挑一个角度——
12 个镜头看下来就是 12 个角度。"稳定"靠的是**把机位写死到物理位置**，不是靠反复写同一句。

---

## 一、每镜五个决策（缺一个，模型就回落到默认）

AI 生成的默认值是：**平视、中景、居中、静止、普通镜头**。不说，就一定拿到这个。

| # | 决策 | 选项 | 不写会怎样 |
|---|---|---|---|
| 1 | **景别 Distance** | wide / medium / medium close-up / close-up / insert(macro) | 全集中景 |
| 2 | **机位高度 Height** | eye level / low angle / high angle / 俯视 overhead | 全是平视，缺压迫与弱势 |
| 3 | **朝向 Facing** | three-quarter / profile / over-the-shoulder / rear / POV | 两人并排正面看镜头，像合影 |
| 4 | **焦段与焦点 Lens** | 24mm 空间 / 35mm 自然 / 50mm 人像 / 85mm 压缩背景 f/2 | 人物和背景糊在一起，没有空间 |
| 5 | **运动 Move** | static / slow push-in / pull-out / tilt / track / arc | 模型自己加漂移，或干脆不动 |

**写成一个短语，不是标签堆。**
`Low-angle medium close-up on an 85mm lens, camera at counter height looking slightly up at the cat`
好过 `low angle, medium close-up, 85mm, cinematic`。

**每个机位必须有物理锚点**：`camera resting on the counter`、`camera at the doorway`、
`camera at eye level across the table`。物理位置比抽象标签更能活下来。

### 1.1 这五个决策在 shots.json 里放哪（字段对照）

> 🔴 **这一节是本文件最重要的部分。** 下面写的字段名**就是代码里真实存在的字段**，
> 照抄就能生效；不是示意图。

| 决策 | 落到哪个字段 | 写法示例 |
|---|---|---|
| 景别 | `shot_size` | `"medium close-up"` |
| 机位 + 高度 + 朝向 + 焦段 + 运动 | `camera` | `"low angle medium close-up on an 85mm lens, camera resting on the counter, slow push-in"` |
| 机位代号 | `angle` | `"table"` |
| 说话人 | `speaker` | `"maoge"` / `null`（空镜、反应镜写 null） |

> 📌 **实战现状（ep11/ep12/ep13 三集 100 镜实测）**：`shot_size` 和 `camera` 字段**全是空的**，
> 景别是直接写进 `frame.prompt` 的 framing 句和 `video_prompt` 的时间码里的。
> 也就是说**现在就能生效的只有 frame.prompt / video_prompt**——
> 下面这两个结构化字段是"更好的写法"，填了才能被 `ac.py check` 稳定识别、统计配比。

**`camera` 字段就是"一段完整的镜头句"**，景别/焦段/机位/运动全写在这一句里，
拼进首帧和视频提示词。示例（真实可用）：

```json
{
  "id": "S07",
  "scene": "SC1",
  "angle": "table",
  "shot_size": "medium close-up",
  "camera": "medium close-up on an 85mm lens at f/2, camera resting on the counter at eye level, three-quarter view, static locked-off tripod",
  "speaker": "maoge",
  "duration": 4
}
```

**`angle` 只写代号，不写描述。** 它的英文描述写在**场景定义**里：

```json
"scenes": {
  "SC1": {
    "set": ["wooden counter", "red paper lantern", "calligraphy menu board", "blue-and-white vase"],
    "angles": {
      "wide":  "wide establishing view from just inside the entrance, looking down the shop toward the counter",
      "table": "camera across the counter at eye level, 85mm, the counter edge in the lower foreground",
      "door":  "camera on the street looking through the open doorway into the shop"
    }
  }
}
```

`ac.py` 用 `场景id__机位代号.jpg` 找场景板，所以 **`angle` 必须在 `scenes[].angles` 里存在**，
否则 `scene-gen` 会拿兜底描述画一张，镜头就漂了。

### 1.2 同一机位的机位句要逐字相同

同一个 `angle` 的所有镜头，机位句（`camera` 字段）**逐字重复**，只有动作变。
这样模型拿到的相机位置永远一致，观众看到的是同一台机器在同一个位置拍的不同时刻。

**不要每镜重新描述一遍"谁在左"** —— 上一集就是"脑子里有轴线，提示词里没写死"，
所以编着编着就反了。左右写进 `scene.set` 或 `camera` 句里的固定位置词。

---

## 二、对话覆盖：这场戏到底要哪几个镜头

真实拍戏不会"一个角度拍完一场对话"，会这样覆盖：

```
1 个 Master（交代空间与站位）
  ↓
每个说话人 1 个 Single（近景 / 中近景，只装一个人）
  ↓
过肩（OTS）——两人关系最紧的时候用
  ↓
反应镜头（Reaction，听的人单独一条，静止、平视）
  ↓
回到 Master 或拉远收尾
```

### 2.1 三种镜头的分工

| 镜头 | 装几个人 | 用来干什么 | 景别 |
|---|---|---|---|
| **Master** | 全部 | 交代空间、站位、关系；一个场景 1 次就够 | wide / medium wide |
| **Single** | **只装 1 个** | 这个人说话时的表情、口型、微表情 | **medium close-up（头肩）** 或 medium |
| **OTS 过肩** | 2 个（前虚后实） | 两人关系最紧、要压迫感 | medium close-up |
| **Reaction** | 1 个 | 听的人的反应（这才是戏） | close-up / medium close-up |
| **Insert** | 0 个 | 手、物件、道具特写（手部动作放这里，别放说话镜） | macro / insert |

### 2.2 一场 4 句对话的标准镜头序列

假设 A 说 2 句、B 说 2 句，直接用这套：

| 顺序 | 镜头 | 谁 | 说明 |
|---|---|---|---|
| 1 | Master wide | — | 定空间、定左右 |
| 2 | Single A（medium close-up） | A 说 | 有表情 |
| 3 | Single B（medium close-up） | B 说 | **同焦段、同高度、同景别**，正反打才均匀 |
| 4 | Reaction A（更近） | A 听 | 不说话的那一下才是戏 |
| 5 | Single B | B 说 | 回正反打 |
| 6 | OTS 或拉远 | — | 收 |

**反打两条必须匹配**：同镜头、同机位高度、同景别。
一边 35mm 中景、一边 85mm 大特写，剪在一起像两部片。

### 2.3 特写怎么写（血泪教训）

| 写法 | 结果 |
|---|---|
| `extreme close-up on her eyes, face fills the frame` | ❌ 脸占满画面，像素不够，五官必崩 |
| `close-up`（含糊） | ⚠️ 模型可能理解成怼脸 |
| `medium close-up, head and shoulders, face fills about one third of the frame` | ✅ 安全，表情够清楚 |
| `the camera pushes in to a medium close-up`（4 秒以上镜） | ✅ 最佳，有过程有细节 |

**特写不是越近越好，是"头肩、脸占画面三分之一"。** 这是 720×1080 竖屏能承受的上限。

### 2.4 说话的镜别让手动

拿着抹布、筷子、告示的手，在嘴动的时候会糊成一团。
手部动作拆成独立的 insert 镜（不说话），说话镜只拍头肩。

---

## 三、竖屏 9:16 的铁律（我们 90% 的片子都犯这条）

竖屏不是横屏裁一刀。竖屏的物理限制会直接毁掉双人戏：

> **禁止 side-by-side two-shot（两人并排横着站）。**
> 竖屏里两个人横着排，两张脸会被挤到左右边缘、中间一大片空，脸小到看不清表情——
> 这就是"表情看不清"和"看着像合影"的物理原因。

替代方案三条，按优先级：

| 方案 | 写法 | 适用 |
|---|---|---|
| **① 交替单人（首选）** | 每镜只装一个说话人，正反打剪 | 所有对话戏 |
| **② 纵深堆叠** | 一人在近处低、一人在远处高，斜着排进竖屏 | 要同框但不要并排 |
| **③ 过肩** | 前景是肩背（虚），后景是对方的脸（实） | 关系最紧的时刻 |

其它竖屏规则：

- **主体居中优于三分法**：窄画幅里把人放偏，另一边就是死空间。
- **用高度不用宽度**：写"天花板/灯笼在上方"而不是"桌子向两边延伸"。
- **运动沿光轴或垂直**：推、拉、俯仰、升降都行；**横移和摇镜会把主体甩出画外**。
- **眼睛放在上三分之一线**（距顶 35–40%），脸和字幕留在 15%–75% 之间。

---

## 四、轴线：谁在左，全场景不许变

`camera_setups.md` 已经写了三机位法和 180° 线，这里只补**它在提示词里怎么落地**——
上一集就是"脑子里有轴线，提示词里没写死"，所以每镜重新描述一遍"谁在左"，编着编着就反了。

### 4.1 轴线写进场景的机位描述

```json
"scenes": {
  "SC1": {
    "set": ["wooden counter", "red paper lantern", "calligraphy menu board",
            "A=猫哥永远画左看右，B=对方永远画右看左；机位全部在柜台这一侧"],
    "angles": {
      "wide":   "wide establishing view from the doorway, 35mm, eye level",
      "table":  "camera across the counter at eye level, 85mm f/2, 猫哥在画左",
      "door":   "camera on the counter side at eye level, 85mm f/2, 对方在画右",
      "ots":    "over the customer's shoulder, 50mm, foreground shoulder soft",
      "insert": "camera resting on the counter, 100mm macro"
    }
  }
}
```

### 4.2 唯一允许换边的情况

一个中性镜头过渡（正面双人镜，机位压在轴线上），或跟着人走过去的运动镜头。
**不许硬切过轴。**

---

## 五、景别递进：相邻两镜必须换景别

> 两个同景别、同角度的镜头剪在一起，观众读到的是**跳切**（画面抖了一下），不是换镜头。

规则：

1. **相邻镜景别必须变一档**：wide → medium close-up → medium → insert，
   不要 medium → medium → medium。
2. **递进有方向**：越吵越近（wide → medium → close），越冷越远（close → medium → wide）。
3. **一集 30 镜的景别配比参考**：
   - wide / medium wide：15%（定场、结尾）
   - medium：35%
   - **medium close-up：35%（对话主体，表情靠这个）**
   - insert / macro：15%（手、道具、食物）

上一集的比例是 medium 100%，所以"死板"。

---

## 六、运镜：每一镜要么一个运动，要么明写不动

| 规则 | 说明 |
|---|---|
| **一镜一个运动** | 推 + 环绕 + 升降叠在一起必糊。一个短镜（4–6 秒）只做一个。 |
| **运动要有速度与终点** | `slow push-in over 4 seconds, ending on a medium close-up`，不是 `push in`。 |
| **不想动就写死** | `static camera, locked-off tripod`。不写，模型常自己加漂移。 |
| **4–6 秒短镜只做"推/极缓推/定点"** | 环绕、升降、跟拍在 4 秒里做不完，出来像抽帧。 |
| **对话镜优先 static 或极缓推** | 说话时镜头动，口型容易对不上。 |
| **运动镜头只放在 Master 上** | 反打/过肩保持稳定，否则两条反打空间感不一致，剪着跳。 |

> 📌 **短剧流 vs 10 秒长镜头**：本 skill 现在跑的是**每镜 4–6 秒独立首帧**的短剧流，
> 一个镜头只做一个运镜是硬规矩。`camera_language.md` 里那套"10 秒里连做 2–3 段运镜"
> 是给 10 秒长镜头用的，**短剧流不要照抄**。

---

## 七、分镜表必须带的字段

`shots.json` 每镜除了原有字段，**强制**多这几项：

```json
{
  "id": "S07",
  "scene": "SC1",
  "angle": "table",
  "shot_size": "medium close-up",
  "camera": "medium close-up on an 85mm lens at f/2, camera resting on the counter at eye level, three-quarter view, static locked-off tripod",
  "speaker": "maoge",
  "duration": 4
}
```

**缺 `angle` 的镜**，`ac.py` 会兜底成 `wide`，等于凭空占掉一个广角位——
**一集里出现 3 个以上被兜底的镜，说明机位没定清，要回去补**。

---

## 八、写完分镜的自查

`ac.py check` 已自动跑下面这些（v2.0.0 起，见 `references/logic_check.md`）：

**必须改**
- [x] **特写（medium close-up / close-up / insert）占比 ≥ 30%？**（低于 30% 报错）
- [x] **全片只有一种景别？**（观众会说"镜头语言死板"）
- [x] **连续 3 镜同景别**（**且同机位**——机位不同不算跳切）＝打回
- [x] **同一机位下角色左右翻转？**（越轴）
- [x] **镜头的机位有没有对应场景板？**（没有 = 场景会漂到别的店）

**建议确认**
- [x] **一集里 wide 有没有至少 2 次**（开场 + 结尾）？
- [x] **提示词里有没有焦段/机位锚点/运动词？**（只写景别 = 模型每次自己挑角度）

下面 4 项**代码查不了，要人眼过**：

- [ ] 每个场景的机位够 3–5 个？（`scenes[].angles` 的键数）
- [ ] 竖屏里有没有 side-by-side two-shot？（提示词里写着 side by side / standing next to each other 的）
- [ ] 说话镜里有没有手部动作？（有＝拆成 insert 镜）
- [ ] 运动镜头是不是只出现在 Master 上？

> 📌 **景别从哪儿认**：实测 ep11/ep12/ep13 三集 100 镜，`shot_size` / `camera` 字段**全是空的**，
> 景别是直接写在 `frame.prompt` 的 framing 句和 `video_prompt` 的时间码里。
> 所以 `check` 按 `shot_size` → `camera` → `frame.prompt`+`video_prompt` 的顺序去找，
> 三处都找不到才判"没写景别"。**新写的镜头表建议把 `shot_size` 字段填上**——
> 填了才能被机器稳定识别，也方便后面统计配比。

---

## 九、这套规则的出处

- 五决策、对话覆盖、180° 轴线、景别递进、转场分层：
  [`joost/ai-camera-shots`](https://github.com/joost/ai-camera-shots)（MIT），
  它的 34 种镜头类型源自 GenHQ × Magnific 的 shot prompt guide。
- 词汇量（70+ 机位 / 60+ 运动 / 80+ 打光 / 80+ 构图）：
  [`Rylaispirit/cinematic-video-prompt-skill`](https://github.com/Rylaispirit/cinematic-video-prompt-skill)。
- 一个短镜只给一个机位想法、镜头契约（起点/运动/速度/终点）：
  [`Emily2040/seedance-2.0` 的 `seedance-camera`](https://github.com/Emily2040/seedance-2.0)。
- 三机位法、越轴症状、机位模板：本 skill 的 `camera_setups.md`。
- 特写的像素上限、"特写靠推镜走到不靠切镜跳到"：本 skill 的 `camera_language.md`。
