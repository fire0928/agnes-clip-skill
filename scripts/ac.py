#!/usr/bin/env python3
"""
ac.py — Agnes Clip Pipeline
用 Agnes 云端算力，把一句话创意全自动做成一条竖屏长视频：
剧本分镜 → 角色定妆图 → 道具图 → 逐镜首帧 → 批量出视频 → 拼接成片。

零第三方依赖：Python 标准库 + ffmpeg（图片裁切、拼接、混音）。
ffmpeg 未装时自动尝试 imageio-ffmpeg 提供的静态二进制。

命令：
  ac.py init <dir> [--title 标题]
  ac.py story <dir> --idea "一句话创意" [--shots 10] [--seconds 8]
  ac.py char-gen <dir> --name hero [--desc "..."] [--tri] [--card-style sheets|turnaround] [--channel agnes|gpt-image|banana] [--force]
  ac.py char-add <dir> <photo.jpg> --name hero
  ac.py views <dir> [--name hero]
  ac.py cast <dir> [list|init|push] [--name girl] [--all]
  ac.py episode-new <第1集目录> --name ep02 --title "第二集"
  ac.py prop-gen <dir> --name sword [--desc "..."] [--force]
  ac.py scene-gen <dir> [--force]
  ac.py frame <dir> [--only S01] [--force] [--dry-run]
  ac.py video <dir> [--only S01] [--wait] [--force] [--allow-paid]
  ac.py fetch <dir>
  ac.py recall <dir> --from <旧集> --shot S03
  ac.py seam <dir>
  ac.py voice <dir> [--force] [--no-fit]
  ac.py music <dir> [--duration 101] [--caption "..."] [--lyrics "..."] [--provider comfyui|volc] [--force]
  ac.py sfx <dir> [--into out/final.mp4]
  ac.py assemble <dir> [--subs] [--voice]
  ac.py auto <dir> --idea "一句话创意" [--shots 10] [--only-first]
  ac.py audit <dir>
  ac.py status <dir>
  ac.py pick-image <dir> [--channel agnes|gpt-image|banana]
  ac.py config-ui
  ac.py music-ui <dir>
  ac.py setup --agnes-key ...
"""
import argparse
import base64
import json
import math
import hashlib
import hmac
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

# 部分中转（apibase.cc 等）用 Cloudflare 拦 python-urllib 默认 UA，会 403 / 读超时。
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# Cloudflare 的 1010 = "浏览器签名不符"。光改 User-Agent 不够，
# 还得把 Accept / Accept-Language / Sec-Ch-Ua 这些头一起带上，才像真浏览器。
# Origin / Referer 会在 _browser_headers() 里按实际目标域名覆盖，这里的值只是兜底。
BROWSER_HEADERS = {
    "User-Agent": BROWSER_UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "identity",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Origin": "https://apihub.agnes-ai.cn",
    "Referer": "https://apihub.agnes-ai.cn/",
}

if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass

# ----------------------------------------------------------------------------- constants

PROJECT_DIRS = [
    "script",
    "assets/characters",
    "assets/props",
    "assets/scenes",
    "frames",
    "clips",
    "audio",
    "out",
]

DEFAULT_AGNES = {
    "endpoint": "https://apihub.agnes-ai.cn/v1",
    "key": "",
    # 可选：视频专用通道（独立 key / 独立入口），只用于 /videos 与轮询；
    # 图片、剧本仍然走上面的 endpoint + key。
    "video_endpoint": "",
    "video_key": "",
    "video_model": "agnes-video-2.5-flash",
    "image_model": "agnes-image-2.5-flash",
    "text_model": "agnes-2.5-flash",
    "image_size": "2K",
    "image_ratio": "9:16",
    "seconds": "8",
    "aspect_ratio": "9:16",
    "jobs": 3,
    "poll_interval": 30.0,
    "timeout": 7200,
    "submit_attempts": 3,
    "submit_rounds": 40,
    # 可选：把首帧上传公网并输出 URL 的 shell 命令，{file} 为本地路径。
    # 留空 = 直接提交 base64 data URI（2.5 flash 实测接受）。
    "frame_upload": "",
}

DEFAULT_MUSIC = {
    # 可选配乐：两条通道，provider 决定走哪条。
    #   comfyui = 本地/远程 ComfyUI + MiniMax Music3（有显卡时用，不花钱）
    #   volc    = 火山引擎 AI 音乐生成（豆包音乐模型，按时长计费，无卡也能跑）
    "provider": "comfyui",
    "endpoint": "",
    "auth": "",
    "unet": "minimax_music3_dit_int8_convrot.safetensors",
    "clip": "minimax_music3_text_encoder_pruned_int8_convrot.safetensors",
    "vae": "minimax_music3_dav.safetensors",
    "steps": 28,
    "cfg": 1.8,
    "duration": 100,
    "caption": "Cinematic instrumental score, warm strings and soft piano, gentle percussion, emotional and healing, 70 BPM",
    # 火山引擎「AI 音乐生成」（豆包音乐模型）OpenAPI
    "volc": {
        "ak": "",
        "sk": "",
        # GenBGMForTime = 按时长后付费；GenBGM = 套餐包。两个入口不互通，默认走后付费。
        "action": "GenBGMForTime",
        "api_version": "2024-08-12",
        "model_version": "v5.0",
        "region": "cn-beijing",
        "service": "imagination",
        "host": "open.volcengineapi.com",
        # 纯音乐单次官方上限 60 秒，超长自动分段生成再交叉淡化拼接
        "chunk_max": 60,
        "poll_interval": 8,
        "timeout": 900,
        "rewrite": False,
    },
}

DEFAULT_VOICES = {
    # 每个角色一种音色；default 兜底，VO 是画外旁白
    "default": "zh-CN-XiaoxiaoNeural",
    "VO": "zh-CN-YunxiNeural",
    "rate": "+0%",
    "volume": 1.6,
    # TTS 通道：edge（免费，只能念稿）/ doubao（豆包 Seed-Audio，有情绪和停顿）
    "provider": "edge",
    # ffmpeg 后处理链（房间感 / 压缩 / 去齿音），可留空
    "postfilter": "",
    # 豆包通道参数（provider=doubao 时才用到）
    "doubao": {
        "endpoint": "https://openspeech.bytedance.com/api/v3/tts/create",
        "key": "",
        "model": "seed-audio-1.0",
        # 用一句自然语言描述角色与情绪，模型自己决定停顿和语气
        "style": "",
        # 一定要写，否则模型可能自己加音效或配乐
        "tail": "只有她的人声，不要背景音效，不要音乐，不要任何其他声音。",
        "speech_rate": 0,
        # 超过这个秒数的空白会被压掉（**别设太小**，轻声气声会被切没）
        "trim_pause": 0.45,
    },
}

DEFAULT_IMAGE = {
    # 出图通道：agnes（默认，稳）/ gpt-image / openai（OpenAI 兼容中转）/ banana（Gemini 原生）
    "provider": "agnes",
    # gpt-image / openai 通道
    "endpoint": "",
    "key": "",
    "model": "gpt-image-2.5",
    # banana 通道（Gemini 原生协议，服装/道具/手部细节最听话）
    "banana": {
        "endpoint": "https://apibase.cc",
        "key": "",
        "model": "nano-banana-pro",
        "image_size": "2K",
    },
}

DEFAULT_TEXT = {
    # workbuddy = 用当前 WorkBuddy 会话模型写剧本（不调用外部 API，不需要 key）
    # api      = 调用外部 OpenAI 兼容文本接口
    "provider": "workbuddy",
    "endpoint": "",
    "key": "",
    "model": "",
}

DEFAULT_VIDEO_CH = {
    # 视频通道（可以独立于图片/文本）：Agnes 免费 / Agnes 付费 / 自定义 OpenAI Videos
    "endpoint": "",
    "key": "",
    "model": "",
    "jobs": 3,
    "poll_interval": 30.0,
    # 多档通道：订阅额度 → 免费额度 → 按量付费，能白嫖就白嫖，排不上才花钱。
    # [{"name":"档位名","endpoint":"...","key":"...","model":"..."}]
    "tiers": [],
    # 分档并行配额：{"0": 3, "2": 3} = 第1档3路 + 第3档3路同时跑
    "tier_slots": {},
    # 换到付费档要不要先问一句（默认要，防止程序偷偷烧钱）
    "paid_requires_confirm": True,
    # 免费档最多试几轮就换下一档
    "free_tier_max_attempts": 1,
}

DEFAULT_CFG = {
    "title": "untitled",
    "ffmpeg": "ffmpeg",
    "text": DEFAULT_TEXT,
    "image": DEFAULT_IMAGE,
    "video": DEFAULT_VIDEO_CH,
    "agnes": DEFAULT_AGNES,
    "music": DEFAULT_MUSIC,
    "voices": DEFAULT_VOICES,
}

# 本 skill 自己的凭据文件，与 ai-video-pipeline 完全隔离
GLOBAL_CFG_PATH = os.path.join(os.path.expanduser("~"), ".workbuddy", "agnes-clip.json")

# aspect_ratio -> 首帧裁切尺寸（与 Agnes 输出一致的比例）
RATIO_SIZE = {
    "9:16": (720, 1280),
    "16:9": (1280, 704),
    "1:1": (720, 720),
    "4:3": (960, 720),
    "3:4": (720, 960),
    "21:9": (1680, 720),
}

# 成片实际像素（字幕坐标系用）
OUT_SIZE = {
    "9:16": (704, 1280),
    "16:9": (1280, 704),
    "1:1": (720, 720),
    "4:3": (960, 720),
    "3:4": (720, 960),
    "21:9": (1680, 720),
}

# 人物外观硬约束：名字里带英文时，模型容易把人做成欧美人，必须每次强调
EAST_ASIAN = (" All characters are East Asian Chinese with East Asian facial features, "
              "black hair, dark eyes and natural East Asian skin tones.")

# 场景风格锚：默认只保留「这是真实中国场景」这一层，不预设具体店铺类型。
# 老版本这里硬编码了「中式老街面馆」，导致非面馆项目（公寓/咖啡店/公交站）都被喂进面馆陈设，
# 是「画面里凭空多出不属于本片的道具」最常见的一个根因。
CN_SHOP_ANCHOR = (
    "Authentic contemporary Chinese setting with real, lived-in Chinese details. "
    "NOT a Japanese izakaya, NOT a sushi bar, NOT a western restaurant, NOT a generic hotel lobby. "
    "No noren curtains, no tatami, no sushi counter, no English-only signage."
)

# 需要特定场景气质时，在 project.json 写 "scene_anchor": "<preset 名>" 或直接写整句英文
SCENE_ANCHOR_PRESETS = {
    "cn_noodle_shop": (
        "A tiny old Chinese street noodle shop (中式老街面馆) in a southern Chinese city at night. "
        "Authentic Chinese details only — NOT a Japanese izakaya, NOT a sushi bar, NOT a café, "
        "NOT a western restaurant. No noren curtains, no tatami, no sushi counter."
    ),
    "cn_apartment": (
        "A small lived-in Chinese urban apartment, ordinary rented flat with simple modern furniture, "
        "warm household clutter, real Chinese domestic details. NOT a showroom, NOT a hotel room, "
        "NOT a western loft."
    ),
    "cn_cafe": (
        "A small independent Chinese neighbourhood coffee shop, wooden tables, warm pendant lights, "
        "plants by the window, handwritten menu board. NOT a Japanese kissaten, NOT a chain store, "
        "NOT a European bistro."
    ),
}


def scene_anchor(cfg, paths=None):
    """场景风格锚：项目 project.json 的 scene_anchor > 全局配置 > 中性中国场景锚。"""
    anchor = cfg.get("scene_anchor") or CN_SHOP_ANCHOR
    root = (paths or {}).get("root") or (paths or {}).get("proj") or "."
    pconf_path = os.path.join(root, "project.json")
    if os.path.exists(pconf_path):
        try:
            pconf = load_json(pconf_path) or {}
        except Exception:
            pconf = {}
        anchor = pconf.get("scene_anchor") or anchor
    # 允许写 preset 名
    anchor = SCENE_ANCHOR_PRESETS.get(anchor.strip(), anchor) if isinstance(anchor, str) else anchor
    return anchor

# 面馆专用兜底陈设：只有地点明确是「面馆」时才自动套用，不再作为全局默认。
# 全局默认必须为空 —— 否则公寓 / 咖啡店 / 公交站的场景板会被塞进面锅和红塑料凳。
NOODLE_SCENE_SET = [
    "white square wall tiles",
    "big stainless-steel noodle boiling pot with rising steam",
    "stainless counter with bowls of chopped scallion and chili oil",
    "red plastic menu board on the wall with unreadable characters",
    "wooden square tables with red plastic stools",
    "glass-fronted drink fridge with soda bottles",
    "warm yellow pendant lamps hanging low",
    "worn terrazzo floor",
]

DEFAULT_SCENE_SET = []


def scene_set_for(place, slug=""):
    """没写 scene.set 时的兜底：地点是面馆才套面馆清单，其它场景一律留空。"""
    hay = "%s %s" % (place or "", slug or "")
    if any(k in hay for k in ("面馆", "面店", "面摊", "noodle")):
        return NOODLE_SCENE_SET
    return DEFAULT_SCENE_SET

# 机位兜底描述
DEFAULT_ANGLES = {
    "wide": "wide establishing view from just inside the entrance, looking down the shop toward the counter",
    "counter": "camera behind the counter looking across it at the dining tables",
    "table": "camera across the window-side table, facing the seat by the window",
    "door": "camera on the street looking through the open doorway into the shop",
}


def deep_merge(base, override):
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, str) and v == "" and out.get(k):
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_global_cfg():
    if os.path.exists(GLOBAL_CFG_PATH):
        try:
            return load_json(GLOBAL_CFG_PATH)
        except Exception as e:
            die("全局配置文件损坏: %s (%s)" % (GLOBAL_CFG_PATH, e))
    return {}


# ----------------------------------------------------------------------------- helpers

def die(msg, code=1):
    print("[ERROR] " + msg, file=sys.stderr)
    sys.exit(code)


def info(msg):
    print("[ac] " + msg, flush=True)


def warn(msg):
    print("[warn] " + msg, flush=True)


def load_json(path, default=None):
    if not os.path.exists(path):
        if default is None:
            die("文件不存在: " + path)
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def project_paths(root):
    # root 绝对化：后续有些步骤会切 cwd 执行 ffmpeg（如 assemble 的 render 用
    # cwd=paths["out"]），相对路径在换了工作目录后就指错文件了。
    root = os.path.abspath(root)
    return {
        "root": root,
        "config": os.path.join(root, "project.json"),
        "shots": os.path.join(root, "script", "shots.json"),
        "story": os.path.join(root, "script", "story.md"),
        "frames": os.path.join(root, "frames"),
        "clips": os.path.join(root, "clips"),
        "audio": os.path.join(root, "audio"),
        "out": os.path.join(root, "out"),
        "chars": os.path.join(root, "assets", "characters"),
        "props": os.path.join(root, "assets", "props"),
        "scenes": os.path.join(root, "assets", "scenes"),
        # 共享角色库：同一系列多集共用一套脸。project.json 里写 cast_dir 才有值。
        "cast": None,
    }


def load_project(root):
    paths = project_paths(root)
    if not os.path.exists(paths["config"]):
        die("不是有效项目目录（缺 project.json）: " + root)
    proj = load_json(paths["config"])
    # cast_dir 支持相对（相对项目根）与绝对路径；只有库目录真实存在才启用，
    # 否则静默回落成「各自项目内一套角色」，不影响老项目。
    cd = (proj.get("cast_dir") or "").strip()
    if cd:
        full = cd if os.path.isabs(cd) else os.path.normpath(os.path.join(root, cd))
        if os.path.isdir(full):
            paths["cast"] = full
    merged = deep_merge(DEFAULT_CFG, load_global_cfg())
    merged = deep_merge(merged, proj)
    if not merged["agnes"].get("key"):
        merged["agnes"]["key"] = os.environ.get("AGNES_API_KEY", "")
    return merged, paths


def char_dir(paths, name):
    """角色资产目录：本集内优先，其次共享角色库。

    读取一律走这里，写入（char-gen / char-add）写本集目录。
    这样第 2 集开头就能直接复用第 1 集锁好的 face_ref，不用重新生成、脸也不会变。
    """
    local = os.path.join(paths["chars"], name)
    if os.path.exists(os.path.join(local, "face_ref.jpg")):
        return local
    lib = paths.get("cast")
    if lib:
        shared = os.path.join(lib, name)
        if os.path.exists(os.path.join(shared, "face_ref.jpg")):
            return shared
    return local


def all_char_names(paths):
    """本集 + 共享库的全部角色名（去重排序）。"""
    names = set()
    for d in (paths.get("chars"), paths.get("cast")):
        if d and os.path.isdir(d):
            for n in os.listdir(d):
                if os.path.isdir(os.path.join(d, n)):
                    names.add(n)
    return sorted(names)


def require_agnes_creds(cfg):
    a = cfg.get("agnes") or {}
    if not a.get("endpoint"):
        die("未配置 Agnes 端点。运行: ac.py setup --agnes-endpoint https://apihub.agnes-ai.cn/v1")
    if not a.get("key"):
        die("未配置 Agnes key。运行: ac.py setup --agnes-key <key>，或设置环境变量 AGNES_API_KEY")


def require_video_agnes_creds(cfg):
    """视频可以走独立 key / 独立入口；没有配置则回落到主 key。"""
    a = cfg.get("agnes") or {}
    if not (a.get("video_endpoint") or a.get("endpoint")):
        die("未配置视频端点。运行: ac.py setup --agnes-video-endpoint <url>")
    if not (a.get("video_key") or a.get("key")):
        die("未配置视频 key。运行: ac.py setup --agnes-video-key <key>")


# ----------------------------------------------------------------------------- ffmpeg

def have_ffmpeg(cfg):
    candidates = [cfg.get("ffmpeg") or "ffmpeg"]
    try:
        import imageio_ffmpeg
        candidates.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass
    for exe in candidates:
        if not exe:
            continue
        try:
            subprocess.run([exe, "-version"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=20)
            return exe
        except Exception:
            continue
    return None


def ff_run(exe, args, check=True, cwd=None):
    cmd = [exe] + args
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)
    if check and p.returncode != 0:
        die("ffmpeg 失败: %s\n%s" % (" ".join(cmd), p.stderr.decode("utf-8", "ignore")[-1500:]))
    return p


def ff_crop_to(w, h, src, dst, exe):
    vf = ("scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,setsar=1" % (w, h, w, h))
    ff_run(exe, ["-y", "-loglevel", "error", "-i", src, "-vf", vf, "-q:v", "2", dst])


def ff_duration(path, exe):
    p = ff_run(exe, ["-i", path], check=False)
    txt = p.stderr.decode("utf-8", "ignore")
    for line in txt.splitlines():
        line = line.strip()
        if line.startswith("Duration:"):
            hms = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = hms.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    return 0.0


def ff_has_audio(path, exe):
    p = ff_run(exe, ["-i", path], check=False)
    return "Audio:" in p.stderr.decode("utf-8", "ignore")


def ff_size(path, exe):
    """返回 (w, h)；取不到返回 None。

    不同模型/不同通道出的竖屏尺寸会不一样：agnes-video-2.5-flash 是 704x1280，
    付费版 agnes-video-2.5 是 720x1280。混着拼的时候 xfade 会因为尺寸不一致直接失败。
    """
    p = ff_run(exe, ["-i", path], check=False)
    txt = p.stderr.decode("utf-8", "ignore")
    for line in txt.splitlines():
        if "Video:" in line:
            m = re.search(r"(\d{2,5})x(\d{2,5})", line)
            if m:
                return int(m.group(1)), int(m.group(2))
    return None


def ff_lufs(path, exe):
    """返回 (integrated_lufs, true_peak_dbtp)；测不到返回 (None, None)。"""
    p = ff_run(exe, ["-hide_banner", "-i", path,
                     "-af", "loudnorm=print_format=json", "-f", "null", "-"],
                check=False)
    txt = p.stderr.decode("utf-8", "ignore")
    m = re.findall(r'"input_i"\s*:\s*"(-?[\d.]+)"', txt)
    t = re.findall(r'"input_tp"\s*:\s*"(-?[\d.]+)"', txt)
    if not m:
        return None, None
    return float(m[-1]), (float(t[-1]) if t else None)


def normalize_loudness(path, exe, target=-16.0, ceiling=-1.5):
    """把成片整体提到 target LUFS（静态增益 + 峰值保护），视频流直接 copy。

    对白片常见坑：TTS 每条都按 -23 LUFS 归过，混完整体只有 -24 左右，
    手机外放听起来闷、小。这里统一抬到 -16（抖音/B站/视频号的常见基准）。
    """
    cur, tp = ff_lufs(path, exe)
    if cur is None:
        warn("测不到响度，跳过响度归一")
        return
    gain = target - cur
    # 不要因为峰值已经很高就把增益压回去——那会得到"又小声又顶着"的结果。
    # 增益照给，峰交给 limiter 兜（对话片偶尔限掉一点峰，听不出来）。
    if gain > 6.0:
        gain = 6.0
    if gain < 0.5:
        info("响度 %.1f LUFS（峰值 %s dBTP），不再调整" % (cur, tp))
        return
    tmp = path + ".norm.mp4"
    af = "volume=%.2fdB" % gain
    if tp is not None and tp + gain > ceiling - 0.3:
        af += ",alimiter=limit=%.3f:level=disabled" % (10 ** (ceiling / 20.0))
    ff_run(exe, ["-y", "-loglevel", "error", "-i", path, "-c:v", "copy",
                 "-af", af, "-c:a", "aac", "-b:a", "192k",
                 "-movflags", "+faststart", tmp])
    os.replace(tmp, path)
    info("响度 %.1f → %.1f LUFS（+%.1f dB，峰值 %s dBTP）"
         % (cur, cur + gain, gain, tp))


def save_image_bytes(raw, dst, exe=None):
    """Agnes 生图返回 PNG；目标名 .jpg 时用 ffmpeg 转码。"""
    is_png = raw[:8] == b"\x89PNG\r\n\x1a\n"
    if is_png and dst.lower().endswith((".jpg", ".jpeg")) and exe:
        tmp = dst + ".png"
        with open(tmp, "wb") as f:
            f.write(raw)
        ff_run(exe, ["-y", "-loglevel", "error", "-i", tmp, "-q:v", "2", dst])
        os.remove(tmp)
        return
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    with open(dst, "wb") as f:
        f.write(raw)


# ----------------------------------------------------------------------------- http

def http_json(url, payload=None, headers=None, method=None, timeout=300):
    data = None
    hdrs = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method or ("POST" if data else "GET"))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def http_bytes(url, timeout=600, headers=None):
    req = urllib.request.Request(url, headers=dict(headers or {}))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def download_file(url, dst, timeout=600):
    raw = http_bytes(url, timeout=timeout)
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    with open(dst, "wb") as f:
        f.write(raw)
    return len(raw)


def file_to_data_uri(path):
    with open(path, "rb") as f:
        raw = f.read()
    mime = "image/png" if raw[:4] == b"\x89PNG" else "image/jpeg"
    return "data:%s;base64,%s" % (mime, base64.b64encode(raw).decode("ascii"))


# ----------------------------------------------------------------------------- agnes core

def agnes_headers(cfg, kind="text"):
    """kind=video 时优先用视频通道 key；图片/剧本永远走主 key。"""
    a = cfg["agnes"]
    key = a.get("key") or ""
    if kind == "video":
        key = (cfg.get("video") or {}).get("key") or a.get("video_key") or key
    return {"Authorization": "Bearer " + key}


def agnes_video_base(cfg):
    a = cfg["agnes"]
    return ((cfg.get("video") or {}).get("endpoint")
            or a.get("video_endpoint") or a.get("endpoint") or "").rstrip("/")


def agnes_host(cfg):
    """轮询接口挂在域名根下（/agnesapi），不在 /v1 下面。"""
    host = agnes_video_base(cfg)
    if host.endswith("/v1"):
        host = host[:-3]
    return host


def video_model(cfg):
    return ((cfg.get("video") or {}).get("model")
            or cfg["agnes"].get("video_model") or "agnes-video-2.5-flash")


def video_jobs(cfg):
    v = cfg.get("video") or {}
    return max(1, int(v.get("jobs") or cfg["agnes"].get("jobs", 3)))


# ---- 视频通道优先级链 ---------------------------------------------------------
# 一个账号可能同时有：订阅额度、国内免费额度、按量付费。开一个片时当然先用不花钱的。
# video.tiers 按顺序排，一档一个 {name, endpoint, key, model}；
# 提交遇到队列满就顺延到下一档，成功后就记住这一档，后面的镜头都走它。
_VIDEO_TIER = {"idx": 0}


def video_tier_list(cfg):
    v = cfg.get("video") or {}
    raw = v.get("tiers") or cfg.get("video_tiers") or []
    out = []
    for t in raw:
        if not str(t.get("key") or "").strip():
            continue
        out.append({
            "name": t.get("name") or t.get("model") or "tier",
            "endpoint": (t.get("endpoint") or "").rstrip("/"),
            "key": str(t.get("key")).strip(),
            "model": t.get("model") or "agnes-video-2.5-flash",
        })
    return out


def _tier_at(cfg, idx):
    tiers = video_tier_list(cfg)
    if tiers and idx is not None and 0 <= int(idx) < len(tiers):
        return tiers[int(idx)]
    return None


def _tier_base(cfg, tier):
    return ((tier or {}).get("endpoint") or agnes_video_base(cfg)).rstrip("/")


def _tier_headers(tier, cfg=None):
    if tier:
        return {"Authorization": "Bearer " + tier["key"]}
    return agnes_headers(cfg, "video")


def _tier_model(cfg, tier):
    return ((tier or {}).get("model") or video_model(cfg))


def video_poll(cfg):
    v = cfg.get("video") or {}
    return max(5.0, float(v.get("poll_interval") or cfg["agnes"].get("poll_interval", 30.0)))


def agnes_text(cfg, messages, temperature=0.7, timeout=300, max_tokens=8000):
    a = cfg["agnes"]
    payload = {
        "model": a.get("text_model", "agnes-2.5-flash"),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    d = http_json(a["endpoint"].rstrip("/") + "/chat/completions", payload,
                  headers=agnes_headers(cfg), timeout=timeout)
    try:
        return d["choices"][0]["message"]["content"]
    except Exception:
        die("Agnes 文本返回格式异常: " + json.dumps(d, ensure_ascii=False)[:500])


# 支持的出图通道。角色卡的 face_ref 与 char_card 必须同通道，否则会串脸。
IMAGE_CHANNELS = {"agnes", "gpt-image", "openai", "banana", "nano-banana", "gemini"}


def image_channel(cfg, paths=None):
    """本项目实际用哪条出图通道。

    优先级：项目 project.json 的 image_channel > 全局 image.provider > agnes。
    项目级选择让同一个 skill 能同时跑不同通道的项目，不用反复改全局配置。
    """
    ch = ((cfg.get("image") or {}).get("provider") or "agnes").strip() or "agnes"
    if ch not in IMAGE_CHANNELS:
        ch = "agnes"
    if paths:
        try:
            pj = load_json(os.path.join(paths.get("root", ""), "project.json"), {})
            proj = (pj.get("image_channel") or "").strip()
            if proj:
                ch = proj
        except Exception:
            pass
    return ch


def _browser_headers(endpoint=""):
    """按目标域名拼一套完整浏览器头，绕过 Cloudflare 的 1010 签名校验。"""
    h = dict(BROWSER_HEADERS)
    try:
        p = urllib.parse.urlparse(endpoint)
        if p.scheme and p.netloc:
            origin = "%s://%s" % (p.scheme, p.netloc)
            h["Origin"] = origin
            h["Referer"] = origin + "/"
    except Exception:
        pass
    return h


def gpt_image_generate(cfg, prompt, ref_paths=None, size=None, ratio=None,
                       project_paths=None, fallback=True):
    """GPT Image 通道（OpenAI 兼容 /images/generations）。

    与 Agnes 的差异：
    - 参考图走 OpenAI 的 input 数组，元素是 {image_url: data-uri} 或 {type:input_image,...}；
    - 尺寸用像素值（1024x1536 等），不是 2K/9:16；
    - 返回走 b64_json（部分中转会返回 url）。

    稳定性：中转站排队时单次请求可能挂 4 分钟以上，所以单次超时给到 480s，
    重试 3 次。fallback=True 时，整条通道彻底失败会自动改走 Agnes 出图，
    保证出图链路不会因为第三方中转不稳定而中断。
    """
    img = cfg.get("image") or {}
    a = cfg["agnes"]
    endpoint = (img.get("endpoint") or a.get("endpoint") or "").rstrip("/")
    key = img.get("key") or a.get("key") or ""
    model = img.get("model") or "gpt-image-1"

    # 尺寸换算：2K / 9:16 这类值要转成 gpt-image 认识的像素值
    def px_size():
        raw = (size or img.get("size") or "2K").strip()
        rt = (ratio or img.get("ratio") or "9:16").strip()
        if "x" in raw.lower():
            return raw
        if rt in ("9:16", "3:4"):
            return "1024x1536"
        if rt in ("16:9", "4:3"):
            return "1536x1024"
        return "1024x1024"

    payload = {
        "model": model,
        "prompt": prompt,
        "size": px_size(),
        "n": 1,
    }
    refs = [p for p in (ref_paths or []) if p]
    if refs:
        payload["input"] = [{"type": "input_image", "image_url": file_to_data_uri(p)} for p in refs]

    url = endpoint + "/images/generations"
    # 部分中转（apibase.cc 等）会用 Cloudflare 拦 python-urllib 的默认 UA，
    # 报 403 error code 1010（浏览器签名不符）。带上完整浏览器头才能出图。
    headers = {"Authorization": "Bearer " + key}
    headers.update(_browser_headers(endpoint))
    last = ""
    for attempt in range(3):
        try:
            # 中转排队可能很久，超时给足 480s，别在 240s 就放弃一次排队机会
            d = http_json(url, payload, headers=headers, timeout=480)
            item = (d.get("data") or [{}])[0]
            if item.get("b64_json"):
                return base64.b64decode(item["b64_json"]), {"provider": "gpt-image", "model": model}
            if item.get("url"):
                # 返回的是图床 URL，下载时同样要带浏览器头，否则图床侧也会 1010
                return http_bytes(item["url"], timeout=240,
                                  headers=_browser_headers(item["url"])), \
                    {"provider": "gpt-image", "model": model}
            last = json.dumps(d, ensure_ascii=False)[:400]
            break
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")
            last = "HTTP %s: %s" % (e.code, body[:400])
            if e.code in (400, 401, 403, 404):
                break
            time.sleep(min(20, 4 * (attempt + 1)))
        except Exception as e:
            last = str(e)
            time.sleep(min(20, 4 * (attempt + 1)))

    # 中转站挂了不要连累整条链路：自动回退到 Agnes 出图
    if fallback:
        print("[ac] GPT Image 通道失败（%s），自动回退 Agnes 出图" % last[:120], flush=True)
        return agnes_image_generate(
            cfg, prompt, ref_paths=ref_paths, size=size, ratio=ratio,
            project_paths=project_paths, force_channel="agnes")
    die("GPT Image 生图失败: " + last)


def banana_image_generate(cfg, prompt, ref_paths=None, size=None, ratio=None,
                          project_paths=None, fallback=True):
    """Nano Banana 通道（Gemini 原生 generateContent，apibase.cc 网关）。

    和另外两条通道的差别：
    - 协议是 Gemini 原生，不是 OpenAI 的 /images/generations，也不是 /chat/completions；
    - 参考图走 parts[].inlineData（base64 + mimeType），顺序就是"主人脸、场景板"；
    - 尺寸是 imageSize(1K/2K/4K) + aspectRatio，不是像素值。
    """
    b = cfg.get("banana") or {}
    endpoint = (b.get("endpoint") or "https://apibase.cc").rstrip("/")
    key = b.get("key") or ""
    model = b.get("model") or "nano-banana-pro"
    image_size = (size or b.get("image_size") or "2K").strip()
    if "x" in image_size.lower():          # 误填像素值时换算回 1K/2K
        image_size = "2K" if image_size.lower().startswith("1536") else "1K"
    rt = (ratio or b.get("ratio") or "9:16").strip()
    if not key:
        if fallback:
            warn("banana 通道没有 key，回退 Agnes 出图")
            return agnes_image_generate(cfg, prompt, ref_paths=ref_paths, size=size,
                                        ratio=ratio, project_paths=project_paths,
                                        force_channel="agnes")
        die("banana 通道缺少 key（~/.workbuddy/agnes-clip.json 的 banana.key）")

    parts = [{"text": prompt}]
    for p in (ref_paths or []):
        if not p:
            continue
        ext = os.path.splitext(p)[1].lower()
        mime = {".png": "image/png", ".webp": "image/webp"}.get(ext, "image/jpeg")
        with open(p, "rb") as f:
            parts.append({"inlineData": {"mimeType": mime,
                                         "data": base64.b64encode(f.read()).decode("ascii")}})
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"imageSize": image_size, "aspectRatio": rt},
        },
    }
    url = endpoint + "/v1beta/models/%s:generateContent" % model
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    headers.update(_browser_headers(endpoint))
    last = ""
    for attempt in range(3):
        try:
            d = http_json(url, payload, headers=headers, timeout=240)
            cands = d.get("candidates") or []
            for c in cands:
                for part in ((c.get("content") or {}).get("parts") or []):
                    inline = part.get("inlineData") or part.get("inline_data") or {}
                    if inline.get("data"):
                        return base64.b64decode(inline["data"]), \
                            {"provider": "banana", "model": model}
            last = json.dumps(d, ensure_ascii=False)[:400]
            break
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")
            last = "HTTP %s: %s" % (e.code, body[:400])
            if e.code in (400, 401, 403, 404):
                break
            time.sleep(min(20, 4 * (attempt + 1)))
        except Exception as e:
            last = str(e)
            time.sleep(min(20, 4 * (attempt + 1)))
    if fallback:
        print("[ac] banana 通道失败（%s），自动回退 Agnes 出图" % last[:160], flush=True)
        return agnes_image_generate(cfg, prompt, ref_paths=ref_paths, size=size,
                                    ratio=ratio, project_paths=project_paths,
                                    force_channel="agnes")
    die("banana 生图失败: " + last)


def agnes_image_generate(cfg, prompt, ref_paths=None, size=None, ratio=None,
                         project_paths=None, force_channel=None):
    """统一生图入口：按项目/全局配置走 banana / gpt-image / agnes 三条通道之一。"""
    ch = force_channel or image_channel(cfg, project_paths)
    if ch in ("banana", "nano-banana", "gemini"):
        return banana_image_generate(cfg, prompt, ref_paths=ref_paths, size=size,
                                     ratio=ratio, project_paths=project_paths)
    if ch in ("gpt-image", "openai"):
        return gpt_image_generate(cfg, prompt, ref_paths=ref_paths, size=size, ratio=ratio,
                                  project_paths=project_paths)
    a = cfg["agnes"]
    payload = {
        "model": a.get("image_model", "agnes-image-2.5-flash"),
        "prompt": prompt,
        "size": size or a.get("image_size", "2K"),
        "ratio": ratio or a.get("image_ratio", "9:16"),
    }
    refs = [p for p in (ref_paths or []) if p]
    if refs:
        payload["extra_body"] = {
            "image": [file_to_data_uri(p) for p in refs],
            "response_format": "b64_json",
        }
    else:
        payload["return_base64"] = True

    url = a["endpoint"].rstrip("/") + "/images/generations"
    last = ""
    # 生图实测 20-60s 出图；给 360s 一旦连接挂起就要干等 6 分钟才重试，改成 120s 快速失败快速重试。
    for attempt in range(5):
        try:
            d = http_json(url, payload, headers=agnes_headers(cfg, "image"), timeout=120)
            item = (d.get("data") or [{}])[0]
            if item.get("b64_json"):
                return base64.b64decode(item["b64_json"]), {"provider": "agnes"}
            if item.get("url"):
                return http_bytes(item["url"], timeout=120), {"provider": "agnes", "url": item["url"]}
            last = json.dumps(d, ensure_ascii=False)[:400]
            break
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")
            last = "HTTP %s: %s" % (e.code, body[:400])
            if e.code in (400, 401, 403, 404):
                break
            time.sleep(min(30, 3 * (attempt + 1)))
        except Exception as e:
            last = str(e)
            time.sleep(min(30, 3 * (attempt + 1)))
    die("Agnes 生图失败: " + last)


def frame_source(cfg, frame_path):
    """本地首帧 → 视频接口可用形式。默认 base64 data URI；配置了 frame_upload 则上传取 URL。

    ⚠️ frame_upload 是配置里的 shell 命令模板，**用 shlex 拆成参数列表执行**，
    不走 shell=True —— 避免配置被篡改后变成任意命令执行。
    """
    a = cfg["agnes"]
    up = (a.get("frame_upload") or "").strip()
    if up:
        import shlex
        try:
            parts = shlex.split(up, posix=(os.name != "nt"))
        except ValueError as e:
            die("frame_upload 命令无法解析: %s (%s)" % (up, e))
        if not parts:
            die("frame_upload 是空的")
        parts = [p.replace("{file}", frame_path) for p in parts]
        p = subprocess.run(parts, shell=False, capture_output=True, text=True)
        out = (p.stdout or "").strip()
        url = out.splitlines()[-1].strip() if out else ""
        if not url.startswith("http"):
            die("frame_upload 没有输出公网 URL。命令: %s\nstdout: %s\nstderr: %s"
                % (" ".join(parts), out[:300], (p.stderr or "")[:300]))
        return url
    return file_to_data_uri(frame_path)


