# Задача: разработать production-ready Telegram-бота для идеальной перекраски стикеров и Custom Emoji

Разработай с нуля полноценного production-ready Telegram-бота на Python для перекраски Telegram Custom Emoji, обычных стикеров, целых sticker/emoji packs и отдельных файлов.

Это должен быть не прототип и не демонстрация. Нужен законченный, хорошо структурированный, асинхронный проект, который можно запустить локально, а затем развернуть на VPS.

Не оставляй `TODO`, `pass`, заглушки, псевдокод или неработающие ветки. Если какая-либо возможность технически ограничена Telegram, реализуй максимально корректное поведение и понятную обработку ограничения.

Перед реализацией обязательно проанализируй актуальный Telegram Bot API и используемые версии библиотек. Если Telegram API изменился относительно требований ниже, адаптируй реализацию под актуальный API, но не меняй пользовательскую концепцию проекта.

---

## Название проекта и бота

Официальное название Telegram-бота:

`Emoji & Sticker Color Bot`

Использовать именно это название во всех местах, где требуется название продукта:

* README;
* описание проекта;
* `/start`, если название бота упоминается в тексте;
* `/help`;
* `/privacy`;
* административная панель;
* документация;
* комментарии конфигурации, если необходимо;
* title/metadata проекта.

Не придумывать альтернативные названия продукта без необходимости.

Название локальной папки проекта и рекомендуемое название GitHub-репозитория:

`emoji-sticker-color-bot`

Название Python package/module, если потребуется отдельный именованный package:

`emoji_sticker_color_bot`

Не путать display name Telegram-бота с Telegram username.

Telegram username будет создан отдельно через BotFather и должен задаваться динамически через Telegram API/configuration. Не hardcode конкретный `@username` в коде.

При генерации short name новых Sticker/Emoji Packs получать актуальный username бота через `getMe()` и использовать его там, где Telegram требует суффикс `_by_<bot_username>`.


# 1. Python и окружение

Минимальная поддерживаемая версия Python проекта:

```text
Python >= 3.12
```

Локальная разработка будет происходить на:

```text
Python 3.14.7
```

На Windows нужно создать:

```text
.venv
```

именно через установленный локальный Python 3.14.x.

Предпочтительно:

```powershell
py -3.14 -m venv .venv
```

После создания проверить:

```powershell
.venv\Scripts\python.exe --version
```

Ожидается Python 3.14.x.

Все Python-библиотеки без исключений должны устанавливаться только внутрь `.venv`.

Запрещено устанавливать Python-пакеты глобально.

Все команды установки должны использовать:

```powershell
.venv\Scripts\python.exe -m pip ...
```

а не системный `pip`.

Обновить внутри `.venv`:

```powershell
.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
```

Проект должен оставаться совместимым минимум с Python 3.12 и не использовать конструкции, которые существуют только в Python 3.14 без реальной необходимости.

На момент разработки использовать актуальную стабильную версию aiogram 3.x, совместимую с Python 3.14.

Создать:

```text
pyproject.toml
requirements.txt
requirements-dev.txt
requirements.lock
.env.example
.gitignore
README.md
```

После подбора рабочих версий зависимостей зафиксировать точные версии в lock-файле для воспроизводимой установки на VPS.

Не переносить `.venv` с Windows на Linux.

Если VPS работает на Linux, на нём создаётся отдельный `.venv`:

```bash
python3.12 -m venv .venv
```

или через более новую установленную совместимую версию Python.

После чего зависимости устанавливаются заново из lock/requirements.

---

# 2. Рекомендуемый стек

Использовать:

```text
aiogram 3.x
asyncio
aiosqlite
pydantic-settings
Pillow
numpy
aiofiles
psutil
imageio-ffmpeg
emoji
regex
python-slugify
pytest
pytest-asyncio
ruff
mypy
```

Если какая-то библиотека на момент разработки имеет проблемы с Python 3.14.7, подобрать современную стабильную альтернативу.

Не подключать тяжёлые библиотеки без реальной необходимости.

Для TGS желательно работать напрямую с gzip + JSON и не тащить огромный Lottie framework, если он не нужен.

Для WEBM использовать FFmpeg.

Предпочтительно получать FFmpeg executable через установленный внутри `.venv` пакет `imageio-ffmpeg`, чтобы для локальной Windows-разработки не требовалась отдельная глобальная Python-библиотека.

Не использовать:

```python
shell=True
```

для запуска FFmpeg.

---

# 3. Архитектура проекта

Не складывать весь проект в один файл.

Пример желаемой структуры:

