#!/usr/bin/env python3
"""
edit_fx.py — фільтри редактора для ffmpeg/ffplay (без tkinter, лише стандартна бібліотека).
  • екранування шляхів для filtergraph (кирилиця, пробіли, апострофи, коми, [ ]);
  • кольорові фільтри (Ч/Б, Тепло, Вінтаж…) + яскравість/контраст/насиченість;
  • поворот / дзеркало, плавна поява/зникнення (відео й звук);
  • текст (drawtext) з обведенням / фоном / тінню і плавною появою.
Один і той самий код будує кадр прев'ю, відтворення (ffplay) і експорт —
тому що бачиш у редакторі, те й отримуєш у файлі.
"""
import math
import os

# ---- властивості кліпа за замовчуванням (нові поля; старі кліпи їх не мають) ----
PIECE_DEFAULTS = {"vol": 1.0, "fin": 0.0, "fout": 0.0, "flt": "none",
                  "br": 0.0, "ct": 1.0, "sat": 1.0, "rot": 0, "flip": False,
                  # ефекти звуку: тон (півтони), бас (дБ), реверб (0..1), ефект
                  "pitch": 0.0, "bass": 0.0, "rev": 0.0, "aeff": "none",
                  "novideo": False,     # «видалити відео — лишити звук»
                  # v3.4: непрозорість кліпа, відеоефект, кадрування (частки з кожного боку)
                  "opa": 1.0, "vfx": "none",
                  "cropl": 0.0, "cropt": 0.0, "cropr": 0.0, "cropb": 0.0,
                  # v3.4 «Коригування» як у CapCut: температура, відтінок, тон, різкість,
                  # світлі / тіні, віньєтка, зерно; покращення відео; звук: шумодав, голос
                  "temp": 0.0, "tint": 0.0, "hue": 0.0, "sharp": 0.0, "hl": 0.0, "sh": 0.0,
                  "vig": 0.0, "grain": 0.0, "stab": False, "deflick": False, "mblur": False,
                  "dn": False, "venh": False}
ADJ_KEYS = ("temp", "tint", "hue", "sharp", "hl", "sh", "vig", "grain", "stab", "deflick", "mblur")
CROP_KEYS = ("cropl", "cropt", "cropr", "cropb")
AFX_KEYS = ("pitch", "bass", "rev", "aeff", "dn", "venh")
AUDIO_EFFECTS = ["none", "phone", "underwater", "8d", "echo"]
_AEFF = {
    "phone": "highpass=f=400,lowpass=f=3000",
    "underwater": "lowpass=f=450,lowpass=f=450",
    "8d": "aformat=channel_layouts=stereo,apulsator=hz=0.125:amount=0.9",
    "echo": "aecho=0.8:0.6:350|700:0.45|0.25",
}
# пресети: тон / бас / реверб / ефект / швидкість кліпа (None — не чіпати) / гучність
AUDIO_PRESETS = {
    "none":      {"pitch": 0.0, "bass": 0.0, "rev": 0.0, "aeff": "none", "speed": 1.0},
    "slowed":    {"pitch": -2.8, "bass": 4.0, "rev": 0.6, "aeff": "none", "speed": 0.85},
    "nightcore": {"pitch": 3.9, "bass": 2.0, "rev": 0.0, "aeff": "none", "speed": 1.25},
    "bass":      {"pitch": 0.0, "bass": 18.0, "rev": 0.0, "aeff": "none", "speed": None},
    "earrape":   {"pitch": 0.0, "bass": 28.0, "rev": 0.0, "aeff": "none", "speed": None, "vol": 30.0},
}

FILTERS = ["none", "bw", "vivid", "warm", "cool", "vintage", "film", "fade"]
_FILTER_VF = {
    "bw": "hue=s=0",
    "vivid": "eq=contrast=1.08:saturation=1.45",
    # lutrgb замість colorbalance: той самий відтінок, але у ~7 разів швидше
    "warm": "lutrgb=r='val*1.10':g='val*1.02':b='val*0.86'",
    "cool": "lutrgb=r='val*0.88':g='val*0.98':b='val*1.12'",
    "vintage": "curves=preset=vintage",
    "film": "eq=contrast=1.25:saturation=0.82:brightness=-0.02",   # без vignette — вона дуже повільна
    "fade": "eq=contrast=0.86:brightness=0.05:saturation=0.75",
}

# ---- відеоефекти (вкладка «Ефекти» зліва): ставляться в pre_vf, тобто однаково
#      у прев'ю, програвачі й експорті. Лише фільтри, що є і в старих збірках ffmpeg.
VFX = ["none", "glitch", "vhs", "oldfilm", "blur", "shake", "chromatic", "flash", "rainbow",
       "invert", "sepia", "edge", "pixel", "sharpen", "posterize", "bloom", "noise"]
_VFX = {
    "glitch": "rgbashift=rh=-8:bh=8:edge=smear",
    "vhs": "rgbashift=rh=3:bh=-3,noise=alls=14:allf=t,eq=saturation=1.25:contrast=1.05",
    "oldfilm": "noise=alls=24:allf=t,hue=s=0.25,eq=contrast=1.18:brightness=-0.03",
    "blur": "boxblur=8:1",
    "shake": "crop=w='iw*0.92':h='ih*0.92':x='iw*0.04+iw*0.03*sin(t*41)':y='ih*0.04+ih*0.03*cos(t*37)'",
    "chromatic": "rgbashift=rh=-5:rv=2:bh=5:bv=-2",
    "flash": "eq=brightness='0.35*lt(mod(t,0.6),0.08)':eval=frame",
    "rainbow": "hue=h='t*120'",
    "invert": "negate",
    "sepia": "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131",
    "edge": "edgedetect=mode=colormix:high=0.2",
    "pixel": "scale='trunc(iw/32)*2':'trunc(ih/32)*2',scale='iw*16':'ih*16':flags=neighbor",
    "sharpen": "unsharp=7:7:1.6",
    "posterize": "lutrgb=r='bitand(val,224)':g='bitand(val,224)':b='bitand(val,224)'",
    "bloom": "eq=brightness=0.06:saturation=1.3:contrast=1.08,unsharp=9:9:-0.7",
    "noise": "noise=alls=35:allf=t",
}

TRANSITIONS = ["fade", "fadeblack", "fadewhite", "slideleft", "wipeleft", "smoothleft",
               "circleopen", "zoomin", "pixelize", "radial"]

TEXT_COLORS = ["#ffffff", "#ffd23f", "#ff4d4d", "#4cc9ff", "#33c27f", "#ff7ad9", "#a970ff", "#ff9f1c",
               "#000000"]
