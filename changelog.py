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
    {"v": "2.6", "date": "2026-11-16 18:35", "items": [
        {"icon": "🎵", "tab": None,
         "uk": ("Зберегти тільки звук", "Кнопка формату біля «Зберегти»: відео (MP4), тільки звук (MP3) або GIF."),
         "ru": ("Сохранить только звук", "Кнопка формата возле «Сохранить»: видео (MP4), только звук (MP3) или GIF."),
         "en": ("Save audio only", "Format button next to “Save”: video (MP4), audio only (MP3) or GIF.")},
        {"icon": "🎛", "tab": None,
         "uk": ("Ефекти звуку", "Slowed + Reverb, Nightcore, бас-буст, earrape, 8D, телефон, під водою, луна, тон і реверб."),
         "ru": ("Эффекты звука", "Slowed + Reverb, Nightcore, басс-буст, earrape, 8D, телефон, под водой, эхо, тон и реверб."),
         "en": ("Sound effects", "Slowed + Reverb, Nightcore, bass boost, earrape, 8D, phone, underwater, echo, pitch and reverb.")},
        {"icon": "💀", "tab": None,
         "uk": ("Гучність до 10000%", "Експериментально — для угару. Права половина повзунка гучності."),
         "ru": ("Громкость до 10000%", "Экспериментально — для угара. Правая половина ползунка громкости."),
         "en": ("Volume up to 10000%", "Experimental — just for fun. The right half of the volume slider.")},
    ]},
    {"v": "2.5", "date": "2026-11-16 18:13", "items": [
        {"icon": "⚡", "tab": "gpu",
         "uk": ("Редактор зберігає втричі швидше", "Весь монтаж — один прохід: відеокарта і декодує, і кодує, ефекти рахуються одразу в потрібному розмірі."),
         "ru": ("Редактор сохраняет втрое быстрее", "Весь монтаж — один проход: видеокарта и декодирует, и кодирует, эффекты считаются сразу в нужном размере."),
         "en": ("Editor saves 3× faster", "The whole edit in one pass: the graphics card decodes and encodes, effects render at the final size.")},
    ]},
    {"v": "2.4.1", "date": "2026-11-16 17:23", "items": [
        {"icon": "⚙", "tab": None,
         "uk": ("Панель налаштувань — за кнопкою", "Права панель редактора схована, відкривається кнопкою ⚙ (або клавішею P) — плеєр став більшим."),
         "ru": ("Панель настроек — по кнопке", "Правая панель редактора скрыта, открывается кнопкой ⚙ (или клавишей P) — плеер стал больше."),
         "en": ("Settings panel on demand", "The editor's right panel is hidden; open it with the ⚙ button (or P) — the player is bigger.")},
    ]},
    {"v": "2.4", "date": "2026-11-16 17:12", "items": [
        {"icon": "▭", "tab": None,
         "uk": ("Формат кадру", "9:16 для TikTok / Shorts / Reels, 1:1, 4:5, 16:9 — кнопка вгорі редактора."),
         "ru": ("Формат кадра", "9:16 для TikTok / Shorts / Reels, 1:1, 4:5, 16:9 — кнопка вверху редактора."),
         "en": ("Frame format", "9:16 for TikTok / Shorts / Reels, 1:1, 4:5, 16:9 — the button at the top of the editor.")},
        {"icon": "◌", "tab": None,
         "uk": ("Розмитий фон", "Замість чорних смуг — те саме відео, розмите на весь кадр, як у CapCut."),
         "ru": ("Размытый фон", "Вместо чёрных полос — то же видео, размытое на весь кадр, как в CapCut."),
         "en": ("Blurred background", "Instead of black bars — the same video blurred to fill the frame, like CapCut.")},
        {"icon": "⋈", "tab": None,
         "uk": ("Переходи між кліпами", "Клікни «+» на стику кліпів: розчинення, через чорне/біле, зсув, шторка, коло, наближення, пікселі, радар."),
         "ru": ("Переходы между клипами", "Кликни «+» на стыке клипов: растворение, через чёрное/белое, сдвиг, шторка, круг, приближение, пиксели, радар."),
         "en": ("Transitions between clips", "Click “+” where two clips meet: dissolve, dip to black/white, slide, wipe, circle, zoom, pixelate, radial.")},
    ]},
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
