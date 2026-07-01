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
import subprocess
import tempfile
import time

NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

DEBUG_LOG = os.path.join(tempfile.gettempdir(), "dac_debug.log")


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
    return {"duration": duration, "width": width, "height": height,
            "has_audio": acodec.strip() == "audio"}


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


def pick_auto_scale(info: dict, target_mb: float, audio_kbps: int) -> int:
    """Авто-підбір висоти кадру так, щоб бітрейт лишався пристойним.
    0 = лишити оригінал. Повертає одне з: 0/1080/720/480/360."""
    h = info["height"] or 9999
    candidates = [0, 1080, 720, 480, 360]
    for scale in candidates:
        eff_h = h if scale == 0 else min(scale, h)
        # орієнтовний «добрий» бітрейт ~ 2.2 kbps на рядок висоти (груба евристика)
        good = eff_h * 2.2
        v = calc_video_kbps(info["duration"], target_mb, audio_kbps, info["has_audio"]) or 0
        if v >= good:
            return scale
    return 360  # навіть так замало — беремо найменший


def _run_pass(cmd, duration, base_pct, span, progress_cb, should_cancel):
    cmd = cmd + ["-progress", "pipe:1", "-nostats", "-loglevel", "error"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, creationflags=NO_WINDOW)
    for line in proc.stdout:
        if should_cancel and should_cancel():
            proc.terminate()
            break
        m = TIME_RE.search(line)
        if m and duration > 0 and progress_cb:
            hh, mn, ss = m.groups()
            done = int(hh) * 3600 + int(mn) * 60 + float(ss)
            progress_cb(base_pct + min(1.0, done / duration) * span)
    proc.wait()
    return proc.returncode


def compress(path, out_path, target_mb, scale, audio_kbps, info,
             progress_cb=None, should_cancel=None, start=None, dur=None):
    """Двопрохідне H.264 з ГАРАНТІЄЮ розміру під ліміт Discord.
    Цілиться у стелю (target_ceiling), а після кодування перевіряє реальний розмір і,
    якщо трохи перевищив — знижує бітрейт і перекодовує (лише pass 2, лог pass 1 переюзуємо).
    start/dur (сек) — необовʼязковий сегмент для обрізки.
    Повертає (ok: bool, message: str, final_mb: float)."""
    duration = dur if dur is not None else info["duration"]
    has_audio = info["has_audio"] and audio_kbps > 0
    ceiling_mb = target_ceiling(target_mb)
    v_kbps = calc_video_kbps(duration, target_mb, audio_kbps, info["has_audio"])
    if not v_kbps or v_kbps < 50:
        return False, "Бітрейт занизький для цього розміру — збільш ліміт або зменш роздільність.", 0.0

    # ТОЧНА обрізка: -ss ПЕРЕД -i = швидкий і (при перекодуванні) кадрово-точний старт;
    # -t ПІСЛЯ -i = вихідна опція -> довжина виходу РІВНО dur (а не рахується від keyframe,
    # як було, коли -t стояв перед -i — саме звідси й бралася різниця в тривалості).
    inss = ["-ss", f"{start or 0:.3f}"] if dur is not None else []
    outdur = ["-t", f"{dur:.3f}"] if dur is not None else []
    vf = ["-vf", f"scale=-2:{scale}"] if scale else []
    # унікальний passlog на кожен вихідний файл -> безпечно для ПАРАЛЕЛЬНОГО кодування частин
    passlog = os.path.join(os.path.dirname(out_path) or ".",
                           "_d2p_" + os.path.splitext(os.path.basename(out_path))[0])

    def venc(kbps):
        return ["ffmpeg", "-y", *inss, "-i", path, *outdur, "-c:v", "libx264",
                "-b:v", f"{kbps}k", "-preset", "medium", *vf]

    try:
        # ---- pass 1: аналіз складності (не залежить від бітрейту, робимо один раз) ----
        rc = _run_pass(venc(v_kbps) + ["-pass", "1", "-passlogfile", passlog,
                                       "-an", "-f", "null", os.devnull],
                       duration, 0.0, 45.0, progress_cb, should_cancel)
        if should_cancel and should_cancel():
            return False, "Скасовано.", 0.0
        if rc != 0:
            return False, "Прохід 1 завершився з помилкою.", 0.0

        audio_args = ["-c:a", "aac", "-b:a", f"{audio_kbps}k"] if has_audio else ["-an"]
        # ---- pass 2 з перевіркою розміру: до 4 спроб, щоразу знижуючи бітрейт ----
        final_mb = 0.0
        for attempt in range(4):
            rc = _run_pass(venc(v_kbps) + ["-pass", "2", "-passlogfile", passlog,
                                           *audio_args, "-movflags", "+faststart", out_path],
                           duration, 45.0, 55.0, progress_cb, should_cancel)
            if should_cancel and should_cancel():
                return False, "Скасовано.", 0.0
            if rc != 0:
                return False, "Прохід 2 завершився з помилкою.", 0.0

            final_mb = os.path.getsize(out_path) / 1024 / 1024
            if final_mb <= ceiling_mb or v_kbps <= 50:
                break  # влізло у стелю (або бітрейт вже на мінімумі) — готово
            # перевищили стелю -> знижуємо бітрейт пропорційно (з невеликим запасом) і повторюємо
            v_kbps = max(50, int(v_kbps * (ceiling_mb / final_mb) * 0.97))
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
    base, _ = os.path.splitext(path)
    return f"{base}_discord_{int(target_mb)}mb.mp4"


