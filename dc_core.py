#!/usr/bin/env python3
"""
dc_core — спільне ядро стиснення відео під Discord (через ffmpeg).
Використовується і ручним компресором (discord_compressor.py),
і авто-вартовим (discord_autowatch.py).
Тільки стандартна бібліотека + ffmpeg/ffprobe у PATH.
"""
import math
import os
import re
import shutil
import struct
import subprocess
import tempfile
import time

# Prefer the current WinGet ffmpeg before any stale copy another application may
# have placed earlier in PATH.  All video entry points import dc_core, so doing
# this here also repairs the auto-overlay, watcher and editor in one place.
try:
    import deps
    deps.refresh_path()
except Exception:
    pass

try:
    import i18n
except Exception:          # ядро має працювати навіть без перекладів
    i18n = None

NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

DEBUG_LOG = os.path.join(tempfile.gettempdir(), "dac_debug.log")

# Мова повідомлень ядра (overlay/editor виставляють її з конфіга).
LANG = "en"


def _t(key, **kw):
    """Локалізоване повідомлення ядра (раніше всі помилки були лише українською)."""
    if i18n is None:
        return key
    return i18n.tr(LANG, key, **kw)


def cancelled_msg() -> str:
    return _t("core_cancel")


# ---- постійний фреймрейт: новий ffmpeg хоче -fps_mode, старий знає лише -vsync ----
_CFR_ARGS = None


def cfr_args() -> list:
    """['-fps_mode','cfr'] на ffmpeg ≥5.1, інакше ['-vsync','cfr'] (перевіряємо один раз)."""
    global _CFR_ARGS
    if _CFR_ARGS is None:
        try:
            rc = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                                 "-i", "nullsrc=s=16x16:d=0.1", "-fps_mode", "cfr",
                                 "-f", "null", "-"], capture_output=True,
                                creationflags=NO_WINDOW, timeout=20).returncode
            _CFR_ARGS = ["-fps_mode", "cfr"] if rc == 0 else ["-vsync", "cfr"]
        except Exception:
            _CFR_ARGS = ["-vsync", "cfr"]
    return list(_CFR_ARGS)


# ---- кодування на ВІДЕОКАРТІ: NVIDIA NVENC / Intel Quick Sync / AMD AMF ----
HW_ENCODE = True   # False = завжди процесор (режим «cpu» з вкладки «Відеокарта»)
ENCODER_MODE = "auto"   # "auto" | "gpu" | "cpu" — з налаштувань
ENCODER_BEST = ""       # переможець тесту швидкості ("x264" або h264_*), "" = тест не робили
_HW = None         # знайдений енкодер ("" = нема), визначається один раз
HW_NAMES = {"h264_nvenc": "NVIDIA NVENC", "h264_qsv": "Intel Quick Sync", "h264_amf": "AMD AMF"}


def _hw_args(enc, kbps):
    """Параметри енкодера відеокарти під заданий бітрейт (VBR з обмеженням піку)."""
    mx, buf = f"{int(kbps * 1.5)}k", f"{kbps * 2}k"
    if enc == "h264_nvenc":
        return ["-c:v", enc, "-preset", "p5", "-tune", "hq", "-rc", "vbr",
                "-multipass", "fullres", "-b:v", f"{kbps}k", "-maxrate", mx, "-bufsize", buf]
    if enc == "h264_qsv":
        return ["-c:v", enc, "-preset", "medium", "-b:v", f"{kbps}k", "-maxrate", mx,
                "-bufsize", buf]
    return ["-c:v", enc, "-quality", "balanced", "-rc", "vbr_peak", "-b:v", f"{kbps}k",
            "-maxrate", mx, "-bufsize", buf]


def configure(cfg):
    """Застосовує вибір з вкладки «Відеокарта» (викликає overlay при старті/зміні)."""
    global ENCODER_MODE, ENCODER_BEST, HW_ENCODE
    ENCODER_MODE = cfg.get("encoder", "auto") if cfg.get("encoder") in ("auto", "gpu", "cpu") else "auto"
    ENCODER_BEST = cfg.get("encoder_best", "") or ""
    HW_ENCODE = ENCODER_MODE != "cpu"


def active_hw() -> str:
    """Яким енкодером відеокарти стискати ЗАРАЗ ("" = процесор)."""
    if ENCODER_MODE == "cpu" or not HW_ENCODE:
        return ""
    if ENCODER_MODE == "auto" and ENCODER_BEST == "x264":
        return ""      # тест показав, що процесор тут швидший
    return hw_encoder()


