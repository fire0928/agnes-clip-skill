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

## 六、负面约束

Agnes 没有独立 negative prompt，全部写成正向句子放结尾：

```text
No text, no watermark, no burned-in subtitles. No camera cuts. Avoid flat graphic colour bands, avoid CG look, avoid plastic skin, avoid identity drift.
```
