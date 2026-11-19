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
    {"v": "3.2.4", "date": "2026-11-20 00:10", "items": [
        {"icon": "🖼", "tab": None,
         "uk": ("Наша іконка", "На панелі задач у веб-вікон тепер іконка програми, а не «планета». Вікно стиснення на панелі задач не з'являється."),
         "ru": ("Наша иконка", "На панели задач у веб-окон теперь иконка программы, а не «планета». Окно сжатия на панели задач не появляется."),
         "en": ("Our icon", "Web windows now show the app icon in the taskbar instead of a globe. The compress window no longer appears in the taskbar.")},
    ]},
    {"v": "3.2.3", "date": "2026-11-19 23:55", "items": [
        {"icon": "🛠", "tab": None,
         "uk": ("Вікна закриваються самі", "Після оновлення чи виходу з програми веб-вікна (меню, «Мої монтажі», «Що нового») закриваються, а не лишаються висіти."),
         "ru": ("Окна закрываются сами", "После обновления или выхода из программы веб-окна (меню, «Мои монтажи», «Что нового») закрываются, а не остаются висеть."),
         "en": ("Windows close themselves", "After an update or quitting the app, web windows (menu, My edits, What's new) close instead of hanging around.")},
    ]},
    {"v": "3.2.2", "date": "2026-11-19 23:40", "items": [
        {"icon": "🎨", "tab": "appearance",
         "uk": ("Інші теми знову працюють", "Вибери Discord, Midnight, Doki Doki чи Aero — меню відкриється в цій темі. Вибери Moon — повернеться веб-дизайн."),
         "ru": ("Другие темы снова работают", "Выбери Discord, Midnight, Doki Doki или Aero — меню откроется в этой теме. Выбери Moon — вернётся веб-дизайн."),
         "en": ("Other themes work again", "Pick Discord, Midnight, Doki Doki or Aero and the menu opens in that theme. Pick Moon to get the web design back.")},
    ]},
    {"v": "3.2.1", "date": "2026-11-19 23:10", "items": [
        {"icon": "🛠", "tab": None,
         "uk": ("Меню завжди у веб-дизайні", "Веб-вікна мають свої заголовки, тож програма більше не плутає їх зі старим меню."),
         "ru": ("Меню всегда в веб-дизайне", "У веб-окон свои заголовки, поэтому программа больше не путает их со старым меню."),
         "en": ("Menu always in the web design", "Web windows have their own titles, so the app no longer confuses them with the old menu.")},
    ]},
    {"v": "3.2", "date": "2026-11-19 22:30", "items": [
        {"icon": "🌙", "tab": None,
         "uk": ("Веб-дизайн Moon", "Меню, «Мої монтажі», «Що нового» і вікно стиснення тепер веб-сторінки: справжнє скло з розмиттям, луна з променями рухається плавно з частотою твого монітора (60, 144, 180 Гц…), промені світять крізь кнопки."),
         "ru": ("Веб-дизайн Moon", "Меню, «Мои монтажи», «Что нового» и окно сжатия теперь веб-страницы: настоящее стекло с размытием, луна с лучами двигается плавно с частотой твоего монитора (60, 144, 180 Гц…), лучи светят сквозь кнопки."),
         "en": ("Moon web design", "Menu, My edits, What's new and the compress window are now web pages: real frosted glass, the moon and rays move smoothly at your monitor's refresh rate (60, 144, 180 Hz…), rays shine through buttons.")},
        {"icon": "⚡", "tab": None,
         "uk": ("Відкривається одразу", "Вікно стиснення готується заздалегідь у фоні, тож після Ctrl+V з'являється без очікування. Немає Edge — працює старе вікно."),
         "ru": ("Открывается сразу", "Окно сжатия готовится заранее в фоне, поэтому после Ctrl+V появляется без ожидания. Нет Edge — работает старое окно."),
         "en": ("Opens instantly", "The compress window is prepared in the background, so it appears right after Ctrl+V. No Edge — the old window is used.")},
    ]},
    {"v": "3.1", "date": "2026-11-19 19:40", "items": [
        {"icon": "🌙", "tab": "appearance",
         "uk": ("Новий дизайн Moon", "Чорне тло, білий і сірий без кольорів, місяць з променями справа вгорі — він ледь плаває, промені гойдаються. Скляні кнопки, нові перемикачі й повзунки."),
         "ru": ("Новый дизайн Moon", "Чёрный фон, белый и серый без цветов, луна с лучами справа вверху — она слегка плавает, лучи покачиваются. Стеклянные кнопки, новые переключатели и ползунки."),
         "en": ("New Moon design", "Black background, only white and grey, a moon with light rays in the top-right that gently drifts and sways. Glass buttons, new toggles and sliders.")},
        {"icon": "🔤", "tab": "appearance",
         "uk": ("Нові шрифти", "Заголовки — Instrument Serif курсивом, текст — Manrope, підписи й цифри — JetBrains Mono. Шрифти вбудовані, нічого ставити не треба. Старі теми — у «Вигляді»."),
         "ru": ("Новые шрифты", "Заголовки — Instrument Serif курсивом, текст — Manrope, подписи и цифры — JetBrains Mono. Шрифты встроены, ничего ставить не нужно. Старые темы — в «Виде»."),
         "en": ("New fonts", "Titles in Instrument Serif italic, text in Manrope, labels and numbers in JetBrains Mono. Fonts are built in, nothing to install. Old themes are under Appearance.")},
    ]},
    {"v": "3.0.4", "date": "2026-11-19 18:20", "items": [
        {"icon": "⟳", "tab": "updates",
         "uk": ("Видно, що качається", "«Оновити» одразу пише, скільки оновлених файлів і скільки МБ буде скачано (і програвач, якщо його ще нема), і качає тільки змінені файли."),
         "ru": ("Видно, что качается", "«Обновить» сразу пишет, сколько обновлённых файлов и сколько МБ будет скачано (и плеер, если его ещё нет), и качает только изменённые файлы."),
         "en": ("See what downloads", "“Update” shows how many updated files and how many MB will download (plus the player if missing), and fetches only changed files.")},
        {"icon": "🛠", "tab": "updates",
         "uk": ("Більше не «вже остання» на старій версії", "Якщо нові файли вже скачались у фоні, а програма ще працює зі старими, «Оновити» тепер сам її перезапускає."),
         "ru": ("Больше не «уже последняя» на старой версии", "Если новые файлы уже скачались в фоне, а программа ещё работает со старыми, «Обновить» теперь сам её перезапускает."),
         "en": ("No more “up to date” on an old version", "If new files were already fetched in the background while the app still runs the old ones, “Update” now restarts it.")},
    ]},
    {"v": "3.0.3", "date": "2026-11-19 17:30", "items": [
        {"icon": "🎚", "tab": None,
         "uk": ("Гучність наживо", "Тягни повзунок гучності, поки відео грає, — звук міняється одразу, плавно і без клацання. Відео не зупиняється і не перезапускається."),
         "ru": ("Громкость вживую", "Тяни ползунок громкости, пока видео играет, — звук меняется сразу, плавно и без щелчков. Видео не останавливается и не перезапускается."),
         "en": ("Live volume", "Drag the volume slider while the video plays: the sound changes instantly and smoothly, with no clicks. The video doesn't stop or restart.")},
    ]},
    {"v": "3.0.2", "date": "2026-11-19 16:40", "items": [
        {"icon": "🔊", "tab": None,
         "uk": ("Гучність, яку чути", "Права частина повзунка тепер плавно йде +10…+60 dB — кожен рух робить голосніше. Лише останній кусок — до +888 dB, де звук уже «рве». Підсилення — чисте множення з жорстким обрізанням, без лімітера."),
         "ru": ("Громкость, которую слышно", "Правая часть ползунка теперь плавно идёт +10…+60 dB — каждое движение делает громче. Только последний кусок — до +888 dB, где звук уже «рвёт». Усиление — чистое умножение с жёстким обрезанием, без лимитера."),
         "en": ("Volume you can hear", "The right side of the slider now goes smoothly through +10…+60 dB, so every move is louder. Only the last bit goes to +888 dB, where the sound just tears. Boost is a plain multiply with hard clipping, no limiter.")},
    ]},
    {"v": "3.0.1", "date": "2026-11-18 16:40", "items": [
        {"icon": "🎯", "tab": None,
         "uk": ("Кадр іде за повзунком", "На паузі картинка миттєво слідує за білим повзунком — без затримки, ще до ▶."),
         "ru": ("Кадр идёт за ползунком", "На паузе картинка мгновенно следует за белым ползунком — без задержки, ещё до ▶."),
         "en": ("Frame follows the playhead", "While paused, the picture follows the white playhead instantly, even before ▶.")},
        {"icon": "✨", "tab": "whatsnew",
         "uk": ("Усе нове одразу", "Після оновлення «Що нового» показує зміни всіх версій, які ти пропустив, а не тільки останньої. Довгі описи більше не вилазять."),
         "ru": ("Всё новое сразу", "После обновления «Что нового» показывает изменения всех версий, которые ты пропустил, а не только последней. Длинные описания больше не вылазят."),
         "en": ("Everything new at once", "After an update, “What's new” shows changes from every version you skipped, not just the last one. Long descriptions no longer overflow.")},
    ]},
    {"v": "3.0", "date": "2026-11-18 15:30", "items": [
        {"icon": "⚡", "tab": None,
         "uk": ("Миттєвий ▶ у редакторі", "Новий вбудований програвач: старт, пауза і продовження — без затримки, як у CapCut. Зміни ефектів і звуку чути одразу, не зупиняючи відео."),
         "ru": ("Мгновенный ▶ в редакторе", "Новый встроенный плеер: старт, пауза и продолжение — без задержки, как в CapCut. Изменения эффектов и звука слышно сразу, не останавливая видео."),
         "en": ("Instant ▶ in the editor", "New built-in player: play, pause and resume with no delay, like CapCut. Effect and sound changes apply live without stopping the video.")},
        {"icon": "⟳", "tab": "updates",
         "uk": ("Оновлення зі смужкою", "«Оновити» показує, скільки лишилось, сам качає новий програвач (3 джерела, без архіваторів; не вийшло — пише і пробує знову) і сам перезапускає програму."),
         "ru": ("Обновление с полоской", "«Обновить» показывает, сколько осталось, сам качает новый плеер (3 источника, без архиваторов; не вышло — пишет и пробует снова) и сам перезапускает программу."),
         "en": ("Update with a progress bar", "“Update” shows the progress, downloads the new player itself (3 sources, no archiver needed; if it fails it says so and retries) and restarts the app.")},
    ]},
    {"v": "2.9.2", "date": "2026-11-18 12:55", "items": [
        {"icon": "🎵", "tab": None,
         "uk": ("Музику чути завжди", "Додана музика тепер грає і в порожньому проєкті, і під фото, і під відео без звуку. Після закриття редактора нічого не грає."),
         "ru": ("Музыку слышно всегда", "Добавленная музыка теперь играет и в пустом проекте, и под фото, и под видео без звука. После закрытия редактора ничего не играет."),
         "en": ("Music always plays", "Added music now plays in an empty project, over photos and over silent videos. Nothing keeps playing after the editor is closed.")},
    ]},
    {"v": "2.9.1", "date": "2026-11-18 12:35", "items": [
        {"icon": "✂", "tab": "general",
         "uk": ("Редактор без вибору файла", "«Відкрити редактор» одразу відкриває порожній проєкт — перетягни або додай ➕ відео, фото чи звук."),
         "ru": ("Редактор без выбора файла", "«Открыть редактор» сразу открывает пустой проект — перетащи или добавь ➕ видео, фото или звук."),
         "en": ("Editor without picking a file", "“Open editor” opens an empty project right away — drop or ➕ add a video, photo or sound.")},
    ]},
    {"v": "2.9", "date": "2026-11-18 12:22", "items": [
        {"icon": "🗑", "tab": None,
         "uk": ("Delete видаляє будь-що", "Вибраний кліп, фото, текст, накладку чи звук. На єдиному кліпі Delete прибирає відео і лишає звук."),
         "ru": ("Delete удаляет что угодно", "Выбранный клип, фото, текст, наложение или звук. На единственном клипе Delete убирает видео и оставляет звук."),
         "en": ("Delete removes anything", "The selected clip, photo, text, overlay or sound. On the only clip, Delete removes the video and keeps the sound.")},
        {"icon": "✂", "tab": None,
         "uk": ("Звук ріжеться і обрізається", "S — розрізати звук по повзунку, тягни краї звуку — обрізати, зайве — Delete. «Тільки звук» на кліпі прибирає картинку."),
         "ru": ("Звук режется и обрезается", "S — разрезать звук по ползунку, тяни края звука — обрезать, лишнее — Delete. «Только звук» на клипе убирает картинку."),
         "en": ("Cut and trim sounds", "S splits a sound at the playhead, drag its edges to trim, Delete removes a piece. “Audio only” on a clip removes the picture.")},
        {"icon": "🎬", "tab": "general",
         "uk": ("Редактор з меню програми", "Кнопки «Відкрити редактор» і «Мої монтажі» — прямо на першій вкладці меню."),
         "ru": ("Редактор из меню программы", "Кнопки «Открыть редактор» и «Мои монтажи» — прямо на первой вкладке меню."),
         "en": ("Editor from the app menu", "“Open editor” and “My edits” buttons right on the first tab of the menu.")},
        {"icon": "🛠", "tab": None,
         "uk": ("Назви не вилазять", "Підписи звуків, накладок і тексту на доріжці обрізаються під ширину блока."),
         "ru": ("Названия не вылезают", "Подписи звуков, наложений и текста на дорожке обрезаются под ширину блока."),
         "en": ("Labels fit", "Sound, overlay and text labels on the timeline are cut to the block width.")},
    ]},
    {"v": "2.8", "date": "2026-11-18 12:00", "items": [
        {"icon": "⚡", "tab": "gpu",
         "uk": ("Усе в 2–5 разів швидше", "Відеокарта NVIDIA тепер і декодує, і зменшує кадр, і кодує — кадри не ганяються через процесор. MP3 удвічі швидше."),
         "ru": ("Всё в 2–5 раз быстрее", "Видеокарта NVIDIA теперь и декодирует, и уменьшает кадр, и кодирует — кадры не гоняются через процессор. MP3 вдвое быстрее."),
         "en": ("Everything 2–5× faster", "The NVIDIA card now decodes, scales and encodes — frames never go through the CPU. MP3 is 2× faster.")},
        {"icon": "🎙", "tab": None,
         "uk": ("Запис голосу", "Кнопка 🎙 (або R) у редакторі: відео грає, ти говориш — запис лягає на доріжку з того ж місця. ПКМ — вибрати мікрофон."),
         "ru": ("Запись голоса", "Кнопка 🎙 (или R) в редакторе: видео играет, ты говоришь — запись ложится на дорожку с того же места. ПКМ — выбрать микрофон."),
         "en": ("Voice recording", "The 🎙 button (or R) in the editor: the video plays while you talk, the recording lands on the track. Right-click to pick a mic.")},
        {"icon": "🎬", "tab": None,
         "uk": ("Мої монтажі — Ctrl+Alt+E", "Усе збережене з редактора лежить у «Відео → Discord Auto-Compress». Ctrl+Alt+E — галерея: клік вставляє в Discord, ✂ — змонтувати знову, «Новий монтаж» — редактор для будь-якого відео."),
         "ru": ("Мои монтажи — Ctrl+Alt+E", "Всё сохранённое из редактора лежит в «Видео → Discord Auto-Compress». Ctrl+Alt+E — галерея: клик вставляет в Discord, ✂ — смонтировать снова, «Новый монтаж» — редактор для любого видео."),
         "en": ("My edits — Ctrl+Alt+E", "Everything you save from the editor goes to “Videos → Discord Auto-Compress”. Ctrl+Alt+E opens the gallery: click to paste into Discord, ✂ to edit again, “New edit” for any video.")},
    ]},
    {"v": "2.7.2", "date": "2026-11-17 11:19", "items": [
        {"icon": "🛠", "tab": None,
         "uk": ("Довгі відео в малий розмір", "Серія на 30 хв тепер влазить і в 16 МБ: звук сам стає легшим (моно), кадр — менше. «Готово» лише тоді, коли файл справді під лімітом."),
         "ru": ("Длинные видео в малый размер", "Серия на 30 мин теперь влезает и в 16 МБ: звук сам становится легче (моно), кадр — меньше. «Готово» только когда файл реально под лимитом."),
         "en": ("Long videos into small sizes", "A 30-min episode now fits even 16 MB: lighter (mono) sound, smaller frame. “Done” only when the file is really under the limit.")},
        {"icon": "✏", "tab": None,
         "uk": ("Свій розмір — будь-який", "Можна ввести й менше за ліміт із налаштувань (від 0.5 МБ)."),
         "ru": ("Свой размер — любой", "Можно ввести и меньше лимита из настроек (от 0.5 МБ)."),
         "en": ("Any custom size", "You can enter less than your limit too (from 0.5 MB).")},
    ]},
    {"v": "2.7", "date": "2026-11-16 18:50", "items": [
        {"icon": "🔊", "tab": None,
         "uk": ("Чесна гучність", "Понад 300% — у децибелах, аж до +888 dB (справжнє підсилення). Під повзунком видно, до скількох звук ще чистий."),
         "ru": ("Честная громкость", "Выше 300% — в децибелах, вплоть до +888 dB (настоящее усиление). Под ползунком видно, до скольких звук ещё чистый."),
         "en": ("Honest volume", "Above 300% it's shown in decibels, up to +888 dB (real gain). Below the slider: how far it stays clean.")},
        {"icon": "▶", "tab": None,
         "uk": ("Зміни чути одразу", "Міняєш звук чи ефекти під час програвання — воно саме продовжується з новими налаштуваннями."),
         "ru": ("Изменения слышно сразу", "Меняешь звук или эффекты во время воспроизведения — оно само продолжается с новыми настройками."),
         "en": ("Changes are heard instantly", "Change the sound or effects while playing — playback continues with the new settings.")},
        {"icon": "🛠", "tab": None,
         "uk": ("Моно-звук без втрат", "Звук з моно-відео більше не стає тихішим на 3 dB."),
         "ru": ("Моно-звук без потерь", "Звук из моно-видео больше не становится тише на 3 dB."),
         "en": ("Mono sound fixed", "Sound from mono videos no longer gets 3 dB quieter.")},
    ]},
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


def since(old_v, cap=12):
    """Усі записи, новіші за old_v (від найновішого). old_v невідома — останні cap."""
    out = []
    for e in CHANGES:
        if e["v"] == old_v:
            return out or CHANGES[:1]
        out.append(e)
    return CHANGES[:min(cap, len(CHANGES))] if not old_v else out[:cap]


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
