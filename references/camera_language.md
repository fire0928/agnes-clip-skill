# 镜头语言库

## 核心原则

**所有镜头语言都必须在一个连续长镜头内完成，禁止切镜。**

"丰富运镜"≠"多切镜头"。切镜会让模型在高分辨率下重建人脸，必崩。想要层次，靠**运镜组合**：一个 10 秒镜头里连续做 2–3 段运动（推、拉、环绕、升降），而不是切 3 个机位。

## 可用运镜（英文写法，直接抄）

| 镜头语言 | 英文写法 | 适用 | 风险 |
|---|---|---|---|
| **航拍俯冲** | `the camera starts as an aerial drone shot high above <场景>, then descends smoothly toward her` | 开场交代大环境 | 高。跨度大，必须"连续下降"到中景，不能直接切人 |
| **航拍环绕** | `the camera circles high above in a slow aerial orbit, looking down at her` | 大场景收尾 | 中 |
| **推镜** | `the camera pushes in slowly and steadily` | 情绪递进、走向人物 | 低 ✅ 最稳 |
| **拉镜** | `the camera pulls back smoothly, revealing <环境>` | 收尾、离开感、交代空间 | 低 ✅ |
| **环绕** | `the camera arcs around her in a slow orbit, revealing <环境>` | 展示人物与环境关系 | 低 ✅ |
| **跟随** | `the camera tracks alongside her at walking pace` | 走路、行进 | 中 |
| **后退跟拍** | `the camera tracks backward ahead of her as she approaches` | 主动走向镜头 | 中 |
| **升降** | `the camera rises slowly on a crane, revealing <场景全貌>` | 宏大收尾 | 中高 |
| **手持跟随** | `handheld camera follows her with subtle natural shake` | 纪实感、临场感 | 中 |
| **侧移** | `the camera slides laterally to the right, keeping her centred` | 过渡、展示纵深 | 低 |
| **低角度** | `low angle looking up at her` | 气势、力量 | 低 |
| **定点** | `locked-off static camera` | 极简、静默 | 无 |

**慎用**：
- `zoom in / zoom out`（光学变焦）：和 dolly 效果不同，模型容易做得像"拉近图片"，画质会糊。优先用 dolly。
- `whip pan`（甩镜）：多数生成模型处理不好，容易整段糊。

## 10 秒内的运镜组合公式

一个镜头最多组合 2–3 段运镜，超过 3 段模型会混乱。

| 用途 | 组合 | 时段分配 |
|---|---|---|
| **开场 / 建置** | 航拍俯冲 → 推镜 → 停在中景 | 0-4 航拍下降 / 4-7 推近 / 7-10 缓推收住 |
| **情绪递进** | 中景 → 推镜到近景 → 微停 | 0-3 中景 / 3-7 推近 / 7-10 停住不动 |
| **展示关系** | 环绕 → 拉镜 | 0-5 环绕 / 5-8 拉远 / 8-10 收住 |
| **行进感** | 后退跟拍 → 侧移 → 环绕 | 0-4 后退 / 4-7 侧移 / 7-10 环绕 |
| **宏大收尾** | 拉镜 → 升降 | 0-5 拉远 / 5-9 升起 / 9-10 定格 |
| **静默凝视** | 定点 → 极缓推 | 0-6 定点 / 6-10 极缓推近 |

## 特写怎么写（重要）

**可以写特写，但只能写 `medium close-up (head and shoulders)`，不能写 `extreme close-up`。**

| 写法 | 结果 |
|---|---|
| `extreme close-up on her eyes, face fills the frame` | ❌ 脸占满画面，像素不够，必崩 |
| `close-up`（含糊） | ⚠️ 模型可能理解成怼脸 |
| `medium close-up, head and shoulders, face fills about one third of the frame` | ✅ 安全，脸够大但不失控 |
| 靠推镜到达：`the camera pushes in to a medium close-up` | ✅ 最佳，有过程有细节 |

**特写必须靠推镜"走到"，不能靠切镜"跳到"。** 建议把特写放在镜头的 5–9 秒，即人物已经稳定运动之后。

## 航拍怎么写（重要）

航拍是全片风险最高的运镜，规则：

1. **首帧机位必须匹配运镜起点**（最容易踩的坑）。首帧图是"自拍近景"，就不能要求"镜头从高空下降"——第一帧被锁死在近景，模型却要执行航拍下降，会在过渡段产生重影/拉伸/糊帧。实测：S01 用自拍近景+航拍俯冲，第 2 帧出现明显重影。
   - 要航拍进场：首帧必须本身就是**远景/航拍视角**（用 `t2i` 单独生成一张"俯视海滩，远处有个小小的白色身影"）
   - 要人物近景起手：只能用**推镜/拉镜/环绕**，不要航拍
2. **必须连续下降**，不能"航拍 → 切到人物"
   ```text
   the camera starts as an aerial drone shot high above the ancient pagoda, then descends smoothly and continuously
   down toward the woman standing in the plaza, settling into a medium-wide shot
   ```
3. **人物在画面里要一直可见**（哪怕很小），模型才不会"重新造一个人"
4. **单镜头里只用一次航拍**，不要在一段里既航拍又贴脸
5. 航拍段建议占 3–4 秒，下降过程本身就消耗时长
6. **安全的航拍用法是"离开"**：近景 → 拉远 → 升起（S10 那种），方向是远离，不会撞机位；风险高的是"俯冲逼近"

## 景别变化的硬限制

| 变化 | 允许度 |
|---|---|
| 中远景 → 腰以上中景 | ✅ 安全（2 倍以内） |
| 腰以上中景 → 头肩特写 | ✅ 可以（1.5 倍） |
| 航拍大远景 → 中景 | ⚠️ 仅限"连续下降" |
| 中远景 → 怼脸特写 | ❌ 禁止 |
| 航拍 → 头肩特写（无过渡） | ❌ 禁止 |

## 全片镜头语言分配建议

一条 10–12 个镜头的短片，建议这样铺，保证"丰富"但不重复：

| 镜头 | 语言 | 作用 |
|---|---|---|
| S01 | 航拍俯冲 → 推镜 | 建置，交代时空 |
| S02 | 后退跟拍 → 环绕 | 人物出场、行进 |
| S03 | 低角度推镜 → 头肩特写 | 第一次情绪接触 |
| S04 | 跟随 → 侧移 | 市井/环境游走 |
| S05 | 环绕 → 拉镜 | 展示空间纵深 |
| S06 | 定点 → 极缓推 | 静默、压迫感 |
| S07 | 推镜 → 微停特写 | 情绪高点 |
| S08 | 侧移 → 拉镜 | 转折 |
| S09 | 跟随 → 环绕 | 流动感 |
| S10 | 拉镜 → 升降航拍 | 收尾，抽离 |

同一运镜连续出现不要超过 2 次，避免节奏单调。
