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

# 本次读取中损坏的文件（页面要显示出来，别让用户以为项目是空的）
BROKEN_FILES = []


def read_json(path, default=None):
    """读 JSON。文件坏掉时返回 default，并把错误记下来（页面上要提示用户）。"""
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        BROKEN_FILES.append({"path": path, "error": str(e)[:200]})
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


def _as_list(v):
    """把可能是字符串 / 列表 / None 的值统一成列表。"""
    if v is None:
        return []
    if isinstance(v, str):
        return [v.strip()] if v.strip() else []
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()]
    return [str(v)]


def _strip_private(obj):
    """递归剥掉所有以下划线开头的临时字段（_has_frame / _images / _shared …）。

    这些是给前端看的临时数据，绝不能写回磁盘。
    """
    if isinstance(obj, dict):
        return {k: _strip_private(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [_strip_private(x) for x in obj]
    return obj


def _merge_by_name(disk_list, incoming):
    """按 name 把前端传来的条目合并进磁盘上的列表。

    规则：
      - 磁盘上有、前端没传 → **保留**（前端可能只是没渲染它）
      - 两边都有 → 用前端的值覆盖同名同名字段，但磁盘上独有的字段保留
        （比如 ac.py 写的 outfit_en，前端没这字段就不会弄丢）
      - 前端有、磁盘上没有 → 新增
    返回合并后的列表；磁盘上原本是空列表时直接用前端数据。
    """
    if not isinstance(disk_list, list) or not disk_list:
        return _strip_private(incoming)
    disk_by = {}
    order = []
    for item in disk_list:
        if not isinstance(item, dict):
            continue
        n = item.get("name") or ""
        disk_by[n] = item
        order.append(n)
    for item in incoming:
        if not isinstance(item, dict):
            continue
        n = item.get("name") or ""
        if n in disk_by:
            base = dict(disk_by[n])
            for k, v in _strip_private(item).items():
                base[k] = v
            disk_by[n] = base
        else:
            disk_by[n] = _strip_private(item)
            order.append(n)
    return [disk_by[n] for n in order]


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
    """角色/道具/场景资产目录里的图片清单。

    两种布局都要认：
      A. 子目录式（角色）：assets/characters/girl/{source,face_ref,turnaround}.jpg
      B. 平铺式（道具/场景）：assets/props/umbrella.jpg
    角色走 A，道具场景两种都可能出现。
    """
    d = os.path.join(root, "assets", kind)
    out = []
    if not os.path.isdir(d):
        return out
    for name in sorted(os.listdir(d)):
        sub = os.path.join(d, name)
        if os.path.isdir(sub):
            imgs = []
            for f in sorted(os.listdir(sub)):
                if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                    imgs.append(f)
            meta = read_json(os.path.join(sub, "meta.json"), {}) or {}
            out.append({"name": name, "images": imgs, "meta": meta})
        elif name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            # 平铺：assets/props/umbrella.jpg → 名字取去掉扩展名
            base = os.path.splitext(name)[0]
            meta = read_json(os.path.join(d, base + ".json"), {}) or {}
            out.append({"name": base, "images": [name], "meta": meta})
    return out


def load_episode(root):
    """读一集的完整内容，返回给前端的数据结构。"""
    root = os.path.abspath(root)
    del BROKEN_FILES[:]
    sj = read_json(shot_file(root), {}) or {}
    cfg = read_json(os.path.join(root, "project.json"), {}) or {}

    # 深拷贝：下面要给角色/分镜挂临时字段（_images / _has_frame 等），
    # 绝不能污染磁盘上的原始对象（虽然当前不落盘，但这样更安全，
    # 也保证 save 时读到的永远是磁盘原样）。
    sj = json.loads(json.dumps(sj, ensure_ascii=False))
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
                "set": [],
                "angles": {},
                "shot_ids": [],
            }
        scenes[key]["shot_ids"].append(s.get("id"))
        # 后出现的分镜里若有更全的场景信息，补进去
        for k in ("time", "weather", "light"):
            if not scenes[key].get(k) and sc.get(k):
                scenes[key][k] = sc[k]
        # 陈设：去重合并（每镜都可能有部分陈设，不能只取第一个）
        for item in _as_list(sc.get("set")):
            if item and item not in scenes[key]["set"]:
                scenes[key]["set"].append(item)
        # 机位表：同一场景不同镜头有不同机位，要合并而不是只留第一个
        # 同一个 angle key 出现多次时保留信息更全的那条（更长的描述）
        for ak, av in (sc.get("angles") or {}).items():
            av = av or ""
            old = scenes[key]["angles"].get(ak) or ""
            if len(str(av)) > len(str(old)):
                scenes[key]["angles"][ak] = av

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
        "broken_files": list(BROKEN_FILES),
        # 各关键文件的修改时间：保存时比对，防止覆盖别人（或另一个页面）的改动
        "mtimes": {
            "shots": file_mtime(shot_file(root)),
            "worldview": file_mtime(wv_path) if wv_path else 0.0,
            "story": file_mtime(story_file(root)),
        },
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
      _mtimes     页面读数据时各文件的修改时间；与当前磁盘不一致就拒绝写入
    """
    root = os.path.abspath(root)
    changed = []
    sj_path = shot_file(root)

    # ⚠ 防覆盖：页面打开之后文件被别人改过（或另一个页面保存过），
    # 这时再用页面上的旧数据写回去会把别人的改动抹掉。直接拒绝并说明。
    mtimes = payload.get("_mtimes") or {}
    if isinstance(mtimes, dict):
        for key, path in (("shots", sj_path),
                          ("worldview", find_worldview_file(root)),
                          ("story", story_file(root))):
            want = mtimes.get(key)
            if not want or not path or not os.path.exists(path):
                continue
            now = file_mtime(path)
            if abs(now - float(want)) > 0.001:
                raise ValueError(
                    "「%s」在你打开这个页面之后被改过了，为避免覆盖别人的改动，本次没有写入。\n"
                    "请点右上角「刷新」重新读一遍，再改再存。" % os.path.basename(path))

    # ⚠ 关键保护：shots.json 坏了（JSON 解析失败）就**拒绝写入**。
    # 否则会把坏文件用空内容覆盖，用户的数据就没了。
    if os.path.exists(sj_path):
        try:
            with open(sj_path, "r", encoding="utf-8") as f:
                sj = json.load(f)
            if not isinstance(sj, dict):
                sj = {}
        except Exception as e:
            raise ValueError(
                "shots.json 解析失败，为避免覆盖你的数据，本次没有写入。\n"
                "请先修好这个文件：%s\n错误：%s" % (sj_path, str(e)[:200]))
    else:
        sj = {}

    # 分镜：整体覆盖（前端传的是完整数组）
    if "shots" in payload:
        if not isinstance(payload["shots"], list):
            raise ValueError("shots 应该是数组，收到的是 %s" % type(payload["shots"]).__name__)
        # 空数组会把整份分镜清空 —— 磁盘上明明有内容时这几乎肯定是误操作
        if not payload["shots"] and (sj.get("shots") or []):
            raise ValueError(
                "收到的分镜是空的，但磁盘上有 %d 镜 —— 拒绝写入（怕把分镜清空了）。\n"
                "确实要清空，请先把 shots.json 里的 shots 改成空数组再保存。"
                % len(sj.get("shots") or []))
        sj["shots"] = _strip_private(payload["shots"])
        changed.append("分镜 %d 镜" % len(sj["shots"]))
    # 角色 / 道具：**按名字合并**，只更新前端传了的那几个字段。
    # 整体覆盖的风险：前端某处没渲染出全部角色就会把其余的删掉。
    if "characters" in payload:
        if not isinstance(payload["characters"], list):
            raise ValueError("characters 应该是数组，收到的是 %s" % type(payload["characters"]).__name__)
        n = _merge_by_name(sj.get("characters") or [], payload["characters"])
        if n:
            sj["characters"] = n
            changed.append("角色 %d 个" % len(n))
    if "props" in payload:
        if not isinstance(payload["props"], list):
            raise ValueError("props 应该是数组，收到的是 %s" % type(payload["props"]).__name__)
        n = _merge_by_name(sj.get("props") or [], payload["props"])
        if n:
            sj["props"] = n
            changed.append("道具 %d 个" % len(n))
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


def file_mtime(path):
    """文件最后修改时间（用于「别人改过了」的提示）。"""
    try:
        return os.path.getmtime(path)
    except Exception:
        return 0.0


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
