#!/usr/bin/env python3
"""
Авто-оновлення Discord Auto-Compress із GitHub
==============================================
Тихо підтягує свіжі файли програми з твого GitHub-репозиторію, щоб у друга завжди
була остання версія — без пересилання архівів. Тільки стандартна бібліотека.

Як це працює:
  • у репозиторії лежить manifest.json зі списком файлів програми;
  • updater тягне manifest, потім кожен файл, і замінює локальні (лише якщо змінилися);
  • на комп'ютері друга поряд лежить порожній файл-маркер «.autoupdate» — лише за його
    наявності оновлення застосовується. У ТЕБЕ (автора) маркера немає, тож твої локальні
    файли ніколи не перезапишуться версією з GitHub.

НАЛАШТУВАННЯ (один раз): впиши сюди адресу свого репозиторію ↓
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request

# ───────────────────────────────────────────────────────────────────────────
#  ЄДИНЕ, ЩО ТРЕБА ВПИСАТИ: «сира» адреса твого репозиторію на GitHub.
#  Формат:  https://raw.githubusercontent.com/ТВІЙ_НІК/НАЗВА_РЕПО/ГІЛКА
#  (гілка зазвичай main). Приклад:
#      https://raw.githubusercontent.com/egor/discord-autocompress/main
# ───────────────────────────────────────────────────────────────────────────
REPO_RAW = os.environ.get(
    "DAC_REPO_RAW",
    "https://raw.githubusercontent.com/ramka1q/discord-autocompress/main"
)

HERE = os.path.dirname(os.path.abspath(__file__))
MARKER = os.path.join(HERE, ".autoupdate")   # є лише в друга -> дозвіл на оновлення
TIMEOUT = 15


def _pinned_base(raw=None) -> str:
    """raw-адреса КОНКРЕТНОГО коміту, а не гілки. Кеш GitHub тримає кожен файл гілки
    окремо до ~5 хв, тож одразу після пушу частина файлів приходила нова, частина стара
    (так і зламалось меню: новий discord_overlay + старий settings_app). Файли коміту
    незмінні -> усе з ОДНІЄЇ версії. Без мережі до API — стара поведінка (гілка)."""
    raw = raw or REPO_RAW
    try:
        m = re.match(r"https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/?$", raw)
        if not m:
            return raw
        owner, repo, branch = m.groups()
        req = urllib.request.Request(
            f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}",
            headers={"User-Agent": "DAC-Updater/2.1", "Accept": "application/vnd.github.sha"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            sha = r.read().decode("ascii", "ignore").strip()
        if re.fullmatch(r"[0-9a-f]{40}", sha):
            return f"https://raw.githubusercontent.com/{owner}/{repo}/{sha}"
    except Exception:
        pass
    return raw


def _fetch(rel: str, base: str = None) -> bytes:
    """Завантажує файл rel із репозиторію (шлях URL-кодується посегментно)."""
    url = (base or REPO_RAW).rstrip("/") + "/" + "/".join(urllib.parse.quote(p) for p in rel.split("/"))
    req = urllib.request.Request(url, headers={"User-Agent": "DAC-Updater/1.0",
                                               "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def _blob_sha(data):
    """git-хеш вмісту (як у GitHub) — щоб без скачування знати, чи файл змінився."""
    import hashlib
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _remote_tree(base):
    """{шлях: (git-хеш, розмір)} коміту з base (raw-адреса з sha) або None."""
    m = re.match(r"https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([0-9a-f]{40})$", base.rstrip("/"))
    if not m:
        return None
    owner, repo, sha = m.groups()
    req = urllib.request.Request(f"https://api.github.com/repos/{owner}/{repo}/git/trees/{sha}?recursive=1",
                                 headers={"User-Agent": "DAC-Updater/2.2"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        tree = json.loads(r.read().decode("utf-8"))
    return {t["path"]: (t["sha"], int(t.get("size", 0))) for t in tree.get("tree", []) if t.get("type") == "blob"}


def _plan(files, base):
    """Які файли треба скачати і скільки це байт: (список, байт або None)."""
    try:
        tree = _remote_tree(base)
        if not tree:
            return list(files), None
        need, size = [], 0
        for rel in files:
            info = tree.get(rel)
            if not info:
                return list(files), None
            dst = os.path.join(HERE, rel.replace("/", os.sep))
            try:
                with open(dst, "rb") as f:
                    if _blob_sha(f.read()) == info[0]:
                        continue
            except OSError:
                pass
            need.append(rel)
            size += info[1]
        return need, size
    except Exception:
        return list(files), None


def _sync(quiet: bool = True, apply: bool = True, progress=None, on_plan=None):
    """Ядро оновлення. Повертає (ok: bool, changed: int).
    ok=False -> збій (мережа/репо); changed = скільки файлів відрізняється/замінено.
    apply=False -> лише РАХУЄ різницю, нічого не пише (для питання «є оновлення?»)."""
    if "USERNAME/REPO" in REPO_RAW:
        if not quiet:
            print("[!] Спершу впиши адресу репозиторію у REPO_RAW (update.py).")
        return False, 0
    base = _pinned_base()
    try:
        manifest = json.loads(_fetch("manifest.json", base).decode("utf-8"))
    except Exception as e:
        if not quiet:
            print("[!] Не вдалося перевірити оновлення:", e)
        return False, 0

    files, total = _plan(manifest.get("files", []), base)
    if on_plan:
        try:
            on_plan(len(files), total)          # скільки файлів і байт буде скачано
        except Exception:
            pass
    fresh = {}
    got = 0
    for i, rel in enumerate(files):
        if progress:
            try:
                pct = got * 100 // total if total else i * 100 // max(1, len(files))
                progress(pct, rel)
            except Exception:
                pass
        try:
            fresh[rel] = _fetch(rel, base)
            got += len(fresh[rel])
        except Exception as e:
            if not quiet:
                print("[!] Помилка завантаження", rel, "—", e)
            return False, 0  # усе-або-нічого: не залишаємо напів-оновлений стан

    changed = 0
    for rel, data in fresh.items():
        dst = os.path.join(HERE, rel.replace("/", os.sep))
        try:
            if os.path.exists(dst):
                with open(dst, "rb") as f:
                    if f.read() == data:
                        continue  # без змін — не чіпаємо
        except OSError:
            pass
        changed += 1
        if not apply:
            continue           # режим лише-перевірки: рахуємо, але не пишемо
        os.makedirs(os.path.dirname(dst) or HERE, exist_ok=True)
        tmp = dst + ".new"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, dst)   # атомарна заміна (безпечно навіть для запущеного .py)

    if not quiet:
        print(f"[OK] Оновлено файлів: {changed}." if changed else "[OK] Уже остання версія.")
    return True, changed


def run(quiet: bool = True) -> bool:
    """Тягне manifest і оновлює всі змінені файли. True при успіху (навіть 0 змін)."""
    ok, _ = _sync(quiet)
    return ok


def check(quiet: bool = True, progress=None, on_plan=None):
    """Примусова перевірка з меню (ігнорує маркер .autoupdate). Повертає (ok, changed).
    progress(pct, name) — для смужки (0..100 по файлах)."""
    return _sync(quiet, progress=progress, on_plan=on_plan)


def available(quiet: bool = True):
    """Лише перевірка (нічого не пише): (ok, changed). Для питання «вийшла нова версія?»."""
    return _sync(quiet, apply=False)


def auto():
    """Викликається програмою на старті: оновлюється лише за наявності маркера .autoupdate."""
    if os.path.exists(MARKER):
        try:
            return _sync(True)[1]          # скільки файлів замінено (0 — уже свіже)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    # --install ставить маркер (перший запуск у друга); далі просто оновлює
    if "--install" in sys.argv:
        try:
            open(MARKER, "w").close()
        except OSError:
            pass
    ok = run(quiet="--quiet" in sys.argv)
    sys.exit(0 if ok else 1)   # ненульовий код -> інсталятор побачить збій
