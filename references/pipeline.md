# 全流程：从一句话到成片 + 审计

这条流水线把「一句话创意」拆成 9 个可验收的步骤。每一步都有固定输入、固定产物、固定检查点，任何一步都能单独重跑。

```
剧本 → 分镜拆解 → 场景扩写/场景图 → 角色提词/多视角图 → 首帧图 → 视频 → 质检 → 合成 → 成片+审计
```

## 首次配置（只做一次）

```bash
python scripts/ac.py config-ui
```

一个本地页面（127.0.0.1）配齐全部可调项：推理来源、生图渠道、生视频通道和并发/轮询、重试策略、配音音色（可试听）、配乐 ComfyUI、ffmpeg 路径。每块都能当场测试连接，保存进 `~/.workbuddy/agnes-clip.json`。

## 1. 一句话创意

输入：一句中文创意 + 想要的镜头数。
产物：项目目录（`ac.py init`）。

```bash
python scripts/ac.py init "<dir>" --title "第三碗面"
```

## 1. 剧本生成

输入：创意 + 基调（温暖/悬疑/爽感…）。
产物：`script/story.md`（人读剧本）。

编剧必须写清楚：场景四要素（时间/地点/天气/光源）、这一镜唯一的动作、微表情过程、对白、说话人。
基调规则：要温暖治愈，结尾必须落在重逢/和解/希望，不用死亡苦情收尾。

## 2. 分镜拆解

产物：`script/shots.json`（机器读镜头表）。

每镜字段：`scene / char / shot_size / camera / action / micro / speaker / line / frame / video_prompt`。

**时长自动计算**，不靠模型拍脑袋：

```
台词秒数 = 中文字数 ÷ 4.2 + 1.2（起收气口）
动作秒数 = beat 数 × 1.7 + 景别空间
  · wide / medium-wide 多给 1.6–2.2 秒
  · medium 1.2 秒
  · close-up 0.6 秒
最终时长 = clamp(4, 12, max(台词秒数 + 1.0, 动作秒数))
```

景别与运镜要有变化：wide / medium-wide / waist-up / medium close-up 轮换；推近、拉远、跟随、环绕、升降、手持、定点换着用。对话镜头必须是腰以上，保证嘴部可见。

## 3. 场景扩写 + 场景图（按场景，不按镜头）

输入：`scene.id` + 场景四要素。
产物：`assets/scenes/<scene_id>.jpg`（一个场景一张）。

```bash
python scripts/ac.py scene-gen "<dir>"
```

**同一个场景的所有镜头共用一张场景板**，只换机位和景别，不换布景。小场景对话尤其要锁死，否则每镜换一张背景，画面会假、会跳。

分镜里用 `scene.id` 区分场景（全片 1–3 个），例如 `shop`（店内）、`door`（门口）。首帧生成时，场景板作为第二张参考图，并明确要求“同一地点、同一陈设与光线，只改变机位”。

## 4. 主角提词 + 主角图（多视角）

输入：角色的中文/英文形象描述（来自 `characters[]`）。
产物：`assets/characters/<name>/source.jpg`、`face_ref.jpg`、`turnaround.jpg`。

```bash
python scripts/ac.py char-gen "<dir>" --name xiao-man --tri
```

- `source.jpg`：定妆图
- `face_ref.jpg`：锁脸锚点（就是定妆图，零漂移）
- `turnaround.jpg`：正面/侧面/背面三视图，用于确认形象、扩展镜头

已有真人照片时用 `char-add` 导入，跳过生成。

## 5. 首帧图

输入：`face_ref.jpg` + `assets/scenes/<sid>.jpg` + `frame.prompt`。
产物：`frames/S01.jpg …`

```bash
python scripts/ac.py frame "<dir>" [--only S01] [--force]
```

首帧 = 人物（参考图锁脸）+ 场景（场景图锁环境）+ 动作姿势（提示词）。
`frame.mode = "source"` 表示直接用定妆图；`swap` 表示换场景/服装生成。

## 6. 视频

输入：首帧图（base64 data URI）+ `video_prompt` + 时长。
产物：`clips/S01.mp4 …`

```bash
python scripts/ac.py video "<dir>" [--wait] [--only S01]
```

- 模型：`agnes-video-2.5-flash`，固定 720P，竖屏 704×1280
- 单段 4–12 秒，超过要拆镜头
- 账号限制：3 路并发、30 秒轮询一次（脚本自动排队）
- 队列满（503）自动退避 + 回队列，最多 10 轮
- 有台词镜头：提示词里带台词原句 + 口型同步指令

## 7. 质量检查（审计）

```bash
python scripts/ac.py audit "<dir>"
```

产物：`AUDIT.md` + `audit.json`。

逐镜检查：

| 检查项 | 方法 | 不合格处理 |
|---|---|---|
| 场景图 / 首帧 / 片段是否存在 | 文件检查 | 标记缺失，重跑对应步骤 |
| 实际时长 vs 计划时长 | ffmpeg 读取 | 相差 >1.5s 标记 |
| 分辨率 / 帧率 | ffmpeg 读取 | 不是 704×1280 / 24fps 标记 |
| 是否有音轨 | ffmpeg stream 检查 | 无音轨标记 |
| 有台词镜头是否真的有人声 | VAD（能量 + 基频周期性） | 检测不到标记 |
| 角色三视图 | 文件检查 | 缺失标记 |
| 成片 | 文件检查 | 缺失标记 |

报告还会给出：资产清单、逐镜核对表、问题列表、成本估算（秒数 × 单价）。

## 8. 合成

```bash
python scripts/ac.py assemble "<dir>"          # 默认：不加字幕，保留原声
python scripts/ac.py assemble "<dir>" --subs   # 需要字幕时
```

合成规则：

- 片段可能有/无音轨，脚本会自动补静音后拼接
- 有配乐时压低原声到 0.4；有 TTS 时压到 0.22；都没有则保留原声 1.0
- 字幕**只在合成阶段生成**：先做 VAD 找真实说话区间，再把每句字幕卡进去；检测不到人声就跳过
- 输出 `out/final.mp4`（H.264 + AAC，faststart）

## 9. 成片 + 审计

产物：

```
out/final.mp4     成片
AUDIT.md          审计报告（人读）
audit.json        审计原始数据（机器读）
```

## 一键跑完

```bash
python scripts/ac.py auto "<dir>" --idea "..." --shots 10
```

`auto` 依次执行：剧本 → 角色（含三视图）→ 道具 → 场景图 → 首帧 → 视频 → 合成 → 审计。
已存在的产物自动跳过，中断后重跑只补缺的部分。

## 目录总览

```
<project>/
├── script/
│   ├── story.md              剧本（场景/动作/微表情/对白）
│   └── shots.json            镜头表（含时长、景别、运镜、台词）
├── assets/
│   ├── characters/<name>/    source.jpg + face_ref.jpg + turnaround.jpg
│   ├── props/<name>.jpg      道具图
│   └── scenes/S01.jpg        每镜空场景图
├── frames/S01.jpg            首帧
├── clips/S01.mp4             片段
├── audio/vo/S01.mp3          台词配音（可选）
├── audio/bgm.mp3             配乐（可选）
├── out/final.mp4             成片
├── AUDIT.md                  审计报告
└── audit.json                审计数据
```
