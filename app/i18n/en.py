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
        "<blockquote>{emoji_icon} Premium Emoji — as a separate message\n"
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
        "Send one sticker or Custom Emoji, a t.me/addstickers/… or t.me/addemoji/… link, "
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
        "<code>rgb(255, 0, 170)</code>, <code>255, 0, 170</code>."
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
        "HEX/RGB code from the website, and send it as a message."
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
        "Tap a code, copy it, and send it to the bot, or use Pick a color."
    ),
    "invalid_color": (
        "Color not recognized. Example: <code>#8B5CF6</code> "
        "or <code>rgb(139, 92, 246)</code>."
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
        "{color_icon} Outlines and lighting are preserved. Continue?"
    ),
    "adaptive_preview": (
        "{icon} The shape is ready. Telegram chooses the actual Adaptive Emoji color based on "
        "where it is used and the current theme."
    ),
    "enter_pack_name": "Enter a title for the new pack (1–64 characters).",
    "split_confirm": "This source is too large for one Telegram pack. Split it into parts?",
    "invalid_pack_name": "The title must be 1–64 characters. Enter another title.",
    "processing": "{icon} Recoloring…\n{done} / {total}",
    "publishing": (
        "{icon} <b>Creating the pack in Telegram</b>\n\n"
        "{file_icon} Files prepared: <b>{prepared} / {total}</b>\n"
        "{pack_icon} Items added: <b>{done} / {total}</b>\n"
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
        "{sticker_icon} The result was sent as a sticker.\n\n"
        "{info_icon} You can add it to a new Emoji Pack or download the source file."
    ),
    "preparing_download": "{icon} Preparing the downloadable file…",
    "done_file": (
        "{icon} Done. Color: <code>{color}</code>\n"
        "{download_icon} The file was sent above."
    ),
    "done_pack": (
        "{icon} <b>Pack ready</b>\n\n{edit_icon} Title: {title}\n"
        "{info_icon} Type: {kind}\n{file_icon} Items: {count}\n"
        "{color_icon} Color: <code>{color}</code>"
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
