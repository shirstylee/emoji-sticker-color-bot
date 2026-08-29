<p align="center">
  <img src="assets/images/readme_banner.png" alt="Emoji & Sticker Color Bot banner" width="100%" />
</p>

<h1 align="center">🎨 Emoji & Sticker Color Bot</h1>

<p align="center">
  Перцептивная перекраска Telegram Emoji, стикеров, наборов и файлов<br />
  с сохранением света, теней, контуров, градиентов и прозрачности
</p>

<p align="center">
  <img alt="Python 3.12+" src="https://img.shields.io/badge/Python-3.12%2B-3776AB?style=flat-square&logo=python&logoColor=white" />
  <img alt="aiogram 3.31" src="https://img.shields.io/badge/aiogram-3.31-26A5E4?style=flat-square&logo=telegram&logoColor=white" />
  <img alt="Telegram Bot API 10.3" src="https://img.shields.io/badge/Bot_API-10.3-26A5E4?style=flat-square&logo=telegram&logoColor=white" />
  <img alt="Tests: 121 passed" src="https://img.shields.io/badge/tests-121%20passed-2EA44F?style=flat-square" />
  <img alt="Interface: Russian, admin RU and EN" src="https://img.shields.io/badge/interface-RU%20%7C%20admin%20RU%20%2F%20EN-7C3AED?style=flat-square" />
</p>

---

## 🌈 Что это за бот

**Emoji & Sticker Color Bot** перекрашивает отдельные Custom Emoji и стикеры, целые Telegram-наборы, изображения, анимации и архивы в выбранный цвет.

Цвет меняется в перцептивном пространстве **OKLab**: бот сохраняет яркость исходника, светотень, фактуру, контуры, градиенты и alpha-канал, поэтому результат не выглядит как плоская цветная заливка.

Поддерживаются:

- 🖼️ статические стикеры и изображения — `WEBP`, `PNG`;
- ✨ анимированные стикеры — `TGS`;
- 🎬 видеостикеры — `WEBM`;
- 📦 наборы и пакетная обработка — Telegram Pack, media group, `ZIP`;
- 😀 составные Unicode Emoji и Adaptive Emoji;
- 🌍 русский интерфейс для пользователей и переключение русского/английского для администраторов.

---

## ✨ Возможности

- 🎨 **Умная перекраска** — сохранение исходной светимости и прозрачности через linear sRGB и OKLab.
- 🎚️ **Три уровня интенсивности** — бережная, обычная и насыщенная перекраска с мгновенным обновлением предпросмотра.
- 🧩 **Один элемент или целый набор** — поддержка стикеров, Custom Emoji, pack-ссылок, файлов, архивов и альбомов.
- 🌀 **Нативные форматы Telegram** — безопасная работа с TGS, WEBM, WEBP и PNG без подмены форматов.
- 📦 **Гибкий результат** — одиночный результат сразу приходит как стикер; его можно добавить в новый или существующий набор. Для целых наборов доступны Emoji Pack, Sticker Pack, добавление в существующий набор и ZIP.
- 🛡️ **Надёжная публикация** — при несовместимости прямого вложения бот загружает файл через `uploadStickerFile`, повторяет операцию по `file_id` и продолжает после точного Telegram `retry_after`.
- 🌈 **Любой цвет** — HEX, RGB, короткие HEX-значения и названия базовых цветов.
- 🌓 **Контрастный Adaptive** — светлые и тёмные детали переносятся в alpha-маску, а уже Adaptive-источники получают насыщенный точный цвет.
- 💎 **Premium Emoji в интерфейсе** — используются реальные Custom Emoji ID из `Main.txt` с автоматическим Unicode fallback.
- 🚦 **Контроль нагрузки** — очередь задач, отдельные лимиты тяжёлых операций, живой таймер Telegram `retry_after` и отмена без перезапуска job.
- 🧹 **Автоочистка** — временные файлы удаляются после успеха, ошибки, отмены, таймаута и при следующем запуске.
- 🔐 **Без сохранения истории пользователей** — данные обычных пользователей, тексты и файлы не сохраняются в базе.
- 🤖 **Telegram-only админ-панель** — русская панель мониторинга; язык, настройки и созданные администратором наборы сохраняются между перезапусками.

