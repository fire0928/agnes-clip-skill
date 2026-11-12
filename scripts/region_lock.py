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

# 室内锚：🔴 纯正向，一个负面词都不写。
# 旧版写了 "NOT a Japanese izakaya, no noren curtains, no paper lanterns, no rising sun motif,
# no calligraphy banners" —— 这些词本身把居酒屋、暖帘、纸灯笼、旭日纹、书法挂轴
# 全部激活了，实测首帧里满屏幡旗挂轴就是这么来的。SKILL.md 早写明「地域锚必须全正向」，
# 代码一直没跟上，2026-11-11 一并修掉。
# 只说这间屋子里**有什么**：中国当代的实用空间、灰墙、水泥地、日光灯、普通金属与木家具。
CN_SHOP_ANCHOR = (
    "Setting: an ordinary working interior in contemporary mainland China. "
    "Plain gray concrete or plaster walls, a practical ceiling with exposed white fluorescent "
    "tubes, a smooth gray cement or terrazzo floor, plain metal shelving and simple wooden "
    "furniture, ordinary Chinese signage in simplified Chinese characters, everyday working "
    "Chinese objects, even functional overhead light. "
    "Photorealistic contemporary Chinese interior, cool neutral daylight-white lighting, "
    "documentary film still, natural colour."
)

SCENE_ANCHOR_PRESETS = {
    "cn_street": CN_STREET_ANCHOR,
    "cn_shop": CN_SHOP_ANCHOR,
    "cn_noodle_shop": (
        "A tiny old Chinese street noodle shop in a southern Chinese city at night. "
        "Pale plaster walls, dark wooden tables and stools worn smooth by years of use, "
        "a stainless steel noodle counter with a tall stock pot, Chinese characters on a "
        "hand-painted menu board, warm tungsten bulbs under a low ceiling, steam rising, "
        "a cement floor. Photorealistic contemporary Chinese family restaurant."
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
        "A small lived-in Chinese urban apartment, an ordinary rented flat with simple modern "
        "furniture, a thermos and teacups on the table, clothes drying on a balcony rack, "
        "a wall calendar in simplified Chinese, warm household clutter and soft afternoon light "
        "through a plain aluminum window frame. Photorealistic Chinese home."
    ),
    "cn_cafe": (
        "A small independent Chinese neighbourhood coffee shop, square wooden tables, "
        "warm pendant lights with plain metal shades, potted green plants by the window, "
        "a handwritten menu board in simplified Chinese, tiled floor, quiet afternoon light. "
        "Photorealistic contemporary Chinese small business."
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
                 # 🔴 2026-11-11：这些词以前没进表，「深圳某大型商超后场退货区」被判成室外，
                 #    最前面被灌进整段街景锚（红路灯/电动车/人行道），室内镜整帧跑成街头。
                 "后场", "退货", "超市", "卖场", "商超", "仓库", "库房", "作坊", "灶间", "堂屋",
                 "车间", "后台", "冷库", "档口", "厂房", "包间", "清点区", "会议室", "店面", "铺子", "屋内", "仓间",
                 "indoor", "interior", "room", "living room", "bedroom", "kitchen", "shop",
                 "restaurant", "cafe", "coffee shop", "office", "studio", "hotel",
                 "supermarket", "warehouse", "store room", "stockroom", "workshop", "backroom",
                 "clearance", "dispatch", "stock area", "loading bay")


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
# 🔴 2026-11-11：改成纯正向。旧版里那四个 "not a Japanese izakaya / not a sushi bar /
#    not a western diner / not a Japanese street with torii gates or shrine lanterns"
#    就是「越禁越来」的元凶；SKILL.md 写了必须全正向，代码这里一直留着否定句。
#    只说这间屋子是什么，不提任何不想要的东西。
_INTERIOR_SCENE_PREFIX = (
    "Authentic contemporary Chinese setting. "
    "Everything visible in frame belongs to this same one enclosed room. "
    "Plain walls, a ceiling with exposed white fluorescent tubes, a smooth cement floor, "
    "ordinary Chinese working furniture and even functional overhead light. "
    "Photorealistic contemporary Chinese interior, documentary film still."
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

    # 🔴🔴 2026-11-11：scene.interior 是**显式声明**，直接决定用哪套锚，不再猜关键词。
    #    旧逻辑的 bug：_auto_anchor 把「商超后场退货区」判成室外 → 返回整段街景锚，
    #    接着 _is_interior_shot 又认出 interior=True → 只是把「室内前缀」拼在街景锚前面，
    #    _strip_outdoor_bits 那几条正则对街景锚一句都匹配不上 —— 结果室内镜的最前面
    #    同时出现「这是室内」和「红路灯、电动车、人行道」，模型照街景画。
    sc = (shot or {}).get("scene") or {}
    if not isinstance(sc, dict):
        sc = {}
    explicit = sc.get("interior", None)
    if explicit is True:
        # 室内镜绝不沾街景锚；项目若写了自己的正向场景长句，保留它。
        base = anchor or ""
        if not base or base == CN_STREET_ANCHOR:
            base = CN_SHOP_ANCHOR
        return _INTERIOR_SCENE_PREFIX + " " + base
    if explicit is False:
        base = anchor or ""
        if not base or base == CN_SHOP_ANCHOR:
            base = CN_STREET_ANCHOR
        return base

    # 没写 interior 才走老的关键词推断（保持旧项目行为不变）
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
