# -*- coding: utf-8 -*-
"""流程引擎：把「一句话创意 → 成片」拆成 9 个显式阶段。

🔴 为什么做这个（2026-10-24 用户反馈）：
> 「一定要流程化，从最开始分析需求，确认方案，然后编剧，拆分镜，
>   这些都要一步步的显示出来给用户看到，而且用户随时可以更新需求的。
>   然后再生成角色，都要显示出来给用户看到真实的图片及进度，
>   然后还要把首帧图也显示出来，
>   之前的情绪分析这些咋没有了呢，怎么就弄丢了呢？逻辑也乱了。」

三个核心问题：
1. **不透明** —— 一条 `auto` 命令跑完，用户中间什么都看不到
2. **不可改** —— 想改需求只能重头再来
3. **丢了分析** —— logline/情绪曲线/母题/因果链这些分析产物
   散在 shots.json 字段里，没有一份**给人看的分析报告**

所以本模块提供：
- **9 个阶段**，每阶段独立、可单独重跑（`--from`）、可回退（`--back`）
- **每阶段落盘产物**，下一个阶段读上一个阶段的产物
- **每阶段一份人读报告**（`report/brief.md` / `report/story.md` / …）
- **阶段状态**记在 `script/_flow.json`，进度一目了然
- **需求可改**：改完 `brief.md` 里的任何一行，`--from story` 重跑即可
"""
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from ac import load_json, save_json  # noqa: E402
except Exception:  # pragma: no cover
    def load_json(p, default=None):
        try:
            with io.open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def save_json(p, obj):
        with io.open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False, indent=1))

# ---------------------------------------------------------------- 阶段定义
# key / 显示名 / 产出物（相对项目目录）/ 一句话说明
STAGES = [
    ("init",     "① 建项目",     ["project.json", "script/"],
     "搭好目录骨架，写入项目配置"),
    ("brief",    "② 需求分析",   ["script/brief.md"],
     "六行工单 + logline 四要素 + 情绪曲线 + 母题 + 出场表 —— 给你确认的"),
    ("story",    "③ 编剧",       ["script/story.md"],
     "把工单写成有场景有动作有对白的故事"),
    ("shots",    "④ 拆分镜",     ["script/shots.json"],
     "故事拆成逐镜分镜表，每镜填满四个空"),
    ("check",    "⑤ 逻辑自检",   ["report/check.md"],
     "因果链 / 情绪曲线 / 问答闭环 / 结构硬伤 —— 不过不许往下跑"),
    ("cast",     "⑥ 角色定妆",   ["assets/characters/"],
     "生成正脸 + 三视图 + 角度图"),
    ("props",    "⑦ 道具与场景", ["assets/props/", "assets/scenes/"],
     "菜品/食材参考图 + 空场景板"),
    ("frame",    "⑧ 首帧",       ["frames/"],
     "逐镜首帧图（这是画面的唯一真源）"),
    ("video",    "⑨ 视频",       ["clips/"],
     "首帧 → Agnes 出片"),
    ("assemble", "⑩ 合成成片",   ["out/"],
     "拼接 + 配乐 + 音效 + 字幕 + 混音"),
]

STAGE_KEYS = [s[0] for s in STAGES]
STAGE_BY_KEY = {s[0]: s for s in STAGES}


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def state_path(paths):
    return os.path.join(paths["root"], "script", "_flow.json")


def report_dir(paths):
    d = os.path.join(paths["root"], "report")
    os.makedirs(d, exist_ok=True)
    return d


def load_state(paths):
    return load_json(state_path(paths), {"stages": {}, "history": []}) or {"stages": {}, "history": []}


def save_state(paths, st):
    save_json(state_path(paths), st)


def mark(paths, key, status="done", note="", artifacts=None):
    """记一个阶段的状态。"""
    st = load_state(paths)
    st.setdefault("stages", {})[key] = {
        "status": status,
        "at": _now(),
        "note": note,
        "artifacts": artifacts or [],
    }
    st.setdefault("history", []).append({"stage": key, "status": status, "at": _now(), "note": note})
    save_state(paths, st)
    return st


def stage_done(paths, key):
    st = load_state(paths)
    return (st.get("stages") or {}).get(key, {}).get("status") == "done"


def reset_from(paths, key):
    """把 key 及其之后的阶段标成 pending（需求改了要重跑）。"""
    st = load_state(paths)
    idx = STAGE_KEYS.index(key)
    for k in STAGE_KEYS[idx:]:
        (st.get("stages") or {}).setdefault(k, {})["status"] = "pending"
    save_state(paths, st)


def write_report(paths, key, title, blocks):
    """写一份人读报告。blocks = [(小标题, 正文)]"""
    d = report_dir(paths)
    p = os.path.join(d, key + ".md")
    L = ["# %s\n" % title, "> 生成时间：%s\n" % _now()]
    for h, body in blocks:
        L.append("## %s\n" % h)
        L.append(body.rstrip() + "\n")
    with io.open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return p


def progress_line(key, status, note=""):
    """给用户看的单行进度（CLI 打印）。"""
    icon = {"done": "✓", "running": "…", "pending": "·", "failed": "✗"}.get(status, "·")
    label = STAGE_BY_KEY.get(key, (key, key))[1]
    return "  %s %-14s %s" % (icon, label, note)