def benchmark(progress_cb=None, should_cancel=None):
    """Тест «що стискає найшвидше»: те саме 8-секундне 1080p-відео стискаємо під 4 МБ
    процесором (x264, 2 проходи) і кожною відеокартою, що є. Повертає
    [{"enc": "x264"|h264_*, "sec": float|None, "mb": float}] — від найшвидшого."""
    import time as _time
    tmp = tempfile.mkdtemp(prefix="dac_bench_")
    src = os.path.join(tmp, "src.mp4")
    try:
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=30:d=8",
                        "-f", "lavfi", "-i", "sine=d=8", "-c:v", "libx264", "-preset", "ultrafast",
                        "-crf", "12", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", src],
                       capture_output=True, creationflags=NO_WINDOW)
        info = ffprobe_info(src)
        cands = ["x264"]
        for enc in ("h264_nvenc", "h264_qsv", "h264_amf"):
            if enc == hw_encoder() or _probe_hw(enc):
                cands.append(enc)
        res = []
        for i, enc in enumerate(cands):
            if should_cancel and should_cancel():
                break
            base, span = i * 100.0 / len(cands), 100.0 / len(cands)
            out = os.path.join(tmp, f"o_{enc}.mp4")
            t0 = _time.monotonic()
            ok, _msg, mb = compress(src, out, 4, 0, 128, info, force_enc=enc,
                                    progress_cb=(lambda p, b=base, s=span: progress_cb(b + p * s / 100))
                                    if progress_cb else None, should_cancel=should_cancel)
            res.append({"enc": enc, "sec": (_time.monotonic() - t0) if ok else None, "mb": mb})
        if progress_cb:
            progress_cb(100.0)
        res.sort(key=lambda r: r["sec"] if r["sec"] else 1e9)
        return res
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _probe_hw(enc) -> bool:
    try:
        return subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                               "-i", "testsrc=s=320x240:d=0.4", *_hw_args(enc, 800),
                               "-pix_fmt", "yuv420p", "-f", "null", "-"],
                              capture_output=True, creationflags=NO_WINDOW,
                              timeout=25).returncode == 0
    except Exception:
        return False


def hw_encoder() -> str:
    """Перший енкодер відеокарти, що РЕАЛЬНО кодує на цьому ПК (тест на 0.4 с відео),
    або "" — тоді працює процесор (x264). Результат кешується."""
    global _HW
    if _HW is None:
        found = ""
        for enc in ("h264_nvenc", "h264_qsv", "h264_amf"):
            if _probe_hw(enc):
                found = enc
                break
        _HW = found
        dlog(f"hw_encoder detected: {found or 'none'}")
    return _HW


# ---- куди класти результат: поруч з оригіналом, а якщо там не можна писати —
#      у %TEMP%\DiscordAutoCompress (напр. відео з read-only теки, архіву чи мережі) ----
FALLBACK_DIR = os.path.join(tempfile.gettempdir(), "DiscordAutoCompress")


def _dir_writable(d: str) -> bool:
    try:
        fd, probe = tempfile.mkstemp(prefix=".dac_w_", dir=d or ".")
        os.close(fd)
        os.remove(probe)
        return True
    except Exception:
        return False


def out_base(path: str) -> str:
    """База імені вихідного файла (без розширення) у теці, куди точно можна писати."""
    base, _ = os.path.splitext(path)
    if _dir_writable(os.path.dirname(os.path.abspath(path))):
        return base
    try:
        os.makedirs(FALLBACK_DIR, exist_ok=True)
    except OSError:
        pass
    return os.path.join(FALLBACK_DIR, os.path.basename(base))


def dlog(msg: str):
    """Проста діагностика у файл (%TEMP%\\dac_debug.log). Ніколи не кидає виняток."""
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass
TIME_RE = re.compile(r"out_time=(\d+):(\d+):(\d+\.\d+)")
VIDEO_EXT = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".m4v", ".wmv", ".mpg", ".mpeg", ".ts"}


def have_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, creationflags=NO_WINDOW)
        subprocess.run(["ffprobe", "-version"], capture_output=True, creationflags=NO_WINDOW)
        return True
    except FileNotFoundError:
        return False


BUILD = "2026-11-17-v2.7.2-low-bitrate"   # маркер версії коду — щоб у логах бачити, чи юзер на новому коді


def probe_diag(path: str) -> str:
    """Діагностика відео для логів: start_time, r/avg fps, к-ть кадрів, тривалості."""
    def p(args):
        return subprocess.run(["ffprobe", "-v", "error", *args],
                              capture_output=True, text=True, creationflags=NO_WINDOW).stdout.strip()
    st = p(["-select_streams", "v:0", "-show_entries", "stream=start_time,r_frame_rate,"
            "avg_frame_rate,nb_frames,duration", "-of", "default=noprint_wrappers=1", path])
    fdur = p(["-show_entries", "format=start_time,duration", "-of", "default=noprint_wrappers=1", path])
    return ("PROBE " + path.replace("\n", " ") + " | " + st.replace("\n", " ") + " | " +
            fdur.replace("\n", " "))


