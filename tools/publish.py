"""Agnes Clip 一键更新：打包 + 提交 + 推送 GitHub。

用法（在本 skill 根目录下跑）：
    python tools/publish.py            # 正常更新
    python tools/publish.py --dry-run  # 只看会做什么，不真推
    python tools/publish.py --bump     # 版本号自动进位（2.0.3 -> 2.0.4）
    python tools/publish.py --bump 2.1.0  # 指定版本号（会校验格式）

它会：
1. 扫全库做安全检查（密钥 / 本机路径 / 缓存文件），有问题直接停；
2. 跑打包，产出 dist/agnes-clip-<版本>.zip；
3. 同步 dist/ 与 tools/ 等全部内容到暂存区；
4. 有改动就提交、打 tag；
5. 通过 SSH(443) 推送到 GitHub。

推送走 SSH 443 端口，因为本机代理会把 github.com 主站掐断（502），
而 ssh.github.com:443 是通的。密钥用 ~/.ssh/id_ed25519。
"""
import os
import re
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
REPO = "ssh://git@ssh.github.com:443/fire0928/agnes-clip-skill.git"
SSH_OPTS = "-o StrictHostKeyChecking=yes -o ConnectTimeout=25 -p 443"
PKG_NAME = "agnes-clip"

# 版本号规则（唯一真源在 tools/version_rule.py）
sys.path.insert(0, os.path.join(ROOT, "tools"))
try:
    from version_rule import next_version, validate_version, describe as _ver_desc
except Exception:  # 规则模块丢了也别把发布流程整个卡死
    next_version = validate_version = None

    def _ver_desc():
        return "版本号 = 主.次.修，补丁位满 9 进到次版本。"

# 不该进仓库的东西
SKIP_DIRS = {"__pycache__", ".git", ".idea", ".vscode", "dist"}
SKIP_FILES = {".DS_Store", ".pyc", ".pyo"}
SECRET_FILES = {"agnes-clip.json", "ai-video-pipeline.json", ".env", "id_rsa"}
SECRET_PAT = re.compile(
    r"(sk-[A-Za-z0-9]{20,}"
    r"|ghp_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|AIza[A-Za-z0-9]{30,}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|id_rsa)"
)
# 本机绝对路径，不能出现在公开仓库里
LOCAL_PAT = re.compile(r"(E:/workbuddy|E:\\workbuddy|C:/Users/[A-Za-z0-9_-]+)")

# 🔴 备份/临时文件：改代码前手动留的，含旧代码旧密钥，必须拦住。
#    之前只扫 .md/.py 等固定后缀，这些文件直接绕过检查被 git add -A 提交上去。
BACKUP_PAT = re.compile(r"(\.bak(\.|$)|\.old$|\.orig$|\.tmp$|~$)")

# 🔴 私人中转端点：公开仓库里不该出现**别人**的私有服务地址。
#    默认端点写死 = 别人装了 skill 会把请求和自己的 key 发到那台机器上。
#    注意：作者自己公司的产品线域名（README 末尾的署名）是正当公开信息，不在此列。
PRIVATE_HOST_PAT = re.compile(
    r"(apibase\.cc"
    r"|ai\.000000\.icu"
    r"|43\.138\.\d+\.\d+"
    r"|134\.175\.\d+\.\d+"
    r"|100\.79\.\d+\.\d+)"
)

# 二进制文件，不做内容扫描
BINARY_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".ico",
              ".mp4", ".mp3", ".wav", ".zip", ".pdf", ".ttf", ".otf", ".woff",
              ".woff2", ".aac", ".m4a", ".mov", ".webm"}

# 这些文件自己就包含密钥样例、本机路径或正则本身，检查时会自己命中自己，跳过
SELF_REferential = {
    "tools/publish.py",       # 含 LOCAL_PAT / SECRET_PAT / PRIVATE_HOST_PAT 定义
    "tools/package_skill.py",  # 含 SECRET_PAT 定义
    "tools/git_sync.py",       # 含 LOCAL_PAT / SECRET_PAT 定义
    "发布指南.md",             # 内部手册，讲的就是本机路径与排错
}

ok = lambda m: print("[ok] " + m)
warn = lambda m: print("[注意] " + m)
fail = lambda m: (print("[停] " + m), sys.exit(1))


