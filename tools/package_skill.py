"""把 skill 打成可分发 zip（不含 __pycache__ / .pyc / 本机凭据）。

用法：
    python tools/package_skill.py
输出：
    dist/agnes-clip-<版本>.zip      结构 = 仓库根目录带 agnes-clip/ 一层
    dist/agnes-clip-<版本>.sha256   校验值
"""
import hashlib
import os
import re
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
PKG_NAME = "agnes-clip"

# 不进包的东西
# 注意：tools/ 不再整个排除 —— git_sync.py 必须带着，
# 装完的人才能跑 "git_sync.py link" 接入自动更新通道。
SKIP_DIRS = {"__pycache__", ".git", ".idea", ".vscode", "dist"}
SKIP_FILES = {".DS_Store", ".pyc", ".pyo", ".log"}
# 只给平哥自己看的操作手册，对外不发
SKIP_NAMES = {"发布指南.md", "建仓说明.md"}
# 本机凭据，绝不能进包
SECRET_FILES = {"agnes-clip.json", "ai-video-pipeline.json", ".env", "id_rsa"}
SECRET_PAT = re.compile(
    r"(sk-[A-Za-z0-9]{20,}|api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9]{20,})"
)


def version():
    """从 SKILL.md 里读 version 字段，读不到就用 mtime。"""
    try:
        txt = open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8").read()
        m = re.search(r"^version:\s*(\S+)", txt, re.M)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    return "1.0.0"


def collected():
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn in SKIP_FILES or fn in SECRET_FILES or fn in SKIP_NAMES:
                continue
            p = os.path.join(dirpath, fn)
            if fn.endswith((".md", ".py", ".html", ".json", ".txt")):
                try:
                    body = open(p, encoding="utf-8").read()
                except Exception:
                    continue
                if SECRET_PAT.search(body):
                    print("  [跳过] 疑似含密钥: %s" % os.path.relpath(p, ROOT))
                    continue
            out.append(p)
    return out


def main():
    ver = version()
    os.makedirs(DIST, exist_ok=True)
    target = os.path.join(DIST, "%s-%s.zip" % (PKG_NAME, ver))
    files = collected()
    # 仓库根目录统一叫 agnes-clip，别人 clone 下来就是这个名
    prefix = PKG_NAME + "/"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            arc = prefix + os.path.relpath(p, ROOT).replace(os.sep, "/")
            z.write(p, arc)
    h = hashlib.sha256(open(target, "rb").read()).hexdigest()
    with open(target + ".sha256", "w", encoding="utf-8") as f:
        f.write("%s  %s\n" % (h, os.path.basename(target)))

    size = os.path.getsize(target) / 1024
    print("版本   : %s" % ver)
    print("文件数 : %d" % len(files))
    print("大小   : %.1f KB" % size)
    print("输出   : %s" % target)
    print("sha256 : %s" % h)


if __name__ == "__main__":
    main()