TEXT_STYLES = ["outline", "box", "shadow", "plain"]
# шаблони тексту (ліва панель «Текст»): шрифт, стиль, кольори, анімації
TEXT_TEMPLATES = [
    ("meme", {"font": "impact", "style": "outline", "color": "#ffffff", "stroke": "#000000", "size": 0.1,
              "tin": {"type": "drop", "d": 0.5}}),
    ("subtitle", {"font": "segoe", "style": "box", "color": "#ffffff", "bgc": "#000000", "size": 0.06,
                  "ny": 0.38, "tin": {"type": "fade", "d": 0.2}, "tout": {"type": "fade", "d": 0.2}}),
    ("typewriter", {"font": "consolas", "style": "box", "color": "#ffffff", "bgc": "#111111", "size": 0.07,
                    "tin": {"type": "typewriter", "d": 1.2}}),
    ("neon", {"font": "verdana", "style": "shadow", "color": "#ff7ad9", "stroke": "#4cc9ff", "size": 0.09,
              "tloop": {"type": "heartbeat"}}),
    ("gaming", {"font": "impact", "style": "outline", "color": "#ffd23f", "stroke": "#7a1fa2", "size": 0.11,
                "tin": {"type": "slide_up", "d": 0.4}, "tloop": {"type": "shake"}}),
    ("elegant", {"font": "georgia", "style": "shadow", "color": "#f5e6c8", "stroke": "#000000", "size": 0.08,
                 "tin": {"type": "slide_up", "d": 0.8}, "tout": {"type": "fade", "d": 0.6}}),
    ("comic", {"font": "comic", "style": "outline", "color": "#ffd23f", "stroke": "#d62828", "size": 0.09,
               "tin": {"type": "drop", "d": 0.6}, "tloop": {"type": "wave"}}),
    ("headline", {"font": "arial", "style": "box", "color": "#ffffff", "bgc": "#e53935", "size": 0.08,
                  "ny": -0.34, "tin": {"type": "slide_right", "d": 0.5}}),
    ("handwrite", {"font": "script", "style": "shadow", "color": "#ffffff", "stroke": "#000000", "size": 0.09,
                   "tin": {"type": "fade", "d": 0.8}, "tloop": {"type": "float"}}),
]

# ---- наліпки: емодзі Noto (Google, OFL) 512×512 PNG, качаються при першому виборі
STICKERS = ["1f602", "1f923", "1f60d", "1f60e", "1f62d", "1f621", "1f631", "1f914", "1f644", "1f480",
            "1f525", "1f4af", "2764", "1f494", "2b50", "2728", "1f389", "1f44d", "1f44e", "1f44f",
            "1f64f", "1f4aa", "1f440", "1f448", "1f449", "1f446", "1f447", "2705", "274c", "26a0",
            "1f6a8", "1f4a5", "1f4a8", "1f4a9", "1f921", "1f47b", "1f480", "1f916", "1f3ae", "1f3c6",
            "1f451", "1f48e", "1f4b8", "1f680", "1f30d", "1f319", "2600", "26a1", "1f308", "1f3b5"]
STICKERS = list(dict.fromkeys(STICKERS))


def sticker_urls(code):
    return [f"https://cdn.jsdelivr.net/gh/googlefonts/noto-emoji@v2.047/png/512/emoji_u{code}.png",
            f"https://fonts.gstatic.com/s/e/notoemoji/latest/{code}/512.png"]


def sticker_char(code):
    try:
        return chr(int(code, 16))
    except ValueError:
        return "?"


def g(p, key):
    """Властивість кліпа/накладки з дефолтом (для старих словників)."""
    return p.get(key, PIECE_DEFAULTS.get(key))


def is_default(p):
    return all(g(p, k) == v for k, v in PIECE_DEFAULTS.items())


def look_default(p):
    """Колір/поворот без змін (кадр із кешу скрабу можна показувати як є)."""
    return (all(g(p, k) == PIECE_DEFAULTS[k] for k in ("flt", "br", "ct", "sat", "rot", "flip",
                                                        "vfx") + CROP_KEYS + ADJ_KEYS)
            and abs(float(p.get("ang", 0.0) or 0.0)) < 0.05)


# ------------------------------------------------------------ екранування -- #
def esc(path):
    """Шлях файлу як значення опції фільтра: два рівні екранування ffmpeg
    (рівень опції: \\ ' : ; рівень графа: \\ ' [ ] , ;). Без лапок — так
    переживає будь-які символи в імені."""
    p = os.path.abspath(path).replace("\\", "/")
    p = "".join(("\\" + ch) if ch in "\\':" else ch for ch in p)
    return "".join(("\\" + ch) if ch in "\\'[],;" else ch for ch in p)


def num(v):
    return f"{float(v):.4f}".rstrip("0").rstrip(".") or "0"


# ------------------------------------------------------- колір / поворот -- #
def eff_dims(w, h, p):
    """Розміри джерела ПІСЛЯ повороту на 90/270."""
    if int(g(p, "rot")) % 180 == 90:
        w, h = h, w
    fw, fh = crop_frac(p)
    return max(2, int(w * fw)), max(2, int(h * fh))


def crop_frac(p):
    """Яка частка ширини / висоти лишається після кадрування."""
    return (max(0.05, 1.0 - float(g(p, "cropl")) - float(g(p, "cropr"))),
            max(0.05, 1.0 - float(g(p, "cropt")) - float(g(p, "cropb"))))


def adjust_vf(p):
    """Тонке коригування кольору (вкладка «Колір» праворуч)."""
    out = []
    t, n = float(g(p, "temp") or 0), float(g(p, "tint") or 0)
    if abs(t) > 1e-3 or abs(n) > 1e-3:
        out.append(f"lutrgb=r='clip(val*{num(1 + 0.18 * t)},0,255)':g='clip(val*{num(1 - 0.12 * n)},0,255)':"
                   f"b='clip(val*{num(1 - 0.18 * t)},0,255)'")
    h = float(g(p, "hue") or 0)
    if abs(h) > 0.5:
        out.append(f"hue=h={num(h)}")
    hl, sh = float(g(p, "hl") or 0), float(g(p, "sh") or 0)
    if abs(hl) > 1e-3 or abs(sh) > 1e-3:
        a = min(0.95, max(0.02, 0.25 + 0.15 * sh))
        b = min(0.98, max(a + 0.02, 0.75 + 0.15 * hl))
        out.append(f"curves=all='0/0 0.25/{num(a)} 0.75/{num(b)} 1/1'")
    sp = float(g(p, "sharp") or 0)
    if sp > 1e-3:
        out.append(f"unsharp=5:5:{num(1.8 * sp)}")
    gr = float(g(p, "grain") or 0)
    if gr > 1e-3:
        out.append(f"noise=alls={int(round(40 * gr))}:allf=t")
    vg = float(g(p, "vig") or 0)
    if vg > 1e-3:
        out.append(f"vignette=angle={num(0.15 + 0.75 * vg)}")
    return out