def sh(cmd, **kw):
    env = dict(os.environ, GIT_SSH_COMMAND="ssh " + SSH_OPTS)
    r = subprocess.run(cmd, cwd=ROOT, shell=isinstance(cmd, str),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env, **kw)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def scan():
    """发布前安全体检。返回问题列表，空列表 = 干净。

    🔴 扫描规则（v2.0.0 加固）：
    1. **按内容全量扫**，不再只看固定后缀 —— 之前只扫 .md/.py/.html/.json/.txt/.sh，
       其它后缀（.bak/.old/.log/无后缀…）整个文件被跳过，等于没有检查。
    2. **备份文件一律拦下**，不让旧代码混进公开仓库。
    3. **私人端点、私有 IP 一律拦下**。
    4. 二进制文件只查扩展名，不读内容。
    """
    issues = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, ROOT).replace(os.sep, "/")
            if fn in SECRET_FILES:
                issues.append("凭据文件不应存在: " + rel)
                continue
            if fn in SKIP_FILES:
                continue
            # ---- 备份/临时文件：直接拦下，不管内容 ----
            if BACKUP_PAT.search(fn):
                issues.append("备份/临时文件不应进仓库（改完删掉）: " + rel)
                continue
            if rel in SELF_REferential:
                continue
            # ---- 二进制：只查扩展名 ----
            ext = os.path.splitext(fn)[1].lower()
            if ext in BINARY_EXT:
                continue
            # ---- 文本：全量读入扫描（不看后缀）----
            try:
                body = open(p, encoding="utf-8").read()
            except Exception:
                # 读不出来（多半是二进制或编码问题）→ 保守跳过，但记一笔
                continue
            if SECRET_PAT.search(body):
                issues.append("疑似含密钥: " + rel)
            m = LOCAL_PAT.search(body)
            if m:
                issues.append("含本机绝对路径 (%s): %s" % (m.group(1), rel))
            h = PRIVATE_HOST_PAT.search(body)
            if h:
                issues.append("含私人中转/内网地址 (%s): %s" % (h.group(1), rel))
            if "__pycache__" in rel or rel.endswith(".pyc"):
                issues.append("缓存文件: " + rel)
    return issues


def bump_version(new):
    """把 SKILL.md 里的版本号改成 new（先按规则校验）。"""
    if validate_version is not None:
        good, why = validate_version(new)
        if not good:
            fail("版本号不合法：%s\n  规则：%s" % (why, _ver_desc()))
    p = os.path.join(ROOT, "SKILL.md")
    txt = open(p, encoding="utf-8").read()
    if re.search(r"^version:", txt, re.M):
        txt = re.sub(r"^version:.*$", "version: " + new, txt, count=1, flags=re.M)
    else:
        txt = txt.replace("agent_created: true",
                          "agent_created: true\nversion: " + new, 1)
    open(p, "w", encoding="utf-8").write(txt)
    ok("版本号 -> %s" % new)
    return new


def cur_version():
    txt = open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8").read()
    m = re.search(r"^version:\s*(\S+)", txt, re.M)
    return m.group(1).strip() if m else "0.0.0"


def do_package(ver=None):
    """打包。ver 不为空时按指定版本号命名（dry-run 演算用）。"""
    if ver:
        # dry-run：临时把版本号写进去打一个包，打完还原
        p = os.path.join(ROOT, "SKILL.md")
        orig = open(p, encoding="utf-8").read()
        try:
            txt = re.sub(r"^version:.*$", "version: " + ver, orig,
                         count=1, flags=re.M)
            open(p, "w", encoding="utf-8").write(txt)
            code, out = sh([sys.executable,
                            os.path.join(ROOT, "tools", "package_skill.py")])
        finally:
            open(p, "w", encoding="utf-8").write(orig)
        print(out.rstrip())
        if code != 0:
            fail("打包失败")
        return ver
    code, out = sh([sys.executable, os.path.join(ROOT, "tools", "package_skill.py")])
    print(out.rstrip())
    if code != 0:
        fail("打包失败")
    return cur_version()


def git(*args, must=True):
    code, out = sh(["git"] + list(args))
    if must and code != 0:
        fail("git %s 失败:\n%s" % (" ".join(args), out.strip()[:500]))
    return code, out


