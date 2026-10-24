# 提示词模板（Agnes 2.5 Flash 版）

Agnes 2.5 flash 吃**自然英文**，不需要 H3 那套特殊措辞。核心是三段式：主体与镜头 → 时间轴动作 → 质感与约束。

## 一、首帧图提示词（agnes-image-2.5-flash）

结构：

```text
<场景与时间>，<人物服装>，<构图与景别>，<光线>，<氛围细节>。
Do NOT describe facial features. Keep the face, identity and hairstyle exactly as in the reference image.
```

示例：

```text
Night outside a convenience store, rain falling. The character stands under the awning in a beige trench coat over a white dress, holding a paper bag. Medium shot from a few meters away, shallow depth of field, warm store light behind her and cool blue street light in front. Wet pavement reflecting the signage. Do NOT describe facial features. Keep the face, identity and hairstyle exactly as in the reference image.
```

要点：
- **只写环境、服装、光线、构图**，不要写「大眼睛、尖下巴」——会和参考图打架。
- 景别用 `medium shot` / `medium-wide shot` / `waist-up medium shot`，不要 `extreme close-up`。
- 场景里写 3–5 个**看得见的实体**（地面反光、雨棚、招牌灯、纸袋、水洼），比写「氛围感」有效。

## 二、视频提示词（agnes-video-2.5-flash）

结构：

```text
One continuous shot, no cuts.
0-Ns: <动作 1>，<运镜 1>
N-Ms: <动作 2>，<运镜 2>，<微表情过程>
M-Zs: <收尾动作>，<运镜 3>
<台词口型段（有台词才写）>
<光线与质感一句话>
Audio: <现场声 1>, <现场声 2>
```

## 二点五、对白与口型（有台词必写）

固定写法，放在时间轴动作之后、质感之前：

```text
The character speaks in Mandarin Chinese with precise lip-sync: "<台词原句>" —
mouth shapes each syllable clearly, jaw and lips move naturally;
keep the face turned toward the listener or camera so the mouth stays visible.
```

三条硬要求：
1. 台词原句用英文双引号包住，一个字都不能改（TTS 和字幕都按它对齐）。
2. 这一镜必须是 **waist-up medium shot** 或 **medium close-up**，远景不写台词。
3. 说话前后各留 0.5 秒不说话：`0-0.5s silent, 0.5-4s speaks, 4-7s silent reaction`。

8 秒示例：

```text
One continuous shot, no cuts.
0-3s: She stands still under the awning, rain streaking past behind her, the camera slowly pushes in from a medium-wide shot.
3-6s: She turns her head slightly toward the street; her eyes shift first, then a faint tension appears at the corner of her mouth, the camera keeps pushing in to a waist-up medium shot.
6-8s: The camera eases back as she looks down at the folded umbrella on the ledge, rain catching the light in the foreground.
Natural night lighting, cinematic realism, shallow depth of field.
Audio: steady rain on the awning, distant traffic, a soft door chime.
```

## 三、运镜词表（Agnes 可用）

| 中文 | 英文写法 |
|---|---|
| 推近 | the camera slowly pushes in |
| 拉远 | the camera eases back / pulls back |
| 跟随 | the camera follows behind her |
| 侧移 | the camera tracks sideways |
| 环绕 | the camera arcs around her |
| 升降 | the camera rises / descends smoothly |
| 定点 | the camera holds a static frame |
| 手持感 | a subtle handheld sway |

一镜最多 2–3 段运镜组合，不要一段里堆 4 个。

## 四、微表情写法

| 不要写 | 改写成 |
|---|---|
| she smiles | a faint smile begins at the corner of her mouth, then reaches her eyes |
| she is sad | her gaze drops, her lower lip tightens slightly, then releases |
| she is surprised | her eyes widen first, her breath catches, then her brows lift |
| she is angry | her jaw sets, her nostrils flare once, her eyes stay fixed |

## 五、写作禁忌

