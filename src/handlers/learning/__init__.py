"""
Learning handlers - Word learning mode
Yangi so'zlarni o'rganish va Flashcard ga qo'shish
"""
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from src.database import get_session
from src.database.models import User, Question
from src.database.models.flashcard import FlashcardDeck, Flashcard, UserFlashcard
from src.repositories import QuestionRepository, UserRepository
from src.repositories.flashcard_repo import FlashcardDeckRepository, FlashcardRepository, UserFlashcardRepository
from src.services import quiz_service
from src.services.sr_algorithm import SpacedRepetitionService, Quality
from src.core.logging import get_logger

logger = get_logger(__name__)
router = Router(name="learning")


class LearningStates(StatesGroup):
    """So'z o'rganish holatlari"""
    learning = State()
    quiz_check = State()


# =====================================================
# FLASHCARD GA QO'SHISH FUNKSIYALARI
# =====================================================

async def get_or_create_learned_deck(session, user_id: int, level_id: int = None) -> FlashcardDeck:
    """
    Foydalanuvchi uchun "O'rganilgan so'zlar" deckini olish yoki yaratish
    """
    deck_repo = FlashcardDeckRepository(session)

    # Mavjud deckni izlash
    result = await session.execute(
        session.query(FlashcardDeck).filter(
            FlashcardDeck.owner_id == user_id,
            FlashcardDeck.name.like("O'rganilgan so'zlar%")
        )
    ) if hasattr(session, 'query') else None

    # SQLAlchemy 2.0 style
    from sqlalchemy import select, and_
    result = await session.execute(
        select(FlashcardDeck).where(
            and_(
                FlashcardDeck.owner_id == user_id,
                FlashcardDeck.name == "📚 O'rganilgan so'zlar"
            )
        )
    )
    deck = result.scalar_one_or_none()

    if not deck:
        # Yangi deck yaratish
        deck = FlashcardDeck(
            name="📚 O'rganilgan so'zlar",
            description="Learning modulidan o'rganilgan so'zlar",
            owner_id=user_id,
            level_id=level_id,
            is_public=False,
            is_premium=False,
            icon="📚",
            cards_count=0
        )
        session.add(deck)
        await session.commit()
        await session.refresh(deck)

    return deck


async def add_word_to_flashcard(
    session,
    user_id: int,
    deck_id: int,
    word: str,
    translation: str,
    example: str = "",
    quality: int = 4,  # 4=Bildim, 5=Oson
    algorithm: str = "sm2"  # "sm2" yoki "anki"
) -> bool:
    """
    So'zni flashcard ga qo'shish

    Args:
        quality: Quality rating (3=Qiyin, 4=Bildim, 5=Oson)
        algorithm: "sm2" yoki "anki"

    Returns:
        True if new card created, False if already exists
    """
    from sqlalchemy import select, and_

    card_repo = FlashcardRepository(session)
    user_fc_repo = UserFlashcardRepository(session)

    # So'z allaqachon mavjudmi tekshirish
    result = await session.execute(
        select(Flashcard).where(
            and_(
                Flashcard.deck_id == deck_id,
                Flashcard.front_text == word
            )
        )
    )
    card = result.scalar_one_or_none()

    if not card:
        # Yangi kartochka yaratish
        card = Flashcard(
            deck_id=deck_id,
            front_text=word,
            back_text=translation,
            example_sentence=example if example else None,
            times_shown=1,
            times_known=1 if quality >= 4 else 0
        )
        session.add(card)
        await session.commit()
        await session.refresh(card)

        # Deck cards_count ni yangilash
        deck_result = await session.execute(
            select(FlashcardDeck).where(FlashcardDeck.id == deck_id)
        )
        deck = deck_result.scalar_one_or_none()
        if deck:
            deck.cards_count += 1
            await session.commit()

        is_new = True
    else:
        is_new = False

    # UserFlashcard yaratish yoki yangilash
    result = await session.execute(
        select(UserFlashcard).where(
            and_(
                UserFlashcard.user_id == user_id,
                UserFlashcard.card_id == card.id
            )
        )
    )
    user_card = result.scalar_one_or_none()

    if not user_card:
        # Tanlangan algoritm bo'yicha boshlang'ich qiymatlar
        interval, easiness, repetitions = SpacedRepetitionService.get_initial_values(
            algorithm=algorithm,
            quality=quality
        )

        user_card = UserFlashcard(
            user_id=user_id,
            card_id=card.id,
            easiness_factor=easiness,
            interval=interval,
            repetitions=repetitions,
            next_review_date=date.today() + timedelta(days=interval),
            last_review_date=date.today(),
            total_reviews=1,
            correct_reviews=1 if quality >= 3 else 0,
            is_learning=True
        )
        session.add(user_card)
        await session.commit()

    return is_new


