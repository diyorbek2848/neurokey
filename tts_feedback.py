# -*- coding: utf-8 -*-
"""TTS feedback — qattiq matnlarni konfiguratsiyaga. Tayyor jumla yo'q prinsipi.

Har bir kalit (ru, en) juftligi. .env da TTS_FEEDBACK_<KEY> orqali override.
"""
from __future__ import annotations

import os

try:
    import config as C
except Exception:
    C = None


def _lang() -> str:
    return "ru"


# Kalit -> (ru, en). Format: {min}, {sec}, {idx}, {result}, {msg}, ...
PHRASES = {
    "todo_added": ("Добавлено в todo.", "Added to your todo."),
    "todo_empty": ("Ваш список todo пуст.", "Your todo list is empty."),
    "todo_done": ("Задача {idx} выполнена.", "Marked task {idx} as done."),
    "todo_no_such": ("Нет такой задачи.", "No such task number."),
    "timer_min": ("Таймер на {min} мин.", "Timer set for {min} minutes."),
    "timer_sec": ("Таймер на {sec} сек.", "Timer set for {sec} seconds."),
    "calc_result": ("Результат: {result}", "Result: {result}"),
    "calc_parse_error": ("Не удалось распознать как вычисление.", "I couldn't parse that as a calculation."),
    "clipboard_copied": ("Текст экрана скопирован.", "Screen text copied to clipboard."),
    "clipboard_no_text": ("Нет текста на экране или pyperclip не установлен.", "No text on screen or clipboard not available. Install pyperclip."),
    "clipboard_copy_error": ("Не удалось скопировать экран. Установите pyperclip и screen capture.", "Could not copy screen. Install pyperclip and screen capture support."),
    "todo_list": ("Ваш todo: {list}", "Your todo: {list}"),
    "calendar_upcoming": ("Предстоящие: {list}", "Upcoming: {list}"),
    "calendar_added": ("Добавлено в календарь.", "Added to calendar."),
    "calendar_empty": ("Календарь пуст.", "Your calendar is empty."),
    "idea_saved": ("Идея сохранена.", "Idea saved."),
    "idea_error": ("Не удалось сохранить идею.", "Could not save idea."),
    "backup_done": ("Бэкап готов.", "Backup done."),
    "backup_failed": ("Бэкап не удался: {msg}", "Backup failed: {msg}"),
    "remember_ok": ("Запомню.", "I'll remember that."),
    "slack_sent": ("Отправлено в Slack.", "Sent to Slack."),
    "slack_failed": ("Не удалось отправить в Slack.", "Could not send to Slack."),
    "discord_sent": ("Отправлено в Discord.", "Sent to Discord."),
    "discord_failed": ("Не удалось отправить в Discord.", "Could not send to Discord."),
    "slack_discord_not_configured": ("Slack или Discord webhook не настроен. Добавьте SLACK_WEBHOOK_URL или DISCORD_WEBHOOK_URL в .env.", "Slack or Discord webhook is not configured. Add SLACK_WEBHOOK_URL or DISCORD_WEBHOOK_URL to .env."),
    "notion_not_configured": ("Notion не настроен. Добавьте NOTION_API_KEY в .env.", "Notion is not configured yet. Add NOTION_API_KEY to .env for note saving."),
    "smart_home_not_configured": ("Умный дом не настроен. Добавьте SMART_HOME_HTTP_URL в .env.", "Smart home is not configured yet. Add SMART_HOME_HTTP_URL to .env."),
    "opened_folder": ("Открыл папку NeuroKey и конфиг.", "Opened NeuroKey folder and config."),
    "opened_error_file": ("Открыл файл ошибок. Отправь владельцу.", "Opened error file. Send it to the owner."),
    "noise_filtered": ("Шум фильтруется, голос не блокируется.", "Background noise is filtered; your voice is not blocked."),
    "screen_watched": ("Экран отслеживается. При вопросе о содержимом — использую для ответа.", "Screen is watched in the background. When you ask what's on screen or search — I use it for answers."),
    "faster": ("Быстрее.", "Faster."),
    "slower": ("Медленнее.", "Slower."),
    "opened": ("Открыто.", "Opened."),
    "could_not_open": ("Не удалось открыть.", "Could not open."),
    "no_connection": ("Нет связи. Попробуй снова.", "No connection. Try again."),
    "cancelled": ("Отменено.", "Cancelled."),
    "clipboard_not_available": ("pyperclip не установлен. pip install pyperclip.", "Clipboard not available. Install pyperclip: pip install pyperclip."),
    "writing_code": ("Пишу код.", "Writing code."),
    "code_saved": ("Код сохранён в {filename}. Открой в Cursor.", "Code saved to {filename}. You can open it in Cursor."),
    "code_save_error": ("Не удалось сохранить код. Проверь права на папку.", "Couldn't save code. Check folder permissions."),
    "code_gen_error": ("Не удалось сгенерировать код. Опиши задачу точнее.", "Couldn't generate code. Try describing the task more precisely."),
    "organ_created": ("Орган создан. Готово.", "Organ created. Done."),
    "remind_min": ("Напомню через {min} мин.", "I'll remind you in {min} minutes."),
    "remind_sec": ("Напомню через минуту.", "I'll remind you in a minute."),
    "summary_error": ("Не удалось сгенерировать сводку.", "Could not generate summary."),
    "code_wont_write": ("Хорошо, не буду писать код.", "Okay, I won't write the code."),
    "didnt_send_cancelled": ("Ничего не отправлено. Отменено.", "Didn't send anything. Cancelled."),
    "tg_sent_no_more": ("Отправлено. Новых сообщений нет.", "Sent. No more new messages."),
    "tg_wait": ("Telegram просит подождать. Попробуй через минуту.", "Telegram asks to wait. Try again in a minute."),
    "tg_failed": ("Не удалось отправить. Проверь интернет и сессию Telegram.", "Failed to send. Check internet and Telegram session."),
    "tg_failed_short": ("Не удалось отправить.", "Failed to send."),
    "cancelled_didnt_send": ("Отменено. Не отправил.", "Cancelled. Didn't send."),
    "file_extracted": ("Содержимое файла извлечено. {n} символов. Спроси подробности.", "File content extracted. {n} chars. Ask for details."),
    "could_not_read_file": ("Не удалось прочитать файл.", "Could not read file."),
    "which_file": ("Какой файл? Скажи путь или сначала открой файл.", "Which file? Say the path or open a file first."),
    "what_command": ("Какую команду выполнить? Скажи: run dir или run winget list.", "What command to run? Say: run dir, or run winget list."),
    "no_open_ports": ("Открытых портов не найдено.", "No open ports found."),
    "no_devices": ("Устройств не найдено.", "No devices found."),
    "opening_telegram": ("Открываю Telegram.", "Opening Telegram."),
    "no_new_messages": ("Новых сообщений в личке нет.", "No new messages in DM right now."),
    "unlocked": ("Разблокировано.", "Unlocked."),
    "wrong_password": ("Неверный пароль. NeuroKey заблокирован.", "Wrong password. NeuroKey is locked."),
    "locked_say_password": ("NeuroKey заблокирован. Скажи пароль для разблокировки.", "NeuroKey locked. Say password to unlock."),
    "locked_say_unlock": ("NeuroKey заблокирован. Скажи «разблокировать» чтобы открыть.", "NeuroKey locked. Say unlock to open."),
    "tg_reply_no_more": ("Ответ отправлен. Новых сообщений нет.", "Sent your reply. No more new messages."),
    "tg_skipped_no_more": ("Пропущено. Новых сообщений нет.", "Skipped. No more new messages."),
    "tg_cant_read": ("Не удалось прочитать Telegram. Проверь сессию: возможно нужен повторный вход по коду.", "Couldn't read Telegram. Check session: you may need to log in again with the code."),
    "search_opened_browser": ("Поиск открыт в браузере. Смотри экран.", "Opened search in browser. Check the screen for results."),
    "youtube_search_opened": ("YouTube поиск открыт.", "Opened YouTube search."),
    "search_opened": ("Поиск открыт. Смотри экран.", "Opened search. Check the screen."),
    "search_info_on_screen": ("Поиск открыт. Инфо и видео на экране.", "Search opened in browser. Info and video are on screen."),
    "which_app": ("Какое приложение? Скажи Telegram, браузер, калькулятор или проводник.", "Which app? Say Telegram, browser, calculator or explorer."),
    "which_app_close": ("Какое приложение закрыть? Скажи Telegram, браузер или калькулятор.", "Which app to close? Say Telegram, browser or calculator."),
    "folder_opened": ("Открыл папку.", "Opened folder."),
    "folder_created_at": ("Папка создана здесь:", "Folder was created at:"),
    "open_folder_first": ("Сначала открой папку, например: открой папку game.", "Open a folder first, for example: open folder game."),
    "specify_filename": ("Укажи имя файла, например: открой из папки readme.", "Specify the file name, for example: open from folder readme."),
    "folder_file_not_found": ("Папку или файл «{target}» не нашёл.", "Folder or file «{target}» not found."),
    "delete_file_confirm": ("Удалить файл {path}? Скажи да или нет.", "Delete file {path}? Say yes or no."),
    "file_not_found": ("Файл не найден.", "File not found."),
    "photo_opened": ("Открыл фото в браузере.", "Opened photo in browser."),
    "photo_not_found": ("Фото не найдено. Скажи название точнее или открой браузер и поищи.", "Photo not found. Say the name more precisely or open browser and search."),
    "check_messages_first": ("Сначала скажи: проверь сообщения в Telegram — тогда скажу кто написал.", "Say first: check messages in Telegram — then I'll say who wrote."),
    "check_messages_first_reply": ("Сначала скажи: проверь сообщения в Telegram — тогда смогу отправить ответ.", "Say first: check messages in Telegram — then I can send a reply."),
    "tg_whom_send": ("Кому отправить? Например: akamga Salom. config.py da TG_CONTACT_ALIASES ni to'ldiring.", "Who to send to? Example: akamga Salom. Fill TG_CONTACT_ALIASES in config.py."),
    "no_unread_emails": ("Непрочитанных писем нет.", "No unread emails."),
    "mail_check_error": ("Не удалось проверить почту.", "Couldn't check mail right now."),
    "weather_error": ("Не удалось получить погоду. Попробуй снова.", "Could not get weather. Try again."),
    "executing_steps": ("Выполняю по шагам.", "Executing step by step."),
    "steps_split_error": ("Не удалось разбить на шаги. Скажи короче, например: открой Telegram, потом браузер.", "Couldn't split into steps. Say it shorter, for example: open Telegram, then browser."),
    "steps_error": ("Что-то пошло не так при выполнении шагов. Попробуй по одному действию.", "Something went wrong running the steps. Try one action at a time."),
    "say_what_to_copy": ("Скажи что копировать или сначала задай вопрос — скопирую ответ.", "Say what to copy, or ask something first — I'll copy the answer."),
    "explorer_restarted": ("Проводник перезапущен. Рабочий стол должен быть.", "Explorer was restarted. Desktop should be back."),
    # Dinamik (Telegram, sandbox)
    "tg_sent_next_suggested": ("Отправлено. Дальше: от {peer}: {msg}. Предложенный ответ: {suggested}. Скажи да — отправить, нет — пропустить.", "Sent. Next: from {peer}: {msg}. Suggested reply: {suggested}. Say yes to send, no to skip."),
    "tg_sent_next_simple": ("Отправлено. Дальше: от {peer}: {msg}. Да — отправить, нет — пропустить.", "Sent. Next: from {peer}: {msg}. Yes to send, no to skip."),
    "tg_reply_mismatch": ("Твой ответ не совпадает с сообщением. Отправить всё равно: {preview}? Скажи да — отправить, нет — отменить.", "Your reply doesn't match the message. Send anyway: {preview}? Say yes to send, no to cancel."),
    "tg_sent_reply_next": ("Ответ отправлен. Дальше: от {peer}: {msg}. Предложенный: {suggested}. Да — отправить, нет — пропустить.", "Sent your reply. Next: from {peer}: {msg}. Suggested: {suggested}. Yes to send, no to skip."),
    "tg_skipped_next": ("Пропущено. Дальше: от {peer}: {msg}. Предложенный: {suggested}. Да — отправить, нет — пропустить.", "Skipped. Next: from {peer}: {msg}. Suggested: {suggested}. Yes to send, no to skip."),
    "tg_from_peer": ("От {peer}: {msg}. Предложенный ответ: {suggested}. Скажи да — отправить, нет — пропустить, или свой ответ.", "From {peer}: {msg}. Suggested reply: {suggested}. Say yes to send, no to skip, or your own reply."),
    "tg_last_from": ("Последнее сообщение от {title}. Можешь сказать: отправь ему ответ — и текст.", "Last message from {title}. You can say: send him a reply — and the text."),
    "tg_send_confirm": ("Отправить «{text}» тому кто написал? Скажи да, отправь — или один. Отмена: два.", "Send «{text}» to the one who wrote? Say yes, send — or one. Cancel: two."),
    "tg_failed_error": ("Не удалось отправить: {e}", "Failed to send: {e}"),
    "tg_new_message": ("У вас новое сообщение! От {peer}: {msg}", "You have a new message! From {peer}: {msg}"),
    "sandbox_result": ("Выполнено в песочнице. {out}", "Ran in sandbox. {out}"),
    "sandbox_done": ("Готово.", "Done."),
}


def get_feedback(key: str, **kwargs) -> str:
    """Kalit bo'yicha TTS matn. Env override: TTS_FEEDBACK_<KEY> (ru|en)."""
    env_key = f"TTS_FEEDBACK_{key.upper()}"
    override = os.getenv(env_key, "").strip()
    if override:
        try:
            return override.format(**kwargs)
        except Exception:
            return override

    pair = PHRASES.get(key)
    if not pair:
        return key

    ru, en = pair[0], pair[1]
    # NeuroKey — только русский. Английский не используется.
    text = ru

    try:
        return text.format(**kwargs)
    except KeyError:
        return text
