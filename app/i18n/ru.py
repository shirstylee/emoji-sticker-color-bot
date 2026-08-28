"""Russian messages."""

RU: dict[str, str] = {
    "start": (
        "{icon} <b>Emoji &amp; Sticker Color Bot</b>\n\n"
        "Отправьте стикер, Custom Emoji, Unicode Emoji, файл или ссылку на набор.\n"
        "Я перекрашу его в выбранный цвет и подготовлю результат в нужном формате."
    ),
    "language_prompt": "{icon} <b>Выберите язык</b>\nChoose a language",
    "main_menu": (
        "{icon} <b>Перекрашиваю Premium Emoji и стикеры в любой цвет</b>\n\n"
        "Сохраняю исходные контуры, свет, тени и прозрачность.\n\n"
        "Выберите действие:"
    ),
    "send_source": (
        "{icon} <b>Отправьте материал для перекраски</b>\n\n"
        "Подойдёт Premium Emoji, стикер, PNG, WEBP, TGS, WEBM, ZIP "
        "или ссылка на Telegram-набор."
    ),
    "my_packs": (
        "{icon} <b>Мои наборы</b>\n\n"
        "Бот не хранит историю пользователей и созданных наборов. "
        "Управлять добавленными наборами можно в официальном боте @Stickers."
    ),
    "information": (
        "{icon} <b>Emoji &amp; Sticker Color Bot</b>\n\n"
        "Перекрашивает Premium Emoji, стикеры и наборы с сохранением контуров, "
        "светотени и прозрачности. Поддерживаются PNG, WEBP, TGS, WEBM и ZIP."
    ),
    "help": (
        "{icon} <b>Emoji &amp; Sticker Color Bot — помощь</b>\n\n"
        "Можно отправить один стикер или Custom Emoji, ссылку t.me/addstickers/… или "
        "t.me/addemoji/…, Unicode Emoji, PNG, WEBP, TGS, WEBM, ZIP или одну media group.\n\n"
        "Цвет принимается как HEX или RGB. Эмодзи-пак создаёт Custom Emoji, стикер-пак — "
        "обычные стикеры. Adaptive доступен только для Custom Emoji и окрашивается Telegram. "
        "Unicode Emoji становится графическим PNG. ZIP сохраняет порядок и исходные форматы."
    ),
    "colors": (
        "{icon} <b>Цвета</b>\n\n"
        "<code>#FFFFFF</code> — Белый\n<code>#000000</code> — Чёрный\n"
        "<code>#FF0000</code> — Красный\n<code>#FF9800</code> — Оранжевый\n"
        "<code>#FFEB3B</code> — Жёлтый\n<code>#4CAF50</code> — Зелёный\n"
        "<code>#03A9F4</code> — Голубой\n<code>#2196F3</code> — Синий\n"
        "<code>#9C27B0</code> — Фиолетовый\n<code>#E91E63</code> — Розовый\n\n"
        "Форматы: <code>#FF00AA</code>, <code>F0A</code>, "
        "<code>rgb(255, 0, 170)</code>, <code>255, 0, 170</code>."
    ),
    "language": "{icon} Выберите язык:",
    "language_changed": "{icon} Язык изменён.",
    "cancelled": "{icon} Задача отменена, временные файлы удалены.",
    "nothing_to_cancel": "Нет активной задачи.",
    "private_only": "Откройте бота в личном чате для обработки файлов.",
    "unsupported": "{icon} Формат не поддерживается. Используйте /help.",
    "busy": "Сначала завершите текущую задачу или нажмите «Отмена».",
    "maintenance": "Сервис временно находится на техническом обслуживании. Попробуйте позже.",
    "overloaded": "Сервис сейчас сильно загружен. Попробуйте немного позже.",
    "rate_limited": "Слишком много новых задач. Попробуйте позже.",
    "source_found": (
        "{icon} <b>Источник найден</b>\n\nНазвание: {title}\nТип: {kind}\nЭлементов: {count}\n"
        "Форматы:\n{formats}\n\n"
        "<code>#FFFFFF</code> — Белый\n<code>#000000</code> — Чёрный\n"
        "<code>#FF0000</code> — Красный\n<code>#FF9800</code> — Оранжевый\n"
        "<code>#FFEB3B</code> — Жёлтый\n<code>#4CAF50</code> — Зелёный\n"
        "<code>#03A9F4</code> — Голубой\n<code>#2196F3</code> — Синий\n"
        "<code>#9C27B0</code> — Фиолетовый\n<code>#E91E63</code> — Розовый\n\n"
        "Нажмите на код, скопируйте его и отправьте боту. Можно также отправить HEX/RGB вручную."
    ),
    "invalid_color": (
        "Не удалось распознать цвет. Пример: <code>#8B5CF6</code> "
        "или <code>rgb(139, 92, 246)</code>."
    ),
    "choose_output": "{icon} Цвет <code>{color}</code> принят. Выберите результат:",
    "preview_ready": "{icon} Предпросмотр первого элемента готов. Продолжить?",
    "adaptive_preview": (
        "{icon} Форма подготовлена. Фактический цвет Adaptive Emoji определяет Telegram "
        "в зависимости от места использования и темы."
    ),
    "enter_pack_name": "Введите название нового набора (1–64 символа).",
    "split_confirm": "Набор слишком большой для одного Telegram-набора. Разделить на части?",
    "invalid_pack_name": "Название должно содержать от 1 до 64 символов. Введите другое.",
    "processing": "{icon} Перекрашиваю…\n{done} / {total}",
    "publishing": "{icon} Файлы готовы. Загружаю элементы в Telegram…",
    "flood_wait": "Telegram временно ограничил скорость. Загрузка продолжится автоматически.",
    "done_file": "{icon} Готово. Цвет: <code>{color}</code>",
    "done_pack": (
        "{icon} <b>Набор готов</b>\n\nНазвание: {title}\nТип: {kind}\n"
        "Элементов: {count}\nЦвет: <code>{color}</code>"
    ),
    "partial": "Готово: {done} / {total}\nНе удалось обработать: {failed}",
    "file_too_large": "Файл слишком большой.",
    "archive_invalid": "Архив повреждён или небезопасен.",
    "tgs_invalid": "Не удалось открыть TGS.",
    "video_too_long": "Видео длиннее допустимых 3 секунд.",
    "emoji_font_missing": "На сервере не настроен совместимый Color Emoji font.",
    "service_error": "Не удалось обработать источник. Попробуйте другой файл.",
    "timeout": "Время ожидания истекло. Временные файлы удалены.",
}
