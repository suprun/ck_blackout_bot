import os
from datetime import datetime
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters
)

# ---- Стани діалогів ----
(
    ADD_INFO_TIME, ADD_INFO_TYPE, ADD_INFO_TEXT, ADD_INFO_PHOTO,
    ADD_INTERVAL_CHANNEL, ADD_INTERVAL_ON, ADD_INTERVAL_OFF,
    REMOVE_INFO_SELECT, REMOVE_INTERVAL_CHANNEL, REMOVE_INTERVAL_SELECT,
    BROADCAST_TYPE, BROADCAST_TEXT, BROADCAST_PHOTO, BROADCAST_CONFIRM,
    CONFIRM_RELOAD, CONFIRM_PAUSE_ALL
) = range(16)

# ---- Головне меню ----
MAIN_MENU = ReplyKeyboardMarkup(
    [
        ["⚡ Графіки", "💬 Інфо"],
        ["🔌 Канали", "📢 Розсилка"],
        ["📊 Статистика", "📡 Статус"],
        ["🕓 Історія", "⚙️ Налаштування"]
    ],
    resize_keyboard=True
)

# ---- Хелпер доступу ----
def _guard_admin(update: Update) -> bool:
    from bot import is_admin
    uid = (update.effective_user.id if update.effective_user else 0)
    return is_admin(uid)


# ---- Entry ----
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _guard_admin(update):
        return await update.message.reply_text("⛔ Немає доступу.")
    await update.message.reply_text("📋 Головне меню адміністратора:", reply_markup=MAIN_MENU)


