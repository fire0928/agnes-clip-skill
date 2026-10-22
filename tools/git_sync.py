#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""git_sync.py —— skill 仓库的「发布 / 更新 / 检查」一体工具。

用法（在本 skill 根目录下跑）：

    python tools/git_sync.py push            # 安全体检 → 打包 → 提交 → 打tag → 推 GitHub
    python tools/git_sync.py push --bump 1.6.0
    python tools/git_sync.py push --dry-run
    python tools/git_sync.py pull            # 从 GitHub 拉最新（对方更新了自动同步到本机）
    python tools/git_sync.py pull --force    # 丢弃本地未提交改动，强制对齐远端
    python tools/git_sync.py check           # 只看远端有没有新版本，不改本地
    python tools/git_sync.py status          # 本地 / 远端版本对照

推送走 SSH 443 端口（ssh.github.com:443），因为本机代理会把 github.com 主站掐断。
密钥用 ~/.ssh/id_ed25519。

**凭据安全**：push 前会全库扫一遍密钥 / 本机绝对路径 / 缓存文件，有问题直接中止不推。
**本机配置不进仓库**：~ 下的凭据文件永远被 .gitignore 排除。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")

# 仓库地址在各自 skill 的 .git-sync.json 里配（这样工具本身可复用）
CONF_PATH = os.path.join(ROOT, ".git-sync.json")
CONF = {
    "repo": "",                 # ssh://git@ssh.github.com:443/<user>/<repo>.git
    "web": "",                  # 浏览器地址，只用于打印
    "package_name": "",         # 打包出来的 zip 名前缀
    "package_script": "",       # 打包脚本相对路径（可选）
    "branch": "main",
}
if os.path.exists(CONF_PATH):
    try:
        CONF.update(json.load(open(CONF_PATH, encoding="utf-8")))
    except Exception:
        pass

SSH_OPTS = "-o StrictHostKeyChecking=yes -o ConnectTimeout=25 -p 443"

SKIP_DIRS = {"__pycache__", ".git", ".idea", ".vscode", ".workbuddy"}
SKIP_FILES = {".DS_Store", ".pyc", ".pyo"}

# 凭据文件：永远不进仓库
SECRET_FILES = {
    "agnes-clip.json", "ai-video-pipeline.json", ".env", "id_rsa", "id_ed25519",
    ".git-sync.local.json",
}
SECRET_PAT = re.compile(
    r"(sk-[A-Za-z0-9]{20,}"
    r"|ghp_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|AIza[A-Za-z0-9]{30,}"
    r"|cpk-[A-Za-z0-9]{20,}"
    r"|id_rsa)"
)
# 本机绝对路径，不能出现在公开仓库里
LOCAL_PAT = re.compile(r"(E:/workbuddy|E:\\workbuddy|C:/Users/[A-Za-z0-9_-]+)")