```text
project/
│
├── app/
│   ├── main.py
│   ├── config.py
│   ├── logging.py
│   │
│   ├── handlers/
│   │   ├── start.py
│   │   ├── help.py
│   │   ├── language.py
│   │   ├── privacy.py
│   │   ├── input.py
│   │   ├── color.py
│   │   ├── preview.py
│   │   ├── output.py
│   │   ├── cancel.py
│   │   └── admin.py
│   │
│   ├── keyboards/
│   │   ├── user.py
│   │   └── admin.py
│   │
│   ├── services/
│   │   ├── jobs.py
│   │   ├── source_resolver.py
│   │   ├── telegram_files.py
│   │   ├── telegram_stickers.py
│   │   ├── telegram_rate_limiter.py
│   │   ├── user_rate_limiter.py
│   │   ├── scheduler.py
│   │   ├── archive.py
│   │   ├── unicode_emoji.py
│   │   ├── premium_emoji.py
│   │   └── cleanup.py
│   │
│   ├── recolor/
│   │   ├── color_math.py
│   │   ├── raster.py
│   │   ├── tgs.py
│   │   └── webm.py
│   │
│   ├── validators/
│   │   ├── common.py
│   │   ├── tgs.py
│   │   ├── image.py
│   │   ├── webm.py
│   │   └── archive.py
│   │
│   ├── database/
│   │   ├── connection.py
│   │   ├── admins.py
│   │   ├── settings.py
│   │   └── statistics.py
│   │
│   ├── models/
│   │   ├── job.py
│   │   ├── source.py
│   │   └── limits.py
│   │
│   ├── i18n/
│   │   ├── ru.py
│   │   └── en.py
│   │
│   └── utils/
│
├── tests/
├── data/
├── temp/
├── logs/
│
├── .env
├── .env.example
├── .gitignore
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

Структуру можно улучшить, если есть более логичный вариант.

Главное:

* разделять Telegram handlers;
* обработку файлов;
* recolor engine;
* Telegram Sticker API;
* rate limits;
* runtime jobs;
* БД;
* admin panel;
* Premium Emoji;
* локализацию.

---

# 4. Главное требование по приватности

Обычные пользователи НЕ должны постоянно сохраняться в БД.

Не создавать таблицу:

```text
users
```

и вообще не создавать никакое постоянное пользовательское хранилище для обычных пользователей.

Нельзя постоянно сохранять:

```text
telegram_user_id
chat_id
username
first_name
last_name
историю запросов
историю цветов
историю созданных паков
названия пользовательских паков
отправленные файлы
полученные emoji
sticker file_id
custom_emoji_id
```

обычных пользователей.

Telegram `user_id` и `chat_id` обычного пользователя допустимо использовать только временно в оперативной памяти, пока они необходимы текущей задаче.

После завершения задачи временное runtime-состояние удаляется.

После перезапуска приложения все runtime user limits и состояния обычных пользователей исчезают.

---

# 5. Администраторы — исключение

Администраторы должны храниться в SQLite.

Допустима таблица:

```text
admins
```

Пример:

```text
telegram_user_id INTEGER PRIMARY KEY
role TEXT
added_at DATETIME
added_by INTEGER NULL
is_active BOOLEAN
```

Можно добавить служебные поля, если они действительно нужны.

Роли:

```text
owner
admin
```

Первоначальный владелец задаётся через:

```env
OWNER_ID=
```

При первом запуске он автоматически добавляется в БД как `owner`.

Owner нельзя удалить, заблокировать или понизить через интерфейс.

Через `/admin` owner должен иметь возможность:

```text
добавить администратора
удалить администратора
посмотреть администраторов
```

Добавление администратора производится по Telegram numeric user ID.

Пользовательская БД при этом всё равно не создаётся.

---

# 6. Поведение /admin

Команда:

```text
/admin
```

доступна только администраторам.

Критическое требование:

если обычный пользователь пишет:

```text
/admin
```

бот не должен отправлять ему НИЧЕГО.

Никакого:

```text
У вас нет доступа
Команда недоступна
Вы не администратор
```

Просто:

```python
return
```

без сообщения.

Неавторизованные `/admin` также не должны попадать в persistent logs.

Все admin callback handlers повторно проверяют admin status.

---

# 7. Какие данные разрешено постоянно хранить

SQLite может содержать только:

```text
admins
app_settings
aggregate_statistics
```

В aggregate statistics допустимо:

```text
date
total_jobs
successful_jobs
failed_jobs
tgs_processed
webm_processed
images_processed
packs_created
telegram_429_count
processing_time_total
```

Никаких user ID внутри статистики.

Также никакой связи:

```text
job -> user
```

на диске быть не должно.

---

# 8. Логи

Нельзя логировать:

```text
user_id
chat_id
username
first_name
last_name
полные Telegram Update
текст пользовательского сообщения
исходный HEX, если это не нужно
названия пользовательских файлов
названия пользовательских паков
file_id
custom_emoji_id
содержимое файлов
```

Использовать случайный:

```text
job_id
```

например UUID.

Пример допустимого лога:

```text
JOB a8421e | TGS | started
JOB a8421e | source_items=84
JOB a8421e | processed=42/84
JOB a8421e | Telegram flood control | retry_after=37
JOB a8421e | finished | 84/84
```

Не логировать raw Telegram exceptions, если они могут включать method payload с `chat_id/user_id`.

Создать sanitizing logging layer.

---

# 9. Временные файлы

Для каждой задачи создавать случайную директорию:

```text
temp/jobs/<uuid>/
```

НЕ:

```text
temp/<telegram_user_id>/
```

Пример:

```text
temp/jobs/8f41a1d4.../
├── source/
├── preview/
├── processed/
└── output/
```

После:

```text
успеха
ошибки
отмены
```

выполнять cleanup в `finally`.

После запуска приложения полностью очищать собственную директорию `temp/jobs`, потому что после рестарта старых runtime jobs больше не существует.

Пока пользователь находится на интерактивном этапе:

```text
выбор цвета
preview
выбор формата
название пака
```

использовать idle timeout:

```text
15 минут
```

После timeout:

* удалить runtime job;
* удалить temp;
* очистить FSM.

Во время реальной обработки или Telegram flood-wait этот 15-минутный idle timeout не применять.

---

# 10. Поддерживаемые источники

Пользователь может отправить:

1. один обычный Telegram sticker;
2. один Telegram Custom Emoji;
3. ссылку на целый sticker pack;
4. ссылку на целый custom emoji pack;
5. `.tgs`;
6. `.webm`;
7. `.webp`;
8. `.png`;
9. `.zip`;
10. обычный Unicode emoji;
11. Telegram media group / набор файлов, если Telegram действительно прислал их как одну media group.

Поддерживать ссылки:

```text
https://t.me/addstickers/<name>
https://t.me/addemoji/<name>
t.me/addstickers/<name>
t.me/addemoji/<name>
```

Корректно обрабатывать query string, trailing slash и похожие безопасные варианты.

Не делать произвольные HTTP fetch на URL пользователя.

Разрешены только заранее известные Telegram pack links.

---

# 11. Один отправленный элемент не означает весь его pack

Если пользователь отправляет один sticker:

обрабатывается только этот sticker.

Если пользователь отправляет один Custom Emoji:

обрабатывается только этот Custom Emoji.

Никогда автоматически не разворачивать его в исходный набор.

Чтобы обработать весь набор, пользователь должен отправить ссылку на pack.

---

# 12. Несколько отдельных сообщений

Правило:

```text
одно сообщение / одна media group / один pack link / один ZIP = одна задача
```

Не собирать автоматически 20 отдельных сообщений пользователя в одну коллекцию.

У обычного пользователя одновременно может существовать только одна активная логическая задача.

Если во время активной задачи он присылает новый источник, предложить:

```text
завершить текущую задачу
или
отменить её
```

---

# 13. Media Group

Если Telegram реально прислал несколько файлов с одинаковым:

```text
media_group_id
```

собрать их в одну задачу.

Использовать небольшой debounce, чтобы дождаться всех элементов группы.

Не склеивать сообщения без одинакового `media_group_id`.

Максимум отдельных файлов в одной media group task:

```text
50
```

---

# 14. Unicode Emoji

Поддерживать обычные Unicode emoji:

```text
🔥
❤️
😀
👨‍💻
🏳️‍🌈
и составные emoji sequences
```

Определять emoji как Unicode grapheme cluster, а не один code point.

Использовать `emoji` + `regex` либо другой корректный Unicode-aware подход.

Unicode Emoji нужно:

```text
отрендерить в прозрачное изображение
↓
применить recolor
↓
дальше работать как с raster source
```

Результат уже НЕ является Unicode-символом.

Для Unicode исходника:

```text
Файл -> PNG
Emoji Pack -> custom emoji
Sticker Pack -> sticker
ZIP -> PNG внутри архива
```

Для рендера использовать системный Color Emoji font через конфиг:

```env
EMOJI_FONT_PATH=
```

На Windows попытаться автоматически найти подходящий системный emoji font.

На Linux поддержать настроенный Noto Color Emoji или совместимый font.

Не скачивать неизвестные внешние assets молча во время обработки.

Если emoji font отсутствует и корректный rendering невозможен, показать понятную ошибку конфигурации вместо повреждённого результата.

---

# 15. Анализ pack

Когда пользователь отправляет ссылку на целый pack, не делать отдельные сообщения на каждом шаге.

Отправить ОДНО основное информационное сообщение примерно такой структуры:

```text
[Premium Emoji] Набор найден

Название: ...
Тип: Emoji Pack / Sticker Pack
Элементов: 84
Форматы:
TGS: 64
WEBM: 12
WEBP: 8

Выберите цвет или отправьте свой код:

#FFFFFF — Белый
#000000 — Чёрный
#FF0000 — Красный
#FF9800 — Оранжевый
#FFEB3B — Жёлтый
#4CAF50 — Зелёный
#03A9F4 — Голубой
#2196F3 — Синий
#9C27B0 — Фиолетовый
#E91E63 — Розовый

Поддерживается HEX и RGB.
```

Не спамить несколькими служебными сообщениями.

---

# 16. Color Picker

Под основным сообщением должна находиться inline-кнопка:

```text
Подобрать цвет
```

которая открывает:

```text
https://htmlcolorcodes.com/color-picker/
```

через:

```python
WebAppInfo
```

чтобы сайт открывался внутри Telegram.

Важно:

этот сайт не является нашей Mini App и не возвращает выбранный цвет обратно в бота.

Поэтому текст интерфейса должен объяснить:

```text
Выберите цвет на сайте, скопируйте HEX/RGB-код и отправьте его боту.
```

Не создавать собственную Mini App.

---

# 17. Форматы цвета

Поддерживать:

```text
#FF00AA
FF00AA

#F0A
F0A

rgb(255, 0, 170)

