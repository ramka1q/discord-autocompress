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
                  "novideo": False}     # «видалити відео — лишити звук»
AFX_KEYS = ("pitch", "bass", "rev", "aeff")
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

TRANSITIONS = ["fade", "fadeblack", "fadewhite", "slideleft", "wipeleft", "smoothleft",
               "circleopen", "zoomin", "pixelize", "radial"]

TEXT_COLORS = ["#ffffff", "#ffd23f", "#ff4d4d", "#4cc9ff", "#33c27f", "#ff7ad9", "#000000"]
TEXT_STYLES = ["outline", "box", "shadow"]


def g(p, key):
    """Властивість кліпа/накладки з дефолтом (для старих словників)."""
    return p.get(key, PIECE_DEFAULTS.get(key))


def is_default(p):
    return all(g(p, k) == v for k, v in PIECE_DEFAULTS.items())


def look_default(p):
    """Колір/поворот без змін (кадр із кешу скрабу можна показувати як є)."""
    return (all(g(p, k) == PIECE_DEFAULTS[k] for k in ("flt", "br", "ct", "sat", "rot", "flip"))
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
        return h, w
    return w, h


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
    rev = float(g(p, "rev") or 0.0)
    if rev > 0.02:
        a = 0.12 + 0.5 * rev
        out.append(f"aecho=0.85:{num(0.55 + 0.35 * rev)}:43|71|113|167|241:"
                   f"{num(a)}|{num(a * 0.75)}|{num(a * 0.55)}|{num(a * 0.4)}|{num(a * 0.28)}")
    return out


def audio_chain(obj, vol, fades):
    return [UPMIX] + afx_chain(obj) + gain_chain(vol) + list(fades)


# ----------------------------------------------------------------- текст -- #
def find_font():
    windir = os.environ.get("WINDIR", r"C:\Windows")
    for f in ("segoeuib.ttf", "arialbd.ttf", "seguisb.ttf", "arial.ttf", "tahomabd.ttf"):
        q = os.path.join(windir, "Fonts", f)
        if os.path.exists(q):
            return q
    return None


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


def drawtext(t, cw, ch, font, txtfile, t0=None, t1=None, alpha_mul=1.0):
    """drawtext для тексту t на кадрі cw×ch. [t0, t1] — коли видно (вихідний час);
    None — завжди (статичний кадр прев'ю, тоді alpha_mul = прозорість у цей момент)."""
    fs = text_px(t, ch)
    col = t.get("color", "#ffffff").lstrip("#")
    parts = [f"fontfile={esc(font)}", f"textfile={esc(txtfile)}", "expansion=none",
             f"fontsize={fs}", f"fontcolor=0x{col}", f"line_spacing={max(2, fs // 6)}",
             f"x=(w-text_w)/2{float(t['nx']):+.4f}*w", f"y=(h-text_h)/2{float(t['ny']):+.4f}*h"]
    st = t.get("style", "outline")
    if st == "box":
        parts += ["box=1", "boxcolor=black@0.55", f"boxborderw={max(4, fs // 4)}"]
    elif st == "shadow":
        sh = max(1, fs // 16)
        parts += [f"shadowx={sh}", f"shadowy={sh}", "shadowcolor=black@0.75"]
    else:
        parts += [f"borderw={max(2, fs // 13)}", "bordercolor=black@0.9"]
    if t0 is not None:
        a, b = float(t0), float(t1)
        parts.append(f"enable='between(t,{num(a)},{num(b)})'")
        fi, fo = float(t.get("fin", 0)), float(t.get("fout", 0))
        if fi > 0.01 or fo > 0.01:
            fi = max(fi, 0.001)
            fo = max(fo, 0.001)
            parts.append(f"alpha='if(lt(t,{num(a)}),0,if(lt(t,{num(a + fi)}),(t-{num(a)})/{num(fi)},"
                         f"if(lt(t,{num(b - fo)}),1,if(lt(t,{num(b)}),({num(b)}-t)/{num(fo)},0))))'")
    elif alpha_mul < 0.999:
        parts.append(f"alpha={num(max(0.0, alpha_mul))}")
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
    return bool(p.get("ain") or p.get("aout") or p.get("acombo"))


def _expr_params(p, dur):
    """Словник {S,X,Y,A,B,F: вираз від t (вихідний час кліпа від 0)} або {}."""
    out = {}

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
