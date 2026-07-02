#!/usr/bin/env python3
"""
jokes.py — цікаві ФАКТИ про програму, що показуються під час стиснення/експорту.
(Раніше тут були жарти; на прохання юзера замінено на факти. Файл лишив із назвою
jokes.py, щоб не міняти manifest/імпорти — онлайн-безпечно.) Лише stdlib.
"""

FACTS = {
    "uk": [
        "Стиснення двопрохідне (x264) — краща якість під заданий розмір.",
        "Програма сама ловить Ctrl+V у Discord і стискає, що у буфері.",
        "Довге відео ділиться на частини, кожна влазить у ліміт.",
        "Розмір гарантовано менший за ліміт — цілимось трохи нижче стелі.",
        "Частини кодуються ПАРАЛЕЛЬНО — на кількох ядрах одразу.",
        "Вбудований редактор має таймлайн у стилі CapCut із хвилею звуку.",
        "Ручки обрізки рухаються стрілками — точність по кадру.",
        "Фото стискаються у WebP, а звук — у MP3.",
        "Кліпи можна експортувати у GIF.",
        "Усе працює ЛОКАЛЬНО — відео не покидає твій комп'ютер.",
        "Програма безкоштовна й з відкритим кодом (ліцензія MIT).",
        "Живе тихо у треї й оновлюється сама з GitHub.",
        "Значок програми намальовано прямо в коді, без файлів-картинок.",
        "Є три теми та три мови (укр / рос / англ).",
        "Можна поставити СВІЙ звук «готово».",
        "Лише Python + ffmpeg — жодних важких залежностей.",
    ],
    "ru": [
        "Сжатие двухпроходное (x264) — лучшее качество под заданный размер.",
        "Программа сама ловит Ctrl+V в Discord и сжимает то, что в буфере.",
        "Длинное видео делится на части, каждая влезает в лимит.",
        "Размер гарантированно меньше лимита — целимся чуть ниже потолка.",
        "Части кодируются ПАРАЛЛЕЛЬНО — сразу на нескольких ядрах.",
        "Встроенный редактор с таймлайном в стиле CapCut и звуковой волной.",
        "Ручки обрезки двигаются стрелками — точность по кадру.",
        "Фото сжимаются в WebP, а звук — в MP3.",
        "Клипы можно экспортировать в GIF.",
        "Всё работает ЛОКАЛЬНО — видео не покидает твой компьютер.",
        "Программа бесплатная и с открытым кодом (лицензия MIT).",
        "Живёт тихо в трее и обновляется сама с GitHub.",
        "Значок программы нарисован прямо в коде, без файлов-картинок.",
        "Есть три темы и три языка (укр / рус / англ).",
        "Можно поставить СВОЙ звук «готово».",
        "Только Python + ffmpeg — никаких тяжёлых зависимостей.",
    ],
    "en": [
        "Compression is two-pass (x264) — best quality at the target size.",
        "It catches Ctrl+V in Discord and compresses whatever is in the clipboard.",
        "Long videos are split into parts that each fit the limit.",
        "The size is guaranteed under the limit — it aims just below the ceiling.",
        "Parts are encoded IN PARALLEL — across several CPU cores at once.",
        "The built-in editor has a CapCut-style timeline with an audio waveform.",
        "Trim handles move with arrow keys — frame-accurate.",
        "Images are compressed to WebP, audio to MP3.",
        "Clips can be exported to GIF.",
        "Everything runs LOCALLY — your videos never leave your computer.",
        "The app is free and open-source (MIT license).",
        "It lives quietly in the tray and updates itself from GitHub.",
        "The app icon is drawn in code — no image files.",
        "Three themes and three languages (UK / RU / EN).",
        "You can set your OWN 'done' sound.",
        "Just Python + ffmpeg — no heavy dependencies.",
    ],
}


def facts_for(lang):
    """Список фактів заданою мовою (fallback -> англ.)."""
    return FACTS.get(lang) or FACTS["en"]


def count(lang="en") -> int:
    return len(facts_for(lang))