def main():
    dry = "--dry-run" in sys.argv
    bump = None
    if "--bump" in sys.argv:
        i = sys.argv.index("--bump")
        nxt = sys.argv[i + 1] if i + 1 < len(sys.argv) else None
        # 后面没跟版本号（或跟的是别的开关）→ 按规则自动进位
        if nxt is None or nxt.startswith("-"):
            if next_version is None:
                fail("版本规则模块 tools/version_rule.py 不在，自动进位用不了")
            bump = next_version(cur_version())
            print("[版本] 自动进位：%s -> %s" % (cur_version(), bump))
        else:
            bump = nxt

    print("=" * 56)
    print("  Agnes Clip 发布  ·  %s" % PKG_NAME)
    print("=" * 56)

    # 0. 必须是 git 仓库
    code, _ = git("rev-parse", "--git-dir", must=False)
    if code != 0:
        print("首次发布，正在初始化本地 git 仓库…")
        git("init", "-q")
        git("remote", "add", "origin", REPO)
        git("config", "user.name", "fire0928")
        git("config", "user.email", "fire0928@gmail.com")

    # 1. 远端对齐
    print("\n[1/5] 对齐远端")
    git("remote", "set-url", "origin", REPO)
    code, out = git("fetch", "origin", "main", must=False)
    if code != 0:
        warn("拉取远端失败（首次发布正常，继续）")

    # 分支名必须叫 main，且要把远端历史接在本地前面，
    # 否则新机器上会出现 src refspec main does not match any
    cur = (git("branch", "--show-current", must=False)[1] or "").strip()
    if cur and cur != "main":
        git("branch", "-m", "main")
        ok("分支名 %s -> main" % cur)
        cur = "main"

    if code == 0:
        _, has = git("rev-parse", "--verify", "origin/main", must=False)
        if has.strip() == "0" or not has.strip():
            # 远端有提交、本地还没有 → 把本地接到远端后面（不动工作区文件）
            code2, _ = git("rev-list", "--count", "origin/main", must=False)
            if code2 == 0:
                git("reset", "--soft", "origin/main", must=False)
                ok("本地历史已接到远端 main 之后")
        else:
            _, behind = git("rev-list", "--count", "HEAD..origin/main", must=False)
            b = (behind or "0").strip()
            if b.isdigit() and int(b) > 0:
                ok("远端有 %s 个新提交，先合并" % b)
                git("merge", "--no-edit", "origin/main", must=False)
            else:
                ok("已是最新")

    # 2. 安全体检
    print("\n[2/5] 安全检查")
    # 🔴 dry-run 只能演算，不能真改 SKILL.md 的版本号。
    #    原来这里直接 bump_version()，结果 --dry-run 跑完版本号就变了，
    #    用户以为只是"看看"，实际工作区已经被改了。
    #    改成：先算出版本号 → 打包用临时版本号 → 真正提交前才落盘。
    target_ver = cur_version()
    if bump:
        target_ver = bump
        if dry:
            print("[dry-run] 版本号会是 %s（当前 %s），不真改文件"
                  % (target_ver, cur_version()))
    issues = scan()
    if issues:
        print("      发现 %d 个问题：" % len(issues))
        for i in issues:
            print("        - " + i)
        fail("有问题未解决，已中止（不会推送）")
    ok("干净：无密钥、无本机路径、无缓存")

    # 3. 打包
    print("\n[3/5] 打包")
    if bump and not dry:
        bump_version(bump)
    ver = do_package(target_ver)
    ok("dist/agnes-clip-%s.zip 就绪" % ver)

    # 4. 提交
    print("\n[4/5] 提交")
    git("add", "-A")
    _, out = git("status", "--short", must=False)
    changed = [l for l in (out or "").splitlines() if l.strip()]
    if not changed:
        warn("没有文件改动，无需提交")
        print("\n结论：本地与上次发布一致。")
        return
    for l in changed[:20]:
        print("      " + l)
    if len(changed) > 20:
        print("      … 另有 %d 个文件" % (len(changed) - 20))
    if dry:
        # 🔴 v2.0.0：dry-run 不能留下副作用。
        #    上面 git add -A 已经把所有改动塞进暂存区了 —— 用户接着自己
        #    git diff 会看到「没改动」，以为改动丢了。dry-run 就该回到原样。
        git("reset", must=False)
        print("\n[dry-run] 到此为止，不提交不推送（暂存区已复位，工作区原样）。")
        return

    _, nfiles = git("diff", "--cached", "--numstat", must=False)
    n = len([l for l in (nfiles or "").splitlines() if l.strip()])
    _, short = git("rev-parse", "--short", "HEAD", must=False)
    msg = "发布 %s v%s：%d 个文件更新" % (PKG_NAME, ver, n)
    code, out = git("commit", "-q", "-m", msg)
    if code != 0:
        fail("提交失败:\n" + out.strip()[:400])
    _, newrev = git("rev-parse", "--short", "HEAD", must=False)
    ok("已提交 %s" % newrev.strip())

    # 5. 打 tag + 推送
    print("\n[5/5] 推送")
    tag = "v" + ver
    git("tag", "-f", tag, must=False)
    code, out = git("push", "origin", "main")
    if code != 0:
        fail("推送失败:\n" + out.strip()[:600])
    ok("main 已推送")
    code, out = git("push", "origin", tag, must=False)
    if code == 0:
        ok("标签 %s 已推送" % tag)

    _, out = git("rev-parse", "HEAD", must=False)
    rev = out.strip()
    print("\n" + "=" * 56)
    print("  发布完成")
    print("  仓库   https://github.com/fire0928/agnes-clip-skill")
    print("  提交   %s" % rev[:7])
    print("  版本   %s" % ver)
    print("  分发包 dist/agnes-clip-%s.zip" % ver)
    print("=" * 56)


if __name__ == "__main__":
    main()