# =====================================================
# SO'Z O'RGANISH REJIMI
# =====================================================

@router.callback_query(F.data == "learn:words")
async def start_learning(callback: CallbackQuery, db_user: User, state: FSMContext):
    """So'z o'rganishni boshlash"""

    # Sozlamalar tekshirish
    if not db_user.has_learning_settings:
        await callback.answer("⚙️ Avval sozlamalarni bajaring!", show_alert=True)
        return

    try:
        level_name = ""
        levels = await quiz_service.get_levels()
        for level in levels:
            if level["id"] == db_user.current_level_id:
                level_name = level["name"]
                break

        # Savollarni olish
        async with get_session() as session:
            question_repo = QuestionRepository(session)

            if db_user.current_day_id:
                questions = await question_repo.get_random_questions(
                    day_id=db_user.current_day_id,
                    count=20
                )
            else:
                questions = await question_repo.get_random_questions(
                    level_id=db_user.current_level_id,
                    count=20
                )

        if not questions:
            await callback.answer("❌ Bu kun uchun so'zlar topilmadi!", show_alert=True)
            return

        # So'zlarni tayyorlash
        words_data = []
        for q in questions:
            words_data.append({
                "id": q.id,
                "word": q.question_text,
                "translation": q.correct_text,
                "example": q.explanation or "",
                "options": [q.option_a, q.option_b, q.option_c, q.option_d],
                "correct_index": ["A", "B", "C", "D"].index(q.correct_option) if q.correct_option else 0
            })

        # State ga saqlash
        await state.set_state(LearningStates.learning)
        await state.update_data(
            words=words_data,
            current_index=0,
            learned_count=0,
            added_to_flashcard=0,
            level_name=level_name,
            level_id=db_user.current_level_id,
            day_number=db_user.current_day_number,
            start_time=datetime.utcnow().isoformat()
        )

        await show_word(callback.message, state, edit=True)
        await callback.answer()

    except Exception as e:
        logger.error(f"Start learning error: {e}")
        await callback.answer("❌ Xatolik yuz berdi!", show_alert=True)


async def show_word(message: Message, state: FSMContext, edit: bool = False):
    """Joriy so'zni ko'rsatish"""
    data = await state.get_data()
    words = data.get("words", [])
    current_index = data.get("current_index", 0)
    level_name = data.get("level_name", "")
    day_number = data.get("day_number", 1)

    if current_index >= len(words):
        await finish_learning(message, state, edit)
        return

    word = words[current_index]
    total = len(words)

    progress = (current_index / total) * 100
    progress_bar = "█" * int(progress / 10) + "░" * (10 - int(progress / 10))

    text = f"""
📚 <b>So'z o'rganish</b>
{level_name} | {day_number}-kun

<b>Progress:</b> {current_index + 1}/{total}
{progress_bar} {progress:.0f}%

━━━━━━━━━━━━━━━━━━

<b>🇩🇪 {word['word']}</b>

━━━━━━━━━━━━━━━━━━

<i>Tarjimani ko'rish uchun tugmani bosing</i>
"""

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👁 Tarjimani ko'rish", callback_data="learn:show_translation")
    )
    builder.row(
        InlineKeyboardButton(text="⏭ O'tkazib yuborish", callback_data="learn:skip"),
        InlineKeyboardButton(text="🏁 Tugatish", callback_data="learn:finish")
    )

    if edit:
        await message.edit_text(text, reply_markup=builder.as_markup())
    else:
        await message.answer(text, reply_markup=builder.as_markup())


