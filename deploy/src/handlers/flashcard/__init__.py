"""
Flashcard Handler - Database bilan ishlaydigan versiya
SM-2 Spaced Repetition algoritmi bilan
"""
import random
from datetime import datetime, date
from typing import Optional, List, Dict, Any

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.database import get_session
from src.database.models import User, FlashcardDeck, Flashcard, UserFlashcard
from src.repositories import (
    DailyLimitManager,
    DifficultCardsManager,
    SRTuningManager,
    FlashcardExportImport,
    DeckPurchaseRepository,
    ExtendedStatsManager,
    FlashcardDeckRepository,
    FlashcardRepository,
    UserFlashcardRepository,
    UserDeckProgressRepository,
    LanguageRepository
)
from src.core.logging import get_logger
from src.services.xp_service import XPService
from src.services.tts_service import generate_audio

logger = get_logger(__name__)
router = Router(name="flashcard")


class FlashcardStates(StatesGroup):
    """Flashcard FSM states"""
    selecting_deck = State()
    studying = State()
    reviewing = State()
    adding_example = State()


# ============================================================
# KEYBOARDS
# ============================================================

def flashcard_menu_keyboard() -> InlineKeyboardMarkup:
    """Flashcard menu keyboard"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📚 O'rganishni boshlash", callback_data="fc:decks")
    )
    builder.row(
        InlineKeyboardButton(text="🔄 Takrorlash", callback_data="fc:review"),
        InlineKeyboardButton(text="📊 Statistika", callback_data="fc:stats")
    )
    builder.row(
        InlineKeyboardButton(text="🔴 Qiyin so'zlar", callback_data="fc:difficult"),
        InlineKeyboardButton(text="📦 Arxiv", callback_data="fc:arxiv")
    )
    builder.row(
        InlineKeyboardButton(text="📤 Export", callback_data="fc:export")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="menu:main")
    )
    return builder.as_markup()


def deck_list_keyboard(decks: List[FlashcardDeck]) -> InlineKeyboardMarkup:
    """Deck ro'yxati keyboard"""
    builder = InlineKeyboardBuilder()
    
    for deck in decks:
        icon = deck.icon if hasattr(deck, 'icon') and deck.icon else "📚"
        premium = "⭐ " if deck.is_premium else ""
        builder.row(
            InlineKeyboardButton(
                text=f"{icon} {premium}{deck.name} ({deck.cards_count} ta)",
                callback_data=f"fc:deck:{deck.id}"
            )
        )
    
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="flashcard:menu")
    )
    return builder.as_markup()


def study_keyboard(show_back: bool = False, card_index: int = 0, total: int = 0) -> InlineKeyboardMarkup:
    """O'rganish keyboard"""
    builder = InlineKeyboardBuilder()
    
    if not show_back:
        builder.row(
            InlineKeyboardButton(text="🔄 Javobni ko'rsat", callback_data="fc:flip")
        )
    else:
        builder.row(
            InlineKeyboardButton(text="❌ Bilmadim", callback_data="fc:answer:0"),
            InlineKeyboardButton(text="🤔 Qiyin", callback_data="fc:answer:3")
        )
        builder.row(
            InlineKeyboardButton(text="✅ Bildim", callback_data="fc:answer:4"),
            InlineKeyboardButton(text="💯 Oson", callback_data="fc:answer:5")
        )
        builder.row(
            InlineKeyboardButton(text="✏️ Misol qo'shish", callback_data="fc:add_example")
        )
    
    builder.row(
        InlineKeyboardButton(text="🔊", callback_data="fc:audio"),
        InlineKeyboardButton(text=f"📍 {card_index + 1}/{total}", callback_data="noop"),
        InlineKeyboardButton(text="⏭ O'tkazish", callback_data="fc:skip")
    )
    builder.row(
        InlineKeyboardButton(text="🏁 Tugatish", callback_data="fc:finish")
    )
    
    return builder.as_markup()


# ============================================================
# HANDLERS
# ============================================================

@router.callback_query(F.data == "flashcard:menu")
async def flashcard_menu(callback: CallbackQuery, state: FSMContext):
    """Flashcard asosiy menu"""
    await state.clear()
    
    # Statistika olish
    user_id = callback.from_user.id
    stats_text = ""
    
    try:
        async with get_session() as session:
            user_fc_repo = UserFlashcardRepository(session)
            stats = await user_fc_repo.get_user_card_stats(user_id)
            
            if stats["total_cards"] > 0:
                stats_text = f"""
📊 <b>Sizning progressingiz:</b>
- O'rganilgan: {stats['learned']} ta
- O'rganilmoqda: {stats['learning']} ta
- Bugun takrorlash: {stats['due_today']} ta
- Aniqlik: {stats['accuracy']:.1f}%
"""
    except Exception as e:
        logger.error(f"Stats error: {e}")
    
    text = f"""
🃏 <b>Flashcards</b>

So'zlarni kartochkalar yordamida o'rganing!

<b>Qanday ishlaydi:</b>
1. Deck tanlang
2. Kartochka ko'rsatiladi
3. Javobni eslang va "Ko'rsat" bosing
4. O'zingizni baholang (Bildim/Bilmadim)
5. SM-2 algoritmi takrorlashni rejalashtiradi
{stats_text}
"""
    
    await callback.message.edit_text(text, reply_markup=flashcard_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "flashcard:start")
async def flashcard_start(callback: CallbackQuery, state: FSMContext, db_user: User):
    """Redirect to decks - start learning"""
    callback.data = "fc:decks"
    await show_decks(callback, state, db_user)


@router.callback_query(F.data.startswith("flashcard:start:"))
async def flashcard_start_deck(callback: CallbackQuery, state: FSMContext, db_user: User):
    """Start flashcard with specific deck - from shop"""
    deck_id = int(callback.data.split(":")[-1])
    user_id = callback.from_user.id

    async with get_session() as session:
        deck_repo = FlashcardDeckRepository(session)
        card_repo = FlashcardRepository(session)
        purchase_repo = DeckPurchaseRepository(session)

        deck = await deck_repo.get_by_id(deck_id)
        if not deck:
            await callback.answer("❌ Deck topilmadi!", show_alert=True)
            return

        # Check access
        has_access = await purchase_repo.has_deck_access(user_id, deck_id)
        if not has_access:
            await callback.answer("🔒 Bu deckni avval sotib oling!", show_alert=True)
            return

        # Get cards
        cards = await card_repo.get_deck_cards(deck_id, limit=20)

    if not cards:
        await callback.answer("❌ Bu deckda kartochkalar yo'q!", show_alert=True)
        return

    # Prepare cards
    cards_data = []
    for card in cards:
        cards_data.append({
            "id": card.id,
            "front": card.front_text,
            "back": card.back_text,
            "example": card.example_sentence or "",
            "front_audio": card.front_audio_url,
            "back_audio": card.back_audio_url
        })

    random.shuffle(cards_data)

    await state.update_data(
        deck_id=deck_id,
        deck_name=deck.name,
        cards=cards_data,
        current_index=0,
        correct_count=0,
        wrong_count=0,
        show_back=False,
        start_time=datetime.utcnow().isoformat()
    )
    await state.set_state(FlashcardStates.studying)

    await send_flashcard(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "flashcard:decks")
async def flashcard_decks(callback: CallbackQuery, state: FSMContext, db_user: User):
    """Redirect to decks"""
    callback.data = "fc:decks"
    await show_decks(callback, state, db_user)


@router.callback_query(F.data == "flashcard:progress")
async def flashcard_progress(callback: CallbackQuery, db_user: User):
    """Redirect to stats"""
    await show_stats(callback, db_user)


