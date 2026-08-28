"""English messages."""

EN: dict[str, str] = {
    "start": (
        "{icon} <b>Emoji &amp; Sticker Color Bot</b>\n\n"
        "Send a sticker, Custom Emoji, Unicode Emoji, file, or pack link.\n"
        "I will recolor it and prepare the result in the format you choose."
    ),
    "help": (
        "{icon} <b>Emoji &amp; Sticker Color Bot — help</b>\n\n"
        "Send one sticker or Custom Emoji, a t.me/addstickers/… or t.me/addemoji/… link, "
        "Unicode Emoji, PNG, WEBP, TGS, WEBM, ZIP, or one media group.\n\n"
        "Colors accept HEX or RGB. Emoji Pack creates Custom Emoji; Sticker Pack creates regular "
        "stickers. Adaptive is only for Custom Emoji and Telegram chooses its color. Unicode Emoji "
        "becomes a graphic PNG. ZIP preserves order and source formats."
    ),
    "privacy": (
        "{icon} <b>Privacy</b>\n\n"
        "Regular Telegram IDs are used only in memory for the current operation and temporary rate "
        "limits; they are not stored permanently. Usernames, names, request, color, and pack history "
        "are not stored. Files are temporary and removed on success, error, timeout, or cancellation. "
        "Technical statistics are anonymous. Administrator records are stored in SQLite solely for "
        "admin-panel access control."
    ),
    "colors": (
        "{icon} <b>Colors</b>\n\n"
        "#FFFFFF — White\n#000000 — Black\n#FF0000 — Red\n#FF9800 — Orange\n"
        "#FFEB3B — Yellow\n#4CAF50 — Green\n#03A9F4 — Light blue\n#2196F3 — Blue\n"
        "#9C27B0 — Purple\n#E91E63 — Pink\n\n"
        "Formats: #FF00AA, F0A, rgb(255, 0, 170), 255, 0, 170."
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
        "{icon} <b>Source found</b>\n\nTitle: {title}\nType: {kind}\nItems: {count}\n"
        "Formats:\n{formats}\n\n"
        "#FFFFFF — White\n#000000 — Black\n#FF0000 — Red\n#FF9800 — Orange\n"
        "#FFEB3B — Yellow\n#4CAF50 — Green\n#03A9F4 — Light blue\n#2196F3 — Blue\n"
        "#9C27B0 — Purple\n#E91E63 — Pink\n\n"
        "Choose a color below or send HEX/RGB.\n"
        "Copy a code from the picker site and send it to the bot."
    ),
    "invalid_color": "Color not recognized. Example: #8B5CF6 or rgb(139, 92, 246).",
    "choose_output": "{icon} Color {color} accepted. Choose an output:",
    "preview_ready": "{icon} A preview of the first item is ready. Continue?",
    "adaptive_preview": (
        "{icon} The shape is ready. Telegram chooses the actual Adaptive Emoji color based on "
        "where it is used and the current theme."
    ),
    "enter_pack_name": "Enter a title for the new pack (1–64 characters).",
    "split_confirm": "This source is too large for one Telegram pack. Split it into parts?",
    "invalid_pack_name": "The title must be 1–64 characters. Enter another title.",
    "processing": "{icon} Recoloring…\n{done} / {total}",
    "publishing": "{icon} Files are ready. Uploading items to Telegram…",
    "flood_wait": "Telegram temporarily limited the upload speed. It will continue automatically.",
    "done_file": "{icon} Done. Color: {color}",
    "done_pack": (
        "{icon} <b>Pack ready</b>\n\nTitle: {title}\nType: {kind}\n"
        "Items: {count}\nColor: {color}"
    ),
    "partial": "Done: {done} / {total}\nFailed: {failed}",
    "file_too_large": "The file is too large.",
    "archive_invalid": "The archive is damaged or unsafe.",
    "tgs_invalid": "Could not open the TGS file.",
    "video_too_long": "The video is longer than the 3-second limit.",
    "emoji_font_missing": "A compatible Color Emoji font is not configured on this server.",
    "service_error": "The source could not be processed. Try another file.",
    "timeout": "The idle timeout expired. Temporary files were removed.",
}
