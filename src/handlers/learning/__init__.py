"""
Learning handlers - Word learning mode
"""
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from src.database import get_session
from src.database.models import User, Question
from src.repositories import QuestionRepository, UserRepository
from src.services import quiz_service
from src.core.logging import get_logger

logger = get_logger(__name__)
router = Router(name="learning")


class LearningStates(StatesGroup):
    """So'z o'rganish holatlari"""
    learning = State()
    quiz_check = State()


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

    # Joriy daraja va kunni olish
    try:
        level_name = ""
        levels = await quiz_service.get_levels()
        for level in levels:
            if level["id"] == db_user.current_level_id:
                level_name = level["name"]
                break

        # Savollarni (so'zlarni) olish
        async with get_session() as session:
            question_repo = QuestionRepository(session)

            # Joriy kun uchun savollar
            if db_user.current_day_id:
                questions = await question_repo.get_random_questions(
                    day_id=db_user.current_day_id,
                    count=20  # Bitta sessiya uchun 20 ta so'z
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
                "word": q.question_text,  # Savol matni = so'z
                "translation": q.correct_answer,  # To'g'ri javob = tarjima
                "example": q.explanation or "",  # Misol
                "options": [q.option_a, q.option_b, q.option_c, q.option_d],
                "correct_index": ["A", "B", "C", "D"].index(q.correct_option) if q.correct_option else 0
            })

        # State ga saqlash
        await state.set_state(LearningStates.learning)
        await state.update_data(
            words=words_data,
            current_index=0,
            learned_count=0,
            level_name=level_name,
            day_number=db_user.current_day_number,
            start_time=datetime.utcnow().isoformat()
        )

        # Birinchi so'zni ko'rsatish
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
    learned_count = data.get("learned_count", 0)
    level_name = data.get("level_name", "")
    day_number = data.get("day_number", 1)

    if current_index >= len(words):
        # Barcha so'zlar tugadi
        await finish_learning(message, state, edit)
        return

    word = words[current_index]
    total = len(words)

    # Progress bar
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
        InlineKeyboardButton(text="❌ Tugatish", callback_data="learn:finish")
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

    # Progress bar
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

<i>So'zni o'rgandingizmi?</i>
"""

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Bildim", callback_data="learn:knew"),
        InlineKeyboardButton(text="❌ Bilmadim", callback_data="learn:didnt_know")
    )
    builder.row(
        InlineKeyboardButton(text="🎯 Mini-test", callback_data="learn:mini_quiz")
    )
    builder.row(
        InlineKeyboardButton(text="❌ Tugatish", callback_data="learn:finish")
    )

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "learn:knew", LearningStates.learning)
async def word_knew(callback: CallbackQuery, db_user: User, state: FSMContext):
    """So'zni bildim"""
    data = await state.get_data()
    current_index = data.get("current_index", 0)
    learned_count = data.get("learned_count", 0)

    # Keyingi so'zga o'tish
    await state.update_data(
        current_index=current_index + 1,
        learned_count=learned_count + 1
    )

    # Foydalanuvchi statistikasini yangilash
    async with get_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_user_id(db_user.user_id)
        if user:
            user.add_words_learned(1)
            await user_repo.save(user)

    await show_word(callback.message, state, edit=True)
    await callback.answer("✅ Ajoyib!")


@router.callback_query(F.data == "learn:didnt_know", LearningStates.learning)
async def word_didnt_know(callback: CallbackQuery, state: FSMContext):
    """So'zni bilmadim - qayta ko'rish uchun oxiriga qo'shish"""
    data = await state.get_data()
    words = data.get("words", [])
    current_index = data.get("current_index", 0)

    if current_index < len(words):
        # Joriy so'zni oxiriga qo'shish
        current_word = words[current_index]
        words.append(current_word)

    # Keyingi so'zga o'tish
    await state.update_data(
        words=words,
        current_index=current_index + 1
    )

    await show_word(callback.message, state, edit=True)
    await callback.answer("📝 Keyinroq qayta ko'rasiz")


@router.callback_query(F.data == "learn:skip", LearningStates.learning)
async def word_skip(callback: CallbackQuery, state: FSMContext):
    """So'zni o'tkazib yuborish"""
    data = await state.get_data()
    current_index = data.get("current_index", 0)

    await state.update_data(current_index=current_index + 1)
    await show_word(callback.message, state, edit=True)
    await callback.answer()