def ffprobe_info(path: str) -> dict:
    """{'duration','width','height','has_audio'}; кидає виняток при помилці."""
    def probe(args):
        out = subprocess.run(["ffprobe", "-v", "error", *args],
                             capture_output=True, text=True, creationflags=NO_WINDOW)
        return out.stdout.strip()

    duration = float(probe(["-show_entries", "format=duration",
                            "-of", "default=noprint_wrappers=1:nokey=1", path]) or 0)
    wh = probe(["-select_streams", "v:0", "-show_entries", "stream=width,height",
                "-of", "csv=s=x:p=0", path])
    width = height = 0
    if "x" in wh:
        try:
            width, height = (int(x) for x in wh.split("x")[:2])
        except ValueError:
            pass
    acodec = probe(["-select_streams", "a:0", "-show_entries", "stream=codec_type",
                    "-of", "default=noprint_wrappers=1:nokey=1", path])
    rfr = probe(["-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                 "-of", "default=noprint_wrappers=1:nokey=1", path])
    fps = 30.0
    try:
        num, den = rfr.split("/")
        fps = float(num) / float(den) if float(den) else float(num)
    except (ValueError, ZeroDivisionError):
        try:
            fps = float(rfr)
        except ValueError:
            pass
    if fps <= 0 or fps > 240:
        fps = 30.0
    return {"duration": duration, "width": width, "height": height,
            "has_audio": acodec.strip() == "audio", "fps": fps}


def target_ceiling(target_mb: float) -> float:
    """Гарантована «стеля» розміру: трохи НИЖЧЕ ліміту, щоб Discord точно пропустив.
    Напр. ліміт 10 -> 9.8, 25 -> 24.5, 50 -> 49, 500 -> 490.
    Запас = максимум із 0.2 МБ та 2 % ліміту (2-прохідний x264 злегка перевищує бітрейт)."""
    return max(0.5, target_mb - max(0.2, target_mb * 0.02))


def calc_video_kbps(duration: float, target_mb: float, audio_kbps: int, has_audio: bool) -> int | None:
    if duration <= 0:
        return None
    # цілимось у стелю (нижче ліміту), а не в сам ліміт — щоб гарантовано влізло
    target_bits = target_ceiling(target_mb) * 8 * 1024 * 1024
    audio_bits = audio_kbps * 1000 * duration if has_audio else 0
    return int((target_bits - audio_bits) / duration / 1000)


MIN_VKBPS = 30     # нижче цього відео — суцільна каша; відмовляємось чесно


def fit_bitrates(duration: float, target_mb: float, audio_kbps: int, has_audio: bool):
    """Бітрейти (звук, відео) під ліміт. Якщо на відео лишається замало (довге відео в
    малий розмір) — звук автоматично знижується аж до 24 kbps моно, щоб відео вистачило.
    Повертає (audio_kbps, video_kbps) або (audio_kbps, None), якщо не влізе навіть так."""
    a = int(audio_kbps or 0)
    v = calc_video_kbps(duration, target_mb, a, has_audio)
    if not has_audio or a <= 0:
        return a, (v if v and v >= MIN_VKBPS else None)
    if v and v >= 150:
        return a, v
    for a2 in (64, 48, 32, 24):
        if a2 >= a:
            continue
        a, v = a2, calc_video_kbps(duration, target_mb, a2, has_audio)
        if v and v >= 150:
            return a, v
    return a, (v if v and v >= MIN_VKBPS else None)


def audio_enc_args(audio_kbps: int) -> list:
    """AAC під бітрейт; на дуже низькому — моно (звучить краще, ніж стерео з 24 kbps)."""
    return ["-c:a", "aac", "-b:a", f"{int(audio_kbps)}k"] + (["-ac", "1"] if audio_kbps <= 48 else [])


def pick_auto_scale(info: dict, target_mb: float, audio_kbps: int) -> int:
    """Авто-підбір висоти кадру так, щоб бітрейт лишався пристойним.
    0 = лишити оригінал. Повертає одне з: 0/1080/720/480/360 — це КОРОТША сторона кадру,
    тож вертикальне відео з телефона (1080x1920) не стискається втричі сильніше за горизонтальне."""
    w, h = info.get("width") or 0, info.get("height") or 0
    h = min(w, h) if (w and h) else (h or 9999)
    candidates = [0] + [c for c in (1080, 720, 480, 360, 240) if c < h]
    audio_kbps, _ = fit_bitrates(info["duration"], target_mb, audio_kbps, info["has_audio"])
    for scale in candidates:
        eff_h = h if scale == 0 else min(scale, h)
        # орієнтовний «добрий» бітрейт ~ 2.2 kbps на рядок висоти (груба евристика)
        good = eff_h * 2.2
        v = calc_video_kbps(info["duration"], target_mb, audio_kbps, info["has_audio"]) or 0
        if v >= good:
            return scale
    return candidates[-1]  # навіть так замало — беремо найменший (але ніколи не збільшуємо кадр)


def _run_pass(cmd, duration, base_pct, span, progress_cb, should_cancel):
    cmd = cmd + ["-progress", "pipe:1", "-nostats", "-loglevel", "error"]
    # utf-8 + replace: ffmpeg пише UTF-8, а локальне cp1251 падало на деяких іменах файлів
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace",
                            creationflags=NO_WINDOW)
    error_tail = []
    for line in proc.stdout:
        line = line.rstrip()
        if should_cancel and should_cancel():
            proc.terminate()
            break
        m = TIME_RE.search(line)
        if m and duration > 0 and progress_cb:
            hh, mn, ss = m.groups()
            done = int(hh) * 3600 + int(mn) * 60 + float(ss)
            progress_cb(base_pct + min(1.0, done / duration) * span)
        elif line and "=" not in line:
            error_tail.append(line)
            del error_tail[:-8]
    proc.wait()
    try:
        proc.stdout.close()
    except Exception:
        pass
    if proc.returncode != 0 and error_tail:
        dlog("ffmpeg failed rc=%s: %s" % (proc.returncode, " | ".join(error_tail)))
    return proc.returncode


def compress(path, out_path, target_mb, scale, audio_kbps, info,
             progress_cb=None, should_cancel=None, start=None, dur=None, force_enc=None):
    """Двопрохідне H.264 з ГАРАНТІЄЮ розміру під ліміт Discord.
    Цілиться у стелю (target_ceiling), а після кодування перевіряє реальний розмір і,
    якщо трохи перевищив — знижує бітрейт і перекодовує (лише pass 2, лог pass 1 переюзуємо).
    start/dur (сек) — необовʼязковий сегмент для обрізки.
    force_enc — "x264" або h264_* (для тесту швидкості); None = за налаштуваннями.
    Повертає (ok: bool, message: str, final_mb: float)."""
    duration = dur if dur is not None else info["duration"]
    audio_kbps, v_kbps = fit_bitrates(duration, target_mb, audio_kbps, info["has_audio"])
    has_audio = info["has_audio"] and audio_kbps > 0
    ceiling_mb = target_ceiling(target_mb)
    if not v_kbps:
        return False, _t("core_lowbr"), 0.0

    # ТОЧНА обрізка: -ss ПЕРЕД -i = швидкий і (при перекодуванні) кадрово-точний старт;
    # -t ПІСЛЯ -i = вихідна опція -> довжина виходу РІВНО dur (а не рахується від keyframe,
    # як було, коли -t стояв перед -i — саме звідси й бралася різниця в тривалості).
    inss = ["-ss", f"{start or 0:.3f}"] if dur is not None else []
    outdur = ["-t", f"{dur:.3f}"] if dur is not None else []
    # При ОБРІЗЦІ примусово робимо постійний фреймрейт (CFR). Відео з телефона/запису
    # екрана часто VFR — там «час кадру» плаває, і вибраний на таймлайні момент не
    # збігається з реальним -> здавалося, що експорт починається/кінчається пізніше.
    cfr = cfr_args() if dur is not None else []
    # scale = коротша сторона: для вертикального відео масштабуємо ШИРИНУ
    portrait = (info.get("height") or 0) > (info.get("width") or 0) > 0
    vf = (["-vf", (f"scale={scale}:-2" if portrait else f"scale=-2:{scale}")]
          if scale else [])
    # унікальний passlog на кожен вихідний файл -> безпечно для ПАРАЛЕЛЬНОГО кодування частин;
    # лежить у TEMP, а не поруч з відео (там може бути заборонено писати)
    passlog = os.path.join(tempfile.gettempdir(),
                           "_d2p_%d_%s" % (os.getpid(),
                                           os.path.splitext(os.path.basename(out_path))[0]))

    def venc(kbps):
        # yuv420p ОБОВ'ЯЗКОВО: відео з OBS/телефона буває 4:4:4 або 10-біт, і тоді x264
        # кодував у High 4:4:4 / High 10 — Discord і браузери таке НЕ програють (чорний кадр)
        return ["ffmpeg", "-y", *inss, "-i", path, *outdur, *cfr, "-c:v", "libx264",
                "-b:v", f"{kbps}k", "-preset", "medium", *vf, "-pix_fmt", "yuv420p"]

    audio_args = audio_enc_args(audio_kbps) if has_audio else ["-an"]

    # ---- ВІДЕОКАРТА (NVENC / Quick Sync / AMF): один прохід, у 3–4 рази швидше ----
    hw = (("" if force_enc == "x264" else force_enc) if force_enc else active_hw())
    if hw:
        kb = v_kbps
        final_mb = 0.0
        for attempt in range(4):
            rc = _run_pass(["ffmpeg", "-y", *inss, "-i", path, *outdur, *cfr, *vf,
                            *_hw_args(hw, kb), "-pix_fmt", "yuv420p", *audio_args,
                            "-movflags", "+faststart", out_path],
                           duration, 0.0, 100.0, progress_cb, should_cancel)
            if should_cancel and should_cancel():
                return False, cancelled_msg(), 0.0
            if rc != 0 or not os.path.exists(out_path):
                # драйвер/ліміт сесій/непідтримуваний формат -> тихо падаємо на процесор
                dlog(f"HW encode {hw} failed rc={rc} -> fallback to x264")
                if force_enc:          # тест швидкості: чесно кажемо, що цей енкодер не зміг
                    return False, _t("core_pass2"), 0.0
                break
            final_mb = os.path.getsize(out_path) / 1024 / 1024
            if final_mb <= ceiling_mb:
                return True, "OK", final_mb
            if kb <= 20 or final_mb > ceiling_mb * 1.3:
                break      # NVENC упирається у свій мінімум -> не марнуємо час на спроби
            kb = max(20, int(kb * (ceiling_mb / final_mb) * 0.95))
        # відеокарта не влізла в ліміт (на дуже низькому бітрейті NVENC перебирає) ->
        # точний 2-прохідний x264 на процесорі
        dlog(f"HW encode {hw}: {final_mb:.2f} MB > {ceiling_mb:.2f} -> x264 2-pass")
        if progress_cb:
            progress_cb(0.0)

    try:
        # ---- pass 1: аналіз складності (не залежить від бітрейту, робимо один раз) ----
        rc = _run_pass(venc(v_kbps) + ["-pass", "1", "-passlogfile", passlog,
                                       "-an", "-f", "null", os.devnull],
                       duration, 0.0, 45.0, progress_cb, should_cancel)
        if should_cancel and should_cancel():
            return False, cancelled_msg(), 0.0
        if rc != 0:
            return False, _t("core_pass1"), 0.0

        # ---- pass 2 з перевіркою розміру: до 4 спроб, щоразу знижуючи бітрейт ----
        final_mb = 0.0
        for attempt in range(4):
            rc = _run_pass(venc(v_kbps) + ["-pass", "2", "-passlogfile", passlog,
                                           *audio_args, "-movflags", "+faststart", out_path],
                           duration, 45.0, 55.0, progress_cb, should_cancel)
            if should_cancel and should_cancel():
                return False, cancelled_msg(), 0.0
            if rc != 0:
                return False, _t("core_pass2"), 0.0

            final_mb = os.path.getsize(out_path) / 1024 / 1024
            if final_mb <= ceiling_mb or v_kbps <= 20:
                break  # влізло у стелю (або бітрейт вже на мінімумі)
            # перевищили стелю -> знижуємо бітрейт пропорційно (з невеликим запасом) і повторюємо
            v_kbps = max(20, int(v_kbps * (ceiling_mb / final_mb) * 0.97))
        if final_mb > target_mb:      # НІКОЛИ не кажемо «готово», якщо Discord його не прийме
            try:
                os.remove(out_path)
            except OSError:
                pass
            return False, _t("core_lowbr"), final_mb
        return True, "OK", final_mb
    finally:
        for ext in (".log", ".log.mbtree", "-0.log", "-0.log.mbtree",
                    "-0.log.temp", "-0.log.mbtree.temp", ".log.temp", ".log.mbtree.temp"):
            f = passlog + ext
            if os.path.exists(f):
                try:
                    os.remove(f)
                except OSError:
                    pass


def output_name(path: str, target_mb: float) -> str:
    return f"{out_base(path)}_discord_{int(target_mb)}mb.mp4"


def compress_segments(path, out_path, target_mb, scale, audio_kbps, info, segments,
                      progress_cb=None, should_cancel=None):
    """Вирізає й склеює сегменти [(start,end),...] у порядку -> одне відео під target_mb.
    ШВИДКО й ТОЧНО: замість старого trim-фільтра (декодував УСЕ відео двічі) використовуємо
    вхідний seek (-ss перед -i) — ffmpeg декодує лише потрібні шматки, і це кадрово-точно.
    Повертає (ok, message, final_mb)."""
    segs = [(float(s), float(e)) for s, e in segments if e > s]
    if not segs:
        return False, _t("core_noseg"), 0.0
    total = sum(e - s for s, e in segs)
    _a, v_kbps = fit_bitrates(total, target_mb, audio_kbps, info["has_audio"])
    if not v_kbps:
        return False, _t("core_toolong"), 0.0

    # ОДИН фрагмент -> одразу через швидкий вхідний seek (compress зі start/dur) — найшвидше й точно
    if len(segs) == 1:
        s, e = segs[0]
        return compress(path, out_path, target_mb, scale, audio_kbps, info,
                        progress_cb=progress_cb, should_cancel=should_cancel, start=s, dur=e - s)

    # БАГАТО фрагментів -> кожен швидко вирізаємо (вхідний seek), склеюємо, тоді 2-прохідно тиснемо
    has_audio = info["has_audio"] and audio_kbps > 0
    tmpd = tempfile.mkdtemp(prefix="dseg_")
    n = len(segs)
    try:
        files = []
        for i, (s, e) in enumerate(segs):
            if should_cancel and should_cancel():
                return False, cancelled_msg(), 0.0
            segf = os.path.join(tmpd, f"s{i}.mp4")
            cmd = ["ffmpeg", "-y", "-ss", f"{s:.3f}", "-i", path, "-t", f"{e - s:.3f}",
                   *cfr_args(),   # CFR -> сегменти рівні за часом, склейка без дрейфу (VFR-джерела)
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]
            cmd += (["-c:a", "aac", "-b:a", "192k"] if has_audio else ["-an"])
            cmd += ["-video_track_timescale", "90000", segf]
            rc = _run_pass(cmd, e - s, i / n * 35.0, 35.0 / n, progress_cb, should_cancel)
            if rc != 0 or not os.path.exists(segf):
                return False, _t("core_cut"), 0.0
            files.append(segf)

        # склейка (concat demuxer, без перекодування — миттєво)
        listf = os.path.join(tmpd, "list.txt")
        with open(listf, "w", encoding="utf-8") as f:
            for pf in files:
                f.write("file '%s'\n" % pf.replace("\\", "/").replace("'", "'\\''"))
        joined = os.path.join(tmpd, "joined.mp4")
        rc = subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listf,
                             "-c", "copy", "-movflags", "+faststart", joined],
                            capture_output=True, creationflags=NO_WINDOW).returncode
        if rc != 0 or not os.path.exists(joined):
            return False, _t("core_join"), 0.0

        jinfo = {"duration": total, "has_audio": has_audio,
                 "width": info.get("width", 0), "height": info.get("height", 0)}
        return compress(joined, out_path, target_mb, scale, audio_kbps, jinfo,
                        progress_cb=(lambda p: progress_cb(35.0 + p * 0.65)) if progress_cb else None,
                        should_cancel=should_cancel)
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)


