#!/usr/bin/env python3
"""
i18n.py — переклади інтерфейсу (uk / ru / en).
Використання:  from i18n import tr;  tr(lang, "key")  або  tr(lang, "key", n=3)
Ключа немає -> повертається сам ключ (щоб нічого не падало).
Тільки стандартна бібліотека.
"""

LANGS = ["uk", "ru", "en"]
LANG_NAMES = {"uk": "Українська", "ru": "Русский", "en": "English"}

STR = {
    # ---- загальне / меню ----
    "app_title":        {"uk": "Discord Auto-Compress", "ru": "Discord Auto-Compress", "en": "Discord Auto-Compress"},
    "tab_general":      {"uk": "Загальне",      "ru": "Общее",         "en": "General"},
    "tab_appearance":   {"uk": "Вигляд",        "ru": "Вид",           "en": "Appearance"},
    "tab_media":        {"uk": "Медіа",         "ru": "Медиа",         "en": "Media"},
    "tab_updates":      {"uk": "Оновлення",     "ru": "Обновления",    "en": "Updates"},
    "tab_performance":  {"uk": "Швидкодія",     "ru": "Производит-ть", "en": "Performance"},
    "tab_about":        {"uk": "Про програму",  "ru": "О программе",   "en": "About"},

    "save":             {"uk": "Зберегти",      "ru": "Сохранить",     "en": "Save"},
    "saved":            {"uk": "Збережено ✓",   "ru": "Сохранено ✓",   "en": "Saved ✓"},
    "close":            {"uk": "Закрити",       "ru": "Закрыть",       "en": "Close"},
    "minimize":         {"uk": "Згорнути",      "ru": "Свернуть",      "en": "Minimize"},

    # ---- ліміт ----
    "limit_title":      {"uk": "Ідеальний розмір (ліміт Discord)", "ru": "Идеальный размер (лимит Discord)", "en": "Target size (Discord limit)"},
    "limit_10":         {"uk": "10 МБ (без Nitro)",  "ru": "10 МБ (без Nitro)",  "en": "10 MB (no Nitro)"},
    "limit_25":         {"uk": "25 МБ",              "ru": "25 МБ",              "en": "25 MB"},
    "limit_50":         {"uk": "50 МБ (Nitro Basic)","ru": "50 МБ (Nitro Basic)","en": "50 MB (Nitro Basic)"},
    "limit_500":        {"uk": "500 МБ (Nitro)",     "ru": "500 МБ (Nitro)",     "en": "500 MB (Nitro)"},

    "opt_autoscale":    {"uk": "Авто-підбір роздільності", "ru": "Авто-подбор разрешения", "en": "Auto-pick resolution"},
    "opt_block":        {"uk": "Блокувати «завелику» вставку в Discord", "ru": "Блокировать «слишком большую» вставку в Discord", "en": "Block oversized paste into Discord"},
    "opt_paste":        {"uk": "Сам вставляти стиснутий файл у Discord", "ru": "Сам вставлять сжатый файл в Discord", "en": "Auto-paste compressed file into Discord"},
    "audio_kbps":       {"uk": "Аудіо kbps:", "ru": "Аудио kbps:", "en": "Audio kbps:"},

    # ---- медіа ----
    "media_title":      {"uk": "Що стискати при Ctrl+V", "ru": "Что сжимать при Ctrl+V", "en": "What to compress on Ctrl+V"},
    "media_video":      {"uk": "Відео 🎬",  "ru": "Видео 🎬",  "en": "Video 🎬"},
    "media_image":      {"uk": "Фото 🖼",   "ru": "Фото 🖼",   "en": "Images 🖼"},
    "media_audio":      {"uk": "Звук 🎵",   "ru": "Звук 🎵",   "en": "Audio 🎵"},
    "keep_title":       {"uk": "Стиснуту копію лишати на ПК?", "ru": "Сжатую копию оставлять на ПК?", "en": "Keep compressed copy on PC?"},
    "keep_ask":         {"uk": "Питати щоразу", "ru": "Спрашивать каждый раз", "en": "Ask every time"},
    "keep_always":      {"uk": "Завжди лишати", "ru": "Всегда оставлять", "en": "Always keep"},
    "keep_never":       {"uk": "Завжди видаляти", "ru": "Всегда удалять", "en": "Always delete"},

    # ---- вигляд ----
    "theme_title":      {"uk": "Тема оформлення", "ru": "Тема оформления", "en": "Theme"},
    "lang_title":       {"uk": "Мова",            "ru": "Язык",            "en": "Language"},

    # ---- оновлення ----
    "check_updates":    {"uk": "Перевірити оновлення", "ru": "Проверить обновления", "en": "Check for updates"},
    "checking":         {"uk": "Перевіряю…",  "ru": "Проверяю…",   "en": "Checking…"},
    "up_to_date":       {"uk": "Уже остання версія ✓", "ru": "Уже последняя версия ✓", "en": "You're up to date ✓"},
    "updated_n":        {"uk": "Оновлено файлів: {n}. Перезапусти програму.", "ru": "Обновлено файлов: {n}. Перезапусти программу.", "en": "Updated {n} file(s). Restart the app."},
    "update_fail":      {"uk": "Не вдалося перевірити (немає інтернету?)", "ru": "Не удалось проверить (нет интернета?)", "en": "Update check failed (no internet?)"},
    "update_hint":      {"uk": "Друг оновлюється сам при запуску. Ця кнопка — примусова перевірка.",
                         "ru": "Друг обновляется сам при запуске. Эта кнопка — принудительная проверка.",
                         "en": "A friend auto-updates on launch. This button forces a check."},

    # ---- швидкодія ----
    "perf_run":         {"uk": "Запустити тест оптимізації", "ru": "Запустить тест оптимизации", "en": "Run optimization test"},
    "perf_running":     {"uk": "Тестую…", "ru": "Тестирую…", "en": "Testing…"},
    "perf_hint":        {"uk": "Перевіряє ffmpeg, ядра CPU і швидкість стиснення.",
                         "ru": "Проверяет ffmpeg, ядра CPU и скорость сжатия.",
                         "en": "Checks ffmpeg, CPU cores and compression speed."},

    # ---- трей ----
    "tray_open":        {"uk": "Відкрити меню", "ru": "Открыть меню", "en": "Open menu"},
    "tray_quit":        {"uk": "Закрити програму", "ru": "Закрыть программу", "en": "Quit"},
    "tray_tip":         {"uk": "Discord Auto-Compress — фон", "ru": "Discord Auto-Compress — фон", "en": "Discord Auto-Compress — running"},

    # ---- overlay (пропозиція) ----
    "ov_video_big":     {"uk": "Це відео завелике для Discord", "ru": "Это видео слишком большое для Discord", "en": "This video is too big for Discord"},
    "ov_image_big":     {"uk": "Це фото завелике для Discord",  "ru": "Это фото слишком большое для Discord",  "en": "This image is too big for Discord"},
    "ov_audio_big":     {"uk": "Цей звук завеликий для Discord","ru": "Этот звук слишком большой для Discord", "en": "This audio is too big for Discord"},
    "ov_compress":      {"uk": "Стиснути і вставити  ▶", "ru": "Сжать и вставить  ▶", "en": "Compress & paste  ▶"},
    "ov_split":         {"uk": "Поділити на частини  ⧉", "ru": "Разделить на части  ⧉", "en": "Split into parts  ⧉"},
    "ov_split_bal":     {"uk": "Стиснути і поділити  ⚖", "ru": "Сжать и разделить  ⚖", "en": "Compress & split  ⚖"},
    "ov_trim":          {"uk": "Обрізати момент ✂", "ru": "Обрезать момент ✂", "en": "Trim a moment ✂"},
    "ov_working":       {"uk": "Стискаю…", "ru": "Сжимаю…", "en": "Compressing…"},
    "ov_splitting":     {"uk": "Ділю на частини…", "ru": "Делю на части…", "en": "Splitting…"},
    "ov_comp_split":    {"uk": "Стискаю і ділю…", "ru": "Сжимаю и делю…", "en": "Compressing & splitting…"},
    "ov_cancel":        {"uk": "Скасувати", "ru": "Отмена", "en": "Cancel"},
    "ov_done":          {"uk": "Готово!", "ru": "Готово!", "en": "Done!"},
    "ov_pasted":        {"uk": "Вставлено в Discord ✓", "ru": "Вставлено в Discord ✓", "en": "Pasted into Discord ✓"},
    "ov_in_clip":       {"uk": "У буфері — натисни Ctrl+V у Discord", "ru": "В буфере — нажми Ctrl+V в Discord", "en": "In clipboard — press Ctrl+V in Discord"},
    "ov_keep_q":        {"uk": "Лишити копію на ПК?", "ru": "Оставить копию на ПК?", "en": "Keep the copy on PC?"},
    "ov_keep":          {"uk": "Лишити", "ru": "Оставить", "en": "Keep"},
    "ov_delete":        {"uk": "Видалити", "ru": "Удалить", "en": "Delete"},
    "ov_deleted":       {"uk": "Копію видалено з ПК", "ru": "Копия удалена с ПК", "en": "Copy deleted from PC"},
    "ov_kept":          {"uk": "Копію збережено поруч з оригіналом", "ru": "Копия сохранена рядом с оригиналом", "en": "Copy saved next to original"},
    "ov_fail":          {"uk": "Не вдалося стиснути", "ru": "Не удалось сжать", "en": "Compression failed"},
    "ov_done_parts":    {"uk": "Готово — {n} частин", "ru": "Готово — {n} частей", "en": "Done — {n} parts"},
}


def tr(lang: str, key: str, **fmt) -> str:
    row = STR.get(key)
    if not row:
        return key
    s = row.get(lang) or row.get("uk") or key
    if fmt:
        try:
            s = s.format(**fmt)
        except Exception:
            pass
    return s