255, 0, 170
```

После parsing всегда нормализовать в:

```text
#RRGGBB
```

Проверять:

```text
R/G/B = 0..255
```

Не принимать некорректные строки частично.

Не использовать пользовательскую alpha-компоненту.

Исходная прозрачность изображения сохраняется автоматически.

---

# 18. Стандартные цвета

Список оставить именно таким:

```text
#FFFFFF — Белый
#000000 — Чёрный
#FF0000 — Красный
#FF9800 — Оранжевый
#FFEB3B — Жёлтый
#4CAF50 — Зелёный
#03A9F4 — Голубой
#2196F3 — Синий
#9C27B0 — Фиолетовый
#E91E63 — Розовый
```

Не добавлять обычные Unicode `🔴🟣🟢` перед названиями.

Premium Emoji будут использоваться отдельно в оформлении интерфейса.

---

# 19. Главное требование к перекраске

НЕЛЬЗЯ делать тупую замену:

```text
все непрозрачные pixels -> #TARGET
```

Нужна качественная монохромная тонировка.

Пользователь выбирает, например:

```text
#FF0000
```

Исходное изображение:

```text
белый блик
светлый объект
основной цвет
тёмная тень
почти чёрный контур
```

должно стать:

```text
очень светлым красным бликом
светлым красным
целевым красным
тёмно-красной тенью
очень тёмно-красным контуром
```

То есть:

```text
исходный hue/chroma убирается
brightness/lightness/contrast сохраняются
alpha сохраняется
формы сохраняются
тени сохраняются
блики сохраняются
контуры сохраняются
градиенты сохраняются
```

---

# 20. Цветовая математика

Не использовать примитивный HSL hue replace, если результат визуально хуже.

Реализовать качественную цветовую модель через:

```text
linear sRGB
OKLab / OKLCH
```

Можно реализовать преобразования самостоятельно через NumPy, чтобы не тянуть тяжёлый color-science framework.

Базовый принцип для цветных target colors:

1. получить perceptual lightness исходного цвета;
2. получить hue/chroma выбранного target;
3. сохранить относительную lightness исходного элемента;
4. назначить target hue;
5. адаптировать chroma;
6. выполнить gamut mapping;
7. преобразовать обратно в sRGB;
8. clamp выполнить только после perceptual gamut correction, а не тупым RGB clipping.

Особое внимание:

```text
очень светлые highlights
очень тёмные outlines
полупрозрачные края
```

Они не должны превращаться в грязные цвета.

---

# 21. Белый, чёрный и серые target colors

У achromatic target:

```text
white
black
gray
```

нет нормального hue.

Поэтому создать отдельную логику.

Если выбран:

```text
#000000
```

нельзя превращать весь объект в абсолютно чёрный прямоугольник без деталей.

Получается тёмная монохромная версия с сохранённым contrast:

```text
highlight -> более светлый тёмно-серый
main -> почти чёрный
shadow -> ещё темнее
```

Для:

```text
#FFFFFF
```

аналогично:

```text
highlight -> почти белый
main -> светло-серый/белый
shadow -> более тёмный светлый оттенок
```

Сохранить различимость деталей.

Написать визуальные unit tests для этого алгоритма.

---

# 22. Alpha

Alpha-channel является священным.

Если исходный pixel имеет:

```text
alpha = X
```

после recolor должен остаться тот же X, кроме ситуаций, где форматирование Telegram объективно требует преобразования.

Не разрушать antialiasing.

Корректно работать с premultiplied alpha.

Не создавать белые/чёрные halos вокруг прозрачных границ.

---

# 23. PNG / WEBP

Использовать:

```text
Pillow
NumPy
```

Изображение переводится в RGBA.

Recolor выполнять векторизованно.

Не делать Python loop по каждому pixel.

При необходимости resize:

```text
Lanczos
```

или другой high-quality filter.

---

# 24. TGS

`.tgs` представляет собой gzipped Lottie JSON.

Работать:

```text
gzip -> JSON -> transform -> compact JSON -> gzip
```

Обязательно безопасно валидировать gzip и максимальный decompressed size.

Не считать любой массив `[r,g,b,a]` цветом.

Нужно понимать структуру Lottie.

Поддержать перекраску:

```text
fill colors
stroke colors
gradient stops
animated color keyframes
nested layers
nested groups
precompositions/assets
анимированные start/end color values
```

Не менять:

```text
transforms
positions
rotations
scales
easing
frame timings
opacity
геометрию paths
```

если это не требуется.

Если внутри есть mask, сохранить mask как есть.

Если встречается нестандартная структура, которую можно безопасно обойти — сохранить её.

Не уничтожать неизвестные JSON fields.

---

# 25. Animated color в TGS

Если элемент во времени меняется:

```text
с красного
на зелёный
на синий
```

после recolor вся анимация должна принадлежать выбранному hue, но изменение lightness/brightness во времени должно остаться.

Обрабатывать:

```text
keyframe.s
keyframe.e
и другие реальные Lottie color payloads
```

а не только static `"k"`.

---

# 26. Gradients

Если source:

```text
светлый
↓
средний
↓
тёмный
```

gradient сохраняется.

Каждая color stop переводится в target hue независимо с сохранением perceptual lightness.

Не заменять весь gradient одним flat color.

---

# 27. Невалидный / нестандартный TGS

Telegram TGS имеет строгий формат.

Если пользователь напрямую загрузил нестандартный TGS, который:

```text
повреждён
не является gzip JSON
использует неподдерживаемую Telegram структуру
слишком большой
```

не запускать гигантский rendering fallback.

Сначала:

```text
safe parse
safe recolor
validation
```

Если гарантировать корректный Telegram output невозможно — вернуть понятную ошибку.

Приоритет:

```text
надёжность сервера > попытка любой ценой обработать мусорный файл
```

---

# 28. WEBM

WEBM — самый тяжёлый тип обработки.

Не загружать все frames видео в RAM одновременно.

Использовать streaming pipeline:

```text
FFmpeg decode
↓
RGBA frames
↓
NumPy recolor
↓
FFmpeg VP9 encode
```

Обрабатывать frame-by-frame.

Сохранять alpha.

Не обрабатывать audio — удалить audio stream.

Telegram video sticker/emoji output должен использовать:

```text
WEBM
VP9
без audio
до 30 FPS
до 3 секунд
```

При необходимости автоматически:

```text
resize
cap FPS
transcode VP8 -> VP9
remove audio
```

НЕ обрезать видео длиннее допустимой продолжительности молча.

Если duration > Telegram maximum — объяснить пользователю проблему.

---

# 29. Telegram dimensions

При создании обычного static/video sticker:

```text
одна сторона = 512 px
вторая <= 512 px
```

Aspect ratio сохранять.

Не растягивать изображение.

Для Custom Emoji static/video:

```text
100x100 px
```

При необходимости использовать transparent padding, а не искажать aspect ratio.

Для TGS:

```text
canvas 512x512
```

не переводить TGS custom emoji в 100x100.

---

# 30. Конвертация Emoji Pack ↔ Sticker Pack

Пользователь не должен думать о Telegram dimensions.

Если:

```text
обычный sticker -> Emoji Pack
```

бот автоматически адаптирует output под Custom Emoji.

Если:

```text
Custom Emoji -> Sticker Pack
```

автоматически адаптировать под sticker requirements.

Не менять aspect ratio.

Для raster/video использовать качественный resize.

---

# 31. Не делать WEBM -> TGS

Не пытаться автоматически превращать:

```text
WEBM -> TGS
PNG -> TGS
WEBP -> TGS
```

Это принципиально разные технологии.

Вместо старой кнопки:

```text
Обычная TGS
```

использовать логическое:

```text
Файл
```

Для single source:

```text
TGS -> TGS
WEBM -> WEBM
WEBP -> WEBP
PNG -> PNG
Unicode -> PNG
```

---

# 32. Output choices

Для одного элемента после выбора цвета показать:

```text
Эмодзи-пак
Стикер-пак
Файл
ZIP-архив
```

Для целого pack:

```text
Эмодзи-пак
Стикер-пак
ZIP-архив
```

Не показывать `Файл`, потому что pack содержит много элементов.

Таким образом пользователь никогда не нажимает `Файл` и неожиданно не получает ZIP.

---

# 33. Preview

Если source содержит больше одного элемента:

после выбора цвета сначала перекрасить только ПЕРВЫЙ элемент.

Именно первый элемент.

Показать preview.

Кнопки:

```text
Продолжить
Другой цвет
Отмена
```

Если первый элемент физически повреждён и preview невозможно сделать, допускается использовать первый следующий исправный элемент, но зафиксировать это только технически.

При:

```text
Другой цвет
```

НЕ скачивать pack заново.

Исходники уже находятся во временной job directory.

Вернуться к выбору цвета и переделать только preview.

---

# 34. Single item preview

Для одного элемента не создавать лишний отдельный approval step.

После выбора цвета сразу перейти к выбору output type.

После выбора output выполнить обработку.

Так интерфейс остаётся быстрым.

---

# 35. Adaptive Emoji

В меню выбора цвета должна присутствовать отдельная кнопка:

```text
Сделать Adaptive
```

Но только там, где эта функция имеет смысл.

Adaptive — это альтернативный режим вместо фиксированного цвета.

То есть нельзя одновременно:

```text
#8B5CF6 + Adaptive
```

Если выбран Adaptive:

```text
fixed target color = NONE
needs_repainting = True
```

При создании набора использовать Telegram adaptive custom emoji functionality.

Adaptive доступен только для:

```text
Custom Emoji Pack
```

Не создавать фальшивый Adaptive режим для обычных sticker packs.

Если пользователь нажал `Сделать Adaptive`, дальнейший output автоматически является Emoji Pack.

Не показывать после этого:

```text
Sticker Pack
File
ZIP
```

как adaptive outputs, потому что adaptive является свойством Telegram Custom Emoji set.

---

# 36. Перекраска исходного Adaptive Emoji

Если пользователь отправил уже существующий Adaptive Emoji, но выбрал конкретный цвет:

```text
#8B5CF6
```

создать обычный fixed-color Custom Emoji.

Для нового set:

```text
needs_repainting = False
```

То есть исходное adaptive-поведение намеренно отключается.

---

# 37. Adaptive preview

Для Adaptive можно показать первый source item как preview формы и коротко объяснить:

```text
Фактический цвет Adaptive Emoji будет определяться Telegram в зависимости от места использования и темы.
```

После:

```text
Продолжить
Отмена
```

перейти к названию Emoji Pack.

Не обещать конкретный цвет preview.

---

# 38. Название нового pack

При output:

```text
Emoji Pack
Sticker Pack
```

бот должен спросить:

```text
Введите название нового набора
```

Если source является целым Telegram pack, рядом показать кнопку:

```text
Использовать название исходного
```

Название должно пройти validation Telegram.

Если слишком длинное — попросить изменить, а не молча сильно обрезать пользовательское название.

---

# 39. Short name

Telegram short name генерируется автоматически.

Пользователь его вручную не вводит.

Алгоритм:

```text
title
↓
ASCII slug
↓
normalize underscores
↓
random suffix
↓
_by_<bot_username>
```

Учитывать Telegram maximum length.

Short name должен:

```text
начинаться с буквы
содержать только допустимые символы
не иметь __
заканчиваться _by_<bot_username>
```

Использовать random suffix, чтобы минимизировать collisions.

Если Telegram всё равно сообщает:

```text
name occupied
```

автоматически сгенерировать новый suffix и повторить.

---

# 40. Emoji associations

При копировании Telegram pack сохранять для каждого элемента оригинальную emoji association, когда Telegram Bot API её предоставляет.

Например:

```text
😂 -> 😂
🔥 -> 🔥
❤️ -> ❤️
```

Если association отсутствует, использовать безопасный fallback emoji.

Сохранять исходный порядок элементов.

---

# 41. Thumbnail

Попытаться сохранить оригинальный thumbnail pack.

Если Telegram API позволяет получить и установить thumbnail:

```text
download
recolor
validate
set new thumbnail
```

Для Custom Emoji set, где thumbnail выбирается через Custom Emoji элемента нового set, сопоставить исходный thumbnail с соответствующим новым элементом, если это возможно.

Если точное соответствие невозможно, использовать первый элемент нового набора.

Ошибка thumbnail не должна уничтожать успешно созданный pack.

---

# 42. Mixed-format packs

Поддерживать pack, где одновременно есть:

```text
TGS
WEBM
WEBP
```

Каждый элемент обрабатывается своим pipeline.

Не конвертировать весь mixed pack в один формат без необходимости.

При создании нового Telegram set использовать mixed-format возможности актуального Bot API.

---

# 43. Максимальный размер Telegram sets

Учитывать текущие Telegram ограничения.

Если пользователь хочет создать обычный Sticker Pack и элементов больше допустимого Telegram maximum:

предложить:

```text
Набор слишком большой для одного стикер-пака.
Разделить его на несколько частей?
```

Кнопки:

```text
Разделить
Отмена
```

Аналогично для Custom Emoji maximum.

Не делить pack автоматически без разрешения пользователя.

---

# 44. Разделение

При согласии:

```text
Pack Name — Part 1
Pack Name — Part 2
...
```

Порядок элементов сохраняется.

Не превышать Telegram maximum на part.

Short names уникальны.

---

# 45. Создание Telegram pack

Использовать максимально эффективный Telegram Bot API flow.

При создании нового set:

сразу передавать максимально допустимое API количество initial stickers одним `createNewStickerSet`.

Остальные добавлять через:

```text
addStickerToSet
```

Не делать лишний:

```text
uploadStickerFile
```

если файл можно безопасно передать непосредственно в create/add operation.

Минимизировать количество Telegram API requests.

---

# 46. Flood control Telegram

Telegram Sticker API имеет rate/flood limits, часть которых не публикуется как фиксированная константа.

НЕ считать слух:

```text
8 emoji / 4 минуты
```

гарантированным официальным законом.

Но архитектура обязана переживать такие ограничения.

Создать:

```text
TelegramStickerRateController
```

При:

```text
429 Too Many Requests
```

читать:

```text
retry_after
```

и автоматически ждать именно указанное Telegram время.

После ожидания продолжать с того же элемента.

Не перезапускать всю задачу.

Ожидание должно быть cancellation-aware.

---

# 47. Экспериментальный limiter 8/240

Добавить конфигурацию:

```env
TELEGRAM_STICKER_CONSERVATIVE_LIMIT_ENABLED=false
TELEGRAM_STICKER_CONSERVATIVE_REQUESTS=8
TELEGRAM_STICKER_CONSERVATIVE_WINDOW_SECONDS=240
```

По умолчанию полагаться на:

```text
batch requests
+
429 retry_after
```

Но через admin/settings должна быть возможность включить консервативный режим `8 requests / 240 seconds`, если реальное тестирование покажет, что Telegram действительно применяет подобный hidden limit к bot token.

Не путать:

```text
API request
```

и:

```text
emoji item
```

Собирать обезличенную агрегированную статистику Telegram 429.

---

# 48. Status во время обработки

Не спамить пользователя.

Использовать одно редактируемое status message.

Пример:

```text
Перекрашиваю набор…
42 / 200
```

При переходе к Telegram upload:

```text
Набор готов.
Загружаю элементы в Telegram…
```

Если Telegram вернул flood wait:

```text
Telegram временно ограничил скорость добавления элементов.
Загрузка продолжится автоматически.
```

Не показывать обычному пользователю:

```text
HTTP 429
retry_after
FloodWait
API method names
```

---

# 49. Частота progress updates

Не делать edit message после каждого элемента.

Ограничить updates:

```text
не чаще одного раза примерно в 1.5–2 секунды
```

или при заметном изменении progress.

Это уменьшает Telegram API traffic.

---

# 50. Ошибки отдельных элементов

Если из 100 элементов один сломан:

1. попытаться обработать;
2. выполнить безопасный retry;
3. если возможно — оптимизировать;
4. если всё равно невозможно — пропустить;
5. продолжить остальные.

В конце:

```text
Готово: 99 / 100
Не удалось обработать: 1
```

Кнопка:

```text
Показать ошибки
```

Ошибки должны содержать:

```text
номер элемента
причину
```

но не server stack trace.

Не отменять весь pack из-за одного плохого элемента, кроме ситуации, когда без этого невозможно создать output вообще.

---

# 51. Validation output

Каждый файл перед отправкой Telegram обязательно валидируется.

Проверять:

```text
format
dimensions
file size
duration
FPS
codec
audio
alpha
TGS validity
```

Если возможно безопасно исправить — исправлять автоматически.

---

# 52. Оптимизация TGS

После recolor:

```text
compact JSON
gzip
check size
```

Не добавлять пробелы/indentation.

Если output больше Telegram limit:

попытаться безопасно уменьшить сериализацию без изменения animation semantics.

Не удалять animation data случайным образом.

Если корректно оптимизировать невозможно — вернуть ошибку конкретного элемента.

---

# 53. Оптимизация WEBM

Если WEBM превышает Telegram maximum:

итеративно уменьшать output size через:

```text
VP9 quality / bitrate / CRF
```

Не уменьшать dimensions ниже Telegram-required target.

Не ухудшать качество больше необходимого.

Если даже после разумного количества попыток невозможно получить валидный файл:

отметить элемент ошибочным.

---

# 54. ZIP input

Поддерживать ZIP.

Из-за стандартного Telegram Bot API установить безопасный default:

```text
MAX_INPUT_DOWNLOAD = 19 MiB
```

Чтобы не упираться точно в границу Telegram.

ZIP security:

```text
max extracted files = 200
max total extracted size = 128 MiB
max compression ratio = 100x
nested archives = запрещены
symlinks = запрещены
absolute paths = запрещены
../ traversal = запрещён
```

Разрешённые файлы:

```text
.tgs
.webm
.webp
.png
```

Игнорировать системные мусорные файлы вроде:

```text
.DS_Store
Thumbs.db
```

Не выполнять никакие файлы.

---

# 55. ZIP output

Структура:

```text
PackName/
├── tgs/
│   ├── 001.tgs
│   └── ...
├── webm/
│   ├── 001.webm
│   └── ...
├── webp/
├── png/
└── info.txt
```

Если безопасное исходное filename реально известно — можно сохранить его.

Если нет:

```text
001.tgs
002.tgs
003.webm
```

Сохранять исходный порядок через numeric prefix.

Filename обязательно sanitize.

---

# 56. info.txt

Не помещать туда персональные данные.

Допустимо:

```text
Source pack title
Selected color
Processing mode
File count
Generated timestamp
```

Нельзя:

```text
telegram user id
username
chat id
```

---

# 57. Большой output ZIP

При стандартном Telegram Bot API не пытаться отправить огромный единый архив.

Установить безопасный output part limit примерно:

```text
45 MiB
```

Если ZIP больше:

автоматически разделить на:

```text
PackName_part01.zip
PackName_part02.zip
```

Не превышать Telegram upload boundary.

---

# 58. Кнопка «Перекрасить ещё»

После успешного результата обязательно:

```text
Перекрасить ещё
```

Она сбрасывает предыдущий runtime state и возвращает пользователя к начальному сценарию.

Старые temp files уже должны быть удалены.

---

# 59. Команды

Пользовательские команды:

```text
/start
/help
/colors
/language
/cancel
/privacy
```

Администраторская:

```text
/admin
```

`/history` НЕ создавать.

---

# 60. /start

Интерфейс минималистичный.

Пример смысла:

```text
Отправьте стикер, Custom Emoji, Unicode Emoji, файл или ссылку на набор.

