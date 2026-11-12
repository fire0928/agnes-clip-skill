# -*- coding: utf-8 -*-
"""空间锁（staging lock）—— 比人脸锁再往上一层。

=== 2026-11-09 重构：机位设计审计后的四条修复 ===

ep19 反复返工（真人 / 沙发 / 户外 / 坐下 / 面条），查代码发现主因不是模型弱，
是机位设计在给模型递错东西：

1. `angle` 字段只是「挑哪张场景板」的键，不描述怎么拍。项目里 F_table /
   F_counter / F_pass 三个机位名全部 return HALL.two(who) —— 同一句取景。
   改机位名 = 换背景照片，镜头语言一个字没变。
   → 新增 `Staging.at(angle, who)`：每个注册机位有专属取景句，构造时强制互不相同。
2. `_tail()` 无条件把 PLACE + DRESSING 追加到**每一个** framing（含 close /
   wide / table_top），于是特写镜、相拥镜也被钉在同一张餐桌上。
   → `_tail(dressing=...)` 参数化：two/side 带陈设，close/over/wide/table_top 不带。
3. 同一个镜里可能出现两句不同的「Staging is fixed …」（例如换了 S_HUG_STAGE
   却仍用 HALL.close()），模型各取一半，就成了「两只猫坐桌边吃面」。
   → `verify()` 新增同镜冲突锁检测。
4. 造个新 scene.id 就能绕过 `verify()` 的分组；`scene.angles` 的机位描述
   根本不进首帧提示词（只在 scene-gen 用），却没人检查。
   → `verify()` 改为「PLACE 必须一致、DRESSING 可缺席但出现就必须一致」，
   并新增 `verify_angles()` 检查照抄与死配置。

=== 用法 ===

    from staging import Staging, verify, verify_angles

    HALL = Staging(
        place=("the dark square table stays fixed ... the grey wolf stands at the LEFT ..."),
        dressing=("exactly four things always sit on the table ..."),
        angles={
            "table": "Medium shot across one dark square table from the counter side",
            "counter-two": "Medium two-shot from behind the long counter, waist-up",
            "pass": "Medium shot from the dining room toward the serving pass",
        },
    )

    framing = HALL.at("counter-two", "the grey wolf at the left, the cat at the right")

    # 生成器 main() 里
    for shot_id, problem in verify(SHOTS) + verify_angles(SHOTS):
        print(shot_id, problem)

兼容：旧写法 `HALL.two(who)` / `HALL.close(who)` / `verify(shots)` 全部保留。
"""


import json
import re


class Staging:
    def __init__(self, place, dressing, table="a dark wooden square table", light="", angles=None):
        self.place = place.strip().rstrip(".")
        self.dressing = dressing.strip().rstrip(".")
        self.table = table
        self.light = light
        self.angles = dict(angles or {})
        # 🔴 两个机位写了同一句描述 = 机位退化，构造时就拦下来
        sig = {}
        for ang, desc in self.angles.items():
            s = " ".join(str(desc).split()).lower()
            if s in sig:
                raise ValueError("机位 %s 和 %s 的取景描述完全相同，等于一个机位起了两个名字"
                                 % (sig[s], ang))
            sig[s] = ang

    # ---------------- 内部：拼装 ----------------
    def _tail(self, dressing=True, place=True):
        """🔴 dressing=False 时只锁「谁在哪侧」，不把桌面陈设塞进特写镜。"""
        out = ""
        if place:
            out += " Staging is fixed for the whole film: " + self.place + "."
        if dressing:
            out += " Set dressing on the table is fixed too: " + self.dressing + "."
        return out

    def _head(self, body):
        return body.strip().rstrip(".") + "."

    # ---------------- 按注册机位取景（推荐） ----------------
    def at(self, angle, who="", dressing=None, extra=""):
        """按机位名取专属取景句；不同 angle 一定是不同的句子。

        dressing=None 时按机位自动判断：只有围着桌子拍的双人镜带桌面陈设，
        近景 / 过肩 / 全景 / 俯拍桌面都不带，避免被钉在餐桌边。
        """
        body = self.angles.get(angle)
        if not body:
            body = "Medium shot across " + self.table + " from the outer side"
        if who:
            body = body.rstrip(".") + ": " + who
        if dressing is None:
            dressing = angle in ("table", "two", "side")
        return self._head(body) + self._tail(dressing=dressing) + (" " + extra if extra else "")

    # ---------------- 兼容旧写法的六种取景 ----------------
    def two(self, who, extra="", dressing=True):
        """双人中景。谁在画面哪一侧要写清楚。默认带桌面陈设。"""
        return self._head("Medium shot across " + self.table + " from the outer side: " + who) \
            + self._tail(dressing=dressing) + (" " + extra if extra else "")

    def over(self, near, far, extra="", dressing=False):
        """过肩：焦点在 far 脸上，桌沿不该抢戏，默认不带陈设锁。"""
        return self._head("Over-the-shoulder shot across the same " + self.table + ": " + near
                          + " blurred in the near foreground, focus on " + far) \
            + self._tail(dressing=dressing) + (" " + extra if extra else "")

    def close(self, who, extra="", dressing=False):
        """单人近景。🔴 默认不带餐桌陈设，否则亲密/表情镜会被钉在桌边。"""
        return self._head("Medium close shot across the same " + self.table + ": " + who
                          + " in the centre of the frame, the table edge in the lower foreground") \
            + self._tail(dressing=dressing) + (" " + extra if extra else "")

    def side(self, who, extra="", dressing=True):
        """并排双人：不是面对面，是并肩朝同一个方向看。"""
        return self._head("Medium shot across the same " + self.table + ": " + who
                          + ", both in three-quarter view facing the same direction") \
            + self._tail(dressing=dressing) + (" " + extra if extra else "")

    def wide(self, note="", dressing=False):
        """全景转场。全片别超过两个；默认不带桌面陈设。"""
        return self._head("Wide shot of the room from the doorway: " + self.table
                          + " in the middle ground" + (", " + note if note else "")) \
            + self._tail(dressing=dressing)

    def table_top(self, what, note="", dressing=False):
        """桌面/手部特写：画面里没有脸。what 已写清桌上有什么，不再叠全局陈设锁。"""
        return self._head("Close shot looking down across the same " + self.table + ": " + what) \
            + self._tail(dressing=dressing) + (" " + note if note else "")