@router.callback_query(F.data == "fc:decks")
async def show_decks(callback: CallbackQuery, state: FSMContext, db_user: User):
    """Deck ro'yxati - Darajalar bo'yicha"""
    from src.database.models import Level
    from src.database.models.language import Day
    from sqlalchemy import select, func

    level_icons = {
        "A1": "🟢", "A2": "🟡", "B1": "🔵",
        "B2": "🟣", "C1": "🟠", "C2": "🔴"
    }

    text = """
🃏 <b>SO'Z KARTALARI</b>

<i>Darajani tanlang va mavzularni o'rganing!</i>

"""

    builder = InlineKeyboardBuilder()

    async with get_session() as session:
        from src.repositories.topic_purchase_repo import TopicPurchaseRepository
        topic_repo = TopicPurchaseRepository(session)

        # Get levels with active decks
        result = await session.execute(
            select(Level).where(Level.is_active == True).order_by(Level.display_order)
        )
        levels = result.scalars().all()

        # User accessible day IDs (free + purchased)
        free_day_ids = set(await topic_repo.get_free_day_ids())
        purchased_day_ids = set(await topic_repo.get_purchased_day_ids(db_user.user_id))
        accessible_ids = free_day_ids | purchased_day_ids

        for level in levels:
            # Count system decks in this level (exclude user personal decks)
            deck_count_result = await session.execute(
                select(func.count(FlashcardDeck.id)).where(
                    FlashcardDeck.level_id == level.id,
                    FlashcardDeck.is_active == True,
                    FlashcardDeck.owner_id == None
                )
            )
            deck_count = deck_count_result.scalar() or 0

            if deck_count == 0:
                continue

            # Count accessible decks (linked to accessible days)
            accessible_count_result = await session.execute(
                select(func.count(FlashcardDeck.id)).where(
                    FlashcardDeck.level_id == level.id,
                    FlashcardDeck.is_active == True,
                    FlashcardDeck.owner_id == None,
                    FlashcardDeck.day_id.in_(accessible_ids) if accessible_ids else FlashcardDeck.id == -1
                )
            )
            accessible_count = accessible_count_result.scalar() or 0

            icon = level_icons.get(level.name.upper().split()[0], "📚")

            if accessible_count == deck_count and deck_count > 0:
                status = "✅"
            elif accessible_count > 0:
                status = f"📊 {accessible_count}/{deck_count}"
            else:
                status = f"📚 {deck_count} ta"

            builder.row(InlineKeyboardButton(
                text=f"{icon} {level.name} — {status}",
                callback_data=f"fc:level:{level.id}"
            ))

    builder.row(InlineKeyboardButton(text="🛒 Do'kon", callback_data="shop:decks"))
    builder.row(InlineKeyboardButton(text="◀️ Orqaga", callback_data="flashcard:menu"))

    await state.set_state(FlashcardStates.selecting_deck)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("fc:level:"))
async def show_level_decks(callback: CallbackQuery, state: FSMContext, db_user: User):
    """Daraja ichidagi mavzular (Day) - flashcard decklar bilan"""
    from src.database.models import Level
    from src.database.models.language import Day
    from sqlalchemy import select

    level_id = int(callback.data.split(":")[-1])

    level_icons = {
        "A1": "🟢", "A2": "🟡", "B1": "🔵",
        "B2": "🟣", "C1": "🟠", "C2": "🔴"
    }

    async with get_session() as session:
        from src.repositories.topic_purchase_repo import TopicPurchaseRepository
        topic_repo = TopicPurchaseRepository(session)

        # Get level
        level_result = await session.execute(
            select(Level).where(Level.id == level_id)
        )
        level = level_result.scalar_one_or_none()

        if not level:
            await callback.answer("❌ Daraja topilmadi!", show_alert=True)
            return

        icon = level_icons.get(level.name.upper().split()[0], "📚")

        # Get system decks in this level (exclude user personal decks)
        decks_result = await session.execute(
            select(FlashcardDeck).where(
                FlashcardDeck.level_id == level_id,
                FlashcardDeck.is_active == True,
                FlashcardDeck.owner_id == None
            ).order_by(FlashcardDeck.display_order)
        )
        decks = decks_result.scalars().all()

        # Get purchased day IDs
        purchased_ids = set(await topic_repo.get_purchased_day_ids(db_user.user_id))

        text = f"""
{icon} <b>{level.name.upper()} — So'z Kartalari</b>

<i>Mavzuni tanlang va o'rganishni boshlang!</i>

✅ = Ochilgan | 🆓 = Bepul | 🔒 = Premium

"""

        builder = InlineKeyboardBuilder()

        for deck in decks:
            # Check access via day
            if deck.day_id:
                day_result = await session.execute(
                    select(Day).where(Day.id == deck.day_id)
                )
                day = day_result.scalar_one_or_none()

                is_purchased = deck.day_id in purchased_ids
                is_free = day and not day.is_premium and day.price == 0

                if is_purchased or is_free:
                    status = "✅"
                    cb = f"fc:deck:{deck.id}"
                else:
                    status = "🔒"
                    cb = f"fc:deck_locked:{deck.id}"

                display = day.display_name if day else deck.name
            else:
                # Deck without day link - use old logic
                if not deck.is_premium:
                    status = "✅"
                    cb = f"fc:deck:{deck.id}"
                else:
                    status = "🔒"
                    cb = f"fc:deck_locked:{deck.id}"
                display = deck.name

            builder.row(InlineKeyboardButton(
                text=f"{status} {display} ({deck.cards_count} ta)",
                callback_data=cb
            ))

        if not decks:
            text += "\n<i>Bu darajada decklar yo'q.</i>\n"

    builder.row(InlineKeyboardButton(text="◀️ Orqaga", callback_data="fc:decks"))

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("fc:deck_locked:"))
async def deck_locked(callback: CallbackQuery):
    """Premium deck - sotib olish kerak"""
    await callback.answer(
        "🔒 Bu mavzuni avval do'kondan sotib oling!",
        show_alert=True
    )



@router.callback_query(F.data.startswith("fc:deck:"))
async def select_deck(callback: CallbackQuery, state: FSMContext, db_user: User):
    """Deck tanlash va o'rganishni boshlash"""
    deck_id = int(callback.data.split(":")[-1])
    user_id = callback.from_user.id
    
    async with get_session() as session:
        deck_repo = FlashcardDeckRepository(session)
        card_repo = FlashcardRepository(session)
        
        deck = await deck_repo.get_by_id(deck_id)
        if not deck:
            await callback.answer("❌ Deck topilmadi!", show_alert=True)
            return
        
        # Premium tekshirish
        if deck.is_premium and not getattr(db_user, 'is_premium', False):
            await callback.answer("⭐ Bu deck faqat Premium uchun!", show_alert=True)
            return
        
        # Kartochkalarni olish
        cards = await card_repo.get_deck_cards(deck_id, limit=20)
    
    if not cards:
        await callback.answer("❌ Bu deckda kartochkalar yo'q!", show_alert=True)
        return
    
    # Kartochkalarni aralashtirish
    cards_data = []
    for card in cards:
        cards_data.append({
            "id": card.id,
            "front": card.front_text,
            "back": card.back_text,
            "example": card.example_sentence or "",
            "front_audio": card.front_audio_url,
            "back_audio": card.back_audio_url
        })
    
    random.shuffle(cards_data)
    
    # State ga saqlash
    await state.update_data(
        deck_id=deck_id,
        deck_name=deck.name,
        cards=cards_data,
        current_index=0,
        correct_count=0,
        wrong_count=0,
        show_back=False,
        start_time=datetime.utcnow().isoformat()
    )
    await state.set_state(FlashcardStates.studying)
    
    # Birinchi kartochkani ko'rsatish
    await send_flashcard(callback.message, state)
    await callback.answer()