Я перекрашу его в выбранный цвет и подготовлю результат в нужном формате.
```

Не делать огромный onboarding.

Дополнительные детали находятся в `/help`.

---

# 61. /help

Объяснить:

```text
что можно отправить
какие форматы поддерживаются
как выбрать цвет
что такое Emoji Pack
что такое Sticker Pack
что такое Adaptive
что Unicode emoji превращается в графический результат
как работает ZIP
```

---

# 62. /colors

Показать стандартную палитру и допустимые форматы HEX/RGB.

---

# 63. /language

Поддержать:

```text
Русский
English
```

Обычным пользователям язык НЕ записывать в БД.

Default:

```text
Telegram language_code = ru -> русский
иначе -> English
```

Если пользователь вручную переключил язык:

хранить override только в RAM.

После рестарта допускается возврат к Telegram language.

Для активной job language сохраняется внутри runtime job.

---

# 64. Premium Emoji

Я отдельно передам Codex TXT-файл со всеми ID Premium Emoji.

Обязательно сначала проанализировать этот TXT.

НЕ придумывать Premium Emoji ID самостоятельно.

Создать единый registry:

```python
PremiumEmoji.SUCCESS
PremiumEmoji.ERROR
PremiumEmoji.COLOR
PremiumEmoji.BACK
PremiumEmoji.CANCEL
PremiumEmoji.LOADING
PremiumEmoji.DOWNLOAD
PremiumEmoji.PACK
PremiumEmoji.ADMIN
...
```

Формат registry адаптировать под реально предоставленный TXT.

---

# 65. Premium Emoji в сообщениях

Во всех основных сообщениях использовать Premium Custom Emoji.

Для HTML formatting использовать корректные Telegram custom emoji entities, например через:

```html
<tg-emoji emoji-id="...">🎨</tg-emoji>
```

Fallback Unicode внутри tag должен семантически подходить.

Не разбрасывать raw IDs по всему проекту.

Все ID только через centralized registry.

---

# 66. Premium Emoji в кнопках

Каждая inline/reply button, где Telegram API поддерживает это поле, должна использовать:

```text
icon_custom_emoji_id
```

из TXT registry.

Например:

```text
Подобрать цвет
Продолжить
Другой цвет
Отмена
Emoji Pack
Sticker Pack
ZIP
Файл
Перекрасить ещё
Admin
```

должны иметь Premium Emoji icon.

Button text при этом остаётся чистым текстом.

Если конкретный клиент не отображает custom button icon, кнопка всё равно должна оставаться понятной по тексту.

---

# 66.1. Безопасный fallback Premium Emoji

Полный Premium Emoji UI не должен быть единственной рабочей веткой интерфейса.

Если Telegram API возвращает ошибку, связанную с отсутствием права использовать Custom Emoji в сообщении или кнопке, бот НЕ должен ломать пользовательский сценарий.

В такой ситуации:

1. повторно отправить или отредактировать сообщение без Premium Custom Emoji;
2. убрать `icon_custom_emoji_id` из кнопок;
3. вместо Premium Emoji использовать семантически подходящий обычный Unicode fallback;
4. не менять текст и смысл кнопок;
5. записать только обезличенный warning в технический лог;
6. не показывать пользователю stack trace или техническое описание Telegram API ошибки.

Fallback должен быть централизованным, а не реализован вручную в каждом handler.

Рекомендуется создать единый UI/helper layer, который умеет:

```text
Premium Emoji available
↓
сообщения + кнопки с Premium Emoji