@router.callback_query(F.data == "learn:show_translation", LearningStates.learning)
async def show_translation(callback: CallbackQuery, state: FSMContext):
    """Tarjimani ko'rsatish"""
    data = await state.get_data()
    words = data.get("words", [])
    current_index = data.get("current_index", 0)
    level_name = data.get("level_name", "")
    day_number = data.get("day_number", 1)

    if current_index >= len(words):
        await finish_learning(callback.message, state, edit=True)
        return

    word = words[current_index]
    total = len(words)

    progress = (current_index / total) * 100
    progress_bar = "█" * int(progress / 10) + "░" * (10 - int(progress / 10))

    example_text = f"\n\n📝 <i>{word['example']}</i>" if word['example'] else ""

    text = f"""
📚 <b>So'z o'rganish</b>
{level_name} | {day_number}-kun

<b>Progress:</b> {current_index + 1}/{total}
{progress_bar} {progress:.0f}%

━━━━━━━━━━━━━━━━━━

<b>🇩🇪 {word['word']}</b>

<b>🇺🇿 {word['translation']}</b>
{example_text}

━━━━━━━━━━━━━━━━━━

<i>Qanchalik yaxshi bildingiz?</i>
"""

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="❌ Bilmadim", callback_data="learn:didnt_know"),
        InlineKeyboardButton(text="🤔 Qiyin", callback_data="learn:hard")
    )
    builder.row(
        InlineKeyboardButton(text="✅ Bildim", callback_data="learn:knew"),
        InlineKeyboardButton(text="💯 Oson", callback_data="learn:easy")
    )
    builder.row(
        InlineKeyboardButton(text="🏁 Tugatish", callback_data="learn:finish")
    )

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


# =====================================================
# 4 TA TUGMA HANDLERLARI
# =====================================================

@router.callback_query(F.data == "learn:didnt_know", LearningStates.learning)
async def word_didnt_know(callback: CallbackQuery, db_user: User, state: FSMContext):
    """
    ❌ Bilmadim
    - Flashcard ga qo'shilmaydi
    - SM-2: Sessiya oxirida qayta ko'rsatiladi
    - Anki: DARHOL qayta chiqadi (2-3 so'zdan keyin)
    """
    data = await state.get_data()
    words = data.get("words", [])
    current_index = data.get("current_index", 0)
    algorithm = db_user.sr_algorithm or "sm2"

    if current_index < len(words):
        current_word = words[current_index].copy()
        # Xato sonini oshirish
        current_word['lapse_count'] = current_word.get('lapse_count', 0) + 1

        if algorithm == "anki":
            # ANKI: So'z darhol qayta chiqadi (2-3 so'zdan keyin)
            lapse_count = current_word['lapse_count']
            # Ko'p xato = tezroq qayta chiqadi
            insert_distance = max(2, 4 - lapse_count)  # 2-4 so'zdan keyin
            insert_position = min(current_index + insert_distance, len(words))
            words.insert(insert_position, current_word)
            msg = f"❌ {insert_distance} so'zdan keyin qayta chiqadi"
        else:
            # SM-2: Sessiya oxirida
            words.append(current_word)
            msg = "❌ Sessiya oxirida qayta ko'rasiz"

    await state.update_data(
        words=words,
        current_index=current_index + 1
    )

    await show_word(callback.message, state, edit=True)
    await callback.answer(msg)


