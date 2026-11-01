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
    r"(sk-[A-Za-z0-9]{20,}"
    r"|ghp_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|AIza[A-Za-z0-9]{30,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9]{20,})"
)
# 🔴 备份/临时文件：改代码前留的旧版本，含旧密钥，绝不能进包。
BACKUP_PAT = re.compile(r"(\.bak(\.|$)|\.old$|\.orig$|\.tmp$|~$)")
# 🔴 私人中转/内网地址：公开分发包里不该有别人的私有服务器地址。
#    注意：作者自己公司的产品线域名是正当公开信息，不在此列。
PRIVATE_HOST_PAT = re.compile(
    r"(apibase\.cc"
    r"|ai\.000000\.icu"
    r"|43\.138\.\d+\.\d+"
    r"|134\.175\.\d+\.\d+"
    r"|100\.79\.\d+\.\d+)"
)
# 本机绝对路径
LOCAL_PAT = re.compile(r"(E:/workbuddy|E:\\workbuddy|C:/Users/[A-Za-z0-9_-]+)")
# 二进制文件，不读内容
BINARY_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".ico",
              ".mp4", ".mp3", ".wav", ".zip", ".pdf", ".ttf", ".otf", ".woff",
              ".woff2", ".aac", ".m4a", ".mov", ".webm"}
# 这些文件自身含正则定义，扫描时会自己命中自己
SELF_REF = {"tools/package_skill.py", "tools/publish.py", "tools/git_sync.py",
            "发布指南.md"}


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
    """收集要打进 zip 的文件。

    🔴 v2.0.0 加固：
    1. **按内容全量扫**，不再只看固定后缀（之前 .bak/.old/无后缀文件直接漏掉）；
    2. **备份文件一律不进包**；
    3. **私人端点、本机绝对路径一律不进包**。
    """
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn in SKIP_FILES or fn in SECRET_FILES or fn in SKIP_NAMES:
                continue
            if BACKUP_PAT.search(fn):
                print("  [跳过] 备份/临时文件: %s" % os.path.relpath(
                    os.path.join(dirpath, fn), ROOT))
                continue
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, ROOT).replace(os.sep, "/")
            if rel in SELF_REF:
                out.append(p)
                continue
            ext = os.path.splitext(fn)[1].lower()
            if ext in BINARY_EXT:
                out.append(p)
                continue
            try:
                body = open(p, encoding="utf-8").read()
            except Exception:
                out.append(p)      # 读不出来的（多半是二进制），放行但不再检查
                continue
            if SECRET_PAT.search(body):
                print("  [跳过] 疑似含密钥: %s" % rel)
                continue
            if LOCAL_PAT.search(body):
                print("  [跳过] 含本机绝对路径: %s" % rel)
                continue
            if PRIVATE_HOST_PAT.search(body):
                print("  [跳过] 含私人中转/内网地址: %s" % rel)
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