def _cut_join(path, segs, tmpd, audio=False):
    """Вирізає сегменти [(s,e)] (CFR, точно) і склеює у один temp-mp4. Повертає шлях або None."""
    an = [] if audio else ["-an"]
    if len(segs) == 1:
        s, e = segs[0]
        out = os.path.join(tmpd, "j.mp4")
        rc = subprocess.run(["ffmpeg", "-y", "-ss", f"{s:.3f}", "-i", path, "-t", f"{e - s:.3f}",
                             *cfr_args(), *an, "-c:v", "libx264", "-preset", "veryfast",
                             "-crf", "18", "-pix_fmt", "yuv420p", out],
                            capture_output=True, creationflags=NO_WINDOW).returncode
        return out if rc == 0 and os.path.exists(out) else None
    files = []
    for i, (s, e) in enumerate(segs):
        f = os.path.join(tmpd, f"c{i}.mp4")
        rc = subprocess.run(["ffmpeg", "-y", "-ss", f"{s:.3f}", "-i", path, "-t", f"{e - s:.3f}",
                             *cfr_args(), *an, "-c:v", "libx264", "-preset", "veryfast",
                             "-crf", "18", "-pix_fmt", "yuv420p", "-video_track_timescale", "90000", f],
                            capture_output=True, creationflags=NO_WINDOW).returncode
        if rc != 0 or not os.path.exists(f):
            return None
        files.append(f)
    listf = os.path.join(tmpd, "l.txt")
    with open(listf, "w", encoding="utf-8") as fh:
        for pf in files:
            fh.write("file '%s'\n" % pf.replace("\\", "/").replace("'", "'\\''"))
    out = os.path.join(tmpd, "j.mp4")
    rc = subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listf,
                         "-c", "copy", out], capture_output=True, creationflags=NO_WINDOW).returncode
    return out if rc == 0 and os.path.exists(out) else None


