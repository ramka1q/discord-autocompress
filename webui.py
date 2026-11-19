#!/usr/bin/env python3
"""
webui.py — меню, «Що нового» і «Мої монтажі» як веб-сторінки (дизайн Moon).

Як це працює (без нових бібліотек — лише стандартна бібліотека, тож старий .exe теж уміє):
  • локальний HTTP-сервер на 127.0.0.1 (випадковий порт + секретний токен у кожному запиті);
  • вікно — Microsoft Edge у режимі застосунку (--app=…), він є в кожному Windows 10/11;
  • сторінка (webui/index.html) бере дані з /api/state і викликає дії через /api/do;
    довгі дії (оновлення, тест, встановлення) шлють прогрес через /api/poll.
Edge немає -> повертаємо False, і програма відкриває старе Tk-меню.
"""
import base64
import json
import os
import queue
import socket
import subprocess
import threading
import time
import urllib.parse

import changelog
import dc_core
import i18n

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "webui")
PROFILE = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                       "DiscordAutoCompress", "webview")
# окремі заголовки веб-вікон (у Tk-меню заголовок «Discord Auto-Compress» — не плутати)
TITLES = {"menu": "Discord Auto-Compress · Moon", "gallery": "My edits · Moon",
          "news": "What's new · Moon"}
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".js": "application/javascript; charset=utf-8", ".png": "image/png",
         ".ttf": "font/ttf", ".svg": "image/svg+xml", ".json": "application/json"}

_srv = {"obj": None}
CRLF = bytes((13, 10))
CRLF2 = CRLF + CRLF


def edge_path():
    """Шлях до msedge.exe (реєстр App Paths, потім звичні папки) або None."""
    try:
        import winreg
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe") as k:
                    p = winreg.QueryValue(k, None)
                    if p and os.path.isfile(p):
                        return p
            except OSError:
                pass
    except ImportError:
        pass
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                 os.environ.get("LOCALAPPDATA")):
        if base:
            p = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
            if os.path.isfile(p):
                return p
    return None


def available():
    return bool(edge_path()) and os.path.isfile(os.path.join(WEB, "index.html"))


