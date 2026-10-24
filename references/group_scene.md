# 群戏镜（多角色同框）

> 实测来源：ep05《清炒折耳根》——用户明确要求「野炊来的动物要多一点儿」，
> 结果 9 镜都是 3-5 人同框，被 check 全部报「同框超过 2 人」。

---

## 一、为什么默认限制 2 人

**这是模型的技术限制，不是创作约束。**

两个 face_ref 一起喂进去时，模型会把两张脸的特征融合（见 `two_shot_faces.md`）。
三个以上还会出现：串脸、多出一个人、站位乱、衣服互换。

所以**除非明确声明，默认 2 人**。

---

## 二、群戏镜怎么声明

```python
shot(
    "S02", 8, SCENE_PATH, "ride",
    ["goulaodi", "tumeimei", "guangwuayi", "daye"],
    ["goulaodi", "tumeimei", "guangwuayi", "daye"],
    "...",
    group_scene=True,
    group_note=("golden retriever on the LEFT, rabbit in the MIDDLE-LEFT, "
                "elderly poodle in the MIDDLE-RIGHT, old ram on the RIGHT, "
                "all four side by side in the cart, all facing forward down the lane"),
)
```

`group_note` **必须写**，否则 check 会报错。写清两件事：
1. **每个人站哪**（LEFT / CENTRE / RIGHT / CENTRE-LEFT …）
2. **朝向**（都朝前、都看镜头、都在看某个人）

---

## 三、群戏镜的提示词要手写 headcount 句

`_cast_clause()` 只会生成「2 人」的模板句。群戏镜要自己写：

```
Headcount in this frame is exactly 5, and these are the only bodies visible:
1) maoge 2) maosao 3) laoxiang (a real human man) 4) xiangzhen (a real human woman) 5) guangwuayi.
Every other seat, the aisle behind them and the rest of the room is empty space.
```

**顺序很重要** —— 要跟 `group_note` 里的站位顺序对上。

---

## 四、群戏镜的实战要点

| 要点 | 说明 |
|---|---|
| **中心人物只有一个** | 画面中心只能有一个焦点（通常是主角），其余人在两侧或后排 |
| **层次要错开** | 前景 1-2 人 + 中景 2 人 + 后排虚化。别 5 个人排成一行 |
| **人数别超 6** | 超过 6 个必串。真的需要更多人 → 分镜 |
| **同框人数 vs 景别** | 3 人以上时**尽量用中景/全景**，特写本来就只看一个人 |
| **参考图会加倍** | 3 人 = 喂 3 张 face_ref，模型负担重 → 群戏镜优先给场景板，别再给一堆道具图 |
| **头号敌人别同框** | 反派跟主角同框时最容易串脸。冲突镜建议分开拍（反应镜 + 对峙镜） |

---

## 五、check 的判定逻辑

```python
if len(cast) > 2:
    if s.get("group_scene"):
        if len(cast) > 6:
            issues.append("群戏镜同框 %d 人，超过 6 人上限")
        elif not (s.get("group_note") or "").strip():
            issues.append("声明了 group_scene 但没写 group_note")
    else:
        issues.append("同框 %d 人，超过 2 人（群戏镜请加 group_scene=True + group_note）")
```

**放宽到 6 人，且强制写站位说明。**

---

## 六、验收清单

- [ ] 人数对吗（有没有多出/少掉的人）？
- [ ] 每个人的脸跟他的单人镜一致吗？
- [ ] 站位跟 `group_note` 写的一致吗？
- [ ] 中心人物清楚吗（不是五六个人挤在一起）？
- [ ] 有没有出现「两个人长得一样」？
- [ ] 人类的角色还是人脸吗（群戏里特别容易退回动物脸）？
