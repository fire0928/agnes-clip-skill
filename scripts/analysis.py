# -*- coding: utf-8 -*-
"""剧本分析报告：把散在 shots.json 字段里的分析结果，变成**给人看的一份报告**。

🔴 为什么做这个（2026-10-24 用户反馈「之前的情绪分析这些咋没有了呢，怎么就弄丢了呢」）：
   情绪曲线、logline 四要素、母题回环、因果链这些**一直在 shots.json 里**，
   但——① 没有一份专门给人看的报告；② 报告里也没有「分析结论」，
   只��罗列字段。用户看不到「这一集的情绪是怎么走的」「逻辑闭合了没有」。
   所以本模块做两件事：
   1. 生成 `report/analysis.md`：logline 四要素 / 情绪曲线图 / 母题 / 因果链 / 结尾高潮
   2. 生成 `report/analysis.json`：给 studio 界面用的结构化数据
"""
import io
import json
import os
import sys

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


def _bar(v, lo=-5, hi=5, width=11):
    """把 -5~+5 画成一条对称的横条。"""
    if v is None:
        v = 0
    mid = width // 2
    n = int(round((float(v) - lo) / float(hi - lo) * (width - 1)))
    n = max(0, min(width - 1, n))
    if n >= mid:
        return "│" + "·" * mid + "█" * (n - mid + 1)
    return "│" + "█" * (n + 1) + "·" * (mid - n - 1)


