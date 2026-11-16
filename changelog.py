#!/usr/bin/env python3
"""
changelog.py — версія програми та список змін по версіях.
З нього беруться: номер і дата версії в меню, вікно «Що нового» (показується
один раз після оновлення) і вкладка «Що нового». Нова версія = новий запис ЗВЕРХУ
списку CHANGES. tab — вкладка меню, яку відкриває кнопка «Показати» (None — без кнопки).
Тільки стандартна бібліотека.
"""

REPO_URL = "https://github.com/ramka1q/discord-autocompress"

CHANGES = [
    {"v": "2.3", "date": "2026-11-16 16:32", "items": [
        {"icon": "T", "tab": None,
         "uk": ("Текст на відео", "Кнопка «T»: титри з обведенням, фоном чи тінню, 7 кольорів, плавна поява. Тягни текст прямо на відео."),
         "ru": ("Текст на видео", "Кнопка «T»: титры с обводкой, фоном или тенью, 7 цветов, плавное появление. Тяни текст прямо на видео."),
         "en": ("Text on video", "The “T” button: titles with outline, box or shadow, 7 colors, fade in/out. Drag the text right on the video.")},
        {"icon": "🎨", "tab": None,
         "uk": ("Панель властивостей", "Справа, як у CapCut: гучність, плавна поява/зникнення, фільтри (Ч/Б, Тепло, Вінтаж…), яскравість, контраст, поворот, дзеркало."),
         "ru": ("Панель свойств", "Справа, как в CapCut: громкость, плавное появление/исчезновение, фильтры (Ч/Б, Тепло, Винтаж…), яркость, контраст, поворот, зеркало."),
         "en": ("Properties panel", "On the right, like CapCut: volume, fade in/out, filters (B&W, Warm, Vintage…), brightness, contrast, rotate, mirror.")},
        {"icon": "▶", "tab": None,
         "uk": ("Відтворення = результат", "Під час програвання видно накладки, текст, фільтри й швидкість, чути додані звуки."),
         "ru": ("Воспроизведение = результат", "Во время воспроизведения видны наложения, текст, фильтры и скорость, слышны добавленные звуки."),
         "en": ("Playback = result", "Playback now shows overlays, text, filters and speed, and plays the added sounds.")},
        {"icon": "🎭", "tab": None,
         "uk": ("Прозорість накладок", "Накладки можна зробити напівпрозорими і вибирати кліком прямо на відео."),
         "ru": ("Прозрачность наложений", "Наложения можно сделать полупрозрачными и выбирать кликом прямо на видео."),
         "en": ("Overlay opacity", "Overlays can be semi-transparent and are picked by clicking them on the video.")},
    ]},
    {"v": "2.2", "date": "2026-11-16 16:13", "items": [
        {"icon": "🎬", "tab": None,
         "uk": ("Новий редактор відео", "Як у CapCut: великий плеєр, лінійка часу, панель інструментів, підказки й гарячі клавіші."),
         "ru": ("Новый редактор видео", "Как в CapCut: большой плеер, линейка времени, панель инструментов, подсказки и горячие клавиши."),
         "en": ("New video editor", "CapCut-style: big player, time ruler, toolbar, tooltips and hotkeys.")},
        {"icon": "🔍", "tab": None,
         "uk": ("Зум туди, де мишка", "Ctrl+колесо наближає доріжку саме в точці під курсором. Є повзунок зуму і «вмістити все»."),
         "ru": ("Зум туда, где мышка", "Ctrl+колесо приближает дорожку именно в точке под курсором. Есть ползунок зума и «вместить всё»."),
         "en": ("Zoom where the mouse is", "Ctrl+wheel zooms right at the cursor. Plus a zoom slider and “fit all”.")},
        {"icon": "⏯", "tab": None,
         "uk": ("Плейхед тягнеться мишкою", "Тягни білий повзунок або клікай по лінійці — кадр оновлюється наживо."),
         "ru": ("Плейхед тянется мышкой", "Тяни белый ползунок или кликай по линейке — кадр обновляется вживую."),
         "en": ("Drag the playhead", "Drag the white playhead or click the ruler — the frame updates live.")},
        {"icon": "↔", "tab": None,
         "uk": ("Кліпи перетягуються", "Тягни кліп, щоб переставити, або вгору — і він стане накладкою. Блоки липнуть до країв (магніт)."),
         "ru": ("Клипы перетаскиваются", "Тяни клип, чтобы переставить, или вверх — и он станет наложением. Блоки липнут к краям (магнит)."),
         "en": ("Drag clips around", "Drag a clip to reorder it, or up to make it an overlay. Blocks snap to edges.")},
    ]},
    {"v": "2.1", "date": "2026-11-01 19:46", "items": [
        {"icon": "⚡", "tab": "gpu",
         "uk": ("Стиснення на відеокарті", "NVIDIA / Intel / AMD — у 2–4 рази швидше. Тест сам знайде найшвидший спосіб."),
         "ru": ("Сжатие на видеокарте", "NVIDIA / Intel / AMD — в 2–4 раза быстрее. Тест сам найдёт самый быстрый способ."),
         "en": ("Compression on the graphics card", "NVIDIA / Intel / AMD — 2–4× faster. A test finds the fastest way for you.")},
        {"icon": "🔔", "tab": "media",
         "uk": ("Сповіщення «Готово»", "Якщо пішов з Discord, поки йде стиснення, Windows покаже, що все готово."),
         "ru": ("Уведомление «Готово»", "Если ушёл из Discord во время сжатия, Windows покажет, что всё готово."),
         "en": ("“Done” notification", "Left Discord while compressing? Windows tells you when it's ready.")},
        {"icon": "🐞", "tab": "about",
         "uk": ("Звіт про помилку", "Одна кнопка збирає все потрібне у файл — просто встав його в Discord."),
         "ru": ("Отчёт об ошибке", "Одна кнопка собирает всё нужное в файл — просто вставь его в Discord."),
         "en": ("Bug report", "One button gathers everything into a file — just paste it into Discord.")},
        {"icon": "✨", "tab": "whatsnew",
         "uk": ("Що нового", "Після кожного оновлення програма сама показує, що змінилось."),
         "ru": ("Что нового", "После каждого обновления программа сама показывает, что изменилось."),
         "en": ("What's new", "After every update the app shows what changed.")},
        {"icon": "🛠", "tab": None,
         "uk": ("Виправлено зависання", "Вікно більше не зависає, коли курсор над кнопкою."),
         "ru": ("Исправлено зависание", "Окно больше не зависает, когда курсор над кнопкой."),
         "en": ("Freeze fixed", "The window no longer freezes when the cursor is over a button.")},
    ]},
    {"v": "2.0", "date": "2026-11-01 19:25", "items": [
        {"icon": "🎨", "tab": "general",
         "uk": ("Новий дизайн", "Градієнти, перемикачі, кільце прогресу з таймером, плавні анімації."),
         "ru": ("Новый дизайн", "Градиенты, переключатели, кольцо прогресса с таймером, плавные анимации."),
         "en": ("New design", "Gradients, toggles, a progress ring with time left, smooth animations.")},
        {"icon": "🌙", "tab": "appearance",
         "uk": ("Тема Midnight", "Четверта тема — глибока ніч з неоновим градієнтом."),
         "ru": ("Тема Midnight", "Четвёртая тема — глубокая ночь с неоновым градиентом."),
         "en": ("Midnight theme", "A fourth theme — deep night with a neon gradient.")},
        {"icon": "🎬", "tab": None,
         "uk": ("Відео з OBS і телефонів", "Тепер завжди програються в Discord (раніше бував чорний екран)."),
         "ru": ("Видео из OBS и телефонов", "Теперь всегда проигрываются в Discord (раньше бывал чёрный экран)."),
         "en": ("Videos from OBS and phones", "Now always play in Discord (they used to show a black screen).")},
        {"icon": "📱", "tab": None,
         "uk": ("Вертикальні відео", "Стискаються з такою ж якістю, як горизонтальні."),
         "ru": ("Вертикальные видео", "Сжимаются с таким же качеством, как горизонтальные."),
         "en": ("Vertical videos", "Keep the same quality as landscape ones.")},
        {"icon": "🌍", "tab": "appearance",
         "uk": ("Усе перекладено", "Редактор і всі повідомлення — українською, російською й англійською."),
         "ru": ("Всё переведено", "Редактор и все сообщения — на украинском, русском и английском."),
         "en": ("Fully translated", "The editor and every message in Ukrainian, Russian and English.")},
    ]},
]

VERSION = CHANGES[0]["v"]
RELEASED = CHANGES[0]["date"]


def release_url(v=None):
    return f"{REPO_URL}/releases/tag/v{v or VERSION}"


def items(entry, lang):
    """[(icon, title, desc, tab), ...] мовою lang."""
    out = []
    for it in entry["items"]:
        title, desc = it.get(lang) or it["en"]
        out.append((it["icon"], title, desc, it.get("tab")))
    return out


def fmt_date(date, lang_tr=None):
    """'2026-11-01 20:30' -> ('01.11.2026', '20:30')."""
    try:
        d, t = date.split()
        y, m, dd = d.split("-")
        return f"{dd}.{m}.{y}", t
    except ValueError:
        return date, ""