| 不要写 | 因为 |
|---|---|
| `cut to` / `jump cut` / `shot 2` | 硬切导致人脸重建崩坏 |
| `extreme close-up` / `face fills the frame` | 脸部像素不足，必糊 |
| `violet neon glow` / `colour LED bands` | 生成平面色带，没有空间感 |
| `she has big eyes and a sharp chin` | 与首帧图冲突，中途换脸 |
| `epic, stunning, masterpiece` | 对画面没有约束力 |
| 一镜 4 段以上运镜 | 模型混乱、画面抽搐 |
| 一镜 5 个以上表情 | 表情僵硬 |

## 五点五、地域与时代锁定（**最重要的一条**）

扩散模型对"东亚"有很强的默认先验。你不明确写，它会给你**日式**——
木结构町屋、纸灯笼、鸟居、榻榻米、和式庭院。

**实测踩过**：写 `An old city street corner at dusk`，出来的是日式町屋 + 灯笼，
完全不是中国现代城市。

**凡是中国当代题材，首帧提示词里必须带上这四句**（位置：场景描述之后、人物描述之前）：

```text
Setting: contemporary mainland China, modern Chinese city.
Architecture and props are modern Chinese, NOT Japanese.
No Japanese-style architecture, no wooden machiya townhouses, no paper lanterns,
no torii gates, no tatami, no kimono, no shrine elements.
```

| 想要的 | 写 | 别写 |
|---|---|---|
| 中国老街 | `old Chinese alley, mid-20th-century Chinese brick housing, red lanterns, Chinese signage` | `old Asian street`（会出日式） |
| 中国现代都市 | `contemporary Chinese city, glass high-rises, Chinese street signs` | `Asian metropolis` |
| 中国乡村 | `rural Chinese village, whitewashed brick walls, tiled roofs` | `Asian countryside` |
| 中国古风 | `ancient Chinese town, Ming-dynasty wooden architecture, Chinese courtyard` | `ancient Asian village` |

**人物也不能是日式**：中国人物要写 `East Asian Chinese`，服饰要写具体的中式单品
（`Chinese-style cotton-linen shirt` / `cheongsam` / `Chinese wool coat`），
不要写 `traditional Asian attire`（会出和服/韩服）。

## 六、负面约束

Agnes 没有独立 negative prompt，全部写成正向句子放结尾：

```text
No text, no watermark, no burned-in subtitles. No camera cuts. Avoid flat graphic colour bands, avoid CG look, avoid plastic skin, avoid identity drift.
```

**当代中国题材还要加**：

```text
No Japanese-style architecture, no wooden townhouses, no paper lanterns, no torii gates, no tatami, no kimono.
```

## 六点五、🔴 比喻和抽象词会被照字面执行（v1.22.0 实测）

**模型不懂比喻，只懂字面。** 你写"a small puff of steam rising from the freshly dug earth
**as if a plan has already been made**"，它会把那股白烟画出来——
泥土里凭空冒烟，观众一看就是穿帮（ep05 S05 真实事故，用户一眼看穿）。

| 你写的（比喻/抽象） | 模型画出来的（字面） | 应该怎么写 |
|---|---|---|
| `a puff of steam rising from the earth`（暗示"心里有底了"） | **地面冒白烟** | 删掉；要表达"有主意"用微表情：`his eyes narrow with quiet determination` |
| `the fire of ambition in his eyes` | 眼睛里冒火 | `his eyes sharpening, jaw setting` |
| `the silence was deafening` | —（这个还行，但别指望） | 直接写动作：`nobody moves, nobody speaks` |
| `ideas sprouting`（暗示灵感冒出） | **地上长出绿芽** | `he taps a leaf thoughtfully` |
| `time seemed to stop` | 画面卡住 | `everything freezes, dust hanging in the light`（这个可以，因为是画面语言） |

**规则**：

1. **情绪用微表情和动作承载，不用自然现象暗示。**
   「他有了主意」→ 写眼睛和嘴角，不要写烟、火、光、芽。
2. **不确定某句会不会被画出来时，问自己：这句话能变成一张图吗？**
   能，而且你不想让它出现，就删掉。
3. **要"没有"某样东西，必须显式写。**
   模型默认会加氛围感——写 `There is NO smoke, NO steam, NO vapour rising from the ground`
   比不写安全得多（野地场景尤其如此，它很爱加雾气）。