@router.callback_query(F.data == "learn:mini_quiz", LearningStates.learning)
async def mini_quiz(callback: CallbackQuery, state: FSMContext):
    """Mini-test - joriy so'z uchun quiz"""
    data = await state.get_data()
    words = data.get("words", [])
    current_index = data.get("current_index", 0)

    if current_index >= len(words):
        await callback.answer("So'zlar tugadi!")
        return

    word = words[current_index]

    text = f"""
🎯 <b>Mini-test</b>

<b>🇩🇪 {word['word']}</b>

Tarjimasini toping:
"""

    builder = InlineKeyboardBuilder()

    # Variantlarni aralashtirish
    import random
    options = word['options'].copy()
    correct_answer = word['translation']

    # Correct answer ni qo'shish (agar yo'q bo'lsa)
    if correct_answer not in options:
        options[word['correct_index']] = correct_answer

    random.shuffle(options)
    correct_new_index = options.index(correct_answer) if correct_answer in options else 0

    # Variantlar tugmalari
    for i, option in enumerate(options):
        builder.row(
            InlineKeyboardButton(
                text=option,
                callback_data=f"learn:answer:{i}:{correct_new_index}"
            )
        )

    await state.set_state(LearningStates.quiz_check)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("learn:answer:"), LearningStates.quiz_check)
async def check_quiz_answer(callback: CallbackQuery, db_user: User, state: FSMContext):
    """Mini-test javobini tekshirish"""
    parts = callback.data.split(":")
    selected = int(parts[2])
    correct = int(parts[3])

    data = await state.get_data()
    words = data.get("words", [])
    current_index = data.get("current_index", 0)
    learned_count = data.get("learned_count", 0)

    word = words[current_index] if current_index < len(words) else None

    if selected == correct:
        # To'g'ri javob
        await state.update_data(
            current_index=current_index + 1,
            learned_count=learned_count + 1
        )

        # Statistikani yangilash
        async with get_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_user_id(db_user.user_id)
            if user:
                user.add_words_learned(1)
                await user_repo.save(user)

        await callback.answer("✅ To'g'ri! Ajoyib!")
    else:
        # Noto'g'ri - qayta ko'rish uchun oxiriga qo'shish
        if word:
            words.append(word)
        await state.update_data(
            words=words,
            current_index=current_index + 1
        )
        await callback.answer("❌ Noto'g'ri. Keyinroq qayta ko'rasiz.")

    # Keyingi so'zga o'tish
    await state.set_state(LearningStates.learning)
    await show_word(callback.message, state, edit=True)


@router.callback_query(F.data == "learn:finish")
async def learn_finish(callback: CallbackQuery, state: FSMContext):
    """O'rganishni tugatish"""
    await finish_learning(callback.message, state, edit=True)
    await callback.answer()


async def finish_learning(message: Message, state: FSMContext, edit: bool = False):
    """O'rganish sessiyasini yakunlash"""
    data = await state.get_data()
    learned_count = data.get("learned_count", 0)
    words = data.get("words", [])
    level_name = data.get("level_name", "")
    day_number = data.get("day_number", 1)

    start_time = datetime.fromisoformat(data.get("start_time", datetime.utcnow().isoformat()))
    duration = (datetime.utcnow() - start_time).total_seconds()
    minutes = int(duration // 60)
    seconds = int(duration % 60)

    # Natija
    if learned_count >= 10:
        rating = "🌟 A'lo!"
        emoji = "🎉"
    elif learned_count >= 5:
        rating = "👍 Yaxshi"
        emoji = "😊"
    else:
        rating = "💪 Davom eting"
        emoji = "📚"

    text = f"""
{emoji} <b>O'rganish tugadi!</b>

📊 <b>Natija: {rating}</b>

<b>Statistika:</b>
├ 📝 O'rganilgan so'zlar: {learned_count}
├ 📚 Daraja: {level_name}
├ 📅 Kun: {day_number}
└ ⏱ Vaqt: {minutes}:{seconds:02d}

{"🏆 Ajoyib natija!" if learned_count >= 10 else ""}
"""

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📚 Yana o'rganish", callback_data="learn:words"),
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
    from src.services import quiz_service

    async with get_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_user_id(db_user.user_id)

        if user and user.current_level_id:
            # Keyingi kunni olish
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

    # Yangi kunni boshlash
    await start_learning(callback, db_user, state)
