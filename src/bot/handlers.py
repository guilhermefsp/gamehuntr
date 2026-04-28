from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from src import services


async def preco(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # CommandHandler populates context.args; MessageHandler (for /preço) does not
    if context.args:
        query = " ".join(context.args)
    else:
        text = update.message.text or ""
        parts = text.split(maxsplit=1)
        query = parts[1] if len(parts) > 1 else ""

    if not query:
        await update.message.reply_text("Uso: /preço <nome do jogo>")
        return
    msg = await update.message.reply_text(f"Buscando preço de *{query}*...", parse_mode="Markdown")

    result = await services.get_price(query)

    if not result:
        await msg.edit_text(f"Jogo *{query}* não encontrado.", parse_mode="Markdown")
        return

    text = _format_price_message(result)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Resultado errado?", callback_data=f"fix:{result['ludopedia_id']}:{query}")]
    ])
    await msg.edit_text(text, parse_mode="Markdown", reply_markup=keyboard, disable_web_page_preview=True)


async def fix_asin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    _, ludopedia_id, search_term = query.data.split(":", 2)
    alternatives = await services.get_amazon_alternatives(search_term)

    if not alternatives:
        await query.edit_message_reply_markup(None)
        await query.message.reply_text("Não encontrei alternativas na Amazon.")
        return

    buttons = [
        [InlineKeyboardButton(
            f"{a['title'][:50]} — R$ {a['price_brl']:.2f}" if a['price_brl'] else a['title'][:60],
            callback_data=f"setalternative:{ludopedia_id}:{a['asin']}"
        )]
        for a in alternatives
    ]
    buttons.append([InlineKeyboardButton("Cancelar", callback_data="cancel")])
    await query.edit_message_reply_markup(InlineKeyboardMarkup(buttons))


async def set_asin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    _, ludopedia_id, asin = query.data.split(":")
    await services.update_asin(int(ludopedia_id), asin)
    await query.edit_message_reply_markup(None)
    await query.message.reply_text("ASIN corrigido. Use /preço novamente para ver o resultado atualizado.")


async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    await update.callback_query.edit_message_reply_markup(None)


def _format_price_message(result: dict) -> str:
    lines = [f"🎲 *{result['title']}*\n"]

    # Ludopedia C2C
    if result.get("c2c_avg") is not None:
        lines.append(
            f"C2C Novo: R$ {result['c2c_avg']:.2f} média ({result['c2c_count']} anúncios)"
            + (f" — [ver anúncios]({result['c2c_url']})" if result.get("c2c_url") else "")
        )
    elif result.get("c2c_url"):
        lines.append(f"C2C: sem anúncios Novo — [ver anúncios]({result['c2c_url']})")

    # Amazon
    price_str = f"R$ {result['price_brl']:.2f}" if result["price_brl"] else "Preço indisponível"
    stock_str = "✅" if result["in_stock"] else "❌"
    amazon_line = f"Amazon: {price_str} {stock_str}"
    if result.get("url"):
        amazon_line += f" — [comprar]({result['url']})"
    lines.append(amazon_line)

    # Lowest ever
    if result.get("lowest_ever"):
        lines.append(f"📉 Menor histórico: R$ {result['lowest_ever']:.2f}")
    else:
        lines.append("📉 Menor histórico: primeiro registro")

    return "\n".join(lines)


def register(application) -> None:
    application.add_handler(CommandHandler("preco", preco))
    # Telegram only allows ASCII command names, so /preço can't be a CommandHandler.
    # Catch it as a text message instead so users who type /preço still get a response.
    from telegram.ext import MessageHandler, filters
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r"^/preço"), preco
    ))
    application.add_handler(CallbackQueryHandler(fix_asin_callback, pattern=r"^fix:"))
    application.add_handler(CallbackQueryHandler(set_asin_callback, pattern=r"^setalternative:"))
    application.add_handler(CallbackQueryHandler(cancel_callback, pattern=r"^cancel$"))
