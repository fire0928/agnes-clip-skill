# 微表情库

## 为什么需要单独写

模型默认给的"笑"是**定格的笑**——嘴角上扬、保持不动，像照片。真人不是这样的：笑意有起势、有到达、有收住，眼睛和嘴角不同步。

要让人"活"，必须在提示词里写成**过程**，而不是状态。

## 三条规则

1. **只在近景写**。中远景写微表情没用，看不见，反而占用了本应描述动作的篇幅。
2. **一个镜头最多 2–3 个微表情**。写多了模型会混，表情变僵硬。
3. **写成动作序列，不写成形容词**。`a faint smile begins at the corner of her mouth, then reaches her eyes` 优于 `she smiles warmly`。

## 表情库（可直接抄）

### 眼神

| 效果 | 英文写法 |
|---|---|
| 直视镜头 | `her eyes lift and hold direct eye contact with the lens` |
| 眼神软化 | `her gaze softens as she looks into the lens` |
| 先垂眼再看 | `her eyes drop for a moment, then rise back to the camera` |
| 眼神游移 | `her gaze drifts slightly to the side, then returns` |
| 眼眶微红 | `her eyes glisten, a faint sheen at the lower lid`（慎用，容易做过头） |
| 眨眼 | `she blinks slowly, once` |
| 睫毛投下阴影 | `her lashes lower, casting a soft shadow on her cheek` |
| 目光追物 | `her eyes follow something off-screen, then settle back on the lens` |

### 笑意（重点）

| 层次 | 英文写法 |
|---|---|
| 极浅 | `a faint smile begins at one corner of her mouth` |
| 逐渐展开 | `the smile spreads slowly, softening her whole face` |
| 笑意到眼底 | `the smile reaches her eyes, delicate lines appearing at the outer corners` |
| 忍笑 | `she presses her lips together, holding back a smile` |
| 笑出声前 | `her shoulders lift with a suppressed laugh, lips parting slightly` |
| 笑后收住 | `the smile fades gradually, her lips returning to rest` |
| 抿笑 | `she bites her lower lip lightly, eyes still smiling` |

### 呼吸与身体

| 效果 | 英文写法 |
|---|---|
| 深呼吸 | `her chest rises with one slow breath, then settles` |
| 放松肩膀 | `her shoulders drop slightly as she relaxes` |
| 轻微点头 | `she gives a barely perceptible nod` |
| 头部微倾 | `she tilts her head a few degrees to one side` |
| 吞咽 | `she swallows once, her throat moving` |
| 呼气可见 | `her breath fogs faintly in the cold air`（冷场景专用） |

### 头发与风（免费的真实感）

| 效果 | 英文写法 |
|---|---|
| 发丝拂面 | `a strand of hair lifts across her cheek` |
| 风掀发梢 | `the wind lifts the ends of her hair` |
| 手拢头发 | `she tucks a loose strand behind her ear, unhurried` |
| 睫毛沾雨 | `fine raindrops cling to her lashes`（雨天专用） |

## 组合模板（按情绪选一条）

**A. 温柔治愈**（写真最常用）
```text
her eyes soften as she looks into the lens, a faint smile begins at the corner of her mouth and slowly reaches
her eyes, a strand of hair lifting across her cheek.
```

**B. 克制的难过**
```text
her eyes drop for a moment, then rise back to the camera; she presses her lips together and swallows once,
the smile never quite arriving.
```

**C. 惊喜 / 开心**
```text
her eyes widen slightly, then her smile spreads quickly and reaches her eyes, her shoulders lifting with a
small suppressed laugh.
```

**D. 神秘 / 若有所思**
```text
her gaze drifts off to the side, then returns to the lens; she tilts her head a few degrees, one corner of
her mouth just barely lifting.
```

**E. 释然**
```text
she lets out one slow breath, her shoulders dropping, and a quiet smile settles on her face without reaching
for anything.
```

## 实测结论与未验证项

| 项 | 状态 |
|---|---|
| `smiles softly` / `warm confident smile` / `direct eye contact` | ✅ 实测有效（走秀四段，近景可见自然笑容） |
| `looks into the lens, slight head tilt` | ✅ 实测有效 |
| `a faint smile begins at the corner of her mouth, then reaches her eyes` | ⚠️ 未单独验证，机制上合理（写成了过程而非状态） |
| 眨眼、吞咽、眼眶微红 | ⚠️ 未验证，10 秒镜头内可能来不及表现 |
| 忍住笑、笑出声前 | ⚠️ 未验证，风险较高（涉及上半身动作联动） |

**建议**：第一次用某个新表情时，先只跑一个 5 秒镜头验证，通过了再批量套用到全片。

## 反面写法

| 不要写 | 原因 |
|---|---|
| `she smiles` | 定格笑，假 |
| `beautiful expression` | 抽象，无约束力 |
| `emotional, touching` | 是观众感受，不是人物动作 |
| 一个镜头塞 5 个表情 | 模型混乱，表情抽搐 |
| 在中远景写"眼角细纹" | 看不见，纯浪费 token |