def has_crop(p):
    return any(float(g(p, k) or 0) > 1e-3 for k in CROP_KEYS)


def pre_vf(p):
    """Поворот + дзеркало + колір — ставиться ПЕРЕД масштабом/позицією."""
    out = []
    rot = int(g(p, "rot")) % 360
    if rot == 90:
        out.append("transpose=1")
    elif rot == 180:
        out += ["hflip", "vflip"]
    elif rot == 270:
        out.append("transpose=2")
    if g(p, "flip"):
        out.append("hflip")
    if has_crop(p):
        fw, fh = crop_frac(p)
        out.append(f"crop=w='trunc(iw*{num(fw)}/2)*2':h='trunc(ih*{num(fh)}/2)*2':"
                   f"x='iw*{num(g(p, 'cropl'))}':y='ih*{num(g(p, 'cropt'))}'")
    if g(p, "stab"):
        out.append("deshake")
    if g(p, "deflick"):
        out.append("deflicker=size=5")
    if g(p, "mblur"):
        out.append("tmix=frames=3:weights='1 2 1'")
    v = _VFX.get(g(p, "vfx"))
    if v:
        out.append(v)
    out += adjust_vf(p)
    f = _FILTER_VF.get(g(p, "flt"))
    if f:
        out.append(f)
    br, ct, sat = float(g(p, "br")), float(g(p, "ct")), float(g(p, "sat"))
    if abs(br) > 1e-3 or abs(ct - 1) > 1e-3 or abs(sat - 1) > 1e-3:
        out.append(f"eq=brightness={num(br)}:contrast={num(ct)}:saturation={num(sat)}")
    return ",".join(out)


# ---------------------------------------------------------------- фейди -- #
def fade_win(t0, t1, fin, fout, kind="v", alpha=False):
    """Фейди для фрагмента, що на виході триває [t0, t1] (t0 може бути < 0, якщо
    відтворення почалось з середини). kind 'v' -> fade, 'a' -> afade."""
    name = "fade" if kind == "v" else "afade"
    al = ":alpha=1" if alpha else ""
    out = []
    fin, fout = max(0.0, float(fin)), max(0.0, float(fout))
    if fin > 0.01 and t0 + fin > 0:
        st = max(0.0, t0)
        d = t0 + fin - st
        if d > 0.01:
            out.append(f"{name}=t=in:st={num(st)}:d={num(d)}{al}")
    if fout > 0.01:
        st = t1 - fout
        d = fout
        if st < 0:
            d += st
            st = 0.0
        if d > 0.01:
            out.append(f"{name}=t=out:st={num(st)}:d={num(d)}{al}")
    return out


def alpha_factor(tau, dur, fin, fout):
    """Множник прозорості в момент tau від початку блока (для статичного прев'ю)."""
    a = 1.0
    if fin > 0.01 and tau < fin:
        a = min(a, max(0.0, tau / fin))
    if fout > 0.01 and tau > dur - fout:
        a = min(a, max(0.0, (dur - tau) / fout))
    return a


VOL_MAX_DB = 888.0          # стеля підсилення: справжні +888 dB (експериментально, «для угару»)
_DB300 = 20.0 * math.log10(3.0)   # 300% = +9.54 dB — далі показуємо децибели


def vol_db(v):
    """Гучність (множник амплітуди) -> dB. 1.0 = 0 dB, 3.0 = +9.54 dB."""
    v = float(v)
    return 20.0 * math.log10(v) if v > 0 else -math.inf


_DB_KNEE = 60.0             # до +60 dB гучність реально РОСТЕ (далі звук — суцільний «квадрат»)
_P300, _PKNEE = 0.6, 0.9   # 0.6..0.9 повзунка: +9.5..+60 dB рівномірно; 0.9..1: +60..+888 dB


def pos_vol(pos):
    """Позиція повзунка 0..1 -> множник гучності.
    0..0.5 -> 0..100%;  0.5..0.6 -> 100..300%;  0.6..0.9 -> +9.5..+60 dB (рівномірно, кожен
    рух чути);  0.9..1 -> +60..+888 dB (там уже лише «рве» — квадратично)."""
    pos = max(0.0, min(1.0, float(pos)))
    if pos <= 0.5:
        return pos * 2.0
    if pos <= _P300:
        db = (pos - 0.5) / (_P300 - 0.5) * _DB300
    elif pos <= _PKNEE:
        db = _DB300 + (_DB_KNEE - _DB300) * (pos - _P300) / (_PKNEE - _P300)
    else:
        db = _DB_KNEE + (VOL_MAX_DB - _DB_KNEE) * ((pos - _PKNEE) / (1.0 - _PKNEE)) ** 2
    return 10.0 ** (db / 20.0)


def vol_pos(v):
    v = max(0.0, float(v))
    if v <= 1.0:
        return v / 2.0
    db = min(VOL_MAX_DB, vol_db(v))
    if db <= _DB300:
        return 0.5 + db / _DB300 * (_P300 - 0.5)
    if db <= _DB_KNEE:
        return _P300 + (_PKNEE - _P300) * (db - _DB300) / (_DB_KNEE - _DB300)
    return _PKNEE + (1.0 - _PKNEE) * math.sqrt((db - _DB_KNEE) / (VOL_MAX_DB - _DB_KNEE))


def vol_label(v):
    """До 300% — проценти, далі — децибели (як просили)."""
    v = float(v)
    if v <= 3.0 + 1e-9:
        return f"{int(round(v * 100))}%"
    db = vol_db(v)
    return f"+{db:.0f} dB" if db >= 100 else f"+{db:.1f} dB"


def gain_chain(vol):
    """Справжнє підсилення на vol (до +888 dB). Число 10^44 не влазить у семпли, тому
    підсилюємо сходинками ≤40 dB з жорстким обрізанням після кожної — математично це
    РІВНО «помножити на vol, а потім цифрова стеля 0 dBFS»."""
    v = float(vol)
    if abs(v - 1.0) <= 1e-3:
        return []
    if v <= 0:
        return ["volume=0"]
    db = vol_db(v)
    if db <= 0.0:
        return [f"volume={db:.4f}dB"]
    # без лімітера: x * gain, потім жорстке обрізання x = min(1, max(-1, x)) — як на SlowWave
    n = max(1, int(math.ceil(db / 40.0)))
    out = []
    for _ in range(n):
        out += [f"volume={db / n:.4f}dB", "asoftclip=type=hard"]
    return out