# ---------------------------------------------------------------- 自检
LOCK_KEYS = ("Staging is fixed for the whole film", "Set dressing on the table is fixed too")


def _locks(prompt):
    """抓出提示词里每一句空间锁；同一句 key 出现多次会全部保留，用来查打架。"""
    out = {}
    for k in LOCK_KEYS:
        vals = []
        for m in re.finditer(re.escape(k), prompt or ""):
            tail = prompt[m.end():]
            j = tail.find(".")
            vals.append(tail[:j + 1].strip() if j >= 0 else tail.strip())
        out[k] = vals
    return out


def verify(shots, keys=LOCK_KEYS):
    """空间锁自检。返回 [(shot_id, 问题描述), ...]，空列表 = 通过。

    规则（2026-11-09 修订）：
    - 同一场景里，PLACE 句必须一字不差；DRESSING 句**可以缺席**（特写镜不该有），
      但一旦出现就必须和同场景其它镜一致。
    - 🔴 同一镜里同一类锁出现两种不同写法 = 两套空间锁打架，必报。
      造新 scene.id 绕不过这一条，因为冲突检测是按镜做的。
    """
    problems = []
    by_scene = {}
    for s in shots:
        prompt = (s.get("frame") or {}).get("prompt") or ""
        locks = _locks(prompt)
        for k in keys:
            vals = [v for v in locks[k] if v]
            if len(set(vals)) > 1:
                problems.append((s["id"], "同一镜出现 %d 句不同的「%s」，两套空间锁打架"
                                 % (len(set(vals)), k[:24])))
        sid = (s.get("scene") or {}).get("id") or ""
        by_scene.setdefault(sid, []).append((s["id"], locks))

    for items in by_scene.values():
        for k in keys:
            present = [(sid, vals[k][0]) for sid, vals in items if vals[k]]
            if not present:
                continue
            ref_id, ref = present[0]
            # 🔴 2026-11-12：漏写也要报。
            #    以前只比对「已经写了锁的镜」，于是同场景里某一镜压根没写空间锁
            #    → 模型在那镜里不知道谁在哪侧 → 人会乱换位置，而 verify 判「通过」。
            #    PLACE 句（谁在哪侧）每镜都必须有；DRESSING 句（桌上摆什么）
            #    特写镜可以没有，所以只对 PLACE 报漏写。
            #    只有当同场景**多数**镜都写了才报漏写 —— 全都没写说明这个场景
            #    本来就没用空间锁，不该拿这套标准去卡。
            if k == LOCK_KEYS[0] and len(present) >= max(2, len(items) // 2):
                for sid, vals in items:
                    if not vals[k]:
                        problems.append((sid, "同场景其它镜都有「%s」，本镜漏了 —— "
                                                "模型在这镜里不知道谁在哪侧" % k[:20]))
            for shot_id, val in present[1:]:
                if val != ref:
                    problems.append((shot_id, "%s 和 %s 不一致" % (k[:20], ref_id)))
    return problems


def verify_angles(shots):
    """机位描述自检。返回 [(shot_id, 问题描述), ...]，空列表 = 通过。

    ep19 审计查到的两个坑：
    - 换了 scene.id（店堂相拥 / 店堂特写）却把 `scene.angles` 整段照抄过来，
      机位表看着变多了，实际还是同一套，而且 `verify()` 按 scene.id 分组查不出来。
    - `scene.angles` 只在 `do_scenes` 生成场景板时读，**根本不进首帧提示词**。
      板若是复制来的、没重跑 scene-gen，它就是一份死配置，check 却只查「有没有写」。
    """
    problems = []
    seen = {}
    for s in shots:
        sc = s.get("scene") or {}
        sid = sc.get("id") or ""
        a = sc.get("angles") or {}
        if not a or sid in seen:
            continue
        sig = json.dumps(a, sort_keys=True, ensure_ascii=False)
        for other, osig in seen.items():
            if osig == sig:
                problems.append((s["id"], "场景「%s」的机位描述整段照抄「%s」，换 id 没换机位"
                                 % (sid, other)))
                break
        seen[sid] = sig

    dead = set()
    for s in shots:
        sc = s.get("scene") or {}
        ang = s.get("angle") or "wide"
        desc = (sc.get("angles") or {}).get(ang) or ""
        prompt = (s.get("frame") or {}).get("prompt") or ""
        if desc and " ".join(desc.split())[:45] not in prompt:
            dead.add(ang)
    for ang in sorted(dead):
        problems.append(("-", "机位 %s 的英文描述没进任何首帧提示词（只在 scene-gen 用，是死配置）"
                         % ang))
    return problems
