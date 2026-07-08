import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from src import services

logger = logging.getLogger(__name__)

WELCOME = (
    "🎲 *GameHuntr* — preços de jogos de tabuleiro no Brasil.\n\n"
    "Envie /preço com o nome de um jogo e receba o preço na Amazon, "
    "os anúncios do mercado da Ludopedia e o menor preço já registrado.\n\n"
    "*Comandos:*\n"
    "/preço <jogo> — busca preços (ex: `/preço Wingspan`)\n"
    "/preço <link> — também aceita links da Ludopedia ou do BoardGameGeek\n"
    "/help — mostra esta mensagem"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await services.record_user(update.effective_user)
    await update.message.reply_text(WELCOME, parse_mode="Markdown")


async def preco(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await services.record_user(update.effective_user)

    # CommandHandler populates context.args; MessageHandler (for /preço) does not
    if context.args:
        query = " ".join(context.args)
    else:
        text = update.message.text or ""
        parts = text.split(maxsplit=1)
        query = parts[1] if len(parts) > 1 else ""

    if not query:
        await update.message.reply_text("Uso: /preço <nome do jogo ou link>")
        return
    msg = await update.message.reply_text(f"Buscando preço de {query}...")

    result = await services.get_price(query)

    if not result:
        await msg.edit_text(f"Jogo {query} não encontrado.")
        return

    # A URL is useless as a re-search term in the callbacks — use the resolved title
    cb_query = result["title"] if query.lower().startswith("http") else query
    await _send_price_reply(update.message, msg, result, cb_query)


async def _send_price_reply(message, status_msg, result: dict, cb_query: str) -> None:
    """Send the price result as a photo with caption; fall back to text when the
    game has no thumbnail or Telegram can't fetch it."""
    caption = _format_price_message(result)
    keyboard = _price_keyboard(result, cb_query)

    if result.get("thumbnail"):
        try:
            await message.reply_photo(
                photo=result["thumbnail"],
                caption=caption,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
            if status_msg:
                await status_msg.delete()
            return
        except Exception as e:
            logger.warning("send_photo failed for %s (%s); falling back to text", result["title"], e)

    if status_msg:
        await status_msg.edit_text(caption, parse_mode="Markdown", reply_markup=keyboard, disable_web_page_preview=True)
    else:
        await message.reply_text(caption, parse_mode="Markdown", reply_markup=keyboard, disable_web_page_preview=True)


def _truncate_for_callback(text: str, max_bytes: int = 42) -> str:
    """callback_data is limited to 64 bytes total — keep the query part within budget."""
    return text.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")


def _price_keyboard(result: dict, cb_query: str) -> InlineKeyboardMarkup:
    q = _truncate_for_callback(cb_query)
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Jogo errado?", callback_data=f"wrong:{result['ludopedia_id']}:{q}"),
            InlineKeyboardButton("Resultado errado?", callback_data=f"fix:{result['ludopedia_id']}:{q}"),
        ]
    ])


async def wrong_game_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await services.record_user(update.effective_user)

    _, current_id, search_term = query.data.split(":", 2)
    alternatives = await services.search_alternatives(search_term, exclude_id=int(current_id))

    if not alternatives:
        await query.message.reply_text("Não encontrei outros jogos com esse nome.")
        return

    buttons = [
        [InlineKeyboardButton(_alternative_label(a), callback_data=f"pick:{a['ludopedia_id']}")]
        for a in alternatives
    ]
    buttons.append([InlineKeyboardButton("Cancelar", callback_data="cancel")])
    markup = InlineKeyboardMarkup(buttons)

    thumb = alternatives[0].get("thumbnail")
    text = "Talvez você quis dizer:"
    if thumb:
        try:
            await query.message.reply_photo(photo=thumb, caption=text, reply_markup=markup)
            return
        except Exception as e:
            logger.warning("send_photo failed for disambiguation (%s); falling back to text", e)
    await query.message.reply_text(text, reply_markup=markup)


def _alternative_label(alt: dict) -> str:
    label = f"{alt['title']} ({alt['year']})" if alt.get("year") else alt["title"]
    return label[:60]


async def pick_game_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await services.record_user(update.effective_user)

    ludopedia_id = int(query.data.split(":", 1)[1])
    status = await query.message.reply_text("Buscando preço...")
    result = await services.get_price_by_id(ludopedia_id)

    if not result:
        await status.edit_text("Não consegui buscar esse jogo. Tente novamente.")
        return

    # Retire the disambiguation buttons so the same list isn't clicked twice
    try:
        await query.edit_message_reply_markup(None)
    except Exception:
        pass

    await _send_price_reply(query.message, status, result, result["title"])


async def fix_asin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await services.record_user(update.effective_user)

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
    await services.record_user(update.effective_user)

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
    url_suffix = f" — [ver anúncios]({result['c2c_url']})" if result.get("c2c_url") else ""
    has_novo = result.get("c2c_novo_min") is not None
    has_used = result.get("c2c_used_min") is not None
    if has_novo:
        lines.append(f"C2C Novo: R$ {result['c2c_novo_min']:.2f} min ({result['c2c_novo_count']} anúncios){url_suffix}")
    if has_used:
        lines.append(f"C2C Usado: R$ {result['c2c_used_min']:.2f} min ({result['c2c_used_count']} anúncios)")
    if not has_novo and not has_used and result.get("c2c_url"):
        lines.append(f"C2C: Esse jogo não tem anúncios no momento{url_suffix}")

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

    # BGG enrichment
    bgg_parts = []
    if result.get("bgg_rating"):
        bgg_parts.append(f"⭐ {result['bgg_rating']:.1f}")
    if result.get("bgg_weight"):
        bgg_parts.append(f"🧠 {result['bgg_weight']:.1f}/5")
    if bgg_parts:
        lines.append(" · ".join(bgg_parts))

    return "\n".join(lines)


def register(application) -> None:
    application.add_handler(CommandHandler(["start", "help"], start))
    application.add_handler(CommandHandler("preco", preco))
    # Telegram only allows ASCII command names, so /preço can't be a CommandHandler.
    # Catch it as a text message instead so users who type /preço still get a response.
    from telegram.ext import MessageHandler, filters
    application.add_handler(MessageHandler(filters.Regex(r"^/preço"), preco))
    application.add_handler(CallbackQueryHandler(wrong_game_callback, pattern=r"^wrong:"))
    application.add_handler(CallbackQueryHandler(pick_game_callback, pattern=r"^pick:"))
    application.add_handler(CallbackQueryHandler(fix_asin_callback, pattern=r"^fix:"))
    application.add_handler(CallbackQueryHandler(set_asin_callback, pattern=r"^setalternative:"))
    application.add_handler(CallbackQueryHandler(cancel_callback, pattern=r"^cancel$"))