Premium Emoji unavailable / Telegram rejected
↓
тот же интерфейс с обычными Unicode fallback icons
```

Нельзя допускать ситуацию, когда отсутствие Premium Emoji ломает `/start`, `/help`, выбор цвета, preview, создание набора, `/admin` или любой другой основной сценарий.

В README отдельно указать:

```text
Для полного интерфейса с Premium Custom Emoji владелец бота должен соответствовать актуальным требованиям Telegram Bot API для использования Custom Emoji ботом.
Если эти требования не выполнены, бот автоматически продолжает работать с обычными Unicode fallback icons.
```

При реализации обязательно сверить актуальные требования Telegram Bot API к использованию Custom Emoji ботами и не hardcode устаревшие условия.


---

# 67. Parse mode

Централизованно использовать:

```text
HTML
```

Не собирать HTML из пользовательских строк без escaping.

Title, filenames и прочие пользовательские значения обязательно:

```python
html.escape(...)
```

---

# 68. FSM / Job state

Для обычного пользователя можно использовать aiogram MemoryStorage.

Ничего persistent.

Основные состояния:

```text
IDLE
SOURCE_ANALYSIS
AWAITING_COLOR
GENERATING_PREVIEW
AWAITING_PREVIEW_DECISION
AWAITING_OUTPUT_TYPE
AWAITING_PACK_NAME
AWAITING_SPLIT_CONFIRMATION
PROCESSING
PUBLISHING
COMPLETED
CANCELLED
```

Реальную processing job дополнительно держать в `JobManager`, а не запихивать большие objects/files внутрь FSM data.

---

# 69. Job model

Пример runtime структуры:

```text
job_id
user_id
chat_id
language
source_type
source_files
source_metadata
selected_color
adaptive
output_type
pack_title
status
progress
cancel_event
created_at
last_interaction_at
```

Это существует ТОЛЬКО в RAM.

Никакой сериализации на диск.

---

# 70. Обычные пользовательские лимиты

Сделать sliding-window limits.

Все counters обычного пользователя существуют ТОЛЬКО в RAM.

DEFAULT LIMITS:

```text
Активных логических задач одновременно:
1

