#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wv_core.py —— 世界观工作台的数据层（零第三方依赖）。

管三件事：
  1. 读：把一个项目目录里的剧本、分镜、角色、道具、场景、世界观读成结构化数据
  2. 找集：在项目父目录里找出同系列的所有集（多集分集展示）
  3. 写：把页面上改过的内容存回磁盘（分镜表 / 角色 / 道具 / 世界观文本）

两个 skill 共用（agnes-clip 与 ai-video-pipeline 的目录结构不同，但都能读）。
"""
import json
import os
import re
import shutil
import time

# 世界观文档的候选文件名（按优先级）
WORLDVIEW_NAMES = ["世界观.md", "worldview.md", "WORLDVIEW.md", "设定集.md"]
# 系列级的世界观（父目录里的）
SERIES_NAMES = ["世界观.md", "worldview.md", "设定集.md"]


def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def read_text(path, default=""):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return default


def write_text(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


# ----------------------------------------------------------------------------- 项目识别

def find_project_root(start):
    """从任意路径往上找项目根（含 project.json 或 script/shots.json）。"""
    cur = os.path.abspath(start)
    if os.path.isfile(cur):
        cur = os.path.dirname(cur)
    for _ in range(6):
        if os.path.exists(os.path.join(cur, "project.json")):
            return cur
        if os.path.exists(os.path.join(cur, "script", "shots.json")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return None


def project_kind(root):
    """判断这是哪个 skill 的项目。"""
    cfg = read_json(os.path.join(root, "project.json"), {}) or {}
    providers = cfg.get("providers") or {}
    if providers.get("video") == "minimax_h3" or "ai-video-pipeline" in str(cfg):
        return "ai-video-pipeline"
    # agnes-clip 的 project.json 有 title/created，镜头表有 characters 顶层键
    return "agnes-clip"


def shot_file(root):
    return os.path.join(root, "script", "shots.json")


def story_file(root):
    return os.path.join(root, "script", "story.md")


def find_worldview_file(root, create=False):
    """项目内的世界观文档。"""
    for n in WORLDVIEW_NAMES:
        p = os.path.join(root, n)
        if os.path.exists(p):
            return p
        # 也可能在 script/ 下
        p2 = os.path.join(root, "script", n)
        if os.path.exists(p2):
            return p2
    if create:
        return os.path.join(root, "世界观.md")
    return None


def find_series_worldview(root):
    """系列级（父目录）的世界观。"""
    parent = os.path.dirname(os.path.abspath(root))
    for n in SERIES_NAMES:
        p = os.path.join(parent, n)
        if os.path.exists(p):
            return p
    return None


def cast_dir(root):
    """共享角色库目录。"""
    p = os.path.join(root, "cast")
    if os.path.isdir(p):
        return p
    cfg = read_json(os.path.join(root, "project.json"), {}) or {}
    cd = cfg.get("cast_dir")
    if cd:
        p = cd if os.path.isabs(cd) else os.path.join(root, cd)
        if os.path.isdir(p):
            return p
    # 父目录的 cast/
    p = os.path.join(os.path.dirname(os.path.abspath(root)), "cast")
    return p if os.path.isdir(p) else None


# ----------------------------------------------------------------------------- 找集

def discover_episodes(root):
    """找出同系列的所有集。

    规则：以项目的父目录为「系列根」，里面每个含 script/shots.json 的子目录算一集。
    当前集排在最前。返回 [{root, name, title, shots, chars, has_worldview, is_current}]
    """
    root = os.path.abspath(root)
    series_root = os.path.dirname(root)
    out = []
    try:
        entries = sorted(os.listdir(series_root))
    except Exception:
        entries = []
    for name in entries:
        d = os.path.join(series_root, name)
        if not os.path.isdir(d):
            continue
        if not os.path.exists(os.path.join(d, "script", "shots.json")):
            continue
        if not os.path.exists(os.path.join(d, "project.json")):
            continue
        sj = read_json(os.path.join(d, "script", "shots.json"), {}) or {}
        cfg = read_json(os.path.join(d, "project.json"), {}) or {}
        out.append({
            "root": d,
            "name": name,
            "title": sj.get("title") or cfg.get("title") or name,
            "shot_count": len(sj.get("shots") or []),
            "char_count": len(sj.get("characters") or []),
            "has_worldview": bool(find_worldview_file(d)),
            "is_current": os.path.normcase(d) == os.path.normcase(root),
        })
    # 当前集排最前，其余按名称
    out.sort(key=lambda e: (not e["is_current"], e["name"]))
    return out


# ----------------------------------------------------------------------------- 读

def _char_assets(root, kind="characters"):
    """角色/道具/场景资产目录里的图片清单。"""
    d = os.path.join(root, "assets", kind)
    out = []
    if not os.path.isdir(d):
        return out
    for name in sorted(os.listdir(d)):
        sub = os.path.join(d, name)
        if not os.path.isdir(sub):
            continue
        imgs = []
        for f in sorted(os.listdir(sub)):
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                imgs.append(f)
        meta = read_json(os.path.join(sub, "meta.json"), {}) or {}
        out.append({"name": name, "images": imgs, "meta": meta})
    return out


def load_episode(root):
    """读一集的完整内容，返回给前端的数据结构。"""
    root = os.path.abspath(root)
    sj = read_json(shot_file(root), {}) or {}
    cfg = read_json(os.path.join(root, "project.json"), {}) or {}

    characters = sj.get("characters") or []
    props = sj.get("props") or []
    shots = sj.get("shots") or []

    # 场景：从分镜里聚合（同一 place 归一个场景）
    scenes = {}
    for s in shots:
        sc = s.get("scene") or {}
        if isinstance(sc, str):
            sc = {"place": sc}
        if not isinstance(sc, dict):
            sc = {}
        key = (sc.get("id") or sc.get("place") or sc.get("slug") or "").strip()
        if not key:
            continue
        if key not in scenes:
            scenes[key] = {
                "id": key,
                "place": sc.get("place") or key,
                "time": sc.get("time") or "",
                "weather": sc.get("weather") or "",
                "light": sc.get("light") or "",
                "set": sc.get("set") or [],
                "angles": sc.get("angles") or {},
                "shot_ids": [],
            }
        scenes[key]["shot_ids"].append(s.get("id"))
        # 后出现的分镜里若有更全的场景信息，补进去
        for k in ("time", "weather", "light"):
            if not scenes[key].get(k) and sc.get(k):
                scenes[key][k] = sc[k]
        if sc.get("set") and not scenes[key].get("set"):
            scenes[key]["set"] = sc["set"]
        if sc.get("angles") and not scenes[key].get("angles"):
            scenes[key]["angles"] = sc["angles"]

    # 角色资产（图片）
    char_assets = {a["name"]: a for a in _char_assets(root, "characters")}
    prop_assets = {a["name"]: a for a in _char_assets(root, "props")}
    scene_assets = {a["name"]: a for a in _char_assets(root, "scenes")}
    cd = cast_dir(root)
    shared_chars = set()
    if cd:
        for a in _char_assets(cd, "characters"):
            shared_chars.add(a["name"])

    for c in characters:
        n = c.get("name") or ""
        a = char_assets.get(n)
        c["_images"] = a["images"] if a else []
        c["_meta"] = a["meta"] if a else {}
        c["_shared"] = n in shared_chars
    for p in props:
        n = p.get("name") or ""
        a = prop_assets.get(n)
        p["_images"] = a["images"] if a else []
        p["_meta"] = a["meta"] if a else {}

    wv_path = find_worldview_file(root)
    series_wv = find_series_worldview(root)

    # 每个镜头关联到已存在的首帧/片段（看进度用）
    for s in shots:
        sid = s.get("id") or ""
        s["_has_frame"] = os.path.exists(os.path.join(root, "frames", sid + ".jpg"))
        s["_has_clip"] = os.path.exists(os.path.join(root, "clips", sid + ".mp4"))

    return {
        "root": root,
        "kind": project_kind(root),
        "title": sj.get("title") or cfg.get("title") or os.path.basename(root),
        "logline": sj.get("logline") or "",
        "genre": sj.get("genre") or "",
        "story_md": read_text(story_file(root), ""),
        "worldview_md": read_text(wv_path, "") if wv_path else "",
        "worldview_path": wv_path or "",
        "series_worldview_md": read_text(series_wv, "") if series_wv else "",
        "series_worldview_path": series_wv or "",
        "characters": characters,
        "props": props,
        "scenes": list(scenes.values()),
        "shots": shots,
        "episodes": discover_episodes(root),
        "shared_cast": sorted(shared_chars),
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


# ----------------------------------------------------------------------------- 写

def save_episode(root, payload):
    """把页面上改过的内容写回磁盘。

    payload 里的可选键：
      shots       整个分镜数组（覆盖写）
      characters  整个角色数组
      props       整个道具数组
      logline     一行故事梗概
      genre       叙事类型
      worldview   世界观文本（存到世界观.md）
      story_md    剧本正文（存到 story.md）
    """
    root = os.path.abspath(root)
    changed = []
    sj_path = shot_file(root)
    sj = read_json(sj_path, {}) or {}

    if "shots" in payload and isinstance(payload["shots"], list):
        # 保留前端传来的下划线临时字段之外的一切
        clean = []
        for s in payload["shots"]:
            s2 = {k: v for k, v in s.items() if not k.startswith("_")}
            clean.append(s2)
        sj["shots"] = clean
        changed.append("分镜 %d 镜" % len(clean))
    if "characters" in payload and isinstance(payload["characters"], list):
        sj["characters"] = [{k: v for k, v in c.items() if not k.startswith("_")}
                            for c in payload["characters"]]
        changed.append("角色 %d 个" % len(sj["characters"]))
    if "props" in payload and isinstance(payload["props"], list):
        sj["props"] = [{k: v for k, v in p.items() if not k.startswith("_")}
                       for p in payload["props"]]
        changed.append("道具 %d 个" % len(sj["props"]))
    if "logline" in payload:
        sj["logline"] = payload["logline"]
        changed.append("梗概")
    if "genre" in payload:
        sj["genre"] = payload["genre"]
        changed.append("类型")

    if len(sj) or os.path.exists(sj_path):
        write_json(sj_path, sj)

    if "worldview" in payload and isinstance(payload["worldview"], str):
        p = find_worldview_file(root, create=True)
        write_text(p, payload["worldview"])
        changed.append("世界观")
    if "story_md" in payload and isinstance(payload["story_md"], str):
        write_text(story_file(root), payload["story_md"])
        changed.append("剧本正文")

    return {"ok": True, "changed": changed,
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")}


def save_series_worldview(root, text):
    """存系列级世界观（父目录的）。"""
    parent = os.path.dirname(os.path.abspath(root))
    p = find_series_worldview(root)
    if not p:
        p = os.path.join(parent, "世界观.md")
    write_text(p, text)
    return {"ok": True, "path": p}


def list_projects(base):
    """列出 base 目录下所有项目（给页面切集用）。"""
    out = []
    if not os.path.isdir(base):
        return out
    for name in sorted(os.listdir(base)):
        d = os.path.join(base, name)
        if not os.path.isdir(d):
            continue
        if not os.path.exists(os.path.join(d, "script", "shots.json")):
            continue
        sj = read_json(os.path.join(d, "script", "shots.json"), {}) or {}
        out.append({
            "root": d,
            "name": name,
            "title": sj.get("title") or name,
            "shots": len(sj.get("shots") or []),
        })
    return out
