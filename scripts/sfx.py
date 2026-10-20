# -*- coding: utf-8 -*-
"""拟音库 —— 纯标准库合成音效，不依赖 numpy / 外部素材。

为什么自己合成：
1. 版权干净，不用去素材站找；
2. 参数全在这里，想要"手机提示音更冷一点""耳鸣再高 200Hz"改一行就行；
3. 短音效不需要联网，离线也能出片。

对外只暴露 build(kind, dur=None, dst=None) -> wav 路径。
"""

import math
import os
import random
import struct
import wave

SR = 44100
PEAK = 0.7  # 每个音效归一化到这个峰值（约 -3dBFS），混音时再按 dB 给增益


# ---------------------------------------------------------------- 基础工具

def _zeros(dur):
    return [0.0] * max(1, int(dur * SR))


def _exp_env(n, tau, attack=0.003):
    """指数衰减包络；attack 秒内线性起音，避免起始爆音。"""
    a = max(1, int(attack * SR))
    out = [0.0] * n
    k = math.exp(-1.0 / (tau * SR)) if tau > 0 else 0.0
    v = 1.0
    for i in range(n):
        out[i] = v * (min(1.0, i / a) if i < a else 1.0)
        v *= k
    return out


def _sine(freq, dur, phase=0.0):
    n = int(dur * SR)
    w = 2.0 * math.pi * freq / SR
    return [math.sin(w * i + phase) for i in range(n)]


def _noise(dur, seed=1):
    rnd = random.Random(seed)
    n = int(dur * SR)
    return [rnd.uniform(-1.0, 1.0) for _ in range(n)]


def _lp(sig, fc):
    """一阶低通。"""
    a = math.exp(-2.0 * math.pi * fc / SR)
    out = [0.0] * len(sig)
    y = 0.0
    for i, x in enumerate(sig):
        y = (1 - a) * x + a * y
        out[i] = y
    return out


def _hp(sig, fc):
    """用"原信号 - 低通"做一阶高通。"""
    lo = _lp(sig, fc)
    return [x - y for x, y in zip(sig, lo)]


def _add(dst, src, at=0.0, gain=1.0):
    s = int(at * SR)
    n = min(len(src), len(dst) - s)
    for i in range(max(0, n)):
        dst[s + i] += src[i] * gain
    return dst


def _mul(sig, env):
    n = min(len(sig), len(env))
    return [sig[i] * env[i] for i in range(n)]


def _fade(sig, fin=0.0, fout=0.0):
    n = len(sig)
    fi = min(n, int(fin * SR))
    fo = min(n, int(fout * SR))
    for i in range(fi):
        sig[i] *= i / fi
    for i in range(fo):
        sig[n - 1 - i] *= i / fo
    return sig


def _norm(sig, peak=PEAK):
    m = max((abs(x) for x in sig), default=0.0)
    if m < 1e-9:
        return sig
    k = peak / m
    return [x * k for x in sig]


def _soft(sig):
    """轻微软限幅，防止叠加后个别尖峰破音。"""
    return [math.tanh(x * 1.05) / math.tanh(1.05) for x in sig]