def analyze(paths):
    """跑一遍剧本分析，返回结构化结果。"""
    story = load_json(paths["shots"], {}) or {}
    shots = story.get("shots") or []
    chars = story.get("characters") or []
    total = sum(s.get("duration") or 0 for s in shots)
    ints = [(s.get("intensity") or 0) for s in shots]

    # ---- logline 四要素 ----
    logline = (story.get("logline") or "").strip()
    want = (story.get("want") or "").strip()
    obstacle = (story.get("obstacle") or "").strip()
    change = (story.get("change") or "").strip()

    # ---- 情绪曲线 ----
    curve = []
    for s in shots:
        curve.append({
            "id": s["id"],
            "intensity": s.get("intensity") or 0,
            "purpose": s.get("purpose") or "",
            "audience": s.get("audience") or "",
            "scene": (s.get("scene") or {}).get("place") or (s.get("scene") or {}).get("id") or "",
            "line": (s.get("line") or "").strip(),
        })
    lo_i = min(range(len(ints)), key=lambda i: ints[i]) if ints else 0
    hi_i = max(range(len(ints)), key=lambda i: ints[i]) if ints else 0

    # 平直段检测（连续三镜同值）
    flat_runs = []
    run = 1
    for i in range(1, len(ints)):
        if ints[i] == ints[i - 1]:
            run += 1
            if run == 3:
                flat_runs.append([shots[i - 2]["id"], shots[i]["id"]])
        else:
            run = 1

    # ---- 问答对 ----
    def is_q(l):
        l = (l or "").strip()
        if not l:
            return False
        if l.endswith(("？", "?")):
            return True
        t = l.rstrip("…").rstrip()
        return t.endswith(("吗", "呢"))

    qa = []
    for i, s in enumerate(shots[:-1]):
        if is_q(s.get("line")):
            nxt = shots[i + 1]
            qa.append({
                "q_id": s["id"], "q": s.get("line"), "q_speaker": s.get("speaker"),
                "a_id": nxt["id"], "a": nxt.get("line"), "a_speaker": nxt.get("speaker"),
                "closed": bool((nxt.get("line") or "").strip()),
            })

    # ---- 结尾 ----
    last = shots[-1] if shots else {}
    ending = {
        "id": last.get("id"),
        "mode": last.get("ending_mode") or "",
        "intensity": last.get("intensity") or 0,
        "line": (last.get("line") or "").strip(),
        "action": (last.get("action") or "").strip(),
        "is_peak": (last.get("intensity") or 0) >= (max(ints) if ints else 0) - 1,
    }

    # ---- 角色 ----
    roles = []
    for c in chars:
        blob = ((c.get("desc_en") or "") + " " + (c.get("desc") or "")).lower()
        kind = "human" if ("human" in blob or "farmer" in blob or "woman" in blob
                           or "man" in blob) else "animal"
        roles.append({
            "name": c.get("name"),
            "kind": kind,
            "voice": c.get("voice") or "",
            "desc": (c.get("desc") or c.get("desc_en") or "")[:120],
            "outfit": (c.get("outfit") or c.get("outfit_en") or "")[:80],
        })

    # ---- 台词镜 ----
    talks = [{"id": s["id"], "speaker": s.get("speaker") or "",
              "line": (s.get("line") or "").strip(),
              "n": len("".join(ch for ch in (s.get("line") or "") if ch.strip()))}
             for s in shots if (s.get("line") or "").strip()]

    # ---- 短剧节奏指标（吸收自 short-drama-writer，v1.20.0）----
    BEAT_WORDS = ("打脸", "反转", "亮出", "揭露", "翻盘", "逆转", "耳光", "巴掌",
                  "撕", "摔", "跪下", "揭穿", "愣住", "震惊", "瞪", "傻眼",
                  "不服", "认输", "服了", "折服", "征服", "抢", "护",
                  "接单", "接了", "赔钱", "凭什么", "谁让", "值不值",
                  "我家的", "我的味道", "尝尝", "就配", "够吃一辈子",
                  "没人要", "别挖", "住手", "你敢", "滚")
    HOOK_WORDS = ("冲突", "对峙", "质问", "赔钱", "吵架", "打架", "抢", "打",
                  "突然", "竟然", "居然", "不料", "反倒", "愣住", "震惊",
                  "瞪", "怒", "吼", "拦住", "追", "闯", "摔", "掀",
                  "凭什么", "谁让", "你敢", "别动", "住手", "反转", "揭穿")
    TAIL_WORDS = ("悬念", "回头", "追", "来了", "电话", "又", "还没完",
                  "却", "突然", "结果", "怎么", "为什么", "愣", "惊",
                  "看着", "望着", "消失", "不见", "远处", "身后")

    def _stext(s):
        fr = (s.get("frame") or {}).get("prompt") or ""
        return " ".join([(s.get("action") or ""), (s.get("micro") or ""),
                         (s.get("video_prompt") or ""), (s.get("line") or ""), fr])

    alltxt = " ".join(_stext(s) for s in shots)
    beats = sum(alltxt.count(w) for w in BEAT_WORDS)
    jumps = 0
    for i in range(1, len(shots)):
        a = shots[i - 1].get("intensity") or 0
        b = shots[i].get("intensity") or 0
        if abs(a - b) >= 3:
            jumps += 1
    first_txt = _stext(shots[0]) if shots else ""
    last_txt = _stext(shots[-1]) if shots else ""
    pace = {
        "beats": beats,
        "jumps": jumps,
        "beats_total": beats + jumps,
        "has_hook": bool(any(k in first_txt for k in HOOK_WORDS)),
        "has_tail": bool(any(k in last_txt for k in TAIL_WORDS)),
        "hook_id": shots[0]["id"] if shots else "",
        "tail_id": shots[-1]["id"] if shots else "",
    }
    # 台词长度分布
    line_lens = []
    for s in shots:
        l = (s.get("line") or "").strip()
        if not l:
            continue
        n = len("".join(ch for ch in l if ch.strip()))
        line_lens.append({"id": s["id"], "n": n, "line": l})
    over = [x for x in line_lens if x["n"] > 14]
    pace["lines"] = line_lens
    pace["over_lines"] = over

    # ---- 角色出场闭环 ----
    appeared = set()
    for s in shots:
        appeared.update(c for c in (s.get("cast") or []) if c)
    never = [c.get("name") for c in chars
             if c.get("name") and c.get("name") not in appeared]

    return {
        "title": story.get("title") or "",
        "n_shots": len(shots),
        "total_seconds": total,
        "logline": logline,
        "four": {"who": want, "obstacle": obstacle, "change": change},
        "curve": curve,
        "low": {"id": shots[lo_i]["id"], "v": ints[lo_i], "audience": shots[lo_i].get("audience") or ""} if shots else {},
        "high": {"id": shots[hi_i]["id"], "v": ints[hi_i], "audience": shots[hi_i].get("audience") or ""} if shots else {},
        "flat_runs": flat_runs,
        "qa": qa,
        "ending": ending,
        "roles": roles,
        "talks": talks,
        "motif": (story.get("motif") or "").strip(),
        "pace": pace,
        "never_appear": never,
    }