async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _guard_admin(update):
        return await update.message.reply_text("⛔ Немає доступу.")

    text = update.message.text

    # --- Графіки ---
    if text == "⚡ Графіки":
        buttons = [
            [InlineKeyboardButton("📅 Показати графік", callback_data="show_schedule")],
            [InlineKeyboardButton("➕ Додати інтервал", callback_data="add_interval_dialog")],
            [InlineKeyboardButton("🗑️ Видалити інтервал", callback_data="remove_interval_dialog")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_main")]
        ]
        await update.message.reply_text("⚡ Керування графіками:", reply_markup=InlineKeyboardMarkup(buttons))

    # --- Інфо ---
    elif text == "💬 Інфо":
        buttons = [
            [InlineKeyboardButton("📋 Показати список", callback_data="show_info")],
            [InlineKeyboardButton("➕ Додати повідомлення", callback_data="add_info_dialog")],
            [InlineKeyboardButton("🗑️ Видалити повідомлення", callback_data="remove_info_dialog")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_main")]
        ]
        await update.message.reply_text("💬 Інформаційні повідомлення:", reply_markup=InlineKeyboardMarkup(buttons))

    # --- Канали ---
    elif text == "🔌 Канали":
        buttons = [
            [InlineKeyboardButton("⏸ Призупинити канал", callback_data="pause_channel")],
            [InlineKeyboardButton("▶️ Відновити канал", callback_data="resume_channel")],
            [InlineKeyboardButton("🔁 Відновити всі", callback_data="resume_all")],
            [InlineKeyboardButton("⚠️ Призупинити всі", callback_data="pause_all_confirm")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_main")]
        ]
        await update.message.reply_text("🔌 Керування каналами:", reply_markup=InlineKeyboardMarkup(buttons))

    # --- Розсилка ---
    elif text == "📢 Розсилка":
        buttons = [
            [InlineKeyboardButton("📝 Текст", callback_data="broadcast_text")],
            [InlineKeyboardButton("🖼 Фото", callback_data="broadcast_photo")],
            [InlineKeyboardButton("❌ Скасувати", callback_data="cancel")]
        ]
        await update.message.reply_text("📢 Оберіть тип розсилки:", reply_markup=InlineKeyboardMarkup(buttons))

    # --- Статистика ---
    elif text == "📊 Статистика":
        from bot import scheduler
        total_msgs = len(scheduler.history)
        paused = len(scheduler.paused_channels)
        await update.message.reply_text(
            f"📊 Поточна статистика:\n"
            f"📬 Відправлено: {total_msgs}\n"
            f"⏸ Каналів на паузі: {paused}\n"
            f"🕓 Останній reload: {scheduler.last_reload}"
        )

    # --- Статус ---
    elif text == "📡 Статус":
        from bot import scheduler, CHANNEL_IDS
        msg = "📡 Поточний стан каналів:\n"
        for i, ch in enumerate(CHANNEL_IDS):
            msg += f"#{i} — {'🔴 На паузі' if scheduler.is_channel_paused(ch) else '🟢 Активний'}\n"
        await update.message.reply_text(msg)

    # --- Історія ---
    elif text == "🕓 Історія":
        from bot import show_history
        await show_history(update, context)

    # --- Налаштування ---
    elif text == "⚙️ Налаштування":
        buttons = [
            [InlineKeyboardButton("🔄 Оновити графіки", callback_data="reload_confirm")],
            [InlineKeyboardButton("💾 Резервне копіювання", callback_data="backup_json")],
            [InlineKeyboardButton("🧾 Показати логи", callback_data="show_logs")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_main")]
        ]
        await update.message.reply_text("⚙️ Системні налаштування:", reply_markup=InlineKeyboardMarkup(buttons))


# ---------- CALLBACKS ----------
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _guard_admin(update):
        return await update.callback_query.answer("⛔ Немає доступу.", show_alert=True)

    q = update.callback_query
    data = q.data
    await q.answer()

    from bot import show_schedule, show_info_schedule, scheduler, CHANNEL_IDS
    from bot import pause_notifications, resume_notifications, pause_channel_cmd, resume_channel_cmd

    if data == "back_main":
        await q.message.reply_text("📋 Повернення до головного меню:", reply_markup=MAIN_MENU)

    # показ списків
    elif data == "show_schedule":
        await show_schedule(update, context)

    elif data == "show_info":
        await show_info_schedule(update, context)

    # додавання діалогів — підхоплюють ConversationHandlers (нижче)
    elif data == "add_info_dialog":
        await q.message.reply_text("🕓 Вкажіть час (HH:MM):", reply_markup=ReplyKeyboardRemove())
        return

    elif data == "add_interval_dialog":
        # початок іншого діалогу — також нижче
        return

    # видалення через діалоги (також розписано нижче)
    elif data == "remove_info_dialog":
        return

    elif data == "remove_interval_dialog":
        return

    # канали
    elif data == "resume_all":
        await resume_notifications(update, context)

    elif data == "pause_channel":
        await q.message.reply_text("Вкажіть: /pause_channel <індекс>")

    elif data == "resume_channel":
        await q.message.reply_text("Вкажіть: /resume_channel <індекс>")

    # reload/backup/logs
    elif data == "reload_confirm":
        from bot import reload_schedules
        await q.message.reply_text("🔄 Перезавантажую...")
        await reload_schedules(update, context)

    elif data == "backup_json":
        backup_dir = "backup"
        os.makedirs(backup_dir, exist_ok=True)
        done = []
        for fname in ["schedule.json", "info_schedule.json"]:
            if os.path.exists(fname):
                bname = f"{backup_dir}/{fname.split('.')[0]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                try:
                    with open(fname, "rb") as src, open(bname, "wb") as dst:
                        dst.write(src.read())
                    done.append(bname)
                except Exception:
                    pass
        await q.message.reply_text("💾 Резервні копії створено:\n" + ("\n".join(done) if done else "Немає файлів"))

    elif data == "show_logs":
        log_file = "admin_actions.log"
        if not os.path.exists(log_file):
            return await q.message.reply_text("ℹ️ Логи відсутні.")
        with open(log_file, "r", encoding="utf-8") as f:
            logs = f.read()[-3000:] or "Немає записів."
        await q.message.reply_text(f"🧾 Останні дії:\n```\n{logs}\n```", parse_mode="Markdown")

    elif data == "pause_all_confirm":
        buttons = [
            [InlineKeyboardButton("✅ Так", callback_data="pause_all_yes")],
            [InlineKeyboardButton("❌ Ні", callback_data="back_main")]
        ]
        await q.message.reply_text("⚠️ Ви впевнені, що хочете зупинити ВСІ канали?",
                                   reply_markup=InlineKeyboardMarkup(buttons))

    elif data == "pause_all_yes":
        scheduler.paused = True
        for ch in CHANNEL_IDS:
            scheduler.pause_channel(ch)
        await q.message.reply_text("⏸ Всі канали призупинено.", reply_markup=MAIN_MENU)


# ---------- ДІАЛОГИ ДОДАВАННЯ ІНФО ----------
async def add_info_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["info_time"] = update.message.text.strip()
    buttons = [
        [InlineKeyboardButton("📝 Текст", callback_data="info_type_text")],
        [InlineKeyboardButton("🖼 Фото", callback_data="info_type_photo")]
    ]
    await update.message.reply_text("Оберіть тип:", reply_markup=InlineKeyboardMarkup(buttons))
    return ADD_INFO_TYPE

async def add_info_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    tp = "text" if "text" in update.callback_query.data else "photo"
    context.user_data["info_type"] = tp
    if tp == "text":
        await update.callback_query.message.reply_text("✏️ Введіть текст:")
        return ADD_INFO_TEXT
    else:
        await update.callback_query.message.reply_text("📸 Надішліть фото з підписом:")
        return ADD_INFO_PHOTO

async def add_info_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from bot import scheduler
    scheduler.add_info_message(context.user_data["info_time"], "text", text=update.message.text.strip())
    await update.message.reply_text("✅ Додано інфо-текст.", reply_markup=MAIN_MENU)
    return ConversationHandler.END

async def add_info_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from bot import scheduler
    photo_id = update.message.photo[-1].file_id
    caption = update.message.caption or ""
    scheduler.add_info_message(context.user_data["info_time"], "photo", photo=photo_id, caption=caption)
    await update.message.reply_text("🖼 Додано інфо-фото.", reply_markup=MAIN_MENU)
    return ConversationHandler.END

# ---------- ДІАЛОГИ ДОДАВАННЯ ІНТЕРВАЛУ ----------
async def add_interval_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    from bot import CHANNEL_IDS
    buttons = [[InlineKeyboardButton(f"#{i} — {cid}", callback_data=f"interval_ch_{i}")]
               for i, cid in enumerate(CHANNEL_IDS)]
    await update.callback_query.message.reply_text("Оберіть канал:", reply_markup=InlineKeyboardMarkup(buttons))
    return ADD_INTERVAL_CHANNEL

async def add_interval_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    context.user_data["interval_idx"] = int(update.callback_query.data.split("_")[-1])
    await update.callback_query.message.reply_text("⏰ Введіть час увімкнення (HH:MM):", reply_markup=ReplyKeyboardRemove())
    return ADD_INTERVAL_ON

async def add_interval_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["interval_on"] = update.message.text.strip()
    await update.message.reply_text("⚡ Введіть час вимкнення (HH:MM):")
    return ADD_INTERVAL_OFF

async def add_interval_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from bot import scheduler, CHANNEL_IDS
    idx = context.user_data["interval_idx"]
    ch_id = CHANNEL_IDS[idx]
    on_s = context.user_data["interval_on"]
    off_s = update.message.text.strip()
    on_t = datetime.strptime(on_s, "%H:%M").time()
    off_t = datetime.strptime(off_s, "%H:%M").time()
    scheduler.channels.setdefault(ch_id, []).append({"on": on_t, "off": off_t})
    scheduler.update_schedule(scheduler.channels)
    await update.message.reply_text(f"✅ Додано інтервал для #{idx} ({ch_id}): ON {on_s} | OFF {off_s}",
                                    reply_markup=MAIN_MENU)
    return ConversationHandler.END

# ---------- ДІАЛОГ ВИДАЛЕННЯ ІНФО ----------
async def remove_info_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    from bot import scheduler
    info = scheduler.info_schedule
    if not info:
        await update.callback_query.message.reply_text("ℹ️ Немає інформаційних повідомлень.")
        return ConversationHandler.END
    buttons = []
    for i, m in enumerate(info, 1):
        pv = m.get("text") or m.get("caption") or ""
        if len(pv) > 30:
            pv = pv[:30] + "..."
        buttons.append([InlineKeyboardButton(f"{i}. {m['time']} — {pv}", callback_data=f"remove_info_{i}")])
    buttons.append([InlineKeyboardButton("❌ Скасувати", callback_data="cancel")])
    await update.callback_query.message.reply_text("🗑 Оберіть повідомлення:", reply_markup=InlineKeyboardMarkup(buttons))
    return REMOVE_INFO_SELECT

async def remove_info_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    idx = int(update.callback_query.data.split("_")[-1]) - 1
    from bot import scheduler, show_info_schedule
    info = scheduler.info_schedule
    if 0 <= idx < len(info):
        removed = info.pop(idx)
        scheduler.save_info_schedule()
        scheduler._schedule_all()
        pv = removed.get("text") or removed.get("caption") or ""
        if len(pv) > 100:
            pv = pv[:100] + "..."
        await update.callback_query.message.reply_text(f"🗑 Видалено: {removed['time']} — {pv}")
        await show_info_schedule(update, context)
    else:
        await update.callback_query.message.reply_text("⚠️ Невірний вибір.")
    return ConversationHandler.END

# ---------- ДІАЛОГ ВИДАЛЕННЯ ІНТЕРВАЛУ ----------
async def remove_interval_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    from bot import CHANNEL_IDS
    buttons = [[InlineKeyboardButton(f"#{i} — {cid}", callback_data=f"rem_ch_{i}")]
               for i, cid in enumerate(CHANNEL_IDS)]
    buttons.append([InlineKeyboardButton("❌ Скасувати", callback_data="cancel")])
    await update.callback_query.message.reply_text("Оберіть канал:", reply_markup=InlineKeyboardMarkup(buttons))
    return REMOVE_INTERVAL_CHANNEL

async def remove_interval_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    idx = int(update.callback_query.data.split("_")[-1])
    context.user_data["remove_ch_idx"] = idx
    from bot import scheduler, CHANNEL_IDS
    ch_id = CHANNEL_IDS[idx]
    intervals = scheduler.channels.get(ch_id, [])
    if not intervals:
        await update.callback_query.message.reply_text("ℹ️ Інтервалів немає.")
        return ConversationHandler.END
    buttons = []
    for j, t in enumerate(intervals, 1):
        buttons.append([InlineKeyboardButton(f"{j}. ON {t['on'].strftime('%H:%M')} | OFF {t['off'].strftime('%H:%M')}",
                                             callback_data=f"rem_iv_{j}")])
    buttons.append([InlineKeyboardButton("❌ Скасувати", callback_data="cancel")])
    await update.callback_query.message.reply_text("Обрати інтервал:", reply_markup=InlineKeyboardMarkup(buttons))
    return REMOVE_INTERVAL_SELECT

async def remove_interval_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    iv_idx = int(update.callback_query.data.split("_")[-1]) - 1
    from bot import scheduler, CHANNEL_IDS, show_schedule
    ch_idx = context.user_data["remove_ch_idx"]
    ch_id = CHANNEL_IDS[ch_idx]
    arr = scheduler.channels.get(ch_id, [])
    if 0 <= iv_idx < len(arr):
        removed = arr.pop(iv_idx)
        scheduler.update_schedule(scheduler.channels)
        await update.callback_query.message.reply_text(
            f"🗑 Видалено інтервал: ON {removed['on'].strftime('%H:%M')} | OFF {removed['off'].strftime('%H:%M')}"
        )
        await show_schedule(update, context)
    else:
        await update.callback_query.message.reply_text("⚠️ Невірний інтервал.")
    return ConversationHandler.END

# ---------- РОЗСИЛКА ВІЗАРД ----------
async def broadcast_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("📝 Текст", callback_data="br_text")],
        [InlineKeyboardButton("🖼 Фото", callback_data="br_photo")],
        [InlineKeyboardButton("❌ Скасувати", callback_data="cancel")]
    ]
    await update.message.reply_text("📢 Оберіть тип розсилки:", reply_markup=InlineKeyboardMarkup(buttons))
    return BROADCAST_TYPE

async def broadcast_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    dt = update.callback_query.data
    if dt == "br_text":
        context.user_data["br_type"] = "text"
        await update.callback_query.message.reply_text("📝 Введіть текст:")
        return BROADCAST_TEXT
    elif dt == "br_photo":
        context.user_data["br_type"] = "photo"
        await update.callback_query.message.reply_text("📸 Надішліть фото з підписом:")
        return BROADCAST_PHOTO

async def broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["br_content"] = {"text": update.message.text.strip()}
    buttons = [[InlineKeyboardButton("✅ Надіслати", callback_data="br_send")],
               [InlineKeyboardButton("❌ Скасувати", callback_data="cancel")]]
    await update.message.reply_text(f"Попередній перегляд:\n\n{context.user_data['br_content']['text']}",
                                    reply_markup=InlineKeyboardMarkup(buttons))
    return BROADCAST_CONFIRM

async def broadcast_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_id = update.message.photo[-1].file_id
    caption = update.message.caption or ""
    context.user_data["br_content"] = {"photo": photo_id, "caption": caption}
    buttons = [[InlineKeyboardButton("✅ Надіслати", callback_data="br_send")],
               [InlineKeyboardButton("❌ Скасувати", callback_data="cancel")]]
    await update.message.reply_photo(photo=photo_id, caption=f"Попередній перегляд:\n\n{caption}",
                                     reply_markup=InlineKeyboardMarkup(buttons))
    return BROADCAST_CONFIRM

async def broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    from bot import CHANNEL_IDS, app, scheduler
    tp = context.user_data.get("br_type")
    data = context.user_data.get("br_content", {})
    if tp == "text":
        txt = data.get("text", "")
        for ch in CHANNEL_IDS:
            try:
                await app.bot.send_message(ch, txt)
                scheduler.add_to_history(ch, "broadcast", txt)
            except Exception as e:
                print(f"⚠️ Помилка у {ch}: {e}")
        await update.callback_query.message.reply_text("✅ Розсилку завершено.", reply_markup=MAIN_MENU)
    else:
        photo = data.get("photo")
        caption = data.get("caption", "")
        for ch in CHANNEL_IDS:
            try:
                await app.bot.send_photo(ch, photo=photo, caption=caption)
                scheduler.add_to_history(ch, "broadcast_photo", caption)
            except Exception as e:
                print(f"⚠️ Помилка у {ch}: {e}")
        await update.callback_query.message.reply_text("✅ Фото-розсилку завершено.", reply_markup=MAIN_MENU)
    return ConversationHandler.END

# ---------- Скасування ----------
async def cancel_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text("❌ Скасовано.", reply_markup=MAIN_MENU)
        else:
            await update.message.reply_text("❌ Скасовано.", reply_markup=MAIN_MENU)
    except Exception:
        pass
    return ConversationHandler.END

# ---------- Реєстрація в app ----------
def register_admin_menu(app):
    # головне меню
    app.add_handler(CommandHandler("menu", show_main_menu))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu))
    # базові callback-и
    app.add_handler(CallbackQueryHandler(handle_callback))

    # діалог: додати інфо
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(lambda u, c: None, pattern="^add_info_dialog$"),
                      MessageHandler(filters.Regex("^$"), lambda u, c: None)],
        states={
            ADD_INFO_TYPE: [CallbackQueryHandler(add_info_type, pattern="^info_type_")],
            ADD_INFO_TIME: [MessageHandler(filters.TEXT, add_info_time)],
            ADD_INFO_TEXT: [MessageHandler(filters.TEXT, add_info_text)],
            ADD_INFO_PHOTO: [MessageHandler(filters.PHOTO, add_info_photo)],
        },
        fallbacks=[CallbackQueryHandler(cancel_dialog, pattern="^cancel$")],
        map_to_parent={}
    ))
    # тригер на "add_info_dialog"
    app.add_handler(CallbackQueryHandler(lambda u, c: add_info_time(u, c), pattern="^add_info_dialog$"))

    # діалог: додати інтервал
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(add_interval_start, pattern="^add_interval_dialog$")],
        states={
            ADD_INTERVAL_CHANNEL: [CallbackQueryHandler(add_interval_channel, pattern="^interval_ch_\\d+$")],
            ADD_INTERVAL_ON: [MessageHandler(filters.TEXT, add_interval_on)],
            ADD_INTERVAL_OFF: [MessageHandler(filters.TEXT, add_interval_off)],
        },
        fallbacks=[CallbackQueryHandler(cancel_dialog, pattern="^cancel$")]
    ))

    # діалог: видалити інфо
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(remove_info_start, pattern="^remove_info_dialog$")],
        states={REMOVE_INFO_SELECT: [CallbackQueryHandler(remove_info_select, pattern="^remove_info_\\d+$")]},
        fallbacks=[CallbackQueryHandler(cancel_dialog, pattern="^cancel$")]
    ))

    # діалог: видалити інтервал
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(remove_interval_start, pattern="^remove_interval_dialog$")],
        states={
            REMOVE_INTERVAL_CHANNEL: [CallbackQueryHandler(remove_interval_channel, pattern="^rem_ch_\\d+$")],
            REMOVE_INTERVAL_SELECT: [CallbackQueryHandler(remove_interval_select, pattern="^rem_iv_\\d+$")],
        },
        fallbacks=[CallbackQueryHandler(cancel_dialog, pattern="^cancel$")]
    ))

    # розсилка-візард (через натискання "📢 Розсилка" в головному меню)
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📢 Розсилка$"), lambda u, c: broadcast_entry(u, c))],
        states={
            BROADCAST_TYPE: [CallbackQueryHandler(broadcast_type, pattern="^br_")],
            BROADCAST_TEXT: [MessageHandler(filters.TEXT, broadcast_text)],
            BROADCAST_PHOTO: [MessageHandler(filters.PHOTO, broadcast_photo)],
            BROADCAST_CONFIRM: [CallbackQueryHandler(broadcast_send, pattern="^br_send$")],
        },
        fallbacks=[CallbackQueryHandler(cancel_dialog, pattern="^cancel$")]
    ))