# 这些文件自己就包含密钥样例、本机路径或正则本身，检查时会自己命中自己
SELF_REF = {
    "tools/git_sync.py",
    "tools/publish.py",
    "tools/package_skill.py",
    "发布指南.md",
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


def git(*args, must=True):
    code, out = sh(["git"] + list(args))
    if must and code != 0:
        fail("git %s 失败:\n%s" % (" ".join(args), out.strip()[:600]))
    return code, out


# ═══════════════ 通用工具 ═══════════════

def cur_version():
    p = os.path.join(ROOT, "SKILL.md")
    if not os.path.exists(p):
        return "0.0.0"
    txt = open(p, encoding="utf-8").read()
    m = re.search(r"^version:\s*(\S+)", txt, re.M)
    return m.group(1).strip() if m else "0.0.0"


def bump_version(new):
    p = os.path.join(ROOT, "SKILL.md")
    txt = open(p, encoding="utf-8").read()
    if re.search(r"^version:", txt, re.M):
        txt = re.sub(r"^version:.*$", "version: " + new, count=1, flags=re.M)
    else:
        txt = txt.replace("agent_created: true",
                          "agent_created: true\nversion: " + new, 1)
    open(p, "w", encoding="utf-8").write(txt)
    ok("版本号 -> %s" % new)
    return new


def scan():
    """发布前安全体检。返回问题列表，空 = 干净。"""
    issues = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, ROOT).replace(os.sep, "/")
            if fn in SECRET_FILES:
                issues.append("凭据文件不应存在: " + rel)
                continue
            if not fn.endswith((".md", ".py", ".html", ".json", ".txt", ".sh", ".yaml", ".yml")):
                continue
            if rel in SELF_REF:
                continue
            try:
                body = open(p, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            if SECRET_PAT.search(body):
                issues.append("疑似含密钥: " + rel)
            m = LOCAL_PAT.search(body)
            if m:
                issues.append("含本机绝对路径 (%s): %s" % (m.group(1), rel))
            if "__pycache__" in rel or rel.endswith(".pyc"):
                issues.append("缓存文件: " + rel)
    return issues


def ensure_repo():
    """确保是 git 仓库且有远端。"""
    code, _ = git("rev-parse", "--git-dir", must=False)
    if code != 0:
        print("首次使用，正在初始化本地 git 仓库…")
        git("init", "-q")
        git("config", "user.name", "fire0928")
        git("config", "user.email", "fire0928@gmail.com")
    if not CONF.get("repo"):
        fail("没配仓库地址。请在 %s 里填 \"repo\"" % os.path.basename(CONF_PATH))
    git("remote", "set-url", "origin", CONF["repo"], must=False)
    if not os.path.exists(CONF["repo"]):
        pass


def fetch_remote():
    code, out = git("fetch", "origin", CONF.get("branch", "main"), must=False)
    return code == 0, out


def remote_head():
    """远端 main 的短 SHA，拿不到返回空串。"""
    code, out = git("rev-parse", "--short", "origin/" + CONF.get("branch", "main"), must=False)
    if code != 0:
        return ""
    return out.strip()


def local_head():
    code, out = git("rev-parse", "--short", "HEAD", must=False)
    return out.strip() if code == 0 else ""


def ahead_behind():
    """返回 (领先远端几个提交, 落后远端几个提交)。"""
    code, out = git("rev-list", "--left-right", "--count", "HEAD...origin/" +
                    CONF.get("branch", "main"), must=False)
    if code != 0:
        return 0, 0
    parts = out.strip().split()
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        return int(parts[0]), int(parts[1])
    return 0, 0


def do_package():
    """调用 skill 自带的打包脚本（如果有）。"""
    script = CONF.get("package_script")
    if not script:
        return None
    p = os.path.join(ROOT, script)
    if not os.path.exists(p):
        return None
    code, out = sh([sys.executable, p])
    print(out.rstrip())
    if code != 0:
        fail("打包失败")
    return cur_version()


# ═══════════════ push ═══════════════

def cmd_push(args):
    print("=" * 56)
    print("  发布  ·  %s" % (CONF.get("package_name") or os.path.basename(ROOT)))
    print("=" * 56)

    ensure_repo()

    # 1. 远端对齐
    print("\n[1/5] 对齐远端")
    fetched, fout = fetch_remote()
    if not fetched:
        warn("拉取远端失败（首次发布正常，继续）")
    cur = (git("branch", "--show-current", must=False)[1] or "").strip()
    if cur and cur != CONF.get("branch", "main"):
        git("branch", "-m", CONF.get("branch", "main"))
        ok("分支名 %s -> %s" % (cur, CONF.get("branch", "main")))

    if fetched:
        _, has = git("rev-parse", "--verify", "origin/" + CONF.get("branch", "main"), must=False)
        if not has.strip():
            code2, _ = git("rev-list", "--count", "origin/" + CONF.get("branch", "main"), must=False)
            if code2 == 0:
                git("reset", "--soft", "origin/" + CONF.get("branch", "main"), must=False)
                ok("本地历史已接到远端之后")
        else:
            a, b = ahead_behind()
            if b > 0:
                ok("远端有 %d 个新提交，先合并" % b)
                git("merge", "--no-edit", "origin/" + CONF.get("branch", "main"), must=False)
            else:
                ok("已是最新")

    # 2. 安全体检
    print("\n[2/5] 安全检查")
    if args.bump:
        bump_version(args.bump)
    issues = scan()
    if issues:
        print("      发现 %d 个问题：" % len(issues))
        for i in issues:
            print("        - " + i)
        fail("有问题未解决，已中止（不会推送）")
    ok("干净：无密钥、无本机路径、无缓存")

    # 3. 打包
    print("\n[3/5] 打包")
    ver = do_package() or cur_version()
    ok("dist/…-%s.zip 就绪" % ver)

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
    if args.dry_run:
        print("\n[dry-run] 到此为止，不提交不推送。")
        return

    _, nfiles = git("diff", "--cached", "--numstat", must=False)
    n = len([l for l in (nfiles or "").splitlines() if l.strip()])
    _, short = git("rev-parse", "--short", "HEAD", must=False)
    msg = "发布 %s v%s：%d 个文件更新" % (CONF.get("package_name") or "skill", ver, n)
    code, out = git("commit", "-q", "-m", msg)
    if code != 0:
        fail("提交失败:\n" + out.strip()[:400])
    _, newrev = git("rev-parse", "--short", "HEAD", must=False)
    ok("已提交 %s" % newrev.strip())

    # 5. tag + 推送
    print("\n[5/5] 推送")
    tag = "v" + ver
    git("tag", "-f", tag, must=False)
    code, out = git("push", "origin", CONF.get("branch", "main"))
    if code != 0:
        fail("推送失败:\n" + out.strip()[:600])
    ok("%s 已推送" % CONF.get("branch", "main"))
    code, out = git("push", "origin", tag, must=False)
    if code == 0:
        ok("标签 %s 已推送" % tag)

    print("\n" + "=" * 56)
    print("  发布完成")
    if CONF.get("web"):
        print("  仓库   " + CONF["web"])
    print("  提交   %s" % newrev.strip())
    print("  版本   %s" % ver)
    print("=" * 56)


# ═══════════════ pull ═══════════════

def cmd_pull(args):
    if getattr(args, "quiet", False):
        # 定时任务模式：只在有更新时输出，没更新就安静退出
        if not fetch_remote()[0]:
            return
        a, b = ahead_behind()
        if b == 0:
            return
        dirty = bool(git("status", "--porcelain", must=False)[1].strip())
        if dirty:
            git("stash", "push", "-u", "-m", "git_sync 自动暂存", must=False)
        if a > 0:
            code, out = git("rebase", "origin/" + CONF.get("branch", "main"), must=False)
            if code != 0:
                git("rebase", "--abort", must=False)
                print("[git_sync] 有更新但 rebase 冲突，已中止，需要人工处理")
                return
        else:
            git("reset", "--hard", "origin/" + CONF.get("branch", "main"), must=False)
        _, rev = git("rev-parse", "--short", "HEAD", must=False)
        print("[git_sync] 已更新到 %s（版本 %s）" % (rev.strip(), cur_version()))
        return

    print("=" * 56)
    print("  更新  ·  %s" % (CONF.get("package_name") or os.path.basename(ROOT)))
    print("=" * 56)

    if git("rev-parse", "--git-dir", must=False)[0] != 0:
        fail("这里不是 git 仓库，没法更新")
    if not CONF.get("repo"):
        fail("没配仓库地址")
    git("remote", "set-url", "origin", CONF["repo"], must=False)

    print("\n[1/4] 拉取远端")
    fetched, out = fetch_remote()
    if not fetched:
        fail("拉取失败:\n" + out.strip()[:400])

    before = local_head()
    a, b = ahead_behind()
    print("      本地 %s ｜ 远端 %s" % (before or "-", remote_head() or "-"))

    if b == 0:
        print("\n结论：已经是最新，没有可更新的内容。")
        return

    print("      远端有 %d 个新提交%s" % (b, "，本地也有 %d 个未推送提交" % a if a else ""))

    print("\n[2/4] 备份当前状态")
    stash = ""
    _, out = git("stash", "list", must=False)
    dirty = bool(git("status", "--porcelain", must=False)[1].strip())
    if dirty and not args.force:
        print("      本地有未提交改动，先 stash 保护起来")
        git("stash", "push", "-u", "-m", "git_sync 自动暂存", must=False)
        stash = "git_sync 自动暂存"
        ok("已暂存，冲突时可用 git stash pop 找回")
    ok("当前提交 %s 已记在 git log 里，随时能回退" % (before or "-"))

    print("\n[3/4] 合并远端更新")
    if a > 0:
        # 本地有未推送提交 → 用 rebase 保持线性
        code, out = git("rebase", "origin/" + CONF.get("branch", "main"), must=False)
        if code != 0:
            warn("rebase 冲突，自动中止")
            git("rebase", "--abort", must=False)
            fail("需要人工处理冲突：\n" + out.strip()[:600])
        ok("rebase 完成（本地提交接在远端之后）")
    else:
        git("reset", "--hard", "origin/" + CONF.get("branch", "main"), must=False)
        ok("已对齐到远端最新")

    print("\n[4/4] 收尾")
    if stash:
        _, out = git("stash", "pop", must=False)
        if out and "CONFLICT" in out.upper():
            warn("恢复本地改动时冲突，已保留 stash：git stash list")
        else:
            ok("本地改动已恢复")

    _, newrev = git("rev-parse", "--short", "HEAD", must=False)
    print("\n" + "=" * 56)
    print("  更新完成")
    print("  %s → %s" % (before or "-", newrev.strip()))
    print("  本地版本 %s" % cur_version())
    if CONF.get("web"):
        print("  仓库   " + CONF["web"])
    print("=" * 56)
    print("提示：代码变了，如果本 skill 有常驻服务，需要重启它才会加载新代码。")


# ═══════════════ link（把 zip 解压的目录接入自动更新通道）═══════════════

def cmd_link(args):
    """把「解压 zip 装好的 skill」接入自动更新通道。

    场景：别人发你一个 zip，你解压到 ~/.workbuddy/skills/xxx/。
    这时这个目录不是 git 仓库，没法 pull。跑这个命令会：
      1. git init + 绑定远端
      2. 从远端拉一份，把本地对齐到最新版（你手改的内容会先 stash 保护）
      3. 以后跑 `git_sync.py pull` 就能同步

    前提：能访问 GitHub（本机走 SSH 443 端口）。
    """
    print("=" * 56)
    print("  接入自动更新通道  ·  %s" % (CONF.get("package_name") or os.path.basename(ROOT)))
    print("=" * 56)

    if not CONF.get("repo"):
        fail("没配仓库地址。请在 %s 里填 \"repo\"" % os.path.basename(CONF_PATH))

    is_repo = git("rev-parse", "--git-dir", must=False)[0] == 0
    if not is_repo:
        print("\n[1/3] 初始化本地 git 仓库")
        git("init", "-q")
        git("config", "user.name", "fire0928")
        git("config", "user.email", "fire0928@gmail.com")
        git("remote", "add", "origin", CONF["repo"], must=False)
        ok("已初始化并绑定远端")
    else:
        print("\n[1/3] 已经是 git 仓库")
        git("remote", "set-url", "origin", CONF["repo"], must=False)
        ok("远端已指向 " + CONF["repo"])

    print("\n[2/3] 拉取远端最新版")
    fetched, out = fetch_remote()
    if not fetched:
        fail("拉取远端失败（网络不通，或这台机器访问不了 GitHub）：\n" + out.strip()[:400])
    ok("已获取远端")

    # 本地有改动先保护
    dirty = bool(git("status", "--porcelain", must=False)[1].strip())
    if dirty:
        print("      本地有改动，先暂存保护")
        git("stash", "push", "-u", "-m", "git_sync link 自动暂存", must=False)
        ok("已暂存（冲突时 git stash pop 找回）")

    branch = CONF.get("branch", "main")
    code, out = git("reset", "--hard", "origin/" + branch, must=False)
    if code != 0:
        fail("对齐远端失败:\n" + out.strip()[:400])
    ok("已对齐到远端最新版")

    print("\n[3/3] 收尾")
    _, rev = git("rev-parse", "--short", "HEAD", must=False)
    print("\n" + "=" * 56)
    print("  接入完成")
    print("  当前提交 %s ｜ 版本 %s" % (rev.strip(), cur_version()))
    print()
    print("  以后更新：")
    print("    python %s pull" % os.path.join("tools", "git_sync.py"))
    print()
    print("  想让它每天自动更新（Windows 任务计划 / Linux cron）：")
    print("    python %s pull --quiet" % os.path.join("tools", "git_sync.py"))
    print("=" * 56)


# ═══════════════ check / status ═══════════════

def cmd_check(args):
    if git("rev-parse", "--git-dir", must=False)[0] != 0:
        print("不是 git 仓库，无法检查更新。")
        return
    if not CONF.get("repo"):
        fail("没配仓库地址")
    git("remote", "set-url", "origin", CONF["repo"], must=False)
    if not fetch_remote()[0]:
        fail("拉取远端失败（网络问题？）")
    a, b = ahead_behind()
    print("本地版本 %s ｜ 提交 %s" % (cur_version(), local_head() or "-"))
    print("远端提交 %s" % (remote_head() or "-"))
    if b > 0:
        print("\n有 %d 个新提交可用。跑：python tools/git_sync.py pull" % b)
    else:
        print("\n已是最新。")
    if a > 0:
        print("（本地还有 %d 个未推送提交）" % a)


def cmd_status(args):
    print("skill 目录 : %s" % ROOT)
    print("版本       : %s" % cur_version())
    print("仓库       : %s" % (CONF.get("repo") or "未配置"))
    if git("rev-parse", "--git-dir", must=False)[0] == 0:
        print("本地提交   : %s" % (local_head() or "-"))
        print("远端提交   : %s" % (remote_head() or "-"))
        a, b = ahead_behind()
        print("领先/落后  : %d / %d" % (a, b))
        _, out = git("status", "--short", must=False)
        dirty = [l for l in (out or "").splitlines() if l.strip()]
        print("未提交改动 : %d 个文件" % len(dirty))


def main():
    ap = argparse.ArgumentParser(description="skill 仓库发布与更新")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("push", help="发布到 GitHub")
    p.add_argument("--bump", help="顺便升版本号，如 1.6.0")
    p.add_argument("--dry-run", action="store_true", help="只做体检和打包，不提交不推送")
    p.set_defaults(func=cmd_push)

    p = sub.add_parser("pull", help="从 GitHub 拉最新更新")
    p.add_argument("--force", action="store_true", help="丢弃本地未提交改动")
    p.add_argument("--quiet", action="store_true", help="定时任务模式：没更新就安静退出")
    p.set_defaults(func=cmd_pull)

    p = sub.add_parser("link", help="把解压装的目录接入自动更新通道（首次只需跑一次）")
    p.set_defaults(func=cmd_link)

    p = sub.add_parser("check", help="检查远端有没有新版本")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("status", help="看本地/远端状态")
    p.set_defaults(func=cmd_status)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