async def send_flashcard(message, state: FSMContext):
    """Joriy kartochkani ko'rsatish"""
    data = await state.get_data()
    cards = data.get("cards", [])
    index = data.get("current_index", 0)
    show_back = data.get("show_back", False)
    
    if index >= len(cards):
        await show_results(message, state)
        return
    
    card = cards[index]
    
    if show_back:
        text = f"""
🃏 <b>Flashcard</b>

<b>🔤 {card['front']}</b>

━━━━━━━━━━━━━━━

<b>✅ {card['back']}</b>
"""
        if card.get('example'):
            text += f"\n💡 <i>Misol: {card['example']}</i>"
        
        text += "\n\n<b>Qanchalik yaxshi bildingiz?</b>"
    else:
        text = f"""
🃏 <b>Flashcard</b>

<b>🔤 {card['front']}</b>

❓ <i>Bu nima?</i>
"""
    
    try:
        await message.edit_text(
            text,
            reply_markup=study_keyboard(show_back, index, len(cards))
        )
    except Exception:
        await message.answer(
            text,
            reply_markup=study_keyboard(show_back, index, len(cards))
        )


@router.callback_query(F.data == "fc:flip", FlashcardStates.studying)
async def flip_card(callback: CallbackQuery, state: FSMContext):
    """Kartochkani aylantirish"""
    await state.update_data(show_back=True)
    await send_flashcard(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "fc:audio", FlashcardStates.studying)
async def play_audio(callback: CallbackQuery, state: FSMContext):
    """Kartochka so'zini ovozda tinglash"""
    from aiogram.types import FSInputFile
    
    data = await state.get_data()
    cards = data.get("cards", [])
    index = data.get("current_index", 0)
    show_back = data.get("show_back", False)
    
    if index >= len(cards):
        await callback.answer("❌ Kartochka topilmadi", show_alert=True)
        return
    
    card = cards[index]
    
    # Front yoki back ni o'qish
    text = card["back"] if show_back else card["front"]
    # Emoji va belgilarni tozalash
    text = text.replace("🔴 ", "").strip()
    
    await callback.answer("🔊 Audio tayyorlanmoqda...")
    
    # Audio yaratish (nemis tili)
    audio_path = await generate_audio(text, lang="de")
    
    if audio_path:
        try:
            audio_file = FSInputFile(audio_path)
            await callback.message.answer_voice(audio_file)
        except Exception as e:
            logger.error(f"Audio send error: {e}")
            await callback.message.answer("❌ Audio yuborishda xatolik")
    else:
        await callback.message.answer("❌ Audio yaratishda xatolik")


@router.callback_query(F.data.startswith("fc:answer:"), FlashcardStates.studying)
async def answer_card(callback: CallbackQuery, state: FSMContext):
    """Javobni baholash"""
    quality = int(callback.data.split(":")[-1])
    user_id = callback.from_user.id
    
    data = await state.get_data()
    cards = data.get("cards", [])
    index = data.get("current_index", 0)
    
    if index >= len(cards):
        await show_results(callback.message, state)
        return
    
    card = cards[index]
    
    # Progress yangilash
    try:
        async with get_session() as session:
            user_fc_repo = UserFlashcardRepository(session)
            await user_fc_repo.update_after_review(
                user_id=user_id,
                flashcard_id=card["id"],
                quality=quality
            )
            # Kunlik limit counterni yangilash
            limit_manager = DailyLimitManager(session)
            deck_id = data.get("deck_id") or 0
            await limit_manager.increment_review(user_id, deck_id)
            
            # XP berish
            xp_earned, level_up = await XPService.reward_flashcard_answer(user_id, quality)
    except Exception as e:
        logger.error(f"Progress update error: {e}")
    
    # Statistika yangilash
    correct_count = data.get("correct_count", 0)
    wrong_count = data.get("wrong_count", 0)
    
    if quality >= 3:
        correct_count += 1
        await callback.answer("✅ Yaxshi!")
    else:
        wrong_count += 1
        await callback.answer("📝 Takrorlash kerak")
    
    # Keyingi kartochka
    await state.update_data(
        current_index=index + 1,
        correct_count=correct_count,
        wrong_count=wrong_count,
        show_back=False
    )
    
    await send_flashcard(callback.message, state)


@router.callback_query(F.data == "fc:add_example", FlashcardStates.studying)
async def add_example_start(callback: CallbackQuery, state: FSMContext):
    """Misol qo'shishni boshlash"""
    data = await state.get_data()
    cards = data.get("cards", [])
    index = data.get("current_index", 0)
    
    if index >= len(cards):
        await callback.answer("❌ Kartochka topilmadi", show_alert=True)
        return
    
    card = cards[index]
    
    await state.set_state(FlashcardStates.adding_example)
    await state.update_data(example_card_id=card["id"])
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data="fc:cancel_example")
    )
    
    await callback.message.edit_text(
        f"✏️ <b>Misol qo'shish</b>\n\n"
        f"<b>So'z:</b> {card['front']}\n"
        f"<b>Tarjima:</b> {card['back']}\n\n"
        f"Ushbu so'z uchun misol yoki kontekst yozing:\n"
        f"<i>(Masalan: \"Ich lerne Deutsch\" - Men nemis tilini o'rganaman)</i>",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.message(FlashcardStates.adding_example)
async def save_example(message, state: FSMContext):
    """Misolni saqlash"""
    example_text = message.text.strip()
    
    if len(example_text) > 500:
        await message.answer("❌ Misol juda uzun (max 500 belgi)")
        return
    
    data = await state.get_data()
    card_id = data.get("example_card_id")
    
    if not card_id:
        await message.answer("❌ Kartochka topilmadi")
        await state.set_state(FlashcardStates.studying)
        return
    
    try:
        async with get_session() as session:
            card_repo = FlashcardRepository(session)
            card = await card_repo.get_by_id(card_id)
            if card:
                card.example_sentence = example_text
                await session.commit()
        
        # State'dagi cards ni yangilash
        cards = data.get("cards", [])
        for c in cards:
            if c["id"] == card_id:
                c["example"] = example_text
                break
        
        await state.update_data(cards=cards)
        await state.set_state(FlashcardStates.studying)
        
        await message.answer("✅ Misol saqlandi!")
        
        # Kartochkani qayta ko'rsatish
        sent = await message.answer("🔄 Davom etamiz...")
        await send_flashcard(sent, state)
        
    except Exception as e:
        logger.error(f"Save example error: {e}")
        await message.answer("❌ Xatolik yuz berdi")
        await state.set_state(FlashcardStates.studying)


@router.callback_query(F.data == "fc:cancel_example")
async def cancel_example(callback: CallbackQuery, state: FSMContext):
    """Misol qo'shishni bekor qilish"""
    await state.set_state(FlashcardStates.studying)
    await callback.answer("❌ Bekor qilindi")
    await send_flashcard(callback.message, state)




@router.callback_query(F.data == "fc:skip", FlashcardStates.studying)
async def skip_card(callback: CallbackQuery, state: FSMContext):
    """Kartochkani o'tkazish"""
    data = await state.get_data()
    index = data.get("current_index", 0)
    
    await state.update_data(current_index=index + 1, show_back=False)
    await callback.answer("⏭ O'tkazildi")
    await send_flashcard(callback.message, state)


@router.callback_query(F.data == "fc:finish", FlashcardStates.studying)
async def finish_early(callback: CallbackQuery, state: FSMContext):
    """Erta tugatish"""
    await show_results(callback.message, state)
    await callback.answer()


async def show_results(message, state: FSMContext):
    """Natijalarni ko'rsatish"""
    data = await state.get_data()
    correct = data.get("correct_count", 0)
    wrong = data.get("wrong_count", 0)
    total = correct + wrong
    deck_name = data.get("deck_name", "Flashcard")
    
    if total == 0:
        percentage = 0
    else:
        percentage = (correct / total) * 100
    
    # Reyting
    if percentage >= 90:
        emoji = "🌟"
        rating = "A'lo!"
    elif percentage >= 70:
        emoji = "👍"
        rating = "Yaxshi"
    elif percentage >= 50:
        emoji = "📚"
        rating = "O'rtacha"
    else:
        emoji = "💪"
        rating = "Mashq qiling"
    
    # Deck progress yangilash
    try:
        user_id = data.get("user_id") or message.chat.id
        deck_id = data.get("deck_id")
        
        if deck_id:
            async with get_session() as session:
                progress_repo = UserDeckProgressRepository(session)
                await progress_repo.update_progress(
                    user_id=user_id,
                    deck_id=deck_id,
                    cards_studied=total,
                    correct=correct
                )
    except Exception as e:
        logger.error(f"Deck progress update error: {e}")
    
    
    # XP statistikasi
    try:
        user_id = data.get("user_id") or message.chat.id
        xp_stats = await XPService.get_user_stats(user_id)
    except Exception:
        xp_stats = {"xp": 0, "level": 1, "level_name": "Boshlang'ich", "progress_bar": "░░░░░░░░░░"}
    text = f"""
{emoji} <b>Flashcard tugadi!</b>

📚 Deck: {deck_name}

📊 <b>Natija: {rating}</b>

✅ Bildim: {correct}
❌ Bilmadim: {wrong}
📈 Foiz: {percentage:.1f}%

⭐ <b>Level {xp_stats["level"]}</b> - {xp_stats["level_name"]}
🎯 XP: {xp_stats["xp"]} | {xp_stats["progress_bar"]}

<i>SM-2 algoritmi takrorlash vaqtini belgiladi.
Ertaga "Takrorlash" bo'limida ko'ring!</i>
"""
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Yana o'rganish", callback_data="fc:decks"),
        InlineKeyboardButton(text="🏠 Menyu", callback_data="menu:main")
    )
    
    await state.clear()
    
    try:
        await message.edit_text(text, reply_markup=builder.as_markup())
    except Exception:
        await message.answer(text, reply_markup=builder.as_markup())