Burst:
3 новых задачи / 10 минут

Всего:
12 задач / 60 минут

Дневной runtime limit:
40 задач / 24 часа

Большие задачи:
5 / 60 минут
15 / 24 часа

Очень большие задачи:
3 / 60 минут
8 / 24 часа

Тяжёлые WEBM pack-задачи:
3 / 60 минут
8 / 24 часа

Максимум смен цвета одного preview:
15
```

Все окна rolling, а не «с начала часа».

---

# 71. Определение большой задачи

`large job`:

```text
более 50 элементов
ИЛИ
ZIP extracted size > 25 MiB
```

`very large job`:

```text
более 120 элементов
ИЛИ
ZIP extracted size > 75 MiB
```

`heavy WEBM job`:

```text
10 или более WEBM элементов
```

Один одиночный WEBM не считать heavy pack job.

Он учитывается только в обычном total rate limit.

---

# 72. Почему именно такие лимиты

Обычный человек сможет:

```text
5 больших pack в час
```

что является достаточно свободным использованием.

При этом один человек не сможет бесконечно отправлять сотни больших pack.

Главную защиту сервера реализуют НЕ пользовательские quotas, а global scheduler + workers.

---

# 73. Администраторские лимиты

Администраторы НЕ ИМЕЮТ пользовательских rate limits.

Для `owner/admin` НЕ применяются:

```text
3/10min
12/hour
40/day
5 large/hour
15 large/day
3 huge/hour
8 huge/day
WEBM quotas
1 active job
preview color-change quota
```

Администратор может запускать несколько задач.

Админские jobs получают более высокий scheduler priority.

НО:

«без лимитов» не означает возможность физически заставить VPS запустить 100 FFmpeg одновременно.

На админов всё равно распространяются:

```text
Telegram API hard limits
Telegram file format requirements
Telegram flood control
доступная RAM
доступный диск
global worker concurrency
ZIP bomb protection
file parsing security
```

Если global workers заняты, admin job ждёт свободный worker с повышенным приоритетом, а не получает персональный rate-limit error.

---

# 74. Global server scheduler

Не запускать все accepted jobs одновременно.

Создать internal scheduler.

Пользователю НЕ показывать:

```text
Вы №18 в очереди
```

Никаких queue positions.

Просто обработка начинается, когда доступен worker.

---

# 75. Dynamic default workers

Определить:

```python
cpu_count = os.cpu_count() or 2
```

Разумные defaults:

```text
GLOBAL_RUNNING_JOBS:
min(max(cpu_count * 2, 4), 12)

TGS workers:
min(max(cpu_count, 2), 6)