@router.callback_query(F.data == "learn:hard", LearningStates.learning)
async def word_hard(callback: CallbackQuery, db_user: User, state: FSMContext):
    """
    🤔 Qiyin
    - Flashcard ga qo'shiladi (quality=3, ko'proq takrorlash)
    - Anki: Sessiyada ham qayta ko'rsatiladi
    """
    data = await state.get_data()
    words = data.get("words", [])
    current_index = data.get("current_index", 0)
    learned_count = data.get("learned_count", 0)
    added_to_flashcard = data.get("added_to_flashcard", 0)
    level_id = data.get("level_id")
    algorithm = db_user.sr_algorithm or "sm2"

    if current_index < len(words):
        word = words[current_index]

        # Flashcard ga qo'shish (foydalanuvchi algoritmini ishlatib)
        try:
            async with get_session() as session:
                deck = await get_or_create_learned_deck(session, db_user.user_id, level_id)
                is_new = await add_word_to_flashcard(
                    session=session,
                    user_id=db_user.user_id,
                    deck_id=deck.id,
                    word=word['word'],
                    translation=word['translation'],
                    example=word.get('example', ''),
                    quality=Quality.HARD,
                    algorithm=algorithm
                )
                if is_new:
                    added_to_flashcard += 1
        except Exception as e:
            logger.error(f"Add to flashcard error: {e}")

        # Anki: Qiyin so'zni sessiyada ham qayta ko'rsatish
        if algorithm == "anki":
            word_copy = word.copy()
            insert_position = min(current_index + 5, len(words))  # 5 so'zdan keyin
            words.insert(insert_position, word_copy)

    await state.update_data(
        words=words,
        current_index=current_index + 1,
        learned_count=learned_count + 0.5,
        added_to_flashcard=added_to_flashcard
    )

    await show_word(callback.message, state, edit=True)
    msg = "🤔 Flashcard ga qo'shildi"
    if algorithm == "anki":
        msg += " + qayta ko'rasiz"
    await callback.answer(msg)


@router.callback_query(F.data == "learn:knew", LearningStates.learning)
async def word_knew(callback: CallbackQuery, db_user: User, state: FSMContext):
    """
    ✅ Bildim
    - Flashcard ga qo'shiladi (quality=4)
    """
    data = await state.get_data()
    words = data.get("words", [])
    current_index = data.get("current_index", 0)
    learned_count = data.get("learned_count", 0)
    added_to_flashcard = data.get("added_to_flashcard", 0)
    level_id = data.get("level_id")

    if current_index < len(words):
        word = words[current_index]

        # Flashcard ga qo'shish (foydalanuvchi algoritmini ishlatib)
        try:
            async with get_session() as session:
                deck = await get_or_create_learned_deck(session, db_user.user_id, level_id)
                is_new = await add_word_to_flashcard(
                    session=session,
                    user_id=db_user.user_id,
                    deck_id=deck.id,
                    word=word['word'],
                    translation=word['translation'],
                    example=word.get('example', ''),
                    quality=Quality.GOOD,
                    algorithm=db_user.sr_algorithm or "sm2"
                )
                if is_new:
                    added_to_flashcard += 1

                # User statistikasini yangilash
                user_repo = UserRepository(session)
                user = await user_repo.get_by_user_id(db_user.user_id)
                if user:
                    user.add_words_learned(1)
                    await user_repo.save(user)
        except Exception as e:
            logger.error(f"Add to flashcard error: {e}")

    await state.update_data(
        current_index=current_index + 1,
        learned_count=learned_count + 1,
        added_to_flashcard=added_to_flashcard
    )

    await show_word(callback.message, state, edit=True)
    await callback.answer("✅ Flashcard ga qo'shildi")


@router.callback_query(F.data == "learn:easy", LearningStates.learning)
async def word_easy(callback: CallbackQuery, db_user: User, state: FSMContext):
    """
    💯 Oson
    - Flashcard ga qo'shiladi (quality=5)
    """
    data = await state.get_data()
    words = data.get("words", [])
    current_index = data.get("current_index", 0)
    learned_count = data.get("learned_count", 0)
    added_to_flashcard = data.get("added_to_flashcard", 0)
    level_id = data.get("level_id")

    if current_index < len(words):
        word = words[current_index]

        # Flashcard ga qo'shish (foydalanuvchi algoritmini ishlatib)
        try:
            async with get_session() as session:
                deck = await get_or_create_learned_deck(session, db_user.user_id, level_id)
                is_new = await add_word_to_flashcard(
                    session=session,
                    user_id=db_user.user_id,
                    deck_id=deck.id,
                    word=word['word'],
                    translation=word['translation'],
                    example=word.get('example', ''),
                    quality=Quality.EASY,
                    algorithm=db_user.sr_algorithm or "sm2"
                )
                if is_new:
                    added_to_flashcard += 1

                # User statistikasini yangilash
                user_repo = UserRepository(session)
                user = await user_repo.get_by_user_id(db_user.user_id)
                if user:
                    user.add_words_learned(1)
                    await user_repo.save(user)
        except Exception as e:
            logger.error(f"Add to flashcard error: {e}")

    await state.update_data(
        current_index=current_index + 1,
        learned_count=learned_count + 1,
        added_to_flashcard=added_to_flashcard
    )

    await show_word(callback.message, state, edit=True)
    await callback.answer("💯 Flashcard ga qo'shildi")