@router.callback_query(F.data == "fc:review")
async def review_due_cards(callback: CallbackQuery, state: FSMContext, db_user: User):
    """Takrorlash kerak bo'lgan kartochkalar"""
    user_id = callback.from_user.id
    
    async with get_session() as session:
        user_fc_repo = UserFlashcardRepository(session)
        card_repo = FlashcardRepository(session)
        # Kunlik limit tekshiruvi
        limit_manager = DailyLimitManager(session)
        # Default deck_id=0 umumiy limit uchun
        limit_status = await limit_manager.can_study(user_id, 0)
        
        if not limit_status["can_review"]:
            await callback.answer(
                f"🎉 Bugungi limit tugadi!\nErtaga davom eting.",
                show_alert=True
            )
            return
        
        # Limitga qarab kartochkalar sonini cheklash
        max_cards = min(20, limit_status["reviews_remaining"])
        
        due_cards = await user_fc_repo.get_due_cards(user_id, limit=max_cards)
    
    if not due_cards:
        await callback.answer("✅ Bugun takrorlash kerak emas!", show_alert=True)
        return
    
    # Kartochkalarni tayyorlash
    cards_data = []
    async with get_session() as session:
        card_repo = FlashcardRepository(session)
        for uc in due_cards:
            card = await card_repo.get_by_id(uc.card_id)
            if card:
                cards_data.append({
                    "id": card.id,
                    "front": card.front_text,
                    "back": card.back_text,
                    "example": card.example_sentence or "",
                })
    
    if not cards_data:
        await callback.answer("❌ Kartochkalar topilmadi!", show_alert=True)
        return
    
    random.shuffle(cards_data)
    
    await state.update_data(
        deck_id=None,
        deck_name="Takrorlash",
        cards=cards_data,
        current_index=0,
        correct_count=0,
        wrong_count=0,
        show_back=False,
        user_id=user_id
    )
    await state.set_state(FlashcardStates.studying)
    
    await callback.message.edit_text(
        f"🔄 <b>Takrorlash</b>\n\n"
        f"Bugun {len(cards_data)} ta kartochkani takrorlash kerak.\n"
        f"Boshlaylik!",
    )
    
    await send_flashcard(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "fc:stats")
async def show_stats(callback: CallbackQuery, db_user: User):
    """Kengaytirilgan Flashcard statistikasi"""
    user_id = callback.from_user.id
    
    try:
        async with get_session() as session:
            limit_manager = DailyLimitManager(session)
            extended_stats = ExtendedStatsManager(session)
            difficult_manager = DifficultCardsManager(session)
            
            limits = await limit_manager.get_user_limits(user_id, 0)
            stats = await extended_stats.get_extended_stats(user_id)
            difficult = await difficult_manager.get_difficult_stats(user_id)
        
        m = stats["mastery"]
        d = stats["difficulty"]
        pb = stats["progress_bars"]
        
        text = f"""
📊 <b>Flashcard Statistikasi</b>

<b>Progress:</b>
{pb['mastered']} {pb.get('mastered_pct', 0):.0f}% o'zlashtirilgan
{pb['learning']} {pb.get('learning_pct', 0):.0f}% o'rganilmoqda

<b>Darajalar:</b>
- 🆕 Yangi: {m['new']}
- 📖 O'rganilmoqda: {m['learning']}
- 🔄 Takrorlanmoqda: {m['reviewing']}
- ✅ O'zlashtirilgan: {m['mastered']}
- 📦 Arxivlangan: {m['suspended']}

<b>Qiyinlik tahlili:</b>
- 🟢 Oson (80%+): {d['easy']}
- 🟡 O'rta (50-79%): {d['medium']}
- 🔴 Qiyin (&lt;50%): {d['hard']}

<b>Bugungi limit:</b>
- 🆕 Yangi: {limits['new_cards_today']}/{limits['new_cards_limit']}
- 🔄 Takrorlash: {limits['reviews_today']}/{limits['review_limit']}

<b>Umumiy:</b>
- Jami takrorlashlar: {stats['total_reviews']}
- Aniqlik: {stats['accuracy']:.1f}%
- O'rtacha EF: {stats['avg_ease_factor']:.2f}
"""
    except Exception as e:
        logger.error(f"Stats error: {e}")
        text = "📊 <b>Statistika</b>\n\n❌ Ma'lumotlarni yuklashda xatolik"
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📈 Batafsil", callback_data="fc:stats_detail"),
        InlineKeyboardButton(text="⚙️ Sozlamalar", callback_data="fc:settings")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="flashcard:menu")
    )
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "fc:stats_detail")
async def show_stats_detail(callback: CallbackQuery, db_user: User):
    """Batafsil statistika"""
    user_id = callback.from_user.id
    
    try:
        async with get_session() as session:
            extended_stats = ExtendedStatsManager(session)
            stats = await extended_stats.get_extended_stats(user_id)
        
        m = stats["mastery"]
        total = stats["total_cards"]
        
        # Foizlar
        if total > 0:
            new_pct = m['new'] / total * 100
            learning_pct = m['learning'] / total * 100
            reviewing_pct = m['reviewing'] / total * 100
            mastered_pct = m['mastered'] / total * 100
        else:
            new_pct = learning_pct = reviewing_pct = mastered_pct = 0
        
        text = f"""
📈 <b>Batafsil Statistika</b>

<b>Kartochkalar taqsimoti:</b>
🆕 Yangi: {m['new']} ({new_pct:.1f}%)
📖 O'rganilmoqda: {m['learning']} ({learning_pct:.1f}%)
🔄 Takrorlanmoqda: {m['reviewing']} ({reviewing_pct:.1f}%)
✅ O'zlashtirilgan: {m['mastered']} ({mastered_pct:.1f}%)

<b>SM-2 ko'rsatkichlari:</b>
- O'rtacha Ease Factor: {stats['avg_ease_factor']:.2f}
  (2.5 = standart, &gt;2.5 = oson, &lt;2.5 = qiyin)
- Arxivlangan: {stats['suspended_count']} ta

<b>Takrorlash samaradorligi:</b>
- Jami takrorlashlar: {stats['total_reviews']}
- To'g'ri javoblar: {stats['correct_reviews']}
- Umumiy aniqlik: {stats['accuracy']:.1f}%

<b>Tavsiya:</b>
"""
        # Tavsiya berish
        if stats['accuracy'] < 60:
            text += "⚠️ Aniqlik past. Qiyin so'zlarni ko'proq takrorlang."
        elif m['new'] > m['mastered']:
            text += "💡 Yangi so'zlardan ko'ra, mavjudlarni mustahkamlang."
        else:
            text += "✅ Yaxshi natija! Shunday davom eting."
        
    except Exception as e:
        logger.error(f"Stats detail error: {e}")
        text = "📈 <b>Batafsil</b>\n\n❌ Xatolik"
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="fc:stats")
    )
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


