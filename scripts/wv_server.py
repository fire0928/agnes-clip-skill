#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wv_server.py —— 世界观工作台的本地服务（零第三方依赖）。

给两个 skill 共用：
    python wv_server.py <项目目录> [--port 8777] [--no-open]

提供：
    GET  /                 页面
    GET  /api/episode       当前集的全部内容（?dir=xxx 可切集）
    GET  /api/asset        读项目里的图片（角色定妆图、道具图）
    POST /api/save         保存改过的内容
    POST /api/save-series  保存系列级世界观

安全：只监听 127.0.0.1，路径参数会被规整到项目根之内，读不到项目外的东西。
"""
import http.server
import json
import os
import posixpath
import sys
import urllib.parse
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wv_core  # noqa: E402

UI_PATH = os.path.join(HERE, "worldview_ui.html")
# 项目里可能有多个 skill 各自的 UI 文件，优先找同目录的
for _alt in ("worldview_ui.html",):
    _p = os.path.join(HERE, _alt)
    if os.path.exists(_p):
        UI_PATH = _p
        break


def _read_ui():
    with open(UI_PATH, "r", encoding="utf-8") as f:
        return f.read()


def safe_join(root, *parts):
    """把路径拼到 root 之内，挡掉 ../ 越界。"""
    base = os.path.abspath(root)
    p = os.path.normpath(os.path.join(base, *parts))
    if not (p == base or p.startswith(base + os.sep)):
        return None
    return p


def make_handler(default_root):
    default_root = os.path.abspath(default_root)

    def allowed_root(candidate):
        """只允许写「当前项目」或「同系列其它集」。

        系列根 = 当前项目的父目录（同系列多集都放在那儿）。
        白名单之外一律拒绝 —— 否则接口能被拿来写项目外的任意路径。
        """
        try:
            c = os.path.abspath(candidate)
        except Exception:
            return None
        if c == default_root:
            return c
        series_root = os.path.dirname(default_root)
        try:
            if os.path.commonpath([c, series_root]) == series_root and c != series_root:
                # 必须是个真项目（有自己的 shots.json）
                if os.path.exists(os.path.join(c, "script", "shots.json")):
                    return c
        except ValueError:
            pass
        return None

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
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj, ensure_ascii=False))

        # ── GET ──
        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            if u.path in ("/", "/index.html"):
                self._send(200, _read_ui(), "text/html")
                return
            if u.path == "/favicon.ico":
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if u.path == "/api/episode":
                root = allowed_root((q.get("dir") or [default_root])[0])
                if not root:
                    self._json({"ok": False, "message": "只能打开当前项目或同系列的其它集"}, 403)
                    return
                if not os.path.isdir(root):
                    self._json({"ok": False, "message": "目录不存在"}, 404)
                    return
                try:
                    self._json(wv_core.load_episode(root))
                except Exception as e:
                    self._json({"ok": False, "message": str(e)[:400]}, 500)
                return
            if u.path == "/api/asset":
                self._serve_asset(q)
                return
            self._json({"ok": False, "message": "not found"}, 404)

        def _serve_asset(self, q):
            root = os.path.abspath((q.get("ep") or [default_root])[0])
            kind = (q.get("kind") or ["characters"])[0]
            name = (q.get("name") or [""])[0]
            fn = (q.get("file") or [""])[0]
            if kind not in ("characters", "props", "scenes"):
                self._json({"ok": False, "message": "bad kind"}, 400)
                return
            # 两种布局：子目录式 assets/<kind>/<name>/<file> 与平铺式 assets/<kind>/<file>
            cands = [
                safe_join(root, "assets", kind, name, fn),
                safe_join(root, "assets", kind, fn),
            ]
            p = None
            for c in cands:
                if c and os.path.isfile(c):
                    p = c
                    break
            if not p:
                self._json({"ok": False, "message": "file not found"}, 404)
                return
            ext = os.path.splitext(p)[1].lower()
            ctype = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                     ".png": "image/png", ".webp": "image/webp"}.get(ext, "application/octet-stream")
            with open(p, "rb") as f:
                self._send(200, f.read(), ctype)

        # ── POST ──
        def do_POST(self):
            u = urllib.parse.urlparse(self.path)
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = 0
            raw = self.rfile.read(n) if n else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except Exception as e:
                self._json({"ok": False, "message": "请求体不是 JSON"}, 400)
                return

            if u.path == "/api/save":
                root = allowed_root(body.get("root") or default_root)
                if not root:
                    self._json({"ok": False, "message": "只能写当前项目或同系列的其它集"}, 403)
                    return
                try:
                    r = wv_core.save_episode(root, body.get("payload") or {})
                    self._json(r)
                except Exception as e:
                    self._json({"ok": False, "message": str(e)[:400]}, 500)
                return
            if u.path == "/api/save-series":
                root = allowed_root(body.get("root") or default_root)
                if not root:
                    self._json({"ok": False, "message": "只能写当前项目或同系列的其它集"}, 403)
                    return
                try:
                    r = wv_core.save_series_worldview(root, body.get("text") or "")
                    self._json(r)
                except Exception as e:
                    self._json({"ok": False, "message": str(e)[:400]}, 500)
                return
            self._json({"ok": False, "message": "not found"}, 404)

    return Handler


def serve(root, port=8777, open_browser=True, stop_after=None):
    """起服务。stop_after 是秒数（测试用），到点自动关。"""
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        print("[停] 目录不存在: " + root)
        sys.exit(1)
    handler = make_handler(root)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = "http://127.0.0.1:%d/" % port
    print("世界观工作台已启动: " + url)
    print("项目: " + root)
    print("关掉这个窗口就停服务。")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    if stop_after:
        import threading
        threading.Timer(stop_after, httpd.shutdown).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def main():
    args = sys.argv[1:]
    root = None
    port = 8777
    open_browser = True
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--port" and i + 1 < len(args):
            port = int(args[i + 1]); i += 2; continue
        if a == "--no-open":
            open_browser = False; i += 1; continue
        if not a.startswith("-"):
            root = a
        i += 1
    if not root:
        print("用法: python wv_server.py <项目目录> [--port 8777] [--no-open]")
        sys.exit(1)
    serve(root, port=port, open_browser=open_browser)


if __name__ == "__main__":
    main()
