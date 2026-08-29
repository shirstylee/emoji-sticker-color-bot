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
        "<blockquote>{magic_icon} Меняю оттенок, сохраняя исходные контуры, свет, "
        "тени и прозрачность.\n{preview_icon} Перед обработкой набора показываю "
        "предпросмотр результата.\n{pack_icon} Поддерживаю отдельные элементы, "
        "целые наборы и архивы.</blockquote>\n\n"
        "{info_icon} Выберите действие:"
    ),
    "send_source": (
        "{icon} <b>Отправьте материал для перекраски:</b>\n\n"
        "<blockquote>{emoji_icon} Premium Emoji — отдельным сообщением\n"
        "{sticker_icon} Стикер — отдельным сообщением\n"
        "{link_icon} Ссылка на набор — addemoji или addstickers\n"
        "{file_icon} Файл — TGS, WEBP, WEBM, PNG или ZIP</blockquote>"
    ),
    "my_packs": (
        "{icon} <b>Мои наборы</b>\n\n"
        "{pack_list}\n\n"
        "{link_icon} Управлять добавленными наборами можно в официальном боте @Stickers."
    ),
    "my_packs_empty": "{lock_icon} Вы пока не создали ни одного набора через бота.",
    "information": (
        "{icon} <b>Emoji &amp; Sticker Color Bot</b>\n\n"
        "{color_icon} Перекрашивает Premium Emoji, стикеры и наборы с сохранением "
        "контуров, светотени и прозрачности.\n\n"
        "{file_icon} Поддерживаются PNG, WEBP, TGS, WEBM и ZIP.\n\n"
        "{support_icon} По вопросам работы сервиса обратитесь в техническую поддержку."
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
        "<blockquote><code>#FFFFFF</code> — Белый\n<code>#000000</code> — Чёрный\n"
        "<code>#FF0000</code> — Красный\n<code>#FF9800</code> — Оранжевый\n"
        "<code>#FFEB3B</code> — Жёлтый\n<code>#4CAF50</code> — Зелёный\n"
        "<code>#03A9F4</code> — Голубой\n<code>#2196F3</code> — Синий\n"
        "<code>#9C27B0</code> — Фиолетовый\n<code>#E91E63</code> — Розовый</blockquote>\n\n"
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
        "{icon} <b>Источник найден</b>\n\n{edit_icon} Название: {title}\n"
        "{info_icon} Тип: {kind}\n{file_icon} Элементов: {count}\n"
        "{pack_icon} Форматы:\n{formats}\n\n{color_icon} <b>Выберите цвет</b>\n\n"
        "<blockquote><code>#FFFFFF</code> — Белый\n<code>#000000</code> — Чёрный\n"
        "<code>#FF0000</code> — Красный\n<code>#FF9800</code> — Оранжевый\n"
        "<code>#FFEB3B</code> — Жёлтый\n<code>#4CAF50</code> — Зелёный\n"
        "<code>#03A9F4</code> — Голубой\n<code>#2196F3</code> — Синий\n"
        "<code>#9C27B0</code> — Фиолетовый\n<code>#E91E63</code> — Розовый</blockquote>\n\n"
        "Нажмите на код, скопируйте его и отправьте боту. Либо откройте «Подобрать цвет», "
        "скопируйте HEX/RGB-код с сайта и отправьте его сообщением."
    ),
    "pack_source_found": (
        "{icon} <b>Набор готов к обработке</b>\n\n"
        "<blockquote>{edit_icon} Название: {title}\n{info_icon} Тип: {kind}\n"
        "{file_icon} Элементов: {count}\n{pack_icon} Форматы:\n{formats}</blockquote>\n\n"
        "{color_icon} <b>Выберите цвет</b>\n\n"
        "<blockquote><code>#FFFFFF</code> — Белый\n<code>#000000</code> — Чёрный\n"
        "<code>#FF0000</code> — Красный\n<code>#FF9800</code> — Оранжевый\n"
        "<code>#FFEB3B</code> — Жёлтый\n<code>#4CAF50</code> — Зелёный\n"
        "<code>#03A9F4</code> — Голубой\n<code>#2196F3</code> — Синий\n"
        "<code>#9C27B0</code> — Фиолетовый\n<code>#E91E63</code> — Розовый</blockquote>\n\n"
        "Нажмите на код, скопируйте его и отправьте боту или воспользуйтесь "
        "кнопкой «Подобрать цвет»."
    ),
    "invalid_color": (
        "Не удалось распознать цвет. Пример: <code>#8B5CF6</code> "
        "или <code>rgb(139, 92, 246)</code>."
    ),
    "choose_output": (
        "{icon} Цвет <code>{color}</code> принят.\n"
        "{pack_icon} Выберите формат результата:"
    ),
    "pack_choose_output": (
        "{icon} Цвет <code>{color}</code> выбран.\n\n"
        "<blockquote>{pack_icon} В наборе: <b>{count}</b> элементов.\n"
        "{time_icon} Telegram сам задаёт паузы между операциями. Бот показывает "
        "точный прогресс и автоматически продолжает работу после ограничения.</blockquote>\n\n"
        "{file_icon} Выберите формат результата:"
    ),
    "preview_ready": (
        "{icon} Предпросмотр первого элемента готов.\n"
        "{color_icon} Контуры и светотень сохранены. Продолжить?"
    ),
    "adaptive_preview": (
        "{icon} Форма подготовлена. Фактический цвет Adaptive Emoji определяет Telegram "
        "в зависимости от места использования и темы."
    ),
    "enter_pack_name": "Введите название нового набора (1–64 символа).",
    "split_confirm": "Набор слишком большой для одного Telegram-набора. Разделить на части?",
    "invalid_pack_name": "Название должно содержать от 1 до 64 символов. Введите другое.",
    "processing": "{icon} Перекрашиваю…\n{done} / {total}",
    "publishing": (
        "{icon} <b>Создаю набор в Telegram</b>\n\n"
        "{file_icon} Подготовлено файлов: <b>{prepared} / {total}</b>\n"
        "{pack_icon} Добавлено элементов: <b>{done} / {total}</b>"
    ),
    "flood_wait": (
        "Telegram временно ограничил скорость.\n"
        "{file_icon} Материал обработан: <b>{done} / {total}</b>\n"
        "Продолжение через <code>{seconds}</code>."
    ),
    "pack_flood_wait": (
        "Telegram ограничивает скорость изменения наборов.\n"
        "{file_icon} Подготовлено файлов: <b>{prepared} / {total}</b>\n"
        "{pack_icon} Добавлено в набор: <b>{done} / {total}</b>\n"
        "Продолжение через <code>{seconds}</code>."
    ),
    "single_result_ready": (
        "{icon} <b>Готово</b>\n\n{color_icon} Цвет: <code>{color}</code>\n"
        "{sticker_icon} Результат отправлен как стикер.\n\n"
        "{info_icon} Его можно добавить в новый Emoji-набор или скачать исходным файлом."
    ),
    "preparing_download": "{icon} Подготавливаю файл для скачивания…",
    "done_file": (
        "{icon} Готово. Цвет: <code>{color}</code>\n"
        "{download_icon} Файл отправлен выше."
    ),
    "done_pack": (
        "{icon} <b>Набор готов</b>\n\n{edit_icon} Название: {title}\n"
        "{info_icon} Тип: {kind}\n{file_icon} Элементов: {count}\n"
        "{color_icon} Цвет: <code>{color}</code>"
    ),
    "partial": "Готово: {done} / {total}\nНе удалось обработать: {failed}",
    "file_too_large": "Файл слишком большой.",
    "archive_invalid": "Архив повреждён или небезопасен.",
    "tgs_invalid": "Не удалось открыть TGS.",
    "video_too_long": "Видео длиннее допустимых 3 секунд.",
    "emoji_font_missing": "На сервере не настроен совместимый Color Emoji font.",
    "service_error": "Не удалось обработать источник. Попробуйте другой файл.",
    "timeout": "Неактивная незавершённая задача закрыта. Её временные файлы удалены.",
}