# ============================================================
# SETTINGS HANDLERS
# ============================================================

@router.callback_query(F.data == "fc:settings")
async def show_settings(callback: CallbackQuery, db_user: User):
    """Limit sozlamalari"""
    user_id = callback.from_user.id
    
    try:
        async with get_session() as session:
            limit_manager = DailyLimitManager(session)
            limits = await limit_manager.get_user_limits(user_id, 0)
        
        text = f"""
⚙️ <b>Limit sozlamalari</b>

<b>Joriy limitlar:</b>
- 🆕 Yangi kartochkalar: <b>{limits['new_cards_limit']}</b> ta/kun
- 🔄 Takrorlash: <b>{limits['review_limit']}</b> ta/kun

Quyidagi tugmalar orqali o'zgartiring:
"""
    except Exception as e:
        logger.error(f"Settings error: {e}")
        text = "⚙️ <b>Sozlamalar</b>\n\n❌ Xatolik yuz berdi"
        limits = {"new_cards_limit": 10, "review_limit": 50}
    
    builder = InlineKeyboardBuilder()
    
    # Yangi kartochkalar limiti
    builder.row(
        InlineKeyboardButton(text="🆕 Yangi kartochkalar:", callback_data="noop")
    )
    builder.row(
        InlineKeyboardButton(text="5", callback_data="fc:set_new:5"),
        InlineKeyboardButton(text="10", callback_data="fc:set_new:10"),
        InlineKeyboardButton(text="15", callback_data="fc:set_new:15"),
        InlineKeyboardButton(text="20", callback_data="fc:set_new:20"),
    )
    
    # Takrorlash limiti
    builder.row(
        InlineKeyboardButton(text="🔄 Takrorlash limiti:", callback_data="noop")
    )
    builder.row(
        InlineKeyboardButton(text="30", callback_data="fc:set_review:30"),
        InlineKeyboardButton(text="50", callback_data="fc:set_review:50"),
        InlineKeyboardButton(text="100", callback_data="fc:set_review:100"),
        InlineKeyboardButton(text="150", callback_data="fc:set_review:150"),
    )
    
    # Notification toggle
    notif_status = "✅" if db_user.notifications_enabled else "❌"
    builder.row(
        InlineKeyboardButton(
            text=f"🔔 Eslatmalar: {notif_status}",
            callback_data="fc:toggle_notif"
        )
    )
    builder.row(
        InlineKeyboardButton(text="🧠 SR Tuning", callback_data="fc:sr_tuning")
    )
    
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="fc:stats")
    )
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("fc:set_new:"))
async def set_new_cards_limit(callback: CallbackQuery, db_user: User):
    """Yangi kartochkalar limitini o'zgartirish"""
    new_limit = int(callback.data.split(":")[2])
    user_id = callback.from_user.id
    
    try:
        async with get_session() as session:
            limit_manager = DailyLimitManager(session)
            await limit_manager.update_limits(user_id, 0, new_cards_limit=new_limit)
        
        await callback.answer(f"✅ Yangi kartochkalar limiti: {new_limit}", show_alert=True)
        
        # Refresh settings page
        await show_settings(callback, db_user)
        
    except Exception as e:
        logger.error(f"Set new limit error: {e}")
        await callback.answer("❌ Xatolik", show_alert=True)


@router.callback_query(F.data.startswith("fc:set_review:"))
async def set_review_limit(callback: CallbackQuery, db_user: User):
    """Takrorlash limitini o'zgartirish"""
    new_limit = int(callback.data.split(":")[2])
    user_id = callback.from_user.id
    
    try:
        async with get_session() as session:
            limit_manager = DailyLimitManager(session)
            await limit_manager.update_limits(user_id, 0, review_limit=new_limit)
        
        await callback.answer(f"✅ Takrorlash limiti: {new_limit}", show_alert=True)
        
        # Refresh settings page
        await show_settings(callback, db_user)
        
    except Exception as e:
        logger.error(f"Set review limit error: {e}")
        await callback.answer("❌ Xatolik", show_alert=True)



@router.callback_query(F.data == "fc:toggle_notif")
async def toggle_notifications(callback: CallbackQuery, db_user: User):
    """Eslatmalarni yoqish/o'chirish"""
    user_id = callback.from_user.id
    
    try:
        async with get_session() as session:
            from src.repositories import UserRepository
            user_repo = UserRepository(session)
            
            # Toggle notification
            new_status = not db_user.notifications_enabled
            await user_repo.update_user(
                user_id,
                notifications_enabled=new_status
            )
            
            # Update db_user object
            db_user.notifications_enabled = new_status
        
        status_text = "yoqildi ✅" if new_status else "o'chirildi ❌"
        await callback.answer(f"🔔 Eslatmalar {status_text}", show_alert=True)
        
        # Refresh settings page
        await show_settings(callback, db_user)
        
    except Exception as e:
        logger.error(f"Toggle notification error: {e}")
        await callback.answer("❌ Xatolik", show_alert=True)

# ============================================================
# SR TUNING HANDLERS
# ============================================================

@router.callback_query(F.data == "fc:sr_tuning")
async def show_sr_tuning(callback: CallbackQuery, db_user: User):
    """SR algoritm sozlamalari"""
    user_id = callback.from_user.id
    
    try:
        async with get_session() as session:
            sr_manager = SRTuningManager(session)
            settings = await sr_manager.get_user_sr_settings(user_id, 0)
        
        text = f"""
🧠 <b>SR Tuning - Spaced Repetition sozlamalari</b>

<b>Joriy sozlamalar:</b>
- Boshlang'ich EF: <b>{settings['initial_ef']}</b>
- Min EF: <b>{settings['min_ef']}</b>
- 1-interval: <b>{settings['first_interval']} kun</b>
- 2-interval: <b>{settings['second_interval']} kun</b>
- Easy bonus: <b>{settings['easy_bonus']}x</b>

<b>Presetlar:</b>
🟢 Oson - kamroq takrorlash
🟡 Normal - standart SM-2
🔴 Qiyin - ko'proq takrorlash
🟣 Intensiv - tez o'rganish
"""
    except Exception as e:
        logger.error(f"SR tuning error: {e}")
        text = "🧠 <b>SR Tuning</b>\n\n❌ Xatolik yuz berdi"
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🟢 Oson", callback_data="fc:sr_preset:easy"),
        InlineKeyboardButton(text="🟡 Normal", callback_data="fc:sr_preset:normal"),
    )
    builder.row(
        InlineKeyboardButton(text="🔴 Qiyin", callback_data="fc:sr_preset:hard"),
        InlineKeyboardButton(text="🟣 Intensiv", callback_data="fc:sr_preset:aggressive"),
    )
    builder.row(
        InlineKeyboardButton(text="🔧 Batafsil sozlash", callback_data="fc:sr_advanced")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="fc:settings")
    )
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("fc:sr_preset:"))
async def apply_sr_preset(callback: CallbackQuery, db_user: User):
    """SR preset qo'llash"""
    preset_name = callback.data.split(":")[2]
    user_id = callback.from_user.id
    
    try:
        preset = SRTuningManager.get_preset(preset_name)
        
        async with get_session() as session:
            sr_manager = SRTuningManager(session)
            await sr_manager.update_sr_settings(
                user_id, 0,
                initial_ef=preset["initial_ef"],
                min_ef=preset["min_ef"],
                first_interval=preset["first_interval"],
                second_interval=preset["second_interval"],
                easy_bonus=preset["easy_bonus"]
            )
        
        await callback.answer(f"✅ {preset['description']}", show_alert=True)
        await show_sr_tuning(callback, db_user)
        
    except Exception as e:
        logger.error(f"SR preset error: {e}")
        await callback.answer("❌ Xatolik", show_alert=True)