---

## 🔄 Как это работает

1. 📤 Отправьте боту стикер, Custom Emoji, файл, media group, ZIP или ссылку на Telegram-набор.
2. 🎯 Откройте HTML Color Picker или нажмите на моноширный код, затем отправьте боту скопированный HEX/RGB.
3. 🎚️ Выберите бережную, обычную или насыщенную интенсивность; для набора бот обновит предпросмотр.
4. 📦 Создайте новый набор, добавьте результат в совместимый существующий набор или получите ZIP.
5. ✅ Получите готовый результат. Исходный набор меняется только при явном выборе «Добавить в существующий набор».

Если большой набор не помещается в один Telegram pack, бот сначала запросит согласие на разбиение.

---

## 🧠 Обработка форматов

| Формат | Что делает бот |
|---|---|
| `PNG` / `WEBP` | OKLab/NumPy, сохранение alpha и автоматический щадящий режим для фотографической текстуры |
| `TGS` | Безопасный разбор gzip JSON, перекраска fill/stroke, animated colors и gradients с сохранением неизвестных Lottie-полей |
| `WEBM` | Потоковый FFmpeg decode → auto texture-aware recolor → VP9/alpha encode без накопления кадров в RAM |
| `ZIP` | Проверка traversal, абсолютных путей, symlink, nested archives, размера, числа файлов и compression ratio |
| Unicode Emoji | Проверка одного grapheme cluster и локальный рендер системным Color Emoji font |

Статический стикер получает прозрачный canvas `512×512`, Custom Emoji — `100×100`, а TGS сохраняет `512×512`. WEBM кодируется в VP9 без аудио, не более 30 FPS; бот оставляет небольшой запас до серверного предела в 3 секунды, чтобы контейнерное округление не вызвало `STICKER_VIDEO_LONG`.

---

## 🏗️ Архитектура

```text
app/
├── handlers/       # Telegram-команды, пользовательский flow и /admin
├── keyboards/      # централизованные Premium Emoji-aware клавиатуры
├── services/       # jobs, источники, очередь, лимиты, архивы, публикация
├── recolor/        # OKLab raster, Lottie/TGS и streaming WEBM
├── validators/     # сигнатуры и безопасная проверка медиа/ZIP
├── database/       # ограниченная SQLite-схема служебных данных
├── models/         # RAM-only jobs/sources и лимиты
├── i18n/           # русская и английская локализация
├── config.py       # окружение и динамические настройки workers
├── constants.py    # лимиты Telegram Bot API и медиа
└── main.py         # диагностика, polling и graceful shutdown
```

CPU-heavy операции выполняются через ограниченный `asyncio.to_thread`, а WEBM использует отдельный semaphore. Планировщик даёт админским задачам повышенный приоритет и приостанавливает новые тяжёлые операции при нехватке RAM или места на диске.

---

## 🛡️ Безопасность

- 🔑 секреты загружаются из локального `.env`, который исключён из Git;
- 🤫 неавторизованный `/admin` не отвечает и не создаёт запись в логах;
- 🚫 архивы защищены от path traversal, symlink и zip bombs;
- 📏 размеры, длительность, разрешение и сигнатуры медиа проверяются до тяжёлой обработки;
- 🧯 временные данные изолированы по случайному job ID и гарантированно очищаются;
- ⏱️ rate limits и Telegram 429 обрабатываются без потери состояния задачи.

---

## 🧰 Технологии

| Область | Решение |
|---|---|
| Telegram | `aiogram 3.31.0`, Telegram Bot API 10.3 |
| Runtime | Python 3.12+, `asyncio`, `pydantic-settings` |
| Изображения | NumPy, Pillow, linear sRGB, OKLab |
| Анимация | Lottie/TGS, `imageio-ffmpeg`, VP9/alpha |
| Хранилище | SQLite / `aiosqlite`, агрегаты и разрешённые служебные данные администраторов |
| Валидация | сигнатуры файлов, Pillow, FFmpeg probe, safe ZIP extraction |
| Качество | Ruff, mypy, pytest |
| Развёртывание | `.venv`, `.env`, hardened systemd unit |

