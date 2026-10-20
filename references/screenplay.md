# 编剧方法：场景 / 动作 / 微表情 / 对白 / 口型

这份文档是 `ac.py story` 背后的创作标准。剧本不是解说词，是**能拍的戏**。

## 一、先定场景，再写人

每一镜的场景必须包含四要素，缺一个画面就会飘：

| 要素 | 写什么 | 反例 |
|---|---|---|
| 时间 | 深夜 / 清晨 / 黄昏 | 「某天」 |
| 地点 | 面馆内 / 便利店门口 / 天台 | 「一个地方」 |
| 天气 | 小雨 / 无风 / 回南天 | 「天气不好」 |
| 光源 | 暖黄吊灯 / 冷蓝街灯 / 招牌灯 | 「有光」 |

场景里再放 3–5 个**看得见的实体**（桌面的光晕、蒸汽、玻璃上的水汽、墙上的旧菜单），画面才有空间感。不要写"氛围感很强"这类抽象词。

## 二、动作：一镜一件事

- 一镜只做 **1 个主要动作**：放下碗、转头、起身、擦桌子。
- 多动作会让模型抽搐或瞬移。
- 动作要能被镜头拍到，不写心理活动（"她想起三年前" → 改成"她盯着空碗，筷子停在半空"）。

## 三、微表情：写过程，不写状态

| 不要写 | 改写成 |
|---|---|
| 她笑了 | 嘴角先轻轻提了一下，笑意才慢慢漫到眼底 |
| 她难过 | 视线先落下，下唇收紧，再缓缓松开 |
| 她惊讶 | 眼睛先睁大，呼吸一顿，眉梢才抬起来 |
| 她生气 | 下颌绷紧，鼻翼轻轻张了一下，眼神定住不动 |

限制：
- 只在 **waist-up medium shot / medium close-up** 写微表情。
- 一镜最多 **2 个**微表情，多了会僵。

## 四、对白：短、口语、有潜台词

1. **每句 ≤18 个汉字**，7 秒镜头念得完。
2. 第一镜就开口，最后一镜用台词收尾。
3. 至少一半镜头有台词，不要通篇旁白。
4. 写**信息差**和**潜台词**，不要解释剧情：
   - 差：我很难过，因为我男朋友三年前去世了。
   - 好：他……三年前就走了。
5. 一镜只说一句话。对话戏用正反打拆成两镜，不要一镜里两个人轮流说。

## 五、口型：把台词写进视频提示词

有台词的镜头，`video_prompt` 必须包含三件事：

```
1) 台词原句（用引号）
2) 口型同步指令
3) 说这句话时脸朝向听者或镜头，嘴部可见
```

固定写法：

```text
The character speaks in Mandarin Chinese with precise lip-sync: "还是不要葱对吧？" —
mouth shapes each syllable clearly, jaw and lips move naturally;
keep the face turned toward the listener or camera so the mouth stays visible.
```

配套要求：
- 镜头必须 **waist-up** 或更近，不要远景说台词。
- 台词前后各留 0.5 秒不说话，口型才有起势和收势。
- 不要在同一镜里写两个人同时说话。

## 六、镜头语言

每镜 2–3 段运镜，写成带时间码的 beat：

```text
0-3s: 中景，镜头缓慢推近，她低头吃面
3-6s: 继续推到腰以上，她抬眼看向对面，视线先落下再抬起
6-7s: 镜头轻微拉回，蒸汽在两人之间升起
```

- 一镜最多 3 段运镜，多了会乱。
- 相邻镜头保持同一光线方向与色调。
- 每镜结尾回到稳定构图，方便接下一镜。
- 禁止切镜：不写 `cut to` / `jump shot`，只写 one continuous shot。

## 七、结构（60–90 秒）

```
0:00-0:08  钩子：一个强情绪画面 + 第一句台词
0:08-0:30  铺垫：3-4 镜，交代关系与异常
0:30-0:55  升级：4 镜，冲突逼近，景别收紧
0:55-1:15  反转：2-3 镜，一句台词翻盘
1:15-1:30  收尾：1-2 镜，留白
```

8 镜 × 7 秒 ≈ 56 秒，是最稳的起步规格。

## 八、示例（《对面那碗面》S01）

```json
{
  "scene": {"slug": "面馆内·夜", "time": "深夜", "place": "面馆内", "weather": "无雨", "light": "暖黄吊灯"},
  "action": "老板娘从厨房走出，把一碗面放在女孩对面，转身欲回厨房",
  "micro": "嘴角先轻轻提了一下，笑意才慢慢漫到眼底，目光在女孩脸上停了一瞬",
  "speaker": "boss",
  "line": "还是不要葱对吧？",
  "video_prompt": "One continuous shot, no cuts. 0-2s: she walks from the kitchen and sets a steaming bowl opposite the girl. 2-5s: she places an empty bowl with chopsticks, then turns back. 5-7s: she pauses and looks over her shoulder. The character speaks in Mandarin Chinese with precise lip-sync: \"还是不要葱对吧？\" — mouth shapes each syllable clearly, jaw and lips move naturally; keep the face turned toward the listener so the mouth stays visible. Audio: ambient shop sounds, faint simmering."
}
```

## 九、交稿前检查清单

- [ ] 每镜都有时间/地点/天气/光源
- [ ] 每镜只有 1 个主要动作
- [ ] 有台词的镜头是腰以上景别
- [ ] 台词 ≤18 字，口语，不解释剧情
- [ ] 一半以上镜头有台词，第一镜开口，最后一镜收尾
- [ ] 每镜视频提示词里都有台词原句 + 口型指令
- [ ] 微表情写成过程，一镜不超过 2 个
- [ ] 没有 cut to / jump cut / 五官描写
- [ ] 双人镜头写清了第二个人的发型和服装