@router.callback_query(F.data == "fc:sr_advanced")
async def show_sr_advanced(callback: CallbackQuery, db_user: User):
    """Batafsil SR sozlamalari"""
    user_id = callback.from_user.id
    
    try:
        async with get_session() as session:
            sr_manager = SRTuningManager(session)
            settings = await sr_manager.get_user_sr_settings(user_id, 0)
        
        text = f"""
🔧 <b>Batafsil SR sozlamalari</b>

<b>Easiness Factor (EF):</b>
- Boshlang'ich: <b>{settings['initial_ef']}</b> (1.3-3.0)
- Minimal: <b>{settings['min_ef']}</b> (1.1-2.0)

<b>Intervallar:</b>
- 1-muvaffaqiyat: <b>{settings['first_interval']} kun</b> (1-7)
- 2-muvaffaqiyat: <b>{settings['second_interval']} kun</b> (3-14)

<b>Bonus:</b>
- Easy bonus: <b>{settings['easy_bonus']}x</b> (1.0-2.0)

Parametrni o'zgartirish uchun tugmani bosing:
"""
    except Exception as e:
        logger.error(f"SR advanced error: {e}")
        text = "🔧 <b>Batafsil sozlamalar</b>\n\n❌ Xatolik"
        settings = {}
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=f"📊 Initial EF: {settings.get('initial_ef', 2.5)}", callback_data="fc:sr_edit:initial_ef")
    )
    builder.row(
        InlineKeyboardButton(text=f"📉 Min EF: {settings.get('min_ef', 1.3)}", callback_data="fc:sr_edit:min_ef")
    )
    builder.row(
        InlineKeyboardButton(text=f"1️⃣ 1-interval: {settings.get('first_interval', 1)} kun", callback_data="fc:sr_edit:first_interval")
    )
    builder.row(
        InlineKeyboardButton(text=f"2️⃣ 2-interval: {settings.get('second_interval', 6)} kun", callback_data="fc:sr_edit:second_interval")
    )
    builder.row(
        InlineKeyboardButton(text=f"⚡ Easy bonus: {settings.get('easy_bonus', 1.3)}x", callback_data="fc:sr_edit:easy_bonus")
    )
    builder.row(
        InlineKeyboardButton(text="🔄 Reset", callback_data="fc:sr_reset"),
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="fc:sr_tuning")
    )
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("fc:sr_edit:"))
async def edit_sr_param(callback: CallbackQuery, db_user: User):
    """SR parametrini tahrirlash"""
    param = callback.data.split(":")[2]
    
    params_info = {
        "initial_ef": ("Boshlang'ich EF", "1.5", "2.0", "2.5", "2.7", "3.0"),
        "min_ef": ("Minimal EF", "1.1", "1.2", "1.3", "1.5", "1.8"),
        "first_interval": ("1-interval (kun)", "1", "2", "3", "5", "7"),
        "second_interval": ("2-interval (kun)", "3", "4", "6", "10", "14"),
        "easy_bonus": ("Easy bonus", "1.0", "1.1", "1.3", "1.5", "2.0")
    }
    
    info = params_info.get(param)
    if not info:
        await callback.answer("❌ Noma'lum parametr", show_alert=True)
        return
    
    text = f"🔧 <b>{info[0]}</b>\n\nQiymatni tanlang:"
    
    builder = InlineKeyboardBuilder()
    builder.row(
        *[InlineKeyboardButton(text=v, callback_data=f"fc:sr_set:{param}:{v}") for v in info[1:]]
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="fc:sr_advanced")
    )
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("fc:sr_set:"))
async def set_sr_param(callback: CallbackQuery, db_user: User):
    """SR parametrini o'rnatish"""
    parts = callback.data.split(":")
    param = parts[2]
    value = float(parts[3])
    user_id = callback.from_user.id
    
    try:
        async with get_session() as session:
            sr_manager = SRTuningManager(session)
            await sr_manager.update_sr_settings(user_id, 0, **{param: value})
        
        await callback.answer(f"✅ {param} = {value}", show_alert=True)
        await show_sr_advanced(callback, db_user)
        
    except Exception as e:
        logger.error(f"SR set param error: {e}")
        await callback.answer("❌ Xatolik", show_alert=True)


@router.callback_query(F.data == "fc:sr_reset")
async def reset_sr_settings(callback: CallbackQuery, db_user: User):
    """SR sozlamalarini reset"""
    user_id = callback.from_user.id
    
    try:
        async with get_session() as session:
            sr_manager = SRTuningManager(session)
            await sr_manager.reset_to_defaults(user_id, 0)
        
        await callback.answer("✅ Standart sozlamalar qaytarildi", show_alert=True)
        await show_sr_advanced(callback, db_user)
        
    except Exception as e:
        logger.error(f"SR reset error: {e}")
        await callback.answer("❌ Xatolik", show_alert=True)



# ============================================================
# DIFFICULT CARDS HANDLERS
# ============================================================

@router.callback_query(F.data == "fc:difficult")
async def show_difficult_cards(callback: CallbackQuery, db_user: User):
    """Qiyin so'zlar ro'yxati"""
    user_id = callback.from_user.id
    
    try:
        async with get_session() as session:
            difficult_manager = DifficultCardsManager(session)
            stats = await difficult_manager.get_difficult_stats(user_id)
            
            # Eager load flashcard data
            for card in stats["cards"]:
                await session.refresh(card, ['card'])
        
        if stats["count"] == 0:
            text = """
🔴 <b>Qiyin so'zlar</b>

Qiyin so'zlar yo'q! 🎉

ℹ️ Bu yerda aniqlik &lt;50% bo'lgan so'zlar ko'rsatiladi.
Kamida 3 marta takrorlangan so'zlar hisobga olinadi.
"""
            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text="◀️ Orqaga", callback_data="flashcard:menu")
            )
            await callback.message.edit_text(text, reply_markup=builder.as_markup())
            await callback.answer()
            return
        
        text = f"""
🔴 <b>Qiyin so'zlar</b>

Jami: <b>{stats['count']} ta</b> so'z aniqlik &lt;50%

<b>Eng qiyin so'zlar:</b>
"""
        for i, uc in enumerate(stats["cards"][:10], 1):
            accuracy = (uc.correct_reviews / uc.total_reviews * 100) if uc.total_reviews > 0 else 0
            text += f"{i}. {uc.card.front_text[:25]}... - <b>{accuracy:.0f}%</b>\n"
        
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="🔄 Qiyin so'zlarni takrorlash",
                callback_data="fc:difficult_study"
            )
        )
        builder.row(
            InlineKeyboardButton(text="◀️ Orqaga", callback_data="flashcard:menu")
        )
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Difficult cards error: {e}")
        await callback.answer("❌ Xatolik", show_alert=True)


@router.callback_query(F.data == "fc:difficult_study")
async def study_difficult_cards(callback: CallbackQuery, state: FSMContext, db_user: User):
    """Qiyin so'zlarni takrorlash"""
    user_id = callback.from_user.id
    
    try:
        async with get_session() as session:
            difficult_manager = DifficultCardsManager(session)
            difficult = await difficult_manager.get_difficult_cards(user_id)
            
            if not difficult:
                await callback.answer("✅ Qiyin so'zlar yo'q!", show_alert=True)
                return
            
            # Eager load
            cards_data = []
            card_repo = FlashcardRepository(session)
            for uc in difficult[:15]:  # Max 15 ta
                card = await card_repo.get_by_id(uc.card_id)
                if card:
                    accuracy = (uc.correct_reviews / uc.total_reviews * 100) if uc.total_reviews > 0 else 0
                    cards_data.append({
                        "id": card.id,
                        "front": f"🔴 {card.front_text}",
                        "back": card.back_text,
                        "example": f"Aniqlik: {accuracy:.0f}%",
                    })
        
        if not cards_data:
            await callback.answer("❌ Kartochkalar topilmadi!", show_alert=True)
            return
        
        await state.update_data(
            deck_id=None,
            deck_name="Qiyin so'zlar",
            cards=cards_data,
            current_index=0,
            correct_count=0,
            wrong_count=0,
            show_back=False,
            user_id=user_id
        )
        await state.set_state(FlashcardStates.studying)
        
        await callback.message.edit_text(
            f"🔴 <b>Qiyin so'zlar</b>\n\n"
            f"{len(cards_data)} ta qiyin so'zni takrorlaymiz.\n"
            f"Diqqat bilan o'rganing!",
        )
        
        await send_flashcard(callback.message, state)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Difficult study error: {e}")
        await callback.answer("❌ Xatolik", show_alert=True)