Raster workers:
min(max(cpu_count // 2, 2), 4)

WEBM workers:
1 при <= 4 CPU threads
2 при > 4 CPU threads

Archive workers:
2

Preview workers:
4
```

Не плодить большое количество Python threads/processes.

WEBM обязательно ограничивать отдельным semaphore.

---

# 76. WEBM нагрузка

На типичном небольшом VPS одновременно должно кодироваться не больше:

```text
1–2 WEBM
```

даже если принято 20 задач.

Остальные ждут internal worker.

Это критическое требование.

---

# 77. CPU-bound операции

Не блокировать asyncio event loop.

CPU-heavy:

```text
image processing
TGS processing большого pack
frame recolor
archive work
```

запускать через подходящий bounded executor / `asyncio.to_thread`, если это действительно полезно.

FFmpeg запускается как async subprocess.

---

# 78. Global pending jobs

Для обычных пользователей установить soft global pending ceiling:

```text
30
```

Если сервер полностью забит и уже накопилось слишком много accepted regular jobs:

вернуть:

```text
Сервис сейчас сильно загружен. Попробуйте немного позже.
```

Без номера очереди.

Admin tasks имеют priority и не блокируются пользовательским pending quota, кроме аварийного resource safety режима.

---

# 79. Resource safety

Перед запуском тяжёлой job проверять `psutil`.

Если:

```text
available RAM < 768 MiB
```

или:

```text
available RAM < 10%
```

не запускать новый тяжёлый worker, пока RAM не освободится.

Если disk free:

```text
< 2 GiB
```

или:

```text
< 10%
```

не принимать новые большие file-processing jobs.

Это не пользовательский rate limit.

Это аварийная защита VPS и действует даже на администратора.

---

# 80. Cancel

Команда:

```text
/cancel
```

и inline:

```text
Отмена
```

должны реально отменять задачу.

Использовать:

```text
asyncio.Event / cancellation token
```

Каждый processing loop периодически проверяет cancellation.

Если работает FFmpeg:

```text
terminate
↓
wait timeout
↓
kill если необходимо
```

После отмены:

```text
очистить temp
освободить semaphores
удалить runtime state
```

---

# 81. Отмена во время Telegram publishing

Если пользователь отменяет задачу после того, как новый pack уже начал создаваться:

best-effort удалить наборы, созданные этой конкретной job, если текущий Telegram Bot API позволяет это сделать.

Если cleanup Telegram pack не удался:

не скрывать проблему.

Сообщить, что часть набора могла уже быть создана.

Никогда не трогать исходный пользовательский pack.

---

# 82. Исходные pack никогда не изменяются

Даже если исходный набор создан этим же ботом:

в обычном recolor workflow всегда создаётся НОВАЯ копия.

Не модифицировать исходный pack.

---

# 83. Admin panel

Вся admin panel только внутри Telegram.

Никакой web admin panel.

Основной `/admin` dashboard:

```text
Статус бота
Uptime

Active jobs
Pending jobs

TGS workers
Raster workers
WEBM workers

CPU
RAM
Disk
Temp size

Processed today
Successful
Failed

Packs created

Telegram 429 today
Last retry_after
Telegram publishing status
```

Использовать Premium Emoji.

---

# 84. Admin panel buttons

Минимум:

```text
Обновить
Активные задачи
Нагрузка
Статистика
Telegram API
Лимиты
Администраторы
Ошибки
Очистить Temp
Режим обслуживания
```

---

# 85. Active jobs в админке

Показывать:

```text
Job #A8421E
Type: TGS Pack
Items: 84
Progress: 42 / 84
State: Processing
Age: 00:01:32
```

НЕ показывать:

```text
Telegram user ID
username
chat id
```

Кнопка:

```text
Остановить задачу
```

может внутри RAM найти job и отменить её.

---

# 86. Temporary runtime block

Если необходимо остановить злоумышленника без persistent user storage:

при активной job администратор может выбрать:

```text
Остановить и временно ограничить
```

Внутри RAM пользовательский ID добавляется во временный runtime deny-set.

Не отображать его admin'у.

После рестарта блокировка исчезает.

Permanent blacklist обычных пользователей НЕ создавать.

---

# 87. Admin management

В `/admin -> Администраторы`:

```text
Owner
Admins
```

Показывать stored admin ID.

Owner может:

```text
Добавить
Удалить
```

Нельзя удалить owner.

Обычный admin не должен иметь возможности удалить owner.

---

# 88. Настройка пользовательских лимитов

Значения rate limits не hardcode в 20 разных местах.

Создать centralized `LimitsConfig`.

Default значения выше.

Дополнительно сохранять изменяемые non-personal settings в SQLite `app_settings`.

Через admin panel owner может менять:

```text
jobs/10min
jobs/hour
jobs/day
large/hour
large/day
huge/hour
huge/day
heavy WEBM/hour
heavy WEBM/day
```

Изменения применяются к новым проверкам сразу.

---

# 89. Maintenance Mode

Через `/admin`:

```text
Режим обслуживания: ON/OFF
```

При ON:

обычные новые user jobs не принимаются.

Сообщение:

```text
Сервис временно находится на техническом обслуживании.
Попробуйте позже.
```

Администраторы продолжают пользоваться ботом без ограничений.

---

# 90. Stats

Persistent statistics только aggregate.

Не создавать:

```text
user_stats
```

Пример:

```text
statistics_daily
date PRIMARY KEY
jobs_total
jobs_success
jobs_failed
items_processed
tgs_processed
webm_processed
raster_processed
emoji_packs_created
sticker_packs_created
telegram_429
processing_ms_total
```

---

# 91. Privacy command

`/privacy` должен честно объяснять:

* обычные Telegram ID не сохраняются постоянно;
* username/name не сохраняются;
* история запросов не сохраняется;
* отправленные файлы временные;
* временные файлы удаляются после завершения/отмены;
* runtime identifiers используются только для выполнения текущей операции и rate limiting;
* техническая статистика обезличена;
* данные администраторов сохраняются для контроля доступа к административной панели.

Не писать:

```text
Бот вообще не обрабатывает персональные данные
```

Это технически неверно.

---

# 92. Ограничения файлов

Safe defaults:

```text
Input Telegram download:
19 MiB

ZIP extracted:
128 MiB

ZIP files:
200

Media group files:
50

Total logical items per one input:
200

Raster max dimension:
4096x4096

Raster max pixels:
16 megapixels

TGS max decompressed JSON:
5 MiB
```

Если Telegram pack содержит допустимое количество элементов — не ограничивать его ниже Telegram maximum только ради искусственного server limit.

---

# 93. Security

Обязательно:

```text
ZIP Slip protection
symlink protection
path sanitization
size limits
decompression bomb protection
image pixel limits
TGS decompression limit
FFmpeg timeout
no shell=True
strict URL parsing
HTML escaping
callback ownership validation
```

Callback должен включать random job identifier, но перед выполнением действия обязательно проверить, что callback sender является владельцем runtime job либо администратором с соответствующим действием.

---

# 94. Не доверять расширению файла

Определять реальные типы по:

```text
header/signature/content
```

где возможно.

Например:

TGS должен реально быть gzip с корректным JSON.

PNG должен иметь PNG signature.

WEBP должен соответствовать RIFF/WEBP.

WEBM проверяется через FFmpeg probing.

Не принимать `virus.exe`, переименованный в `.png`.

---

# 95. Telegram private chat

Основной бот предназначен для private chats.

Color Picker WebApp и основной workflow работают именно там.

Не запускать file-processing workflow в группах.

В группе предпочтительно либо молча игнорировать обычные сообщения, либо отправлять минимальное указание перейти в private chat только если пользователь явно вызвал `/start`.

Не создавать spam в группах.

---

# 96. Ошибки интерфейса

Обычный пользователь получает человеческие ошибки:

```text
Формат не поддерживается
Не удалось открыть TGS
Файл слишком большой
Видео длиннее допустимого
Архив повреждён
Telegram временно ограничил создание набора
```

Не показывать:

```text
traceback
Python exception
absolute filesystem path
SQL
FFmpeg internal command
bot token
```

---

# 97. Ошибки для администратора

В `/admin -> Ошибки` показывать технически полезную, но обезличенную информацию:

```text
job_id
time
component
error_type
sanitized message
```

Без `user_id`.

Persistent error log также не должен позволять определить пользователя.

---

# 98. Повторная обработка

Кнопка `Другой цвет` переиспользует скачанный source.

Нельзя повторно скачивать:

```text
200 Telegram files
```

только потому, что пользователь поменял цвет preview.

Это уменьшает:

```text
API traffic
CPU
диск
время
```

---

# 99. Кэш

Не делать persistent cache пользовательских files.

Допустим только cache внутри одной active job.

После job уничтожить.

Общий persistent Telegram file cache не создавать.

---

# 100. Telegram file IDs

Не сохранять Telegram file_id обычного пользователя на диск.

Они могут жить внутри runtime job.

После завершения удаляются вместе с объектом job.

---

# 101. Testing

Написать нормальные tests.

Минимум unit tests:

```text
HEX parsing
short HEX parsing
RGB parsing
invalid RGB
color normalization

OKLab conversion
alpha preservation
black recolor
white recolor
colored recolor
gradient preservation

TGS gzip load/save
static TGS colors
animated TGS colors
gradient TGS colors
unknown fields preserved
corrupted TGS rejection

ZIP traversal
ZIP symlink
ZIP bomb-like ratio
ZIP max count

short name generation
short name length
short name suffix

user rate limiter
rolling windows
admin bypass

one active regular job
multiple admin jobs

FSM cancellation
timeout cleanup

429 retry_after
cancellation during flood wait

/admin silent for regular user

database contains admin
database does not create regular user record
```

---

# 102. Integration tests

Mock Telegram API.

Проверить workflow:

```text
single sticker
custom emoji
pack link
TGS
PNG
ZIP
Unicode emoji
```

Pack workflow:

```text
source
↓
color
↓
preview
↓
continue
↓
output
↓
name
↓
process
↓
publish
↓
cleanup
```

---

# 103. 429 integration test

Сымитировать:

```text
addStickerToSet
↓
429 retry_after=2
↓
wait
↓
retry
↓
success
```

Убедиться, что:

```text
job не потеряна
progress не сброшен
элементы не дублируются
```

---

# 104. Cleanup tests

После:

```text
success
failure
cancel
timeout
```

job directory должна отсутствовать.

FSM очищен.

Runtime limiter корректно сохраняет только временный rate window, если задача закончилась.

---

# 105. Privacy test

После обработки обычного пользователя проверить SQLite.

Telegram ID пользователя НЕ должен появиться ни в одной persistent таблице.

Также проверить обычные application logs.

ID пользователя не должен встречаться.

---

# 106. README

README должен подробно объяснять:

```text
требования
Python versions
создание .venv
установку dependencies
.env
запуск
Premium Emoji TXT
Unicode Emoji font
Windows
Linux VPS
структуру проекта
privacy model
Telegram limits
FFmpeg
tests
```

---

# 107. .env.example

Минимум:

```env
BOT_TOKEN=
OWNER_ID=

COLOR_PICKER_URL=https://htmlcolorcodes.com/color-picker/

DATABASE_PATH=data/bot.db
TEMP_ROOT=temp/jobs

EMOJI_FONT_PATH=

LOG_LEVEL=INFO

TELEGRAM_STICKER_CONSERVATIVE_LIMIT_ENABLED=false
TELEGRAM_STICKER_CONSERVATIVE_REQUESTS=8
TELEGRAM_STICKER_CONSERVATIVE_WINDOW_SECONDS=240
```

Добавить остальные реально необходимые параметры.

---

# 108. .gitignore

Обязательно:

```text
.venv/
.env
__pycache__/
*.pyc

data/*.db
data/*.db-shm
data/*.db-wal

temp/
logs/

.pytest_cache/
.mypy_cache/
.ruff_cache/
```

Не коммитить bot token.

---

# 109. Database

Использовать SQLite + aiosqlite.

Включить:

```text
WAL
foreign_keys
busy_timeout
```

Если оправдано.

Миграции сделать простыми и надёжными.

Не подключать PostgreSQL для такой маленькой admin/settings database без необходимости.

---

# 110. Graceful shutdown

При остановке:

1. перестать принимать новые jobs;
2. пометить shutdown;
3. отменить processing tasks;
4. terminate FFmpeg;
5. cleanup temp;
6. закрыть SQLite;
7. закрыть Bot session.

Не оставлять orphan FFmpeg processes.

---

# 111. Startup

При startup:

1. проверить Python version;
2. загрузить config;
3. проверить BOT_TOKEN;
4. инициализировать SQLite;
5. создать owner;
6. загрузить Premium Emoji registry;
7. проверить FFmpeg;
8. проверить temp directories;
9. очистить stale temp;
10. запустить scheduler;
11. запустить polling.

---

# 112. Premium Emoji TXT validation

Если предоставленный TXT не содержит ID, необходимого для конкретной semantic action:

НЕ придумывать ID.

Использовать:

```text
обычный fallback icon
```

и записать warning без персональных данных.

Результат проверки Premium Emoji registry хранить только как обезличенное runtime-состояние.

Не отправлять owner/admin автоматические сообщения при каждом startup.

Добавить просмотр диагностики Premium Emoji по запросу через `/admin`, например:

```text
/admin
↓
Диагностика
↓
Premium Emoji

Registry loaded: ...
Mappings available: ...
Fallback mode: ON/OFF
```

Диагностика не должна содержать персональные данные пользователей.

---

# 113. UX

Интерфейс должен быть:

```text
минималистичным
аккуратным
быстрым
без технического мусора
без лишних сообщений
```

Предпочитать:

```text
edit_message_text
edit_message_reply_markup
```

вместо создания нового сообщения на каждом шаге.

Но media preview можно отправлять отдельным сообщением.

После завершения старые control keyboards желательно деактивировать, чтобы пользователь случайно не нажал кнопку старой job.

---

# 114. Основной workflow обычного pack

Итоговый сценарий:

```text
Пользователь отправляет pack
↓
Bot анализирует
↓
Одно сообщение:
название + тип + количество + форматы + colors
↓
Пользователь отправляет HEX/RGB
↓
Перекрашивается первый item
↓
Preview
↓
Продолжить / Другой цвет / Отмена
↓
Выбор:
Emoji Pack / Sticker Pack / ZIP
↓
Если pack:
ввод названия
↓
Если превышен Telegram limit:
спросить про split
↓
Обработка
↓
Validation
↓
Optimization
↓
Telegram publishing / ZIP
↓
Result
↓
Перекрасить ещё
↓
cleanup
```

---

# 115. Workflow single item

```text
Пользователь отправляет item
↓
Source information + colors
↓
Color
↓
Emoji Pack / Sticker Pack / File / ZIP
↓
Если pack -> название
↓
Processing
↓
Result
↓
Перекрасить ещё
```

Без отдельного preview approval.

---

# 116. Adaptive workflow

```text
Source
↓
Сделать Adaptive
↓
Preview / explanation
↓
Продолжить
↓
Название Emoji Pack
↓
needs_repainting=True
↓
Create Custom Emoji Pack
↓
Result
```

---

# 117. Result message для pack

Показывать примерно:

```text
Набор готов

Название: ...
Тип: Emoji Pack
Элементов: 84
Цвет: #8B5CF6
```

Кнопки:

```text
Добавить набор
Перекрасить ещё
```

Для split:

показать ссылки на каждую part.

---

# 118. Telegram-created URL

Для:

```text
Sticker Pack
```

формировать корректный `t.me/addstickers/...`.

Для:

```text
Custom Emoji Pack
```

формировать корректный `t.me/addemoji/...`.

Не путать ссылки.

---

# 119. Сохранение порядка

Order новых items должен точно соответствовать source pack.

Если отдельный item пропущен из-за ошибки:

оставшиеся сохраняют относительный порядок.

В error report указать source index.

---

# 120. Performance

Не оптимизировать преждевременно, но не писать заведомо медленный код.

Обязательно:

```text
NumPy vectorization
streaming WEBM
bounded concurrency
no unbounded gather()
no 200 simultaneous FFmpeg
no whole-video frame list in RAM
compact TGS JSON
```

---

# 121. Memory

Большой pack не должен одновременно хранить десятки полностью декодированных изображений/видео в RAM.

Source files находятся на disk temp.

Обрабатывать ограниченными batches или item-by-item.

---

# 122. Disk

Удалять intermediate files элемента, если они больше не нужны.

Не хранить одновременно лишние копии:

```text
source
decoded
recolored
optimized_v1
optimized_v2
optimized_v3
```

без cleanup.

---

# 123. Telegram batching

Использовать максимум initial stickers, который разрешает текущий `createNewStickerSet`.

Не hardcode это значение в пяти местах.

Создать Telegram constants/config layer.

Если Bot API изменит maximum, исправление должно требовать изменения только в одном месте.

---

# 124. Telegram limits

Все внешние Telegram ограничения держать centralized.

Например:

```text
TELEGRAM_CUSTOM_EMOJI_SET_MAX
TELEGRAM_REGULAR_STICKER_SET_MAX
TELEGRAM_CREATE_INITIAL_MAX
TELEGRAM_TGS_MAX_BYTES
TELEGRAM_WEBM_MAX_BYTES
...
```

При возможности при обновлении проекта сверять их с официальной документацией.

---

# 125. Код

Требования:

```text
type hints
dataclasses / Pydantic where уместно
async/await
маленькие функции
dependency separation
нет circular imports
нет global mutable state без manager
```

Runtime managers допустимы через explicit application context/dependency injection.

---

# 126. Formatting / lint

Проект должен проходить:

```text
ruff check
mypy
pytest
```

Настроить разумные правила.

Не отключать type checking глобальным:

```text
ignore_errors = true
```

ради зелёного результата.

---

# 127. Финальная проверка

Перед завершением работы:

1. установить dependencies только в `.venv`;
2. проверить interpreter `.venv`;
3. запустить lint;
4. запустить tests;
5. проверить импорт приложения;
6. проверить startup без реального токена настолько, насколько возможно;
7. проверить SQLite schema;
8. проверить отсутствие пользовательской таблицы;
9. проверить `.gitignore`;
10. проверить отсутствие secrets;
11. проверить Premium Emoji registry;
12. проверить FFmpeg discovery.

---

# 128. Что нельзя делать

Категорически нельзя:

```text
создавать persistent users table
сохранять ID обычных пользователей
сохранять историю
сохранять пользовательские файлы после job
логировать raw Telegram Updates
ставить libraries global
использовать shell=True
запускать unlimited WEBM
показывать /admin обычному пользователю
изменять исходные packs
пытаться WEBM -> TGS
тупо заливать весь рисунок одним RGB
игнорировать alpha
игнорировать Telegram 429
hardcode sleep(240) после каждого 8-го emoji
создавать web admin panel
```

---

# 129. Что должно получиться

В результате нужен законченный Telegram bot:

* Python >=3.12;
* локально работает с Python 3.14.7;
* все Python dependencies в `.venv`;
* aiogram 3.x;
* RU/EN;
* Premium Emoji во всём интерфейсе;
* TGS/WEBM/WEBP/PNG/ZIP;
* Unicode Emoji;
* sticker pack links;
* emoji pack links;
* mixed packs;
* качественная perceptual recolor;
* сохранение shadows/highlights/alpha/gradients;
* Adaptive Emoji;
* preview;
* Emoji Pack;
* Sticker Pack;
* File;
* ZIP;
* Telegram flood control;
* intelligent resource scheduler;
* RAM-only ordinary user limits;
* unlimited admins на уровне пользовательских quotas;
* SQLite только для admins/settings/aggregate stats;
* полноценная `/admin`;
* полное удаление временных файлов;
* отсутствие persistent пользовательской истории;
* production-grade error handling;
* tests;
* README.

Не ограничивайся написанием архитектурного описания.

Реально создай весь проект, установи зависимости в `.venv`, реализуй код, запусти тесты и исправь обнаруженные ошибки.

Если в существующем репозитории уже есть код — сначала внимательно проанализируй его и аккуратно интегрируй/рефакторни существующую реализацию вместо бессмысленного переписывания работающих частей.

Если рядом с задачей предоставлен TXT с Premium Emoji ID — обязательно прочитай его до создания интерфейса и используй реальные ID оттуда.