LIVE_STAGES = 23           # 23 × ≤38.6 dB = до +888 dB (кожна сходинка — у межах float)


def live_stage(vol):
    """Множник ОДНІЄЇ сходинки живої гучності: загальне vol = stage ** LIVE_STAGES."""
    v = float(vol)
    return 0.0 if v <= 0 else v ** (1.0 / LIVE_STAGES)


def live_gain_af(vol):
    """Гучність кліпа для програвача, яку можна міняти НА ХОДУ (af-command): x·gain, потім
    жорстке обрізання до [-1, 1] — сходинками; при gain ≥ 1 це рівно один множник + обрізання."""
    g = f"{live_stage(vol):.9g}"
    st = ",".join(f"volume@lv{i}={g},asoftclip=type=hard" for i in range(LIVE_STAGES))
    return f"@lgain:lavfi=[{st}]"


# моно -> стерео БЕЗ втрати 3 dB (стандартне перетворення ffmpeg робить тихіше на 3 dB)
UPMIX = "aformat=channel_layouts=mono|stereo,pan=stereo|FL=FL+FC|FR=FR+FC"


def atempo_chain(sp):
    parts, v = [], float(sp)
    while v > 2.0:
        parts.append("atempo=2.0"); v /= 2.0
    while v < 0.5:
        parts.append("atempo=0.5"); v /= 0.5
    parts.append(f"atempo={v:.6f}")
    return parts


# ---- криві швидкості (як у CapCut): форма = множники швидкості в 5 точках кліпа;
#      ділимо кліп на CURVE_N шматків зі сталою швидкістю. p["speed"] = СЕРЕДНЯ швидкість
#      (тож уся математика тривалостей лишається як була), p["cbase"] = базова швидкість.
CURVES = {"montage": [2.0, 0.55, 2.0, 0.55, 2.0], "hero": [1.0, 1.0, 0.25, 1.0, 1.0],
          "bullet": [2.5, 2.2, 0.2, 2.2, 2.5], "jumpcut": [1.0, 1.0, 5.0, 1.0, 1.0],
          "flashin": [5.0, 2.5, 1.0, 1.0, 1.0], "flashout": [1.0, 1.0, 1.0, 2.5, 5.0]}
CURVE_N = 16


def curve_segs(p):
    c = CURVES.get(p.get("curve") or "")
    if not c:
        return None
    base = float(p.get("cbase", 1.0))
    out = []
    for i in range(CURVE_N):
        x0, x1 = i / CURVE_N, (i + 1) / CURVE_N
        xm = (x0 + x1) / 2 * (len(c) - 1)
        j = min(len(c) - 2, int(xm))
        f = xm - j
        out.append((x0, x1, max(0.05, base * (c[j] + (c[j + 1] - c[j]) * f))))
    return out


def curve_speed(p):
    segs = curve_segs(p)
    if not segs:
        return float(p.get("speed", 1.0))
    return 1.0 / sum((x1 - x0) / v for x0, x1, v in segs)


def _curve_T(segs, L, x):
    t = 0.0
    for x0, x1, v in segs:
        if x <= x0:
            break
        t += (min(x, x1) - x0) * L / v
    return t


def curve_setpts(p, start):
    """setpts: час виходу від точки start (секунда джерела) з кривою швидкості."""
    segs = curve_segs(p)
    s, L = float(p["s"]), max(0.01, float(p["e"]) - float(p["s"]))
    X = f"(({num(start - s)}+(PTS-STARTPTS)*TB)/{num(L)})"
    cum, parts = 0.0, []
    for x0, x1, v in segs:
        parts.append((x0, x1, v, cum))
        cum += (x1 - x0) * L / v
    x0, x1, v, c0 = parts[-1]
    e = f"{num(c0)}+({X}-{num(x0)})*{num(L / v)}"
    for x0, x1, v, c0 in reversed(parts[:-1]):
        e = f"if(lt({X},{num(x1)}),{num(c0)}+({X}-{num(x0)})*{num(L / v)},{e})"
    t0 = _curve_T(segs, L, (start - s) / L)
    return f"setpts='({e}-{num(t0)})/TB'"


def curve_atempo(p, start, uid):
    """Звук з кривою швидкості: шматки atrim + atempo, склеєні concat (від start)."""
    segs = curve_segs(p)
    s, L = float(p["s"]), max(0.01, float(p["e"]) - float(p["s"]))
    xs = (start - s) / L
    pcs = []
    for x0, x1, v in segs:
        if x1 <= xs + 1e-9:
            continue
        a = max(x0, xs)
        pcs.append(((a - xs) * L, (x1 - xs) * L, v))
    if not pcs:
        return "asetpts=PTS-STARTPTS"

    def one(st, en, v, last):
        tr = f"atrim=start={num(st)}" + ("" if last else f":end={num(en)}")
        return tr + ",asetpts=PTS-STARTPTS," + ",".join(atempo_chain(v))
    if len(pcs) == 1:
        return "asetpts=PTS-STARTPTS," + one(*pcs[0], True)
    k = len(pcs)
    out = "asetpts=PTS-STARTPTS,asplit=" + str(k) + "".join(f"[cs{uid}x{i}]" for i in range(k))
    for i, (st, en, v) in enumerate(pcs):
        out += f";[cs{uid}x{i}]" + one(st, en, v, i == k - 1) + f"[cd{uid}x{i}]"
    out += ";" + "".join(f"[cd{uid}x{i}]" for i in range(k)) + f"concat=n={k}:v=0:a=1"
    return out


def afx_default(p):
    return all(g(p, k) == PIECE_DEFAULTS[k] for k in AFX_KEYS)


def afx_chain(p):
    """Ефекти звуку: тон без зміни довжини, бас-буст, ефект (телефон/вода/8D/луна), реверб."""
    if not p:
        return []
    out = []
    pitch = float(g(p, "pitch") or 0.0)
    if abs(pitch) > 0.05:
        r = 2.0 ** (pitch / 12.0)
        out += ["aresample=44100", f"asetrate={int(round(44100 * r))}", "aresample=44100"]
        out += atempo_chain(1.0 / r)              # повертаємо довжину — змінюється лише тон
    bass = float(g(p, "bass") or 0.0)
    if bass > 0.3:
        out.append(f"bass=g={num(bass)}:f=100:w=0.6")
    e = _AEFF.get(g(p, "aeff"))
    if e:
        out.append(e)
    if g(p, "dn"):                       # шумодав (як «Зменшити шум» у CapCut)
        out.append("afftdn=nr=18:nf=-30")
    if g(p, "venh"):                     # покращити голос: зрізати гул, підняти розбірливість
        out += ["highpass=f=80", "equalizer=f=3000:t=q:w=1.2:g=4",
                "acompressor=threshold=0.125:ratio=3:attack=10:release=200:makeup=1.6"]
    rev = float(g(p, "rev") or 0.0)
    if rev > 0.02:
        a = 0.12 + 0.5 * rev
        out.append(f"aecho=0.85:{num(0.55 + 0.35 * rev)}:43|71|113|167|241:"
                   f"{num(a)}|{num(a * 0.75)}|{num(a * 0.55)}|{num(a * 0.4)}|{num(a * 0.28)}")
    return out


