# -*- coding: utf-8 -*-
"""抽帧法核对全片产品外观：每个挂了道具的镜头抽三帧拼成联络图。

用法：
    python tools/prop_audit.py <项目目录>              # 全部道具镜
    python tools/prop_audit.py <项目目录> --ids S11,S12
    python tools/prop_audit.py <项目目录> --cols 3 --out qa/prop_audit.jpg

为什么要它：产品形态错了，看分镜、看提示词、听台词都发现不了，
只有把成片里"产品入画的那几帧"抽出来并排看才穿帮。
ep02《黄精》就是靠它查出 S11/S12 手里举的是人参。
"""
import argparse
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
AC = os.path.join(SKILL, "scripts", "ac.py")


def load_ffmpeg(root):
    p = os.path.join(root, "project.json")
    if os.path.exists(p):
        try:
            d = json.load(open(p, encoding="utf-8"))
            if d.get("ffmpeg") and os.path.exists(d["ffmpeg"]):
                return d["ffmpeg"]
        except Exception:
            pass
    try:
        sys.path.insert(0, os.path.join(SKILL, "scripts"))
        import ac  # noqa
        return ac.have_ffmpeg({"agnes": {}}) or "ffmpeg"
    except Exception:
        return "ffmpeg"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--ids", default="")
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--cell", type=int, default=300)
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    root = os.path.abspath(a.dir)
    sp = os.path.join(root, "script", "shots.json")
    if not os.path.exists(sp):
        sys.exit("找不到 %s" % sp)
    d = json.load(open(sp, encoding="utf-8"))
    shots = d.get("shots") or []
    want = {x.strip() for x in a.ids.split(",") if x.strip()}

    picked = []
    for s in shots:
        names = list(s.get("props") or []) + list(s.get("shape_props") or [])
        if not names:
            continue
        if want and s["id"] not in want:
            continue
        picked.append((s, names))
    if not picked:
        sys.exit("没有挂道具的镜头（先按 SKILL.md 建 props 并挂 shot.props / shape_props）")

    ff = load_ffmpeg(root)
    tmp = os.path.join(root, "qa", "_propaudit")
    os.makedirs(tmp, exist_ok=True)
    out = a.out or os.path.join(root, "qa", "prop_audit.jpg")

    rows = []
    for s, names in picked:
        clip = os.path.join(root, "clips", s["id"] + ".mp4")
        if not os.path.exists(clip):
            print("[skip] %s 缺片段" % s["id"])
            continue
        dur = float(s.get("duration") or 0)
        if dur <= 0:
            dur = 6.0
        frames = []
        for k, f in enumerate((0.30, 0.50, 0.72)):
            fp = os.path.join(tmp, "%s_%d.png" % (s["id"], k))
            subprocess.run([ff, "-hide_banner", "-v", "error", "-ss", "%.2f" % (dur * f),
                            "-i", clip, "-frames:v", "1", "-y", fp], check=False)
            if os.path.exists(fp):
                frames.append(fp)
        if frames:
            rows.append((s["id"], names, frames))
        print("[ok] %s  props=%s  frames=%d" % (s["id"], ",".join(names), len(frames)))

    if not rows:
        sys.exit("没有可用帧")

    from PIL import Image, ImageDraw
    C = a.cell
    ncol = max(len(r[2]) for r in rows)
    ncol = max(ncol, a.cols)
    out_img = Image.new("RGB", (C * ncol, C * len(rows) + 18), "white")
    dr = ImageDraw.Draw(out_img)
    dr.text((4, 4), "prop audit: %d shots  |  %s" % (len(rows), ", ".join(
        "%s=%s" % (r[0], "+".join(r[1])) for r in rows))[:180], fill="black")
    for j, (sid, names, frames) in enumerate(rows):
        y = 18 + j * C
        for k, fp in enumerate(frames):
            im = Image.open(fp).convert("RGB")
            im.thumbnail((C, C))
            out_img.paste(im, (k * C, y))
        dr.rectangle([0, y, 78, y + 20], fill="black")
        dr.text((4, y + 5), sid, fill="yellow")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    out_img.save(out, quality=88)
    print("\n联络图 -> %s  (%d 行)" % (out, len(rows)))
    print("逐行比对外观：形态不对的镜必须重出首帧 + 视频。")


if __name__ == "__main__":
    main()