def gif_out_name(path: str) -> str:
    return out_base(path) + "_discord.gif"


def export_gif(path, out_path, segments, fps=14, width=480, progress_cb=None, should_cancel=None):
    """Робить якісний GIF з обраних сегментів (2-прохідна палітра). (ok, msg, mb)."""
    segs = [(float(s), float(e)) for s, e in segments if e > s]
    if not segs:
        return False, _t("core_noseg"), 0.0
    total = sum(e - s for s, e in segs)
    if total > 30:
        return False, _t("core_gif_long"), 0.0
    tmpd = tempfile.mkdtemp(prefix="dgif_")
    try:
        if progress_cb:
            progress_cb(15)
        trimmed = _cut_join(path, segs, tmpd, audio=False)
        if not trimmed:
            return False, _t("core_gif_fail"), 0.0
        if progress_cb:
            progress_cb(50)
        vf = f"fps={fps},scale={width}:-1:flags=lanczos"
        pal = os.path.join(tmpd, "pal.png")
        subprocess.run(["ffmpeg", "-y", "-i", trimmed, "-vf", vf + ",palettegen=stats_mode=diff", pal],
                       capture_output=True, creationflags=NO_WINDOW)
        if not os.path.exists(pal):
            return False, _t("core_gif_fail"), 0.0
        if progress_cb:
            progress_cb(75)
        rc = subprocess.run(["ffmpeg", "-y", "-i", trimmed, "-i", pal, "-lavfi",
                             vf + "[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3", out_path],
                            capture_output=True, creationflags=NO_WINDOW).returncode
        if rc != 0 or not os.path.exists(out_path):
            return False, _t("core_gif_fail"), 0.0
        if progress_cb:
            progress_cb(100)
        return True, "OK", os.path.getsize(out_path) / 1024 / 1024
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)


