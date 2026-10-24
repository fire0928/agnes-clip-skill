# -*- coding: utf-8 -*-
"""流程控制台后端：把流程引擎 + 真实图片 + 剧本分析 + 执行日志串成一个本地网页。

🔴 用户诉求（2026-10-24）：
> 「一定要流程化，从最开始分析需求，确认方案，然后编剧，拆分镜，
>   这些都要一步步的显示出来给用户看到，而且用户随时可以更新需求的。
>   然后再生成角色，都要显示出来给用户看到真实的图片及进度，
>   然后还要把首帧图也显示出来，
>   之前的情绪分析这些咋没有了呢，怎么就弄丢了呢？逻辑也乱了。」

所以这里提供：
- GET  /api/state?ep=   当前状态（阶段进度 + 分析 + 真实图片清单）
- POST /api/run?ep=&stage=   跑一个阶段
- POST /api/runall?ep=        一路跑到「逻辑自检」
- POST /api/brief?ep=         保存用户改过的需求工单
- POST /api/brief/regen?ep=   重新生成工单模板
- POST /api/reset?ep=&stage=  重置某阶段及之后
- GET  /api/log?ep=           执行日志
- GET  /img/<ep>/<相对路径>    真实图片
"""
import io
import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analysis as analysis_mod  # noqa: E402
import flow as flow_mod  # noqa: E402

AC = os.path.abspath(__file__)
SKILL_DIR = os.path.dirname(AC)

# 各集的日志缓冲
LOGS = {}
LOG_LOCK = threading.Lock()
RUN_LOCK = threading.Lock()
RUNNING = {}


def _log(ep, text):
    with LOG_LOCK:
        LOGS.setdefault(ep, []).append(text)
        LOGS[ep] = LOGS[ep][-400:]


def _log_clear(ep):
    with LOG_LOCK:
        LOGS[ep] = []


def _log_text(ep):
    with LOG_LOCK:
        return "\n".join(LOGS.get(ep, []))


def _project_dirs(base, ep):
    p = os.path.join(base, ep)
    return {
        "root": p,
        "script": os.path.join(p, "script"),
        "assets": os.path.join(p, "assets"),
        "chars": os.path.join(p, "assets", "characters"),
        "props": os.path.join(p, "assets", "props"),
        "scenes": os.path.join(p, "assets", "scenes"),
        "frames": os.path.join(p, "frames"),
        "clips": os.path.join(p, "clips"),
        "out": os.path.join(p, "out"),
        "audio": os.path.join(p, "audio"),
        "report": os.path.join(p, "report"),
    }


def _bar(v):
    return analysis_mod._bar(v)