## 六点六、🔴 植物/食材的形态必须写死（v1.22.0 实测）

**模型对"白色根茎"有强先验：默认画成人参/胡萝卜形**——粗、长、直、圆锥。
用户原话：「拔鱼腥草的时候，根是不是，这像人参了，要参考鱼腥草的图片来生成啊。」

| 食材 | 模型默认画成 | 真实形态（要写进提示词） |
|---|---|---|
| 折耳根/鱼腥草 | 人参（粗长直） | **细、短、弯、有节**：长 3-5cm、比铅笔芯细、微弯、一节一节像串珠、须根细密分叉 |
| 紫苏 | 大圆叶 | 心形、边缘锯齿、紫绿两面、叶脉凸起 |
| 香椿 | 普通绿叶 | 羽状复叶、小叶边缘有浅锯齿、正面绿背面浅 |
| 蕨菜 | 普通野草 | 拳卷状嫩芽（问号形）、成熟后羽状分裂 |

**写法模板**（三件套，缺一不可）：

```text
<食材> has <尺寸 + 粗细>，<形状（直/弯/分叉）>，<表面特征（节/毛/纹）>，
<颜色与质地>。 The roots are NOT thick, NOT long, NOT straight,
NOT carrot-shaped and NOT ginseng-shaped.
```

**并且必须喂道具参考图**：文字描述再准，模型也画不准中国地方食材
（见 `human_and_props.md` 第二部分）。图是唯一的事实来源。

## 六点七、🔴 火与灶的结构必须写死（v1.22.0 实测）

**模型对"火 + 锅"的默认构图是：火苗从锅正中心直窜上来。**
用户原话：「搭建完灶之后竟然在锅中间烧火了」。

真实野外石灶：**石头围成一圈 → 圈内侧留通风缝 → 锅被圈上的石头托住架高 →
火在圈下方的空隙和石头缝里烧**。

```text
The stove is a rough ring of flat grey river stones standing on the grass,
with gaps between the stones so air can pass through.
The black iron wok sits ON TOP of the stone ring, resting on the upper stones,
raised above the ground with open space beneath it.
The fire burns BELOW the wok, in the open space under the ring and through the
gaps between the stones — the flames are never directly underneath the centre
of the wok in a solid column, and there is no fire inside the wok itself.
```

**铁律**：凡是画面里有"灶/锅/火"，都要写清**三者的空间关系**
（锅在哪、火在哪、支撑是什么）。只写 `over a roaring fire` 模型就自己发挥，
而它默认的发挥就是「火在锅正中间」。

## 六点八、🔴 运动方向必须和人的朝向一致（v1.22.0 实测）

**症状**：车/船/人往左走，画面里的人却转头看同伴或看镜头——
观众一眼看出"方向不对"，非常别扭。用户原话：「第一个分镜里面，车子与猫哥的方向相反，显然错了」。

**根因**：提示词里写了**人物关系句**——`The two characters face each other,
their eyes meet on each other's face`——这句在静态对话镜里是对的，
但在**有运动载具/有行进方向**的镜里，它会逼着人转头，于是和行进方向矛盾。

**规则**：

| 镜头类型 | 人物朝向怎么写 |
|---|---|
| 对话镜（原地站着） | ✅ `face each other, eyes meet` |
| **载具/行进镜** | ❌ 绝不要 `face each other`！要写： |
| | `Both characters face FORWARD in the same direction the vehicle is travelling` |
| | `he does NOT turn his head back, does NOT look at the passenger, does NOT look at the camera` |

**模板**（载具镜专用）：

```text
Both characters face FORWARD in the same direction the <载具> is travelling,
looking <去向>. The driver keeps his head and eyes turned forward along the
direction of travel; he does NOT turn his head back, does NOT look at the
passenger, and does NOT look at the camera. The passenger also looks forward,
her head angled the same way the <载具> is moving.
```

视频提示词同步：`rides into frame moving AWAY from the camera down the lane,
his head and eyes fixed forward down the lane, never turning back`。

> **同源坑**：走路、骑车、划船、开车、坐车——**所有有行进方向的镜头**，
> 人物眼神都要锁在行进方向上。想要"回头看"的戏，单独给一镜。