@router.callback_query(F.data == "learn:skip", LearningStates.learning)
async def word_skip(callback: CallbackQuery, state: FSMContext):
    """So'zni o'tkazib yuborish"""
    data = await state.get_data()
    current_index = data.get("current_index", 0)

    await state.update_data(current_index=current_index + 1)
    await show_word(callback.message, state, edit=True)
    await callback.answer()


@router.callback_query(F.data == "learn:finish")
async def learn_finish(callback: CallbackQuery, state: FSMContext):
    """O'rganishni tugatish"""
    await finish_learning(callback.message, state, edit=True)
    await callback.answer()


async def finish_learning(message: Message, state: FSMContext, edit: bool = False):
    """O'rganish sessiyasini yakunlash"""
    data = await state.get_data()
    learned_count = data.get("learned_count", 0)
    added_to_flashcard = data.get("added_to_flashcard", 0)
    level_name = data.get("level_name", "")
    day_number = data.get("day_number", 1)

    start_time = datetime.fromisoformat(data.get("start_time", datetime.utcnow().isoformat()))
    duration = (datetime.utcnow() - start_time).total_seconds()
    minutes = int(duration // 60)
    seconds = int(duration % 60)

    # Natija
    if learned_count >= 15:
        rating = "🌟 A'lo!"
        emoji = "🎉"
    elif learned_count >= 10:
        rating = "👍 Yaxshi"
        emoji = "😊"
    elif learned_count >= 5:
        rating = "📚 O'rtacha"
        emoji = "💪"
    else:
        rating = "🔄 Davom eting"
        emoji = "📝"

    text = f"""
{emoji} <b>O'rganish tugadi!</b>

📊 <b>Natija: {rating}</b>

<b>Statistika:</b>
├ 📝 O'rganilgan: {int(learned_count)} ta so'z
├ 🃏 Flashcard ga qo'shildi: {added_to_flashcard} ta
├ 📚 Daraja: {level_name}
├ 📅 Kun: {day_number}
└ ⏱ Vaqt: {minutes}:{seconds:02d}

💡 <i>Flashcard da takrorlashni unutmang!
So'zlar SM-2 algoritmi bilan takrorlanadi va
180+ kun interval bo'lganda arxivga tushadi.</i>
"""

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📚 Yana o'rganish", callback_data="learn:words"),
        InlineKeyboardButton(text="🃏 Flashcard", callback_data="flashcard:menu")
    )
    builder.row(
        InlineKeyboardButton(text="🎯 Quiz", callback_data="quick:start")
    )
    builder.row(
        InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="menu:main")
    )

    await state.clear()

    if edit:
        await message.edit_text(text, reply_markup=builder.as_markup())
    else:
        await message.answer(text, reply_markup=builder.as_markup())


@router.callback_query(F.data == "learn:next_day")
async def next_day(callback: CallbackQuery, db_user: User, state: FSMContext):
    """Keyingi kunga o'tish"""
    async with get_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_user_id(db_user.user_id)

        if user and user.current_level_id:
            days = await quiz_service.get_days(user.current_level_id)

            if days:
                current_day_num = user.current_day_number
                next_day_num = current_day_num + 1

                if next_day_num <= len(days):
                    user.current_day_number = next_day_num
                    user.current_day_id = days[next_day_num - 1]["id"]
                    user.total_days_completed += 1
                    await user_repo.save(user)

                    await callback.answer(f"📅 {next_day_num}-kunga o'tdingiz!", show_alert=True)
                else:
                    await callback.answer("🎉 Bu daraja tugadi! Keyingi darajaga o'ting.", show_alert=True)
                    return

    await start_learning(callback, db_user, state)