# ============================================================
# EXPORT/IMPORT HANDLERS
# ============================================================

@router.callback_query(F.data == "fc:export")
async def show_export_menu(callback: CallbackQuery, db_user: User):
    """Export menyusi - faqat bepul yoki sotib olingan decklar"""
    user_id = callback.from_user.id

    try:
        async with get_session() as session:
            deck_repo = FlashcardDeckRepository(session)
            purchase_repo = DeckPurchaseRepository(session)
            decks = await deck_repo.get_all()
            
            # Prepare deck list with ownership info
            deck_list = []
            for deck in decks[:10]:
                if deck.is_premium:
                    purchased = await purchase_repo.has_purchased(user_id, deck.id)
                    deck_list.append({
                        "deck": deck,
                        "locked": not purchased
                    })
                else:
                    deck_list.append({
                        "deck": deck,
                        "locked": False
                    })

        text = """
📤 <b>Eksport</b>

Qaysi deckni eksport qilmoqchisiz?

🔓 - eksport mumkin
🔒 - sotib olish kerak
"""

        builder = InlineKeyboardBuilder()

        # All owned cards export
        builder.row(
            InlineKeyboardButton(
                text="📚 Barcha kartochkalarim",
                callback_data="fc:export_all"
            )
        )

        # By deck
        for item in deck_list:
            deck = item["deck"]
            if item["locked"]:
                builder.row(
                    InlineKeyboardButton(
                        text=f"🔒 {deck.icon} {deck.name}",
                        callback_data=f"fc:export_locked:{deck.id}"
                    )
                )
            else:
                builder.row(
                    InlineKeyboardButton(
                        text=f"🔓 {deck.icon} {deck.name}",
                        callback_data=f"fc:export_deck:{deck.id}"
                    )
                )

        builder.row(
            InlineKeyboardButton(text="◀️ Orqaga", callback_data="flashcard:menu")
        )

        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()

    except Exception as e:
        logger.error(f"Export menu error: {e}")
        await callback.answer("❌ Xatolik", show_alert=True)


@router.callback_query(F.data.startswith("fc:export_locked:"))
async def export_locked_deck(callback: CallbackQuery, db_user: User):
    """Qulflangan deck - sotib olish kerak"""
    deck_id = int(callback.data.split(":")[2])
    
    try:
        async with get_session() as session:
            deck_repo = FlashcardDeckRepository(session)
            deck = await deck_repo.get_by_id(deck_id)
            deck_name = deck.name if deck else "Deck"
            price = deck.price if deck else 50
        
        await callback.answer(
            f"🔒 {deck_name} premium deck!\n"
            f"Eksport uchun avval sotib oling ({price} ⭐)",
            show_alert=True
        )
    except Exception as e:
        await callback.answer("🔒 Bu deck qulflangan", show_alert=True)


async def export_all_cards(callback: CallbackQuery, db_user: User):
    """Barcha kartochkalarni eksport"""
    user_id = callback.from_user.id
    
    await callback.answer("⏳ Tayyorlanmoqda...", show_alert=False)
    
    try:
        async with get_session() as session:
            exporter = FlashcardExportImport(session)
            csv_content = await exporter.export_all_csv(user_id)
        
        if not csv_content:
            await callback.message.edit_text(
                "❌ Kartochkalar topilmadi!",
                reply_markup=InlineKeyboardBuilder().row(
                    InlineKeyboardButton(text="◀️ Orqaga", callback_data="flashcard:menu")
                ).as_markup()
            )
            return
        
        # Send as file
        from aiogram.types import BufferedInputFile
        from datetime import datetime
        
        filename = f"flashcards_{user_id}_{datetime.now().strftime('%Y%m%d')}.csv"
        file = BufferedInputFile(
            csv_content.encode('utf-8-sig'),  # BOM for Excel
            filename=filename
        )
        
        await callback.message.answer_document(
            document=file,
            caption=f"📤 <b>Eksport tayyor!</b>\n\n"
                   f"Fayl: <code>{filename}</code>\n"
                   f"Format: CSV (UTF-8)\n\n"
                   f"💡 Excel yoki Google Sheets da oching."
        )
        
        await callback.message.delete()
        
    except Exception as e:
        logger.error(f"Export all error: {e}")
        await callback.message.edit_text(
            f"❌ Eksport xatosi: {str(e)[:100]}",
            reply_markup=InlineKeyboardBuilder().row(
                InlineKeyboardButton(text="◀️ Orqaga", callback_data="flashcard:menu")
            ).as_markup()
        )


@router.callback_query(F.data.startswith("fc:export_deck:"))
async def export_deck(callback: CallbackQuery, db_user: User):
    """Deckni eksport qilish"""
    deck_id = int(callback.data.split(":")[2])
    user_id = callback.from_user.id
    
    await callback.answer("⏳ Tayyorlanmoqda...", show_alert=False)
    
    try:
        async with get_session() as session:
            exporter = FlashcardExportImport(session)
            csv_content = await exporter.export_deck_csv(user_id, deck_id)
            
            deck_repo = FlashcardDeckRepository(session)
            deck = await deck_repo.get_by_id(deck_id)
            deck_name = deck.name if deck else "unknown"
        
        if not csv_content:
            await callback.message.edit_text(
                "❌ Kartochkalar topilmadi!",
                reply_markup=InlineKeyboardBuilder().row(
                    InlineKeyboardButton(text="◀️ Orqaga", callback_data="fc:export")
                ).as_markup()
            )
            return
        
        from aiogram.types import BufferedInputFile
        from datetime import datetime
        
        safe_name = deck_name.replace(' ', '_')[:20]
        filename = f"flashcards_{safe_name}_{datetime.now().strftime('%Y%m%d')}.csv"
        file = BufferedInputFile(
            csv_content.encode('utf-8-sig'),
            filename=filename
        )
        
        await callback.message.answer_document(
            document=file,
            caption=f"📤 <b>{deck_name}</b> eksport qilindi!\n\n"
                   f"Fayl: <code>{filename}</code>"
        )
        
        await callback.message.delete()
        
    except Exception as e:
        logger.error(f"Export deck error: {e}")
        await callback.message.edit_text(
            f"❌ Eksport xatosi",
            reply_markup=InlineKeyboardBuilder().row(
                InlineKeyboardButton(text="◀️ Orqaga", callback_data="fc:export")
            ).as_markup()
        )


# ============================================================
# ARXIV (Suspended Cards) HANDLERS
# ============================================================

def arxiv_keyboard(suspended_cards: list, page: int = 0, per_page: int = 5) -> InlineKeyboardMarkup:
    """Arxivlangan so'zlar keyboard"""
    builder = InlineKeyboardBuilder()
    
    start = page * per_page
    end = start + per_page
    page_cards = suspended_cards[start:end]
    
    for card in page_cards:
        # card - UserFlashcard object, card.card - Flashcard
        builder.row(
            InlineKeyboardButton(
                text=f"📦 {card.card.front_text[:20]}... ({card.interval} kun)",
                callback_data=f"arxiv:view:{card.id}"
            )
        )
    
    # Pagination
    nav_buttons = []
    total_pages = (len(suspended_cards) + per_page - 1) // per_page
    
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="◀️", callback_data=f"arxiv:page:{page-1}")
        )
    
    if total_pages > 1:
        nav_buttons.append(
            InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop")
        )
    
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton(text="▶️", callback_data=f"arxiv:page:{page+1}")
        )
    
    if nav_buttons:
        builder.row(*nav_buttons)
    
    builder.row(
        InlineKeyboardButton(text="🔄 Hammasini qayta faollashtirish", callback_data="arxiv:unsuspend_all")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="flashcard:menu")
    )
    
    return builder.as_markup()