class Bridge:
    """Усе, що сторінка може попросити в програми. Дії з вікнами Tk виконуються в потоці Tk."""

    def __init__(self, watcher):
        self.w = watcher
        self.token = base64.urlsafe_b64encode(os.urandom(24)).decode("ascii").rstrip("=")
        self.events, self.ev_lock, self.ev_cond = [], threading.Lock(), threading.Condition()
        self.tkq = queue.Queue()
        self.gallery_hwnd = None
        self.overlay = None              # webov.Mirror поточного вікна стиснення
        self.busy = set()
        self._tk_pump()

    # ---------- потік Tk ----------
    def _tk_pump(self):
        try:
            while True:
                fn = self.tkq.get_nowait()
                try:
                    fn()
                except Exception as e:
                    dc_core.dlog("webui tk action fail " + repr(e))
        except queue.Empty:
            pass
        try:
            self.w.root.after(60, self._tk_pump)
        except Exception:
            pass

    def on_tk(self, fn, wait=False, timeout=600):
        if not wait:
            self.tkq.put(fn)
            return None
        box, ev = {}, threading.Event()

        def run():
            try:
                box["v"] = fn()
            finally:
                ev.set()
        self.tkq.put(run)
        ev.wait(timeout)
        return box.get("v")

    # ---------- події для сторінки ----------
    def emit(self, kind, **data):
        with self.ev_cond:
            self.events.append(dict(data, kind=kind, n=len(self.events) + 1))
            del self.events[:-400]
            self.ev_cond.notify_all()

    def poll(self, since, wait=1.0):
        t_end = time.monotonic() + wait
        with self.ev_cond:
            while True:
                out = [e for e in self.events if e["n"] > since]
                left = t_end - time.monotonic()
                if out or left <= 0:
                    last = self.events[-1]["n"] if self.events else 0
                    return {"events": out, "last": last}
                self.ev_cond.wait(left)

    # ---------- дані ----------
    @property
    def cfg(self):
        return self.w.cfg

    def lang(self):
        return self.cfg.get("lang", "en")

    def strings(self):
        L = self.lang()
        return {k: (row.get(L) or row.get("en") or row.get("uk") or k) for k, row in i18n.STR.items()}

    def state(self, page="menu"):
        import deps
        import jokes
        import stats
        L = self.lang()
        d = stats.load()
        hist = []
        for i, e in enumerate(d.get("history", [])):
            hist.append({"i": i, "t": e.get("t", 0), "kind": e.get("kind", "video"), "name": e.get("name", ""),
                         "orig": e.get("orig", 0), "final": e.get("final", 0), "parts": e.get("parts", 1)})
        news = []
        for entry in changelog.CHANGES:
            news.append({"v": entry["v"], "date": entry["date"],
                         "items": [{"icon": a, "title": b, "desc": c, "tab": t}
                                   for a, b, c, t in changelog.items(entry, L)]})
        keys = ("target_mb", "auto_scale", "block_paste", "auto_paste", "audio_kbps", "compress_video",
                "compress_images", "compress_audio", "keep_local", "offer_shrink", "sound_done",
                "notify_done", "encoder", "theme", "lang", "bench", "bench_at", "encoder_best")
        c = {k: self.cfg.get(k) for k in keys}
        sf = self.cfg.get("sound_file", "")
        return {
            "page": page, "version": changelog.VERSION, "released": changelog.RELEASED,
            "lang": L, "langs": [[k, i18n.LANG_NAMES[k]] for k in i18n.LANGS],
            "S": self.strings(), "cfg": c, "sound_custom": bool(sf and os.path.isfile(sf)),
            "stats": {"files": d.get("files", 0), "saved_mb": d.get("saved_mb", 0.0),
                      "avg": stats.avg_percent(d) if d.get("files") else None,
                      "since": d.get("since"), "by_kind": d.get("by_kind", {}), "history": hist},
            "news": news, "news_since": getattr(self.w, "_news_from", None),
            "facts": jokes.facts_for(L), "deps": deps.check(), "cpu": os.cpu_count() or 1,
            "gpu": self._gpu_state(), "lib": self._lib_items() if page == "gallery" else [],
            "hotkey": "Ctrl+Alt+E", "repo": changelog.REPO_URL if hasattr(changelog, "REPO_URL")
            else "https://github.com/ramka1q/discord-autocompress",
            "release_url": changelog.release_url(),
            "themes": self._themes(),
            "donate": self._has_donate(),
        }

    @staticmethod
    def _has_donate():
        try:
            import monetize
            return bool(monetize.has_donate())
        except Exception:
            return False

    @staticmethod
    def _themes():
        import themes
        return [[k, themes.palette(k)["name"], themes.palette(k)["bg"], themes.palette(k)["accent"],
                 themes.palette(k).get("accent2", themes.palette(k)["accent"])] for k in themes.order()]

    def _gpu_state(self):
        hw = dc_core._HW if getattr(dc_core, "_HW", None) is not None else None
        return {"known": hw is not None, "hw": hw or "",
                "hw_name": dc_core.HW_NAMES.get(hw, "") if hw else "",
                "names": dict(getattr(dc_core, "HW_NAMES", {}))}

    def _lib_items(self):
        import library
        out = []
        for p in library.items():
            try:
                st = os.stat(p)
            except OSError:
                continue
            nm = os.path.basename(p)
            nm = nm[20:] if len(nm) > 20 and nm[4] == "-" else nm
            out.append({"path": p, "name": nm, "mb": round(st.st_size / 1048576, 1), "t": st.st_mtime,
                        "audio": p.lower().endswith((".mp3", ".m4a"))})
        return out

    # ---------- налаштування ----------
    def set(self, changes):
        allowed = {"target_mb": int, "auto_scale": bool, "block_paste": bool, "auto_paste": bool,
                   "audio_kbps": int, "compress_video": bool, "compress_images": bool,
                   "compress_audio": bool, "keep_local": str, "offer_shrink": bool, "sound_done": bool,
                   "notify_done": bool, "encoder": str, "theme": str, "lang": str}
        cfg = dict(self.cfg)
        reload_page = False
        for k, v in changes.items():
            if k not in allowed:
                continue
            try:
                v = allowed[k](v)
            except (TypeError, ValueError):
                continue
            if k == "audio_kbps":
                v = max(0, min(320, v))
            if k == "lang" and v not in i18n.LANGS:
                continue
            if k in ("theme", "lang") and cfg.get(k) != v:
                reload_page = True
            cfg[k] = v

        def apply():
            self.w._on_settings_save(cfg)
        self.on_tk(apply, wait=True, timeout=10)
        import themes
        if "theme" in changes and not themes.palette(cfg.get("theme")).get("mono"):
            # інша тема — це звичайне (Tk) меню: відкриваємо його, а веб-вікно закриється
            self.on_tk(lambda: self.w.open_settings(tab="appearance"))

            def shut():                      # про всяк випадок закриваємо веб-вікно й самі
                h = _find_window(TITLES["menu"])
                if h:
                    import ctypes
                    ctypes.windll.user32.PostMessageW(ctypes.c_void_p(h), 0x0010, 0, 0)   # WM_CLOSE
            threading.Timer(1.2, shut).start()
            return {"ok": True, "close": True}
        return {"ok": True, "reload": reload_page}

    # ---------- дії ----------
    def do(self, action, a):
        fn = getattr(self, "act_" + action, None)
        if not fn:
            return {"ok": False, "err": "unknown action"}
        return fn(a or {}) or {"ok": True}

    # ---- вікно стиснення (webov) ----
    def _ov(self, fn):
        m = self.overlay
        if m is not None:
            self.on_tk(lambda: fn(m))

    def act_ov_click(self, a):
        self._ov(lambda m: m.click(str(a.get("id", ""))))

    def act_ov_chip(self, a):
        self._ov(lambda m: m.chip(str(a.get("tag", ""))))

    def act_ov_esc(self, a):
        self._ov(lambda m: m.esc())

    def act_ov_entry(self, a):
        self._ov(lambda m: m.entry(a.get("v", ""), bool(a.get("submit"))))

    def act_ov_drag(self, a):
        self._ov(lambda m: m.drag(a.get("dx", 0), a.get("dy", 0)))

    def act_ov_scene(self, a):
        m = self.overlay
        if m is None:
            return {"ok": True, "scene": None}
        import webov
        return {"ok": True, "scene": self.on_tk(lambda: webov.scene(m.ov), wait=True, timeout=5)}

    def act_open_editor(self, a):
        import library
        self.on_tk(lambda: library.open_empty_editor(self.w))

    def act_open_gallery(self, a):
        self.on_tk(lambda: self.w.open_gallery())

    def act_open_menu(self, a):
        self.on_tk(lambda: self.w.open_settings(tab=a.get("tab")))

    def _lib_path(self, p):
        import library
        p = os.path.abspath(str(p or ""))
        if os.path.dirname(p) != os.path.abspath(library.lib_dir()) or not os.path.isfile(p):
            return None
        return p

    def act_lib_paste(self, a):
        p = self._lib_path(a.get("path"))
        if not p:
            return {"ok": False}
        import discord_overlay as h
        h.set_clipboard_files([p])
        try:
            self.w.mark_self_clipboard()
        except Exception:
            pass
        hw = self.gallery_hwnd
        if hw:
            def go():
                try:
                    h.user32.SetForegroundWindow(hw)
                    self.w.root.after(250, h.send_ctrl_v)
                except Exception:
                    pass
            self.on_tk(go)
            return {"ok": True, "pasted": True}
        try:
            import library
            self.w.notify(library.T("lib_title"), library.T("lib_copied"))
        except Exception:
            pass
        return {"ok": True, "pasted": False}

    def act_lib_play(self, a):
        p = self._lib_path(a.get("path"))
        if p:
            os.startfile(p)

    def act_lib_edit(self, a):
        p = self._lib_path(a.get("path"))
        if p:
            import library
            self.on_tk(lambda: library.open_editor(self.w, p, self.gallery_hwnd))

    def act_lib_folder(self, a):
        import library
        os.startfile(library.lib_dir())

    def _hist(self, i):
        import stats
        h = stats.load().get("history", [])
        try:
            e = h[int(i)]
        except (IndexError, ValueError, TypeError):
            return None, []
        return e, [p for p in e.get("paths", []) if p and os.path.isfile(p)]

    def act_hist_copy(self, a):
        e, paths = self._hist(a.get("i"))
        if not paths:
            return {"ok": False}
        import discord_overlay as h
        h.set_clipboard_files(paths)
        return {"ok": True}

    def act_hist_open(self, a):
        e, paths = self._hist(a.get("i"))
        if not paths:
            return {"ok": False}
        subprocess.Popen(["explorer", "/select,", os.path.normpath(paths[0])])

    def act_hist_clear(self, a):
        import stats
        stats.clear_history()

    def act_pick_sound(self, a):
        def pick():
            from tkinter import filedialog
            return filedialog.askopenfilename(parent=self.w.root, title=i18n.tr(self.lang(), "sound_pick"),
                                              filetypes=[("Audio", "*.wav *.mp3 *.m4a *.ogg *.aac *.flac *.wma"),
                                                         ("*", "*.*")])
        p = self.on_tk(pick, wait=True)
        if not p:
            return {"ok": False}
        import shutil
        wav = os.path.join(os.path.expanduser("~"), ".discord_done_sound.wav")
        try:
            if p.lower().endswith(".wav"):
                shutil.copyfile(p, wav)
                ok = os.path.isfile(wav)
            else:
                ok = dc_core.prepare_sound(p, wav)
        except Exception:
            ok = False
        if ok:
            cfg = dict(self.cfg, sound_file=wav)
            self.on_tk(lambda: self.w._on_settings_save(cfg), wait=True, timeout=10)
            self._play(wav)
        return {"ok": bool(ok)}

    @staticmethod
    def _play(wav):
        try:
            import ctypes
            ctypes.windll.winmm.PlaySoundW(ctypes.c_wchar_p(wav), None, 0x00020003)
        except Exception:
            pass

    def act_reset_sound(self, a):
        cfg = dict(self.cfg, sound_file="")
        self.on_tk(lambda: self.w._on_settings_save(cfg), wait=True, timeout=10)
        try:
            import ctypes
            ctypes.windll.winmm.PlaySoundW(ctypes.c_wchar_p("SystemAsterisk"), None, 0x00010003)
        except Exception:
            pass

    def act_open_url(self, a):
        import monetize
        url = a.get("url", "")
        ok = (url.startswith("https://github.com/ramka1q/discord-autocompress")
              or url == getattr(monetize, "DONATE_URL", None))
        if ok:
            monetize.open_url(url)

    def act_donate(self, a):
        import monetize
        if monetize.has_donate():
            monetize.open_url(monetize.DONATE_URL)

    def act_restart(self, a):
        self.on_tk(self.w.restart_app)

    def act_whatsnew_popup(self, a):
        open_page(self.w, "news")

    # --- довгі дії з прогресом ---
    def _bg(self, name, fn):
        if name in self.busy:
            return {"ok": False, "busy": True}
        self.busy.add(name)

        def run():
            try:
                fn()
            except Exception as e:
                dc_core.dlog(f"webui {name} fail {e!r}")
                self.emit(name, state="error", err=str(e)[:120])
            finally:
                self.busy.discard(name)
        threading.Thread(target=run, daemon=True).start()
        return {"ok": True}

    def act_update(self, a):
        def work():
            import update
            try:
                import mpvplayer
                need_mpv = not mpvplayer.dll_path()
            except Exception:
                mpvplayer, need_mpv = None, False
            plan = {"n": 0, "size": None}

            def got_plan(n, total):
                plan.update(n=n, size=total)
                self.emit("update", state="plan", n=n, size=total, mpv=need_mpv,
                          mpv_size=getattr(mpvplayer, "Z_SIZE", 0) if need_mpv else 0)
            share = 10 if need_mpv else 100
            ok, changed = update.check(on_plan=got_plan,
                                       progress=lambda p, rel: self.emit("update", state="files",
                                                                         pct=p * share // 100))
            if ok and need_mpv:
                done = threading.Event()

                def st(state, pct, src):
                    if state == "running":
                        self.emit("update", state="player", pct=share + pct * (100 - share) // 100)
                    else:
                        self.emit("update", state=state, pct=pct, src=src)
                mpvplayer.ensure_downloaded(on_status=st, on_done=lambda _ok: done.set())
                done.wait()
                changed = max(1, changed)
            if ok and changed == 0:
                try:   # фонове самолікування могло вже покласти нові файли, а працює старий код
                    import re
                    with open(os.path.join(HERE, "changelog.py"), encoding="utf-8") as f:
                        m = re.search(r'\{"v":\s*"([^"]+)"', f.read())
                    if m and m.group(1) != changelog.VERSION:
                        changed = 1
                except Exception:
                    pass
            self.emit("update", state="done", ok=ok, changed=changed)
            if ok and changed:
                time.sleep(1.0)
                self.on_tk(self.w.restart_app)
        return self._bg("update", work)

    def act_perf(self, a):
        def work():
            import deps
            if not deps.all_ok(refresh=True):
                done = threading.Event()
                res = {}
                deps.install_progress(progress_cb=lambda v: self.emit("perf", state="dl", pct=v),
                                      done_cb=lambda ok: (res.update(ok=ok), done.set()))
                done.wait()
                if not res.get("ok"):
                    return self.emit("perf", state="dl_fail")
            import optimize_test
            r = optimize_test.run(lambda v: self.emit("perf", state="run", pct=v), lang=self.lang())
            self.emit("perf", state="done", lines=r.get("lines", []), verdict=r.get("verdict", ""),
                      ok=r.get("ok", False))
        return self._bg("perf", work)

    def act_deps_install(self, a):
        def work():
            import deps
            done = threading.Event()
            res = {}
            deps.install(log_cb=lambda s: self.emit("deps", state="log", line=s),
                         done_cb=lambda ok: (res.update(ok=ok), done.set()))
            done.wait()
            self.emit("deps", state="done", ok=res.get("ok", False), deps=deps.check(refresh=True))
        return self._bg("deps", work)

    def act_deps_check(self, a):
        import deps
        return {"ok": True, "deps": deps.check(refresh=True)}

    def act_report(self, a):
        def work():
            import report
            path = report.build(dict(self.cfg), changelog.VERSION, changelog.RELEASED)
            import discord_overlay as h
            try:
                h.set_clipboard_files([path])
            except Exception:
                pass
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            self.emit("report", state="done", ok=True)
        return self._bg("report", work)

    def act_gpu(self, a):
        def work():
            dc_core.hw_encoder()
            self.emit("gpu", state="done", gpu=self._gpu_state())
        return self._bg("gpu", work)

    def act_bench(self, a):
        def work():
            res = dc_core.benchmark(lambda p: self.emit("bench", state="run", pct=p))
            ok = [r for r in res if r.get("sec")]
            if ok:
                cfg = dict(self.cfg)
                cfg["encoder_best"] = ok[0]["enc"]
                cfg["bench"] = [{"enc": r["enc"], "sec": round(r["sec"], 2) if r.get("sec") else None}
                                for r in res]
                cfg["bench_at"] = time.strftime("%d.%m.%Y %H:%M")
                self.on_tk(lambda: self.w._on_settings_save(cfg), wait=True, timeout=10)
            self.emit("bench", state="done", bench=self.cfg.get("bench"), at=self.cfg.get("bench_at"),
                      best=self.cfg.get("encoder_best"))
        return self._bg("bench", work)

    def thumb(self, path):
        p = self._lib_path(path)
        if not p:
            return None
        import library
        t = library._thumb(p, 384, 216)
        return t or None


class _Req:
    """Мінімальний HTTP/1.1 на сирому socket (у старому .exe немає http.server)."""
    REASON = {200: "OK", 400: "Bad Request", 403: "Forbidden", 404: "Not Found", 500: "Server Error"}

    def __init__(self, conn, bridge):
        self.c, self.b = conn, bridge

    def read(self):
        self.c.settimeout(30)
        buf = b""
        while CRLF2 not in buf:
            ch = self.c.recv(65536)
            if not ch:
                return False
            buf += ch
            if len(buf) > 1 << 20:
                return False
        head, _, rest = buf.partition(CRLF2)
        lines = head.decode("latin-1").split(CRLF.decode())
        try:
            self.method, self.path, _v = lines[0].split(" ", 2)
        except ValueError:
            return False
        self.headers = {}
        for ln in lines[1:]:
            k, _, v = ln.partition(":")
            self.headers[k.strip().lower()] = v.strip()
        n = int(self.headers.get("content-length") or 0)
        while len(rest) < n:
            ch = self.c.recv(65536)
            if not ch:
                break
            rest += ch
        self.body = rest[:n]
        return True

    def send(self, code, body, ctype="application/json; charset=utf-8", cache=False):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        lines = [f"HTTP/1.1 {code} {self.REASON.get(code, 'OK')}", f"Content-Type: {ctype}",
                 f"Content-Length: {len(body)}",
                 "Cache-Control: " + ("max-age=86400" if cache else "no-store"), "Connection: close"]
        hdr = CRLF.join(x.encode("latin-1") for x in lines) + CRLF2
        try:
            self.c.sendall(hdr + body)
        except OSError:
            pass

    def file(self, full, cache=False):
        try:
            with open(full, "rb") as f:
                body = f.read()
        except OSError:
            return self.send(404, {"err": "not found"})
        return self.send(200, body, TYPES.get(os.path.splitext(full)[1].lower(), "application/octet-stream"), cache)

    def handle(self):
        b = self.b
        if not self.read():
            return
        host = self.headers.get("host", "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):          # захист від DNS-rebinding
            return self.send(403, {"err": "forbidden"})
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        authed = self.headers.get("x-token") == b.token or q.get("t", [""])[0] == b.token
        path = u.path
        if self.method == "GET":
            if path in ("/icon.png", "/favicon.ico"):      # значок програми (вкладка/панель задач)
                try:
                    import appicon
                    return self.send(200, appicon._png_bytes(256), "image/png", cache=True)
                except Exception:
                    return self.send(404, {"err": "icon"})
            if path in ("/", "/index.html"):
                if q.get("t", [""])[0] != b.token:
                    return self.send(403, "forbidden", "text/plain")
                return self.file(os.path.join(WEB, "index.html"))
            for pre, base in (("/web/", WEB), ("/fonts/", os.path.join(HERE, "fonts")),
                              ("/assets/", os.path.join(HERE, "assets"))):
                if path.startswith(pre):
                    full = os.path.abspath(os.path.join(base, urllib.parse.unquote(path[len(pre):])))
                    if not full.startswith(os.path.abspath(base) + os.sep):
                        return self.send(403, {"err": "forbidden"})
                    return self.file(full, cache=pre != "/web/")
            if not authed:
                return self.send(403, {"err": "token"})
            if path == "/api/state":
                return self.send(200, b.state(q.get("page", ["menu"])[0]))
            if path == "/api/poll":
                try:
                    since = int(q.get("since", ["0"])[0])
                    w = max(0.0, min(15.0, float(q.get("w", ["15"])[0])))
                except ValueError:
                    since, w = 0, 15.0
                return self.send(200, b.poll(since, w))
            if path == "/api/thumb":
                t = b.thumb(q.get("p", [""])[0])
                return self.file(t) if t else self.send(404, {"err": "none"})
            return self.send(404, {"err": "not found"})
        if self.method == "POST":
            if not authed:
                return self.send(403, {"err": "token"})
            try:
                data = json.loads(self.body.decode("utf-8") or "{}")
            except ValueError:
                return self.send(400, {"err": "bad json"})
            try:
                if path == "/api/set":
                    return self.send(200, b.set(data))
                if path == "/api/do":
                    return self.send(200, b.do(str(data.get("action", "")), data.get("args")))
            except Exception as e:
                dc_core.dlog("webui POST fail " + repr(e))
                return self.send(500, {"ok": False, "err": str(e)[:200]})
            return self.send(404, {"err": "not found"})
        return self.send(400, {"err": "method"})


def _serve(sock, bridge):
    while True:
        try:
            conn, _a = sock.accept()
        except OSError:
            return

        def one(c=conn):
            try:
                _Req(c, bridge).handle()
            except Exception as e:
                dc_core.dlog("webui req fail " + repr(e))
            finally:
                try:
                    c.close()
                except OSError:
                    pass
        threading.Thread(target=one, daemon=True).start()


def start(watcher):
    """Запускає сервер один раз (фоновий потік). Повертає (bridge, port)."""
    s = _srv.get("obj")
    if s:
        return s
    bridge = Bridge(watcher)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(32)
    port = sock.getsockname()[1]
    threading.Thread(target=_serve, args=(sock, bridge), daemon=True).start()
    _srv["obj"] = (bridge, port)
    dc_core.dlog(f"webui server on {port}")
    return _srv["obj"]


def _find_window(title):
    import ctypes
    u32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _):
        n = u32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            u32.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value == title and u32.IsWindowVisible(hwnd):
                found.append(hwnd)
        return True
    u32.EnumWindows(cb, 0)
    return found[0] if found else None


def close_all():
    """Закриває всі веб-вікна програми (меню, галерея, «Що нового», вікно стиснення)."""
    import ctypes
    u32 = ctypes.windll.user32
    titles = set(TITLES.values()) | {"DAC Overlay"}
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _):
        n = u32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            u32.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value in titles:
                found.append(hwnd)
        return True
    u32.EnumWindows(cb, 0)
    for h in found:
        u32.PostMessageW(ctypes.c_void_p(h), 0x0010, 0, 0)       # WM_CLOSE
    try:
        import webov
        p = webov._st.get("proc")
        if p and p.poll() is None:
            p.terminate()
    except Exception:
        pass


def _focus(hwnd):
    import ctypes
    u32 = ctypes.windll.user32
    u32.ShowWindow(ctypes.c_void_p(hwnd), 9)      # SW_RESTORE
    u32.SetForegroundWindow(ctypes.c_void_p(hwnd))


def open_page(watcher, page="menu", tab=None, gallery_hwnd=None):
    """Відкриває сторінку в окремому вікні Edge (або піднімає вже відкрите).
    False — Edge немає (тоді викликач показує Tk-вікно)."""
    exe = edge_path()
    if not exe or not os.path.isfile(os.path.join(WEB, "index.html")):
        dc_core.dlog(f"webui open {page}: no Edge ({exe}) or no index.html")
        return False
    try:
        bridge, port = start(watcher)
    except Exception as e:
        dc_core.dlog("webui start fail " + repr(e))
        return False
    if page == "gallery":
        bridge.gallery_hwnd = gallery_hwnd
    existing = _find_window(TITLES.get(page, ""))
    if existing:
        dc_core.dlog(f"webui open {page}: focus existing {existing}")
        if tab:
            bridge.emit("nav", page=page, tab=tab)
        if page == "gallery":
            bridge.emit("reload", page="gallery")
        _focus(existing)
        return True
    size = {"menu": (1180, 780), "gallery": (980, 700), "news": (620, 860)}.get(page, (1100, 760))
    try:
        import ctypes
        sw, sh = ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)
    except Exception:
        sw, sh = 1920, 1080
    w, h = min(size[0], sw - 40), min(size[1], sh - 80)
    x, y = max(0, (sw - w) // 2), max(0, (sh - h) // 2 - 20)
    frag = f"#{page}" + (f"/{tab}" if tab else "")
    url = f"http://127.0.0.1:{port}/?t={bridge.token}{frag}"
    os.makedirs(PROFILE, exist_ok=True)
    args = [exe, f"--app={url}", f"--user-data-dir={PROFILE}", f"--window-size={w},{h}",
            f"--window-position={x},{y}", "--no-first-run", "--no-default-browser-check",
            "--disable-features=Translate,msEdgeSidebarV2,msUndersideButton,msHubApps",
            "--disable-sync", "--force-dark-mode", "--enable-features=WebContentsForceDark:false"]
    try:
        subprocess.Popen(args, creationflags=0x08000000)
    except OSError as e:
        dc_core.dlog("webui edge launch fail " + repr(e))
        return False
    dc_core.dlog(f"webui open {page} {tab or ''}")
    return True
