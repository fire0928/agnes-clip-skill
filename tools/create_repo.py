#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""create_repo.py —— 在 GitHub 上给本 skill 建仓库（只做一次）。

用法：
    python tools/create_repo.py --token ghp_xxx
    python tools/create_repo.py --token ghp_xxx --name my-skill-repo

token 从 https://github.com/settings/tokens 生成，勾 **repo** 权限即可。
**token 只在命令行传，不要写进任何文件。** 建完仓脚本就把远端配好，
以后更新走 `tools/git_sync.py push`，不再需要 token。

说明：这台机器的代理会把 github.com 主站掐断（502），
但 ssh.github.com:443 是通的 —— 所以推送一律走 SSH，只有「建仓」这一步用 API。
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONF_PATH = os.path.join(ROOT, ".git-sync.json")


def die(msg):
    print("[停] " + msg, file=sys.stderr)
    sys.exit(1)


def api(url, token, method="GET", payload=None):
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=60) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        return e.code, body
    except Exception as e:
        return 0, str(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True, help="GitHub Personal Access Token（repo 权限）")
    ap.add_argument("--name", default=None, help="仓库名，默认取 .git-sync.json 里的")
    ap.add_argument("--private", action="store_true", help="建成私有仓库")
    ap.add_argument("--description", default=None)
    args = ap.parse_args()

    conf = {}
    if os.path.exists(CONF_PATH):
        conf = json.load(open(CONF_PATH, encoding="utf-8"))
    repo_url = conf.get("repo") or ""
    if not repo_url:
        die("先在 .git-sync.json 里配好 repo 地址")
    # 从 ssh://git@ssh.github.com:443/<user>/<repo>.git 解析出 user/repo
    tail = repo_url.split("443/", 1)[-1]
    if tail.endswith(".git"):
        tail = tail[:-4]
    if "/" not in tail:
        die("无法从 repo 地址解析出 owner/repo: " + repo_url)
    owner, repo = tail.split("/", 1)
    if args.name:
        repo = args.name
    full = "%s/%s" % (owner, repo)

    print("准备建仓：%s" % full)

    # 1. 确认 token 有效
    st, d = api("https://api.github.com/user", args.token)
    if st != 200:
        die("token 无效或没权限：%s" % str(d)[:300])
    login = d.get("login")
    print("[ok] token 有效，当前账号 %s" % login)
    if login != owner:
        print("[注意] token 账号是 %s，但配置里写的是 %s" % (login, owner))

    # 2. 仓库是否已存在
    st, d = api("https://api.github.com/repos/%s" % full, args.token)
    if st == 200:
        print("[ok] 仓库已存在：%s" % d.get("html_url"))
    else:
        # 3. 建仓
        payload = {
            "name": repo,
            "description": args.description or conf.get("description") or
            "AI 视频生成流水线 skill（本地 ComfyUI 路线）",
            "private": bool(args.private),
            "auto_init": False,
        }
        st, d = api("https://api.github.com/user/repos", args.token, method="POST", payload=payload)
        if st not in (200, 201):
            die("建仓失败：%s" % str(d)[:500])
        print("[ok] 仓库已建：%s" % d.get("html_url"))

    # 4. 配远端并做第一次推送
    ssh_url = "ssh://git@ssh.github.com:443/%s.git" % full
    conf["repo"] = ssh_url
    conf.setdefault("web", "https://github.com/%s" % full)
    json.dump(conf, open(CONF_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("[ok] .git-sync.json 已更新")

    env = dict(os.environ, GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=yes -o ConnectTimeout=25 -p 443")
    for cmd in (["git", "remote", "set-url", "origin", ssh_url],
                ["git", "add", "-A"],
                ["git", "commit", "-q", "-m", "首次发布"],
                ["git", "push", "-u", "origin", "main"]):
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=env)
        if r.returncode != 0:
            die("git %s 失败:\n%s" % (" ".join(cmd[1:]), (r.stderr or r.stdout)[-500:]))
    print("[ok] 首次推送完成")

    # 5. 打版本标签
    ver = "0.0.0"
    skill_md = os.path.join(ROOT, "SKILL.md")
    if os.path.exists(skill_md):
        import re
        m = re.search(r"^version:\s*(\S+)", open(skill_md, encoding="utf-8").read(), re.M)
        if m:
            ver = m.group(1)
    r = subprocess.run(["git", "tag", "-f", "v" + ver], cwd=ROOT, capture_output=True, env=env)
    subprocess.run(["git", "push", "origin", "v" + ver], cwd=ROOT, capture_output=True, env=env)

    print("\n" + "=" * 50)
    print("  建仓完成")
    print("  仓库   https://github.com/%s" % full)
    print("  版本   v%s" % ver)
    print("\n以后更新只跑：python tools/git_sync.py push")
    print("=" * 50)


if __name__ == "__main__":
    main()
