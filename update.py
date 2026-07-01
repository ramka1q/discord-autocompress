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


def _fetch(rel: str) -> bytes:
    """Завантажує файл rel із репозиторію (шлях URL-кодується посегментно)."""
    url = REPO_RAW.rstrip("/") + "/" + "/".join(urllib.parse.quote(p) for p in rel.split("/"))
    req = urllib.request.Request(url, headers={"User-Agent": "DAC-Updater/1.0",
                                               "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def run(quiet: bool = True) -> bool:
    """Тягне manifest і оновлює всі змінені файли. True, якщо щось оновилось."""
    if "USERNAME/REPO" in REPO_RAW:
        if not quiet:
            print("[!] Спершу впиши адресу репозиторію у REPO_RAW (update.py).")
        return False
    try:
        manifest = json.loads(_fetch("manifest.json").decode("utf-8"))
    except Exception as e:
        if not quiet:
            print("[!] Не вдалося перевірити оновлення:", e)
        return False

    files = manifest.get("files", [])
    fresh = {}
    for rel in files:
        try:
            fresh[rel] = _fetch(rel)
        except Exception as e:
            if not quiet:
                print("[!] Помилка завантаження", rel, "—", e)
            return False  # усе-або-нічого: не залишаємо напів-оновлений стан

    changed = 0
    for rel, data in fresh.items():
        dst = os.path.join(HERE, rel.replace("/", os.sep))
        try:
            if os.path.exists(dst) and open(dst, "rb").read() == data:
                continue  # без змін — не чіпаємо
        except OSError:
            pass
        os.makedirs(os.path.dirname(dst) or HERE, exist_ok=True)
        tmp = dst + ".new"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, dst)   # атомарна заміна (безпечно навіть для запущеного .py)
        changed += 1

    if not quiet:
        print(f"[OK] Оновлено файлів: {changed}." if changed else "[OK] Уже остання версія.")
    return True   # успіх (навіть якщо нічого не змінилось); помилки повертають False вище


def auto():
    """Викликається програмою на старті: оновлюється лише за наявності маркера .autoupdate."""
    if os.path.exists(MARKER):
        try:
            run(quiet=True)
        except Exception:
            pass


if __name__ == "__main__":
    # --install ставить маркер (перший запуск у друга); далі просто оновлює
    if "--install" in sys.argv:
        try:
            open(MARKER, "w").close()
        except OSError:
            pass
    ok = run(quiet="--quiet" in sys.argv)
    sys.exit(0 if ok else 1)   # ненульовий код -> інсталятор побачить збій