def prepare_sound(src, out_wav) -> bool:
    """Конвертує будь-який аудіо/відео у короткий .wav (макс 8с) для звуку «готово».
    PlaySound грає лише .wav, тож приводимо все до нього. True при успіху."""
    try:
        rc = subprocess.run(
            ["ffmpeg", "-y", "-i", src, "-t", "8", "-ac", "2", "-ar", "44100",
             "-vn", out_wav], capture_output=True, creationflags=NO_WINDOW).returncode
        return rc == 0 and os.path.exists(out_wav)
    except Exception:
        return False


def waveform_png(path, out_png, width=596, height=42, color="6a7bf0") -> bool:
    """Малює аудіо-хвилю всього відео у PNG (showwavespic). True при успіху."""
    rc = subprocess.run(
        ["ffmpeg", "-y", "-i", path, "-filter_complex",
         f"aformat=channel_layouts=mono,compand,showwavespic=s={width}x{height}:colors=#{color}",
         "-frames:v", "1", out_png],
        capture_output=True, creationflags=NO_WINDOW).returncode
    return rc == 0 and os.path.exists(out_png)


def audio_envelope(path, hz: int = 100, ar: int = 8000) -> list:
    """Обвідна гучності всього відео як список піків 0..1 (по `hz` значень/сек).
    Декодуємо звук у mono s16le через ffmpeg і рахуємо максимум |семпла| у кожному
    «відрі». Потрібно, щоб намалювати хвилю ВЕКТОРОМ на канвасі — тоді вона тягнеться
    за зумом/обрізкою/переміщенням кліпів (на відміну від готового PNG). [] якщо звуку
    нема / ffmpeg не зміг. Лише stdlib (struct) — щоб точно йшло онлайн у старому exe."""
    try:
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", path,
             "-ac", "1", "-ar", str(ar), "-f", "s16le", "-"],
            capture_output=True, creationflags=NO_WINDOW).stdout
    except Exception:
        return []
    if not out:
        return []
    per = max(1, ar // max(1, hz))           # семплів на одне значення обвідної
    n = len(out) // 2                        # усього семплів (int16)
    env = []
    peak = 1
    for b in range(0, n, per):
        m = min(per, n - b)
        try:
            vals = struct.unpack_from("<%dh" % m, out, b * 2)
        except struct.error:
            break
        a = 0
        for v in vals:
            av = -v if v < 0 else v
            if av > a:
                a = av
        if a > peak:
            peak = a
        env.append(a)
    return [a / peak for a in env]           # нормалізуємо до максимуму (0..1)


def extract_frame(path: str, t: float, out_png: str, width: int = 380) -> bool:
    """Витягує один кадр на позиції t (сек) у PNG для прев'ю. True при успіху."""
    r = subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{max(0, t):.2f}", "-i", path, "-frames:v", "1",
         "-vf", f"scale={width}:-2", "-q:v", "3", out_png],
        capture_output=True, creationflags=NO_WINDOW)
    return r.returncode == 0 and os.path.exists(out_png)