def compress_segments(path, out_path, target_mb, scale, audio_kbps, info, segments,
                      progress_cb=None, should_cancel=None):
    """Вирізає й склеює сегменти [(start,end),...] у порядку -> одне відео під target_mb.
    ШВИДКО й ТОЧНО: замість старого trim-фільтра (декодував УСЕ відео двічі) використовуємо
    вхідний seek (-ss перед -i) — ffmpeg декодує лише потрібні шматки, і це кадрово-точно.
    Повертає (ok, message, final_mb)."""
    segs = [(float(s), float(e)) for s, e in segments if e > s]
    if not segs:
        return False, "Немає сегментів для збереження.", 0.0
    total = sum(e - s for s, e in segs)
    v_kbps = calc_video_kbps(total, target_mb, audio_kbps, info["has_audio"])
    if not v_kbps or v_kbps < 50:
        return False, "Загалом задовго для цього ліміту — прибери сегмент або підвищ ліміт.", 0.0

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
                return False, "Скасовано.", 0.0
            segf = os.path.join(tmpd, f"s{i}.mp4")
            cmd = ["ffmpeg", "-y", "-ss", f"{s:.3f}", "-i", path, "-t", f"{e - s:.3f}",
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]
            cmd += (["-c:a", "aac", "-b:a", "192k"] if has_audio else ["-an"])
            cmd += ["-video_track_timescale", "90000", segf]
            rc = _run_pass(cmd, e - s, i / n * 35.0, 35.0 / n, progress_cb, should_cancel)
            if rc != 0 or not os.path.exists(segf):
                return False, "Не вдалося вирізати фрагмент.", 0.0
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
            return False, "Не вдалося склеїти фрагменти.", 0.0

        jinfo = {"duration": total, "has_audio": has_audio,
                 "width": info.get("width", 0), "height": info.get("height", 0)}
        return compress(joined, out_path, target_mb, scale, audio_kbps, jinfo,
                        progress_cb=(lambda p: progress_cb(35.0 + p * 0.65)) if progress_cb else None,
                        should_cancel=should_cancel)
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)


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
        return False, "Не вдалося визначити тривалість відео.", []
    n = int(n_parts) if n_parts else plan_parts(duration, target_mb, audio_kbps, info["has_audio"])
    if n <= 1:
        n = 2  # якщо потрапили сюди — відео все одно не влізло цілим, ділимо хоча б навпіл
    part_len = duration / n
    base, _ = os.path.splitext(path)
    scale = pick_auto_scale(info, target_mb, audio_kbps) if auto_scale else 0
    if workers is None:
        workers = auto_workers(n)
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
                    elif msg != "Скасовано." and fail[0] is None:
                        fail[0] = f"Частина {i + 1}: {msg}"
                        cancelled[0] = True   # одна впала -> зупиняємо решту
        except Exception as e:                # будь-яка несподіванка -> лог + зупинка, а не тихий зависон
            dlog(f"part {i + 1}/{n} EXCEPTION: {e!r}")
            with lock:
                if fail[0] is None:
                    fail[0] = f"Частина {i + 1}: {e}"
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
        return False, fail[0] or "Скасовано.", []
    return True, "OK", [o for o in outputs if o]


def _cleanup_outputs(paths):
    for p in paths:
        try:
            if os.path.exists(p):
                os.remove(p)
        except OSError:
            pass
