#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""version_rule.py —— 版本号规则（全 skill 唯一真源）。

## 规则（2026-11-01 起，v2.0.0 定版）

版本号是三段 `主.次.修`，**每一段只能是 0-9 的一个数字**：

    2.0.0 → 2.0.1 → … → 2.0.9 → 2.1.0 → … → 2.9.0 → 3.0.0

- 补丁位（第三段）满 9 → 进位到次版本，第三段归零
- 次版本（第二段）满 9 → 进位到主版本，第二、三段归零
- **不允许出现两位数**：1.37.0 这种"次版本 37"是旧规矩，已废除

## 为什么这么定

旧的 `1.23.0 → 1.37.0` 让版本号越来越长：
中间发生了什么只能去翻 GitHub 对比，本机版本和 GitHub 版本还长期对不上（1.37 vs 1.23）。
三位单数字能保证：
1. 版本号长度恒定，一眼能看出"到哪了"；
2. 补丁位最多 9 个，装不满一个版本来回折腾；
3. 不再出现 `1.37.0` 这种别人一看就懵的数字。

## 用法

    from version_rule import next_version, validate_version
    next_version("2.0.9")        # -> "2.1.0"
    next_version("2.9.9")        # -> "3.0.0"
    next_version("2.0.0")        # -> "2.0.1"
    validate_version("2.0.10")   # -> (False, "补丁位只能是 0-9，10 越界了")
"""
import re

# 版本号：三位，每位 0-9
VER_RE = re.compile(r"^(\d)\.(\d)\.(\d)$")

MAX_SEG = 9  # 每段上限（同时也是进位阈值）


def parse_version(v):
    """拆版本号 -> (主, 次, 修)；格式不对返回 None。"""
    if v is None:
        return None
    m = VER_RE.match(str(v).strip())
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


def fmt_version(t):
    """三元组 -> '2.0.1'。"""
    return "%d.%d.%d" % tuple(t)


def next_version(cur):
    """按规则算出下一个版本号。

    2.0.8 -> 2.0.9 -> 2.1.0 -> 2.1.1 -> …

    当前版本号本身不合规（比如 1.37.0）时，
    先把它规整到最近的合法版本再进位：1.37.0 -> 2.0.0 -> 2.0.1。
    """
    t = parse_version(cur)
    if t is None:
        t = _normalize(cur)
    major, minor, patch = t
    if patch < MAX_SEG:
        return fmt_version((major, minor, patch + 1))
    if minor < MAX_SEG:
        return fmt_version((major, minor + 1, 0))
    return fmt_version((major + 1, 0, 0))


def _normalize(v):
    """把不合规的旧版本号规整到最近的合法版本。

    旧规矩下版本号会出现两位数（1.37.0 这种），
    那种号没法拆成"主.次.修"，一律理解成"要进主版本了"：

    1.37.0 -> 2.0.0
    1.9.1  -> 1.9.1（本来就合规，原样返回）
    """
    s = str(v or "").strip()
    parts = s.split(".")
    nums = []
    for p in parts:
        try:
            nums.append(int(p))
        except ValueError:
            nums.append(0)
    while len(nums) < 3:
        nums.append(0)
    major, minor, patch = nums[0], nums[1], nums[2]
    if any(n > MAX_SEG for n in (major, minor, patch)):
        # 老版本号：整体进到下一个主版本，规矩重来
        return (min(major + 1, MAX_SEG), 0, 0)
    return (major, minor, patch)


def validate_version(v):
    """校验版本号是否符合规则。

    返回 (是否合法, 出错原因)。合法时原因为空串。
    """
    s = str(v or "").strip()
    if not s:
        return False, "版本号是空的"
    if not re.match(r"^\d+\.\d+\.\d+$", s):
        return False, "版本号要写成三段，比如 2.0.1（现在写的是 %s）" % s
    segs = s.split(".")
    for i, seg in enumerate(segs):
        n = int(seg)
        if n > MAX_SEG:
            which = ["主版本", "次版本", "补丁位"][i]
            return False, ("%s只能是 0-9，%s 越界了"
                           % (which, seg))
    if int(segs[2]) == 0 and int(segs[1]) == 0:
        # 允许 2.0.0 这种整版起点
        pass
    return True, ""


def describe():
    """给用户看的一句话规则说明。"""
    return ("版本号 = 主.次.修，三段各 0-9。"
            "补丁位满 9 自动进到次版本（2.0.9 → 2.1.0），"
            "次版本满 9 进到主版本（2.9.9 → 3.0.0）。")