@router.message(F.text == "/arxiv")
async def arxiv_command(message: Message, db_user: User):
    """Arxivlangan so'zlar ro'yxati"""
    user_id = message.from_user.id
    
    try:
        async with get_session() as session:
            user_fc_repo = UserFlashcardRepository(session)
            suspended = await user_fc_repo.get_suspended_cards(user_id)
            
            # Eager load flashcard data
            for card in suspended:
                await session.refresh(card, ['card'])
        
        if not suspended:
            text = """
📦 <b>Arxiv</b>

Arxivlangan so'zlar yo'q.

ℹ️ Interval 180+ kun bo'lgan so'zlar avtomatik arxivlanadi.
Bu so'zlarni siz juda yaxshi o'zlashtirdingiz! 🎉
"""
            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text="◀️ Orqaga", callback_data="flashcard:menu")
            )
            await message.answer(text, reply_markup=builder.as_markup())
            return
        
        text = f"""
📦 <b>Arxiv</b>

Arxivlangan so'zlar: <b>{len(suspended)} ta</b>

ℹ️ Bu so'zlarni juda yaxshi o'zlashtirdingiz (interval 180+ kun).
Qayta takrorlash uchun so'zni tanlang.
"""
        await message.answer(text, reply_markup=arxiv_keyboard(suspended, page=0))
        
    except Exception as e:
        logger.error(f"Arxiv error: {e}")
        await message.answer("❌ Xatolik yuz berdi")


@router.callback_query(F.data == "fc:arxiv")
async def arxiv_callback(callback: CallbackQuery, db_user: User):
    """Arxiv menu callback"""
    user_id = callback.from_user.id
    
    try:
        async with get_session() as session:
            user_fc_repo = UserFlashcardRepository(session)
            suspended = await user_fc_repo.get_suspended_cards(user_id)
            
            for card in suspended:
                await session.refresh(card, ['card'])
        
        if not suspended:
            text = """
📦 <b>Arxiv</b>

Arxivlangan so'zlar yo'q.

ℹ️ Interval 180+ kun bo'lgan so'zlar avtomatik arxivlanadi.
"""
            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text="◀️ Orqaga", callback_data="flashcard:menu")
            )
            await callback.message.edit_text(text, reply_markup=builder.as_markup())
        else:
            text = f"""
📦 <b>Arxiv</b>

Arxivlangan so'zlar: <b>{len(suspended)} ta</b>

ℹ️ Qayta takrorlash uchun so'zni tanlang.
"""
            await callback.message.edit_text(text, reply_markup=arxiv_keyboard(suspended, page=0))
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Arxiv callback error: {e}")
        await callback.answer("❌ Xatolik", show_alert=True)


@router.callback_query(F.data.startswith("arxiv:page:"))
async def arxiv_page(callback: CallbackQuery, db_user: User):
    """Arxiv sahifani o'zgartirish"""
    page = int(callback.data.split(":")[2])
    user_id = callback.from_user.id
    
    try:
        async with get_session() as session:
            user_fc_repo = UserFlashcardRepository(session)
            suspended = await user_fc_repo.get_suspended_cards(user_id)
            
            for card in suspended:
                await session.refresh(card, ['card'])
        
        text = f"""
📦 <b>Arxiv</b>

Arxivlangan so'zlar: <b>{len(suspended)} ta</b>

ℹ️ Qayta takrorlash uchun so'zni tanlang.
"""
        await callback.message.edit_text(text, reply_markup=arxiv_keyboard(suspended, page=page))
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Arxiv page error: {e}")
        await callback.answer("❌ Xatolik", show_alert=True)


@router.callback_query(F.data.startswith("arxiv:view:"))
async def arxiv_view_card(callback: CallbackQuery, db_user: User):
    """Arxivlangan so'zni ko'rish"""
    user_card_id = int(callback.data.split(":")[2])
    
    try:
        async with get_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(UserFlashcard).where(UserFlashcard.id == user_card_id)
            )
            user_card = result.scalar_one_or_none()
            
            if not user_card:
                await callback.answer("So'z topilmadi", show_alert=True)
                return
            
            await session.refresh(user_card, ['card'])
            card = user_card.card
        
        accuracy = (user_card.correct_reviews / user_card.total_reviews * 100) if user_card.total_reviews > 0 else 0
        
        text = f"""
📦 <b>Arxivlangan so'z</b>

<b>Old:</b> {card.front_text}
<b>Orqa:</b> {card.back_text}

📊 <b>Statistika:</b>
- Interval: {user_card.interval} kun
- Takrorlashlar: {user_card.total_reviews}
- Aniqlik: {accuracy:.0f}%
- Oxirgi takrorlash: {user_card.last_review_date or "—"}

Qayta faollashtirmoqchimisiz?
"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Qayta faollashtirish",
                callback_data=f"arxiv:unsuspend:{user_card.card_id}"
            )
        )
        builder.row(
            InlineKeyboardButton(text="◀️ Orqaga", callback_data="fc:arxiv")
        )
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Arxiv view error: {e}")
        await callback.answer("❌ Xatolik", show_alert=True)


@router.callback_query(F.data.startswith("arxiv:unsuspend:"))
async def arxiv_unsuspend_card(callback: CallbackQuery, db_user: User):
    """So'zni qayta faollashtirish"""
    card_id = int(callback.data.split(":")[2])
    user_id = callback.from_user.id
    
    try:
        async with get_session() as session:
            user_fc_repo = UserFlashcardRepository(session)
            result = await user_fc_repo.unsuspend_card(user_id, card_id)
            
            if result:
                await callback.answer("✅ So'z qayta faollashtirildi!", show_alert=True)
            else:
                await callback.answer("❌ So'z topilmadi", show_alert=True)
                return
            
            # Refresh arxiv list
            suspended = await user_fc_repo.get_suspended_cards(user_id)
            
            for card in suspended:
                await session.refresh(card, ['card'])
        
        if not suspended:
            text = """
📦 <b>Arxiv</b>

Arxivlangan so'zlar yo'q.
"""
            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text="◀️ Orqaga", callback_data="flashcard:menu")
            )
            await callback.message.edit_text(text, reply_markup=builder.as_markup())
        else:
            text = f"""
📦 <b>Arxiv</b>

Arxivlangan so'zlar: <b>{len(suspended)} ta</b>
"""
            await callback.message.edit_text(text, reply_markup=arxiv_keyboard(suspended, page=0))
        
    except Exception as e:
        logger.error(f"Unsuspend error: {e}")
        await callback.answer("❌ Xatolik", show_alert=True)


@router.callback_query(F.data == "arxiv:unsuspend_all")
async def arxiv_unsuspend_all(callback: CallbackQuery, db_user: User):
    """Barcha so'zlarni qayta faollashtirish"""
    user_id = callback.from_user.id
    
    try:
        async with get_session() as session:
            from sqlalchemy import update
            result = await session.execute(
                update(UserFlashcard)
                .where(
                    UserFlashcard.user_id == user_id,
                    UserFlashcard.is_suspended == True
                )
                .values(is_suspended=False)
            )
            await session.commit()
            count = result.rowcount
        
        text = f"""
📦 <b>Arxiv</b>

✅ <b>{count} ta</b> so'z qayta faollashtirildi!

Endi ularni /flashcard orqali takrorlashingiz mumkin.
"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="📚 Flashcard", callback_data="flashcard:menu")
        )
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Unsuspend all error: {e}")
        await callback.answer("❌ Xatolik", show_alert=True)
