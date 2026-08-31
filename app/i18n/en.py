"""English messages."""

EN: dict[str, str] = {
    "start": (
        "{icon} <b>Emoji &amp; Sticker Color Bot</b>\n\n"
        "Send a sticker, Custom Emoji, Unicode Emoji, file, or pack link.\n"
        "I will recolor it and prepare the result in the format you choose."
    ),
    "language_prompt": "{icon} <b>Choose a language</b>\nВыберите язык",
    "main_menu": (
        "{icon} <b>I recolor Premium Emoji and stickers in any color</b>\n\n"
        "<blockquote>{magic_icon} I change the hue while preserving outlines, lighting, "
        "shadows, and transparency.\n{preview_icon} A pack preview is shown before full "
        "processing.\n{pack_icon} Single items, complete packs, and archives are supported."
        "</blockquote>\n\n"
        "{info_icon} Choose an action:"
    ),
    "send_source": (
        "{icon} <b>Send material to recolor:</b>\n\n"
        "<blockquote>{emoji_icon} Premium Emoji — one or more in one message\n"
        "{sticker_icon} Sticker — as a separate message\n"
        "{link_icon} Pack link — addemoji or addstickers\n"
        "{file_icon} File — TGS, WEBP, WEBM, PNG, or ZIP</blockquote>"
    ),
    "my_packs": (
        "{icon} <b>My packs</b>\n\n"
        "{pack_list}\n\n"
        "{link_icon} Manage packs you added through the official @Stickers bot."
    ),
    "my_packs_empty": "{lock_icon} You have not created any packs through the bot yet.",
    "information": (
        "{icon} <b>Emoji &amp; Sticker Color Bot</b>\n\n"
        "{color_icon} Recolors Premium Emoji, stickers, and packs while preserving outlines, "
        "lighting, shadows, and transparency.\n\n"
        "{file_icon} PNG, WEBP, TGS, WEBM, and ZIP are supported.\n\n"
        "{support_icon} Contact technical support if you need assistance."
    ),
    "help": (
        "{icon} <b>Emoji &amp; Sticker Color Bot — help</b>\n\n"
        "Send one or more Custom Emoji, a sticker, a t.me/addstickers/… or t.me/addemoji/… link, "
        "Unicode Emoji, PNG, WEBP, TGS, WEBM, ZIP, or one media group.\n\n"
        "Colors accept HEX or RGB. Emoji Pack creates Custom Emoji; Sticker Pack creates regular "
        "stickers. Adaptive is only for Custom Emoji and Telegram chooses its color. Unicode Emoji "
        "becomes a graphic PNG. ZIP preserves order and source formats."
    ),
    "colors": (
        "{icon} <b>Colors</b>\n\n"
        "<blockquote><code>#FFFFFF</code> — White\n<code>#000000</code> — Black\n"
        "<code>#FF0000</code> — Red\n<code>#FF9800</code> — Orange\n"
        "<code>#FFEB3B</code> — Yellow\n<code>#4CAF50</code> — Green\n"
        "<code>#03A9F4</code> — Light blue\n<code>#2196F3</code> — Blue\n"
        "<code>#9C27B0</code> — Purple\n<code>#E91E63</code> — Pink</blockquote>\n\n"
        "Formats: <code>#FF00AA</code>, <code>F0A</code>, "
        "<code>rgb(255, 0, 170)</code>, <code>255, 0, 170</code>. "
        "Send multiple HEX codes separated by spaces or new lines."
    ),
    "language": "{icon} Choose a language:",
    "language_changed": "{icon} Language changed.",
    "cancelled": "{icon} Job cancelled and temporary files removed.",
    "nothing_to_cancel": "There is no active job.",
    "private_only": "Open the bot in a private chat to process files.",
    "unsupported": "{icon} Unsupported format. See /help.",
    "busy": "Finish the current job first or press Cancel.",
    "maintenance": "The service is temporarily under maintenance. Please try later.",
    "overloaded": "The service is busy. Please try again a little later.",
    "rate_limited": "Too many new jobs. Please try later.",
    "source_found": (
        "{icon} <b>Source found</b>\n\n{edit_icon} Title: {title}\n"
        "{info_icon} Type: {kind}\n{file_icon} Items: {count}\n"
        "{pack_icon} Formats:\n{formats}\n\n{color_icon} <b>Choose a color</b>\n\n"
        "<blockquote><code>#FFFFFF</code> — White\n<code>#000000</code> — Black\n"
        "<code>#FF0000</code> — Red\n<code>#FF9800</code> — Orange\n"
        "<code>#FFEB3B</code> — Yellow\n<code>#4CAF50</code> — Green\n"
        "<code>#03A9F4</code> — Light blue\n<code>#2196F3</code> — Blue\n"
        "<code>#9C27B0</code> — Purple\n<code>#E91E63</code> — Pink</blockquote>\n\n"
        "Tap a code to copy it and send it to the bot. Or open Pick a color, copy the "
        "HEX/RGB code from the website, and send it as a message. Multiple HEX codes "
        "can be separated by spaces or new lines."
    ),
    "pack_source_found": (
        "{icon} <b>Pack ready for processing</b>\n\n"
        "<blockquote>{edit_icon} Title: {title}\n{info_icon} Type: {kind}\n"
        "{file_icon} Items: {count}\n{pack_icon} Formats:\n{formats}</blockquote>\n\n"
        "{color_icon} <b>Choose a color</b>\n\n"
        "<blockquote><code>#FFFFFF</code> — White\n<code>#000000</code> — Black\n"
        "<code>#FF0000</code> — Red\n<code>#FF9800</code> — Orange\n"
        "<code>#FFEB3B</code> — Yellow\n<code>#4CAF50</code> — Green\n"
        "<code>#03A9F4</code> — Light blue\n<code>#2196F3</code> — Blue\n"
        "<code>#9C27B0</code> — Purple\n<code>#E91E63</code> — Pink</blockquote>\n\n"
        "Tap a code, copy it, and send it to the bot, or use Pick a color. Multiple HEX "
        "codes can be separated by spaces or new lines."
    ),
    "invalid_color": (
        "Color not recognized. Example: <code>#8B5CF6</code> "
        "or <code>rgb(139, 92, 246)</code>."
    ),
    "too_many_colors": (
        "This would create too many results in one job. Choose at most {maximum_colors} "
        "colors and no more than {maximum_items} resulting items."
    ),
    "choose_intensity": (
        "{icon} <b>Choose recoloring intensity</b>\n\n"
        "<blockquote>Source items: <b>{source_count}</b>\n"
        "Selected colors: <b>{color_count}</b>\n"
        "Resulting items: <b>{result_count}</b>\n"
        "Colors: <code>{colors}</code></blockquote>\n\n"
        "Soft retains more source hues, Normal works for most stickers, and Vivid "
        "produces a dense target color."
    ),
    "choose_output": (
        "{icon} Color <code>{color}</code> accepted.\n"
        "{pack_icon} Choose an output format:"
    ),
    "pack_choose_output": (
        "{icon} Color <code>{color}</code> selected.\n\n"
        "<blockquote>{pack_icon} Pack items: <b>{count}</b>.\n"
        "{time_icon} Telegram determines pauses between operations. The bot shows exact "
        "progress and resumes automatically after a restriction.</blockquote>\n\n"
        "{file_icon} Choose the output format:"
    ),
    "preview_ready": (
        "{icon} A preview of the first item is ready.\n"
        "{color_icon} Outlines and lighting are preserved.\n"
        "Intensity: <b>{intensity}</b>. Continue?"
    ),
    "adaptive_preview": (
        "{icon} The shape is ready. Telegram chooses the actual Adaptive Emoji color based on "
        "where it is used and the current theme."
    ),
    "enter_pack_name": "Enter a title for the new pack (1–64 characters).",
    "existing_pack_link_prompt": (
        "Send a link to an existing pack. It must be a pack this bot created for your account."
    ),
    "existing_pack_admin_prompt": (
        "Choose one of your packs created in the bot, or send another link."
    ),
    "existing_pack_invalid_link": (
        "The link was not recognized. Send a link in the form "
        "<code>https://t.me/addemoji/...</code> or "
        "<code>https://t.me/addstickers/...</code>."
    ),
    "existing_pack_wrong_bot": (
        "This pack was created by another bot. Telegram only lets a bot edit packs it created."
    ),
    "existing_pack_unavailable": "Telegram could not find this pack or denied access to it.",
    "existing_pack_type_mismatch": (
        "The link type does not match the pack type, or this pack cannot be updated."
    ),
    "existing_pack_full": (
        "The pack already contains {current} items; {incoming} are being added, while "
        "Telegram's limit is {maximum}. Choose another pack."
    ),
    "existing_pack_adaptive_mismatch": (
        "Regular and Adaptive Emoji cannot be mixed in one pack. Choose a compatible pack."
    ),
    "existing_pack_checking": "Checking the pack…",
    "split_confirm": "This source is too large for one Telegram pack. Split it into parts?",
    "invalid_pack_name": "The title must be 1–64 characters. Enter another title.",
    "processing": (
        "{icon} <b>Recoloring the material</b>\n\n"
        "<blockquote>Processed: <b>{done} / {total}</b>\n"
        "Preserving outlines, lighting, and transparency.</blockquote>\n\n"
        "Please wait for processing to finish."
    ),
    "cancel_choose": (
        "{icon} <b>Cancel jobs</b>\n\n"
        "<blockquote>Active jobs: <b>{count}</b>\n{jobs}</blockquote>\n\n"
        "Choose which jobs to stop:"
    ),
    "cancelled_last": "{icon} The latest job was cancelled. Temporary files were removed.",
    "cancelled_all": (
        "{icon} All active jobs were cancelled: <b>{count}</b>. Temporary files were removed."
    ),
    "publishing": (
        "{icon} <b>Creating the pack in Telegram</b>\n\n"
        "{file_icon} Files prepared: <b>{prepared} / {total}</b>\n"
        "{pack_icon} Items added: <b>{done} / {total}</b>\n"
        "{time_icon} Estimated readiness: in <code>{eta}</code>"
    ),
    "publishing_existing": (
        "{icon} <b>Adding to an existing pack</b>\n\n"
        "{pack_icon} Pack: {title}\n"
        "{file_icon} Items added: <b>{done} / {total}</b>\n"
        "{time_icon} Estimated readiness: in <code>{eta}</code>"
    ),
    "flood_wait": (
        "Telegram temporarily limited the upload speed.\n"
        "{file_icon} Material processed: <b>{done} / {total}</b>\n"
        "Continuing in <code>{seconds}</code>."
    ),
    "pack_flood_wait": (
        "Telegram limits the speed of sticker pack changes.\n"
        "{file_icon} Files prepared: <b>{prepared} / {total}</b>\n"
        "{pack_icon} Added to the pack: <b>{done} / {total}</b>\n"
        "Continuing in <code>{seconds}</code>.\n"
        "{time_icon} Estimated readiness: in <code>{eta}</code>."
    ),
    "single_result_ready": (
        "{icon} <b>Done</b>\n\n{color_icon} Color: <code>{color}</code>\n"
        "Intensity: <b>{intensity}</b>\n"
        "{sticker_icon} The result was sent as a sticker.\n\n"
        "{info_icon} You can add it to a new or existing Emoji Pack."
    ),
    "preparing_download": "{icon} Preparing the downloadable file…",
    "intensity_soft": "Soft",
    "intensity_normal": "Normal",
    "intensity_vivid": "Vivid",
    "done_file": (
        "{icon} Done. Color: <code>{color}</code>\n"
        "{download_icon} The file was sent above."
    ),
    "done_pack": (
        "{icon} <b>Pack ready</b>\n\n{edit_icon} Title: {title}\n"
        "{info_icon} Type: {kind}\n{file_icon} Items: {count}\n"
        "{color_icon} Color: <code>{color}</code>"
    ),
    "done_existing_pack": (
        "{icon} <b>Done</b>\n\n{pack_icon} Pack: {title}\n"
        "{file_icon} Items added: <b>{count}</b>"
    ),
    "existing_pack_add_failed": (
        "{icon} Telegram stopped adding items to the existing pack.\n"
        "Successfully added: <b>{done} / {total}</b>. Items already added were preserved."
    ),
    "telegram_item_rejected": "Telegram rejected the prepared file",
    "retry_failed": (
        "{icon} Retrying only failed items: <b>{count}</b>. Completed results will not "
        "be processed again."
    ),
    "partial": "Done: {done} / {total}\nFailed: {failed}",
    "file_too_large": "The file is too large.",
    "source_invalid": "The file is empty or damaged.",
    "format_mismatch": "The file content does not match its declared format.",
    "image_invalid": "The image is damaged or its resolution is too large.",
    "webm_invalid": "The WEBM is damaged, has no video, or its resolution is too large.",
    "archive_invalid": "The archive is damaged or unsafe.",
    "tgs_invalid": "Could not open the TGS file.",
    "video_too_long": "The video is longer than the 3-second limit.",
    "emoji_font_missing": "A compatible Color Emoji font is not configured on this server.",
    "service_error": "The source could not be processed. Try another file.",
    "timeout": "An inactive unfinished job was closed and its temporary files were removed.",
}