---

## 🚀 Быстрый запуск

### Windows

Все Python-зависимости устанавливаются только в проектную `.venv`:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.venv\Scripts\python.exe -m pip install -r requirements.lock
Copy-Item .env.example .env
```

Заполните `.env`, затем запустите диагностику и бота:

```powershell
.venv\Scripts\python.exe -m app.main --check
.venv\Scripts\python.exe -m app.main
```

### Linux / VPS

Windows-окружение нельзя переносить на Linux — создайте `.venv` заново:

```bash
cd /opt/emoji-sticker-color-bot
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -r requirements.lock
cp .env.example .env
.venv/bin/python -m app.main --check
.venv/bin/python -m app.main
```

Готовый hardened unit находится в `deploy/emoji-sticker-color-bot.service`:

```bash
sudo cp deploy/emoji-sticker-color-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now emoji-sticker-color-bot
```

---

## ⚙️ Конфигурация

Минимальный `.env`:

```env
BOT_TOKEN=123456:replace_me
OWNER_ID=123456789
```

Основные пути:

```env
DATABASE_PATH=data/bot.db
TEMP_ROOT=temp/jobs
PREMIUM_EMOJI_PATH=Main.txt
EMOJI_FONT_PATH=
LOG_DIR=logs
COLOR_PICKER_URL=https://htmlcolorcodes.com/color-picker/
```

Полный список лимитов и настроек с безопасными значениями по умолчанию находится в `.env.example`.
Публикация наборов по умолчанию использует отдельное безопасное окно: 8 изменений
за 240 секунд. Оно не применяется к предпросмотрам, одиночной перекраске и обычной
отправке сообщений; серверный `retry_after` всегда имеет приоритет. Одиночные PNG/WEBP
используют отдельный высокий пользовательский лимит `30 / 10 минут`, `120 / час`,
`500 / сутки`; TGS, WEBM и групповые источники остаются в строгом окне. Перед выбором
цвета бот декодирует и проверяет каждый файл, а при публикации набора показывает
динамическое примерное время готовности.

---

## 💎 Premium Emoji

При запуске бот полностью читает `Main.txt` и принимает только реальные 16–20-значные ID из правой части строк. Семантические действия (`SUCCESS`, `COLOR`, `CANCEL`, `PACK`, `ADMIN` и другие) сопоставляются по описанию — raw ID не дублируются в handlers и клавиатурах.

Если нужного ID нет или Telegram отклоняет `custom_emoji` / `icon_custom_emoji_id`, интерфейс автоматически повторяется с обычным Unicode Emoji. Диагностика доступна в `/admin → Premium Emoji`.

---

## 🤖 Команды

Пользовательские команды:

- `/start` — начать работу;
- `/help` — инструкция и поддерживаемые форматы;
- `/colors` — примеры цветов;
- `/cancel` — отменить текущую задачу;

Обычным пользователям доступен только русский интерфейс. Для owner и назначенных администраторов дополнительно доступны `/language` (выбор сохраняется), «Мои наборы» с постоянной историей созданных паков и русская `/admin`: состояние сервиса, задачи, нагрузка, статистика, Telegram API, лимиты, ошибки, режим обслуживания, Premium Emoji и управление администраторами. Администратор может запускать несколько логических задач одновременно; фактический параллелизм ограничивается только безопасными ресурсными worker-лимитами сервера.

---

## ✅ Проверка проекта

Offline-диагностика не требует Bot Token:

```powershell
.venv\Scripts\python.exe -m app.main --check
```

Полный quality gate:

```powershell
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy app
.venv\Scripts\python.exe -m pytest
```

Тесты покрывают парсинг цветов, OKLab/alpha/contrast, Adaptive-маски, нормализацию TGS timing, WEBM, ZIP security, лимиты, параллельные админские задачи, живой Telegram 429 countdown, миграцию SQLite, silent `/admin` и ключевые workflow-компоненты.

---

<p align="center">
  <strong>🎨 Один цвет — для любого Emoji, стикера или набора ✨</strong>
</p>