class SubmitError(Exception):
    """视频任务提交失败（队列满等），可重试。"""
    pass


class PaidTierNeedsConfirm(Exception):
    """免费通道都排不上，需要用付费档，但当前策略要求人工确认。

    不自动降级到付费档，是为了不烧钱。调用方捕获它之后，
    要么让用户确认（把 video.paid_requires_confirm 改 false，或本次加 --allow-paid），
    要么把这一镜留到后面再跑。
    """
    pass


def _video_payload(cfg, model, prompt, seconds, aspect_ratio,
                   first_frame, last_frame, images, audios, seed):
    payload = {"model": model, "prompt": prompt, "size": "720P", "n": 1}
    if first_frame or last_frame:
        payload["mode"] = "keyframe"
        if first_frame:
            payload["first_frame"] = first_frame
        if last_frame:
            payload["last_frame"] = last_frame
    elif images or audios:
        payload["mode"] = "reference"
        if images:
            payload["images"] = list(images)[:5]
        if audios:
            payload["audios"] = list(audios)[:3]
    else:
        payload["mode"] = "text"
    payload["seconds"] = str(seconds)
    payload["aspect_ratio"] = aspect_ratio
    if seed is not None:
        payload["seed"] = int(seed)
    return payload


def _submit_on_tier(cfg, tier, prompt, seconds, aspect_ratio,
                    first_frame=None, last_frame=None, images=None,
                    audios=None, seed=None, quick=False, max_attempts=None):
    """在指定档位上提交一次。quick=True 时少试几轮（用于试探下一档）。
    max_attempts 显式指定时覆盖配置里的 submit_attempts（免费档省着用）。"""
    a = cfg["agnes"]
    payload = _video_payload(cfg, _tier_model(cfg, tier), prompt, seconds, aspect_ratio,
                             first_frame, last_frame, images, audios, seed)
    url = _tier_base(cfg, tier) + "/videos"
    if max_attempts is not None:
        attempts = max(1, int(max_attempts))
    else:
        attempts = 2 if quick else int(a.get("submit_attempts", 8))
    last = ""
    for i in range(attempts):
        try:
            d = http_json(url, payload, headers=_tier_headers(tier, cfg), timeout=90)
            if d.get("video_id") or d.get("id"):
                return d
            last = json.dumps(d, ensure_ascii=False)[:500]
            break
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")
            last = "HTTP %s: %s" % (e.code, body[:400])
            # 403/404 基本是这档不通（没额度/没这个模型），别死磕，直接换下一档
            if e.code in (400, 401, 403, 404):
                break
            # 队列满（503）也不值得在免费档上死磕
            if e.code == 503 and max_attempts is not None:
                break
            # 429 = 速率限制（不是队列满）。退避要长得多，否则继续撞墙。
            if e.code == 429:
                # 只试一次（分档配额模式）时别 sleep —— 立刻返回让调度器换档
                if attempts <= 1:
                    break
                wait = min(180, 30 * (2 ** i))
                info("  速率限制（HTTP 429），%ds 后重试（%d/%d）" % (wait, i + 1, attempts))
                time.sleep(wait)
                continue
            wait = min(60, 2 * (2 ** i))
            if attempts <= 1:
                break
            info("  排队中（HTTP %s），%ds 后重试（%d/%d）" % (e.code, wait, i + 1, attempts))
            time.sleep(wait)
        except Exception as e:
            last = str(e)
            wait = min(60, 2 * (2 ** i))
            info("  提交异常（%s），%ds 后重试" % (str(e)[:120], wait))
            time.sleep(wait)
    raise SubmitError(last)


def agnes_video_submit(cfg, prompt, seconds, aspect_ratio, first_frame=None,
                       last_frame=None, images=None, audios=None, seed=None,
                       force_tier=None, force_max_attempts=None):
    """按 video.tiers 的优先级提交：订阅额度 → 免费额度 → 付费。成功一档就记住它。

    省钱的两个开关（写在全局配置 video 下）：
      free_tier_max_attempts : 免费档单次提交最多试几轮（默认 1）。
                               队列满就立刻换下一档，不在免费档上死磕。
      paid_requires_confirm  : True 时付费档不会自动降级命中，
                               而是抛 PaidTierNeedsConfirm，由人工放行后才用。

    force_tier : 指定只用这一档提交（不降级）。调度器用它实现
                 「免费档 N 路 + 付费档 M 路」的分档并行配额。
    force_max_attempts : 配合 force_tier 用，限制内部重试次数。
                 分档配额模式下应传 1 —— 让这一档快速失败，
                 调度器好立刻换下一档，而不是在限流退避里把线程堵死。
    """
    tiers = video_tier_list(cfg)
    if not tiers:
        d = _submit_on_tier(cfg, None, prompt, seconds, aspect_ratio,
                            first_frame, last_frame, images, audios, seed)
        d["_tier"] = None
        return d

    vcfg = cfg.get("video") or {}
    free_max = max(1, int(vcfg.get("free_tier_max_attempts") or 1))
    paid_confirm = bool(vcfg.get("paid_requires_confirm"))
    # 付费档 = 非 flash 的那些（按量计价的模型）
    def is_paid(t):
        return not str(t.get("model") or "").endswith("-flash")

    # ---- 分档配额：只打指定那一档，不降级 ----
    if force_tier is not None:
        idx = max(0, min(int(force_tier), len(tiers) - 1))
        tier = tiers[idx]
        d = _submit_on_tier(cfg, tier, prompt, seconds, aspect_ratio,
                            first_frame, last_frame, images, audios, seed,
                            max_attempts=force_max_attempts)
        d["_tier"] = idx
        return d

    start = min(_VIDEO_TIER.get("idx", 0), len(tiers) - 1)
    errors = []
    for idx in range(start, len(tiers)):
        tier = tiers[idx]
        paid = is_paid(tier)
        if paid and paid_confirm:
            # 不自动烧钱：把免费档的失败原因留档，等人工确认
            raise PaidTierNeedsConfirm(
                "免费视频通道都排不上，需要用付费档「%s（%s）」才能继续。\n"
                "  已尝试：%s\n"
                "  确认要用付费档的话，把全局配置 ~/.workbuddy/agnes-clip.json 里\n"
                "  video.paid_requires_confirm 改成 false，或用 --allow-paid 提交本次任务。"
                % (tier["name"], tier["model"],
                   ("; ".join(errors) if errors else "无")))

        # 免费档：少试几轮，队列满就换下一档
        attempts = None
        if not paid:
            attempts = free_max
        try:
            d = _submit_on_tier(cfg, tier, prompt, seconds, aspect_ratio,
                                first_frame, last_frame, images, audios, seed,
                                max_attempts=attempts)
            if idx != _VIDEO_TIER.get("idx"):
                info("  视频通道切到第 %d 档：%s（%s）"
                     % (idx + 1, tier["name"], tier["model"]))
                _VIDEO_TIER["idx"] = idx
            d["_tier"] = idx
            return d
        except SubmitError as e:
            errors.append("%s: %s" % (tier["name"], str(e)[:120]))
            if idx + 1 < len(tiers):
                info("  第 %d 档 %s 排不上（%s），换下一档"
                     % (idx + 1, tier["name"], str(e)[:80]))
                # 降档后，之后都从这一档开始试
                _VIDEO_TIER["idx"] = idx + 1
    raise SubmitError("所有视频通道都失败：\n  " + "\n  ".join(errors))


def agnes_video_status(cfg, video_id, tier_idx=None):
    tier = _tier_at(cfg, tier_idx)
    base = _tier_base(cfg, tier)
    host = base[:-3] if base.endswith("/v1") else base
    headers = _tier_headers(tier, cfg)
    q = urllib.parse.urlencode({"video_id": video_id, "model_name": _tier_model(cfg, tier)})
    try:
        return http_json(host + "/agnesapi?" + q, headers=headers, timeout=60)
    except urllib.error.HTTPError as e:
        if e.code not in (404, 405):
            raise
    # 兜底：部分入口只有 OpenAI Videos 兼容的 /v1/videos/{id}
    return http_json(base + "/videos/" + video_id, headers=headers, timeout=60)


# ----------------------------------------------------------------------------- music (optional, comfy)

def comfy_auth_headers(mus_cfg):
    """ComfyUI 的 Basic Auth 头。music.auth 形如 "user:pass"，为空则不带头。"""
    raw = (mus_cfg.get("auth") or "").strip()
    if not raw:
        return {}
    import base64 as _b64
    return {"Authorization": "Basic " + _b64.b64encode(raw.encode("utf-8")).decode()}


def comfy_submit(mus_cfg, workflow, client_id="agnes-clip"):
    endpoint = mus_cfg["endpoint"].rstrip("/")
    d = http_json(endpoint + "/prompt", {"prompt": workflow, "client_id": client_id},
                  headers=comfy_auth_headers(mus_cfg), timeout=120)
    if "prompt_id" not in d:
        die("ComfyUI 提交失败: " + json.dumps(d, ensure_ascii=False)[:600])
    return d["prompt_id"]


def comfy_wait(mus_cfg, prompt_id, timeout=1800):
    endpoint = mus_cfg["endpoint"].rstrip("/")
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(15)
        try:
            h = http_json(endpoint + "/history/" + prompt_id,
                          headers=comfy_auth_headers(mus_cfg), timeout=60)
        except Exception:
            continue
        if prompt_id not in h:
            info("  配乐生成中 %ds" % int(time.time() - t0))
            continue
        st = h[prompt_id].get("status", {})
        if st.get("status_str") == "error":
            die("配乐生成失败")
        outs = []
        for _nid, o in h[prompt_id].get("outputs", {}).items():
            for key in ("audio", "gifs", "videos"):
                outs.extend(o.get(key, []))
        return outs
    die("配乐等待超时")


def build_music_workflow(mus_cfg, caption, duration, seed, lyrics=None):
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": mus_cfg["unet"], "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": mus_cfg["clip"], "type": "minimax", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": mus_cfg["vae"]}},
        "4": {"class_type": "MiniMaxMusic3TextEncode", "inputs": {
            "clip": ["2", 0], "caption": caption,
            "lyrics": lyrics if lyrics else "[Instrumental]",
            "seed": seed, "max_duration": float(duration),
            "cfg_scale": mus_cfg.get("cfg", 1.8), "top_k": mus_cfg.get("top_k", 50)}},
        "5": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["4", 0]}},
        "6": {"class_type": "EmptyMiniMaxMusic3LatentAudio", "inputs": {"seconds": float(duration), "batch_size": 1}},
        "7": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "seed": seed, "steps": mus_cfg.get("steps", 28), "cfg": mus_cfg.get("cfg", 1.8),
            "sampler_name": "euler", "scheduler": "simple",
            "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["6", 0], "denoise": 1.0}},
        "8": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
        "9": {"class_type": "SaveAudioMP3", "inputs": {"audio": ["8", 0], "filename_prefix": "ac_bgm_%d" % seed, "quality": "V0"}},
    }