def max_seconds(target_mb: float, audio_kbps: int, video_kbps: int) -> float:
    """Максимальна тривалість (сек), що влізе в target_mb при заданому відео-бітрейті."""
    target_bits = target_ceiling(target_mb) * 8 * 1024 * 1024
    per_sec = (video_kbps + audio_kbps) * 1000
    return target_bits / per_sec if per_sec else 0.0


def plan_parts(duration: float, target_mb: float, audio_kbps: int, has_audio: bool,
               min_video_kbps: int = 700) -> int:
    """Скільки частин потрібно, щоб КОЖНА влізла в ліміт із пристойною якістю
    (відео ~min_video_kbps). Для довгого відео, яке не стиснути цілком."""
    per_sec = (min_video_kbps + (audio_kbps if has_audio else 0)) * 1000
    ceiling_bits = target_ceiling(target_mb) * 8 * 1024 * 1024
    max_sec = ceiling_bits / per_sec if per_sec else duration
    if max_sec <= 0:
        return 1
    return max(1, math.ceil(duration / max_sec))


def plan_parts_balanced(duration: float, target_mb: float, audio_kbps: int, has_audio: bool) -> int:
    """Компроміс «стиснути І поділити»: приблизно посередині між макс-якісним поділом
    (багато частин, високий бітрейт) і мінімально можливою кількістю частин (сильніше стиснути).
    Тобто частин менше, ніж при чистому поділі, зате кожна стискається агресивніше."""
    hi = plan_parts(duration, target_mb, audio_kbps, has_audio, min_video_kbps=700)  # якість
    lo = plan_parts(duration, target_mb, audio_kbps, has_audio, min_video_kbps=150)  # мінімум частин
    return max(lo, round((hi + lo) / 2))


