# 唯美山水的锚点词库

> 用户要求「增加一些对美丽环境，山水，花草的描写，画面要唯美」。
> 唯美不是靠滤镜，是靠**具体的景物**。这份词库直接抄。

---

## 一、🔴 安全词 vs 危险词（最重要）

扩散模型对「东亚」有强默认先验，**写错一个词就招来日式町屋**。

### ✅ 安全（中国南方春天实景，放心用）
| 类别 | 词 |
|---|---|
| 远山 | `薄雾青山` `层叠的青蓝色山峦` `对岸云雾` `远山轮廓` |
| 水 | `浅溪石滩` `绿河湾` `江面反光` `清澈的溪水` `河边草地` |
| 田 | `翠绿稻田` `水田映着天光` `新插的秧苗` |
| 林 | `竹林` `细长翠竹` `白梅花树` `桃花枝` `嫩绿春树` |
| 花草 | `野花雏菊` `小黄花` `落满花瓣的土路` `青苔` `蕨类` |
| 光 | `晨光穿过竹叶` `逆光的叶脉` `斑驳树影` `水面金光` `柔和雾气` |
| 氛围 | `花瓣在空气里飘` `清润的空气` `万物生发` `春天的光` |

### ❌ 危险（会招来日式元素）
`樱花隧道` `樱花瀑布` `日式庭院` `鸟居` `神社` `町屋` `枯山水` `石灯笼` `和室` `神龛`

**兜底句**（每条野外场景锚都加）：
```
NOT a Japanese countryside, no torii gates, no shrine, no wooden machiya townhouses,
no cherry blossom tunnel, no Japanese stone lantern
```

> ⚠️ 记忆里的教训：写 `no wooden machiya townhouses` 这类否定句，
> **"machiya" 这个词本身会激活町屋概念**，越禁越来。
> 最好**只写正向描述**（`Chinese southern spring countryside` + 具体景物），
> 否定句只作补充，别当主力。

---

## 二、按场景类型的锚点模板

### 乡间小路 / 乡野
```
a winding country lane in rural south-western China in early spring,
lush green rice paddies on both sides, misty blue-green mountains layered in the
far distance, pale morning haze softening the horizon, tall bamboo groves and
slender trees with fresh light-green spring foliage, white wildflowers and pink
peach blossom petals scattered along the path, a clear shallow stream running
beside the lane with smooth wet stones under the water,
Chinese southern spring countryside
```

### 山坡 / 野外草地
```
a sloping riverside meadow in rural south-western China in early spring,
wild grass dotted with small yellow and white wildflowers, a bamboo grove behind,
a wild plum tree in white blossom, distant misty blue-green mountains under a
clear pale sky, soft golden sunlight filtering through the branches,
Chinese southern spring countryside
```

### 河滩 / 水边
```
a grassy riverbank clearing in rural south-western China in early spring,
the wide green river curving past, misty blue-green mountains on the far bank,
bamboo groves and flowering wild plum trees along the bank, soft golden sunlight
filtering through the branches, drifting blossom petals in the air,
Chinese southern spring countryside
```

---

## 三、唯美要落在「具体的物件」上

抽象的「美丽的风景」模型拍不出来。要写**能看见的东西**：

| 抽象（没用） | 具体（有效） |
|---|---|
| 美丽的田野 | 翠绿的稻田里新插的秧苗一行行整整齐齐 |
| 有溪水 | 浅溪从灰白石滩上流过，水面映着天光 |
| 开满了花 | 地上散着白色雏菊和几簇小黄花 |
| 春天的感觉 | 空气里飘着几片粉色的桃花瓣 |
| 树很美 | 细长的翠竹一根根立着，叶子被风翻出银白的背面 |
| 光很好看 | 晨光从竹叶间漏下来，在土路上洒了一片碎金 |

---

## 四、光线词（唯美的关键）

| 时段 | 词 |
|---|---|
| 清晨 | `pale morning haze` `soft golden light filtering through` `dew on the leaves` |
| 上午 | `clear bright daylight` `luminous backlight` `dappled sunlight` |
| 逆光 | `backlit leaves glowing` `light coming through the canopy` `rim light` |
| 傍晚 | `warm golden hour` `long soft shadows` `orange glow on the water` |

**背光**是让植物「发光」的关键词：
`the backlit leaves glowing translucent emerald` —— 逆光叶脉那一下最好看。

---

## 五、机位与唯美的配合

| 机位 | 怎么拍才美 |
|---|---|
| 全景 / wide | **前景要有东西**（草叶/花瓣/石头），中间是主体，远处是山——三层纵深 |
| 中景 | 让人物占画面 1/3，留 2/3 给环境 |
| 特写 | 前景叶子虚化 + 主体实焦 + 背景山影虚化 |
| 俯拍 | 拍水田/花海/落叶，路弯成引导线 |
| 平视 | 拍远山层叠 + 雾，最适合「诗意的空镜」 |

**三层纵深**是唯美画面的通用公式：
```
前景：虚化的草叶/花瓣/枝条
中景：主体（人或物）
远景：山/水/雾
```

---

## 六、验收清单

- [ ] 有远景吗（山/雾/天空）？还是只有一片绿？
- [ ] 有水吗？中国南方春天的画面几乎都有水
- [ ] 前景有东西吗（别让主体贴边）？
- [ ] 光有方向吗（逆光/侧光/晨光/斑驳）？
- [ ] 有具体的花/草吗（不是「美丽的花」）？
- [ ] 有飘落的花瓣/雾气这类「动感」元素吗？
- [ ] 色调是几个主色（建议 2-3 个：翠绿+紫红+粉）？
- [ ] 检查有没有混进日式元素（鸟居/町屋/石灯笼/樱花隧道）？
