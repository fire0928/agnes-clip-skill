"""校验已安装的快捷指令是否与 skill 自带的一致，并可一键重装。

用法：
    python tools/sync_commands.py                 # 同步（覆盖更新）
    python tools/sync_commands.py --check         # 只检查不写
    python tools/sync_commands.py --project <目录> # 额外同步到某个项目

快捷指令装在两处：
    用户级  ~/.workbuddy/commands/          所有项目都能用
    项目级  <项目>/.workbuddy/commands/      只在这个项目能用

项目级目录自动发现：从当前工作目录向上找 .workbuddy/commands（最多 6 层）。
"""
import hashlib
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "commands")
USER_DIR = os.path.join(os.path.expanduser("~"), ".workbuddy", "commands")


def md5(p):
    with open(p, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()[:10]


def find_project_dirs():
    """从当前工作目录向上找项目级 commands 目录。"""
    out = []
    cur = os.getcwd()
    for _ in range(6):
        cand = os.path.join(cur, ".workbuddy", "commands")
        if os.path.isdir(cand):
            out.append(cand)
            break
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return out


def main():
    check = "--check" in sys.argv
    if not os.path.isdir(SRC):
        print("这个 skill 没有 commands/ 目录，跳过。")
        return
    files = sorted(f for f in os.listdir(SRC) if f.endswith(".md"))

    targets = [("用户级", USER_DIR)]
    if "--project" in sys.argv:
        i = sys.argv.index("--project")
        proj = sys.argv[i + 1] if i + 1 < len(sys.argv) else None
        if proj:
            targets.append(("项目级", os.path.join(os.path.abspath(proj), ".workbuddy", "commands")))
    for d in find_project_dirs():
        if not any(d == t[1] for t in targets):
            targets.append(("项目级", d))

    stale = []
    for name, dst in targets:
        print("=== %s (%s) ===" % (name, dst))
        for f in files:
            s = os.path.join(SRC, f)
            t = os.path.join(dst, f)
            if not os.path.exists(t):
                print("  [缺失] %s" % f)
                stale.append((dst, f))
            elif md5(s) != md5(t):
                print("  [不同] %s  ← 需更新" % f)
                stale.append((dst, f))
            else:
                print("  [一致] %s" % f)

    if check:
        print("\n共 %d 个需要更新。" % len(stale))
        return
    if not stale:
        print("\n全部已是最新，无需改动。")
        return
    for dst, f in stale:
        os.makedirs(dst, exist_ok=True)
        shutil.copy2(os.path.join(SRC, f), os.path.join(dst, f))
    print("\n已更新 %d 个文件。重启 WorkBuddy 后生效。" % len(stale))


if __name__ == "__main__":
    main()