def _write(path, mono, width=0.0):
    """mono -> 立体声写盘；width 给左右声道的轻微电平差，让音效不贴脸。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    l = mono
    r = [x * (1.0 - width) for x in mono] if width else mono
    frames = bytearray()
    for a, b in zip(l, r):
        frames += struct.pack("<hh", int(max(-1, min(1, a)) * 32767),
                              int(max(-1, min(1, b)) * 32767))
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(bytes(frames))
    return path


# ---------------------------------------------------------------- 音效定义

def _glass():
    """玻璃杯轻碰：三个非谐泛音 + 一下极短的碰撞噪声。"""
    dur = 1.6
    out = _zeros(dur)
    for f, g, tau in ((2480, 1.0, 1.10), (3720, 0.55, 0.72),
                      (5150, 0.30, 0.42), (1240, 0.22, 1.35)):
        _add(out, _mul(_sine(f, dur), _exp_env(int(dur * SR), tau, 0.002)), 0, g)
    click = _mul(_hp(_noise(0.02, 7), 3500), _exp_env(int(0.02 * SR), 0.004))
    _add(out, click, 0, 0.55)
    return _fade(_norm(out), 0.0, 0.25)


def _notify():
    """手机消息提示音：单音铃，带两个泛音，尾音稍长——这是"叮"。"""
    dur = 1.05
    out = _zeros(dur)
    for f, g, tau in ((1568, 1.0, 0.42), (3136, 0.42, 0.28),
                      (4320, 0.16, 0.16)):
        _add(out, _mul(_sine(f, dur), _exp_env(int(dur * SR), tau, 0.004)), 0, g)
    return _fade(_norm(out), 0.0, 0.3)


def _notify_soft():
    """同款提示音，但更闷、更暗——用在他的第二条敷衍回复。"""
    dur = 0.9
    out = _zeros(dur)
    for f, g, tau in ((1174, 1.0, 0.34), (2348, 0.30, 0.20)):
        _add(out, _mul(_sine(f, dur), _exp_env(int(dur * SR), tau, 0.006)), 0, g)
    return _fade(_norm(_lp(out, 4200)), 0.0, 0.25)


def _tick():
    """键盘/按键：一下极短的高频脆响。"""
    dur = 0.09
    out = _zeros(dur)
    _add(out, _mul(_hp(_noise(0.03, 3), 2600), _exp_env(int(0.03 * SR), 0.006)), 0, 1.0)
    _add(out, _mul(_sine(1350, 0.03), _exp_env(int(0.03 * SR), 0.012)), 0, 0.35)
    return _fade(_norm(out), 0.0, 0.02)


def _tap():
    """手指触屏 / 按下说话键。"""
    dur = 0.12
    out = _zeros(dur)
    _add(out, _mul(_hp(_noise(0.012, 11), 3000), _exp_env(int(0.012 * SR), 0.003)), 0, 1.0)
    _add(out, _mul(_sine(2200, 0.04), _exp_env(int(0.04 * SR), 0.010)), 0, 0.3)
    return _fade(_norm(out), 0.0, 0.03)


def _whoosh():
    """语音发出去 / 气流扫过：带通噪声，先起后落。"""
    dur = 0.62
    n = int(dur * SR)
    base = _hp(_lp(_noise(dur, 21), 5200), 380)
    env = []
    for i in range(n):
        t = i / n
        env.append((t ** 1.6) * math.exp(-3.2 * max(0.0, t - 0.28)))
    return _fade(_norm(_mul(base, env)), 0.0, 0.05)


def _thud():
    """手机扣在床/桌上：低频闷响 + 一下短促撞击。"""
    dur = 0.45
    out = _zeros(dur)
    _add(out, _mul(_sine(86, dur), _exp_env(int(dur * SR), 0.10, 0.002)), 0, 1.0)
    _add(out, _mul(_sine(172, 0.18), _exp_env(int(0.18 * SR), 0.045)), 0, 0.35)
    _add(out, _mul(_lp(_noise(0.06, 5), 900), _exp_env(int(0.06 * SR), 0.012)), 0, 0.5)
    return _fade(_norm(out), 0.0, 0.12)


def _rain(dur=8.0):
    """窗外的雨：两层带通噪声 + 缓慢起伏。不喧哗，只做底。"""
    dur = max(1.0, float(dur))
    base = _lp(_noise(dur, 31), 4000)
    base = _hp(base, 420)
    hiss = _hp(_noise(dur, 41), 5200)
    n = len(base)
    out = [0.0] * n
    for i in range(n):
        t = i / SR
        m = 0.82 + 0.10 * math.sin(2 * math.pi * 0.13 * t) \
            + 0.06 * math.sin(2 * math.pi * 0.31 * t + 1.7)
        out[i] = base[i] * m + hiss[i] * 0.10 * m
    return _fade(_norm(out), 1.2, 1.5)


def _tinnitus(dur=6.0):
    """耳鸣：高频细线 + 一层极窄的噪声。

    只放纯正弦会像测试音；混一点 3.4–4.6kHz 的窄带噪声，再加 ±4Hz 的慢漂移，
    听起来才是"耳朵里在响"，而不是音响在响。
    """
    dur = max(0.5, float(dur))
    out = _zeros(dur)
    n = int(dur * SR)
    band = _hp(_lp(_noise(dur, 57), 4600), 3400)
    for i in range(n):
        t = i / SR
        mod = 0.72 + 0.28 * math.sin(2 * math.pi * 0.55 * t)
        out[i] += band[i] * 0.55 * mod
    for f, g in ((3860, 1.0), (5230, 0.42), (7790, 0.10)):
        w = 2.0 * math.pi * f / SR
        for i in range(n):
            t = i / SR
            drift = 4.0 * math.sin(2 * math.pi * 0.19 * t + f)
            mod = 0.72 + 0.28 * math.sin(2 * math.pi * 0.55 * t + f)
            out[i] += g * mod * math.sin(w * i + 2 * math.pi * drift * t)
    return _fade(_norm(out), min(1.4, dur * 0.35), min(1.6, dur * 0.4))


def _drone(dur=5.0):
    """低频"嗡"：55Hz 双振荡拍频 + 二三次泛音。

    纯 55Hz 在手机喇叭上几乎放不出来，所以泛音不能省——手机上听到的"嗡"
    其实是 110/165/220Hz 这几层。
    """
    dur = max(0.5, float(dur))
    out = _zeros(dur)
    for f, g in ((55.0, 1.0), (55.7, 0.9), (110.4, 0.45),
                 (165.0, 0.18), (220.8, 0.10)):
        _add(out, _sine(f, dur), 0, g)
    n = len(out)
    for i in range(n):
        t = i / SR
        out[i] *= 0.80 + 0.20 * math.sin(2 * math.pi * 0.09 * t)
    return _fade(_norm(_soft(out)), min(1.6, dur * 0.4), min(2.0, dur * 0.45))


BANK = {
    "glass": _glass,
    "notify": _notify,
    "notify2": _notify_soft,
    "tick": _tick,
    "tap": _tap,
    "whoosh": _whoosh,
    "thud": _thud,
    "rain": _rain,
    "tinnitus": _tinnitus,
    "drone": _drone,
}

# 需要按时长现场生成的（其余是固定短音）
PARAMETRIC = {"rain", "tinnitus", "drone"}


def kind_names():
    return sorted(BANK)


def build(kind, dur=None, dst=None):
    """生成（或复用）一个音效 wav，返回路径。"""
    if kind not in BANK:
        raise ValueError("未知音效：%s（可用：%s）" % (kind, ", ".join(kind_names())))
    if dst is None:
        raise ValueError("需要 dst")
    if os.path.exists(dst):
        return dst
    sig = BANK[kind](dur) if kind in PARAMETRIC and dur else BANK[kind]()
    sig = _soft(_norm(sig))
    return _write(dst, sig)


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    for k in kind_names():
        p = build(k, 4.0 if k in PARAMETRIC else None,
                  os.path.join(out, k + ".wav"))
        print("ok", p)