def audio_chain(obj, vol, fades, off=0.0):
    return [UPMIX] + afx_chain(obj) + kf_vol_af(obj, off) + gain_chain(vol) + list(fades)


# ----------------------------------------------------------------- текст -- #
def find_font():
    windir = os.environ.get("WINDIR", r"C:\Windows")
    for f in ("segoeuib.ttf", "arialbd.ttf", "seguisb.ttf", "arial.ttf", "tahomabd.ttf"):
        q = os.path.join(windir, "Fonts", f)
        if os.path.exists(q):
            return q
    return None


_E3_T = "(1-pow(1-u,3))"


def new_text(at, text="Text"):
    return {"text": text, "at": float(at), "dur": 3.0, "size": 0.085, "color": "#ffffff",
            "style": "outline", "nx": 0.0, "ny": 0.30, "zoom": 1.0, "fin": 0.25, "fout": 0.25}


def text_px(t, ch):
    return max(8, int(round(float(t["size"]) * ch * float(t.get("zoom", 1.0)))))


def write_text_file(t, folder, i):
    path = os.path.join(folder, f"txt_{i}.txt")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(clean_text(t["text"]))
    return path


def clean_text(s):
    """drawtext не вміє кольорові емодзі (малює квадратик) — прибираємо їх."""
    out = "".join(ch for ch in s.replace("\r", "")
                  if ord(ch) <= 0xFFFF and ch not in "️‍")
    return "\n".join(ln.rstrip() for ln in out.split("\n"))


# ---- шрифти Windows (з кирилицею), рамка / фон тексту, анімації тексту ----
FONTS = [("segoe", "segoeuib.ttf"), ("arial", "arialbd.ttf"), ("impact", "impact.ttf"),
         ("comic", "comicbd.ttf"), ("times", "timesbd.ttf"), ("georgia", "georgiab.ttf"),
         ("verdana", "verdanab.ttf"), ("trebuchet", "trebucbd.ttf"), ("consolas", "consolab.ttf"),
         ("script", "segoesc.ttf"), ("print", "segoepr.ttf")]


def font_path(name):
    windir = os.environ.get("WINDIR", r"C:\Windows")
    for k, fn in FONTS:
        if k == name:
            q = os.path.join(windir, "Fonts", fn)
            return q if os.path.exists(q) else None
    return None


def fonts_available():
    return [k for k, _ in FONTS if font_path(k)]


# In / Out: u = прогрес 0..1;  Loop: T = секунди від початку тексту.
# X / Y — зсув у частках кадру, A — множник прозорості. (Розмір шрифту в часі ffmpeg 8
# не вміє — падає, тому лише рух і прозорість.)
TEXT_IN = {
    "fade": {"A": "u"},
    "slide_up": {"Y": f"0.12*(1-{_E3_T})", "A": "min(1,u*2)"},
    "slide_down": {"Y": f"-0.12*(1-{_E3_T})", "A": "min(1,u*2)"},
    "slide_left": {"X": f"0.3*(1-{_E3_T})", "A": "min(1,u*2)"},
    "slide_right": {"X": f"-0.3*(1-{_E3_T})", "A": "min(1,u*2)"},
    "drop": {"Y": "-0.35*(1-u)*abs(cos(u*PI*1.5))", "A": "min(1,u*4)"},
    "blink": {"A": "if(lt(u,0.25),0,if(lt(u,0.4),1,if(lt(u,0.55),0,1)))"},
    "typewriter": {},
}
TEXT_OUT = {k: v for k, v in TEXT_IN.items() if k != "typewriter"}
TEXT_LOOP = {
    "float": {"Y": "0.015*sin(T*2.4)"},
    "shake": {"X": "0.006*sin(T*47)", "Y": "0.005*cos(T*53)"},
    "wave": {"X": "0.02*sin(T*3)"},
    "blink": {"A": "if(lt(sin(T*PI*2),0),0.25,1)"},
    "heartbeat": {"A": "0.55+0.45*abs(sin(T*PI*1.2))"},
    "jitter": {"X": "0.004*sin(T*91)", "Y": "0.004*sin(T*77)"},
}


def _text_exprs(t, a, b):
    """{X,Y,A: вираз від t} для анімацій тексту, що видно в [a, b]."""
    out = {}

    def put(k, e):
        out[k] = e if k not in out else (f"({out[k]})*({e})" if k == "A" else f"({out[k]})+({e})")
    for slot, table, rev in (("tin", TEXT_IN, False), ("tout", TEXT_OUT, True)):
        an = t.get(slot)
        if not an or an.get("type") not in table:
            continue
        d = max(0.05, min(float(an.get("d", 0.5)), max(0.05, b - a)))
        u = f"clip(({num(b)}-t)/{num(d)},0,1)" if rev else f"clip((t-{num(a)})/{num(d)},0,1)"
        for k, e in table[an["type"]].items():
            put(k, "(" + e.replace("u", "(" + u + ")") + ")")
    lp = t.get("tloop")
    if lp and lp.get("type") in TEXT_LOOP:
        for k, e in TEXT_LOOP[lp["type"]].items():
            put(k, "(" + e.replace("T", f"(t-{num(a)})") + ")")
    return out


def _typewriter(t):
    an = t.get("tin") or {}
    return an.get("type") == "typewriter"


