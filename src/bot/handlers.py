from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from src import services


async def preco(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Uso: /preco <nome do jogo>")
        return

    query = " ".join(context.args)
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
    await query.message.reply_text("ASIN corrigido. Use /preco novamente para ver o resultado atualizado.")


async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    await update.callback_query.edit_message_reply_markup(None)


def _format_price_message(result: dict) -> str:
    price_str = f"R$ {result['price_brl']:.2f}" if result['price_brl'] else "Preço indisponível"
    stock_str = "✅ Em estoque" if result['in_stock'] else "❌ Fora de estoque"
    lowest_str = (
        f"\n📉 Menor preço histórico: R$ {result['lowest_ever']:.2f}"
        if result.get('lowest_ever')
        else "\n📉 Menor preço histórico: primeiro registro"
    )

    return (
        f"🎲 *{result['title']}*\n\n"
        f"Amazon: {price_str} {stock_str}\n"
        f"[Comprar na Amazon]({result['url']})"
        f"{lowest_str}"
    )


def register(application) -> None:
    application.add_handler(CommandHandler("preco", preco))
    application.add_handler(CallbackQueryHandler(fix_asin_callback, pattern=r"^fix:"))
    application.add_handler(CallbackQueryHandler(set_asin_callback, pattern=r"^setalternative:"))
    application.add_handler(CallbackQueryHandler(cancel_callback, pattern=r"^cancel$"))