def do_music_comfy(cfg, paths, duration=None, caption=None, seed=None, lyrics=None, force=False):
    m = cfg.get("music") or {}
    if not m.get("endpoint"):
        die("未配置配乐 ComfyUI 端点（music.endpoint）。不需要配乐可跳过，assemble 会输出无配乐版")
    duration = duration or m.get("duration", 100)
    caption = caption or m.get("caption")
    seed = seed or int(time.time()) % 100000
    lyrics = lyrics if lyrics is not None else m.get("lyrics")
    dst = os.path.join(paths["audio"], "bgm.mp3")
    # 幂等：同一 seed 的配乐已存在就跳过，除非 --force
    if os.path.exists(dst) and not force:
        meta_p = os.path.join(paths["audio"], "bgm.meta.json")
        if os.path.exists(meta_p):
            try:
                meta = json.load(open(meta_p, encoding="utf-8"))
                if meta.get("seed") == seed and meta.get("duration") == float(duration):
                    info("配乐已存在（seed=%s），跳过。--force 可重生成" % seed)
                    return
            except Exception:
                pass
    info("生成配乐 %.1f 秒 ..." % duration)
    pid = comfy_submit(m, build_music_workflow(m, caption, duration, seed, lyrics))
    outs = comfy_wait(m, pid)
    if not outs:
        die("配乐没有输出")
    item = outs[0]
    q = urllib.parse.urlencode({"filename": item.get("filename"),
                                "subfolder": item.get("subfolder", ""),
                                "type": item.get("type", "output")})
    raw = http_bytes(m["endpoint"].rstrip("/") + "/view?" + q,
                     headers=comfy_auth_headers(m))
    with open(dst, "wb") as f:
        f.write(raw)
    try:
        json.dump({"seed": seed, "duration": float(duration), "caption": caption,
                   "lyrics": lyrics or "[Instrumental]", "provider": "comfyui"},
                  open(os.path.join(paths["audio"], "bgm.meta.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    except Exception:
        pass
    info("配乐 -> audio/bgm.mp3 (%.1f MB)" % (len(raw) / 1e6))


# ----------------------------------------------------------------------------- music · 火山引擎
# 火山引擎「AI 音乐生成」（豆包音乐模型）OpenAPI。
# 签名为火山自有 V4：中间密钥是【二进制】，不是十六进制（官方文档示例可直接反推验证）。
# 两个入口不互通：GenBGMForTime = 按时长后付费，GenBGM = 套餐包。走错报 200028。

VOLC_ERR_HINT = {
    "200028": "没有可用资源包 / 未开通「按时长计费」。去 AI 音乐生成控制台把后付费开关打开，"
              "或确认调的是 GenBGMForTime 而不是套餐包的 GenBGM",
    "50000001": "版权相似度校验没通过。把 Text 写具体（乐器/情绪/场景/节奏），或开 music.volc.rewrite",
    "InvalidAccessKey": "AccessKey 不存在，核对 AK",
    "SignatureDoesNotMatch": "签名不匹配，通常是 SK 填错或本机时间偏差超过 5 分钟",
}


def _volc_cfg(cfg):
    m = cfg.get("music") or {}
    vc = dict(DEFAULT_MUSIC["volc"])
    vc.update({k: v for k, v in (m.get("volc") or {}).items() if v not in (None, "")})
    return vc


def _volc_sign(vc, payload, action, api_version):
    """返回 (要发的 headers, query string)。Host 只参与签名，不放发送头里由 urllib 自己补。"""
    ak = (vc.get("ak") or "").strip()
    sk = (vc.get("sk") or "").strip()
    if not ak or not sk:
        die("火山配乐缺 AK/SK。跑 `ac.py setup` 或配置界面「配乐」TAB 填 AccessKey / SecretKey")
    region = vc.get("region") or "cn-beijing"
    service = vc.get("service") or "imagination"
    host = vc.get("host") or "open.volcengineapi.com"
    t = time.gmtime()
    xdate = time.strftime("%Y%m%dT%H%M%SZ", t)
    short = xdate[:8]
    query = "Action=%s&Version=%s" % (urllib.parse.quote(action, safe=""),
                                      urllib.parse.quote(api_version, safe=""))
    payload_hash = hashlib.sha256(payload).hexdigest()
    signed_headers = "content-type;host;x-content-sha256;x-date"
    canonical = "\n".join([
        "POST", "/", query,
        "content-type:application/json",
        "host:" + host,
        "x-content-sha256:" + payload_hash,
        "x-date:" + xdate,
        "", signed_headers, payload_hash,
    ])
    scope = "%s/%s/%s/request" % (short, region, service)
    sts = "\n".join(["HMAC-SHA256", xdate, scope,
                     hashlib.sha256(canonical.encode("utf-8")).hexdigest()])

    def _h(key, msg):
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    k = _h(sk.encode("utf-8"), short)
    k = _h(k, region)
    k = _h(k, service)
    k = _h(k, "request")
    sig = hmac.new(k, sts.encode("utf-8"), hashlib.sha256).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-Date": xdate,
        "X-Content-Sha256": payload_hash,
        "Authorization": "HMAC-SHA256 Credential=%s/%s, SignedHeaders=%s, Signature=%s"
                         % (ak, scope, signed_headers, sig),
    }
    return headers, query


def volc_request(vc, action, body, timeout=90):
    host = vc.get("host") or "open.volcengineapi.com"
    api_version = vc.get("api_version") or "2024-08-12"
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers, query = _volc_sign(vc, payload, action, api_version)
    url = "https://%s/?%s" % (host, query)
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "ignore")
        try:
            return json.loads(raw)
        except Exception:
            die("火山接口 HTTP %s: %s" % (e.code, raw[:400]))
    except Exception as e:
        die("火山接口连不上（%s）：%s" % (host, e))


def _volc_error(d):
    err = ((d or {}).get("ResponseMetadata") or {}).get("Error") or {}
    code = str(err.get("Code") or "").strip()
    if not code:
        return None
    msg = err.get("Message") or ""
    hint = VOLC_ERR_HINT.get(code)
    for k, v in VOLC_ERR_HINT.items():
        if k.lower() in code.lower():
            hint = v
            break
    return "%s %s%s" % (code, msg, ("\n  → " + hint) if hint else "")


def _volc_prompt(caption, idx, total):
    """分段时给模型一点接续提示，否则每段都像重新开头。"""
    base = (caption or "").strip()
    if total <= 1:
        return base
    if idx == 1:
        tail = "这是同一首曲子的第 1 段（共 %d 段），安静铺陈，结尾不要收死，留给下一段接上" % total
    elif idx == total:
        tail = "这是同一首曲子的最后一段（第 %d/%d 段），承接上一段的乐器与调性，情绪收拢，自然收尾" % (idx, total)
    else:
        tail = ("这是同一首曲子的第 %d/%d 段，保持和上一段相同的乐器编制、调性与速度，"
                "小幅递进，不要出现明显的重新起段" % (idx, total))
    return (base + "。" if base else "") + tail + "。纯器乐，无人声。"


def volc_music_chunk(vc, text, seconds):
    body = {"Text": text, "Duration": int(round(seconds)),
            "Version": vc.get("model_version") or "v5.0"}
    if vc.get("rewrite"):
        body["EnableInputRewrite"] = True
    action = vc.get("action") or "GenBGMForTime"
    d = volc_request(vc, action, body)
    e = _volc_error(d)
    if e:
        die("火山配乐提交失败：\n  " + e)
    res = d.get("Result") or {}
    tid = res.get("TaskID") or res.get("TaskId") or (d.get("TaskID") or "")
    if not tid:
        die("火山配乐没返回 TaskID：" + json.dumps(d, ensure_ascii=False)[:400])
    info("  任务 %s 已提交（%d 秒），轮询中 ..." % (str(tid)[:18], int(round(seconds))))
    t0 = time.time()
    interval = float(vc.get("poll_interval") or 8)
    limit = float(vc.get("timeout") or 900)
    while time.time() - t0 < limit:
        time.sleep(interval)
        q = volc_request(vc, "QuerySong", {"TaskID": tid})
        qe = _volc_error(q)
        if qe:
            die("火山配乐查询失败：\n  " + qe)
        r = q.get("Result") or {}
        st = r.get("Status")
        if st == 2:
            detail = r.get("SongDetail") or {}
            url = detail.get("AudioUrl") or ""
            if not url:
                die("火山配乐成功但没给 AudioUrl")
            return url, detail.get("Duration")
        if st == 3:
            fr = r.get("FailureReason") or {}
            msg = "%s %s" % (fr.get("Code"), fr.get("Msg") or "")
            hint = VOLC_ERR_HINT.get(str(fr.get("Code")), "")
            die("火山配乐生成失败：%s%s" % (msg, ("\n  → " + hint) if hint else ""))
        info("  生成中 %ds（状态 %s）" % (int(time.time() - t0), st))
    die("火山配乐等待超时（%ds）" % int(limit))


def _audio_to_wav(cfg, src, dst):
    exe = have_ffmpeg(cfg)
    if not exe:
        die("拼接配乐需要 ffmpeg，但没找到")
    ff_run(exe, ["-y", "-loglevel", "error", "-i", src, "-vn",
                 "-ar", "44100", "-ac", "2", dst])
    return dst


def _stitch_bgm(cfg, parts, out_mp3, target, fade=2.0):
    """多段交叉淡化拼成一条，再做响度归一化 —— 归一化必须在拼接之后。"""
    exe = have_ffmpeg(cfg)
    if not exe:
        die("拼接配乐需要 ffmpeg，但没找到")
    os.makedirs(os.path.dirname(os.path.abspath(out_mp3)), exist_ok=True)
    tmp = out_mp3 + ".stitch.wav"
    if len(parts) == 1:
        ff_run(exe, ["-y", "-loglevel", "error", "-i", parts[0], "-t", "%.2f" % target,
                     "-ar", "44100", "-ac", "2", tmp])
    else:
        args = []
        for p in parts:
            args += ["-i", p]
        chain = []
        prev = "[0:a]"
        for i in range(1, len(parts)):
            lab = "[x%d]" % i
            chain.append("%s[%d:a]acrossfade=d=%.2f:c1=tri:c2=tri%s" % (prev, i, fade, lab))
            prev = lab
        args += ["-filter_complex", ";".join(chain), "-map", prev,
                 "-t", "%.2f" % target, "-ar", "44100", "-ac", "2", tmp]
        ff_run(exe, ["-y", "-loglevel", "error"] + args)
    ff_run(exe, ["-y", "-loglevel", "error", "-i", tmp,
                 "-af", "loudnorm=I=-23:TP=-2:LRA=7",
                 "-c:a", "libmp3lame", "-b:a", "192k", out_mp3])
    try:
        os.remove(tmp)
    except Exception:
        pass
    return out_mp3


def do_music_volc(cfg, paths, duration=None, caption=None):
    vc = _volc_cfg(cfg)
    m = cfg.get("music") or {}
    duration = float(duration or m.get("duration", 100))
    caption = caption or m.get("caption")
    chunk_max = float(vc.get("chunk_max") or 60)
    fade = 2.0
    # 纯音乐单次官方上限 60 秒；超长就切成 n 段，每段留出交叉淡化的重叠
    n, each = 1, duration
    for cand in range(1, 13):
        per = (duration + fade * (cand - 1)) / cand
        if per <= chunk_max + 1e-6:
            n, each = cand, per
            break
    else:
        die("配乐时长 %.0f 秒太长，分段也算不下（上限 %d 段）" % (duration, 12))
    info("火山引擎配乐：%.0f 秒，分 %d 段（每段 %.0f 秒，交叉淡化 %.0f 秒）"
         % (duration, n, each, fade))
    tmpdir = os.path.join(paths["audio"], "_volc")
    os.makedirs(tmpdir, exist_ok=True)
    parts = []
    for i in range(1, n + 1):
        text = _volc_prompt(caption, i, n)
        url, real = volc_music_chunk(vc, text, each)
        raw_path = os.path.join(tmpdir, "part%d.raw" % i)
        download_file(url, raw_path, timeout=300)
        with open(raw_path, "rb") as f:
            head = f.read(4)
        # 服务端实际返 WAV（Content-Type 常被标成 video/mp4，别信）
        wav = os.path.join(tmpdir, "part%d.wav" % i)
        if head == b"RIFF":
            os.replace(raw_path, wav)
        else:
            _audio_to_wav(cfg, raw_path, wav)
        parts.append(wav)
        info("  第 %d/%d 段就绪%s" % (i, n, ("（服务端时长 %.1fs）" % real) if real else ""))
    dst = os.path.join(paths["audio"], "bgm.mp3")
    _stitch_bgm(cfg, parts, dst, duration, fade)
    size = os.path.getsize(dst) / 1e6
    info("配乐 -> audio/bgm.mp3 (%.1f MB，火山引擎)" % size)


def do_music(cfg, paths, duration=None, caption=None, seed=None, provider=None,
             lyrics=None, force=False):
    prov = (provider or (cfg.get("music") or {}).get("provider") or "comfyui").strip().lower()
    if prov in ("volc", "volcengine", "doubao", "ark"):
        return do_music_volc(cfg, paths, duration, caption)
    if prov in ("comfyui", "comfy", "local", ""):
        return do_music_comfy(cfg, paths, duration, caption, seed, lyrics, force)
    die("不认识的配乐通道 %r，可选 comfyui / volc" % prov)


def cmd_music(args):
    cfg, paths = load_project(args.dir)
    do_music(cfg, paths, args.duration, args.caption, args.seed,
             provider=getattr(args, "provider", None),
             lyrics=getattr(args, "lyrics", None),
             force=getattr(args, "force", False))


# ----------------------------------------------------------------------------- init

def init_project(root, title=None, force=False):
    for d in PROJECT_DIRS:
        os.makedirs(os.path.join(root, d), exist_ok=True)

    cfg_path = os.path.join(root, "project.json")
    if os.path.exists(cfg_path) and not force:
        info("project.json 已存在，跳过（--force 覆盖）")
    else:
        # 项目文件只存创作参数；并发/轮询/超时等运行参数一律走全局配置，避免项目里写死后无法调优
        cfg = {
            "title": title or os.path.basename(root.rstrip("/\\")),
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ffmpeg": "ffmpeg",
            "agnes": {
                "seconds": DEFAULT_AGNES["seconds"],
                "aspect_ratio": DEFAULT_AGNES["aspect_ratio"],
                "image_size": DEFAULT_AGNES["image_size"],
                "image_ratio": DEFAULT_AGNES["image_ratio"],
            },
        }
        save_json(cfg_path, cfg)
        info("已创建 project.json（凭据与并发参数在 ~/.workbuddy/agnes-clip.json）")

    shots_path = os.path.join(root, "script", "shots.json")
    if not os.path.exists(shots_path):
        save_json(shots_path, {"shots": []})
        info("已创建 script/shots.json")

    readme = os.path.join(root, "README.md")
    if not os.path.exists(readme):
        with open(readme, "w", encoding="utf-8") as f:
            f.write("# %s\n\n由 agnes-clip-平哥分享版 管理。\n\n"
                    "| 目录 | 内容 |\n|---|---|\n"
                    "| script/ | story.md 剧本、shots.json 镜头表 |\n"
                    "| assets/characters/ | 角色定妆图 / 人脸参考 |\n"
                    "| assets/props/ | 道具参考 |\n"
                    "| frames/ | 每镜首帧图 |\n"
                    "| clips/ | 每镜视频片段 |\n"
                    "| audio/ | 配乐 |\n"
                    "| out/ | 成片 final.mp4 |\n" % (title or os.path.basename(root)))
    info("项目已就绪: " + root)


def cmd_init(args):
    init_project(os.path.abspath(args.dir), args.title, args.force)


# ----------------------------------------------------------------------------- story

STORY_SYSTEM = """你是资深竖屏短剧编剧兼分镜师。你的任务不是写解说词，而是写一场能拍的戏：
有场景、有动作、有微表情、有对白、有口型。

零、先立骨架（没有骨架不许写分镜）
0.1 logline 必须四要素齐全：谁 + 想要什么 + 遇到什么阻碍 + 最后变成什么。只写"她穿越了十个朝代"不算。
0.2 母题 `motif`：一个具体物件或动作贯穿全片，首镜出现、末镜回应（开头空手，结尾手里多了它）。
0.3 每镜必须给 `intensity`（-5~+5 的情绪值）、`purpose`（推进/停顿/转折）、`because`（因为上一镜____，所以这一镜____）、`audience`（观众该想什么）。
    全片要有至少一个最低点和一个最高点，禁止连续三镜同一 intensity。
0.4 禁止连续两镜都是"站着看/望着远处"。每镜必须有一个具体动作（推门、抬手、跨过、抓起、放下）。
0.5 写完做删一镜测试：删掉一镜故事不残缺，那镜就是废镜，重写。

一、戏怎么写
0. 先定基调：用户要温暖/治愈/积极，结尾必须落在重逢、和解、希望或日常的暖上；不要用死亡、绝症、苦情收尾。冲突可以有，但要给出出口。
1. 先定一场戏的时间、地点、天气、光源，再写人物。场景要能被镜头拍出来，不要写心理活动。
1.5 每个分镜必须写全四项：`scene`（含 `id` / 时间 / 地点 / 天气 / 光源）、`char`（人物）、`speaker`（谁说话）、`line`（对白）。
    全片只设 1–3 个场景，每个场景一个 `scene.id`。同一场景的镜头必须复用同一个 id；小场景对话只换机位和景别，不换布景，避免画面乱跳。
1.6 每个场景必须写“场景圣经” `scene.set`：5–8 条具体陈设，写到材质和颜色（例：“白瓷砖墙”“不锈钢煮面大锅冒热气”“红底塑料菜单牌”“木方桌配红色塑料凳”“玻璃门饮料冷柜”）。这是同一场景所有镜头共用的布景，禁止每镜另想一套。
1.7 每个场景必须写 `scene.axis`：谁在画左、谁在画右，三个机位都在轴线同一侧，整场不许换边。
    每个分镜的 frame.prompt 必须写清"景别 + 机位关系 + 人物在画面哪一侧"，例如
    "over-the-shoulder from behind him: she is framed on the left third, his shoulder soft in the right foreground"。
    缺了"哪一侧"模型就会自由发挥，一发挥就跳轴。
1.7.1 每个场景必须给机位表 `scene.angles`：键是机位名（wide / counter / table / door，或自定义），值是英文机位描述（摄影机在哪、朝哪、什么景别）。每个分镜用 `angle` 字段引用其中一个机位。同一场景的镜头只换机位，不换布景。
1.8 每个分镜写 `cast`：这一镜画面里出现的**所有**人物（角色 name 组成的数组）。画面里只能有这些人，绝不能出现背景路人、其他食客。
1.85 frame.prompt 必须写清这一镜台词提到的实物和位置：几碗面、碗放在谁面前、谁坐在哪个位置、手里拿的什么。台词说“两碗”就必须是两碗，说“对面”就必须能看到对面那个位置。只写“medium shot, warm light”会让画面和台词对不上。
1.9 每个角色必须有 `outfit_en`：全片固定不变的一套服装（上衣/下装/鞋/配件），写到颜色和材质。所有镜头复用同一套，禁止中途换衣服。
1.95 中国文化锚：写中式场景就写到底，不要写成日式。面馆要写白瓷砖墙、不锈钢大锅、红底菜单、塑料凳、玻璃饮料柜；不要写吧台、暖帘、居酒屋、榻榻米、寿司台。
2. 每一镜只做 1 个主要动作；一个连续长镜头，禁止切镜，video_prompt 禁止出现 cut to / jump cut。
3. 景别跨度不超过 2 倍（中远景 ↔ 腰部以上中景），禁止直接怼脸特写。
4. 同框不超过 2 人。同框时 frame.prompt 必须写明第二个角色的发型、服装颜色与材质、站位与朝向（参考图只锁主角的脸）。
5. 不写五官长相（脸由参考图锁定）；不写"史诗、震撼、杰作"；不写颜色光带。
5.5 角色一律是东亚人（中国人）长相。desc_en 必须以 "East Asian Chinese" 开头；每条 video_prompt 里要写明 All characters are East Asian Chinese with East Asian facial features, black hair, dark eyes。名字用英文时尤其要强调，否则模型会把人做成欧美人。
5.6 中餐餐具细节：筷子平放在碗沿或筷架上，不要直立插在饭/面里（像上香，是禁忌）。frame.prompt 里写清 chopsticks resting on the bowl rim。

二、微表情（必须写成过程）
不要写"她笑了/她难过"。写肌肉的顺序和眼神的变化，例如：
- "嘴角先轻轻提了一下，笑意才慢慢漫到眼底"
- "视线先落下，下唇收紧，再缓缓松开"
每镜最多 2 个微表情，只在腰以上景别使用。

三、对白与口型（这是片子的主体）
6. 至少一半镜头要有角色真正说出口的台词，第一镜就有人开口，最后一镜用一句台词收尾。不要通篇旁白。
7. 台词写进 line，说话人写进 speaker（角色 name；画外旁白写 "VO"）。每镜只说一句，≤18 个汉字，口语化、有潜台词，不要念说明书。
7.1 **短句不许单独成镜**：8 个字以内（「陈屿。」「我知道。」「嗯。」）不要占一个镜头——Agnes 一镜最少 4 秒，短句单独成镜必然空 2 秒。这种回应直接并在**相邻那一镜**里，当第二个人接话（管线也会自动合并）。
7.2 单镜时长硬约束：`seconds` 只能是 "4"–"12" 的字符串。台词镜按"字数/4.2 + 1 秒"给，封顶 8 秒；无台词镜按动作给。
8. 有台词的镜头必须用 waist-up medium shot 或 medium close-up，保证嘴部清楚可见；不要用远景说台词。
9. video_prompt 里必须原样引用台词，并写清口型同步，固定写法：
   The character speaks in Mandarin Chinese with precise lip-sync: "台词" —
   mouth shapes each syllable clearly, jaw and lips move naturally;
   keep the face turned toward the listener or camera so the mouth stays visible.
   台词前后各留 0.5 秒不说话，让口型和动作有呼吸感。

四、镜头语言（要灵活，不要十条一个样）
10. 全片景别要有变化：建立镜头用 wide / medium-wide，对话用 waist-up 或 medium close-up，情绪点可以用 close-up，但相邻镜头景别跨度不超过 2 倍。
11. 每镜 2–3 段运镜，写法要换：推近、拉远、跟随、环绕/环视（slow arc / orbit）、升降、手持、定点。同一种运镜不要连续用超过两镜。
11.5 全片用 1–2 次环视镜头（camera slowly arcs around the subject），用在情绪落点或三人同框，不要用在台词特写。
11.6 同一场景里紧接的两镜，如果是同一机位、同一组人在说话（正反打、接话），把后一镜标成 `"link": "prev"`：
     管线会直接取上一镜的**最后一帧**当这一镜的首帧，场景、站位、碗的位置全部接上，不会跳。
     注意：link=prev 的镜头不要再靠文生图首帧，也不要跨场景使用；接力镜头的 frame.prompt 仍要写画面内容，但只需要描述“从上一帧继续发生什么”。
12. 每镜写清 shot_size 和 camera 两个字段，video_prompt 用带时间码的 beat 落实。
13. 不要每镜都写 7 秒。时长由台词字数、beat 数、景别自动计算，你只需让内容配得上长度：宽景多给环境，特写少给动作。
14. **AI 画面里不能出现任何文字**。每镜 video_prompt 末尾必须加：
    No on-screen text, no subtitles, no captions, no watermark — clean image only.
    （字幕只在最后 ffmpeg 合成阶段按真实人声生成，不能烘进 AI 画面。）

只输出 JSON，不要 markdown 代码块，不要任何解释。格式：
{
  "title": "片名",
  "logline": "一句话故事",
  "genre": "类型",
  "characters": [
    {"name": "girl", "desc": "中文：年龄/性别/发型/体型/基础服装/气质",
     "desc_en": "East Asian Chinese, 24-year-old woman, shoulder-length black hair, slim",
     "outfit_en": "cream knit cardigan over a dark navy dress, black flat shoes",
     "voice": "zh-CN-XiaoxiaoNeural"}
  ],
  "props": [{"name": "prop_1", "desc": "中文", "desc_en": "English"}],
  "shots": [
    {
      "id": "S01",
      "duration": 0,
      "scene": {
        "id": "shop", "slug": "老街面馆·夜",
        "time": "深夜", "place": "老街面馆内", "weather": "无风，夜静", "light": "暖黄吊灯 + 窗外路面泛蓝光",
        "set": ["白瓷砖墙", "不锈钢煮面大锅冒热气", "红底塑料菜单牌", "木方桌配红色塑料凳", "玻璃门饮料冷柜", "墙上挂钟"],
        "angles": {
          "wide": "wide view from just inside the entrance looking toward the counter",
          "counter": "camera behind the counter looking across it at the dining tables",
          "table": "camera across the window-side table facing the window seat"
        }
      },
      "angle": "wide",
      "link": "",
      "char": "girl",
      "cast": ["girl"],
      "shot_size": "wide / medium-wide / waist-up medium / medium close-up",
      "camera": "dolly in slowly / follow / arc / static ...",
      "action": "中文：这一镜唯一的主要动作",
      "micro": "中文：微表情过程",
      "speaker": "girl",
      "line": "角色真正说出口的中文台词（≤18字）",
      "frame": {"mode": "swap", "prompt": "English first-frame prompt: location, outfit, lighting, composition, camera distance. Do NOT describe facial features. End with: Keep the face, identity and hairstyle exactly as in the reference image."},
      "video_prompt": "English: one continuous shot, no cuts. 0-3s ... 3-6s ... 6-8s ... Include the Mandarin line verbatim with precise lip-sync and a micro-expression process. Audio: ambience."
    }
  ]
}

要求：
- characters 1–2 个；props 0–3 个。
- duration 可以留 0，管线会按台词字数、beat 数、景别自动计算（4–12 秒）。
- 景别和运镜要有变化，不要十条一个样；对话镜头必须是腰以上。
- 8 镜的片子至少 4 镜有台词；6 镜至少 3 镜；不要把所有台词堆在最后。
- 第一镜建立场景并开口，最后一镜用台词收尾。"""


def generate_story(cfg, idea, n_shots, seconds, title=None):
    require_agnes_creds(cfg)
    total = int(n_shots * float(seconds))
    user = ("创意：%s\n镜头数：%d\n每镜时长：约 %s 秒（总时长约 %d 秒）\n%s"
            % (idea, n_shots, seconds, total,
               ("片名：%s" % title) if title else "片名你自己起。"))
    content = agnes_text(cfg, [
        {"role": "system", "content": STORY_SYSTEM},
        {"role": "user", "content": user},
    ], temperature=0.8, timeout=300, max_tokens=16000)

    data = parse_json_block(content)
    if not isinstance(data, dict) or "shots" not in data:
        content2 = agnes_text(cfg, [
            {"role": "system", "content": "把下面的内容修复成合法 JSON，只输出 JSON，不要解释：\n" + content[:30000]},
            {"role": "user", "content": "只输出 JSON"},
        ], temperature=0.2, timeout=300, max_tokens=16000)
        data = parse_json_block(content2)
        if not isinstance(data, dict) or "shots" not in data:
            die("剧本模型没有返回合法 JSON。原始输出前 800 字：\n" + content[:800])
    return normalize_story(data, n_shots, seconds, title)


def parse_json_block(text):
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", t)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


FEMALE_VOICES = ["zh-CN-XiaoxiaoNeural", "zh-CN-XiaoyiNeural", "zh-CN-liaoning-XiaobeiNeural"]
MALE_VOICES = ["zh-CN-YunxiNeural", "zh-CN-YunjianNeural", "zh-CN-YunyangNeural"]


def _gender_hint(text):
    t = (text or "").lower()
    if any(k in t for k in ("\u5973", "female", "woman", "girl", "\u5979")):
        return "f"
    if any(k in t for k in ("\u7537", "male", "man", "boy", "\u4ed6")):
        return "m"
    return "f"


def assign_voices(chars):
    """同一部片子里不同角色尽量给不同音色，并纠正性别不匹配的音色。"""
    used = set()
    for c in chars:
        hint = _gender_hint((c.get("desc") or "") + " " + (c.get("desc_en") or ""))
        pool = FEMALE_VOICES if hint == "f" else MALE_VOICES
        other = MALE_VOICES if hint == "f" else FEMALE_VOICES
        v = (c.get("voice") or "").strip()
        # 模型给错的性别音色直接丢弃
        if v and v not in other and v not in used:
            used.add(v)
            c["voice"] = v
            continue
        pick = next((x for x in pool if x not in used), None)
        if not pick:
            pick = pool[0]
        used.add(pick)
        c["voice"] = pick
    return chars


CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def count_beats(vp):
    """数视频提示词里有几个带时间码的镜头 beat（0-3s / 3-6s …）。"""
    hits = re.findall(r"\d+(?:\.\d+)?\s*(?:-|–|—)\s*\d+(?:\.\d+)?\s*s", vp or "")
    return max(1, len(hits))


def calc_duration(line, beats, shot_size=""):
    """按台词字数、镜头 beat 数、景别自动算这条镜头该多长（4–12 秒）。

    中文语速约 4.2 字/秒；景别越大，需要的时间越多（看得清空间）；
    特写可以短，宽景要长。模型给的 duration 只作参考，最终以这里为准。
    """
    n = len(CJK_RE.findall(line or ""))
    speech = (n / 4.2 + 1.2) if n else 0.0
    size = (shot_size or "").lower()
    if "medium-wide" in size or "medium wide" in size:
        space = 1.6
    elif "wide" in size:
        space = 2.2
    elif "close" in size:
        space = 0.6
    else:
        space = 1.2
    action = beats * 1.7 + space
    if n:
        # 有台词：以台词为锚。一句 13 字约 3.1 秒说话，加 1 秒起落就是 4-5 秒，
        # 不再让"动作/空间"把镜头撑到 7-10 秒（那会变成前 6 秒干站着）。
        d = speech + 0.9
        if "wide" in size:
            d += 0.5
        return max(4, min(8, int(round(d))))
    return max(4, min(12, int(round(action))))


def _clean_cn(t):
    t = (t or "").strip()
    for p in ("中文：", "中文:", "Chinese:", "中文描述："):
        if t.startswith(p):
            t = t[len(p):].strip()
    return t


def _scene_id_from_place(place):
    p = (place or "scene").strip()
    for suf in ("靠窗桌", "柜台", "门口", "店内", "内景", "外景", "桌边", "窗边"):
        p = p.replace(suf, "")
    p = re.sub(r"[^\w\-]+", "_", p).strip("_")
    return p or "scene"


def _merge_scene_ids(ids):
    """把“面馆靠窗桌/面馆柜台/面馆门口”这类同一地点的 id 合并成一个。"""
    uniq = sorted(set(ids), key=len)
    mapping = {}
    for x in uniq:
        base = x
        for y in uniq:
            if y != x and len(y) >= 2 and y in x:
                base = y
                break
        mapping[x] = base
    return [mapping[x] for x in ids]


def normalize_story(data, n_shots, seconds, title=None):
    chars = data.get("characters") or []
    if not isinstance(chars, list) or not chars:
        chars = [{"name": "hero", "desc": "主角", "desc_en": "the main character"}]
    char_names = []
    for c in chars:
        name = (c.get("name") or "hero").strip()
        c["name"] = name
        c["desc"] = _clean_cn(c.get("desc"))
        if not c.get("desc_en"):
            c["desc_en"] = c.get("desc") or name
        de = (c.get("desc_en") or "").strip()
        if "east asian" not in de.lower() and "chinese" not in de.lower():
            de = "East Asian Chinese, " + de
        c["desc_en"] = de
        c["outfit_en"] = (c.get("outfit_en") or "").strip()
        char_names.append(name)
    assign_voices(chars)

    props = data.get("props") or []
    if not isinstance(props, list):
        props = []
    for p in props:
        p["name"] = (p.get("name") or "prop").strip()
        if not p.get("desc_en"):
            p["desc_en"] = p.get("desc") or p["name"]

    shots = data.get("shots") or []
    if not isinstance(shots, list) or not shots:
        die("剧本没有镜头")
    raw_ids = []
    for s in shots[:n_shots]:
        sc = s.get("scene")
        if isinstance(sc, dict):
            sid_ = (sc.get("id") or "").strip() or _scene_id_from_place(sc.get("place") or sc.get("slug"))
        else:
            sid_ = _scene_id_from_place(str(sc or ""))
        raw_ids.append(sid_)
    scene_ids = _merge_scene_ids(raw_ids)
    out = []
    for i, s in enumerate(shots[:n_shots]):
        sid = "S%02d" % (i + 1)
        dur = 7  # 占位；下面按台词/beat/景别重算
        ch = s.get("char") or char_names[0]
        if ch not in char_names:
            ch = char_names[0]
        frame = s.get("frame") or {}
        mode = frame.get("mode") if frame.get("mode") in ("source", "swap") else "swap"
        fp = (frame.get("prompt") or "").strip()
        if mode == "swap" and not fp:
            fp = ("Cinematic film still of the character in a scene matching the story, medium shot, "
                  "natural lighting, shallow depth of field. "
                  "Keep the face, identity and hairstyle exactly as in the reference image.")
        vp = (s.get("video_prompt") or "").strip()
        if not vp:
            vp = ("One continuous shot, no cuts. The character moves naturally in the scene, "
                  "the camera slowly pushes in, natural light, cinematic realism.")
        line = (s.get("line") or "").strip()
        if len(line) > 18:
            line = line[:18]
        speaker = (s.get("speaker") or "").strip()
        if line:
            if not speaker:
                speaker = ch
            elif speaker != "VO" and speaker not in char_names:
                speaker = ch
        else:
            speaker = ""
        scene = s.get("scene") or {}
        if isinstance(scene, str):
            scene = {"slug": scene}
        if not isinstance(scene, dict):
            scene = {}
        scene["id"] = scene_ids[i]
        # 场景圣经：陈设清单 + 机位表（同一场景的所有镜头必须共用同一份）
        st = scene.get("set")
        if isinstance(st, str):
            st = [st]
        scene["set"] = [x.strip() for x in (st or []) if isinstance(x, str) and x.strip()]
        if not isinstance(scene.get("angles"), dict):
            scene["angles"] = {}
        angle = (s.get("angle") or "").strip() or "wide"
        angle = re.sub(r"\s+", "-", angle)[:40]
        scene["angles"].setdefault(angle, "")
        # 本镜 cast 白名单：只能出现这些人，不许有背景路人
        cast = s.get("cast")
        if isinstance(cast, str):
            cast = [cast]
        cast = [c for c in (cast or []) if c in char_names]
        if cast and ch not in cast:
            ch = cast[0]
        if not cast:
            cast = [ch]
        cast = list(dict.fromkeys(cast))
        action = _clean_cn(s.get("action"))
        micro = _clean_cn(s.get("micro"))
        shot_size = (s.get("shot_size") or "").strip()
        camera = (s.get("camera") or "").strip()
        # 时长由内容决定：台词字数 + 时间码 beat 数 + 景别
        if not line and s.get("duration"):
            try:
                dur = max(4, min(12, int(round(float(s["duration"])))))
            except Exception:
                dur = calc_duration(line, count_beats(vp), shot_size)
        else:
            dur = calc_duration(line, count_beats(vp), shot_size)
        # 台词必须落在镜头前段：写死开口窗口，禁止拖到最后
        if line:
            n_cjk = len(CJK_RE.findall(line))
            spoken = max(1.2, n_cjk / 4.2)
            lead = 0.5 if dur <= 6 else 0.7
            speak_end = min(dur - 0.6, lead + spoken)
            if speak_end <= lead + 0.6:
                speak_end = max(lead + 0.8, dur - 1.0)
            timed = (' Timing: the character starts speaking at about %.1fs and finishes the line by %.1fs; '
                     'after %.1fs only a silent reaction — never delay the line to the end of the shot.'
                     % (lead, speak_end, speak_end))
            # 口型指令：默认普通话；镜头规格里写了 dialect 就换成对应方言，
            # 让画面里的人自己就在说那种话，口型和叠上去的方言 TTS 对得上。
            dialect = (s.get("dialect") or "").strip()
            if dialect:
                lang = ("%s with precise lip-sync" % dialect)
                extra = ("the accent is clearly audible in the mouth shapes, "
                         "the tongue and jaw follow the local pronunciation, not standard Mandarin")
            else:
                lang = "Mandarin Chinese with precise lip-sync"
                extra = "mouth shapes each syllable clearly, jaw and lips move naturally"
            lips = (' The character speaks in %s: "%s" — '
                    '%s; '
                    'keep the face turned toward the listener or camera so the mouth stays visible.'
                    % (lang, line, extra))
            low = vp.lower()
            if "precise lip-sync" not in low and "lip sync" not in low:
                vp = vp.rstrip() + timed + lips
            else:
                vp = vp.rstrip() + timed
        if "no subtitles" not in vp.lower() and "no on-screen text" not in vp.lower():
            vp = vp.rstrip() + " No on-screen text, no subtitles, no captions, no watermark — clean image only."
        if "east asian" not in vp.lower():
            vp = vp.rstrip() + EAST_ASIAN
        out.append({
            "id": sid,
            "duration": dur,
            "scene": scene,
            "angle": angle,
            "cast": cast,
            "link": (s.get("link") or "").strip().lower(),
            "intensity": s.get("intensity"),
            "purpose": (s.get("purpose") or "").strip(),
            "because": (s.get("because") or "").strip(),
            "audience": (s.get("audience") or "").strip(),
            "char": ch,
            "shot_size": shot_size,
            "camera": camera,
            "action": action,
            "micro": micro,
            "speaker": speaker,
            "frame": {"mode": mode, "prompt": fp},
            "video_prompt": vp,
            "line": line,
        })

    # 同一场景统一布景与机位表：取第一条非空的，避免每个镜头各长一套
    byscene = {}
    for s in out:
        k = s["scene"]["id"]
        cur = byscene.setdefault(k, {"set": [], "angles": {}})
        if not cur["set"] and s["scene"].get("set"):
            cur["set"] = list(s["scene"]["set"])
        for a, d in (s["scene"].get("angles") or {}).items():
            if d and not cur["angles"].get(a):
                cur["angles"][a] = d
            cur["angles"].setdefault(a, d)
    for s in out:
        k = s["scene"]["id"]
        s["scene"]["set"] = byscene[k]["set"] or list(DEFAULT_SCENE_SET)
        angles = byscene[k]["angles"] or {}
        for a in {s.get("angle") or "wide"}:
            if not angles.get(a):
                angles[a] = DEFAULT_ANGLES.get(a, a.replace("-", " "))
        s["scene"]["angles"] = angles

    out = merge_short_shots(out)

    return {
        "title": title or data.get("title") or "untitled",
        "logline": data.get("logline") or "",
        "genre": data.get("genre") or "",
        "characters": chars,
        "props": props,
        "shots": out,
    }


def merge_short_shots(shots, max_chars=6):
    """短台词不单独成镜：并进相邻镜，避免 Agnes 4 秒下限里空掉两秒。

    合并条件（缺一条就单独成镜）：
    1. ≤6 个汉字的短回应（「陈屿。」「我知道。」「嗯。」）；
    2. 与上一镜同场景，且上一镜还没并过别的句子；
    3. 合并后画面不超过 2 人；如果接话的人本来不在画面里，把他补进 cast 变成双人镜头；
    4. 两句合起来能装进 8 秒。
    """
    out = []
    for s in shots:
        line = (s.get("line") or "").strip()
        n = len(CJK_RE.findall(line))
        if out and 0 < n <= max_chars:
            prev = out[-1]
            speaker = s.get("speaker") or s.get("char")
            cast = list(prev.get("cast") or [])
            if (prev["scene"]["id"] == s["scene"]["id"] and not prev.get("extra_lines")
                    and (speaker in cast or len(cast) < 2)):
                if speaker not in cast:
                    cast.append(speaker)
                    prev["cast"] = cast
                    fp = (prev.get("frame") or {}).get("prompt") or ""
                    prev.setdefault("frame", {})["prompt"] = (
                        fp.rstrip() + " Frame this as a TWO-SHOT: %s is also in frame, "
                        "facing the other person, both faces visible." % speaker)
                total_chars = len(CJK_RE.findall(prev.get("line") or "")) + n
                need = total_chars / 4.2 + 1.9
                if need <= 8:
                    prev["extra_lines"] = [{"speaker": speaker, "line": line}]
                    prev["duration"] = max(prev["duration"], min(8, int(round(need + 0.4))))
                    prev["video_prompt"] = (prev["video_prompt"].rstrip() +
                        ' Then %s answers briefly, a different voice: "%s" — short reply, '
                        'natural lip movement, the camera stays on both of them.'
                        % (speaker, line))
                    info("%s 的「%s」只有 %d 字，并入 %s（该镜 %ss，双人）"
                         % (s["id"], line, n, prev["id"], prev["duration"]))
                    continue
        out.append(s)
    for i, s in enumerate(out):
        s["id"] = "S%02d" % (i + 1)
    return out


def write_story_files(paths, story):
    title = story["title"]
    lines = ["# " + title, ""]
    if story.get("logline"):
        lines += ["> " + story["logline"], ""]
    if story.get("genre"):
        lines += ["类型：" + story["genre"], ""]

    lines += ["## 角色", ""]
    for c in story["characters"]:
        voice = ("（音色 %s）" % c["voice"]) if c.get("voice") else ""
        lines.append("- **%s**%s：%s" % (c["name"], voice, c.get("desc", "")))
    if story.get("props"):
        lines += ["", "## 道具", ""]
        for p in story["props"]:
            lines.append("- **%s**：%s" % (p["name"], p.get("desc", "")))

    # 场景分组：同场景镜头共用一张场景板
    groups = {}
    for s in story["shots"]:
        groups.setdefault(scene_key(s), []).append(s)
    lines += ["", "## 场景分组", "", "| 场景 | 地点 | 光线 | 镜号 |", "|---|---|---|---|"]
    for k, g in groups.items():
        sc = g[0].get("scene") or {}
        lines.append("| %s | %s | %s | %s |" % (
            k, sc.get("place") or "-", sc.get("light") or "-",
            ", ".join(x["id"] for x in g)))

    lines += ["", "## 分镜表", "", "| 镜号 | 时长 | 场景 | 说话人 | 台词 |", "|---|---|---|---|---|"]
    for s in story["shots"]:
        slug = (s.get("scene") or {}).get("slug") or "-"
        who = s.get("speaker") or "-"
        if who == "VO":
            who = "旁白"
        lines.append("| %s | %ss | %s | %s | %s |" % (
            s["id"], s["duration"], slug, who, s.get("line") or ""))

    lines += ["", "## 剧本正文", ""]
    for s in story["shots"]:
        sc = s.get("scene") or {}
        slug = sc.get("slug") or "未命名场景"
        lines.append("### %s · %s · %ss" % (s["id"], slug, s["duration"]))
        meta = " / ".join([x for x in (sc.get("time"), sc.get("place"), sc.get("weather"), sc.get("light")) if x])
        if meta:
            lines.append("- **场景**：" + meta)
        if s.get("link") in ("prev", "tail", "prev-tail", "prev_tail"):
            lines.append("- **接力**：首帧取上一镜尾帧（场景/站位直接接上）")
        lines.append("- **机位**：" + (s.get("angle") or "wide"))
        if s.get("intensity") is not None:
            lines.append("- **情绪**：%s（%s）" % (s.get("intensity"), s.get("purpose") or ""))
        if s.get("because"):
            lines.append("- **因果**：" + s["because"])
        if s.get("audience"):
            lines.append("- **观众该想**：" + s["audience"])
        shot = " / ".join([x for x in (s.get("shot_size"), s.get("camera")) if x])
        if shot:
            lines.append("- **镜头**：" + shot)
        who = s.get("speaker")
        who_txt = "旁白" if who == "VO" else (who or "无台词")
        lines.append("- **人物**：%s；说话：%s" % (s.get("char") or "-", who_txt))
        if s.get("action"):
            lines.append("- **动作**：" + s["action"])
        if s.get("micro"):
            lines.append("- **微表情**：" + s["micro"])
        if s.get("line"):
            who = "旁白" if s.get("speaker") == "VO" else s.get("speaker")
            lines.append("- **对白**：%s：「%s」" % (who, s["line"]))
        else:
            lines.append("- **对白**：（无台词）")
        lines.append("")

    lines += ["> 镜头表机器可读版本见 `script/shots.json`。", ""]

    os.makedirs(os.path.dirname(paths["story"]), exist_ok=True)
    with open(paths["story"], "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    save_json(paths["shots"], story)


def text_provider(cfg):
    return ((cfg.get("text") or {}).get("provider") or "workbuddy").lower()


def do_story(cfg, paths, idea, n_shots, seconds, title=None):
    # 推理用 WorkBuddy 默认时，不调外部 API：把提示词落盘，交给当前会话模型写 shots.json
    if text_provider(cfg) == "workbuddy":
        total = int(n_shots * float(seconds))
        prompt = (STORY_SYSTEM + "\n\n---\n\n创意：%s\n镜头数：%d\n每镜时长：约 %s 秒（总时长约 %d 秒）\n%s\n"
                  % (idea, n_shots, seconds, total,
                     ("片名：%s" % title) if title else "片名你自己起。"))
        p = os.path.join(paths["root"], "script", "story_prompt.md")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(prompt)
        die("推理当前设为 WorkBuddy 默认：剧本应由当前会话模型按 script/story_prompt.md 直接写入 "
            "script/shots.json（无需外部 key）。写好后再运行 auto。")
    info("生成剧本与镜头表（%d 镜，按内容自动算时长）..." % n_shots)
    story = generate_story(cfg, idea, n_shots, seconds, title)
    write_story_files(paths, story)
    info("剧本 -> script/story.md，镜头表 -> script/shots.json（%d 镜）" % len(story["shots"]))
    return story


def cmd_story(args):
    cfg, paths = load_project(args.dir)
    do_story(cfg, paths, args.idea, args.shots, args.seconds, args.title)


# ----------------------------------------------------------------------------- characters

def make_turnaround(cfg, paths, name):
    """生成角色三视图（正面 / 侧面 / 背面），用于形象确认与扩展。"""
    exe = have_ffmpeg(cfg)
    cdir = char_dir(paths, name)
    src = os.path.join(cdir, "face_ref.jpg")
    if not os.path.exists(src):
        die("找不到 %s 的 face_ref.jpg" % name)
    prompt = ("Character turnaround sheet of an East Asian Chinese person: the same person shown in "
              "three full-body views side by side — front view, side view, back view. "
              "East Asian facial features, black hair. Identical face, hairstyle, body proportions and outfit "
              "across all three views. Pure white background, even flat lighting, full body in frame, "
              "orthographic, like a game character design sheet. No text, no watermark.")
    info("%s 生成三视图 ..." % name)
    raw, _ = agnes_image_generate(cfg, prompt, ref_paths=[src], project_paths=paths)
    save_image_bytes(raw, os.path.join(cdir, "turnaround.jpg"), exe)
    info("%s 三视图 -> assets/characters/%s/turnaround.jpg" % (name, name))


# --------------------------------------------------------------------------- 角度分格裁切
#
# 设定卡里本来就有正面/侧面/背面，但首帧生成一直只喂 face_ref.jpg（正面），
# 于是拍侧背面时模型只能自己脑补 → 转个角度脸就漂。
# 这里把设定卡按白色分隔带自动定位格子，裁成独立小图存进 assets/characters/<名>/views/，
# 首帧按机位挑对应角度喂进去。
#
# 为什么不写死比例：Agnes 和 GPT Image 两个通道出的卡尺寸不同（1254 vs 2048），
# 分格位置也不完全一致。实测用"白底列投影找分隔带"两边都稳。

VIEW_NAMES = ("front", "side", "back")


def _card_panels(img_path):
    """在设定卡上半部找竖直白色分隔带，返回各格的 x 区间。

    只用 Pillow，不依赖 numpy——大多数环境没装，装依赖会让 skill 跑不起来。
    算法：逐列统计「该列在中上部有多少比例的像素接近纯白」，连续超阈值的列
    合成一条分隔带，再把贴边的（画布边界）去掉，剩下的中点即为格线。
    """
    from PIL import Image
    im = Image.open(img_path).convert("L")     # 灰度：白 = 255
    w, h = im.size                              # 原图尺寸
    y0, y1 = int(h * 0.04), int(h * 0.56)
    crop = im.crop((0, y0, w, y1))
    cw, ch = crop.size                          # 裁片尺寸（只有高度变了）
    px = crop.load()
    # 每列的「近白行数」占比
    ratio = []
    for x in range(cw):
        n = 0
        for y in range(ch):
            if px[x, y] > 232:
                n += 1
        ratio.append(n / float(ch))
    thr, minw = 0.88, max(2, int(w * 0.002))
    runs, cur = [], None
    for x in range(cw):
        if ratio[x] > thr:
            cur = [x, x] if cur is None else [cur[0], x]
        else:
            if cur:
                runs.append(cur)
                cur = None
    if cur:
        runs.append(cur)
    merged = []
    for r in runs:
        if merged and r[0] - merged[-1][1] < w * 0.006:
            merged[-1][1] = r[1]
        else:
            merged.append(list(r))
    inner = [r for r in merged if r[0] > w * 0.01 and r[1] < w * 0.99]
    bounds = [0] + [(r[0] + r[1]) // 2 for r in inner] + [w]
    cells = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]
    return im, (h, w), [c for c in cells if c[1] - c[0] > w * 0.05]


def cut_views(cfg, paths, name, quiet=False):
    """把设定卡裁成 views/front.jpg、side.jpg、back.jpg。

    设定卡版式：大头 | 正面 | 侧面 | 背面 | 细节列（sheets）
    或：大头 | 正 | 四分之三侧 | 侧 | 背（turnaround）
    两种都取"中间那几格"当三视图。裁不准就返回空 dict，不影响主流程。
    """
    cdir = char_dir(paths, name)
    card = os.path.join(cdir, "char_card.jpg")
    if not os.path.exists(card):
        return {}
    try:
        im, (h, w), cells = _card_panels(card)
    except Exception as e:
        warn("%s 设定卡分格定位失败（不影响出片）：%s" % (name, str(e)[:80]))
        return {}
    if len(cells) < 3:
        warn("%s 设定卡只识别到 %d 格，跳过分角度参考图" % (name, len(cells)))
        return {}
    # 第 0 格是大头，中间是三视图，末格是细节列
    mid = cells[1:-1]
    if len(mid) == 4:          # turnaround 版式多一个四分之三侧，取后三个
        mid = mid[-3:]
    if len(mid) < 3:
        return {}
    vdir = os.path.join(cdir, "views")
    os.makedirs(vdir, exist_ok=True)
    made = {}
    y0, y1 = int(h * 0.02), int(h * 0.62)
    for nm, (x0, x1) in zip(VIEW_NAMES, mid[:3]):
        dst = os.path.join(vdir, nm + ".jpg")
        try:
            crop = im.crop((x0, y0, x1, y1))
            # 裁完缩到长边 1024，喂参考图不必给太大
            sc = 1024.0 / max(crop.size)
            if sc < 1:
                crop = crop.resize((max(1, int(crop.width * sc)),
                                    max(1, int(crop.height * sc))))
            crop.convert("RGB").save(dst, "JPEG", quality=92)
            made[nm] = dst
        except Exception as e:
            warn("%s 裁 %s 失败：%s" % (name, nm, str(e)[:60]))
    if made and not quiet:
        info("%s 已分出角度参考图: %s" % (name, " / ".join(made)))
    return made


def view_for_angle(paths, name, angle):
    """按机位挑角度参考图；没有就回落到 face_ref.jpg。

    只在"确实要看到脸"的机位才用角度图：
    - front / eye / close → 正面
    - side / three_quarter → 侧面（四分之三）
    - back → 背面
    - 顶视/俯视/过肩等拿不准的，一律用 face_ref.jpg（最稳）
    """
    fref = os.path.join(char_dir(paths, name), "face_ref.jpg")
    a = (angle or "").strip().lower()
    pick = None
    if a in ("back", "rear", "from_behind"):
        pick = "back"
    elif a in ("side", "profile", "three_quarter", "3q"):
        pick = "side"
    elif a in ("front", "eye", "close", "closeup", "portrait"):
        pick = "front"
    else:
        return fref if os.path.exists(fref) else None
    p = os.path.join(char_dir(paths, name), "views", pick + ".jpg")
    if os.path.exists(p):
        return p
    return fref if os.path.exists(fref) else None


def cmd_views(args):
    """从已有设定卡重切角度参考图（改了版式或换了卡之后用）。"""
    cfg, paths = load_project(args.dir)
    names = []
    if args.name:
        names = [args.name]
    else:
        cdir = paths["chars"]
        if os.path.isdir(cdir):
            names = [d for d in sorted(os.listdir(cdir))
                     if os.path.isdir(os.path.join(cdir, d))]
    if not names:
        die("没有可用角色（先跑 char-gen）")
    for n in names:
        made = cut_views(cfg, paths, n)
        if not made:
            print("  %s: 没有可用设定卡，跳过" % n)
    info("完成。角度图在各角色的 views/ 下。")


# 角色设定卡（character sheet）的分格布局。
# 参考的是常见的国漫/游戏角色设定稿：大头 + 多角度 + 表情行 + 细节特写。
# 实测 agnes-image-2.5-flash 能稳定复刻这种排版，且每格人脸一致。
CHAR_CARD_STYLES = {
    "sheets": (
        "Professional character design sheet, multi-panel layout on a pure white background. "
        "Left third: one large head-and-shoulders portrait, facing the viewer. "
        "Center: three full-body turnaround views side by side — front view, side view, back view. "
        "Bottom row: four square expression close-ups — neutral, looking down, angry, faint smile. "
        "Right edge: four small square detail crops — face close-up, hand, sleeve cuff, and one prop. "
        "Every panel shows the identical person: same face, same hairstyle, same costume, same proportions. "
        "Clean semi-realistic rendering, even flat lighting, thin neat panel dividers between panels."
    ),
    "turnaround": (
        "Professional character turnaround sheet, multi-panel layout on a pure white background. "
        "Left third: one large head-and-shoulders portrait. "
        "Center: full-body front view, three-quarter view, side view and back view in one row. "
        "Bottom row: four square expression close-ups — neutral, looking down, angry, faint smile. "
        "Right edge: full-body standing pose. "
        "Every panel shows the identical person: same face, same hairstyle, same costume. "
        "Clean semi-realistic rendering, even flat lighting, thin neat panel dividers."
    ),
}


def make_char_card(cfg, paths, name, face_ref, desc="", outfit="", style="sheets",
                   channel=None):
    """以正脸为参考，生成多格角色设定卡（大头 + 多角度 + 表情 + 细节）。

    face_ref 必须是干净的正脸单图——设定卡里每一格都要靠它保持同一个人。

    channel：留空 = 跟随项目/全局出图通道。但**必须与生成 face_ref 的通道一致**，
    否则两张图是两张脸，卡上的人会对不上锚点。传了 channel 就强制走它。
    """
    base = CHAR_CARD_STYLES.get(style) or CHAR_CARD_STYLES["sheets"]
    who = "East Asian Chinese person"
    bits = [base, who]
    if desc.strip():
        bits.append("Character details: " + desc.strip() + ".")
    if outfit.strip():
        bits.append("Wearing exactly this outfit in every panel: " + outfit.strip() + ".")
    bits.append("No text, no letters, no captions, no watermark, no signature.")
    prompt = " ".join(bits)
    cdir = char_dir(paths, name)
    out = os.path.join(cdir, "char_card.jpg")
    info("%s 生成角色设定卡 ..." % name)
    raw, _ = agnes_image_generate(cfg, prompt, ref_paths=[face_ref],
                                  size="2K", ratio="1:1", project_paths=paths,
                                  force_channel=channel)
    save_image_bytes(raw, out, have_ffmpeg(cfg))
    info("%s 设定卡 -> assets/characters/%s/char_card.jpg" % (name, name))
    return out


def do_char_gen(cfg, paths, name, desc, with_turnaround=False, outfit="",
                card=True, card_style="sheets", channel=None, force=False):
    """生成角色资产。

    两段式：
      1. 先出一张干净正脸半身照 → source.jpg / face_ref.jpg
         （这张是首帧的锁脸锚点，必须干净、单人、正面）
      2. 再以它为参考出多格角色设定卡 → char_card.jpg
         （大头 + 多角度 + 表情行 + 细节特写，给人看设定用，不参与锁脸）

    channel：None=跟随配置；"agnes"/"gpt-image"/"banana" 可显式指定。
    两段必须同通道，所以先定下 channel 再两段都用它。

    幂等：face_ref.jpg 已存在且描述/服装/通道都没变时直接跳过（**每次重跑都烧额度**）。
    """
    require_agnes_creds(cfg)
    exe = have_ffmpeg(cfg)
    cdir = os.path.join(paths["chars"], name)
    os.makedirs(cdir, exist_ok=True)
    ch = (channel or "").strip() or image_channel(cfg, paths)

    # ── 幂等守卫：已有资产且规格未变就跳过 ──
    meta_p = os.path.join(cdir, "meta.json")
    face_p = os.path.join(cdir, "face_ref.jpg")
    if not force and os.path.exists(face_p) and os.path.exists(meta_p):
        try:
            old = json.load(open(meta_p, encoding="utf-8"))
            same = (old.get("desc") == desc and old.get("outfit") == outfit
                    and old.get("channel") == ch
                    and (not card or bool(old.get("char_card"))))
            if same:
                info("角色 %s 已存在（face_ref.jpg + 设定卡齐全），跳过。--force 可重做" % name)
                return
            info("角色 %s 规格有变化，重新生成" % name)
        except Exception:
            pass

    # 定妆图的服装必须和全片 outfit_en 一致，否则首帧会照着参考图穿错衣服。
    wear = ("Wearing exactly this outfit: %s. " % outfit.strip()) if (outfit or "").strip() else ""
    prompt = ("Character reference portrait of an East Asian Chinese person: %s. "
              "%s"
              "East Asian facial features, black hair, dark eyes, natural East Asian skin tones. "
              "Front-facing half-body, neutral standing pose, clean neutral studio background, "
              "soft even lighting, photorealistic cinematic look, natural skin texture, "
              "sharp facial features. Single person only, plain backdrop, "
              "no text, no watermark." % (desc, wear))
    info("生成角色形象 %s（通道 %s）..." % (name, ch))
    raw, _ = agnes_image_generate(cfg, prompt, project_paths=paths, force_channel=ch)
    save_image_bytes(raw, os.path.join(cdir, "source.jpg"), exe)
    shutil.copy2(os.path.join(cdir, "source.jpg"), os.path.join(cdir, "face_ref.jpg"))
    if card:
        card_path = make_char_card(cfg, paths, name, os.path.join(cdir, "face_ref.jpg"),
                                   desc=desc, outfit=outfit, style=card_style, channel=ch)
        # 设定卡里已有正/侧/背三视图，裁成独立小图供首帧按机位取用。
        # 裁不出来不影响出片，首帧会照旧用 face_ref.jpg。
        views = cut_views(cfg, paths, name)
    else:
        card_path, views = "", {}
    if with_turnaround:
        make_turnaround(cfg, paths, name)
    save_json(os.path.join(cdir, "meta.json"), {
        "name": name,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "desc": desc,
        "outfit": outfit,
        "channel": ch,
        "source": "source.jpg",
        "face_ref": "face_ref.jpg",
        "char_card": "char_card.jpg" if card else "",
        "card_style": card_style if card else "",
        "views": {k: os.path.relpath(v, cdir).replace(os.sep, "/")
                  for k, v in (views or {}).items()},
        "rule": "所有首帧一律以 face_ref.jpg 为参考图；禁止用上一段尾帧接力（会累积漂移）",
        "card_rule": "char_card.jpg 是设定稿，给人看造型用；不要拿它当首帧参考图，"
                     "多格排版会污染单镜头构图",
        "channel_rule": "face_ref 与 char_card 必须在同一条出图通道上生成（换通道 = 换脸）",
        "view_rule": "views/ 是从设定卡裁出的角度图，首帧按机位自动取；"
                     "拿不准的机位仍走 face_ref.jpg",
    })
    info("角色资产完成: assets/characters/%s/" % name)


def cmd_char_gen(args):
    cfg, paths = load_project(args.dir)
    name = args.name or "hero"
    desc = args.desc
    outfit = getattr(args, "outfit", "") or ""
    if not desc or not outfit:
        sj = load_json(paths["shots"], {"shots": []})
        for c in sj.get("characters", []):
            if c.get("name") == name:
                desc = desc or c.get("desc_en") or c.get("desc")
                outfit = outfit or c.get("outfit_en") or ""
                break
    if not desc:
        die("缺少 --desc，且 shots.json 的 characters 里没有 %s 的描述" % name)
    style = getattr(args, "card_style", "") or "sheets"
    if style not in CHAR_CARD_STYLES:
        die("--card-style 只能是：%s" % " / ".join(CHAR_CARD_STYLES))
    chan = getattr(args, "channel", "") or ""
    if chan and chan not in IMAGE_CHANNELS:
        die("--channel 只能是：%s" % " / ".join(sorted(IMAGE_CHANNELS)))
    do_char_gen(cfg, paths, name, desc, with_turnaround=args.tri, outfit=outfit,
                card=not getattr(args, "no_card", False), card_style=style,
                channel=chan or None, force=getattr(args, "force", False))


def cmd_char_add(args):
    """已有真人照片：导入为角色资产。"""
    cfg, paths = load_project(args.dir)
    require_agnes_creds(cfg)
    exe = have_ffmpeg(cfg)
    name = args.name
    src = os.path.abspath(args.image)
    if not os.path.exists(src):
        die("图片不存在: " + src)
    cdir = os.path.join(paths["chars"], name)
    os.makedirs(cdir, exist_ok=True)
    shutil.copy2(src, os.path.join(cdir, "source.jpg"))
    shutil.copy2(src, os.path.join(cdir, "face_ref.jpg"))
    info("已导入原图 -> source.jpg / face_ref.jpg（零漂移锚点）")
    prompt = ("Character turnaround sheet: the same person shown in three full-body views side by side — "
              "front, side, back. Identical face, hairstyle and outfit across views. Pure white background, "
              "even flat lighting, full body, orthographic. No text, no watermark.")
    info("生成三视图 ...")
    raw, _ = agnes_image_generate(cfg, prompt, ref_paths=[src], project_paths=paths)
    save_image_bytes(raw, os.path.join(cdir, "turnaround.jpg"), exe)
    save_json(os.path.join(cdir, "meta.json"), {
        "name": name,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "source.jpg",
        "face_ref": "face_ref.jpg",
        "turnaround": "turnaround.jpg",
        "rule": "所有首帧一律以 face_ref.jpg 为参考图；禁止用上一段尾帧接力（会累积漂移）",
    })
    info("角色资产完成: assets/characters/%s/" % name)


# ----------------------------------------------------------------------------- cast / episodes

def _cast_dir_for(paths, create=False):
    """拿到（必要时创建）共享角色库目录，并写回 project.json 的 cast_dir。"""
    lib = paths.get("cast")
    if lib:
        return lib
    lib = os.path.join(paths["root"], "cast")
    if create:
        os.makedirs(lib, exist_ok=True)
        cfg = load_json(paths["config"], {}) or {}
        cfg["cast_dir"] = "cast"
        save_json(paths["config"], cfg)
        paths["cast"] = lib
        info("已把共享角色库挂到项目内 cast/（project.json cast_dir=cast）")
    return lib


def _copy_char(src_chars, dst_lib, name, force=False):
    s = os.path.join(src_chars, name)
    if not os.path.exists(os.path.join(s, "face_ref.jpg")):
        return False
    d = os.path.join(dst_lib, name)
    if os.path.exists(os.path.join(d, "face_ref.jpg")) and not force:
        info("共享库已有角色 %s，跳过（--force 覆盖）" % name)
        return True
    os.makedirs(d, exist_ok=True)
    for f in ("source.jpg", "face_ref.jpg", "turnaround.jpg", "meta.json"):
        if os.path.exists(os.path.join(s, f)):
            shutil.copy2(os.path.join(s, f), os.path.join(d, f))
    # 设定卡与角度图也要带过去，否则第 2 集得多花一次生图重出
    if os.path.exists(os.path.join(s, "char_card.jpg")):
        shutil.copy2(os.path.join(s, "char_card.jpg"), os.path.join(d, "char_card.jpg"))
    sv = os.path.join(s, "views")
    if os.path.isdir(sv):
        dv = os.path.join(d, "views")
        os.makedirs(dv, exist_ok=True)
        for f in os.listdir(sv):
            if f.lower().endswith((".jpg", ".jpeg", ".png")):
                shutil.copy2(os.path.join(sv, f), os.path.join(dv, f))
    return True


def cmd_cast(args):
    """共享角色库：list / init / push。同一系列多集共用同一张脸。"""
    cfg, paths = load_project(args.dir)
    action = (getattr(args, "action", None) or "list").strip()

    if action == "list":
        names = all_char_names(paths)
        print("本集角色目录: %s" % paths["chars"])
        if paths.get("cast"):
            print("共享角色库:   %s" % paths["cast"])
        else:
            print("共享角色库:   （未挂载，跑一次 cast init 即可启用）")
        lib = os.path.normcase(paths.get("cast") or "\0")
        for n in names:
            d = char_dir(paths, n)
            where = "共享" if os.path.normcase(d).startswith(lib) else "本集"
            print("  %-12s %-4s %s" % (n, where, d))
        if not names:
            print("  （还没有角色）")
        return

    if action == "init":
        info("共享角色库就绪: " + _cast_dir_for(paths, create=True))
        return

    if action == "push":
        lib = _cast_dir_for(paths, create=True)
        if args.name:
            names = [args.name]
        else:
            names = sorted(d for d in os.listdir(paths["chars"])
                           if os.path.isdir(os.path.join(paths["chars"], d)))
        n = 0
        for name in names:
            if _copy_char(paths["chars"], lib, name, force=args.force):
                info("已收入共享库: %s" % name)
                n += 1
        if not n:
            warn("没有可推送的角色（本集 assets/characters/ 为空）")
        return

    die("未知操作: %s（可用 list / init / push）" % action)


def cmd_episode_new(args):
    """在同一系列下新建一集，并自动复用已有角色（同一张脸，不重新生成）。"""
    src = os.path.abspath(args.dir)
    inside = bool(getattr(args, "inside", False))
    if os.path.exists(os.path.join(src, "project.json")):
        if inside:
            # 第 1 集本身就是项目根：新集落在它下面，共享库也建在这里
            series, donor = src, src
        else:
            series, donor = os.path.dirname(src), src
    else:
        series, donor = src, None
        # 系列根下找一集当供体
        if os.path.isdir(series):
            for d in sorted(os.listdir(series)):
                p = os.path.join(series, d)
                if os.path.exists(os.path.join(p, "project.json")):
                    donor = p
                    break

    ep = os.path.join(series, args.name)
    if os.path.exists(os.path.join(ep, "project.json")):
        die("剧集已存在: " + ep)

    os.makedirs(ep, exist_ok=True)
    init_project(ep, args.title or args.name)

    # 建共享库，并把供体那集的角色收进去
    lib = os.path.join(series, "cast")
    os.makedirs(lib, exist_ok=True)
    moved = []
    if donor:
        donor_chars = os.path.join(donor, "assets", "characters")
        if os.path.isdir(donor_chars):
            for n in sorted(os.listdir(donor_chars)):
                if _copy_char(donor_chars, lib, n):
                    moved.append(n)

    cfg = load_json(os.path.join(ep, "project.json"), {}) or {}
    cfg["cast_dir"] = os.path.relpath(lib, ep).replace("\\", "/")
    cfg["series"] = os.path.basename(series.rstrip("/\\"))
    save_json(os.path.join(ep, "project.json"), cfg)

    info("新剧集就绪: " + ep)
    print("  共享角色库: %s" % lib)
    if moved:
        print("  可直接复用角色: " + ", ".join(moved))
        print("  shots.json 里把 char / cast 写成这些名字即可，首帧自动读共享库的脸，不会重生成")
    else:
        print("  还没有可复用角色（第 1 集先做 char-gen / char-add，再跑 cast push）")
    print("  下一步: ac.py story \"%s\" --idea \"...\" --shots 8" % ep)


# ----------------------------------------------------------------------------- props

def do_prop_gen(cfg, paths, name, desc, force=False):
    require_agnes_creds(cfg)
    exe = have_ffmpeg(cfg)
    pdir = paths["props"]
    os.makedirs(pdir, exist_ok=True)
    jpg = os.path.join(pdir, name + ".jpg")
    js = os.path.join(pdir, name + ".json")
    # 幂等：已存在且描述没变就跳过
    if not force and os.path.exists(jpg) and os.path.exists(js):
        try:
            old = json.load(open(js, encoding="utf-8"))
            if old.get("desc") == desc:
                info("道具 %s 已存在，跳过。--force 可重做" % name)
                return
        except Exception:
            pass
    prompt = ("Product-style reference image of a single prop: %s. "
              "Centered, whole object in frame, clean neutral background, soft studio lighting, "
              "photorealistic, high detail, no text, no watermark, no people." % desc)
    info("生成道具 %s ..." % name)
    raw, _ = agnes_image_generate(cfg, prompt, project_paths=paths)
    save_image_bytes(raw, jpg, exe)
    save_json(js, {
        "name": name, "desc": desc, "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    info("道具资产 -> assets/props/%s.jpg" % name)


def cmd_prop_gen(args):
    cfg, paths = load_project(args.dir)
    name = args.name
    desc = args.desc
    if not desc:
        sj = load_json(paths["shots"], {"shots": []})
        for p in sj.get("props", []):
            if p.get("name") == name:
                desc = p.get("desc_en") or p.get("desc")
                break
    if not desc:
        die("缺少 --desc，且 shots.json 的 props 里没有 %s 的描述" % name)
    do_prop_gen(cfg, paths, name, desc, force=getattr(args, "force", False))


# ----------------------------------------------------------------------------- scenes

def _first_sentence(text):
    t = (text or "").strip()
    for sep in (". ", "。", "! ", "? "):
        if sep in t:
            return t.split(sep)[0]
    return t


def scene_key(shot):
    """同一场景只生成一张场景板；镜头只换机位，不换布景。"""
    sc = shot.get("scene") or {}
    sid = (sc.get("id") or "").strip()
    if sid:
        return re.sub(r"[^\w\-]+", "_", sid)
    place = (sc.get("place") or sc.get("slug") or "scene").strip()
    for suffix in ("靠窗桌", "柜台", "门口", "店内", "内景", "外景"):
        place = place.replace(suffix, "")
    place = re.sub(r"[^\w\-]+", "_", place)
    return place or "scene"


def angle_key(shot):
    """场景 × 机位：同一机位共用一张板，板名 shop__table。"""
    ang = (shot.get("angle") or "wide").strip()
    ang = re.sub(r"[^\w\-]+", "_", ang) or "wide"
    return scene_key(shot) + "__" + ang


def plate_for(paths, shot):
    """本镜该用哪张场景板：优先本机位板，缺了退到广角板，再退到场景名老文件。"""
    for name in (angle_key(shot), scene_key(shot) + "__wide", scene_key(shot)):
        p = os.path.join(paths["scenes"], name + ".jpg")
        if os.path.exists(p):
            return p
    return None


def do_scenes(cfg, paths, force=False):
    """按「场景 × 机位」生成空场景板：同一场景共享一套陈设，只换机位。"""
    require_agnes_creds(cfg)
    exe = have_ffmpeg(cfg)
    shots = load_json(paths["shots"])["shots"]
    os.makedirs(paths["scenes"], exist_ok=True)

    groups = {}
    for s in shots:
        if s.get("reuse"):
            continue
        key = scene_key(s)
        ang = (s.get("angle") or "wide").strip() or "wide"
        g = groups.setdefault(key, {"scene": s.get("scene") or {}, "angles": {}})
        g["angles"].setdefault(ang, []).append(s["id"])
        if len((s.get("scene") or {}).get("set") or []) > len(g["scene"].get("set") or []):
            g["scene"] = s.get("scene") or {}

    made = 0
    # 场景风格锚：项目 project.json 的 scene_anchor 优先，其次全局配置，最后才用面馆默认锚
    anchor = scene_anchor(cfg, paths)
    for key, g in groups.items():
        sc = g["scene"]
        setlist = sc.get("set") or scene_set_for(sc.get("place"), sc.get("id"))
        place = sc.get("place") or ""
        time_ = sc.get("time") or "night"
        weather = sc.get("weather") or ""
        light = sc.get("light") or "warm interior light"
        angles = sc.get("angles") or {}
        order = sorted(g["angles"].keys(), key=lambda a: (a != "wide", a))
        wide_dst = os.path.join(paths["scenes"], key + "__wide.jpg")
        for ang in order:
            dst = os.path.join(paths["scenes"], angle_key({"scene": {"id": key}, "angle": ang}) + ".jpg")
            if os.path.exists(dst) and not force:
                info("场景板 %s/%s 已存在，跳过" % (key, ang))
                continue
            desc = angles.get(ang) or DEFAULT_ANGLES.get(ang, ang.replace("-", " "))
            if setlist:
                set_clause = ("Set dressing that MUST all be present and stay identical across every shot "
                              "of this location: %s. " % ", ".join(setlist))
            else:
                # 没写 set 时不要塞任何具体道具：模型会把不属于本片的碗/锅/菜单牌画进来
                set_clause = ("Set dressing must be plain, believable and specific to this location as described; "
                              "do not invent props, food or signage that the description does not imply. ")
            prompt = (
                "Empty location plate, no people at all. %s "
                "%s"
                "Camera: %s. Time: %s, %s. Lighting: %s. Location: %s. "
                "Cinematic realism, 35mm lens, natural depth of field, vertical composition. "
                "ONE single continuous full-frame photograph of ONE room from ONE camera position - "
                "no collage, no grid, no split panels, no borders, no multiple views stacked together. "
                "No people, no hands, no readable text or lettering on signs (blank signboards), no watermark."
                % (anchor, set_clause, desc, time_, weather, light, place)
            )
            # 不拿别的机位板当参考：模型会直接抄那张的机位，导致所有机位长得一样。
            refs = []
            if ang != "wide":
                prompt += (" This is a DIFFERENT camera position of the same shop described above: "
                           "keep every set-dressing item on the list, but do not repeat the entrance "
                           "establishing viewpoint — reframe from the position stated in Camera.")
            info("生成场景板 %s/%s（%d 镜：%s）..." % (key, ang, len(g["angles"][ang]),
                                              "、".join(g["angles"][ang])))
            raw, _ = agnes_image_generate(cfg, prompt, ref_paths=refs, project_paths=paths)
            save_image_bytes(raw, dst, exe)
            made += 1
    n_plates = sum(len(g["angles"]) for g in groups.values())
    info("场景板 %d/%d 张 -> assets/scenes/（%d 个场景）" % (made, n_plates, len(groups)))


def cmd_scene_gen(args):
    cfg, paths = load_project(args.dir)
    do_scenes(cfg, paths, force=args.force)


# ----------------------------------------------------------------------------- frames

FACE_LOCK = (" Keep the face, identity, hairstyle and body proportions exactly as in the reference image; "
             "same person, no morphing, no identity drift.")


def _position_clause(shot):
    """人物站位兜底：提示词没写左右，就按 cast 顺序补一句。

    两人：先出场的在画左三分之一，第二人在画右三分之一，摄影机同在轴线一侧。
    一人：略偏左，视线方向留空间。已经写过 left/right 的不重复加。

    坑（实测）：判断「提示词里已经写了站位」时，不能只认 "on the left"——
    "in the LEFT third" 也算。漏判会让这里再追加一句
    "side by side ... both fully visible from the waist up"，
    和过肩镜（只露肩、半身）设定自相矛盾，模型就会多画出一个完整的人。
    """
    prompt = (shot.get("frame") or {}).get("prompt") or ""
    low = prompt.lower()
    if any(k in low for k in ("left third", "right third", "on the left", "on the right",
                              "left side of frame", "right side of frame",
                              "in the left", "in the right", "left third of", "right third of")):
        return ""
    cast = shot.get("cast") or [shot.get("char")]
    cast = [c for c in cast if c]
    if len(cast) >= 2:
        return (" Composition: %s is placed on the LEFT third of the frame, %s on the RIGHT third, "
                "both at the same distance from the lens, camera on one side of the axis only — "
                "do not cross the line or mirror the staging." % (cast[0], cast[1]))
    if cast:
        return (" Composition: %s is placed slightly LEFT of centre, angled into the frame with empty space "
                "in the direction of their gaze; camera at eye level." % cast[0])
    return ""


def _cast_clause(shot, chars):
    """画面人物白名单 + 服装锁定。

    两个坑（实测）：
    1) 写成 "no other customers / no duplicated person" 这类否定句，反而会把被否定的东西画出来；
       所以这里只做“正面点名 + 明确人数”，空位一律用“是空的”这种陈述句。
    2) 过肩镜头里前景那个人的脸根本看不见，却把它的 face_ref 一起喂进去，模型会照着参考图
       在画面别处再放一个完整的人 —— 于是同一镜里出现两个同一个人（S06 的真实事故）。
       用 shot.faces 只喂“确实露脸”的角色参考图。
    """
    cast = shot.get("cast") or [shot.get("char")]
    # 同一角色可以按镜换装（现代 / 玄幻两套造型）：shot.outfits 优先于角色全局服装
    per_shot = shot.get("outfits") or {}
    parts = []
    for i, name in enumerate(cast, 1):
        c = chars.get(name) or {}
        outfit = ((per_shot.get(name) or "").strip()
                  or (c.get("outfit_en") or "").strip())
        who = (c.get("desc_en") or name).strip()
        if outfit:
            parts.append("%d) %s (%s), wearing exactly: %s" % (i, name, who, outfit))
        else:
            parts.append("%d) %s (%s)" % (i, name, who))
    return (" Headcount in this frame is exactly %d, and these are the only bodies visible: %s. "
            "Every other seat, the aisle behind them, the doorway and the window are empty space. "
            "Their outfits are fixed for the whole film and match the character reference exactly."
            % (len(parts), " ".join(parts)))


def _frame_for_shot(cfg, paths, shot, exe, chars=None, dry=False):
    sid = shot["id"]
    out = os.path.join(paths["frames"], sid + ".jpg")
    fmode = (shot.get("frame") or {}).get("mode", "source")
    cname = shot.get("char") or "hero"
    cdir = char_dir(paths, cname)
    face_ref = os.path.join(cdir, "face_ref.jpg")
    source = os.path.join(cdir, "source.jpg")

    if fmode == "plate":
        # 空镜（无人物）：直接用场景板裁切当首帧
        plate = plate_for(paths, shot)
        if not plate:
            die("%s 的 frame.mode=plate 但没有场景板（先跑 scene-gen）" % sid)
        w, h = RATIO_SIZE.get(cfg["agnes"].get("aspect_ratio", "9:16"), (720, 1280))
        if exe:
            ff_crop_to(w, h, plate, out, exe)
        else:
            shutil.copy2(plate, out)
        info("%s 首帧 = 场景板空镜（无人物）" % sid)
        return out

    if not os.path.exists(face_ref) and fmode != "gen":
        die("找不到角色 %s 的 face_ref.jpg，先运行 char-gen / char-add" % cname)

    if fmode == "source":
        w, h = RATIO_SIZE.get(cfg["agnes"].get("aspect_ratio", "9:16"), (720, 1280))
        if exe:
            ff_crop_to(w, h, source, out, exe)
            info("%s 首帧 = 角色原图裁切" % sid)
        else:
            shutil.copy2(source, out)
            info("%s 首帧 = 角色原图（未裁切）" % sid)
        return out

    prompt = (shot.get("frame") or {}).get("prompt")
    if not prompt:
        die("%s 的 frame.mode=%s 但没有 frame.prompt" % (sid, fmode))
    # 空镜生成模式（gen）：没有人物，不需要锁脸、不需要人物白名单，
    # 但可以喂场景板当参考，用来生成「空镜 + 特定道具」的定制画面。
    is_empty_gen = (fmode == "gen")
    if not is_empty_gen:
        if "identity drift" not in prompt.lower():
            prompt += FACE_LOCK
        if "east asian" not in prompt.lower():
            prompt += EAST_ASIAN
    # 场景风格锚 + 人物白名单 + 服装锁
    prompt += " " + scene_anchor(cfg, paths)
    if not is_empty_gen:
        prompt += _cast_clause(shot, chars or {})
        prompt += _position_clause(shot)
    # 室内镜头不要飘到街上（模型很容易把“面馆”画成灯笼街）
    if (shot.get("scene") or {}).get("interior", True):
        # 注意：这里不能写死 "the shop"——公寓、卧室这种内景会被推成店铺。
        where = ((shot.get("scene") or {}).get("place") or "").strip() or "this interior"
        prompt += (" This frame is INSIDE (%s): no street, no sidewalk, no outdoor view as the main "
                   "background, no hanging lanterns, no shop sign, no passers-by." % where)

    # shot.faces：只把“画面里真露脸”的角色参考图喂进去。过肩镜头前景那人背对镜头，
    # 喂了他的脸就会被复制成第二个人（实测事故），所以允许按镜收窄。
    face_cast = shot.get("faces") or shot.get("cast") or [cname]
    ang = (shot.get("angle") or "").strip()
    refs = []
    if not is_empty_gen:
        for n in face_cast:
            # 按机位取对应角度的参考图：侧面机位喂侧脸、背面机位喂背影，
            # 没裁出来或机位不明确就回落到 face_ref.jpg（最稳）。
            p = view_for_angle(paths, n, ang)
            if p and os.path.exists(p):
                refs.append(p)
        if not refs:
            refs = [face_ref]

    # shot.no_plate=true：极近景时不给场景板。板是中景，模型会照抄它的构图，压不住景别。
    plate = None if shot.get("no_plate") else plate_for(paths, shot)
    if plate:
        refs.append(plate)
        if is_empty_gen:
            prompt += (" The location is identical to the reference location plate: same walls, "
                       "counter, furniture, set dressing, props and lighting; only the camera "
                       "position and framing change. The plate is empty of people — this frame "
                       "is also empty of people, but the specific objects named above are "
                       "now present.")
        else:
            prompt += (" The location is identical to the reference location plate: same walls, counter, "
                       "furniture, set dressing, props and lighting; only the camera position and framing "
                       "change. Keep every character exactly as in the character references.")
    else:
        if shot.get("no_plate"):
            info("%s 按 no_plate 跳过场景板（极近景，避免照抄中景构图）" % sid)
        else:
            warn("%s 没有场景板（先跑 scene-gen），首帧只锁人物" % sid)
    if dry:
        print("\n===== %s 首帧最终提示词（%d 字）=====" % (sid, len(prompt)))
        print(prompt)
        print("----- 参考图 %d 张 -----" % len(refs))
        for r in refs:
            print("  " + r)
        return None

    require_agnes_creds(cfg)
    n_face = len([r for r in refs
                  if os.path.basename(r) == "face_ref.jpg"
                  or os.path.basename(os.path.dirname(r)) == "views"])
    # 机位决定了喂哪张角度图，日志要能看出来
    used_view = ""
    for r in refs:
        if os.path.basename(os.path.dirname(r)) == "views":
            used_view = os.path.splitext(os.path.basename(r))[0]
            break
    info("%s 生成首帧（机位 %s，参考图 %d 张：人脸 %d%s + 场景 %d）"
         % (sid, shot.get("angle") or "wide", len(refs), n_face,
            ("/" + used_view) if used_view else "", 1 if plate else 0))
    raw, _ = agnes_image_generate(cfg, prompt, ref_paths=refs, project_paths=paths)
    save_image_bytes(raw, out, exe)
    info("%s 首帧 -> frames/%s.jpg" % (sid, sid))
    return out


def do_frames(cfg, paths, only=None, force=False, dry=False):
    exe = have_ffmpeg(cfg)
    if not exe:
        warn("未找到 ffmpeg：首帧不做裁切；assemble 阶段仍需要 ffmpeg")
    story = load_json(paths["shots"])
    shots = story["shots"]
    if not shots:
        die("script/shots.json 里没有镜头")
    chars = {c.get("name"): c for c in (story.get("characters") or [])}
    only_set = set(only.split(",")) if only else None
    for shot in shots:
        if only_set and shot["id"] not in only_set:
            continue
        if shot.get("reuse"):
            # 回忆镜头直接用旧集片段剪（见 recall 命令），不需要首帧
            continue
        target = os.path.join(paths["frames"], shot["id"] + ".jpg")
        if os.path.exists(target) and not force:
            info("%s 跳过：首帧已存在（--force 覆盖）" % shot["id"])
            continue
        if (shot.get("link") or "").strip().lower() in ("prev", "tail", "prev-tail", "prev_tail"):
            i = shots.index(shot)
            prev_clip = os.path.join(paths["clips"], shots[i - 1]["id"] + ".mp4") if i > 0 else ""
            if prev_clip and os.path.exists(prev_clip) and exe:
                extract_tail_frame(prev_clip, target, exe)
                info("%s 首帧 = %s 尾帧（接力）" % (shot["id"], os.path.basename(prev_clip)))
                continue
            info("%s 接力镜头：上一镜还没出片，等视频阶段自动取尾帧" % shot["id"])
            continue
        _frame_for_shot(cfg, paths, shot, exe, chars, dry=dry)


def cmd_frame(args):
    cfg, paths = load_project(args.dir)
    do_frames(cfg, paths, args.only, args.force, dry=getattr(args, "dry_run", False))


# ----------------------------------------------------------------------------- video

def _clamp_seconds(v):
    try:
        v = int(round(float(v)))
    except Exception:
        v = 8
    return max(4, min(12, v))


def extract_tail_frame(clip, dst, exe, back=0.4):
    """取上一段视频的最后一帧，作为下一段的首帧（接力拍摄）。"""
    ff_run(exe, ["-y", "-loglevel", "error", "-sseof", "-%.2f" % back, "-i", clip,
                 "-frames:v", "1", "-q:v", "2", dst])


def _submit_one(cfg, task, force_tier=None, force_max_attempts=None):
    a = cfg["agnes"]
    sid = task["shot"]
    prev = task.get("link_prev")
    if prev and os.path.exists(prev):
        exe = have_ffmpeg(cfg)
        if exe:
            extract_tail_frame(prev, task["frame"], exe)
            info("%s 首帧 = %s 的尾帧（接力，不重新构图）" % (sid, os.path.basename(prev)))
    first = frame_source(cfg, task["frame"])
    last = None
    if task.get("tail"):
        last = frame_source(cfg, task["tail"])
        info("%s 尾帧 = %s（落点钉在下一镜的构图上）" % (sid, os.path.basename(task["tail"])))
    if force_tier is not None:
        tiers = video_tier_list(cfg)
        tn = tiers[force_tier]["name"] if 0 <= force_tier < len(tiers) else "?"
        info("%s 提交 Agnes（%ss, %s, 720P）→ %s ..." % (sid, task["seconds"], a.get("aspect_ratio", "9:16"), tn))
    else:
        info("%s 提交 Agnes（%ss, %s, 720P）..." % (sid, task["seconds"], a.get("aspect_ratio", "9:16")))
    d = agnes_video_submit(cfg, task["prompt"], task["seconds"],
                           a.get("aspect_ratio", "9:16"),
                           first_frame=first, last_frame=last, seed=task.get("seed"),
                           force_tier=force_tier, force_max_attempts=force_max_attempts)
    vid = d.get("video_id") or d.get("id")
    info("%s 已入队 video_id=%s" % (sid, vid))
    return {"shot": sid, "video_id": vid, "seconds": task["seconds"],
            "clip": task["clip"], "status": "queued", "progress": None,
            "tier": d.get("_tier")}


def do_videos(cfg, paths, only=None, force=False, wait=False, allow_partial=False):
    require_video_agnes_creds(cfg)
    a = cfg["agnes"]
    shots = load_json(paths["shots"])["shots"]
    if not shots:
        die("script/shots.json 里没有镜头")
    only_set = set(only.split(",")) if only else None

    tasks = []
    for idx, shot in enumerate(shots):
        if only_set and shot["id"] not in only_set:
            continue
        if shot.get("reuse"):
            continue
        sid = shot["id"]
        frame_path = os.path.join(paths["frames"], sid + ".jpg")
        link_now = (shot.get("link") or "").strip().lower()
        linked = link_now in ("prev", "tail", "prev-tail", "prev_tail") and idx > 0
        if not os.path.exists(frame_path) and not linked:
            info("%s 跳过：没有首帧图（先跑 frame）" % sid)
            continue
        clip_path = os.path.join(paths["clips"], sid + ".mp4")
        if os.path.exists(clip_path) and not force:
            info("%s 跳过：clips/%s.mp4 已存在（--force 覆盖）" % (sid, sid))
            continue
        prompt = (shot.get("video_prompt") or "").strip()
        if not prompt:
            die("%s 缺 video_prompt" % sid)
        link = (shot.get("link") or "").strip().lower()
        prev_clip = None
        if link in ("prev", "tail", "prev-tail", "prev_tail") and idx > 0:
            prev_clip = os.path.join(paths["clips"], shots[idx - 1]["id"] + ".mp4")

        # 尾帧桥接：把"下一镜的首帧"钉成本镜的落点。
        # 好处是剪辑点上 A 的最后一帧 == B 的第一帧，拼接处零跳变；
        # 而且每镜两端都锚在已生成的首帧上，不像"尾帧接力"那样一镜一镜往下漂。
        tail_spec = shot.get("tail_frame")
        tail_path = None
        if tail_spec:
            key = str(tail_spec).strip().lower()
            if key == "next":
                if idx + 1 < len(shots):
                    tail_path = os.path.join(paths["frames"], shots[idx + 1]["id"] + ".jpg")
                    key = shots[idx + 1]["id"]
            elif key not in ("", "false", "none"):
                tail_path = os.path.join(paths["frames"], str(tail_spec).strip() + ".jpg")
            if tail_path and not os.path.exists(tail_path):
                warn("%s 的尾帧 %s 还没生成（tail_frame=%s），本次不挂尾帧"
                     % (sid, os.path.basename(tail_path), tail_spec))
                tail_path = None
        tasks.append({
            "shot": sid,
            "link_prev": prev_clip,
            "tail": tail_path,
            "frame": frame_path,
            "clip": clip_path,
            "prompt": prompt,
            "seconds": _clamp_seconds(shot.get("duration") or a.get("seconds", 8)),
            "seed": shot.get("seed"),
        })

    if not tasks:
        info("没有需要提交的镜头")
        return []
    if not wait:
        slots = video_jobs(cfg)
        jobs = []
        runnable = [t for t in tasks if not t.get("link_prev") or os.path.exists(t["link_prev"])]
        try:
            for t in runnable[:slots]:
                jobs.append(_submit_one(cfg, t))
        except PaidTierNeedsConfirm as e:
            die(str(e))
        except SubmitError as e:
            die("Agnes 队列已满，提交失败：%s。稍后重跑，或用 --wait 让脚本排队等待" % str(e)[:200])
        done_ids = {j["shot"] for j in jobs}
        # 注意：这里必须跟已有的 _pending.json 合并。分几批 --only 提交时如果直接覆盖，
        # 前一批「待补位」的镜头就永久丢了（fetch 只会跑最后一批，然后清空文件）。
        pend_path = os.path.join(paths["clips"], "_pending.json")
        old = load_json(pend_path, {}) or {}
        keep_jobs = [j for j in (old.get("jobs") or [])
                     if j.get("status") != "completed" and j.get("shot") not in done_ids]
        keep_queue = [t for t in (old.get("queue") or [])
                      if t["shot"] not in done_ids
                      and t["shot"] not in {j["shot"] for j in keep_jobs}]
        save_json(pend_path,
                  {"jobs": keep_jobs + jobs,
                   "queue": keep_queue + [t for t in tasks if t["shot"] not in done_ids]})
        info("已提交 %d 个任务（并发上限 %d），其余 %d 个待补位。用 fetch 继续"
             % (len(jobs), slots, len(tasks) - len(jobs)))
        return jobs

    solved = _run_scheduler(cfg, paths, [], tasks)
    bad = [j for j in solved if j.get("status") == "failed"]
    if bad and not allow_partial:
        sys.exit(2)
    if bad:
        warn("有 %d 个镜头没排上队，先合成已有片段（可之后单独补跑这些镜）" % len(bad))
    return solved


def _run_scheduler(cfg, paths, jobs, queue):
    """Agnes 并发调度：最多 jobs 路同时生成，全局每 poll_interval 秒只查一个任务。"""
    a = cfg["agnes"]
    slots = video_jobs(cfg)
    interval = video_poll(cfg)
    deadline = time.time() + float(a.get("timeout", 7200))
    inflight = [j for j in (jobs or []) if j.get("status") != "completed"]
    queue = list(queue or [])
    finished = [j for j in (jobs or []) if j.get("status") == "completed"]
    last_poll = 0.0
    next_fill = 0.0
    rounds = max(1, int(a.get("submit_rounds", 10)))

    # ---- 分档并行配额 ----
    # video.tier_slots = {"0": 3, "2": 3}  表示第 1 档（免费）开 3 路、第 3 档（付费）再开 3 路，
    # 两组同时跑，总并发 = 各档配额之和。空缺或没配就退回全局 slots。
    vcfg = cfg.get("video") or {}
    tier_slots = vcfg.get("tier_slots") or {}
    use_quota = bool(tier_slots) and bool(vcfg.get("paid_requires_confirm") is False)
    # 每档当前占用的槽位数
    tier_used = {}
    # 档位轮转指针：分档配额模式下从哪一档开始试
    tier_rr = 0
    # 各档限流冷却：某档 429 后，冷却期内不再投喂它（速率限制要等窗口恢复）
    tier_cooldown = {}

    def _tier_ready(idx, now):
        until = tier_cooldown.get(idx)
        return not (until and now < until)

    def _tier_cap(idx):
        """这一档能占几个槽位；没配就返回 0（表示不参与配额）。"""
        for k, v in tier_slots.items():
            if int(k) == int(idx):
                return max(0, int(v))
        return 0

    def _pick_task_for_tier(idx):
        """给指定档位挑一个还没分配过档位的任务。"""
        for t in queue:
            if t.get("assigned_tier") is None:
                if t.get("link_prev") and not os.path.exists(t["link_prev"]):
                    continue
                t["assigned_tier"] = int(idx)
                return t
        return None

    while inflight or queue:
        # 补位：有空槽就提交下一个；队列满时等一会儿重新排队，不丢任务
        if queue and len(inflight) < slots:
            wait = next_fill - time.time()
            if wait > 0:
                time.sleep(min(wait, max(0.0, deadline - time.time())))
            while queue and len(inflight) < slots:
                runnable = [t for t in queue if not t.get("link_prev") or os.path.exists(t["link_prev"])]
                if not runnable:
                    break

                # ---- 分档配额模式：按各档配额分别投喂 ----
                if use_quota:
                    # 从上次成功的档开始试；失败时不推进指针，下一轮自然换到另一档，
                    # 避免总是先撞同一个限流档（限流是速率问题，不是队列满）
                    tl = video_tier_list(cfg)
                    n_tier = len(tl)
                    order = [(tier_rr + k) % n_tier for k in range(n_tier)] if n_tier else []
                    placed = False
                    for tidx in order:
                        cap = _tier_cap(tidx)
                        if cap <= 0:
                            continue
                        if tier_used.get(tidx, 0) >= cap:
                            continue
                        # 限流冷却中的档位直接跳过，别再拿请求去撞墙
                        if not _tier_ready(tidx, time.time()):
                            continue
                        task = _pick_task_for_tier(tidx)
                        if task is None:
                            continue
                        queue.remove(task)
                        try:
                            # force_max_attempts=1 → 这一档只试一次就换下一档，
                            # 不在限流退避里把整个调度线程堵死
                            inflight.append(_submit_one(cfg, task, force_tier=tidx,
                                                        force_max_attempts=1))
                            tier_used[tidx] = tier_used.get(tidx, 0) + 1
                            tier_rr = tidx          # 记住这一档可用，下一轮先用它
                        except SubmitError as e:
                            # 这一档排不上：任务放回队列，交给下一档或下一轮
                            task["assigned_tier"] = None
                            queue.append(task)
                            # tier_rr 不动 → 下一轮从别档开始
                            if "429" in str(e):
                                # 速率限制：冷却 3 分钟，别再拿请求去撞墙
                                tier_cooldown[tidx] = time.time() + 180
                                info("  %s 档被限流，冷却 180s" % tl[tidx]["name"])
                            info("  %s 档排不上（%s），换下一档"
                                 % (tl[tidx]["name"], str(e)[:70]))
                        placed = True
                        break
                    if placed:
                        continue
                    # 所有配额档都在冷却 → 等最早的冷却结束，别空转刷请求
                    if tier_cooldown:
                        soonest = min(tier_cooldown.values())
                        wait_cd = max(5.0, min(180.0, soonest - time.time()))
                        info("  各档都在限流冷却，%.0fs 后再试" % wait_cd)
                        next_fill = max(next_fill, time.time() + wait_cd)
                        break
                    # 没有冷却信息 → 回落到普通降级链
                    task = runnable[0]
                    queue.remove(task)
                else:
                    task = runnable[0]
                    queue.remove(task)

                try:
                    inflight.append(_submit_one(cfg, task))
                except PaidTierNeedsConfirm as e:
                    # 免费通道都排不上，要用付费档 —— 按策略停下来等人工确认
                    save_json(os.path.join(paths["clips"], "_pending.json"),
                              {"jobs": inflight, "queue": queue})
                    die(str(e))
                except SubmitError as e:
                    tries = int(task.get("tries", 0)) + 1
                    task["tries"] = tries
                    if tries >= rounds:
                        info("  %s 提交 %d 轮仍失败，放弃：%s"
                             % (task["shot"], tries, str(e)[:160]))
                        finished.append({"shot": task["shot"], "status": "failed",
                                         "clip": task["clip"]})
                    else:
                        # 429 是速率限制：退避要长得多，别继续撞墙
                        is_rl = "429" in str(e)
                        wait_s = 120 if is_rl else 45
                        info("  %s 提交 %d 轮仍失败（%s），%ds 后重新排队（第 %d/%d 轮）"
                             % (task["shot"], tries,
                                "速率限制" if is_rl else "队列满", wait_s, tries, rounds))
                        queue.append(task)
                        next_fill = time.time() + wait_s
                        break

        if not inflight:
            continue

        # 全局节流：不管几路任务，一律每 interval 秒查一次
        now = time.time()
        if now - last_poll < interval:
            time.sleep(min(interval - (now - last_poll), max(0.0, deadline - now)))
        if time.time() > deadline:
            save_json(os.path.join(paths["clips"], "_pending.json"),
                      {"jobs": inflight, "queue": queue})
            die("等待超时（%ds）。未完成: %s。已写入 clips/_pending.json，可用 fetch 续查"
                % (int(a.get("timeout", 7200)), ", ".join(j["shot"] for j in inflight)))

        job = inflight.pop(0)   # 轮转，一次只查一个
        try:
            d = agnes_video_status(cfg, job["video_id"], job.get("tier"))
            last_poll = time.time()
        except urllib.error.HTTPError as e:
            last_poll = time.time()
            if e.code == 429:
                info("  接口限流（429），按 %ds 节奏继续" % int(interval))
            else:
                info("  %s 查询失败: HTTP %s" % (job["shot"], e.code))
            inflight.append(job)
            continue
        except Exception as e:
            last_poll = time.time()
            info("  %s 查询失败: %s" % (job["shot"], str(e)[:160]))
            inflight.append(job)
            continue

        st = d.get("status")
        pg = d.get("progress")
        if st == "completed":
            url = d.get("url")
            if not url:
                die("%s 已完成但没有 url 字段" % job["shot"])
            size = download_file(url, job["clip"])
            info("  %s 完成 -> clips/%s.mp4 (%.1f MB)" % (job["shot"], job["shot"], size / 1e6))
            job["status"] = "completed"
            finished.append(job)
            # 释放该档的槽位配额，让这一档能继续投喂新任务
            tidx = job.get("tier")
            if tidx is not None and tier_used.get(tidx, 0) > 0:
                tier_used[tidx] -= 1
        elif st == "failed":
            err = d.get("error") or d.get("message") or json.dumps(d, ensure_ascii=False)[:300]
            info("  %s 失败: %s" % (job["shot"], str(err)[:300]))
            job["status"] = "failed"
            finished.append(job)
            tidx = job.get("tier")
            if tidx is not None and tier_used.get(tidx, 0) > 0:
                tier_used[tidx] -= 1
        else:
            if pg != job["progress"]:
                job["progress"] = pg
                info("  %s %s %s" % (job["shot"], st or "pending",
                                     ("%s%%" % pg) if pg is not None else ""))
            inflight.append(job)

    ok = [j for j in finished if j.get("status") == "completed"]
    bad = [j for j in finished if j.get("status") == "failed"]
    info("视频完成 %d 个%s" % (len(ok), ("，失败: " + ", ".join(j["shot"] for j in bad)) if bad else ""))
    return finished


def cmd_fetch(args):
    """续查/续提任务（读 clips/_pending.json），不会重复提交已入队的任务。"""
    cfg, paths = load_project(args.dir)
    p = os.path.join(paths["clips"], "_pending.json")
    if not os.path.exists(p):
        die("没有待续查任务（clips/_pending.json 不存在）")
    raw = load_json(p)
    if isinstance(raw, list):
        jobs, queue = raw, []
    else:
        jobs, queue = raw.get("jobs", []), raw.get("queue", [])
    for j in jobs:
        if j.get("clip") and os.path.exists(j["clip"]):
            j["status"] = "completed"
    _run_scheduler(cfg, paths, jobs, queue)
    os.remove(p)
    info("全部完成，已清理 _pending.json")


def cmd_video(args):
    cfg, paths = load_project(args.dir)
    if getattr(args, "allow_paid", False):
        # 本次任务临时放行付费档（不写回全局配置）
        cfg.setdefault("video", {})["paid_requires_confirm"] = False
        info("已放行付费档（仅本次任务）")
    do_videos(cfg, paths, args.only, args.force, args.wait)


# ----------------------------------------------------------------------------- recall (复用旧集当回忆)

# 回忆调色：不是为了好看，是为了让观众知道"这段不是现在"。
RECALL_GRADES = {
    "warm": "eq=saturation=0.66:contrast=0.97:brightness=0.03,"
            "colorbalance=rs=0.04:gs=0.01:bs=-0.03",
    "cold": "eq=saturation=0.42:contrast=1.02:brightness=-0.015,"
            "colorbalance=rs=-0.03:bs=0.06",
    "neutral": "eq=saturation=0.55:contrast=0.98",
}


def do_recall(cfg, paths, only=None, force=False, dry=False):
    """把别的剧集（通常是第 1 集）的片段剪成"回忆"放进本集 clips/。

    镜头表里这样写，就不用调 Agnes、不花额度：
        "reuse": {"from": "../clips/S01.mp4", "in": 0.0, "dur": 5.0,
                  "speed": 0.85, "grade": "warm"}
    - from：相对本集根目录（也支持绝对路径）
    - in/dur：源片段的入点与**成片要的长度**（秒）
    - speed：<1 放慢（回忆感），>1 加快，默认 1
    - grade：warm / cold / neutral，叠柔光、颗粒、暗角，原声一律去掉
    """
    exe = have_ffmpeg(cfg)
    if not exe:
        die("找不到 ffmpeg，回忆片段需要它来剪")
    shots = load_json(paths["shots"])["shots"]
    only_set = set(only.split(",")) if only else None
    w, h = RATIO_SIZE.get(cfg["agnes"].get("aspect_ratio", "9:16"), (704, 1280))
    made, skipped = 0, 0
    for shot in shots:
        r = shot.get("reuse") or {}
        if not r:
            continue
        sid = shot["id"]
        if only_set and sid not in only_set:
            continue
        dst = os.path.join(paths["clips"], sid + ".mp4")
        if os.path.exists(dst) and not force:
            skipped += 1
            continue
        src = r.get("from") or ""
        if not os.path.isabs(src):
            src = os.path.normpath(os.path.join(paths["root"], src))
        if not os.path.exists(src):
            warn("%s 复用源不存在: %s" % (sid, src))
            continue
        t_in = max(0.0, float(r.get("in", 0.0)))
        out_dur = float(r.get("dur") or shot.get("duration") or 6.0)
        speed = float(r.get("speed") or 1.0)
        if speed <= 0:
            speed = 1.0
        src_dur = out_dur * speed
        grade = RECALL_GRADES.get((r.get("grade") or "warm").strip(), RECALL_GRADES["warm"])
        chain = ["scale=%d:%d:force_original_aspect_ratio=increase" % (w, h),
                 "crop=%d:%d" % (w, h), "setsar=1"]
        if abs(speed - 1.0) > 1e-3:
            chain.append("setpts=PTS/%.4f" % speed)
        chain += ["fps=24", grade, "gblur=sigma=0.35",
                  "noise=alls=5:allf=t", "vignette=PI/5", "format=yuv420p"]
        cmd = ["-y", "-loglevel", "error",
               "-ss", "%.3f" % t_in, "-t", "%.3f" % src_dur, "-i", src,
               "-an", "-vf", ",".join(chain),
               "-c:v", "libx264", "-preset", "medium", "-crf", "17",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", dst]
        if dry:
            print("%s  <- %s [%.2f, %.2f] x%.2f  %s" % (sid, os.path.basename(src), t_in,
                                                        t_in + src_dur, speed,
                                                        (r.get("grade") or "warm")))
            continue
        try:
            ff_run(exe, cmd)
        except SystemExit:
            warn("%s 回忆片段剪失败" % sid)
            continue
        got = ff_duration(dst, exe)
        if got is None or got < out_dur * 0.8:
            warn("%s 只有 %.2fs（想要 %.2fs），源片段可能不够长" % (sid, got or 0, out_dur))
        else:
            info("%s 回忆片段 %.2fs（源 %s 从 %.2fs 起%s）"
                 % (sid, got, os.path.basename(src), t_in,
                    "" if abs(speed - 1) < 1e-3 else "，%.2f 倍速" % speed))
        made += 1
    info("回忆片段：新剪 %d 条，跳过 %d 条 -> clips/" % (made, skipped))


def cmd_recall(args):
    cfg, paths = load_project(args.dir)
    do_recall(cfg, paths, getattr(args, "only", None),
              getattr(args, "force", False), getattr(args, "dry_run", False))


# ----------------------------------------------------------------------------- voice (edge-tts)

def have_edge_tts():
    try:
        import edge_tts  # noqa: F401
        return True
    except Exception:
        return False


def _spk_conf(cfg, speaker):
    """取某个说话人的独立 TTS 配置（可以按角色换 provider / 音色 / 语速）。

    以前 voices 下每个角色只能写一个音色名，provider 是全局的，
    双人对白就没法做到"男的走豆包、女的走 edge"。现在允许写成对象：
        "girl": {"provider": "edge", "voice": "zh-CN-XiaoyiNeural", "rate": "-12%"}
    写字符串的旧配置继续兼容。
    """
    v = cfg.get("voices") or {}
    c = v.get(speaker)
    if speaker == "VO" and not isinstance(c, dict):
        c = v.get("VO")
    return c if isinstance(c, dict) else {}


def _voice_for(cfg, speaker):
    v = cfg.get("voices") or {}
    if speaker == "VO":
        c = v.get("VO") or v.get("default")
    else:
        c = v.get(speaker) or v.get("default")
    if isinstance(c, dict):
        # 角色配置写成对象时，voice 可能故意留空（走豆包靠 style 描述音色）。
        # 这时日志如果回落到 voices.default 会显示成别人的音色，非常容易误判，所以标出来。
        if c.get("voice"):
            return c.get("voice")
        if c.get("style"):
            return "doubao:%s" % c["style"][:12]
        return v.get("default") or "zh-CN-XiaoxiaoNeural"
    return c or "zh-CN-XiaoxiaoNeural"


def _doubao_tts(cfg, txt, dst, rate_pct=0, style=None, tail=None, model=None):
    """豆包 Seed-Audio 语音合成（https://openspeech.bytedance.com/api/v3/tts/create）。

    走 text_prompt：「角色描述 + 台词」一句自然语言，模型自己决定情绪和停顿，
    比 edge-tts 的逐字朗读强一个量级。返回 (ok, err)。

    style / tail / model 可按角色覆盖（双人对白里男声走豆包、女声走 edge 时用得上）。
    """
    vcfg = cfg.get("voices") or {}
    db = vcfg.get("doubao") or {}
    key = (db.get("key") or "").strip()
    if not key:
        return False, "未配置 voices.doubao.key（豆包语音合成 API Key）"
    style = (style if style is not None else (db.get("style") or "")).strip()
    tail = (tail if tail is not None else (db.get("tail") or "")).strip()
    prompt = "%s“%s”" % (style, txt)
    if tail:
        prompt += "。" + tail
    body = {
        "model": model or db.get("model") or "seed-audio-1.0",
        "text_prompt": prompt,
        "audio_config": {
            "format": "mp3",
            "sample_rate": 48000,
            "pitch_rate": int(db.get("pitch_rate") or 0),
            "speech_rate": int(rate_pct),
            "loudness_rate": int(db.get("loudness_rate") or 0),
        },
        "watermark": {},
    }
    url = db.get("endpoint") or "https://openspeech.bytedance.com/api/v3/tts/create"
    attempts = int(db.get("attempts") or 3)
    last = ""
    for i in range(attempts):
        try:
            req = urllib.request.Request(
                url, data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json", "X-Api-Key": key})
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.loads(r.read().decode("utf-8"))
            raw = base64.b64decode(d.get("audio") or "")
            if not raw:
                last = "返回里没有 audio 字段：%s" % json.dumps(d, ensure_ascii=False)[:200]
            else:
                with open(dst, "wb") as f:
                    f.write(raw)
                return True, ""
        except urllib.error.HTTPError as e:
            last = "HTTP %s: %s" % (e.code, e.read().decode("utf-8", "ignore")[:200])
            if e.code in (400, 401, 403):
                break
        except Exception as e:
            last = str(e)[:200]
        time.sleep(min(20, 3 * (i + 1)))
    return False, last


def _trim_pauses(exe, src, dst, keep=0.45):
    """把豆包生成的长停顿压到 keep 秒，其余音频原样保留。

    豆包爱插 1.8~2.3 秒的戏，单句独白听着舒服，塞镜头里就超长了。
    """
    try:
        ff_run(exe, ["-y", "-loglevel", "error", "-i", src, "-af",
                     "silenceremove=start_periods=0:start_silence=0.08:"
                     "stop_periods=-1:stop_duration=%.2f:stop_silence=%.2f:"
                     "stop_threshold=-38dB" % (keep, keep),
                     "-ar", "44100", "-ac", "1", "-b:a", "192k", dst])
        return True
    except SystemExit:
        return False


def _tts_one(cfg, voice, txt, dst, rate_pct=None, pitch=None, spk=None):
    """跑一次 TTS。provider=edge（默认）走 edge-tts，provider=doubao 走豆包。

    spk：该说话人的独立配置（dict）。里面写了 provider 就按它走，
    这样一集里可以男声豆包、女声 edge。
    """
    vcfg = cfg.get("voices") or {}
    spk = spk or {}
    provider = (spk.get("provider") or vcfg.get("provider") or "edge")
    if provider == "doubao":
        # 语速：调用方已经算好的 rate_pct 优先；没给就用该角色的 rate / 全局 rate
        if rate_pct is None:
            raw = spk.get("rate", vcfg.get("rate")) or "0"
            rate_pct = int(str(raw).replace("%", "") or 0)
        db = vcfg.get("doubao") or {}
        return _doubao_tts(cfg, txt, dst, rate_pct=rate_pct,
                           style=(spk.get("style") if spk.get("style") is not None
                                  else db.get("style")),
                           tail=(spk.get("tail") if spk.get("tail") is not None
                                 else db.get("tail")),
                           model=spk.get("model"))

    # ---- edge-tts：rate/pitch 必须用 = 连接（+/- 开头会被 argparse 当选项）
    cmd = [sys.executable, "-m", "edge_tts", "--voice", voice,
           "--text", txt, "--write-media", dst]
    slow = 0
    if rate_pct is not None:
        # edge-tts 的语速解析要求 "+N%" / "-N%"，但 N 为负时微软端会返回
        # "No audio was received"（负语速在 SSML 里是非法值）。
        # 降速改用 pitch 补偿：语速夹到 0%，靠降调实现"念得更慢更沉"的效果。
        pct = int(rate_pct)
        if pct < 0:
            slow = -pct               # 降速幅度记下来，用 pitch 补
            pct = 0
        r = "%+d%%" % pct
    else:
        r = spk.get("rate", vcfg.get("rate"))
        # 配置里直接写了负语速（如 "-6%"）也要走降调补偿，不能直接丢给 edge-tts
        if r and str(r).startswith("-"):
            try:
                slow = abs(int(str(r).replace("%", "").replace("-", "") or 0))
                r = "+0%%"
            except ValueError:
                slow = 0
    if r:
        cmd += ["--rate=%s" % str(r)]
    pt = pitch if pitch is not None else spk.get("pitch", vcfg.get("pitch"))
    if slow:
        # 降速对应的降调：每 10% 降速约降 2Hz 音高
        base_pt = 0
        if pt:
            try:
                base_pt = int(str(pt).replace("%", "").replace("+", "").replace("Hz", "") or 0)
            except ValueError:
                base_pt = 0
        pt = "%+dHz" % (base_pt - 2 * (slow // 10))
    if pt:
        cmd += ["--pitch=%s" % str(pt)]
    # 注意：voices.volume 是混音时的增益倍数（如 1.6），不是 edge-tts 的 "+10%"。
    # 要给 edge-tts 调音量得写 voices.tts_volume = "+10%"，别拿 volume 直接传。
    tv = spk.get("tts_volume", vcfg.get("tts_volume"))
    if tv and "%" in str(tv):
        cmd += ["--volume=%s" % str(tv)]
    pr = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if pr.returncode != 0 or not os.path.exists(dst):
        err = pr.stderr.decode("utf-8", "ignore")[-200:]
        # 回退：带 rate/pitch 失败时，去掉这两个参数再试一次（至少要出人声）
        if any(a.startswith("--rate") or a.startswith("--pitch") for a in cmd):
            cmd2 = [a for a in cmd if not a.startswith("--rate") and not a.startswith("--pitch")]
            pr2 = subprocess.run(cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if pr2.returncode == 0 and os.path.exists(dst):
                return True, ""
            err = err + " | 回退后仍失败: " + pr2.stderr.decode("utf-8", "ignore")[-120:]
        return False, err
    return True, ""


def _pct(x):
    return int(round(x))


def do_voice(cfg, paths, force=False, only=None, fit=True):
    """把每一镜的 line 用 edge-tts 念成 audio/vo/<sid>.mp3，按角色分配音色。

    only：只生成这些镜号（集合）；None = 全部。
    fit：合成后如果比该镜时长还长，自动提语速重合成（最多提到 base+16%），
         保证配音一定塞得进画面，不用回头重剪。
    """
    shots = load_json(paths["shots"])["shots"]
    lines = [s for s in shots if (s.get("line") or "").strip()]
    if only:
        lines = [s for s in lines if s["id"] in only]
    if not lines:
        info("没有台词，跳过配音")
        return []
    if not have_edge_tts():
        warn("未安装 edge-tts，跳过配音（pip install edge-tts）")
        return []
    vcfg = cfg.get("voices") or {}
    exe = have_ffmpeg(cfg)
    vo_dir = os.path.join(paths["audio"], "vo")
    os.makedirs(vo_dir, exist_ok=True)
    stored = load_json(paths["shots"], {"shots": []})
    char_voice = {c.get("name"): c.get("voice") for c in stored.get("characters", []) if c.get("voice")}
    made = []
    for s in lines:
        sid = s["id"]
        dst = os.path.join(vo_dir, sid + ".mp3")
        if os.path.exists(dst) and not force:
            made.append(dst)
            continue
        speaker = s.get("speaker") or s.get("char")
        parts = [(speaker, s["line"])]
        for x in (s.get("extra_lines") or []):
            if (x.get("line") or "").strip():
                parts.append((x.get("speaker") or speaker, x["line"]))

        # 每个说话人可能有自己的 provider / 语速（男声豆包、女声 edge 这类）
        spk_confs = {spk: _spk_conf(cfg, spk) for spk, _ in parts}
        is_doubao = ((vcfg.get("provider") or "edge") == "doubao"
                     or any((c.get("provider") or "") == "doubao" for c in spk_confs.values()))
        if is_doubao:
            base_rate = float((vcfg.get("doubao") or {}).get("speech_rate") or 0)
            step, max_rate = 8.0, base_rate + 48
        else:
            base_rate = float(str(vcfg.get("rate") or "+0%").replace("%", "") or 0)
            step, max_rate = 3.0, base_rate + 16
        limit = float(s.get("duration") or 0) - 0.30
        rate_now = base_rate
        attempt = 0
        while True:
            tmp_parts = []
            ok = True
            for k, (spk, txt) in enumerate(parts):
                voice = char_voice.get(spk) or _voice_for(cfg, spk)
                conf = spk_confs.get(spk) or {}
                part = "%s.part%d.mp3" % (dst, k)
                info("%s 配音（%s）：%s" % (sid, conf.get("voice") or voice, txt))
                # 各角色自己的基准语速 + 本次为塞进画面追加的量
                try:
                    pbase = float(str(conf.get("rate", vcfg.get("rate") or "+0%"))
                                  .replace("%", "") or 0)
                except Exception:
                    pbase = base_rate
                good, err = _tts_one(cfg, voice, txt, part,
                                     rate_pct=_pct(pbase + (rate_now - base_rate)),
                                     spk=conf)
                if not good:
                    warn("%s 配音失败：%s" % (sid, err))
                    ok = False
                    break
                tmp_parts.append(part)
            if not ok:
                break

            # 多句先拼成一整条
            if len(tmp_parts) == 1:
                raw = tmp_parts[0]
            else:
                raw = dst + ".join.mp3"
                args = ["-y", "-loglevel", "error"]
                for tp in tmp_parts:
                    args += ["-i", tp]
                fc = "".join("[%d:a]" % i for i in range(len(tmp_parts)))
                args += ["-filter_complex", "%sconcat=n=%d:v=0:a=1[out]" % (fc, len(tmp_parts)),
                         "-map", "[out]", "-b:a", "192k", raw]
                try:
                    ff_run(exe, args)
                except SystemExit:
                    warn("%s 多句配音拼接失败" % sid)
                    ok = False
                    break

            # 豆包爱插长停顿，先压到 0.45s 再量时长
            if is_doubao and exe:
                keep = float((vcfg.get("doubao") or {}).get("trim_pause") or 0.45)
                trimmed = dst + ".trim.mp3"
                if _trim_pauses(exe, raw, trimmed, keep=keep):
                    if os.path.abspath(raw) != os.path.abspath(trimmed):
                        try:
                            os.remove(raw)
                        except Exception:
                            pass
                    raw = trimmed

            # 塞不进画面就提语速再来一遍
            real = ff_duration(raw, exe)
            if fit and limit > 0 and real > limit and attempt < 6:
                rate_now = min(max_rate, rate_now + step)
                info("  %s 配音 %.2fs 超镜长 %.2fs，语速提到 %+d%% 重来"
                     % (sid, real, limit, _pct(rate_now)))
                # 不删中间文件（批量删除会被安全钩子拦下并中断进程），
                # 临时名固定，下一轮直接覆盖写
                attempt += 1
                continue
            if fit and limit > 0 and real > limit:
                warn("%s 配音仍超镜长（%.2fs > %.2fs），建议改成更短的句子" % (sid, real, limit))
            break

        if not ok:
            continue

        # 后处理：房间感/压缩/去齿音（角色级优先，其次项目级 voices.postfilter）
        main_conf = spk_confs.get(parts[0][0]) or {}
        pf = (main_conf.get("postfilter") or vcfg.get("postfilter") or "").strip()
        if pf and exe and os.path.exists(raw):
            try:
                ff_run(exe, ["-y", "-loglevel", "error", "-i", raw, "-af", pf,
                             "-ar", "44100", "-ac", "1", "-b:a", "192k", dst])
            except SystemExit:
                warn("%s 配音后处理失败，用干声" % sid)
                shutil.copyfile(raw, dst)
            pass
        else:
            if os.path.abspath(raw) != os.path.abspath(dst):
                shutil.move(raw, dst)
            pass
        made.append(dst)
    info("配音 %d 句 -> audio/vo/" % len(made))
    return made


def cmd_voice(args):
    cfg, paths = load_project(args.dir)
    do_voice(cfg, paths, force=args.force,
             fit=not getattr(args, "no_fit", False))


# ----------------------------------------------------------------------------- assemble

def _ass_time(t):
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return "%d:%02d:%05.2f" % (h, m, s)


def _ass_text(t):
    return (t.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
             .replace("\n", "\\N"))


def write_subs(cfg, paths, timed_lines):
    """生成 ASS 字幕。timed_lines = [(shot, start_sec, end_sec), ...]，时间已经对准真实人声。"""
    w, h = OUT_SIZE.get(cfg["agnes"].get("aspect_ratio", "9:16"), (704, 1280))
    font_size = max(26, int(w * 0.058))
    rows = [
        "[Script Info]", "ScriptType: v4.00+",
        "PlayResX: %d" % w, "PlayResY: %d" % h, "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,Microsoft YaHei,%d,&H00FFFFFF,&H000000FF,&H00141414,&H78000000,"
        "0,0,0,0,100,100,0,0,1,3,1,2,40,40,140,1" % font_size,
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    count = 0
    for shot, start, end in timed_lines:
        line = (shot.get("line") or "").strip()
        extras = [x.get("line") for x in (shot.get("extra_lines") or [])
                  if (x.get("line") or "").strip()]
        if extras:
            line = line + (" / " if line else "") + " / ".join(extras)
        if not line or end <= start:
            continue
        rows.append("Dialogue: 0,%s,%s,Default,,0,0,0,,%s"
                    % (_ass_time(start), _ass_time(end), _ass_text(line)))
        count += 1
    path = os.path.join(paths["out"], "_subs.ass")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(rows) + "\n")
    return path if count else None


def _split_sub(text, max_chars=14):
    """长句在中点附近的标点处切两条，避免 ASS 自动换行变成歪的两排。"""
    text = (text or "").strip()
    if len(text) <= max_chars:
        return [text]
    mid = len(text) / 2.0
    cand = [i + 1 for i, ch in enumerate(text)
            if ch in "，。！？、；…—" and 4 <= i + 1 <= len(text) - 4]
    cut = min(cand, key=lambda i: abs(i - mid)) if cand else int(mid)
    return [text[:cut].strip(), text[cut:].strip()]


def write_shot_subs(paths, entries, max_chars=14, size=38, margin_v=150):
    """按镜头表里的 shot["subs"] 生成逐句 ASS。

    subs 写的是本镜内的相对时间，转场/收紧改动时间轴后会自动跟着走：
        "subs": [{"t": 0.2, "d": 1.4, "text": "趁热喝，不加糖。"}]
    长句自动切成前后两条，时长按字数比例分配，保证每排不超过 max_chars。
    margin_v：字幕距底部像素。裁掉画面底部后要调小，否则字幕会贴着画面下沿。
    """
    rows = []
    head = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 704",
        "PlayResY: 1280",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding",
        "Style: Default,Microsoft YaHei,%d,&H00FFFFFF,&H000000FF,&H00141414,"
        "&H78000000,0,0,0,0,100,100,0,0,1,3,1,2,40,40,%d,1" % (size, margin_v),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    count = 0
    for e in entries:
        subs = e["shot"].get("subs") or []
        for s in subs:
            text = (s.get("text") or "").strip()
            if not text:
                continue
            t0 = e["start"] + float(s.get("t", 0.0))
            d = float(s.get("d", 2.0))
            parts = _split_sub(text, max_chars)
            if len(parts) == 1:
                segs = [(t0, t0 + d, parts[0])]
            else:
                total_chars = sum(len(x) for x in parts) or 1
                segs, cur = [], t0
                for p in parts:
                    dd = max(0.7, d * len(p) / total_chars)
                    segs.append((cur, cur + dd - 0.06, p))
                    cur += dd
            for a, b, txt in segs:
                if b <= a:
                    continue
                rows.append("Dialogue: 0,%s,%s,Default,,0,0,0,,%s"
                            % (_ass_time(a), _ass_time(b), _ass_text(txt)))
                count += 1
    if not count:
        return None
    path = os.path.join(paths["out"], "_subs_shots.ass")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(head + rows) + "\n")
    return path


def detect_speech(cfg, clip, exe):
    """在片段的音轨里找出真正有人声的时间段（能量 + 基频周期性）。

    返回 [(start, end), ...]（相对片段开头的秒数）。检测不到就返回 []。
    """
    try:
        p = subprocess.run([exe, "-v", "error", "-i", clip, "-ac", "1", "-ar", "16000",
                            "-f", "s16le", "-acodec", "pcm_s16le", "-"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        raw = p.stdout
        if not raw:
            return []
        import struct
        n = len(raw) // 2
        data = struct.unpack("<%dh" % n, raw[:n * 2])
        sr = 16000
        frame = int(sr * 0.04)
        hop = int(sr * 0.02)
        feats = []
        for st in range(0, max(0, n - frame), hop):
            seg = data[st:st + frame]
            e = sum(x * x for x in seg) / len(seg)
            best = 0.0
            if e > 300:
                for lag in range(int(sr / 320), int(sr / 70)):
                    num = sum(seg[i] * seg[i + lag] for i in range(0, len(seg) - lag, 4))
                    den = math.sqrt(
                        sum(seg[i] * seg[i] for i in range(0, len(seg) - lag, 4)) *
                        sum(seg[i + lag] * seg[i + lag] for i in range(0, len(seg) - lag, 4))) or 1
                    c = num / den
                    if c > best:
                        best = c
            feats.append((st / sr, e, best))
        if not feats:
            return []
        p90 = sorted(f[1] for f in feats)[int(len(feats) * 0.9)]
        thr = max(300, p90 * 0.12)
        segs = []
        for t, e, b in feats:
            if e > thr and b > 0.5:
                if segs and t - segs[-1][1] < 0.35:
                    segs[-1][1] = t + 0.04
                else:
                    segs.append([t, t + 0.04])
        return [(a, b) for a, b in segs if b - a >= 0.25]
    except Exception as e:
        warn("人声检测失败（%s），跳过该镜字幕" % str(e)[:120])
        return []


def _parse_transition(spec):
    """dissolve:0.7 / fadewhite:0.4 / fadeblack:0.5 -> (xfade 名称, 秒数)"""
    raw = (spec or "").strip().lower()
    if raw in ("", "none"):
        return None, 0.0
    name, _, dur = raw.partition(":")
    table = {"dissolve": "fade", "fade": "fade", "fadewhite": "fadewhite",
             "white": "fadewhite", "fadeblack": "fadeblack", "black": "fadeblack"}
    kind = table.get(name, "fade")
    try:
        d = float(dur) if dur else 0.7
    except Exception:
        d = 0.7
    return kind, max(0.1, min(2.0, d))


def _xfade_chain(exe, clips, durs, trans, kinds, dst, with_audio=False, crop_bottom=0):
    """逐段转场拼接：trans[i]/kinds[i] 是第 i-1 段到第 i 段之间的转场。

    trans 全是 0.04 时等价于硬切；不同边界可以用不同转场与时长。

    crop_bottom：裁掉底部多少像素。用来去掉视频模型自己烧进画面的字幕/水印
    （提示词写了 no on-screen text 也不一定管用），顺带让竖屏比例更标准。
    返回合成后的总时长。
    """
    args = ["-y", "-loglevel", "error"]
    for c in clips:
        args += ["-i", c]
    parts = []
    prev = "[0:v]"
    L = float(durs[0])
    for i in range(1, len(clips)):
        d = float(trans[i])
        out = "[v%d]" % i
        parts.append("%s[%d:v]xfade=transition=%s:duration=%.3f:offset=%.3f%s"
                     % (prev, i, kinds[i], d, max(0.0, L - d), out))
        prev = out
        L = L + float(durs[i]) - d
    # 底部裁切：xfade 链之后再裁，避免每段裁切导致尺寸不一致
    if crop_bottom and crop_bottom > 0:
        parts.append("%scrop=iw:ih-%d,setsar=1[vc]" % (prev, int(crop_bottom)))
        prev = "[vc]"
    maps = ["-map", prev]
    if with_audio:
        ap = "[0:a]"
        for i in range(1, len(clips)):
            out = "[a%d]" % i
            parts.append("%s[%d:a]acrossfade=d=%.3f:c1=tri:c2=tri%s"
                         % (ap, i, float(trans[i]), out))
            ap = out
        maps += ["-map", ap, "-c:a", "aac", "-b:a", "160k"]
    else:
        maps += ["-an"]
    # 滤镜链长（51 镜 = 50 个 xfade）时命令行会超 Windows 长度限制 → 写文件
    fc_path = os.path.join(os.path.dirname(dst) or ".", "_xfade_filter.txt")
    with open(fc_path, "w", encoding="utf-8") as f:
        f.write(";".join(parts))
    args += ["-filter_complex_script", fc_path] + maps + [
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", dst]
    try:
        ff_run(exe, args)
    finally:
        if os.path.exists(fc_path):
            os.remove(fc_path)
    return L


def _xfade_concat(exe, clips, durs, kind, dur, dst, with_audio=False):
    """用 xfade 拼视频；with_audio=True 时音频也做 acrossfade，不丢台词原声。"""
    n = len(clips)
    return _xfade_chain(exe, clips, durs, [0.0] + [float(dur)] * (n - 1),
                        ["none"] + [kind] * (n - 1), dst, with_audio=with_audio)


def _tighten_entries(cfg, paths, entries, exe):
    """按人声位置收紧片段：砍掉开口前的长时间静音，尾部留一点反应。

    专治"一句台词撑 7 秒、前 6 秒干站着"。裁完会重算 timecode。
    """
    work_dir = os.path.join(paths["out"], "_tight")
    os.makedirs(work_dir, exist_ok=True)
    changed = 0
    for e in entries:
        shot = e["shot"]
        if not (shot.get("line") or "").strip():
            continue
        if shot.get("tighten") is False:
            info("%s 按 tighten=false 跳过收紧（关键动作在台词之后）" % shot["id"])
            continue
        try:
            segs = detect_speech(cfg, e["clip"], exe)
        except Exception:
            continue
        if not segs:
            continue
        dur = e["duration"]
        s0, s1 = segs[0][0], segs[-1][1]
        head = max(0.0, s0 - 0.5)
        tail = min(dur, s1 + 0.9)
        if tail - head < 1.6:
            continue
        if head < 0.5 and tail > dur - 0.5:
            continue
        dst = os.path.join(work_dir, shot["id"] + ".mp4")
        ff_run(exe, ["-y", "-loglevel", "error", "-ss", "%.3f" % head, "-to", "%.3f" % tail,
                     "-i", e["clip"], "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                     "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                     "-movflags", "+faststart", dst])
        info("%s 收紧：开口在 %.2fs，砍掉头部 %.2fs，成段 %.2fs"
             % (shot["id"], s0, head, tail - head))
        e["clip"] = dst
        e["duration"] = tail - head
        changed += 1
    if changed:
        t = 0.0
        for e in entries:
            e["start"] = t
            t += e["duration"]
    return changed


def _bgm_segments(entries):
    """按 shot.bgm（0-1）把时间轴切成音量段。没写 bgm 的镜头沿用上一段音量。"""
    segs = []
    for e in entries:
        v = e["shot"].get("bgm")
        if v is None:
            if not segs:
                continue
            v = segs[-1]["v"]
        v = max(0.0, min(1.5, float(v)))
        if segs and abs(segs[-1]["v"] - v) < 1e-4:
            segs[-1]["dur"] += e["duration"]
        else:
            segs.append({"start": e["start"], "dur": e["duration"], "v": v})
    return segs


def build_bgm_chain(bgm_idx, entries, total, fade=0.45, tail=3.0):
    """按镜头给定的 bgm 音量生成分段包络链。

    音乐素材本身按原时间轴切片，拼回去仍是同一首连贯的曲子，
    只是每段音量不同 —— 这样"什么时候有音乐、多大声"可以逐镜控制。
    段间用 0.8s 淡入淡出，边界正好落在镜头切换点上，听感像换气。
    """
    segs = _bgm_segments(entries)
    if not segs:
        return None
    used = segs[-1]["start"] + segs[-1]["dur"]
    if used < total - 0.05:
        segs[-1]["dur"] += total - used
    parts, labels = [], []
    n = len(segs)
    for i, s in enumerate(segs):
        st, d, v = s["start"], s["dur"], s["v"]
        f = ("[%d:a]atrim=%.3f:%.3f,asetpts=PTS-STARTPTS,apad,atrim=0:%.3f,"
             "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=%.3f"
             % (bgm_idx, st, st + d, d, v))
        if v > 0.001:
            if i > 0:
                f += ",afade=t=in:st=0:d=%.2f" % min(fade, d / 3.0)
            if i < n - 1:
                f += ",afade=t=out:st=%.2f:d=%.2f" % (max(0.0, d - fade), min(fade, d / 3.0))
            else:
                f += ",afade=t=out:st=%.2f:d=%.2f" % (max(0.0, d - tail), min(tail, d / 3.0))
        parts.append(f + "[b%d]" % i)
        labels.append("[b%d]" % i)
    parts.append("%sconcat=n=%d:v=0:a=1[mus]" % ("".join(labels), n))
    return parts


def _load_sfx():
    """加载同目录的 sfx.py（拟音合成库）。"""
    try:
        import sfx as m
        return m
    except ImportError:
        d = os.path.dirname(os.path.abspath(__file__))
        if d not in sys.path:
            sys.path.insert(0, d)
        import sfx as m
        return m


def db_to_gain(db):
    return 10.0 ** (float(db) / 20.0)


def collect_sfx(paths, entries, exe=None):
    """把镜头表里的 sfx 线索摊到绝对时间轴，缺的音效现场合成。

    每镜可写（at 是本镜内的秒数，gain 是 dB，相对音效峰值 -3dBFS）：
        "sfx": [{"at": 2.6, "kind": "glass", "gain": -22},
                {"at": 0.0, "kind": "rain", "dur": 42, "gain": -32}]
    也可写成简写 "sfx": ["tick", "whoosh"]（默认落在镜头开头、-12dB）。
    """
    m = _load_sfx()
    bank = os.path.join(paths["audio"], "sfx")
    os.makedirs(bank, exist_ok=True)
    cues = []
    for e in entries:
        for c in (e["shot"].get("sfx") or []):
            if isinstance(c, str):
                c = {"kind": c}
            kind = (c.get("kind") or "").strip()
            if not kind:
                continue
            dur = c.get("dur")
            # 优先用真实音效文件（audio/sfx/<kind>.wav|mp3|ogg|m4a），没有再现场合成
            dst = None
            for ext in (".wav", ".mp3", ".ogg", ".m4a", ".flac"):
                cand = os.path.join(bank, kind + ext)
                if os.path.exists(cand):
                    dst = cand
                    break
            if dst is None:
                name = kind if not dur else "%s_%g" % (kind, float(dur))
                dst = os.path.join(bank, name + ".wav")
            if not os.path.exists(dst):
                try:
                    m.build(kind, dur, dst)
                except Exception as ex:
                    warn("%s 音效 %s 合成失败：%s" % (e["shot"]["id"], kind, ex))
                    continue
            cues.append({
                "path": dst,
                "kind": kind,
                "shot": e["shot"]["id"],
                "start": max(0.0, e["start"] + float(c.get("at", 0.0))),
                "gain": db_to_gain(c.get("gain", -12)),
                "gain_db": float(c.get("gain", -12)),
            })
    return cues


def _timeline(paths, exe):
    """按片段实际时长排时间轴（不做收紧），给独立叠加用。"""
    shots = load_json(paths["shots"])["shots"]
    entries = []
    t = 0.0
    for shot in shots:
        p = os.path.join(paths["clips"], shot["id"] + ".mp4")
        if not os.path.exists(p):
            continue
        d = ff_duration(p, exe)
        entries.append({"shot": shot, "clip": p, "duration": d, "start": t})
        t += d
    return entries, t


def do_sfx(cfg, paths, into=None, out=None):
    """音效：生成素材，或把音效叠到已有成片上（视频流直接复制，不重编码）。"""
    exe = have_ffmpeg(cfg)
    if not exe:
        die("找不到 ffmpeg")
    entries, total = _timeline(paths, exe)
    cues = collect_sfx(paths, entries, exe)
    if not cues:
        info("镜头表里没有 sfx 线索，只生成了素材库 audio/sfx/")
        return None
    info("音效 %d 条：%s" % (len(cues), "、".join(
        "%s@%.2fs(%s %.0fdB)" % (c["shot"], c["start"], c["kind"], c["gain_db"])
        for c in cues)))
    if not into:
        return None

    src = into if os.path.isabs(into) else os.path.join(paths["root"], into)
    if not os.path.exists(src):
        die("找不到要叠加的成片：" + src)
    dst = out or os.path.join(paths["out"], "final-sfx.mp4")
    if not os.path.isabs(dst):
        dst = os.path.join(paths["root"], dst)

    inputs = ["-i", src]
    parts = ["[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[base]"]
    labels = ["[base]"]
    for i, c in enumerate(cues):
        inputs += ["-i", c["path"]]
        ms = int(round(c["start"] * 1000))
        parts.append("[%d:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
                     "adelay=%d|%d,volume=%.4f[s%d]" % (i + 1, ms, ms, c["gain"], i))
        labels.append("[s%d]" % i)
    parts.append("%samix=inputs=%d:duration=first:normalize=0,"
                 "alimiter=limit=0.95:level=disabled,aresample=44100[a]"
                 % ("".join(labels), len(labels)))
    # 滤镜链长（几十条音效）会超 Windows 命令行长度限制 → 写文件
    fc_path = os.path.join(paths["out"], "_sfx_filter.txt")
    with open(fc_path, "w", encoding="utf-8") as f:
        f.write(";".join(parts))
    try:
        ff_run(exe, ["-y", "-loglevel", "error"] + inputs +
               ["-filter_complex_script", fc_path,
                "-map", "0:v", "-map", "[a]", "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", dst])
    finally:
        if os.path.exists(fc_path):
            os.remove(fc_path)
    info("已叠加音效 -> %s" % dst)
    return dst


def _clip_mean_db(exe, path, cache=None):
    """量一条片段原声的平均电平（dBFS）。用来判断模型是不是自己念了台词。

    视频模型（尤其是给「她说了一句话」这种提示词时）会自己生成英文人声，
    纯环境镜通常 mean 在 -40 以下，带人声的一般 -32 以上。
    """
    if cache is not None and path in cache:
        return cache[path]
    lvl = None
    try:
        r = subprocess.run([exe, "-hide_banner", "-i", path, "-af", "volumedetect",
                            "-f", "null", "-"], capture_output=True)
        txt = r.stderr.decode("utf8", "ignore")
        m = re.search(r"mean_volume:\s*(-?[\d.]+)", txt)
        if m:
            lvl = float(m.group(1))
    except Exception:
        lvl = None
    if cache is not None:
        cache[path] = lvl
    return lvl


def do_assemble(cfg, paths, use_subs=False, use_voice=False, transition=None, tighten=True,
                crop_bottom=0):
    exe = have_ffmpeg(cfg)
    if not exe:
        die("找不到 ffmpeg（装 imageio-ffmpeg 或配置 ffmpeg 路径）")
    shots = load_json(paths["shots"])["shots"]

    entries = []
    t = 0.0
    for shot in shots:
        p = os.path.join(paths["clips"], shot["id"] + ".mp4")
        if not os.path.exists(p):
            info("缺少片段: " + shot["id"])
            continue
        d = ff_duration(p, exe)
        entries.append({"shot": shot, "clip": p, "duration": d, "start": t})
        t += d
    if not entries:
        die("没有任何片段")
    if tighten:
        n = _tighten_entries(cfg, paths, entries, exe)
        if n:
            info("已收紧 %d 段（砍掉口播前的空等）" % n)
    total = sum(e["duration"] for e in entries)
    info("共 %d 段，总时长 %.2f 秒" % (len(entries), total))

    has_audio = [ff_has_audio(e["clip"], exe) for e in entries]
    mixed = any(has_audio) and not all(has_audio)
    work = [e["clip"] for e in entries]
    if mixed:
        norm_dir = os.path.join(paths["out"], "_norm")
        os.makedirs(norm_dir, exist_ok=True)
        for i, (c, h) in enumerate(zip(work, has_audio)):
            if h:
                continue
            dst = os.path.join(norm_dir, "n%02d.mp4" % i)
            ff_run(exe, ["-y", "-loglevel", "error", "-i", c,
                         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                         "-shortest", "-map", "0:v", "-map", "1:a",
                         "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", dst])
            work[i] = dst

    tmp_list = os.path.join(paths["out"], "_concat.txt")
    with open(tmp_list, "w", encoding="utf-8") as f:
        for c in work:
            f.write("file '%s'\n" % c.replace("\\", "/"))

    video_only = os.path.join(paths["out"], "_video_only.mp4")
    kind, tdur = _parse_transition(transition)

    # 逐段转场：镜头表里 shot["x"] = {"kind": "fade", "dur": 0.8} 表示「进入本镜时」
    # 用什么转场；没写就是硬切（实现为 0.04s 极短叠化，肉眼不可见）。
    trans, kinds = [0.0], ["none"]
    for i, e in enumerate(entries):
        if i == 0:
            continue
        x = e["shot"].get("x") or {}
        k = (x.get("kind") or kind or "cut").strip()
        if k in ("", "cut", "none"):
            # 硬切也走 0.1s 极短叠化：xfade 不支持短于一帧的时长，否则整条链会断
            d = 0.1
            k = "fade"
        else:
            d = float(x.get("dur", tdur if kind else 0.6))
        d = max(0.1, min(d, 0.4 * min(entries[i - 1]["duration"], e["duration"])))
        trans.append(d)
        kinds.append(k)

    if any(t > 0.05 for t in trans[1:]) and len(work) > 1:
        all_audio = all(has_audio)
        info("逐段转场 %d 处叠化，合计 %.1fs（音频同步交叉淡化）"
             % (sum(1 for t in trans[1:] if t > 0.05), sum(trans[1:])))
        # xfade 要求各段帧率/尺寸/像素格式一致，先统一
        # 尺寸按"出现次数最多的那个"当基准（混用 flash / 付费模型时会出现 704 与 720 并存）
        sizes = [ff_size(c, exe) for c in work]
        sizes = [s for s in sizes if s]
        canon = None
        if sizes:
            canon = max(set(sizes), key=lambda s: (sizes.count(s), s[0]))
        tr_dir = os.path.join(paths["out"], "_tr")
        os.makedirs(tr_dir, exist_ok=True)
        for i, c in enumerate(work):
            dst = os.path.join(tr_dir, "t%02d.mp4" % i)
            if canon:
                vf = ("scale=%d:%d:force_original_aspect_ratio=increase,"
                      "crop=%d:%d,setsar=1" % (canon[0], canon[1], canon[0], canon[1]))
            else:
                vf = "scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1"
            ff_run(exe, ["-y", "-loglevel", "error", "-i", c, "-r", "24",
                         "-vf", vf,
                         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                         "-movflags", "+faststart", dst])
            work[i] = dst
            entries[i]["duration"] = ff_duration(dst, exe)
        _xfade_chain(exe, work, [e["duration"] for e in entries], trans, kinds, video_only,
                     with_audio=all_audio, crop_bottom=crop_bottom)
        starts = [0.0]
        for i in range(1, len(entries)):
            starts.append(starts[i - 1] + entries[i - 1]["duration"] - trans[i])
        for e, s in zip(entries, starts):
            e["start"] = s
        total = sum(e["duration"] for e in entries) - sum(trans[1:])
        info("转场后总时长 %.2f 秒（原 %.2f）" % (total, sum(e["duration"] for e in entries)))
        if not all_audio:
            has_audio = [False] * len(entries)
            mixed = False
    else:
        ff_run(exe, ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", tmp_list,
                     "-c", "copy", video_only])

    # 配音：有台词就自动补 TTS
    vo_map = []
    if use_voice and any((e["shot"].get("line") or "").strip() for e in entries):
        vo_dir = os.path.join(paths["audio"], "vo")
        # 只给 shot.tts=true 的镜头补 TTS（如 VO 旁白镜），不把全部对白重配一遍
        need = [e for e in entries if e["shot"].get("tts")
                and (e["shot"].get("line") or "").strip()
                and not os.path.exists(os.path.join(vo_dir, e["shot"]["id"] + ".mp3"))]
        if need:
            do_voice(cfg, paths, only=set(e["shot"]["id"] for e in need))
        for e in entries:
            if not (e["shot"].get("line") or "").strip():
                continue
            p = os.path.join(vo_dir, e["shot"]["id"] + ".mp3")
            if os.path.exists(p):
                vo_map.append((e["start"], p))

    # 输入：0=视频，1=配乐（可选），2=静音床，3..=配音
    bgm = os.path.join(paths["audio"], "bgm.mp3")
    try:
        pconf = load_json(os.path.join(paths["root"], "project.json")) or {}
    except Exception:
        pconf = {}
    if pconf.get("bgm_file"):
        for cand in (os.path.join(paths["audio"], "music", pconf["bgm_file"]),
                     os.path.join(paths["audio"], pconf["bgm_file"])):
            if os.path.exists(cand):
                bgm = cand
                info("配乐：%s（project.json bgm_file）" % os.path.basename(cand))
                break
    inputs = ["-i", video_only]
    idx = 1
    bgm_idx = None
    if os.path.exists(bgm):
        # 曲比片短就循环铺满，避免结尾突然没音乐
        try:
            bd = ff_duration(bgm, exe)
        except Exception:
            bd = 0.0
        if bd and bd < total - 0.5:
            info("配乐只有 %.0fs，循环铺满整片" % bd)
            inputs += ["-stream_loop", "-1", "-i", bgm]
        else:
            inputs += ["-i", bgm]
        bgm_idx = idx
        idx += 1
    bed_idx = idx
    inputs += ["-f", "lavfi", "-t", "%.3f" % (total + 0.5), "-i", "anullsrc=r=44100:cl=stereo"]
    idx += 1
    vo_inputs = []
    for start, p in vo_map:
        inputs += ["-i", p]
        vo_inputs.append((idx, start))
        idx += 1
    sfx_cues = collect_sfx(paths, entries, exe)
    sfx_inputs = []
    for c in sfx_cues:
        inputs += ["-i", c["path"]]
        sfx_inputs.append((idx, c))
        idx += 1

    parts = []
    labels = []
    mute_cache = {}
    parts.append("[%d:a]volume=0[bed]" % bed_idx)
    labels.append("[bed]")
    if any(has_audio) or mixed:
        # 只有叠加配乐/TTS 时才压低原声；否则保持原声（模型自己的台词都在这条轨里）
        # 注意：台词本身就在这条轨上，压很了会把人声一起压小，所以有配乐时只降 ~1.7dB
        line_shots = [e for e in entries if (e["shot"].get("line") or "").strip()]
        tts_full = bool(vo_map) and all(
            os.path.exists(os.path.join(paths["audio"], "vo", e["shot"]["id"] + ".mp3"))
            for e in line_shots)
        amb_vol = 0.22 if tts_full else (0.82 if bgm_idx is not None else 1.0)
        # 双人对白集：模型会在「她开口说话」的镜头里自己念英文（训练偏英语），
        # 压到 0.22 还是听得见。凡是有台词、而且已经配好 TTS 的镜头，把原声整段静音，
        # 只留其余镜头的环境底噪。project.json audio.mute_native_on_dialogue=false 可关。
        amb_chain = "[0:a]volume=%.2f" % amb_vol
        mute_on_dlg = True
        try:
            mute_on_dlg = (pconf.get("audio") or {}).get("mute_native_on_dialogue", True)
        except Exception:
            pass
        muted = []
        if tts_full and mute_on_dlg:
            for e in entries:
                sid = e["shot"]["id"]
                if not (e["shot"].get("line") or "").strip():
                    continue
                if not os.path.exists(os.path.join(paths["audio"], "vo", sid + ".mp3")):
                    continue
                # 只有「原声里真的有人声」才压；纯环境镜（安静的房间、空镜）保留底噪，
                # 否则整片变成一条一条的真空，比英文更难听。
                lvl = _clip_mean_db(exe, e["clip"], mute_cache)
                if lvl is None or lvl < -33:
                    continue
                a0 = e["start"]
                b0 = e["start"] + e["duration"]
                amb_chain += ",volume=0.10:enable='between(t,%.3f,%.3f)'" % (a0, b0)
                muted.append("%s(%.0fdB)" % (sid, lvl))
        if muted:
            info("压低原声 %d 镜（模型自念英文）：%s" % (len(muted), "、".join(muted)))
        parts.append(amb_chain + "[amb]")
        labels.append("[amb]")
    if bgm_idx is not None:
        chain = build_bgm_chain(bgm_idx, entries, total)
        if chain:
            segs = _bgm_segments(entries)
            info("配乐分段：%d 段，音量 %s" % (
                len(segs),
                " / ".join("%.2fs起%.2f" % (s["start"], s["v"]) for s in segs)))
            parts.extend(chain)
        else:
            parts.append("[%d:a]atrim=0:%.3f,apad,volume=0.85[mus]" % (bgm_idx, total))
        labels.append("[mus]")
    vol = float((cfg.get("voices") or {}).get("volume", 1.6))
    for i, (vi, start) in enumerate(vo_inputs):
        ms = int(round((start + 0.3) * 1000))
        parts.append("[%d:a]adelay=%d|%d,volume=%.2f[v%d]" % (vi, ms, ms, vol, i))
        labels.append("[v%d]" % i)
    for i, (si, c) in enumerate(sfx_inputs):
        ms = int(round(c["start"] * 1000))
        parts.append("[%d:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
                     "adelay=%d|%d,volume=%.4f[s%d]" % (si, ms, ms, c["gain"], i))
        labels.append("[s%d]" % i)
    if sfx_cues:
        info("音效 %d 条：%s" % (len(sfx_cues), "、".join(
            "%s+%.2fs %s %.0fdB" % (c["shot"], c["start"] - next(
                e["start"] for e in entries if e["shot"]["id"] == c["shot"]),
                c["kind"], c["gain_db"]) for c in sfx_cues)))

    if len(labels) > 1:
        parts.append("%samix=inputs=%d:duration=first:normalize=0,"
                     "alimiter=limit=0.9:level=disabled,aresample=44100[a]"
                     % ("".join(labels), len(labels)))
        audio_map = "[a]"
    else:
        audio_map = "[bed]"

    sub_path = None
    subs_override = os.path.join(paths["out"], "_subs_override.ass")
    if use_subs and any(e["shot"].get("subs") for e in entries):
        # 镜头表里写了逐句字幕：按时间轴自动生成，长句自动切成两条单排
        sub_path = write_shot_subs(paths, entries,
                                   margin_v=max(60, 150 - int(crop_bottom or 0)))
        if sub_path:
            n = sum(1 for l in open(sub_path, encoding="utf-8") if l.startswith("Dialogue:"))
            info("字幕：按镜头表逐句生成 %d 条（时间轴已跟转场重排）" % n)
    elif use_subs and os.path.exists(subs_override):
        # 外部字幕优先（逐句手写时间轴，VAD 漏检轻声台词时用它补）
        sub_path = subs_override
        info("字幕使用外部文件 _subs_override.ass（%d 行）"
             % sum(1 for l in open(subs_override, encoding="utf-8") if l.startswith("Dialogue:")))
    elif use_subs:
        timed = []
        for e in entries:
            sid = e["shot"]["id"]
            line = (e["shot"].get("line") or "").strip()
            if not line:
                continue
            vo_p = os.path.join(paths["audio"], "vo", sid + ".mp3")
            if use_voice and os.path.exists(vo_p):
                d = ff_duration(vo_p, exe)
                start = e["start"] + 0.3
                end = min(e["start"] + e["duration"] - 0.1, start + d + 0.4)
                timed.append((e["shot"], start, end))
            elif ff_has_audio(e["clip"], exe):
                segs = detect_speech(cfg, e["clip"], exe)
                if segs:
                    merged = [list(segs[0])]
                    for a, b in segs[1:]:
                        if a - merged[-1][1] < 0.6:
                            merged[-1][1] = b
                        else:
                            merged.append([a, b])
                    a, b = max(merged, key=lambda x: x[1] - x[0])
                    start = e["start"] + max(0.0, a - 0.15)
                    end = min(e["start"] + e["duration"] - 0.05, e["start"] + b + 0.45)
                    timed.append((e["shot"], start, end))
                    info("%s 人声 %.2f-%.2fs，字幕已对齐" % (sid, a, b))
                else:
                    info("%s 未检测到人声，跳过字幕" % sid)
        if timed:
            sub_path = write_subs(cfg, paths, timed)
    if sub_path:
        # 用真实文件名（外部覆盖时是 _subs_override.ass），否则滤镜会烧到旧字幕
        parts.append("[0:v]ass=%s[vout]" % os.path.basename(sub_path))

    final = os.path.join(paths["out"], "final.mp4")

    def render(burn):
        # 滤镜图很长（51 镜 = 50+ 个配音/音效输入 + 36 段配乐），
        # 直接放在命令行里会撞 Windows 的命令行长度上限（WinError 206）。
        # 写成文件用 -filter_complex_script 传入，长度无限制。
        fc_path = os.path.join(paths["out"], "_filter.txt")
        with open(fc_path, "w", encoding="utf-8") as f:
            f.write(";".join(parts))
        cmd = ["-y", "-loglevel", "error"] + inputs + ["-filter_complex_script", fc_path,
                                                       "-map", "[vout]" if burn else "0:v",
                                                       "-map", audio_map]
        if burn:
            cmd += ["-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-pix_fmt", "yuv420p"]
        else:
            cmd += ["-c:v", "copy"]
        cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", "final.mp4"]
        try:
            ff_run(exe, cmd, cwd=paths["out"])
        finally:
            if os.path.exists(fc_path):
                os.remove(fc_path)

    if sub_path:
        try:
            render(True)
        except SystemExit:
            warn("字幕烧制失败（可能是字体问题），改为无字幕输出")
            # 去掉 ass 滤镜重试。
            # 注意：video_only 等中间产物这时已被删掉（见下面的清理），
            # 所以要先把它们重新生成出来，否则重试必然失败。
            parts[:] = [p for p in parts if "[vout]" not in p]
            if not os.path.exists(video_only):
                _xfade_chain(exe, work, [e["duration"] for e in entries], trans, kinds,
                             video_only, with_audio=all_audio, crop_bottom=crop_bottom)
            render(False)
    else:
        render(False)

    for p in (video_only, tmp_list):
        if os.path.exists(p):
            os.remove(p)
    norm_dir = os.path.join(paths["out"], "_norm")
    if os.path.isdir(norm_dir):
        shutil.rmtree(norm_dir, ignore_errors=True)
    normalize_loudness(final, exe)
    info("成片 -> out/final.mp4  (%.1f MB, %.1fs)" % (os.path.getsize(final) / 1e6, total))
    return final


def cmd_assemble(args):
    cfg, paths = load_project(args.dir)
    do_assemble(cfg, paths, use_subs=args.subs, use_voice=args.voice,
                transition=getattr(args, "transition", None),
                tighten=not getattr(args, "no_tighten", False),
                crop_bottom=int(getattr(args, "crop_bottom", 0) or 0))


def cmd_seam(args):
    cfg, paths = load_project(args.dir)
    do_seam(cfg, paths, window=args.window)


def cmd_sfx(args):
    cfg, paths = load_project(args.dir)
    do_sfx(cfg, paths, into=args.into, out=args.out)


def _gray_thumb(path, exe, w=48, h=80):
    """把一帧缩成很小的灰度图，用来粗算两帧差多少（不依赖 numpy）。"""
    tmp = path + ".thumb.ppm"
    try:
        ff_run(exe, ["-y", "-loglevel", "error", "-i", path, "-frames:v", "1",
                     "-vf", "scale=%d:%d,format=gray" % (w, h), tmp])
    except SystemExit:
        return None
    try:
        with open(tmp, "rb") as f:
            data = f.read()
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass
    # 跳过 ppm 头（P5...\n）
    i = 0
    nl = 0
    while i < len(data) and nl < 3:
        if data[i:i+1] == b"\n":
            nl += 1
        i += 1
    return data[i:i + w * h]


def do_seam(cfg, paths, window=0.4):
    """量相邻两镜的「接缝跳变」：上一镜最后一帧 vs 下一镜第一帧的灰度差。

    数值越小剪起来越顺；60 以上基本就是硬跳（换景/换光/换机位）。
    加了 tail_frame（尾帧桥接）的镜头，这个数会掉到个位数。
    """
    exe = have_ffmpeg(cfg)
    shots = load_json(paths["shots"])["shots"]
    rows = []
    for i in range(len(shots) - 1):
        a, b = shots[i], shots[i + 1]
        ca = os.path.join(paths["clips"], a["id"] + ".mp4")
        cb = os.path.join(paths["clips"], b["id"] + ".mp4")
        if not os.path.exists(ca):
            continue
        fa = os.path.join(paths["out"], "_seam_a.png")
        ff_run(exe, ["-y", "-loglevel", "error", "-sseof", "-%.2f" % window, "-i", ca,
                     "-frames:v", "1", fa])
        if os.path.exists(cb):
            fb = os.path.join(paths["out"], "_seam_b.png")
            ff_run(exe, ["-y", "-loglevel", "error", "-i", cb, "-frames:v", "1", fb])
        else:
            fb = os.path.join(paths["frames"], b["id"] + ".jpg")
            if not os.path.exists(fb):
                continue
        ta, tb = _gray_thumb(fa, exe), _gray_thumb(fb, exe)
        if not ta or not tb or len(ta) != len(tb):
            continue
        diff = sum(abs(x - y) for x, y in zip(ta, tb)) / float(len(ta))
        rows.append((a["id"], b["id"], diff, bool(b.get("tail_frame")), b.get("kind")))
    top = sorted(rows, key=lambda x: -x[2])[:6]
    if top:
        print("最跳的 6 处：")
        for a_id, b_id, d, bridged, kind in top:
            tag = "尾帧桥接" if bridged else ("回忆" if kind == "recall" else "")
            mark = " <<< 硬跳" if d >= 60 else (" < 轻微" if d >= 35 else "")
            print("  %s → %s  差值 %.1f%s %s" % (a_id, b_id, d, mark, tag))
        print("")
    print("接缝检查（上一镜末帧 vs 下一镜首帧，灰度差 0-255）")
    print("%-6s %-6s %6s  %s" % ("前", "后", "差值", "备注"))
    for a, b, d, bridged, kind in rows:
        tag = "尾帧桥接" if bridged else ("回忆" if kind == "recall" else "")
        mark = "  <<< 跳" if d >= 60 else ("  <" if d >= 35 else "")
        print("%-6s %-6s %6.1f  %s%s" % (a, b, d, tag, mark))
    if rows:
        avg = sum(r[2] for r in rows) / len(rows)
        worst = max(rows, key=lambda x: x[2])
        print("\n平均 %.1f，最跳的一处 %s→%s %.1f" % (avg, worst[0], worst[1], worst[2]))
    return rows


def do_audit(cfg, paths):
    """出一份成片审计报告：逐镜核对资产、时长、分辨率、音轨、人声，写 AUDIT.md / audit.json。"""
    exe = have_ffmpeg(cfg)
    shots = load_json(paths["shots"])["shots"]
    rows = []
    issues = []
    total_planned = 0
    total_actual = 0.0
    image_count = 0

    for s in shots:
        sid = s["id"]
        planned = int(s.get("duration") or 0)
        total_planned += planned
        frame = os.path.join(paths["frames"], sid + ".jpg")
        scene = plate_for(paths, s) or os.path.join(paths["scenes"], scene_key(s) + ".jpg")
        clip = os.path.join(paths["clips"], sid + ".mp4")
        rec = {
            "id": sid, "planned": planned,
            "scene": os.path.exists(scene), "frame": os.path.exists(frame),
            "clip": False, "actual": None, "res": "", "fps": "", "audio": False,
            "speech": [], "speaker": s.get("speaker") or "", "line": s.get("line") or "",
            "shot_size": s.get("shot_size") or "",
        }
        image_count += (1 if rec["scene"] else 0) + (1 if rec["frame"] else 0)
        is_recall = (s.get("kind") == "recall")
        # 回忆镜是从前几集剪出来的，本来就没有场景板/首帧，别报成缺失
        if not rec["scene"] and not is_recall:
            issues.append("%s 缺场景图" % sid)
        if not rec["frame"] and not is_recall:
            issues.append("%s 缺首帧" % sid)
        if os.path.exists(clip):
            rec["clip"] = True
            d = ff_duration(clip, exe)
            rec["actual"] = round(d, 2)
            total_actual += d
            p = ff_run(exe, ["-i", clip], check=False)
            txt = p.stderr.decode("utf-8", "ignore")
            m = re.search(r"(\d{2,5})x(\d{2,5})", txt)
            if m:
                rec["res"] = "%sx%s" % (m.group(1), m.group(2))
            m = re.search(r"([\d.]+) fps", txt)
            if m:
                rec["fps"] = m.group(1)
            rec["audio"] = "Audio:" in txt
            is_vo = (rec["speaker"] or "").upper() == "VO"
            if rec["audio"]:
                rec["speech"] = detect_speech(cfg, clip, exe)
            if abs(d - planned) > 1.5:
                issues.append("%s 实际 %.2fs 与计划 %ds 相差超过 1.5s" % (sid, d, planned))
            # VO（画外音/独白）是后期 TTS 贴上去的，片段里本来就没这条人声
            if rec["line"] and not rec["speech"] and not is_vo:
                issues.append("%s 有台词但未检测到人声" % sid)
            if rec["speech"] and d > 0 and rec["speech"][0][0] > 0.45 * d and not is_vo:
                issues.append("%s 台词到 %.1fs 才开口（占 %.0f%%），前段空等，合成前建议收紧"
                              % (sid, rec["speech"][0][0], 100.0 * rec["speech"][0][0] / d))
            if rec["res"] and rec["res"] not in ("704x1280", "720x1280"):
                issues.append("%s 分辨率 %s 与竖屏 720P 预期不符" % (sid, rec["res"]))
        else:
            issues.append("%s 缺视频片段" % sid)
        rows.append(rec)

    # 角色资产
    chars = []
    for name in all_char_names(paths):
        cdir = char_dir(paths, name)
        if os.path.isdir(cdir):
            c = {
                "name": name,
                "source": os.path.exists(os.path.join(cdir, "source.jpg")),
                "face_ref": os.path.exists(os.path.join(cdir, "face_ref.jpg")),
                "turnaround": os.path.exists(os.path.join(cdir, "turnaround.jpg")),
            }
            if not c["turnaround"]:
                issues.append("角色 %s 缺三视图" % name)
            chars.append(c)

    props = []
    if os.path.isdir(paths["props"]):
        props = sorted(f[:-4] for f in os.listdir(paths["props"]) if f.endswith(".jpg"))

    clips_done = sum(1 for r in rows if r["clip"])
    plate_keys = {angle_key(x) for x in shots}
    scenes_done = sum(1 for k in plate_keys if os.path.exists(os.path.join(paths["scenes"], k + ".jpg")))
    frames_done = sum(1 for r in rows if r["frame"])
    speech_done = sum(1 for r in rows if r["speech"])
    dialogue = sum(1 for r in rows if r["line"])
    final = os.path.join(paths["out"], "final.mp4")
    final_ok = os.path.exists(final)
    if not final_ok:
        issues.append("还没有成片 out/final.mp4")

    video_cost = total_actual * 0.025
    md = []
    md.append("# 成片审计报告 — %s" % cfg.get("title", ""))
    md.append("")
    md.append("- 项目目录：`%s`" % paths["root"])
    md.append("- 生成时间：%s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    md.append("- 模型：%s（视频）/ %s（图片）/ %s（编剧）" % (
        cfg["agnes"].get("video_model"), cfg["agnes"].get("image_model"), cfg["agnes"].get("text_model")))
    md.append("- 镜头数：%d；计划总时长：%d 秒；实际片段总时长：%.2f 秒" % (
        len(rows), total_planned, total_actual))
    md.append("")
    md.append("## 一、流水线阶段")
    md.append("")
    md.append("| 阶段 | 命令 | 产物 | 状态 |")
    md.append("|---|---|---|---|")
    md.append("| 剧本与分镜 | `ac.py story` | `script/story.md`、`script/shots.json` | %s |" % (
        "OK" if os.path.exists(paths["story"]) else "缺失"))
    md.append("| 角色定妆 + 多视角 | `ac.py char-gen --tri` | `assets/characters/<name>/` | %d 个角色 |" % len(chars))
    md.append("| 道具图 | `ac.py prop-gen` | `assets/props/` | %d 张 |" % len(props))
    md.append("| 场景扩写 + 场景图 | `ac.py scene-gen` | `assets/scenes/` | %d/%d 个场景 |" % (scenes_done, len(plate_keys)))
    md.append("| 首帧图 | `ac.py frame` | `frames/` | %d/%d |" % (frames_done, len(rows)))
    md.append("| 视频 | `ac.py video` | `clips/` | %d/%d |" % (clips_done, len(rows)))
    md.append("| 合成 | `ac.py assemble` | `out/final.mp4` | %s |" % ("OK" if final_ok else "未完成"))
    md.append("")
    md.append("## 二、资产清单")
    md.append("")
    md.append("- 角色：" + "、".join(
        "%s（定妆%s / 三视图%s）" % (c["name"], "OK" if c["face_ref"] else "缺", "OK" if c["turnaround"] else "缺")
        for c in chars))
    md.append("- 道具：%d 张（%s）" % (len(props), "、".join(props) if props else "无"))
    md.append("- 场景板：%d/%d 个场景（同场景镜头共用一张板）；首帧：%d/%d；视频片段：%d/%d" % (
        scenes_done, len(plate_keys), frames_done, len(rows), clips_done, len(rows)))
    md.append("- 有台词镜头：%d 个；检测到人声：%d 个" % (dialogue, speech_done))
    md.append("")
    # 剧本自检：场景圣经 / 机位 / 人物白名单 / 服装锁
    story = load_json(paths["shots"])
    chars = {c.get("name"): c for c in (story.get("characters") or [])}
    script_issues = []
    for name, c in chars.items():
        if not (c.get("outfit_en") or "").strip():
            script_issues.append("角色 %s 没有 outfit_en（服装未锁定，会中途换衣服）" % name)
    seen_scene = {}
    for sh in shots:
        sc = sh.get("scene") or {}
        key = scene_key(sh)
        if sh.get("kind") == "recall":
            continue  # 回忆镜沿用前几集素材，自己的场景/机位描述没意义
        seen_scene.setdefault(key, sc)
        if len(sc.get("set") or []) < 4:
            script_issues.append("%s 的场景 %s 陈设不足（set 少于 4 条）" % (sh["id"], key))
        if not (sc.get("angles") or {}).get(sh.get("angle") or "wide"):
            script_issues.append("%s 的机位 %s 没有英文描述" % (sh["id"], sh.get("angle")))
        for n in (sh.get("cast") or []):
            if n not in chars:
                script_issues.append("%s 的 cast 里有未定义角色 %s" % (sh["id"], n))

    md.append("## 三、逐镜核对")
    md.append("")
    md.append("| 镜 | 景别 | 计划 | 实际 | 场景图 | 首帧 | 片段 | 分辨率 | 帧率 | 音轨 | 人声 | 台词 |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        md.append("| %s | %s | %ds | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["id"], r["shot_size"] or "-", r["planned"],
            ("%.2fs" % r["actual"]) if r["actual"] else "-",
            "OK" if r["scene"] else "-", "OK" if r["frame"] else "-", "OK" if r["clip"] else "-",
            r["res"] or "-", r["fps"] or "-", "有" if r["audio"] else "无",
            ("%.2f-%.2fs" % r["speech"][0]) if r["speech"] else "-",
            (r["line"] or "-")))
    md.append("")
    md.append("## 三·五、剧本自检（场景圣经 / 机位 / 人物 / 服装）")
    md.append("")
    if script_issues:
        for x in script_issues:
            md.append("- ⚠ " + x)
            issues.append(x)
    else:
        md.append("- 全部通过：每个场景都有陈设清单与机位表，每个角色都有固定服装，每镜人物白名单有效。")
    md.append("")
    md.append("| 场景 | 陈设条数 | 机位 | 镜号 |")
    md.append("|---|---|---|---|")
    ang_map = {}
    for sh in shots:
        ang_map.setdefault(scene_key(sh), {}).setdefault(sh.get("angle") or "wide", []).append(sh["id"])
    for key, sc in seen_scene.items():
        for ang, ids in ang_map.get(key, {}).items():
            md.append("| %s | %d | %s | %s |" % (key, len(sc.get("set") or []), ang, "、".join(ids)))
    md.append("")

    md.append("## 四、质检结论")
    md.append("")
    if issues:
        md.append("发现 %d 个问题：" % len(issues))
        md.append("")
        for x in issues:
            md.append("- " + x)
    else:
        md.append("全部检查项通过：场景图、首帧、片段、分辨率、音轨、人声均正常。")
    md.append("")
    md.append("## 五、成本估算")
    md.append("")
    md.append("- 视频：%.2f 秒 × $0.025/秒 = $%.3f（当前限时免费，实际 $0）" % (total_actual, video_cost))
    md.append("- 图片：约 %d 张（当前免费，实际 $0）" % image_count)
    md.append("")
    md.append("## 六、文件位置")
    md.append("")
    md.append("- 剧本：`script/story.md`")
    md.append("- 镜头表：`script/shots.json`")
    md.append("- 角色：`assets/characters/`")
    md.append("- 场景图：`assets/scenes/`")
    md.append("- 首帧：`frames/`")
    md.append("- 片段：`clips/`")
    md.append("- 成片：`out/final.mp4`")
    md.append("")

    md_path = os.path.join(paths["root"], "AUDIT.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    save_json(os.path.join(paths["root"], "audit.json"), {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "title": cfg.get("title"),
        "shots": rows, "characters": chars, "props": props,
        "total_planned": total_planned, "total_actual": round(total_actual, 2),
        "issues": issues,
    })
    info("审计报告 -> AUDIT.md（问题 %d 个）" % len(issues))
    return md_path


def cmd_audit(args):
    cfg, paths = load_project(args.dir)
    do_audit(cfg, paths)


# ----------------------------------------------------------------------------- auto

def cmd_auto(args):
    root = os.path.abspath(args.dir)
    if not os.path.exists(os.path.join(root, "project.json")):
        init_project(root, args.title)
    cfg, paths = load_project(root)
    require_agnes_creds(cfg)

    t0 = time.time()
    story = load_json(paths["shots"], {"shots": []})
    if args.regen_story or not story.get("shots"):
        if not args.idea:
            die("还没有镜头表，请用 --idea 提供一句话创意（或先手动写好 script/shots.json）")
        story = do_story(cfg, paths, args.idea, args.shots, args.seconds, args.title)
    else:
        info("复用已有镜头表（--regen-story 重新生成）")

    for c in story.get("characters", []):
        cdir = char_dir(paths, c["name"])
        face_ok = os.path.exists(os.path.join(cdir, "face_ref.jpg"))
        tri_ok = os.path.exists(os.path.join(cdir, "turnaround.jpg"))
        if face_ok and tri_ok:
            info("角色 %s 已存在（含三视图），跳过" % c["name"])
            continue
        if not face_ok:
            do_char_gen(cfg, paths, c["name"], c.get("desc_en") or c.get("desc") or c["name"],
                        with_turnaround=True)
        elif not tri_ok:
            make_turnaround(cfg, paths, c["name"])

    for p in story.get("props", []):
        if os.path.exists(os.path.join(paths["props"], p["name"] + ".jpg")):
            info("道具 %s 已存在，跳过" % p["name"])
            continue
        do_prop_gen(cfg, paths, p["name"], p.get("desc_en") or p.get("desc") or p["name"])

    do_scenes(cfg, paths)
    do_frames(cfg, paths)

    only = "S01" if args.only_first else None
    do_videos(cfg, paths, only=only, force=args.force, wait=True, allow_partial=True)
    # 回忆镜头不走进视频通道：直接用旧剧集的片段剪（--only-first 时也一起剪好）
    if any(s.get("reuse") for s in story["shots"]):
        do_recall(cfg, paths, force=args.force)

    if args.music:
        try:
            duration = sum(float(s.get("duration") or 8) for s in story["shots"])
            do_music(cfg, paths, duration=duration + 2,
                     caption=args.music_caption)
        except SystemExit:
            warn("配乐失败，保持无配乐")
    else:
        info("未启用配乐（加 --music 开启；通道由配置里的 music.provider 决定：comfyui / volc）")

    if args.only_first:
        info("仅生成 S01，跳过合成。验收后运行: ac.py auto <dir>（不加 --only-first）")
        return
    final = do_assemble(cfg, paths, use_subs=args.subs)
    do_audit(cfg, paths)
    info("全流程完成，用时 %.1f 分钟" % ((time.time() - t0) / 60))
    print("\n成片: " + final)


# ----------------------------------------------------------------------------- status

def cmd_status(args):
    cfg, paths = load_project(args.dir)
    shots = load_json(paths["shots"])["shots"]
    print("\n项目: %s" % cfg.get("title"))
    print("目录: %s" % paths["root"])
    print("Agnes: %s（视频）/ %s（图片）/ %s（文本）" % (
        cfg["agnes"].get("video_model"), cfg["agnes"].get("image_model"), cfg["agnes"].get("text_model")))
    print()
    print("%-6s %-8s %-10s %-10s %s" % ("镜头", "时长", "首帧", "视频", "旁白"))
    print("-" * 70)
    done_f = done_v = 0
    for s in shots:
        f = os.path.join(paths["frames"], s["id"] + ".jpg")
        c = os.path.join(paths["clips"], s["id"] + ".mp4")
        fs = "OK" if os.path.exists(f) else "-"
        cs = "OK" if os.path.exists(c) else "-"
        done_f += 1 if os.path.exists(f) else 0
        done_v += 1 if os.path.exists(c) else 0
        print("%-6s %-8s %-10s %-10s %s" % (s["id"], s.get("duration", 8), fs, cs, (s.get("line") or "")[:28]))
    print("-" * 70)
    print("首帧 %d/%d   视频 %d/%d" % (done_f, len(shots), done_v, len(shots)))
    bgm = os.path.join(paths["audio"], "bgm.mp3")
    final = os.path.join(paths["out"], "final.mp4")
    print("配乐: %s   成片: %s" % ("OK" if os.path.exists(bgm) else "-", "OK" if os.path.exists(final) else "-"))
    names = all_char_names(paths)
    if names:
        print("角色: " + ", ".join(names))
        if paths.get("cast"):
            print("共享角色库: " + paths["cast"])
    if os.path.isdir(paths["props"]):
        names = [f[:-4] for f in os.listdir(paths["props"]) if f.endswith(".jpg")]
        if names:
            print("道具: " + ", ".join(names))


# ----------------------------------------------------------------------------- setup

def cmd_setup(args):
    cfg = load_global_cfg()
    cfg.setdefault("agnes", {})
    cfg.setdefault("music", {})

    supplied = any([args.agnes_endpoint, args.agnes_key, args.agnes_video_model,
                    args.agnes_image_model, args.agnes_text_model,
                    args.agnes_video_endpoint, args.agnes_video_key,
                    args.music_endpoint, args.music_auth,
                    getattr(args, "music_provider", None),
                    getattr(args, "volc_ak", None), getattr(args, "volc_sk", None)])

    def ask(label, cur, secret=False):
        shown = ("已设置" if cur else "空") if secret else (cur or "空")
        v = input("  %s [%s]: " % (label, shown)).strip()
        return v or cur

    if supplied:
        if args.agnes_endpoint:
            cfg["agnes"]["endpoint"] = args.agnes_endpoint
        if args.agnes_key:
            cfg["agnes"]["key"] = args.agnes_key
        if args.agnes_video_model:
            cfg["agnes"]["video_model"] = args.agnes_video_model
        if args.agnes_image_model:
            cfg["agnes"]["image_model"] = args.agnes_image_model
        if args.agnes_text_model:
            cfg["agnes"]["text_model"] = args.agnes_text_model
        if args.agnes_video_endpoint:
            cfg["agnes"]["video_endpoint"] = args.agnes_video_endpoint
        if args.agnes_video_key:
            cfg["agnes"]["video_key"] = args.agnes_video_key
        if args.music_endpoint:
            cfg["music"]["endpoint"] = args.music_endpoint
        if args.music_auth:
            cfg["music"]["auth"] = args.music_auth
        if getattr(args, "music_provider", None):
            cfg["music"]["provider"] = args.music_provider
        if getattr(args, "volc_ak", None):
            cfg["music"].setdefault("volc", {})["ak"] = args.volc_ak
        if getattr(args, "volc_sk", None):
            cfg["music"].setdefault("volc", {})["sk"] = args.volc_sk
    else:
        print("配置 Agnes Clip · 平哥分享版（直接回车 = 保留当前值）\n")
        cfg["agnes"]["endpoint"] = ask("Agnes 端点", cfg["agnes"].get("endpoint") or DEFAULT_AGNES["endpoint"])
        cfg["agnes"]["key"] = ask("Agnes key", cfg["agnes"].get("key"), secret=True)
        cfg["agnes"]["video_model"] = ask("视频模型", cfg["agnes"].get("video_model") or DEFAULT_AGNES["video_model"])
        cfg["agnes"]["image_model"] = ask("图片模型", cfg["agnes"].get("image_model") or DEFAULT_AGNES["image_model"])
        cfg["agnes"]["text_model"] = ask("文本模型（写剧本）", cfg["agnes"].get("text_model") or DEFAULT_AGNES["text_model"])
        print("\n[可选] 视频专用通道（独立 key / 独立入口，只用于视频；留空 = 用上面的主 key）")
        cfg["agnes"]["video_endpoint"] = ask("视频端点", cfg["agnes"].get("video_endpoint"))
        cfg["agnes"]["video_key"] = ask("视频 key", cfg["agnes"].get("video_key"), secret=True)
        print("\n[可选] 配乐：comfyui（有显卡）或 volc（火山引擎，无卡也能跑），不需要直接回车")
        cfg["music"]["provider"] = ask("配乐通道 comfyui/volc",
                                       cfg["music"].get("provider") or "comfyui")
        if (cfg["music"].get("provider") or "").lower() in ("comfyui", "comfy", "local"):
            cfg["music"]["endpoint"] = ask("ComfyUI 端点", cfg["music"].get("endpoint"))
            cfg["music"]["auth"] = ask("Basic Auth user:pass", cfg["music"].get("auth"), secret=True)
        else:
            mvolc = cfg["music"].setdefault("volc", {})
            mvolc["ak"] = ask("火山 AccessKey", mvolc.get("ak"))
            mvolc["sk"] = ask("火山 SecretKey", mvolc.get("sk"), secret=True)

    os.makedirs(os.path.dirname(GLOBAL_CFG_PATH), exist_ok=True)
    save_json(GLOBAL_CFG_PATH, cfg)
    print("\n已写入: " + GLOBAL_CFG_PATH)
    print("这个文件只在本机，发布 skill 时不会带走任何密钥。")

    if args.check:
        for label, ep, key in (
            ("主通道", cfg["agnes"].get("endpoint"), cfg["agnes"].get("key")),
            ("视频通道", cfg["agnes"].get("video_endpoint"), cfg["agnes"].get("video_key")),
        ):
            if not ep:
                continue
            try:
                d = http_json(ep.rstrip("/") + "/models",
                              headers={"Authorization": "Bearer " + (key or "")}, timeout=15)
                ids = [m.get("id") for m in d.get("data", [])]
                print("\n%s: OK，%d 个模型" % (label, len(ids)))
                if "agnes-video-2.5-flash" in ids:
                    print("  含 agnes-video-2.5-flash ✓")
            except Exception as e:
                print("\n%s: 不通（%s）" % (label, e))
        if (cfg.get("music") or {}).get("provider") == "volc":
            r = _volc_probe(cfg)
            print("\n配乐(火山): %s %s" % ("OK" if r.get("ok") else "不通",
                                          r.get("note") or r.get("message") or ""))


# ----------------------------------------------------------------------------- config UI

CONFIG_UI_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agnes Clip 配置</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%232563eb'/%3E%3Ctext x='16' y='22' font-size='16' font-family='sans-serif' font-weight='bold' fill='white' text-anchor='middle'%3EA%3C/text%3E%3C/svg%3E">
<style>
  :root{--bg:#f5f6f8;--card:#fff;--text:#1c1e21;--muted:#6b7280;--line:#e5e7eb;--accent:#2563eb;--ok:#15803d;--err:#b91c1c;--warn:#b45309}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif}
  .wrap{max-width:1000px;margin:0 auto;padding:24px 20px 70px}
  h1{font-size:21px;margin:0 0 3px}
  .sub{color:var(--muted);margin-bottom:16px;font-size:13px}
  .sub code{background:#eef1f5;padding:1px 5px;border-radius:4px;font-size:12px}

  /* ---- TAB ---- */
  .tabs{display:flex;gap:4px;flex-wrap:wrap;border-bottom:2px solid var(--line);margin-bottom:18px;position:sticky;top:0;background:var(--bg);z-index:20;padding-top:4px}
  .tab{border:0;background:transparent;padding:9px 15px;font:inherit;font-size:13.5px;color:var(--muted);cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-2px;border-radius:6px 6px 0 0}
  .tab:hover{color:var(--text);background:#eef1f5}
  .tab.on{color:var(--accent);border-bottom-color:var(--accent);font-weight:600;background:#eaf1fe}
  .tab .dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--ok);margin-left:6px;vertical-align:middle}
  .tab .dot.off{background:#cbd5e1}
  .pane{display:none}
  .pane.on{display:block}

  .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px 14px;margin-bottom:14px}
  .card h2{font-size:15px;margin:0 0 2px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
  .tag{font-size:11px;font-weight:400;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:1px 8px;background:#fafbfc}
  .hint{color:var(--muted);font-size:12px;margin:4px 0 12px}
  .grid{display:grid;grid-template-columns:118px 1fr;gap:10px 12px;align-items:center}
  .grid.tight{grid-template-columns:1fr 1fr;gap:10px 12px;align-items:center}
  label{color:#374151;font-size:13px}
  input,select,textarea{width:100%;padding:8px 10px;border:1px solid var(--line);border-radius:8px;font:inherit;background:#fff;color:var(--text)}
  input:focus,select:focus,textarea:focus{outline:2px solid #bfdbfe;border-color:var(--accent)}
  input[readonly]{background:#f6f7f9;color:var(--muted)}
  .row{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px;align-items:center}
  button{border:1px solid var(--line);background:#fff;color:var(--text);padding:8px 14px;border-radius:8px;font:inherit;cursor:pointer}
  button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
  button.ghost{color:var(--muted)}
  button:hover{filter:brightness(.97)}
  .status{font-size:12px;margin-top:8px;min-height:18px}
  .ok{color:var(--ok)} .err{color:var(--err)} .muted{color:var(--muted)} .warn{color:var(--warn)}
  .hide{display:none}
  .foot{position:sticky;bottom:0;background:linear-gradient(to top,var(--bg) 72%,transparent);padding:14px 0 4px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}

  /* 总览表 */
  table{width:100%;border-collapse:collapse;font-size:13px}
  th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}
  th{font-size:12px;color:var(--muted);font-weight:600;background:#fafbfc;position:sticky;top:0}
  td code{font-size:12px;background:#f2f4f7;padding:1px 5px;border-radius:4px;word-break:break-all}
  .pill{display:inline-block;font-size:11px;padding:1px 8px;border-radius:999px;border:1px solid var(--line);background:#fafbfc;color:var(--muted)}
  .pill.on{color:var(--ok);border-color:#bbf7d0;background:#f0fdf4}
  .pill.off{color:#94a3b8}
  .pill.hot{color:var(--warn);border-color:#fde68a;background:#fffbeb}
  .note{font-size:12px;color:var(--muted);background:#fafbfc;border:1px solid var(--line);border-left:3px solid var(--accent);padding:8px 11px;border-radius:0 8px 8px 0;margin:10px 0}
  .kv{display:grid;grid-template-columns:150px 1fr;gap:6px 12px;font-size:13px}
  .kv b{font-weight:600;color:#374151}
</style>
</head>
<body>
<div class="wrap">
  <h1>Agnes Clip 配置</h1>
  <div class="sub">所有内容只写进本机 <code>~/.workbuddy/agnes-clip.json</code>，不会上传。带 <span class="pill hot">项目级</span> 标记的项可在每个项目开工时单独选择。</div>

  <div class="tabs" id="tabs">
    <button class="tab on" data-pane="overview">总览<span class="dot off" id="dot-overview"></span></button>
    <button class="tab" data-pane="image">生图<span class="dot off" id="dot-image"></span></button>
    <button class="tab" data-pane="text">推理 / 编剧<span class="dot off" id="dot-text"></span></button>
    <button class="tab" data-pane="video">生视频<span class="dot off" id="dot-video"></span></button>
    <button class="tab" data-pane="voice">配音</button>
    <button class="tab" data-pane="music">配乐</button>
    <button class="tab" data-pane="system">系统</button>
  </div>

  <!-- ============ 总览 ============ -->
  <div class="pane on" id="pane-overview">
    <div class="card">
      <h2>各流程 Agent 配置一览 <span class="tag">谁在干活、用哪条通道</span></h2>
      <div class="hint">这张表是本页所有配置的实时汇总。改完任一 TAB 回来刷新即可看到变化。点「保存配置」生效。</div>
      <table id="tbl-overview">
        <thead><tr><th style="width:96px">流程</th><th style="width:120px">通道</th><th style="width:150px">模型</th><th>端点</th><th style="width:110px">Key</th><th style="width:120px">备注</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
    <div class="card">
      <h2>项目级选择 <span class="tag">每个项目开工时可单独指定</span></h2>
      <div class="hint">在项目目录跑 <code>ac.py pick-image &lt;项目目录&gt;</code> 可为单个项目指定生图通道，写进该项目的 <code>project.json</code>，不影响其它项目。</div>
      <div class="grid">
        <label>当前项目</label><input id="ov-project" placeholder="填项目目录路径（例：~/projects/我的片子）">
        <label>项目出图通道</label>
        <select id="ov-project-channel">
          <option value="">（跟随全局设置）</option>
          <option value="agnes">Agnes 生图</option>
          <option value="gpt-image">GPT Image 生图</option>
          <option value="openai">自定义 OpenAI 兼容</option>
        </select>
      </div>
      <div class="row">
        <button id="ov-read">读取项目设置</button>
        <button id="ov-write">写入项目</button>
        <span class="status" id="st-ov"></span>
      </div>
    </div>
  </div>

  <!-- ============ 生图 ============ -->
  <div class="pane" id="pane-image">
    <div class="card">
      <h2>出图通道 <span class="tag">角色定妆 / 道具 / 场景板 / 首帧</span></h2>
      <div class="hint">选一个通道，下面的端点 / key / 模型都跟着切换，保存后全片生效。</div>
      <div class="grid">
        <label>通道</label>
        <select id="image-provider">
          <option value="agnes">Agnes（agnes-image-2.5-flash）</option>
          <option value="gpt-image">GPT Image（gpt-image-1 / gpt-image-2）</option>
          <option value="openai">自定义 OpenAI 兼容接口</option>
        </select>
        <label>端点</label><input id="image-endpoint" placeholder="https://apihub.agnes-ai.cn/v1">
        <label>API Key</label><input id="image-key" type="password" placeholder="cpk-... 或 sk-...">
        <label>模型</label><input id="image-model" placeholder="agnes-image-2.5-flash">
        <label>尺寸 / 比例</label>
        <div style="display:flex;gap:10px">
          <input id="image-size" placeholder="2K" style="max-width:120px">
          <input id="image-ratio" placeholder="9:16" style="max-width:120px">
        </div>
      </div>
      <div class="row"><button data-test="image">测试连接</button><span class="status" id="st-image"></span></div>
      <div class="note" id="image-note"></div>
    </div>
    <div class="card">
      <h2>备选通道地址 <span class="tag">一键填入，改完再切</span></h2>
      <div class="hint">这些是常用中转。点一下填进上面的端点 / key / 模型，key 隐藏显示。</div>
      <div class="row" id="image-presets"></div>
    </div>
  </div>

  <!-- ============ 推理 ============ -->
  <div class="pane" id="pane-text">
    <div class="card">
      <h2>推理 / 编剧 <span class="tag">写剧本、分镜、对白</span></h2>
      <div class="hint">默认用 WorkBuddy 当前会话模型，不需要任何 key。要固定用某个模型就选第二项。</div>
      <div class="grid">
        <label>来源</label>
        <select id="text-provider">
          <option value="workbuddy">WorkBuddy 默认（推荐，无需 key）</option>
          <option value="api">外部文本 API（OpenAI 兼容）</option>
        </select>
        <div id="text-fields" class="hide" style="grid-column:1/-1">
          <div class="grid">
            <label>端点</label><input id="text-endpoint" placeholder="https://.../v1">
            <label>API Key</label><input id="text-key" type="password" placeholder="sk-...">
            <label>模型</label><input id="text-model" placeholder="模型名">
          </div>
        </div>
      </div>
      <div class="row"><button data-test="text">测试连接</button><span class="status" id="st-text"></span></div>
    </div>
  </div>

  <!-- ============ 生视频 ============ -->
  <div class="pane" id="pane-video">
    <div class="card">
      <h2>生视频 <span class="tag">agnes-video-2.5-flash</span></h2>
      <div class="hint">视频可以单独选渠道、单独配 key。免费通道走 apihub，付费通道走 api。</div>
      <div class="grid">
        <label>通道</label>
        <select id="video-preset">
          <option value="free">Agnes 免费通道（apihub）</option>
          <option value="paid">Agnes 付费通道（api）</option>
          <option value="custom">自定义</option>
        </select>
        <label>端点</label><input id="video-endpoint" placeholder="https://api.agnes-ai.cn/v1">
        <label>API Key</label><input id="video-key" type="password" placeholder="sk-...（只用于视频）">
        <label>模型</label><input id="video-model" placeholder="agnes-video-2.5-flash">
        <label>并发 / 轮询</label>
        <div style="display:flex;gap:10px">
          <input id="video-jobs" type="number" min="1" max="10" style="max-width:90px"> <span class="muted">路并发</span>
          <input id="video-poll" type="number" min="5" step="5" style="max-width:100px"> <span class="muted">秒轮询</span>
        </div>
        <label>默认时长 / 画幅</label>
        <div style="display:flex;gap:10px">
          <input id="video-seconds" type="number" min="4" max="12" style="max-width:90px"> <span class="muted">秒</span>
          <select id="video-ratio" style="max-width:120px">
            <option value="9:16">9:16 竖屏</option>
            <option value="16:9">16:9 横屏</option>
            <option value="1:1">1:1 方形</option>
            <option value="4:3">4:3</option>
            <option value="3:4">3:4</option>
          </select>
        </div>
      </div>
      <div class="row"><button data-test="video">测试连接</button><span class="status" id="st-video"></span></div>
    </div>
    <div class="card">
      <h2>生视频·高级 <span class="tag">队列满、重试、首帧上传</span></h2>
      <div class="grid">
        <label>单次超时</label><input id="video-timeout" type="number" min="300" step="300" style="max-width:130px">
        <label>每轮重试</label><input id="video-attempts" type="number" min="1" max="20" style="max-width:130px">
        <label>总重试轮数</label><input id="video-rounds" type="number" min="1" max="200" style="max-width:130px">
        <label>首帧上传</label><input id="video-frame-upload" placeholder="留空 = 直接传 base64（推荐）">
      </div>
      <div class="hint">首帧上传命令里用 <code>{file}</code> 代表本地文件路径，命令要输出一行公网 URL。</div>
    </div>
  </div>

  <!-- ============ 配音 ============ -->
  <div class="pane" id="pane-voice">
    <div class="card">
      <h2>配音 <span class="tag">edge-tts，按角色分配音色</span></h2>
      <div class="hint">默认音色用于所有角色；可以在 <code>shots.json</code> 的角色里单独指定 <code>voice</code> 覆盖。</div>
      <div class="grid">
        <label>默认音色</label><input id="voice-default" list="voice-list" placeholder="zh-CN-XiaoxiaoNeural">
        <label>旁白音色</label><input id="voice-vo" list="voice-list" placeholder="zh-CN-YunxiNeural">
        <label>语速 / 音量</label>
        <div style="display:flex;gap:10px">
          <input id="voice-rate" placeholder="+0%" style="max-width:110px">
          <input id="voice-volume" type="number" min="0.1" max="4" step="0.1" style="max-width:110px">
        </div>
      </div>
      <datalist id="voice-list">
        <option value="zh-CN-XiaoxiaoNeural"><option value="zh-CN-YunxiNeural"><option value="zh-CN-XiaoyiNeural">
        <option value="zh-CN-YunjianNeural"><option value="zh-CN-YunyangNeural"><option value="zh-CN-XiaochenNeural">
        <option value="zh-CN-XiaohanNeural"><option value="zh-CN-liaoning-XiaobeiNeural"><option value="zh-CN-shaanxi-XiaoniNeural">
        <option value="en-US-AriaNeural"><option value="en-US-GuyNeural">
      </datalist>
      <div class="row">
        <input id="voice-sample" value="陈姐，还是一碗阳春面，不要葱。" style="flex:1;min-width:220px">
        <button id="btn-tts">试听</button>
        <span class="status" id="st-tts"></span>
      </div>
      <audio id="tts-audio" controls class="hide" style="width:100%;margin-top:10px"></audio>
    </div>
  </div>

  <!-- ============ 配乐 ============ -->
  <div class="pane" id="pane-music">
    <div class="card">
      <h2>配乐 <span class="tag">两条通道任选一条</span></h2>
      <div class="hint">有显卡走 ComfyUI（不花钱）；没卡或排队太久走火山引擎（0.002 元/秒，100 秒约两毛）。留空也能出片，只是没背景音乐。</div>
      <div class="grid">
        <label>通道</label>
        <select id="music-provider">
          <option value="comfyui">ComfyUI · MiniMax Music3（本地/远程）</option>
          <option value="volc">火山引擎 · 豆包音乐（无显卡也能跑）</option>
        </select>
      </div>
    </div>

    <div class="card" id="card-music-comfy">
      <h2>ComfyUI 参数 <span class="tag">provider = comfyui 时生效</span></h2>
      <div class="grid">
        <label>端点</label><input id="music-endpoint" placeholder="https://comfyui.example.com">
        <label>Basic Auth</label><input id="music-auth" placeholder="user:password">
      </div>
      <div class="grid" style="margin-top:10px">
        <label>UNet</label><input id="music-unet" placeholder="minimax_music3_dit_int8_convrot.safetensors">
        <label>CLIP</label><input id="music-clip" placeholder="minimax_music3_text_encoder_pruned_int8_convrot.safetensors">
        <label>VAE</label><input id="music-vae" placeholder="minimax_music3_dav.safetensors">
        <label>步数 / CFG</label>
        <div style="display:flex;gap:10px">
          <input id="music-steps" type="number" min="8" max="60" style="max-width:90px">
          <input id="music-cfg" type="number" min="0.5" max="6" step="0.1" style="max-width:90px">
        </div>
      </div>
    </div>

    <div class="card" id="card-music-volc">
      <h2>火山引擎参数 <span class="tag">provider = volc 时生效</span></h2>
      <div class="hint">AI 音乐生成（豆包音乐模型）。AK/SK 在火山控制台右上角「密钥管理」里建，建议用子账号。</div>
      <div class="grid">
        <label>AccessKey</label><input id="music-volc-ak" placeholder="AKLT...">
        <label>SecretKey</label><input id="music-volc-sk" type="password" placeholder="留空 = 保持原值">
        <label>计费入口</label>
        <select id="music-volc-action">
          <option value="GenBGMForTime">GenBGMForTime · 按时长后付费</option>
          <option value="GenBGM">GenBGM · 套餐包</option>
        </select>
        <label>模型版本</label><input id="music-volc-ver" placeholder="v5.0" style="max-width:120px">
      </div>
      <div class="hint" style="margin-top:10px">纯音乐单次上限 60 秒，更长的片子会自动分段生成再交叉淡化拼接；两个入口不互通，走错会报 200028。</div>
    </div>

    <div class="card">
      <h2>通用 <span class="tag">两条通道共用</span></h2>
      <div class="grid">
        <label>默认时长</label><input id="music-duration" type="number" min="10" step="5" style="max-width:120px">
        <label>默认提示词</label><input id="music-caption" placeholder="Cinematic instrumental score...">
      </div>
      <div class="row"><button data-test="music">测试连接</button><span class="status" id="st-music"></span></div>
    </div>
  </div>

  <!-- ============ 系统 ============ -->
  <div class="pane" id="pane-system">
    <div class="card">
      <h2>系统 <span class="tag">合成 / 字幕用的 ffmpeg</span></h2>
      <div class="grid">
        <label>ffmpeg 路径</label><input id="sys-ffmpeg" placeholder="ffmpeg">
        <label>配置文件</label><input id="sys-path" readonly class="muted">
      </div>
      <div class="hint">填 <code>ffmpeg</code> 表示用 PATH 里的；装了 imageio-ffmpeg 会自动找到。留空也能出片，只是不能用音效和字幕。</div>
    </div>
    <div class="card">
      <h2>并发与限额 <span class="tag">Agnes 账号硬限制</span></h2>
      <div class="hint">Agnes 账号最多 3 路并发、30 秒轮询一次。这两项改大了会被服务端限流或队列超时。</div>
      <div class="grid">
        <label>视频并发路数</label><input id="sys-jobs" type="number" min="1" max="10" style="max-width:130px">
        <label>轮询间隔（秒）</label><input id="sys-poll" type="number" min="5" step="5" style="max-width:130px">
      </div>
    </div>
  </div>

  <div class="foot">
    <button class="primary" id="save">保存配置</button>
    <button class="ghost" id="reload">重新读取</button>
    <span class="status" id="st-save"></span>
  </div>
</div>

<script>
const $ = (id) => document.getElementById(id);
let CFG = null;

/* 任何 JS 异常都显示出来，不要让整页变哑巴 */
window.addEventListener('error', (e) => {
  const st = document.getElementById('st-save');
  if (st) { st.className = 'status err'; st.textContent = 'JS 错误：' + (e.message || e) + '（第 ' + (e.lineno||'?') + ' 行）'; }
});
window.addEventListener('unhandledrejection', (e) => {
  const st = document.getElementById('st-save');
  if (st) { st.className = 'status err'; st.textContent = '异步错误：' + ((e.reason && e.reason.message) || e.reason); }
});

/* ---- TAB 切换 ---- */
document.querySelectorAll('.tab').forEach(t=>{
  t.addEventListener('click',()=>{
    document.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));
    document.querySelectorAll('.pane').forEach(x=>x.classList.remove('on'));
    t.classList.add('on');
    $('pane-'+t.dataset.pane).classList.add('on');
    if(t.dataset.pane==='overview') renderOverview();
  });
});

/* ---- 出图通道预设 ---- */
const IMAGE_PRESETS = [
  {name:'Agnes 2.5', provider:'agnes', endpoint:'https://apihub.agnes-ai.cn/v1', model:'agnes-image-2.5-flash', size:'2K'},
  {name:'GPT Image 1', provider:'gpt-image', endpoint:'https://api.openai.com/v1', model:'gpt-image-1', size:'1024x1536'},
  {name:'GPT Image 2', provider:'gpt-image', endpoint:'https://api.openai.com/v1', model:'gpt-image-2', size:'1024x1536'},
  {name:'自定义中转', provider:'gpt-image', endpoint:'', model:'gpt-image-1', size:'1024x1536'},
];
function renderImagePresets(){
  const box = $('image-presets'); box.innerHTML='';
  IMAGE_PRESETS.forEach(p=>{
    const b=document.createElement('button');
    b.textContent=p.name;
    b.title=p.endpoint+'  ·  '+p.model;
    b.addEventListener('click',()=>{
      $('image-provider').value=p.provider;
      $('image-endpoint').value=p.endpoint;
      $('image-model').value=p.model;
      $('image-size').value=p.size;
      syncImageNote();
      say('st-image',true,'已填入 '+p.name+'，key 请自行补上后点「保存配置」');
    });
    box.appendChild(b);
  });
}
const IMAGE_NOTE = {
  'agnes':'Agnes 生图：支持多张参考图（首帧要锁人脸 + 场景板时必须用它）。',
  'gpt-image':'GPT Image 生图：质量高、人物一致性更稳，支持多图参考；尺寸用 1024x1536 这类像素值，不是 2K。',
  'openai':'自定义 OpenAI 兼容生图接口：端点要带 /v1，模型名按对方文档填。',
};
function syncImageNote(){ $('image-note').textContent = IMAGE_NOTE[$('image-provider').value] || ''; }

function fill(cfg){
  CFG = cfg;
  const t = cfg.text || {}, img = cfg.image || {}, v = cfg.video || {};
  const vo = cfg.voices || {}, mu = cfg.music || {}, sy = cfg.system || {};
  $('text-provider').value = t.provider || 'workbuddy';
  $('text-endpoint').value = t.endpoint || '';
  $('text-key').value = t.key || '';
  $('text-model').value = t.model || '';
  $('image-provider').value = img.provider || 'agnes';
  $('image-endpoint').value = img.endpoint || '';
  $('image-key').value = img.key || '';
  $('image-model').value = img.model || '';
  $('image-size').value = img.size || '2K';
  $('image-ratio').value = img.ratio || '9:16';
  $('video-preset').value = v.preset || 'free';
  $('video-endpoint').value = v.endpoint || '';
  $('video-key').value = v.key || '';
  $('video-model').value = v.model || '';
  $('video-jobs').value = v.jobs || 3;
  $('video-poll').value = v.poll || 30;
  $('video-seconds').value = v.seconds || 8;
  $('video-ratio').value = v.ratio || '9:16';
  $('video-timeout').value = v.timeout || 7200;
  $('video-attempts').value = v.attempts || 3;
  $('video-rounds').value = v.rounds || 40;
  $('video-frame-upload').value = v.frame_upload || '';
  $('voice-default').value = vo.default || '';
  $('voice-vo').value = vo.VO || '';
  $('voice-rate').value = vo.rate || '+0%';
  $('voice-volume').value = vo.volume || 1.6;
  $('music-provider').value = mu.provider || 'comfyui';
  $('music-endpoint').value = mu.endpoint || '';
  $('music-auth').value = mu.auth || '';
  $('music-unet').value = mu.unet || '';
  $('music-clip').value = mu.clip || '';
  $('music-vae').value = mu.vae || '';
  $('music-steps').value = mu.steps || 28;
  $('music-cfg').value = mu.cfg || 1.8;
  const mv = mu.volc || {};
  $('music-volc-ak').value = mv.ak || '';
  $('music-volc-sk').value = mv.sk || '';
  $('music-volc-action').value = mv.action || 'GenBGMForTime';
  $('music-volc-ver').value = mv.model_version || 'v5.0';
  $('music-duration').value = mu.duration || 100;
  $('music-caption').value = mu.caption || '';
  $('sys-ffmpeg').value = sy.ffmpeg || 'ffmpeg';
  $('sys-path').value = sy.config_path || '';
  $('sys-jobs').value = v.jobs || 3;
  $('sys-poll').value = v.poll || 30;
  toggle(); syncMusicProvider(); syncImageNote(); renderImagePresets(); renderOverview();
}
function syncMusicProvider(){
  const p = $('music-provider').value;
  $('card-music-comfy').classList.toggle('hide', p !== 'comfyui');
  $('card-music-volc').classList.toggle('hide', p !== 'volc');
}
$('music-provider').addEventListener('change', syncMusicProvider);
function toggle(){
  $('text-fields').classList.toggle('hide', $('text-provider').value === 'workbuddy');
}
function num(id, dflt){ const n = parseFloat($(id).value); return isNaN(n) ? dflt : n; }
function collect(){
  return {
    text:{provider:$('text-provider').value, endpoint:$('text-endpoint').value.trim(), key:$('text-key').value.trim(), model:$('text-model').value.trim()},
    image:{provider:$('image-provider').value, endpoint:$('image-endpoint').value.trim(), key:$('image-key').value.trim(), model:$('image-model').value.trim(), size:$('image-size').value.trim(), ratio:$('image-ratio').value.trim()},
    video:{preset:$('video-preset').value, endpoint:$('video-endpoint').value.trim(), key:$('video-key').value.trim(), model:$('video-model').value.trim(),
           jobs:num('video-jobs',3), poll_interval:num('video-poll',30), seconds:num('video-seconds',8), ratio:$('video-ratio').value,
           timeout:num('video-timeout',7200), attempts:num('video-attempts',3), rounds:num('video-rounds',40),
           frame_upload:$('video-frame-upload').value.trim()},
    voices:{default:$('voice-default').value.trim(), VO:$('voice-vo').value.trim(), rate:$('voice-rate').value.trim(), volume:num('voice-volume',1.6)},
    music:{provider:$('music-provider').value, endpoint:$('music-endpoint').value.trim(), auth:$('music-auth').value.trim(), unet:$('music-unet').value.trim(), clip:$('music-clip').value.trim(), vae:$('music-vae').value.trim(),
           steps:num('music-steps',28), cfg:num('music-cfg',1.8), duration:num('music-duration',100), caption:$('music-caption').value.trim(),
           volc:{ak:$('music-volc-ak').value.trim(), sk:$('music-volc-sk').value.trim(), action:$('music-volc-action').value, model_version:$('music-volc-ver').value.trim()}},
    system:{ffmpeg:$('sys-ffmpeg').value.trim()}
  };
}
function say(id, ok, msg){ const e=$(id); e.className='status '+(ok?'ok':'err'); e.textContent=msg; }

/* ---- 总览表 ---- */
function mask(k){
  if(!k) return '—';
  return k.length>10 ? k.slice(0,6)+'…'+k.slice(-4) : '（短）';
}
function renderOverview(){
  const c = collect();
  const rows = [
    ['出图', c.image.provider, c.image.model, c.image.endpoint, c.image.key, c.image.size+' / '+c.image.ratio, 'image'],
    ['推理/编剧', c.text.provider==='workbuddy'?'workbuddy':'api', c.text.model||'（会话模型）', c.text.endpoint||'—', c.text.key, 'OpenAI 兼容', 'text'],
    ['生视频', c.video.preset, c.video.model, c.video.endpoint, c.video.key, c.video.jobs+' 路 / '+(c.video.poll_interval||30)+'s', 'video'],
    ['配音', 'edge-tts', $('voice-default').value, '本机', '', $('voice-rate').value, null],
    ['配乐', c.music.provider==='volc' ? 'volc' : 'comfyui',
     c.music.provider==='volc' ? ('豆包音乐 '+(c.music.volc.model_version||'v5.0'))
       : ($('music-unet').value ? 'MiniMax Music3' : ''),
     c.music.provider==='volc' ? 'open.volcengineapi.com' : c.music.endpoint,
     c.music.provider==='volc' ? c.music.volc.ak : c.music.auth,
     c.music.provider==='volc' ? (c.music.volc.action||'GenBGMForTime') : ($('music-steps').value+' 步'), null],
    ['视频首帧', c.video.frame_upload? '上传命令':'base64 直传', '—', '—', '', c.video.frame_upload?'已配置':'推荐', null],
  ];
  const tb = document.querySelector('#tbl-overview tbody');
  tb.innerHTML='';
  rows.forEach(r=>{
    const tr=document.createElement('tr');
    tr.innerHTML = '<td><b>'+r[0]+'</b></td>'
      + '<td><span class="pill '+(r[1]?'on':'off')+'">'+esc(r[1]||'—')+'</span></td>'
      + '<td><code>'+esc(r[2]||'—')+'</code></td>'
      + '<td><code>'+esc(r[3]||'—')+'</code></td>'
      + '<td><code>'+esc(mask(r[4]))+'</code></td>'
      + '<td class="muted">'+esc(r[5])+'</td>';
    tb.appendChild(tr);
  });
  // TAB 上的状态点
  const dots = {image:c.image.endpoint&&c.image.key, text:true, video:c.video.endpoint&&c.video.key};
  for(const k in dots){ const d=$('dot-'+k); if(d) d.classList.toggle('off', !dots[k]); }
  const d0=$('dot-overview'); if(d0) d0.classList.remove('off');
}
function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

/* ---- 项目级通道 ---- */
$('ov-read').addEventListener('click', async ()=>{
  const dir=$('ov-project').value.trim();
  if(!dir){ say('st-ov',false,'先填项目目录'); return; }
  try{
    const r=await fetch('/api/project?dir='+encodeURIComponent(dir));
    const d=await r.json();
    if(!d.ok){ say('st-ov',false,d.message||'读取失败'); return; }
    $('ov-project-channel').value=d.channel||'';
    say('st-ov',true,'已读取：'+(d.channel||'（跟随全局）'));
  }catch(e){ say('st-ov',false,'请求失败：'+e); }
});
$('ov-write').addEventListener('click', async ()=>{
  const dir=$('ov-project').value.trim();
  if(!dir){ say('st-ov',false,'先填项目目录'); return; }
  try{
    const r=await fetch('/api/project',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({dir:dir, channel:$('ov-project-channel').value})});
    const d=await r.json();
    if(d.ok){ say('st-ov',true,'已写入：'+dir); } else { say('st-ov',false,d.message||'写入失败'); }
  }catch(e){ say('st-ov',false,'请求失败：'+e); }
});

/* ---- 测试 ---- */
async function test(kind){
  const st = 'st-'+kind; say(st,true,'测试中…');
  try{
    const r = await fetch('/api/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind, config:collect()})});
    const d = await r.json();
    if(d.ok){ say(st,true,'连接成功' + (d.count!=null?('，'+d.count+' 个模型'):'') + (d.has_model===false?'（未找到指定模型）':'') + (d.note?('；'+d.note):'')); }
    else { say(st,false,'失败：'+(d.message||'未知错误')); }
  }catch(e){ say(st,false,'请求失败：'+e); }
}
document.querySelectorAll('[data-test]').forEach(b=>b.addEventListener('click',()=>test(b.dataset.test)));
$('text-provider').addEventListener('change', toggle);
$('image-provider').addEventListener('change', syncImageNote);
$('video-preset').addEventListener('change', ()=>{
  const v=$('video-preset').value;
  if(v==='free'){ $('video-endpoint').value='https://apihub.agnes-ai.cn/v1'; }
  if(v==='paid'){ $('video-endpoint').value='https://api.agnes-ai.cn/v1'; }
  if(v==='custom'){ $('video-endpoint').value=''; }
});
$('btn-tts').addEventListener('click', async ()=>{
  say('st-tts',true,'合成中…');
  $('tts-audio').classList.add('hide');
  try{
    const r = await fetch('/api/tts',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({voice:$('voice-default').value.trim(), rate:$('voice-rate').value.trim(),
                           volume:num('voice-volume',1.6), text:$('voice-sample').value})});
    if(!r.ok){ const d = await r.json().catch(()=>({message:'HTTP '+r.status})); say('st-tts',false,'失败：'+(d.message||'')); return; }
    const buf = await r.arrayBuffer();
    const url = URL.createObjectURL(new Blob([buf],{type:'audio/mpeg'}));
    const a = $('tts-audio'); a.src = url; a.classList.remove('hide'); a.play();
    say('st-tts',true,'好了，点播放听一下');
  }catch(e){ say('st-tts',false,'失败：'+e); }
});
$('save').addEventListener('click', async ()=>{
  say('st-save',true,'保存中…');
  const r = await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(collect())});
  const d = await r.json();
  if(d.ok){ say('st-save',true,'已保存到 ' + ($('sys-path').value || '~/.workbuddy/agnes-clip.json')); renderOverview(); }
  else { say('st-save',false,'保存失败：'+(d.message||'')); }
});
$('reload').addEventListener('click', ()=>{
  fetch('/api/config').then(r=>r.json()).then(fill).then(()=>say('st-save',true,'已重新读取'));
});
fetch('/api/config').then(r=>r.json()).then(fill).catch(()=>say('st-save',false,'读取配置失败'));
fetch('/api/context').then(r=>r.json()).then(c=>{
  if(c && c.dir){ $('ov-project').value = c.dir; }
}).catch(()=>{});
</script>
</body>
</html>
"""


def _detect_preset(ep):
    """从端点反推视频通道类型，界面上回显正确的下拉项。"""
    e = (ep or "").lower()
    if "apihub" in e:
        return "free"
    if "api.agnes-ai" in e:
        return "paid"
    return "custom" if e else "free"


def _ui_public(cfg):
    a = cfg.get("agnes") or {}
    t = cfg.get("text") or {}
    v = cfg.get("video") or {}
    img = cfg.get("image") or {}
    vo = cfg.get("voices") or {}
    mu = cfg.get("music") or {}
    return {
        "text": {
            "provider": t.get("provider") or "workbuddy",
            "endpoint": t.get("endpoint") or "",
            "key": t.get("key") or "",
            "model": t.get("model") or (a.get("text_model") or ""),
        },
        "image": {
            "provider": img.get("provider") or "agnes",
            "endpoint": img.get("endpoint") or a.get("endpoint") or "",
            "key": img.get("key") or a.get("key") or "",
            "model": img.get("model") or a.get("image_model") or "agnes-image-2.5-flash",
            "size": img.get("size") or a.get("image_size") or "2K",
            "ratio": img.get("ratio") or a.get("image_ratio") or "9:16",
        },
        "video": {
            "preset": v.get("preset") or _detect_preset(v.get("endpoint") or a.get("video_endpoint") or a.get("endpoint")),
            "endpoint": v.get("endpoint") or a.get("video_endpoint") or a.get("endpoint") or "",
            "key": v.get("key") or a.get("video_key") or a.get("key") or "",
            "model": v.get("model") or a.get("video_model") or "agnes-video-2.5-flash",
            "jobs": v.get("jobs") or a.get("jobs") or 3,
            "poll": v.get("poll_interval") or a.get("poll_interval") or 30,
            "seconds": v.get("seconds") or a.get("seconds") or 8,
            "ratio": v.get("ratio") or a.get("aspect_ratio") or "9:16",
            "timeout": v.get("timeout") or a.get("timeout") or 7200,
            "attempts": v.get("attempts") or a.get("submit_attempts") or 3,
            "rounds": v.get("rounds") or a.get("submit_rounds") or 40,
            "frame_upload": v.get("frame_upload") if v.get("frame_upload") is not None
                            else (a.get("frame_upload") or ""),
        },
        "voices": {
            "default": vo.get("default") or DEFAULT_VOICES["default"],
            "VO": vo.get("VO") or DEFAULT_VOICES["VO"],
            "rate": vo.get("rate") or DEFAULT_VOICES["rate"],
            "volume": vo.get("volume") or DEFAULT_VOICES["volume"],
        },
        "music": {
            "provider": mu.get("provider") or DEFAULT_MUSIC["provider"],
            "endpoint": mu.get("endpoint") or "",
            "auth": mu.get("auth") or "",
            "unet": mu.get("unet") or DEFAULT_MUSIC["unet"],
            "clip": mu.get("clip") or DEFAULT_MUSIC["clip"],
            "vae": mu.get("vae") or DEFAULT_MUSIC["vae"],
            "steps": mu.get("steps") or DEFAULT_MUSIC["steps"],
            "cfg": mu.get("cfg") or DEFAULT_MUSIC["cfg"],
            "duration": mu.get("duration") or DEFAULT_MUSIC["duration"],
            "caption": mu.get("caption") if mu.get("caption") is not None else DEFAULT_MUSIC["caption"],
            "volc": _volc_cfg(cfg),
        },
        "system": {
            "ffmpeg": cfg.get("ffmpeg") or "ffmpeg",
            "config_path": GLOBAL_CFG_PATH,
        },
    }


def _ui_merge(cfg, data):
    out = json.loads(json.dumps(cfg or {}))
    for k in ("agnes", "text", "video", "image", "voices", "music"):
        out.setdefault(k, {})
    out["text"].update({
        "provider": ((data.get("text") or {}).get("provider") or "workbuddy").strip(),
        "endpoint": ((data.get("text") or {}).get("endpoint") or "").strip(),
        "key": ((data.get("text") or {}).get("key") or "").strip(),
        "model": ((data.get("text") or {}).get("model") or "").strip(),
    })
    img = data.get("image") or {}
    out["image"]["provider"] = (img.get("provider") or out["image"].get("provider") or "agnes").strip()
    if img.get("endpoint"):
        out["image"]["endpoint"] = img["endpoint"].strip()
        # 只在走 Agnes 出图时才同步主地址；切到 gpt-image 时不能覆盖 agnes.endpoint
        # （那是文本/视频也在用的主端点，覆盖了会把推理和视频一起带偏）
        if out["image"]["provider"] == "agnes":
            out["agnes"]["endpoint"] = img["endpoint"].strip()
    if img.get("key"):
        out["image"]["key"] = img["key"].strip()
        if out["image"]["provider"] == "agnes":
            out["agnes"]["key"] = img["key"].strip()
    if img.get("model"):
        out["image"]["model"] = img["model"].strip()
        if out["image"]["provider"] == "agnes":
            out["agnes"]["image_model"] = img["model"].strip()
    if img.get("size"):
        out["image"]["size"] = img["size"].strip()
        if out["image"]["provider"] == "agnes":
            out["agnes"]["image_size"] = img["size"].strip()
    if img.get("ratio"):
        out["image"]["ratio"] = img["ratio"].strip()
        if out["image"]["provider"] == "agnes":
            out["agnes"]["image_ratio"] = img["ratio"].strip()

    v = data.get("video") or {}
    out["video"]["preset"] = (v.get("preset") or "").strip()
    out["video"]["endpoint"] = (v.get("endpoint") or "").strip()
    out["video"]["key"] = (v.get("key") or "").strip()
    out["video"]["model"] = (v.get("model") or "").strip()
    out["video"]["jobs"] = max(1, int(v.get("jobs") or 3))
    out["video"]["poll_interval"] = max(5.0, float(v.get("poll_interval") or 30))
    out["video"]["seconds"] = max(4, min(12, float(v.get("seconds") or 8)))
    out["video"]["ratio"] = (v.get("ratio") or "9:16").strip()
    out["video"]["timeout"] = max(300, float(v.get("timeout") or 7200))
    out["video"]["attempts"] = max(1, int(v.get("attempts") or 3))
    out["video"]["rounds"] = max(1, int(v.get("rounds") or 40))
    out["video"]["frame_upload"] = (v.get("frame_upload") or "").strip()
    # 同步到 agnes 老字段，保证脚本各处读到的是同一份
    if out["video"]["endpoint"]:
        out["agnes"]["video_endpoint"] = out["video"]["endpoint"]
    if out["video"]["key"]:
        out["agnes"]["video_key"] = out["video"]["key"]
    if out["video"]["model"]:
        out["agnes"]["video_model"] = out["video"]["model"]
    out["agnes"]["jobs"] = out["video"]["jobs"]
    out["agnes"]["poll_interval"] = out["video"]["poll_interval"]
    out["agnes"]["seconds"] = str(int(out["video"]["seconds"]))
    out["agnes"]["aspect_ratio"] = out["video"]["ratio"]
    out["agnes"]["timeout"] = out["video"]["timeout"]
    out["agnes"]["submit_attempts"] = out["video"]["attempts"]
    out["agnes"]["submit_rounds"] = out["video"]["rounds"]
    out["agnes"]["frame_upload"] = out["video"]["frame_upload"]

    vo = data.get("voices") or {}
    out["voices"].update({
        "default": (vo.get("default") or DEFAULT_VOICES["default"]).strip(),
        "VO": (vo.get("VO") or DEFAULT_VOICES["VO"]).strip(),
        "rate": (vo.get("rate") or DEFAULT_VOICES["rate"]).strip(),
        "volume": float(vo.get("volume") or DEFAULT_VOICES["volume"]),
    })
    mu = data.get("music") or {}
    out["music"].update({
        "provider": (mu.get("provider") or out["music"].get("provider") or "comfyui").strip(),
        "endpoint": (mu.get("endpoint") or "").strip(),
        "auth": (mu.get("auth") or "").strip(),
        "unet": (mu.get("unet") or DEFAULT_MUSIC["unet"]).strip(),
        "clip": (mu.get("clip") or DEFAULT_MUSIC["clip"]).strip(),
        "vae": (mu.get("vae") or DEFAULT_MUSIC["vae"]).strip(),
        "steps": max(8, int(mu.get("steps") or DEFAULT_MUSIC["steps"])),
        "cfg": float(mu.get("cfg") or DEFAULT_MUSIC["cfg"]),
        "duration": max(10, float(mu.get("duration") or DEFAULT_MUSIC["duration"])),
        "caption": (mu.get("caption") or DEFAULT_MUSIC["caption"]).strip(),
    })
    mv = mu.get("volc") or {}
    old_v = (out["music"].get("volc") or {})
    out["music"]["volc"] = dict(DEFAULT_MUSIC["volc"], **old_v)
    if (mv.get("ak") or "").strip():
        out["music"]["volc"]["ak"] = mv["ak"].strip()
    # SK 输入框留空 = 保留原值，避免每次保存都得重填
    if (mv.get("sk") or "").strip():
        out["music"]["volc"]["sk"] = mv["sk"].strip()
    if mv.get("action"):
        out["music"]["volc"]["action"] = mv["action"].strip()
    if (mv.get("model_version") or "").strip():
        out["music"]["volc"]["model_version"] = mv["model_version"].strip()
    sy = data.get("system") or {}
    ff = (sy.get("ffmpeg") or "").strip()
    out["ffmpeg"] = ff or "ffmpeg"
    return out


def _volc_probe(cfg):
    """用 QuerySong 打一个空任务：签名对不对能立刻看出来，业务报「任务不存在」反而是通的。"""
    vc = _volc_cfg(cfg)
    if not (vc.get("ak") and vc.get("sk")):
        return {"ok": False, "message": "没填 AccessKey / SecretKey（火山控制台右上角「密钥管理」新建）"}
    payload = json.dumps({"TaskID": "agnes-clip-connect-test"}, ensure_ascii=False).encode("utf-8")
    try:
        headers, query = _volc_sign(vc, payload, "QuerySong", vc.get("api_version") or "2024-08-12")
        url = "https://%s/?%s" % (vc.get("host") or "open.volcengineapi.com", query)
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                body = json.loads(r.read().decode("utf-8", "ignore"))
        except urllib.error.HTTPError as e:
            body = json.loads(e.read().decode("utf-8", "ignore") or "{}")
    except Exception as e:
        return {"ok": False, "message": "连不上火山 OpenAPI：%s" % str(e)[:160]}
    meta = body.get("ResponseMetadata") or {}
    err = meta.get("Error") or {}
    code = str(err.get("Code") or "")
    if any(t in code for t in ("Signature", "AccessKey", "Credential", "AuthFailure", "InvalidCredential")):
        return {"ok": False, "message": "签名/密钥不通过：%s %s" % (code, err.get("Message") or "")}
    return {"ok": True,
            "note": "AK/SK 签名通过 · %s" % (code or ("RequestId " + str(meta.get("RequestId") or "")[:12]))}


def _ui_test(data):
    kind = (data.get("kind") or "").lower()
    cfg = data.get("config") or {}
    if kind == "text" and ((cfg.get("text") or {}).get("provider") or "workbuddy") == "workbuddy":
        return {"ok": True, "message": "WorkBuddy 默认，无需测试"}
    if kind == "music":
        mu = cfg.get("music") or {}
        if (mu.get("provider") or "comfyui").strip().lower() in ("volc", "volcengine", "doubao", "ark"):
            return _volc_probe(cfg)
        ep = (mu.get("endpoint") or "").strip().rstrip("/")
        auth = (mu.get("auth") or "").strip()
        if not ep:
            return {"ok": False, "message": "未填配乐端点（不填也能出片，只是没背景音乐）"}
        try:
            headers = {}
            if auth:
                headers["Authorization"] = "Basic " + base64.b64encode(auth.encode()).decode()
            req = urllib.request.Request(ep + "/system_stats", headers=headers)
            with urllib.request.urlopen(req, timeout=15) as r:
                body = r.read().decode("utf-8", "ignore")[:200]
            return {"ok": True, "note": "ComfyUI 已响应"}
        except Exception as e:
            return {"ok": False, "message": str(e)[:200]}
    if kind == "text":
        ep = ((cfg.get("text") or {}).get("endpoint") or "").strip()
        key = ((cfg.get("text") or {}).get("key") or "").strip()
        model = ((cfg.get("text") or {}).get("model") or "").strip()
    elif kind == "image":
        ep = ((cfg.get("image") or {}).get("endpoint") or "").strip()
        key = ((cfg.get("image") or {}).get("key") or "").strip()
        model = ((cfg.get("image") or {}).get("model") or "").strip()
    else:
        ep = ((cfg.get("video") or {}).get("endpoint") or "").strip()
        key = ((cfg.get("video") or {}).get("key") or "").strip()
        model = ((cfg.get("video") or {}).get("model") or "").strip()
    if not ep:
        return {"ok": False, "message": "端点为空"}
    try:
        d = http_json(ep.rstrip("/") + "/models",
                      headers={"Authorization": "Bearer " + key}, timeout=15)
        ids = [m.get("id") for m in d.get("data", [])]
        has = (model in ids) if model else None
        return {"ok": True, "count": len(ids), "has_model": has, "models": ids[:12]}
    except Exception as e:
        return {"ok": False, "message": str(e)[:200]}


def _ui_tts(data):
    """试听：用当前填的音色合成一句，返回 mp3 字节。"""
    if not have_edge_tts():
        raise RuntimeError("未安装 edge-tts（pip install edge-tts）")
    voice = (data.get("voice") or DEFAULT_VOICES["default"]).strip()
    rate = (data.get("rate") or "+0%").strip()
    text = (data.get("text") or "这是一句试听。").strip()[:120]
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    try:
        cmd = [sys.executable, "-m", "edge_tts", "--voice", voice,
               "--text", text, "--write-media", tmp]
        if rate:
            cmd += ["--rate=%s" % rate]  # 同上：-10% 不能被当成选项
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.returncode != 0 or not os.path.exists(tmp):
            raise RuntimeError(p.stderr.decode("utf-8", "ignore")[-200:] or "合成失败")
        with open(tmp, "rb") as f:
            return f.read()
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass


def _ui_project_read(directory):
    """读某个项目的出图通道设置。"""
    d = (directory or "").strip()
    if not d:
        return {"ok": True, "channel": "", "exists": False}
    d = os.path.abspath(os.path.expanduser(d))
    pj = os.path.join(d, "project.json")
    if not os.path.exists(pj):
        return {"ok": True, "channel": "", "exists": False}
    pj = load_json(pj, {})
    return {"ok": True, "channel": (pj.get("image_channel") or ""), "exists": True,
            "title": pj.get("title") or os.path.basename(d)}


def _ui_project_write(directory, channel):
    """把出图通道写进某个项目的 project.json。"""
    d = (directory or "").strip()
    if not d:
        raise ValueError("没有填项目目录")
    d = os.path.abspath(os.path.expanduser(d))
    if not os.path.isdir(d):
        raise ValueError("目录不存在：" + d)
    pj_path = os.path.join(d, "project.json")
    pj = load_json(pj_path, {}) if os.path.exists(pj_path) else {}
    if channel:
        pj["image_channel"] = channel
    else:
        pj.pop("image_channel", None)
    save_json(pj_path, pj)
    return {"ok": True, "channel": channel, "path": pj_path}


def cmd_pick_image(args):
    """给单个项目指定出图通道（不���全局配置）。"""
    cfg, paths = load_project(args.dir)
    pj_path = os.path.join(paths["root"], "project.json")
    pj = load_json(pj_path, {}) if os.path.exists(pj_path) else {}
    if args.channel:
        pj["image_channel"] = args.channel.strip()
    else:
        pj.pop("image_channel", None)
    save_json(pj_path, pj)
    if args.channel:
        info("%s 的出图通道已设为：%s" % (paths["root"], args.channel))
    else:
        info("%s 的出图通道已清除（跟随全局设置）" % paths["root"])
    # 列出该通道可用的模型，方便确认 key 有没有这个通道的权限
    ch = args.channel or ((cfg.get("image") or {}).get("provider") or "agnes")
    img = cfg.get("image") or {}
    info("当前通道：%s  端点：%s  模型：%s" % (ch, img.get("endpoint") or "-", img.get("model") or "-"))


def cmd_config_ui(args):
    import http.server
    import webbrowser

    cfg = load_global_cfg()

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(200, CONFIG_UI_HTML, "text/html")
            elif self.path == "/favicon.ico":
                # 浏览器一定会来要图标，不给就在控制台留一条 404 噪音。
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
            elif self.path == "/api/config":
                self._send(200, json.dumps(_ui_public(cfg), ensure_ascii=False))
            elif self.path == "/api/context":
                # 启动时用 --dir 指定的当前项目，前端自动填进「项目级选择」
                self._send(200, json.dumps({"dir": getattr(args, "dir", "") or ""}, ensure_ascii=False))
            elif self.path.startswith("/api/project"):
                q = urllib.parse.urlparse(self.path)
                d = urllib.parse.parse_qs(q.query)
                directory = (d.get("dir") or [""])[0]
                try:
                    self._send(200, json.dumps(_ui_project_read(directory), ensure_ascii=False))
                except Exception as e:
                    self._send(200, json.dumps({"ok": False, "message": str(e)[:300]}, ensure_ascii=False))
            else:
                self._send(404, "{}")

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                data = {}
            if self.path == "/api/config":
                merged = _ui_merge(cfg, data)
                save_json(GLOBAL_CFG_PATH, merged)
                cfg.clear()
                cfg.update(merged)
                self._send(200, json.dumps({"ok": True}, ensure_ascii=False))
            elif self.path == "/api/project":
                try:
                    self._send(200, json.dumps(_ui_project_write(
                        data.get("dir") or "", (data.get("channel") or "").strip()), ensure_ascii=False))
                except Exception as e:
                    self._send(200, json.dumps({"ok": False, "message": str(e)[:300]}, ensure_ascii=False))
            elif self.path == "/api/test":
                self._send(200, json.dumps(_ui_test(data), ensure_ascii=False))
            elif self.path == "/api/tts":
                try:
                    audio = _ui_tts(data)
                    self._send(200, audio, "audio/mpeg")
                except Exception as e:
                    self._send(500, json.dumps({"ok": False, "message": str(e)[:300]},
                                               ensure_ascii=False))
            else:
                self._send(404, "{}")

    port = int(getattr(args, "port", 0) or 8765)
    httpd = None
    for p in range(port, port + 12):
        try:
            httpd = http.server.ThreadingHTTPServer(("127.0.0.1", p), Handler)
            port = p
            break
        except OSError:
            continue
    if not httpd:
        die("端口都被占用，换一个 --port")
    url = "http://127.0.0.1:%d/" % port
    info("配置界面已启动：%s" % url)
    info("（这个窗口别关，关了页面就没了；要退出按 Ctrl+C）")

    # 打开浏览器：Windows 下 webbrowser 经常静默失败，所以用系统命令兜底
    if not getattr(args, "no_open", False):
        opened = False
        try:
            opened = webbrowser.open(url, new=2)
        except Exception:
            opened = False
        if not opened:
            try:
                if os.name == "nt":
                    os.startfile(url)  # noqa: S606
                else:
                    subprocess.Popen(["xdg-open", url])
                opened = True
            except Exception:
                pass
        if not opened:
            info("浏览器没能自动打开，手动在浏览器里访问：%s" % url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        info("配置界面已关闭")


def cmd_music_ui(args):
    """配乐台：本地网页里试听配乐库、逐镜调音量、一键重新合成。"""
    import http.server
    import urllib.parse
    import webbrowser

    cfg, paths = load_project(args.dir)
    exe = have_ffmpeg(cfg)
    music_dir = os.path.join(paths["audio"], "music")
    os.makedirs(music_dir, exist_ok=True)
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "music_ui.html")
    state = {"proc": None}

    def tracks():
        names = []
        bgm = os.path.join(paths["audio"], "bgm.mp3")
        if os.path.exists(bgm):
            names.append("bgm.mp3")
        for f in sorted(os.listdir(music_dir)):
            if f.lower().endswith((".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg")):
                names.append(f)
        out = []
        for n in names:
            p = os.path.join(paths["audio"], n)
            if not os.path.exists(p):
                p = os.path.join(music_dir, n)
            try:
                d = ff_duration(p, exe) if exe else 0.0
            except Exception:
                d = 0.0
            out.append({"name": n, "dur": round(d, 1)})
        return out

    def timeline():
        shots = load_json(paths["shots"])["shots"]
        entries = []
        t = 0.0
        for s in shots:
            p = os.path.join(paths["clips"], s["id"] + ".mp4")
            d = ff_duration(p, exe) if os.path.exists(p) and exe else float(s.get("duration") or 0)
            entries.append({"id": s["id"], "start": t, "dur": d,
                            "line": (s.get("line") or "").strip(),
                            "scene": (s.get("scene") or {}).get("place") or "",
                            "bgm": s.get("bgm") if s.get("bgm") is not None
                            else (entries[-1]["bgm"] if entries else 0.3)})
            t += d
        return {"title": cfg.get("title") or os.path.basename(paths["root"]),
                "total": t, "shots": entries,
                "tracks": tracks(),
                "current": (load_json(os.path.join(paths["root"], "project.json")) or {}).get("bgm_file") or "bgm.mp3"}

    def save_shot(sid, v):
        p = paths["shots"]
        d = load_json(p)
        for s in d["shots"]:
            if s["id"] == sid:
                s["bgm"] = round(float(v), 3)
        save_json(p, d)

    def set_track(name):
        pp = os.path.join(paths["root"], "project.json")
        conf = load_json(pp) or {}
        conf["bgm_file"] = None if name == "bgm.mp3" else name
        save_json(pp, conf)

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _file(self, p, ctype):
            if not p or not os.path.exists(p):
                self._send(404, "{}")
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
            self.wfile.write(data)

        def do_GET(self):
            path = urllib.parse.unquote(self.path.split("?")[0])
            if path in ("/", "/index.html"):
                with open(html_path, encoding="utf-8") as f:
                    self._send(200, f.read(), "text/html")
            elif path == "/api/state":
                self._send(200, json.dumps(timeline(), ensure_ascii=False))
            elif path == "/api/status":
                alive = state["proc"] is not None and state["proc"].poll() is None
                fp = os.path.join(paths["out"], "final.mp4")
                self._send(200, json.dumps({
                    "building": alive,
                    "final": os.path.getmtime(fp) if os.path.exists(fp) else 0,
                }, ensure_ascii=False))
            elif path.startswith("/media/track/"):
                name = os.path.basename(path[len("/media/track/"):])
                p = os.path.join(music_dir, name)
                if not os.path.exists(p):
                    p = os.path.join(paths["audio"], name)
                self._file(p, "audio/mpeg")
            elif path.startswith("/media/clip/"):
                name = os.path.basename(path[len("/media/clip/"):])
                self._file(os.path.join(paths["clips"], name), "video/mp4")
            else:
                self._send(404, "{}")

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            path = self.path.split("?")[0]
            if path == "/api/upload":
                name = urllib.parse.unquote(self.headers.get("X-Filename") or "track.mp3")
                name = os.path.basename(name)
                body = self.rfile.read(n)
                with open(os.path.join(music_dir, name), "wb") as f:
                    f.write(body)
                self._send(200, json.dumps({"ok": True}, ensure_ascii=False))
                return
            try:
                data = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                data = {}
            if path == "/api/shot":
                save_shot(data.get("id"), data.get("bgm", 0))
                self._send(200, json.dumps({"ok": True}, ensure_ascii=False))
            elif path == "/api/track":
                set_track(data.get("file") or "bgm.mp3")
                self._send(200, json.dumps({"ok": True}, ensure_ascii=False))
            elif path == "/api/apply":
                if state["proc"] is not None and state["proc"].poll() is None:
                    self._send(200, json.dumps(
                        {"message": "上一次还在合成，等它跑完"}, ensure_ascii=False))
                    return
                # 合成参数跟着项目走：project.json 的 assemble 段可覆盖。
                # 默认不混 TTS（模型片段通常自带人声，混了会双重人声），
                # 但 tighten 默认开——项目若靠留白（开口偏晚是设计），必须显式写 false。
                conf = load_json(os.path.join(paths["root"], "project.json")) or {}
                a = conf.get("assemble") or {}
                cmdline = [sys.executable, os.path.abspath(__file__), "assemble", paths["root"]]
                if a.get("subs"):
                    cmdline.append("--subs")
                if a.get("voice"):
                    cmdline.append("--voice")
                if a.get("tighten") is False:
                    cmdline.append("--no-tighten")
                if a.get("transition"):
                    cmdline += ["--transition", str(a["transition"])]
                state["proc"] = subprocess.Popen(cmdline, cwd=os.path.dirname(
                    os.path.abspath(__file__)), stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL)
                self._send(200, json.dumps(
                    {"message": "已保存，正在后台重新合成（约 1-2 分钟）"},
                    ensure_ascii=False))
            else:
                self._send(404, "{}")

    port = int(getattr(args, "port", 0) or 8788)
    httpd = None
    for p in range(port, port + 12):
        try:
            httpd = http.server.ThreadingHTTPServer(("127.0.0.1", p), Handler)
            port = p
            break
        except OSError:
            continue
    if not httpd:
        die("端口都被占用，换一个 --port")
    url = "http://127.0.0.1:%d/" % port
    info("配乐台已启动：%s（Ctrl+C 退出）" % url)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        info("配乐台已关闭")


# ----------------------------------------------------------------------------- 世界观工作台

def cmd_worldview(args):
    """世界观工作台：网页里查看/修改剧本、分镜、角色、道具、场景、世界观。

    多集会在左侧列出，点一下就切过去。
    """
    import sys as _sys
    _here = os.path.dirname(os.path.abspath(__file__))
    if _here not in _sys.path:
        _sys.path.insert(0, _here)
    import wv_server

    cfg, paths = load_project(args.dir)
    root = paths["root"]
    port = getattr(args, "port", 8777) or 8777
    # 端口被占就顺延
    for p in range(port, port + 20):
        try:
            import socket
            s = socket.socket()
            s.bind(("127.0.0.1", p))
            s.close()
            port = p
            break
        except OSError:
            continue
    wv_server.serve(root, port=port, open_browser=not getattr(args, "no_open", False))


# ----------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(prog="ac.py", description="Agnes Clip Pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="创建项目文件夹结构")
    p.add_argument("dir")
    p.add_argument("--title", default=None)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("story", help="写剧本 + 镜头表")
    p.add_argument("dir")
    p.add_argument("--idea", required=True)
    p.add_argument("--shots", type=int, default=10)
    p.add_argument("--seconds", type=float, default=8)
    p.add_argument("--title", default=None)
    p.set_defaults(func=cmd_story)

    p = sub.add_parser("char-gen", help="文本描述生成角色形象（正脸 + 多格角色设定卡）")
    p.add_argument("dir")
    p.add_argument("--name", default="hero")
    p.add_argument("--desc", default=None)
    p.add_argument("--outfit", default=None, help="英文服装；不填则用 shots.json 里的 outfit_en")
    p.add_argument("--tri", action="store_true")
    p.add_argument("--no-card", action="store_true", help="只出正脸，不生成多格设定卡")
    p.add_argument("--card-style", default="sheets", help="设定卡版式：sheets / turnaround")
    p.add_argument("--channel", default="", help="出图通道：agnes / gpt-image / banana；默认跟随配置")
    p.add_argument("--force", action="store_true", help="已存在也重新生成（会重新出图，消耗额度）")
    p.set_defaults(func=cmd_char_gen)

    p = sub.add_parser("char-add", help="导入已有照片作为角色")
    p.add_argument("dir")
    p.add_argument("image")
    p.add_argument("--name", default="hero")
    p.set_defaults(func=cmd_char_add)

    p = sub.add_parser("cast", help="共享角色库：本集/多集复用同一张脸（list / init / push）")
    p.add_argument("dir")
    p.add_argument("action", nargs="?", default="list", choices=["list", "init", "push"])
    p.add_argument("--name", default="")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_cast)

    p = sub.add_parser("episode-new", help="在同一系列下新建一集，自动复用已有角色形象")
    p.add_argument("dir", help="已有剧集目录（或系列根目录）")
    p.add_argument("--name", required=True, help="新剧集目录名，如 ep02")
    p.add_argument("--title", default="")
    p.add_argument("--inside", action="store_true",
                   help="新集建在当前项目目录内部（第 1 集就是项目根时用这个）")
    p.set_defaults(func=cmd_episode_new)

    p = sub.add_parser("prop-gen", help="生成道具参考图")
    p.add_argument("dir")
    p.add_argument("--name", required=True)
    p.add_argument("--desc", default=None)
    p.add_argument("--force", action="store_true", help="已存在也重新生成（会重新出图，消耗额度）")
    p.set_defaults(func=cmd_prop_gen)

    p = sub.add_parser("scene-gen", help="按场景四要素生成空场景图（不带人物）")
    p.add_argument("dir")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_scene_gen)

    p = sub.add_parser("frame", help="逐镜生成首帧图（--dry-run 只打印最终提示词与参考图）")
    p.add_argument("dir")
    p.add_argument("--only", default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="只打印最终提示词与参考图，不调用生图")
    p.set_defaults(func=cmd_frame)

    p = sub.add_parser("video", help="提交 Agnes 视频任务")
    p.add_argument("dir")
    p.add_argument("--only", default=None)
    p.add_argument("--wait", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--allow-paid", action="store_true",
                   help="本次任务允许在免费通道排不上时用付费档（默认要人工确认）")
    p.set_defaults(func=cmd_video)

    p = sub.add_parser("fetch", help="续查已提交任务并下载（读 clips/_pending.json）")
    p.add_argument("dir")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("seam", help="量相邻镜头的接缝跳变（上一镜末帧 vs 下一镜首帧）")
    p.add_argument("dir")
    p.add_argument("--window", type=float, default=0.4, help="取上一镜最后多少秒的帧")
    p.set_defaults(func=cmd_seam)

    p = sub.add_parser("recall", help="把旧剧集片段剪成回忆（不调 Agnes，不花额度）")
    p.add_argument("dir")
    p.add_argument("--only", default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="只打印每条回忆的入点/时长，不剪")
    p.set_defaults(func=cmd_recall)

    p = sub.add_parser("music", help="生成配乐（comfyui 本地 / volc 火山引擎）")
    p.add_argument("dir")
    p.add_argument("--duration", type=float, default=None)
    p.add_argument("--caption", default=None)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--lyrics", default=None,
                   help="歌词（带唱词时用）；不给就是纯器乐 [Instrumental]")
    p.add_argument("--force", action="store_true", help="已存在也重新生成")
    p.add_argument("--provider", default=None,
                   help="comfyui（本地显卡）或 volc（火山引擎豆包音乐，无卡也能跑）")
    p.set_defaults(func=cmd_music)

    p = sub.add_parser("voice", help="按台词生成配音（edge-tts，按角色分配音色）")
    p.add_argument("dir")
    p.add_argument("--force", action="store_true")
    p.add_argument("--no-fit", action="store_true",
                   help="不做「超镜长自动提语速」，按配置语速原样出")
    p.set_defaults(func=cmd_voice)

    p = sub.add_parser("assemble", help="拼接 + 混音出成片（字幕默认关闭）")
    p.add_argument("dir")
    p.add_argument("--subs", action="store_true",
                   help="在合成阶段烧字幕，并用 VAD 对准真实人声位置（默认不加字幕）")
    p.add_argument("--no-tighten", action="store_true",
                   help="不按人声收紧片段（默认会砍掉开口前的静音）")
    p.add_argument("--transition", default=None,
                   help="转场：none / dissolve:0.7 / fadewhite:0.4（穿越、闪回用白闪）")
    p.add_argument("--voice", action="store_true",
                   help="生成并混入 TTS 配音（默认关闭；模型自己会出声时别开，会双重人声）")
    p.add_argument("--crop-bottom", type=int, default=0,
                   help="裁掉底部多少像素（去掉视频模型自己烧进画面的字幕/水印）")
    p.set_defaults(func=cmd_assemble)

    p = sub.add_parser("sfx", help="按镜头表 sfx 字段生成音效，或把音效叠到已有成片上")
    p.add_argument("dir")
    p.add_argument("--into", default=None,
                   help="把音效叠到这个成片上（视频流直接复制），如 out/final.mp4")
    p.add_argument("--out", default=None, help="叠加输出路径，默认 out/final-sfx.mp4")
    p.set_defaults(func=cmd_sfx)

    p = sub.add_parser("auto", help="全自动：剧本 → 角色 → 道具 → 首帧 → 视频 → 成片")
    p.add_argument("dir")
    p.add_argument("--idea", default="")
    p.add_argument("--shots", type=int, default=10)
    p.add_argument("--seconds", type=float, default=8)
    p.add_argument("--title", default=None)
    p.add_argument("--music", action="store_true")
    p.add_argument("--music-caption", default=None)
    p.add_argument("--subs", action="store_true", help="成片时烧字幕（按真实人声对齐）")
    p.add_argument("--only-first", action="store_true")
    p.add_argument("--regen-story", action="store_true")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_auto)

    p = sub.add_parser("audit", help="出成片审计报告（逐镜核对 + 质检 + 成本）")
    p.add_argument("dir")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("status", help="查看进度")
    p.add_argument("dir")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("config-ui", help="打开本地配置界面（推理 / 生图 / 生视频）")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    p.add_argument("--dir", default="", help="当前项目目录，页面自动填入「项目级选择」")
    p.set_defaults(func=cmd_config_ui)

    p = sub.add_parser("views", help="从已有设定卡重切角度参考图（views/front|side|back）")
    p.add_argument("dir")
    p.add_argument("--name", default="", help="只处理某个角色；不给则处理全部")
    p.set_defaults(func=cmd_views)

    p = sub.add_parser("pick-image", help="给单个项目指定出图通道（不写全局配置）")
    p.add_argument("dir")
    p.add_argument("--channel", default="", help="agnes / gpt-image / openai / banana，留空=跟随全局")
    p.set_defaults(func=cmd_pick_image)

    p = sub.add_parser("music-ui", help="打开配乐台（试听配乐库 / 逐镜调音量 / 重新合成）")
    p.add_argument("dir")
    p.add_argument("--port", type=int, default=8788)
    p.set_defaults(func=cmd_music_ui)

    p = sub.add_parser("worldview", help="打开世界观工作台（剧本/分镜/角色/道具/场景/世界观，多集切换）")
    p.add_argument("dir")
    p.add_argument("--port", type=int, default=8777)
    p.add_argument("--no-open", action="store_true", help="不自动开浏览器")
    p.set_defaults(func=cmd_worldview)

    p = sub.add_parser("setup", help="配置 Agnes 凭据（写入 ~/.workbuddy/agnes-clip.json）")
    p.add_argument("--agnes-endpoint", default=None)
    p.add_argument("--agnes-key", default=None)
    p.add_argument("--agnes-video-model", default=None)
    p.add_argument("--agnes-image-model", default=None)
    p.add_argument("--agnes-text-model", default=None)
    p.add_argument("--agnes-video-endpoint", default=None)
    p.add_argument("--agnes-video-key", default=None)
    p.add_argument("--music-endpoint", default=None)
    p.add_argument("--music-auth", default=None)
    p.add_argument("--music-provider", default=None, help="comfyui 或 volc")
    p.add_argument("--volc-ak", default=None, help="火山引擎 AccessKey")
    p.add_argument("--volc-sk", default=None, help="火山引擎 SecretKey")
    p.add_argument("--check", action="store_true")
    p.set_defaults(func=cmd_setup)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
