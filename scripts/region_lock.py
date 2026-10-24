#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""region_lock.py —— 地域与时代锁定（防日式 / 防跑偏）。

为什么需要：
扩散模型对"东亚"有很强的默认先验。你不明确写，它给你**日式**——
木结构町屋、纸灯笼、鸟居、榻榻米、和式庭院。

**实测踩过**：写 `An old city street corner at dusk`，出来的是日式町屋 + 和式灯笼，
完全不是中国现代城市。

两条关键经验（都很反直觉）：
1. **负面约束无效，甚至反效果**。写 "no wooden machiya townhouses" 之后，
   出来的还是町屋，而且 "machiya" 这个词本身会激活町屋概念 —— 越禁越来。
   → 只能**纯正向描述**想要的画面，一个负面词都不提。
2. **锚要放最前面**。用户写的场景描述常常是 "An old city street corner" 这种中性说法，
   引导力很强。地域锚放结尾压不住，放开头才有效。

与 agnes-clip 共用同一套文案（那边叫 CN_STREET_ANCHOR / _auto_scene_anchor）。
"""

import re

# 室外街道锚：全正向，一个负面词都没有
CN_STREET_ANCHOR = (
    "Setting: contemporary mainland China, a modern Chinese city street at dusk. "
    "Concrete and glass apartment buildings, Chinese shop signs, red Chinese-style street lamps, "
    "electric scooters parked along the curb, Chinese signage, everyday Chinese urban life. "
    "Modern Chinese architecture and contemporary Chinese street furniture, "
    "clean paved sidewalk, Chinese city road markings. "
    "Photorealistic contemporary Chinese city, cool blue dusk sky with warm orange lamp glow."
)

# 室内锚：室内场景的默认先验是日式居酒屋/咖啡馆，用排除项是安全的（模型不容易误读室内）
CN_SHOP_ANCHOR = (
    "Authentic contemporary Chinese setting with real, lived-in Chinese details. "
    "NOT a Japanese izakaya, NOT a sushi bar, NOT a western restaurant, NOT a generic hotel lobby. "
    "No noren curtains, no tatami, no sushi counter, no English-only signage. "
    "No paper lanterns, no round chochin lanterns, no rising sun motif, no calligraphy banners."
)

SCENE_ANCHOR_PRESETS = {
    "cn_street": CN_STREET_ANCHOR,
    "cn_shop": CN_SHOP_ANCHOR,
    "cn_noodle_shop": (
        "A tiny old Chinese street noodle shop (中式老街面馆) in a southern Chinese city at night. "
        "Authentic Chinese details only — NOT a Japanese izakaya, NOT a sushi bar, NOT a café, "
        "NOT a western restaurant. No noren curtains, no tatami, no sushi counter."
    ),
    "cn_old_street": (
        "An old residential street in a Chinese city, mid-20th-century Chinese brick housing "
        "with red-painted metal doors, white-tiled walls, Chinese characters painted on the walls, "
        "Chinese-style street lamps, bicycles parked against the wall, laundry hanging on balconies, "
        "everyday Chinese residential life, warm dusk light, cool blue sky. "
        "Photorealistic contemporary Chinese city street."
    ),
    "cn_city_night": (
        "A modern Chinese city street at night, glass and concrete high-rises, illuminated Chinese "
        "shop signs in Chinese characters, Chinese-style street lamps, Chinese cars and electric "
        "scooters, everyday Chinese urban life, wet asphalt reflections. "
        "Photorealistic contemporary Chinese city at night."
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

_OUTDOOR_HINTS = ("街", "路口", "巷", "马路", "路边", "户外", "室外", "车站", "桥", "公园", "广场",
                   "street", "road", "corner", "sidewalk", "outdoor", "alley", "crossroad",
                   "avenue", "bridge", "park", "bus stop", "intersection", "plaza")
# 室内词放在前面判断：像「街角咖啡店」这种带"街"字但其实是室内的，
# 必须让具体的室内场所名先命中。
_INDOOR_HINTS = ("室内", "屋里", "房间", "客厅", "卧室", "厨房", "店里", "馆内", "教室", "办公室", "车内",
                 "咖啡店", "面包店", "便利店", "书店", "理发店", "餐厅", "饭店", "面馆", "食堂", "医院",
                 "学校", "公司", "工厂", "仓库", "酒吧", "旅馆", "酒店", "民宿",
                 "indoor", "interior", "room", "living room", "bedroom", "kitchen", "shop",
                 "restaurant", "cafe", "coffee shop", "office", "studio", "hotel")


def _auto_anchor(shot):
    """按场景描述判断室内还是室外。判不出就按室外（室外的日式风险更高）。"""
    sc = (shot or {}).get("scene") or {}
    if isinstance(sc, str):
        sc = {"place": sc}
    if not isinstance(sc, dict):
        sc = {}
    text = " ".join(str(sc.get(k) or "") for k in
                    ("place", "slug", "id", "time", "light", "weather")).lower()
    if any(w in text for w in _INDOOR_HINTS):
        return CN_SHOP_ANCHOR
    if any(w in text for w in _OUTDOOR_HINTS):
        return CN_STREET_ANCHOR
    return CN_STREET_ANCHOR


def _is_interior_shot(shot):
    """室内镜头？（scene.interior 明确为 True，或机位/场景描述指向店内）"""
    if not isinstance(shot, dict):
        return False
    sc = shot.get("scene") or {}
    if not isinstance(sc, dict):
        return False
    if sc.get("interior") is True:
        return True
    if sc.get("interior") is False:
        return False
    return False


# 室内镜头的地域锚：纯正向描述 + 剥掉项目 anchor 里的“街上”表述。
# 为什么要剥：project.json 的 scene_anchor 常常写成
#   "A small neighbourhood Chinese noodle shop and the street outside it in a modern Chinese city"
# 而这个 anchor 会被拼到提示词**最前面**（压先验），
# 于是 "the street outside it" 反而把整帧推成室外街景 —— 实测室内镜整帧跑出街头。
_INTERIOR_SCENE_PREFIX = (
    # 🔴 只做地域约束，**不带任何具体陈设**。
    #    之前这里硬写了「白墙 / 木家具 / 刷金属吊灯 / 一摞碗」——那是某一间店堂的样子，
    #    套到菜市场、后厨、灶间上就成了串味（ep04 菜市场首帧里冒出来米面馆的吊灯和纸条）。
    #    陈设一律由各场景自己的 anchor + scene.set 负责。
    "Authentic contemporary Chinese setting. "
    "Everything visible in frame belongs to this same location. "
    "Contemporary Chinese, not a Japanese izakaya, not a sushi bar, not a western diner, "
    "not a Japanese street with torii gates or shrine lanterns. "
)


def _strip_outdoor_bits(anchor):
    """把 anchor 里指向街道/室外的片段删掉，保留地域风格约束。"""
    if not anchor:
        return ""
    out = anchor
    # 常见写法："A and the street outside it in a modern Chinese city" / "and the street outside"
    for pat in (
        r",?\s*and the street outside it[^,.;]*",
        r",?\s*and the street outside[^,.;]*",
        r",?\s*and the street[^,.;]*",
        r",?\s*with the street outside[^,.;]*",
    ):
        out = re.sub(pat, "", out, flags=re.I)
    return out.strip()


def scene_anchor(cfg, paths=None, shot=None):
    """地域锁定锚。项目 project.json 的 scene_anchor 优先，其次全局配置，最后自动选。

    🔴 分场景锚（实测 ep03 踩过）：项目级 scene_anchor 写的是主场景（比如面馆），
       于是**同一片子里其它场景**（比如老大爷家的灶间）也被这个锚带偏 ——
       灶间里冒出面馆的菜单条和挂轴。所以场景自己带 `anchor` 字段时优先用它。
    """
    anchor = (cfg or {}).get("scene_anchor") or ""
    root = (paths or {}).get("root") or (paths or {}).get("proj") or "."
    import os
    pconf_path = os.path.join(root, "project.json")
    if os.path.exists(pconf_path):
        try:
            import json
            with open(pconf_path, encoding="utf-8") as f:
                pconf = json.load(f) or {}
            anchor = pconf.get("scene_anchor") or anchor
        except Exception:
            pass
    # 场景自带锚优先（scene.anchor / scene.scene_anchor）
    if shot:
        sc = shot.get("scene") or {}
        if isinstance(sc, str):
            sc = {}
        sa = (sc.get("anchor") or sc.get("scene_anchor") or "").strip()
        if sa:
            anchor = sa
    if not anchor:
        anchor = _auto_anchor(shot)
    if isinstance(anchor, str):
        anchor = SCENE_ANCHOR_PRESETS.get(anchor.strip(), anchor)
    # 🔴 室内镜头：把 anchor 里的“街上”表述剥掉，并强制用内景正向锚。
    #    anchor 会被拼在提示词最前面，"the street outside it" 会把整帧推成室外。
    if _is_interior_shot(shot):
        anchor = _INTERIOR_SCENE_PREFIX + " " + _strip_outdoor_bits(anchor)
    return anchor


def lock_region(prompt, cfg=None, paths=None, shot=None, position="front"):
    """把地域锚拼进提示词。

    position="front"（默认）：放最前面，压得住"东亚老街"这种默认先验。
    position="end"：放结尾，适合已经写得很具体的提示词。
    """
    anchor = scene_anchor(cfg, paths, shot)
    if not anchor:
        return prompt
    if position == "end":
        return (prompt or "") + " " + anchor
    return anchor + " " + (prompt or "")