def write_report(paths, data):
    """写出人读版分析报告。"""
    out_dir = os.path.join(paths["root"], "report")
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, "analysis.md")

    L = []
    A = L.append
    A("# 剧本分析报告 · %s\n" % (data.get("title") or ""))
    A("> %d 镜 / 计划 %d 秒\n" % (data["n_shots"], data["total_seconds"]))

    # ---- logline ----
    A("## 一、一句话故事\n")
    A("> %s\n" % (data.get("logline") or "（未填）"))
    four = data.get("four") or {}
    A("**四要素**：\n")
    A("| 要素 | 内容 |")
    A("|---|---|")
    A("| 谁 | %s |" % (four.get("who") or "—"))
    A("| 想要什么 | %s |" % (four.get("who") and "见 logline" or "—"))
    A("| 阻碍 | %s |" % (four.get("obstacle") or "—"))
    A("| 最后变成什么 | %s |" % (four.get("change") or "—"))
    A("")

    # ---- 情绪曲线 ----
    A("## 二、情绪曲线\n")
    A("```")
    for c in data["curve"]:
        A("%-4s %-3s %s  %s" % (c["id"], "%+d" % c["intensity"],
                                 _bar(c["intensity"]), c["purpose"]))
    A("```")
    lo, hi = data.get("low") or {}, data.get("high") or {}
    A("- **最低点**：%s（%+d）—— %s" % (lo.get("id", "—"), lo.get("v", 0), lo.get("audience", "")))
    A("- **最高点**：%s（%+d）—— %s" % (hi.get("id", "—"), hi.get("v", 0), hi.get("audience", "")))
    if data.get("flat_runs"):
        A("- ⚠️ **平直段**：%s 连续三镜同值 —— 情绪没起伏，看下去会闷"
          % "、".join("%s~%s" % (a, b) for a, b in data["flat_runs"]))
    else:
        A("- ✅ 无连续三镜同值，情绪有起伏")
    A("")

    # ---- 母题 ----
    A("## 三、母题回环\n")
    A("%s\n" % (data.get("motif") or "（未填 —— 建议补一个贯穿全片的物件或动作）"))

    # ---- 因果链 ----
    A("## 四、因果链\n")
    A("每一镜都要能回答「观众凭什么知道下一镜会发生」。\n")
    A("| 镜 | 因为上一镜…所以这一镜… |")
    A("|---|---|")
    story = load_json(paths["shots"], {}) or {}
    for s in story.get("shots") or []:
        A("| %s | %s |" % (s["id"], (s.get("because") or "—").replace("|", "/")))
    A("")

    # ---- 问答闭环 ----
    A("## 五、问答闭环\n")
    qa = data.get("qa") or []
    if not qa:
        A("全片没有问句 —— 不存在悬空对话。\n")
    else:
        A("| 问 | 答 | 状态 |")
        A("|---|---|---|")
        for q in qa:
            A("| %s %s | %s %s | %s |" % (
                q["q_id"], q.get("q") or "", q["a_id"], q.get("a") or "",
                "✅" if q.get("closed") else "⚠️ 没答"))
        A("")

    # ---- 结尾 ----
    A("## 六、结尾高潮\n")
    e = data.get("ending") or {}
    A("- 末镜：%s，强度 %+d %s" % (e.get("id", "—"), e.get("intensity", 0),
                                  "✅ 落在峰值" if e.get("is_peak") else "⚠️ 不在峰值"))
    A("- 收尾模式：`%s`" % (e.get("mode") or "未标注"))
    A("- 末镜台词：「%s」" % (e.get("line") or "（无）"))
    A("- 末镜动作：%s" % (e.get("action") or "—"))
    A("")

    # ---- 角色 ----
    A("## 七、角色\n")
    A("| 角色 | 物种 | 音色 | 简介 |")
    A("|---|---|---|---|")
    for r in data.get("roles") or []:
        A("| %s | %s | %s | %s |" % (
            r["name"], "**真人**" if r["kind"] == "human" else "拟人动物",
            r.get("voice") or "—", (r.get("desc") or "")[:60]))
    if data.get("never_appear"):
        A("")
        A("> ⚠️ 从没出现过：%s" % "、".join(data["never_appear"]))
    A("")

    # ---- 短剧节奏指标 ----
    pc = data.get("pace") or {}
    A("## 八·五、短剧节奏指标\n")
    A("| 指标 | 结果 | 判定 |")
    A("|---|---|---|")
    A("| 首钩（%s）| %s | %s |" % (
        pc.get("hook_id", "—"),
        "有" if pc.get("has_hook") else "无",
        "✅ 前 3 秒抓人" if pc.get("has_hook") else "⚠️ 开场没钩子，不许平开"))
    A("| 爆点数 | %d（词命中 %d + 情绪跳变 %d）| %s |" % (
        pc.get("beats_total", 0), pc.get("beats", 0), pc.get("jumps", 0),
        "✅ ≥3" if pc.get("beats_total", 0) >= 3 else "⚠️ 建议 ≥3"))
    A("| 尾钩（%s）| %s | %s |" % (
        pc.get("tail_id", "—"),
        "有" if pc.get("has_tail") else "无",
        "✅ 留了悬念" if pc.get("has_tail") else "⚠️ 自然收尾了"))
    over = pc.get("over_lines") or []
    A("| 台词长度 | 超 14 字 %d 句 | %s |" % (
        len(over), "✅" if not over else "⚠️ 要砍：%s"
        % "、".join("%s(%d字)" % (x["id"], x["n"]) for x in over)))
    A("")
    A("> 指标口径见 `references/short_drama_craft.md`（吸收自 short-drama-writer）。\n")

    # ---- 台词 ----
    A("## 八、台词一览（连起来念一遍，念不顺就是逻辑断了）\n")
    for t in data.get("talks") or []:
        A("- `%s` **%s**：%s" % (t["id"], t["speaker"], t["line"]))
    A("")

    with io.open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")

    # ---- JSON（给界面用）----
    jp = os.path.join(out_dir, "analysis.json")
    with io.open(jp, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=1))
    return p, jp