def auto_workers(n: int) -> int:
    """Скільки частин стискати ПАРАЛЕЛЬНО, щоб не перевантажити CPU.
    x264 і так багатопотоковий, тож даємо кожному кодуванню ~2 ядра
    (напр. 6 ядер -> 3 паралельні частини). Мінімум 1, максимум = n."""
    cpu = os.cpu_count() or 2
    return max(1, min(n, max(2, cpu // 2)))


def split_compress(path, target_mb, auto_scale, audio_kbps, info,
                   progress_cb=None, should_cancel=None, part_cb=None, n_parts=None,
                   workers=None):
    """Ділить довге відео на частини і стискає їх ПАРАЛЕЛЬНО під ліміт Discord.
    n_parts — явна кількість частин; None = авто (за якістю). workers — скільки частин
    кодувати одночасно (None = авто за кількістю ядер).
    progress_cb(pct) — загальний прогрес 0..100; part_cb(done, n) — скільки частин готово.
    Повертає (ok: bool, message: str, outputs: list[str])."""
    import threading   # лише threading — БЕЗ concurrent.futures (його могло не бути у старому .exe)

    duration = info["duration"]
    if duration <= 0:
        return False, _t("core_nodur"), []
    n = int(n_parts) if n_parts else plan_parts(duration, target_mb, audio_kbps, info["has_audio"])
    if n <= 1:
        n = 2  # якщо потрапили сюди — відео все одно не влізло цілим, ділимо хоча б навпіл
    part_len = duration / n
    base = out_base(path)
    scale = pick_auto_scale(info, target_mb, audio_kbps) if auto_scale else 0
    if workers is None:
        workers = auto_workers(n)
        if active_hw():
            workers = min(workers, 3)   # відеокарти мають ліміт одночасних сесій кодування
    dlog(f"split_compress start: n={n} workers={workers} cpu={os.cpu_count()} dur={duration:.1f}")

    # план: (індекс, старт, тривалість, вихідний файл)
    tasks = []
    for i in range(n):
        s = i * part_len
        d = (duration - s) if i == n - 1 else part_len
        tasks.append((i, s, d, f"{base}_discord_{int(target_mb)}mb_part{i + 1}.mp4"))

    outputs = [None] * n
    prog = [0.0] * n
    done = [0]
    fail = [None]
    cancelled = [False]
    lock = threading.Lock()
    sem = threading.Semaphore(max(1, workers))   # обмежуємо, скільки частин кодуються одночасно

    def sc():
        return cancelled[0] or bool(should_cancel and should_cancel())

    # ВАЖЛИВО: робочі потоки лише оновлюють числа під замком і НЕ чіпають GUI.
    # Усі progress_cb/part_cb викликає ОДИН потік (цей) — інакше Tkinter з різних
    # потоків підвішує головне вікно (0% і мертва кнопка «Скасувати»).
    def make_prog(i):
        def cb(p):
            with lock:
                prog[i] = p
        return cb

    def work(i, s, d, out_i):
        try:
            with sem:                       # чекаємо вільний «слот» кодування
                if sc():
                    return
                dlog(f"part {i + 1}/{n} START")
                ok, msg, _mb = compress(path, out_i, target_mb, scale, audio_kbps, info,
                                        progress_cb=make_prog(i), should_cancel=sc, start=s, dur=d)
                dlog(f"part {i + 1}/{n} DONE ok={ok} msg={msg}")
                with lock:
                    if ok:
                        outputs[i] = out_i
                    elif msg != cancelled_msg() and fail[0] is None:
                        fail[0] = _t("core_part", n=i + 1, msg=msg)
                        cancelled[0] = True   # одна впала -> зупиняємо решту
        except Exception as e:                # будь-яка несподіванка -> лог + зупинка, а не тихий зависон
            dlog(f"part {i + 1}/{n} EXCEPTION: {e!r}")
            with lock:
                if fail[0] is None:
                    fail[0] = _t("core_part", n=i + 1, msg=e)
                cancelled[0] = True
        finally:
            with lock:
                done[0] += 1

    threads = [threading.Thread(target=work, args=t, daemon=True) for t in tasks]
    for th in threads:
        th.start()

    # цей (єдиний) потік звітує прогрес і чекає завершення
    last_done = -1
    while True:
        with lock:
            pct, dn = sum(prog) / n, done[0]
        if progress_cb:
            progress_cb(pct)
        if part_cb and dn != last_done:
            part_cb(dn, n)
            last_done = dn
        if should_cancel and should_cancel():
            cancelled[0] = True
        if dn >= n:
            break
        time.sleep(0.12)
    for th in threads:
        th.join(timeout=5)

    dlog(f"split_compress end: fail={fail[0]} cancelled={cancelled[0]} done={done[0]}/{n}")
    if fail[0] or sc():
        _cleanup_outputs([t[3] for t in tasks])   # прибираємо всі (навіть недороблені) файли
        return False, fail[0] or cancelled_msg(), []
    return True, "OK", [o for o in outputs if o]


def _cleanup_outputs(paths):
    for p in paths:
        try:
            if os.path.exists(p):
                os.remove(p)
        except OSError:
            pass
