# 人类角色 vs 拟人动物 + 道具参考图

> 两件事，都是实测踩出来的：
> ① 世界观说「所有人都是动物」时，**明确写了"人"的角色也会被画成兽脸**（ep04 卖菜阿姨）。
> ② 中国地方菜**光靠文字描述画不准**，必须喂真实参考图（ep04 鲊广椒）。

---

## 一、人类角色混居（拟人动物世界观里的"真人"）

### 症状

世界观锚写着 `every inhabitant is an anthropomorphic animal`，
那么**画面里所有人**都会被画成兽脸——包括你明确写了
`an elderly Tujia woman` 的角色。

ep04 实测：卖菜阿姨的设定卡和首帧都长着羊/猫的脸，
但用户要的是「一个卖菜的老太太，是人」。

### 根因

不是「描述不够详细」，而是**两句话在打架**：
- 世界观锚：所有人都是拟人动物
- 角色描述：an elderly woman

模型只能选一边，而世界观锚的权重更高（它是全局锚）。

### 修法：显式声明「他是人」

角色描述里加这几句（**不能只写 "a woman"**）：

```
a real human being — a human person with a human face, human skin with no fur
anywhere on the body, human eyes, human nose and human lips,
human hands with human fingers and human skin, natural human skin texture and
pores, real human wrinkles and age lines, human hair.
This character is a human being, NOT an animal and NOT an anthropomorphic
animal character: no fur, no muzzle, no animal ears, no tail, no paws.
This is a real person living among anthropomorphic animal neighbours.
```

### 配套：把镜头里的世界观句也改掉

**不要写**：
```
Every inhabitant in this market is an anthropomorphic animal.
```

**要写**：
```
Most shoppers and stallholders in this market are anthropomorphic animals,
but the old woman selling zha guang jiao is a real human being
with human skin and a human face.
```

> 句子里的例外对象要**点名**，模型才知道该把谁排除掉。

### 服装也要写

```
her hands are human hands with human skin and human fingers, not paws
```

光在描述里说"是人"不够，**手是最容易漏的部位**——
上半身是人脸、下半身是爪子的情况很常见。

### skill 已内置（v1.15.0）

- `_is_human_character(desc)` 判定：描述里有 `a real human / human being /
  human skin / woman / man / grandmother...` 且**不含动物词** → 认为是人类
- `_species_clause()` 增加人类分支，返回上面那段声明
- `ANTHROPOMORPHIC` 世界观锚从「全是动物」改成「**大多数**是动物，
  明确写了人类的角色保持人类」

> ⚠️ 角色描述里如果同时出现动物词和人类词，**按动物算**（先排除动物）。

---

## 一点五、ep05 S18 事故：真人镜被兽化（三个连环坑）

ep04 修了「阿姨被画成兽脸」，但 ep05 又踩了一次更隐蔽的坑：
**一整镜里两个角色都是真人**（老乡夫妇），结果祥婶长了狐狸脸、老乡长了狗脸。

这一次的根因不是「描述不够」，而是**三处代码级自相矛盾**，单修任何一处都不够。

### 坑 1：无条件的「所有角色的手都是爪子」

双人同框时代码会追加这句（为了防 ep04 S23 猫嫂手变人手）：

```
Every character's visible hands are furry animal paws with the same fur colour
as the rest of that character, never human fingers or human skin.
```

画面里全是真人时，这句和角色描述里的
`human hands with human fingers and human skin` **正面打架**，
模型两边各取一半 → 兽化。

**修法**：按角色分开声明。动物说爪子，真人说人手。
skill 现在按 `ref_bind` 里每个角色跑一次 `_is_human_character`，
人和动物混框时分别写一句，并强调「两种手不能混」。

### 坑 2：世界观锚里的通用动物描述被套到真人身上

世界观锚有一句通用描述：

```
a cartoon animal with a full furry animal head, a furry muzzle and snout,
whiskers, animal ears and a tail, standing upright on two legs
```

它描述的是这个世界里的**动物居民**，但当一镜里全是真人时，
模型会把它当成对**画面主体**的描述。

**修法**：真人镜用单独的锚（`WORLD_REAL`），只说环境，不给主体套动物外形：

```
set in a rural Chinese spring hillside where the animal neighbours live
elsewhere in this world; the two people in this frame are the only bodies
visible and both of them are real human beings, human faces, human skin,
no fur, no animal muzzle, no animal ears, no tail
```

### 坑 3：`project.json` 漏写 `character_type`

`project.json` 里没写 `"character_type": "anthropomorphic_animal"` 时，
skill 会往提示词里加 **EAST_ASIAN** 那句：

```
All characters are East Asian Chinese with East Asian facial features,
black hair, dark eyes and natural East Asian skin tones.
```