def print_flow(paths):
    """打印整条流程的进度表。"""
    st = load_state(paths)
    stages = st.get("stages") or {}
    print("")
    print("  流程进度 ─────────────────────────────────────────")
    for k, label, arts, desc in STAGES:
        rec = stages.get(k) or {}
        status = rec.get("status", "pending")
        note = rec.get("note") or desc
        at = rec.get("at", "")
        print(progress_line(k, status, "%s%s" % (note, ("  [%s]" % at) if at else "")))
    print("  ──────────────────────────────────────────────────")
    cur = next((k for k in STAGE_KEYS
                if (stages.get(k) or {}).get("status") != "done"), None)
    if cur:
        print("  下一步：%s（ac.py flow <项目> --stage %s）"
              % (STAGE_BY_KEY[cur][1], cur))
    else:
        print("  全部完成 🎉")
    print("")


def brief_template(cfg, paths, idea, n_shots, seconds):
    """生成需求分析工单模板（用户可编辑）。"""
    st = load_state(paths)
    old = ""
    bp = os.path.join(paths["root"], "script", "brief.md")
    if os.path.exists(bp):
        with io.open(bp, encoding="utf-8") as f:
            old = f.read()
    total = int(n_shots * float(seconds))
    tpl = """# 需求分析 · 剧本工单

> 这一份是**给你确认和修改**的。改完任何一行，跑
> `ac.py flow <项目> --from story` 就能按新需求重写剧本。
> 状态：`{status}`（已确认填 ✅）

---

## 一、一句话创意

{idea}

- 目标：**{n} 镜 / 约 {total} 秒**
- 题材：____________（温情 / 美食 / 悬疑 / 喜剧 / 社会现实…）
- 受众：____________

---

## 二、六行工单（**必填，空着就别往下走**）

```text
我想让观众感觉到：
主角想要：
他的阻碍：
最后他变成了：
必须出现的画面：（最多 3 个，多了就散）
绝对不能出现的：
```

---

## 三、logline 四要素

格式：**谁 + 想要什么 + 遇到什么阻碍 + 最后变成什么**

```
谁 =
想要什么 =
阻碍 =
最后变成什么 =
```

> ❌ 反例：「一个猫去乡下野炊做折耳根」——只有做什么，没有变化
> ✅ 正例：「猫哥想在乡下给朋友们露一手做折耳根，结果挖了老乡的地被讹钱，
>    最后用一盘菜把讹人的人变成了常客」

---

## 四、情绪曲线表（先排完再写镜头）

| 镜 | 强度 | 作用 | 说明 |
|---|---|---|---|
| S01 | +1 | 推进 | |
| S02 | | | |

规则：
- 至少一个**最低点**（谷）——通常在 60%-75% 处
- 至少一个**最高点**（峰）——一般最后 1-2 镜
- **禁止连续三镜同值**
- **锯齿型 > 平推型**（真实节奏本来就有起伏，一路平推反而假）

---

## 五、母题（motif）

一个**具体物件或动作**贯穿全片：首镜出现、末镜回应。

```text
母题 =
首镜怎么出现：
末镜怎么回应：
```

| 类型 | 例子 |
|---|---|
| 物件 | 一把带泥的折耳根（开头在坡上，结尾夹进别人碗里） |
| 动作 | 猫哥的手（开头翻草丛，结尾给别人盛饭） |
| 一句话 | 开头说一半，结尾说完 |

---

## 六、出场表

| 角色 | 物种 | 功能定位 | 首次出场 | 必有名词/动作 | 音色 |
|---|---|---|---|---|---|
| maoge | 拟人动物 | 主角 | S01 | — | |
| | | | | | |

> 🔴 **每个角色都要填「必有名词/动作」**——
> 填不出来的角色要么给他一句台词，要么让他别出现（纯凑人数会被模型画丢）。

---

## 七、场景与机位

| 场景 id | 地点 | 时间 | 天气 | 光源 | 机位 |
|---|---|---|---|---|---|
| | | | | | |

> 同一场景的所有镜头**共用一个 scene.id**，只换机位不换布景。

---

## 八、本集硬规矩

- 结尾必须落在**具体肢体动作**上，不能是「两人站着说完最后一句」
- 炒菜/做菜段**零台词**（让观众「看饿了」）
- 台词 ≤ 18 字，口语化、有潜台词
- 每镜一个具体动作，禁止连续两镜「站着看」
- **问了就必须有人答，且答的是同一个问题**
- **冲突方不能天降**（前面要有界碑/标牌/台词线索）
- **人跑了就要交代怎么回来的**

---

## 九、确认

- [ ] 我看过这份工单，同意按它写剧本
- [ ] 需要改的地方已改在上面

确认后跑：`ac.py flow <项目> --from story`
"""
    # ⚠️ 用 .format() 而不是 % 格式化——模板里有大量 % 符号（提示语、母题说明），
    #    用 % 会因为「% 后面不是合法转换符」直接抛 TypeError。
    tpl = tpl.format(
        status=st.get("stages", {}).get("brief", {}).get("status", "pending"),
        idea=idea, n=n_shots, total=total)
    with io.open(bp, "w", encoding="utf-8") as f:
        f.write(tpl)
    return bp
