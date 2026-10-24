# 双人同框：脸被"平均"、手变成人手

> 实测事故来源：ep04《渣广椒炒腊肉》S05 / S06 / S23。
> 现象：单人镜里角色脸完全正确，**双人同框就崩**。

---

## 一、两个典型症状

| 症状 | 现场 | 根因 |
|---|---|---|
| **脸被平均** | 猫哥（海豹重点色，深褐面罩无条纹）和卖菜阿姨（浅色羊脸）同框 → 猫哥脸出成白底带褐色斑块，像只普通虎斑猫 | 模型不知道**哪张参考图对应画面里哪个人**，两张脸特征被融合 |
| **手变成人手** | 猫嫂双手捧猫哥的脸 → 画出一双白净的人类手指 | 动物角色做**手部精细动作**时，模型退回人类手的通识 |

**关键规律**：单人镜永远正确（同框才有问题）。所以只要是双人镜，就默认要检查这两项。

---

## 二、脸被平均：三层修法

### 1. shots.json 顶层必须有 `characters` 字段

`ac.py` 的 `_cast_clause()` 靠这个字段锁服装和描述。**缺这一段时**，
白名单里只剩角色名（`1) maoge (maoge)`），模型拿不到任何辨识特征。

```json
{
  "characters": [
    {"name": "maoge",
     "desc_en": "a seal-point Ragdoll cat with fluffy pure white fur, a smooth solid DARK BROWN face mask with NO stripes...",
     "outfit_en": "a faded olive-green military field jacket over a white crew-neck t-shirt, ..."},
    {"name": "maiyi",
     "desc_en": "an elderly Tujia woman with a weathered kind face, warm hazel eyes, silver-grey hair...",
     "outfit_en": "a dark indigo floral blouse, a dark blue floral headscarf, a coarse white cotton apron..."}
  ],
  "shots": [ ... ]
}
```

### 2. 显式绑定「哪张图是谁」

skill 现在会自动在双人镜的提示词里插这一段（`v1.14.0` 起自动生效）：

```
Reference photo 1 is the face of maiyi; reference photo 2 is the face of maoge.
Do not blend the two faces together and do not average their colouring —
each character keeps its own exact face, its own fur colouring and its own eye colour,
with no shared markings between them.
```

紧接着会把每个角色的 `desc_en` **再念一遍**——单靠"参考图"模型会忽略，
文字重复一遍能把它拉回来。

### 3. 姿态要让脸在画面里足够大

**模型对"脸占多少像素"极其敏感**。以下三种姿态必崩：

| 姿态 | 为什么崩 | 改法 |
|---|---|---|
| 背对镜头（"转身冲着某人的背影说话"） | 脸只有侧边一条线 | 改成「**转回身面向镜头这一侧**，朝画外某人说话」 |
| 弯腰低头（"弯腰看锅"） | 脸被压扁、只露头顶 | 改成「**上身微微前倾但脸完全抬着**」 |
| 脸在画面边缘/被前景挡住 | 特征权重不足 | 换机位，把脸放到画面中部 |

**保脸的动作写法**：说话对象在画外，但**脸朝镜头这一侧**——
既能对上视线，又保住完整的脸部特征。

---

## 三、手变成人手

### 修法 1：skill 自动加爪子声明（v1.14.0 起）

双人镜的提示词里会自动追加：

```
Every character's visible hands are furry animal paws with the same fur colour
as the rest of that character, never human fingers or human skin.
```

### 修法 2：手部动作必须在提示词里显式描述

**S23 翻车的原因**：动作写了「两只手捧住他的脸」，但**英文提示词里手是空白**，
模型就自己填了人手。动作 ≠ 提示词，两者必须都写。

正确的写法（把手的形态写全）：

```
both of her furry grey tabby paws — short silver-grey fur, rounded pink paw pads,
small blunt claws — resting flat against his cheeks, one on each side,
her slim furry toes spread gently over his cheekbones
```

关键词：**fur / paw pads / blunt claws / furry toes**。
不要只写 `hands`（模型会当人）。

### 修法 3：把「精细手部动作」换成「整只手/前爪」

捧脸、捏、搓、握手这类动作最容易出人手。能换就换：

| 容易出人手 | 改成 |
|---|---|
| 双手捧住他的脸 | 两只前爪平贴在他双颊上 |
| 捏着耳朵揪 | 一只前爪扣在耳朵上 |
| 伸手扶住他的胳膊 | 前爪搭在他小臂上 |
| 握住他的手 | 一只前爪轻轻按在他手背上 |

---

## 四、验收清单（出片后必查）

- [ ] 双人镜里，每个角色的**脸型和配色跟单人镜是否一致**？（尤其猫哥的面罩）
- [ ] 双人镜里有没有**人手**？（尤其做手部动作的角色）
- [ ] 有没有人多出/少掉？（白名单人数对不对）
- [ ] 背对/低头的镜，脸是否还能认出是那个角色？

**自查最快的方式**：把同一角色的单人镜和双人镜**并排看**。
单人镜对、双人镜错 = 就是本文档说的两个病。

---

## 五、附：为什么单人镜不会崩

单人镜只喂一张 face_ref，且提示词里这个角色的描述占绝对主导。
双人镜喂两张参考图 + 两个描述，模型要同时满足两组特征，
在有限权重下**做了折中**——于是两个人的特征互相污染。

所以：
- 参考图**绑定**能解决「谁是谁」
- **重复描述**能解决「特征权重不够」
- **姿态调整**能解决「脸太小」
- 三条一起上才稳