def drawtext(t, cw, ch, font, txtfile, t0=None, t1=None, alpha_mul=1.0, local=None):
    """drawtext для тексту t на кадрі cw×ch. [t0, t1] — коли видно (вихідний час);
    None — завжди (статичний кадр прев'ю: alpha_mul = прозорість фейдів, local = секунда
    тексту, щоб показати анімацію в цей момент)."""
    fs = text_px(t, ch)
    font = font_path(t.get("font")) or font
    col = t.get("color", "#ffffff").lstrip("#")
    stc = (t.get("stroke") or "#000000").lstrip("#")
    dur = float(t.get("dur", 3.0))
    if t0 is None:                       # статичний кадр: виразам підставляємо час числом
        lt = 0.0 if local is None else float(local)
        ex = {k: num(_py(v.replace("if(", "if("), t=lt)) for k, v in _text_exprs(t, 0.0, dur).items()}
        win = (0.0, dur, lt)
    else:
        ex = _text_exprs(t, float(t0), float(t1))
        win = None
    X = f"+({ex['X']})*w" if "X" in ex else ""
    Y = f"+({ex['Y']})*h" if "Y" in ex else ""
    base = [f"fontfile={esc(font)}", "expansion=none",
            f"fontsize={fs}", f"fontcolor=0x{col}", f"line_spacing={max(2, fs // 6)}",
            f"x='(w-text_w)/2{float(t['nx']):+.4f}*w{X}'", f"y='(h-text_h)/2{float(t['ny']):+.4f}*h{Y}'"]
    st = t.get("style", "outline")
    if st == "box":
        bc = (t.get("bgc") or "#000000").lstrip("#")
        base += ["box=1", f"boxcolor=0x{bc}@{num(t.get('bga', 0.55))}", f"boxborderw={max(4, fs // 4)}"]
    elif st == "shadow":
        sh = max(1, fs // 16)
        base += [f"shadowx={sh}", f"shadowy={sh}", f"shadowcolor=0x{stc}@0.75"]
    elif st == "plain":
        pass
    else:
        base += [f"borderw={max(2, fs // 13)}", f"bordercolor=0x{stc}@0.9"]
    A = ex.get("A")
    alpha = None
    if t0 is not None:
        a, b = float(t0), float(t1)
        fi, fo = float(t.get("fin", 0)), float(t.get("fout", 0))
        fe = None
        if fi > 0.01 or fo > 0.01:
            fi = max(fi, 0.001)
            fo = max(fo, 0.001)
            fe = (f"if(lt(t,{num(a)}),0,if(lt(t,{num(a + fi)}),(t-{num(a)})/{num(fi)},"
                  f"if(lt(t,{num(b - fo)}),1,if(lt(t,{num(b)}),({num(b)}-t)/{num(fo)},0))))")
        if fe and A:
            alpha = f"({fe})*clip({A},0,1)"
        elif fe or A:
            alpha = fe or f"clip({A},0,1)"
    else:
        m = alpha_mul * (max(0.0, min(1.0, float(A))) if A else 1.0)
        if m < 0.999:
            alpha = num(max(0.0, m))
    if alpha:
        base.append(f"alpha='{alpha}'")
    # друкарська машинка: ряд drawtext із дедалі довшим початком тексту
    full = clean_text(t["text"])
    if _typewriter(t) and len(full) > 1:
        d = max(0.1, min(float(t["tin"].get("d", 1.0)), dur))
        G = min(len(full), 30)
        outs = []
        for i in range(1, G + 1):
            k = int(math.ceil(len(full) * i / G))
            pf = os.path.splitext(txtfile)[0] + f"_tw{i}.txt"
            with open(pf, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(full[:k])
            if t0 is not None:
                a, b = float(t0), float(t1)
                s0 = a + d * (i - 1) / G
                s1 = (a + d * i / G) if i < G else b
                en = f"enable='between(t,{num(s0)},{num(s1)})'"
            else:
                lt = win[2]
                s0, s1 = d * (i - 1) / G, (d * i / G if i < G else win[1] + 1)
                if not (s0 <= lt < s1 or (i == 1 and lt < 0)):
                    continue
                en = None
            outs.append("drawtext=" + ":".join(base + [f"textfile={esc(pf)}"] + ([en] if en else [])))
        if outs:
            return ",".join(outs)
    parts = base + [f"textfile={esc(txtfile)}"]
    if t0 is not None:
        parts.append(f"enable='between(t,{num(float(t0))},{num(float(t1))})'")
    return "drawtext=" + ":".join(parts)


# ------------------------------------------------------------- анімації -- #
# Анімація кліпа (як у CapCut: In / Out / Combo). Кожна — набір виразів ffmpeg від
# u (прогрес 0..1 анімації In/Out) або T (секунди від початку кліпа, для Combo):
#   S  — масштаб кадру (1 = як є),  X/Y — зсув у частках кадру,  A — поворот (рад),
#   B  — яскравість (+1 = білий спалах),  F — видимість (0 = чорний, 1 = як є).
# Ті самі рядки рахує і Python (живі прев'ю-плитки), тому в них лише функції,
# що є і в ffmpeg, і в Python: sin cos exp pow min max abs clip if lt PI.
ANIM_DEF_D = 0.6                 # тривалість In/Out за замовчуванням, с

_E3 = "(1-pow(1-u,3))"           # ease-out cubic

ANIMS_IN = {
    # key: (категорія, {параметр: вираз від u})
    "fade":        ("basic", {"F": "u"}),
    "zoom_in":     ("basic", {"S": f"0.25+0.75*{_E3}", "F": "min(1,u*3)"}),
    "zoom_out":    ("basic", {"S": f"1.7-0.7*{_E3}", "F": "min(1,u*2)"}),
    "pop":         ("basic", {"S": "1+0.35*sin(u*PI)*(1-u)", "F": "min(1,u*4)"}),
    "slide_left":  ("slide", {"X": f"-(1-{_E3})"}),
    "slide_right": ("slide", {"X": f"(1-{_E3})"}),
    "slide_up":    ("slide", {"Y": f"(1-{_E3})"}),
    "slide_down":  ("slide", {"Y": f"-(1-{_E3})"}),
    "drop":        ("slide", {"Y": "-(1-u)*abs(cos(u*PI*1.5))"}),
    "spin":        ("spin", {"A": f"-PI*(1-{_E3})", "S": f"0.3+0.7*{_E3}", "F": "min(1,u*3)"}),
    "swing":       ("spin", {"A": "0.6*(1-u)*cos(u*PI*3)"}),
    "rock":        ("shake", {"A": "0.25*(1-u)*sin(u*PI*8)"}),
    "shake":       ("shake", {"X": "0.06*(1-u)*sin(u*90)", "Y": "0.04*(1-u)*cos(u*70)"}),
    "flash":       ("light", {"B": "pow(1-u,2)"}),
    "blink":       ("light", {"F": "if(lt(u,0.25),0,if(lt(u,0.4),1,if(lt(u,0.55),0,1)))"}),
}
# Out — дзеркало In: той самий вираз, але u йде від 1 до 0 (кліп «зникає»)
ANIMS_OUT = {k: v for k, v in ANIMS_IN.items()}
ANIMS_COMBO = {
    "pulse":    ("basic", {"S": "1+0.06*sin(T*PI*2/0.8)"}),
    "kenburns": ("basic", {"S": "1+0.18*T/D"}),
    "float":    ("slide", {"Y": "0.03*sin(T*2.4)"}),
    "sway":     ("spin", {"A": "0.07*sin(T*3)"}),
    "spin":     ("spin", {"A": "T*PI*2/3", "S": "0.8"}),
    "shake":    ("shake", {"X": "0.012*sin(T*47)", "Y": "0.010*cos(T*53)"}),
    "quake":    ("shake", {"X": "0.03*sin(T*61)*abs(sin(T*3))", "A": "0.03*sin(T*37)"}),
    "flicker":  ("light", {"B": "0.18*abs(sin(T*13))*lt(sin(T*5),0)"}),
    "strobe":   ("light", {"F": "if(lt(sin(T*PI*4),0),0.35,1)"}),
}
ANIM_CATS = ["all", "basic", "slide", "spin", "shake", "light"]


def anim_table(kind):
    return {"in": ANIMS_IN, "out": ANIMS_OUT, "combo": ANIMS_COMBO}[kind]


def has_anim(p):
    return bool(p.get("ain") or p.get("aout") or p.get("acombo") or has_kf(p)
                or float(g(p, "opa")) < 0.999)


# ------------------------------------------------------------- ключові кадри -- #
# p["kf"] = {"zoom"|"nx"|"ny"|"ang"|"opa"|"vol": [[ts, value], ...]} — ts = секунда ДЖЕРЕЛА
# (тому розрізання / обрізка кліпа не зсувають ключі). Значення — абсолютні; між ключами
# лінійно, до першого / після останнього — значення крайнього ключа (як у CapCut).
# Словник і списки НЕ змінюємо на місці (undo тримає копії) — лише замінюємо.
KF_KEYS = ("zoom", "nx", "ny", "ang", "opa", "vol", "op")
KF_DEF = {"zoom": 1.0, "nx": 0.0, "ny": 0.0, "ang": 0.0, "opa": 1.0, "vol": 1.0, "op": 1.0}
OVL_KF_KEYS = ("zoom", "nx", "ny", "op")


def has_kf(p, key=None):
    kf = p.get("kf") or {}
    if key:
        return bool(kf.get(key))
    return any(kf.get(k) for k in KF_KEYS)


def kf_times(p):
    """Усі секунди джерела, де в кліпа є ключ (будь-якого параметра)."""
    out = set()
    for k in KF_KEYS:
        for ts, _v in (p.get("kf") or {}).get(k) or []:
            out.add(round(float(ts), 3))
    return sorted(out)


def kf_base(p, key):
    if key == "opa":
        return float(g(p, "opa"))
    return float(p.get(key, KF_DEF[key]) or 0.0)


def kf_val(p, key, ts):
    pts = (p.get("kf") or {}).get(key)
    if not pts:
        return kf_base(p, key)
    if ts <= pts[0][0]:
        return float(pts[0][1])
    for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
        if ts <= t1:
            return float(v0) + (float(v1) - float(v0)) * (ts - t0) / max(1e-6, t1 - t0)
    return float(pts[-1][1])


def kf_set(p, key, ts, val, eps=0.02):
    """Новий p["kf"] з ключем key у ts (замінює ключ, що ближче за eps)."""
    kf = dict(p.get("kf") or {})
    pts = [list(x) for x in (kf.get(key) or []) if abs(float(x[0]) - ts) > eps]
    pts.append([round(float(ts), 4), float(val)])
    kf[key] = sorted(pts)
    p["kf"] = kf


def kf_del_at(p, ts, eps=0.02):
    kf = {}
    for k, pts in (p.get("kf") or {}).items():
        keep = [x for x in pts if abs(float(x[0]) - ts) > eps]
        if keep:
            kf[k] = keep
    p["kf"] = kf


def kf_expr(p, key, tsx):
    """Вираз ffmpeg: значення key в момент tsx (вираз секунди джерела)."""
    pts = (p.get("kf") or {}).get(key) or []
    if not pts:
        return None
    e = num(pts[-1][1])
    for (t0, v0), (t1, v1) in reversed(list(zip(pts, pts[1:]))):
        lin = f"{num(v0)}+({num(float(v1) - float(v0))})*(({tsx})-{num(t0)})/{num(max(1e-6, t1 - t0))}"
        e = f"if(lt({tsx},{num(t1)}),{lin},{e})"
    return f"if(lt({tsx},{num(pts[0][0])}),{num(pts[0][1])},{e})"


def _kf_params(p):
    """S/X/Y/A/F від ключових кадрів (відносно статичних zoom/nx/ny/ang кліпа)."""
    out = {}
    tsx = f"({num(p.get('s', 0.0))}+(t)*{num(p.get('speed', 1.0))})"
    zb = max(0.01, float(p.get("zoom", 1.0)))
    ze = kf_expr(p, "zoom", tsx)
    S = f"(({ze})/{num(zb)})" if ze else None
    if S:
        out["S"] = S
    for key, ax in (("nx", "X"), ("ny", "Y")):
        e = kf_expr(p, key, tsx)
        b = float(p.get(key, 0.0))
        if e or (S and abs(b) > 1e-4):
            cur = f"({e})" if e else num(b)
            out[ax] = f"({cur}-{num(b)}*{S or '1'})"
    e = kf_expr(p, "ang", tsx)
    if e:
        out["A"] = f"((({e})-{num(float(p.get('ang', 0.0) or 0.0))})*PI/180)"
    e = kf_expr(p, "opa", tsx)
    if e:
        out["F"] = f"clip({e},0,1)"
    elif float(g(p, "opa")) < 0.999:
        out["F"] = num(g(p, "opa"))
    return out


def kf_vol_af(p, off=0.0):
    """Ключі гучності -> volume з виразом (множник відносно статичної гучності кліпа)."""
    if not p or not has_kf(p, "vol"):
        return []
    vb = float(p.get("vol", 1.0))
    if vb <= 0.005:
        return []
    tsx = f"({num(p.get('s', 0.0))}+(t+{num(off)})*{num(p.get('speed', 1.0))})"
    return [f"volume=volume='max(0,{kf_expr(p, 'vol', tsx)})/{num(vb)}':eval=frame"]


# ------------------------------------------------- накладки: хромакей / маска -- #
MASKS = ["none", "circle", "rect", "heart", "star", "split", "line"]
_MASK = {
    "circle": "lte(pow((X-W/2)/(W/2),2)+pow((Y-H/2)/(H/2),2),1)",
    "rect": "lte(pow(abs(X-W/2)/(W/2),8)+pow(abs(Y-H/2)/(H/2),8),0.8)",
    "heart": "lte(pow(pow(1.25*(X-W/2)/(W/2),2)+pow(1.25*(H/2-Y)/(H/2)+0.25,2)-1,3)"
             "-pow(1.25*(X-W/2)/(W/2),2)*pow(1.25*(H/2-Y)/(H/2)+0.25,3),0)",
    "star": "lte(hypot((X-W/2)/(W/2),(Y-H/2)/(H/2)),0.55+0.4*cos(5*atan2(X-W/2,H/2-Y)))",
    "split": "lt(X,W/2)",
    "line": "lt(abs(Y-H/2),H/6)",
}


def key_mask_vf(o):
    """Хромакей (прибрати колір фону) і форма-маска для накладки -> рядок або ''."""
    out = []
    ck = o.get("ck")
    if ck:
        sim = max(0.01, min(1.0, float(o.get("cks", 0.3))))
        out.append(f"format=rgba,colorkey=0x{ck.lstrip('#')}:{num(sim)}:{num(min(1.0, sim * 0.4 + 0.02))}")
    m = _MASK.get(o.get("mask") or "none")
    if m:
        if o.get("minv"):
            m = f"1-{m}"
        out.append(f"format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*({m})'")
    return ",".join(out)


def _expr_params(p, dur):
    """Словник {S,X,Y,A,B,F: вираз від t (вихідний час кліпа від 0)} або {}."""
    out = dict(_kf_params(p))

    def put(key, e, mode):
        if key not in out:
            out[key] = e
        elif key in ("S", "F"):
            out[key] = f"({out[key]})*({e})"
        else:
            out[key] = f"({out[key]})+({e})"
    dur = max(0.05, float(dur))
    for slot, table in (("ain", ANIMS_IN), ("aout", ANIMS_OUT)):
        a = p.get(slot)
        if not a or a.get("type") not in table:
            continue
        d = max(0.05, min(float(a.get("d", ANIM_DEF_D)), dur))
        u = f"clip(t/{num(d)},0,1)" if slot == "ain" else f"clip(({num(dur)}-t)/{num(d)},0,1)"
        for key, e in table[a["type"]][1].items():
            put(key, "(" + e.replace("u", "(" + u + ")") + ")", slot)
    a = p.get("acombo")
    if a and a.get("type") in ANIMS_COMBO:
        for key, e in ANIMS_COMBO[a["type"]][1].items():
            put(key, "(" + e.replace("T", "(t)").replace("D", num(dur)) + ")", "combo")
    return out


def anim_vf(p, cw, ch, fps, dur, off=0.0, uid=0):
    """Фільтр анімації для кадру cw×ch (ставиться ПІСЛЯ масштабу/позиції кліпа).
    off — з якої секунди кліпа почалось відтворення (t у графі тоді рахується від 0).
    Повертає рядок для вставки в ланцюжок через кому (може містити ; і мітки) або ''."""
    ex = _expr_params(p, dur)
    if not ex:
        return ""
    if off:
        ex = {k: v.replace("(t)", f"(t+{num(off)})").replace("clip(t/", f"clip((t+{num(off)})/")
              .replace(f"clip(({num(dur)}-t)", f"clip(({num(dur)}-(t+{num(off)}))")
              for k, v in ex.items()}
    q = lambda e: "'" + e + "'"
    out = []
    if "A" in ex:
        out.append(f"rotate=a={q(ex['A'])}:ow=iw:oh=ih:c=black")
    if "S" in ex:
        # масштаб, що змінюється в часі: розмір кадру ПОСТІЙНИЙ (overlay не вміє міняти розмір
        # на ходу). Збільшення > 1 — масштаб + обрізка по центру; зменшення < 1 — масштаб + поля.
        s = ex["S"]
        out.append(f"scale=w={q(f'trunc({cw}*max({s},1)/2)*2')}:h={q(f'trunc({ch}*max({s},1)/2)*2')}:eval=frame,"
                   f"crop=w={cw}:h={ch}:x='(iw-ow)/2':y='(ih-oh)/2',"
                   f"scale=w={q(f'max(2,trunc({cw}*min({s},1)/2)*2)')}:h={q(f'max(2,trunc({ch}*min({s},1)/2)*2)')}:eval=frame,"
                   f"pad=w={cw}:h={ch}:x='(ow-iw)/2':y='(oh-ih)/2':eval=frame")
    if "X" in ex or "Y" in ex:
        lab = f"an{uid}"
        x = f"({ex.get('X', '0')})*W"
        y = f"({ex.get('Y', '0')})*H"
        out.append(f"format=yuv420p[{lab}s];color=c=black:s={cw}x{ch}:r={num(fps)}[{lab}b];"
                   f"[{lab}b][{lab}s]overlay=x={q(x)}:y={q(y)}:eval=frame:shortest=1")
    if "B" in ex or "F" in ex:
        b = ex.get("B", "0")
        f = ex.get("F", "1")
        # eq: Y' = (Y-0.5)*c + 0.5 + b.  c = F, b = 0.5F-0.5 (+B)  ->  Y' = F*Y (+B у бік білого)
        out.append(f"eq=brightness={q(f'clip(({b})+0.5*({f})-0.5,-1,1)')}:"
                   f"contrast={q(f'clip({f},0,2)')}:saturation={q(f'clip({f},0,3)')}:eval=frame")
    return ",".join(out)


# --- той самий вираз у Python (для живих плиток у панелі) ---
def _clip(v, a, b):
    return max(a, min(b, v))


_PYENV = {"sin": math.sin, "cos": math.cos, "exp": math.exp, "pow": pow, "min": min, "max": max,
          "abs": abs, "clip": _clip, "PI": math.pi, "trunc": math.trunc,
          "lt": lambda a, b: 1.0 if a < b else 0.0, "if": None}


def _py(expr, **vars_):
    e = expr.replace("if(", "_if(")
    env = dict(_PYENV, _if=lambda c, a, b: a if c else b, **vars_)
    try:
        return float(eval(e, {"__builtins__": {}}, env))
    except Exception:
        return 0.0


def anim_sample(kind, key, x, dur=2.0):
    """Значення (S,X,Y,A,B,F) анімації в момент x (In/Out: x = прогрес 0..1; Combo: секунди)."""
    table = anim_table(kind)
    if key not in table:
        return 1.0, 0.0, 0.0, 0.0, 0.0, 1.0
    ex = table[key][1]
    if kind == "combo":
        v = lambda k, d: _py(ex[k].replace("T", "(T)").replace("D", str(dur)), T=x) if k in ex else d
    else:
        u = x if kind == "in" else 1.0 - x
        v = lambda k, d: _py(ex[k], u=u) if k in ex else d
    return v("S", 1.0), v("X", 0.0), v("Y", 0.0), v("A", 0.0), v("B", 0.0), v("F", 1.0)