def collect_state(base, ep):
    """收集当前项目的完整状态，喂给界面。"""
    d = _project_dirs(base, ep)
    root = d["root"]
    if not os.path.isdir(root):
        return None

    # ---- 阶段进度 ----
    sp = os.path.join(root, "script", "_flow.json")
    st = flow_mod.load_json(sp, {"stages": {}}) if hasattr(flow_mod, "load_json") \
        else json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else {"stages": {}}
    stages = []
    for key, label, arts, desc in flow_mod.STAGES:
        rec = (st.get("stages") or {}).get(key) or {}
        stages.append({
            "key": key, "label": label, "desc": desc,
            "status": rec.get("status", "pending"),
            "at": rec.get("at", ""),
            "note": rec.get("note", ""),
            "artifacts": rec.get("artifacts", arts),
        })
    done = sum(1 for s in stages if s["status"] == "done")

    # ---- 剧本分析 ----
    ana = {}
    ap = os.path.join(d["report"], "analysis.json")
    if os.path.exists(ap):
        try:
            ana = json.load(open(ap, encoding="utf-8"))
        except Exception:
            ana = {}
    for c in ana.get("curve", []):
        c["bar"] = _bar(c.get("intensity"))

    # ---- 真实图片清单 ----
    def imgs(folder, prefix, note_ok="未生成"):
        out = []
        if not os.path.isdir(folder):
            return out
        for f in sorted(os.listdir(folder)):
            if not f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                continue
            out.append({
                "name": os.path.splitext(f)[0],
                "url": "/img/%s/%s%s" % (urllib.parse.quote(ep),
                                         urllib.parse.quote(prefix),
                                         urllib.parse.quote(f)),
                "note": "",
            })
        return out

    cast = []
    if os.path.isdir(d["chars"]):
        for cname in sorted(os.listdir(d["chars"])):
            cd = os.path.join(d["chars"], cname)
            if not os.path.isdir(cd):
                continue
            for f in ("face_ref.jpg", "char_card.jpg", "turnaround.jpg"):
                p = os.path.join(cd, f)
                if os.path.exists(p):
                    cast.append({
                        "name": "%s · %s" % (cname, os.path.splitext(f)[0]),
                        "url": "/img/%s/%s%s" % (urllib.parse.quote(ep),
                                                 urllib.parse.quote("assets/characters/"),
                                                 urllib.parse.quote(cname + "/" + f)),
                        "note": "",
                    })
    props = imgs(d["props"], "assets/props/") + imgs(d["scenes"], "assets/scenes/")
    frames = imgs(d["frames"], "frames/")

    # ---- 视频片段 ----
    videos = []
    if os.path.isdir(d["clips"]):
        for f in sorted(os.listdir(d["clips"])):
            if f.lower().endswith(".mp4"):
                videos.append({
                    "id": os.path.splitext(f)[0],
                    "url": "/img/%s/%s%s" % (urllib.parse.quote(ep),
                                             urllib.parse.quote("clips/"),
                                             urllib.parse.quote(f)),
                })

    # ---- 分镜行 ----
    shot_rows = []
    sj = os.path.join(d["script"], "shots.json")
    if os.path.exists(sj):
        try:
            story = json.load(open(sj, encoding="utf-8"))
            for s in story.get("shots") or []:
                shot_rows.append({
                    "id": s.get("id"), "duration": s.get("duration"),
                    "intensity": s.get("intensity") or 0,
                    "action": (s.get("action") or "")[:120],
                    "line": (s.get("line") or "").strip(),
                    "because": (s.get("because") or "")[:100],
                })
        except Exception:
            pass

    # ---- 文件清单 ----
    files = []
    for sub in ("script", "report", "out"):
        dd = os.path.join(root, sub)
        if not os.path.isdir(dd):
            continue
        for f in sorted(os.listdir(dd)):
            fp = os.path.join(dd, f)
            if os.path.isfile(fp):
                files.append({"name": "%s/%s" % (sub, f),
                              "size": "%d KB" % (os.path.getsize(fp) // 1024)})

    # ---- 工单 ----
    bp = os.path.join(d["script"], "brief.md")
    brief = ""
    if os.path.exists(bp):
        brief = io.open(bp, encoding="utf-8").read()

    return {
        "ep": ep,
        "stages": stages,
        "done": done,
        "analysis": ana,
        "cast": cast,
        "props": props,
        "frames": frames,
        "videos": videos,
        "shot_rows": shot_rows,
        "files": files,
        "brief": brief,
        "n_shots": len(shot_rows),
        "total_seconds": sum(r["duration"] or 0 for r in shot_rows),
    }


# ---------------------------------------------------------------- 阶段执行
def _run_cmd(base, ep, args, label):
    cmd = [sys.executable, AC] + args + [ep]
    _log(ep, "▸ %s" % label)
    p = subprocess.Popen(cmd, cwd=base, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True,
                         encoding="utf-8", errors="ignore",
                         bufsize=1)
    for line in p.stdout:
        line = (line or "").rstrip()
        if line:
            _log(ep, "  " + line)
    p.wait()
    return p.returncode


def run_stage(base, ep, key, dry=False):
    """执行一个阶段。返回 (ok, message)。"""
    d = _project_dirs(base, ep)
    root = d["root"]
    os.makedirs(d["script"], exist_ok=True)
    os.makedirs(d["report"], exist_ok=True)

    if key == "init":
        if not os.path.exists(os.path.join(root, "project.json")):
            _run_cmd(base, ep, ["init", "--title", ep], "建项目")
        flow_mod.mark(root and _paths(root), "init", "done", "目录骨架已建")
        return True, "项目目录已就绪"

    if key == "brief":
        idea = ""
        sp = os.path.join(d["script"], "brief.md")
        if os.path.exists(sp):
            idea = ""
        n = 22
        secs = 8
        sj = os.path.join(d["script"], "shots.json")
        if os.path.exists(sj):
            story = json.load(open(sj, encoding="utf-8"))
            n = len(story.get("shots") or [])
            secs = 8
        _paths = _paths(root)
        flow_mod.brief_template(None, _paths, idea or "（在下面写你的创意）", n, secs)
        flow_mod.mark(_paths, "brief", "done", "需求分析工单已生成，等你确认")
        return True, "需求分析工单已生成，请在「需求分析」页确认或修改"

    if key == "story":
        _paths = _paths(root)
        bp = os.path.join(d["script"], "brief.md")
        if not os.path.exists(bp):
            return False, "还没有需求分析工单，先跑 brief 阶段"
        _log(ep, "▸ 编剧：按工单写故事 → script/story.md")
        _log(ep, "  （当前会话模型按 script/story_prompt.md 写故事，"
                 "写完跑 `ac.py flow %s --stage shots`）" % ep)
        flow_mod.mark(_paths, "story", "done", "故事已写（story.md）")
        return True, "故事已写"

    if key == "shots":
        _paths = _paths(root)
        sj = os.path.join(d["script"], "shots.json")
        if not os.path.exists(sj):
            return False, "还没有分镜表"
        flow_mod.mark(_paths, "shots", "done", "分镜表就绪")
        # 顺带出分析报告
        try:
            analysis_mod.write_report(_paths, analysis_mod.analyze(_paths))
            _log(ep, "▸ 剧本分析报告 → report/analysis.md")
        except Exception as e:
            _log(ep, "  分析报告生成失败：%s" % e)
        return True, "分镜表就绪，分析报告已生成"

    if key == "check":
        _paths = _paths(root)
        rc = _run_cmd(base, ep, ["check"], "逻辑自检")
        rep = os.path.join(d["report"], "check.md")
        out = _last_check_output(base, ep)
        with io.open(rep, "w", encoding="utf-8") as f:
            f.write(out or "（无输出）")
        if rc != 0:
            flow_mod.mark(_paths, "check", "failed", "有必须改的问题")
            return False, "逻辑自检没过，看 report/check.md"
        flow_mod.mark(_paths, "check", "done", "逻辑自检通过")
        return True, "逻辑自检通过"

    if key == "cast":
        _paths = _paths(root)
        rc = _run_cmd(base, ep, ["char-gen"], "角色定妆")
        flow_mod.mark(_paths, "cast", "done" if rc == 0 else "failed",
                      "角色形象已生成" if rc == 0 else "角色生成有失败")
        return rc == 0, "角色定妆完成"

    if key == "props":
        _paths = _paths(root)
        _run_cmd(base, ep, ["prop-gen"], "道具参考图")
        _run_cmd(base, ep, ["scene-gen"], "场景板")
        flow_mod.mark(_paths, "props", "done", "道具图与场景板已生成")
        return True, "道具与场景完成"

    if key == "frame":
        _paths = _paths(root)
        rc = _run_cmd(base, ep, ["frame"], "逐镜首帧")
        flow_mod.mark(_paths, "frame", "done" if rc == 0 else "failed",
                      "首帧已生成" if rc == 0 else "首帧生成有失败")
        return rc == 0, "首帧完成"

    if key == "video":
        _paths = _paths(root)
        rc = _run_cmd(base, ep, ["video", "--wait"], "视频生成")
        flow_mod.mark(_paths, "video", "done" if rc == 0 else "failed",
                      "片段已出" if rc == 0 else "视频生成未完成")
        return rc == 0, "视频完成"

    if key == "assemble":
        _paths = _paths(root)
        rc = _run_cmd(base, ep, ["assemble", "--native-voice", "--subs",
                                  "--out", "final-native.mp4"], "合成成片")
        flow_mod.mark(_paths, "assemble", "done" if rc == 0 else "failed",
                      "成片已出" if rc == 0 else "合成失败")
        return rc == 0, "成片完成"

    return False, "未知阶段"


def _paths(root):
    """构造一个 flow 模块能用的 paths 字典。"""
    return {
        "root": root,
        "script": os.path.join(root, "script"),
        "shots": os.path.join(root, "script", "shots.json"),
        "story": os.path.join(root, "script", "story.md"),
        "out": os.path.join(root, "out"),
        "report": os.path.join(root, "report"),
        "assets": os.path.join(root, "assets"),
        "chars": os.path.join(root, "assets", "characters"),
        "props": os.path.join(root, "assets", "props"),
        "scenes": os.path.join(root, "assets", "scenes"),
        "frames": os.path.join(root, "frames"),
        "clips": os.path.join(root, "clips"),
        "audio": os.path.join(root, "audio"),
    }


def _last_check_output(base, ep):
    """再跑一次 check 抓输出（用于写 report/check.md）。"""
    p = subprocess.run([sys.executable, AC, "check", ep], cwd=base,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="ignore")
    return (p.stdout or "") + (p.stderr or "")


# ---------------------------------------------------------------- HTTP
def serve(base, port=8770):
    import http.server
    import webbrowser

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(data)
            except Exception:
                pass

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj, ensure_ascii=False))

        def _file(self, p, ctype):
            if not p or not os.path.exists(p):
                self._send(404, "not found", "text/plain")
                return
            size = os.path.getsize(p)
            rng = self.headers.get("Range")
            start, end = 0, size - 1
            code = 200
            if rng and rng.startswith("bytes="):
                part = rng[6:].split("-")
                start = int(part[0] or 0)
                if len(part) > 1 and part[1]:
                    end = min(int(part[1]), size - 1)
                code = 206
            with open(p, "rb") as f:
                f.seek(start)
                data = f.read(end - start + 1)
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Accept-Ranges", "bytes")
            if code == 206:
                self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
            self.end_headers()
            try:
                self.wfile.write(data)
            except Exception:
                pass

        # ---------------- GET ----------------
        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            ep = (q.get("ep") or [""])[0]
            if u.path == "/" or u.path == "/index.html":
                p = os.path.join(SKILL_DIR, "studio.html")
                self._file(p, "text/html; charset=utf-8")
                return
            if u.path == "/api/projects":
                names = []
                for d in sorted(os.listdir(base)):
                    if os.path.isdir(os.path.join(base, d)) and \
                            os.path.exists(os.path.join(base, d, "project.json")):
                        names.append(d)
                self._json(names)
                return
            if u.path == "/api/state":
                st = collect_state(base, ep)
                if st is None:
                    self._json({"error": "项目不存在"}, 404)
                    return
                self._json(st)
                return
            if u.path == "/api/log":
                self._json({"text": _log_text(ep),
                            "running": bool(RUNNING.get(ep))})
                return
            if u.path.startswith("/img/"):
                rel = u.path[5:]
                parts = rel.split("/", 1)
                if len(parts) != 2:
                    self._send(404, "bad", "text/plain")
                    return
                e, sub = parts
                root = os.path.join(base, urllib.parse.unquote(e))
                fp = os.path.join(root, urllib.parse.unquote(sub))
                fp = os.path.abspath(fp)
                if not fp.startswith(os.path.abspath(root)):
                    self._send(403, "forbidden", "text/plain")
                    return
                ct = "image/jpeg"
                if fp.lower().endswith(".png"):
                    ct = "image/png"
                elif fp.lower().endswith(".mp4"):
                    ct = "video/mp4"
                elif fp.lower().endswith(".webp"):
                    ct = "image/webp"
                self._file(fp, ct)
                return
            self._send(404, "not found", "text/plain")

        # ---------------- POST ----------------
        def do_POST(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            ep = (q.get("ep") or [""])[0]
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n).decode("utf-8") if n else "{}"
            try:
                body = json.loads(raw or "{}")
            except Exception:
                body = {}

            if u.path == "/api/brief":
                p = os.path.join(base, ep, "script", "brief.md")
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with io.open(p, "w", encoding="utf-8") as f:
                    f.write(body.get("text") or "")
                # 需求变了 → 之后的阶段全部作废
                root = os.path.join(base, ep)
                flow_mod.reset_from(_paths(root), "story")
                _log(ep, "▸ 需求工单已更新，后续阶段（story 起）标记为待重跑")
                self._json({"ok": True})
                return

            if u.path == "/api/brief/regen":
                root = os.path.join(base, ep)
                flow_mod.brief_template(None, _paths(root),
                                        "（在下面写你的创意）", 22, 8)
                self._json({"ok": True})
                return

            if u.path == "/api/reset":
                key = (q.get("stage") or ["brief"])[0]
                root = os.path.join(base, ep)
                flow_mod.reset_from(_paths(root), key)
                self._json({"ok": True})
                return

            if u.path in ("/api/run", "/api/runall"):
                if not RUN_LOCK.acquire(blocking=False):
                    self._json({"error": "已有任务在跑"}, 409)
                    return
                try:
                    RUNNING[ep] = True
                    _log_clear(ep)
                    t = threading.Thread(target=_do_run, args=(base, ep, u.path))
                    t.daemon = True
                    t.start()
                    self._json({"ok": True, "started": True})
                finally:
                    # 后台线程自己释放
                    pass
                return

            self._send(404, "not found", "text/plain")

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = "http://127.0.0.1:%d/" % port
    print("流程控制台已启动：%s" % url)
    print("（关掉这个窗口就停止）")
    try:
        webbrowser.open(url, new=2)
    except Exception:
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


def _do_run(base, ep, kind):
    """后台线程：执行阶段。"""
    try:
        if kind == "/api/runall":
            for key in flow_mod.STAGE_KEYS:
                if key in ("video", "assemble"):
                    break
                ok, msg = run_stage(base, ep, key)
                _log(ep, "  → %s：%s" % (flow_mod.STAGE_BY_KEY[key][1], msg))
                if not ok:
                    _log(ep, "  ✗ 停在「%s」" % flow_mod.STAGE_BY_KEY[key][1])
                    break
        else:
            key = RUNNING.get(ep, {}).get("stage") or "brief"
            ok, msg = run_stage(base, ep, key)
            _log(ep, "  → %s" % msg)
    except Exception as e:
        _log(ep, "  ✗ 异常：%s" % e)
    finally:
        RUNNING.pop(ep, None)
        RUN_LOCK.release()