这句会把猫**拉回人样**、长出人类五官——而且它出现在提示词里
`character_type_clause` 的守卫条件里，看起来像是被正确处理了，其实项目配置漏了。

**修法**：拟人动物项目的 `project.json` **必须**写：

```json
{ "character_type": "anthropomorphic_animal" }
```

> ep03 写了，ep04 和 ep05 都漏了。漏了不会报错，只是画面悄悄变味。

### 坑 4（补充）：视频阶段是**另一条独立生成链**

首帧画对了不代表视频里不会被兽化。视频模型只看到「首帧图 + 文字提示词」，
文字不写「这是人」，它就按世界观里的动物套。

**修法**：skill 的 `do_videos()` 现在会把 `_human_cast_clause()` 追加到
**视频提示词**里（真人定性句 + "never turn a human into an animal"）。

### skill 已内置（v1.19.0）

- `_human_cast_clause(shot, chars)`：真人角色逐个点名定性
  （human face / no fur / no muzzle / no whiskers / no animal ears / no tail /
  human hands with human fingers），并声明「通用动物描述只适用于动物角色」
- 首帧提示词：按角色分别声明手是爪子还是人手（不再一刀切）
- 视频提示词：同一份真人定性句追加一遍
- `project.json` 的 `character_type` 缺失会导致 EAST_ASIAN 混入，**必须显式配置**

### 验收清单（真人镜）

- [ ] 真人是不是**人脸**（不是狐狸脸/狗脸）？
- [ ] 真人的手是不是**人手**？
- [ ] 这一镜**有没有动物同框**？没有的话更危险——
      世界观锚的通用动物描述会直接套到真人身上
- [ ] `project.json` 里 `character_type` 写了没？
- [ ] 视频出片后**再复查一遍**真人镜（视频链和首帧链是两回事）？

---

## 二、道具参考图（菜品/食材必须喂图）

### 症状

中国地方菜用文字描述**几乎画不准**。

ep04 实测：鲊广椒（恩施特产，剁碎红辣椒拌粗玉米面发酵），
我写「rich golden-brown, coarse-grained」→ 模型画成一坨深红褐色糊状物，
像辣椒酱，完全不像真的。

搜了实物图才发现真品是**金黄色小颗粒 + 深红辣椒碎，泡在红油里**。

### 修法：`prop-gen` 生成参考图 → `shot.props` 挂上

```bash
# 1) 生成道具参考图
python scripts/ac.py prop-gen ep04 --name zhaguangjiao --desc "..."
# → assets/props/zhaguangjiao.jpg

# 2) 在镜头表里挂上（文件名，不带 .jpg）
shot(..., props=["zhaguangjiao", "zha_guangjiao_chao_larou"])
```

skill 会自动：
- 把 `assets/props/<name>.jpg` 喂给模型
- 在提示词里加绑定声明：
  `Reference photo 3 is a close-up of zhaguangjiao itself — the actual food,
  correctly coloured and correctly textured. Reproduce its exact colour and texture.`

> 编号接着人脸图往后数（人脸绑定声明已占用 1/2），不能从 1 重来。

### 参考图的描述要写「拍成什么样」

`prop-gen` 的 desc 写的是**成品照**，不是食材说明：

```
✅ "A close-up food photograph of Enshi Tujia zha guang jiao, fermented chopped
    red chili pepper mixed with coarse yellow corn meal, aged in a dark brown
    glazed earthenware jar. The fermented pepper is now a rich golden amber
    colour with deep red chili pieces visible, made of small crumbly golden
    granules the size of coarse sand, some reddish oil glistening on the surface,
    resting in a shallow dark brown glazed earthenware bowl... Warm overhead
    kitchen light, shallow depth of field, high detail on the granular texture"

❌ "发酵的辣椒 corn meal mix, golden brown, grainy"   ← 太抽象，模型自由发挥
```

**关键词**：close-up food photograph / individual granules clearly distinguishable /
textured / glistening oil / shallow depth of field。

### 顺便也用参考图校正提示词

道具图出来后，**回头看提示词里的颜色描述**——我写「deep red-brown」，
参考图明明是金黄颗粒。**参考图是唯一的事实来源，提示词要跟它对齐。**

### 特写镜头更适合喂道具图

景别越近，模型越会照着参考图画（而不是自由发挥）。
所以「菜特写」这一镜**必须**挂道具图，而且要给足张数（0.6→0.8）。

---

## 三、验收清单

- [ ] 人类角色是不是**人脸**（不是兽脸）？
- [ ] 人类角色的**手是不是人手**（不是爪子）？
- [ ] 镜头里的世界观句有没有把人类排除掉？
- [ ] 菜品镜：**颜色对不对**（拿参考图比对）？
- [ ] 菜品镜：**质地对不对**（颗粒感 / 油光 / 焦边）？
- [ ] 特写镜：画面里是不是**只有菜**（不该出现脸）？
