"""
Simple Quiz Handler - Uses inline buttons for immediate response
"""
from datetime import datetime
from typing import Dict, Any, List
import random

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.database import get_session
from src.database.models import User, Question
from src.database.models.flashcard import Flashcard, UserFlashcard
from src.services import quiz_service
from src.services.sr_algorithm import SpacedRepetitionService, Quality
from src.repositories import QuestionRepository, ProgressRepository, StreakRepository, UserRepository
from src.repositories.spaced_rep_repo import SpacedRepetitionRepository
from src.repositories.flashcard_repo import UserFlashcardRepository
from src.keyboards.inline import language_keyboard, level_keyboard, day_keyboard, back_button
from src.core.logging import get_logger

logger = get_logger(__name__)
router = Router(name="simple_quiz")


# ============================================================
# FLASHCARD INTEGRATION
# ============================================================

async def update_flashcard_from_quiz(
    session,
    user_id: int,
    question_text: str,
    is_correct: bool,
    algorithm: str = None  # None bo'lsa foydalanuvchi sozlamasidan olinadi
) -> bool:
    """
    Quiz javobiga qarab UserFlashcard ni yangilash.

    Agar so'z Flashcard da mavjud bo'lsa:
    - To'g'ri javob: interval oshadi (algoritm bo'yicha)
    - Noto'g'ri javob: interval qaytariladi

    Returns: True if flashcard was updated, False otherwise
    """
    from sqlalchemy import select, and_
    from datetime import date, timedelta

    # Agar algoritm berilmagan bo'lsa, foydalanuvchi sozlamasidan olish
    if algorithm is None:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_user_id(user_id)
        algorithm = user.sr_algorithm if user else "sm2"

    # Flashcard ni so'z bo'yicha topish
    result = await session.execute(
        select(Flashcard).where(Flashcard.front_text == question_text)
    )
    card = result.scalar_one_or_none()

    if not card:
        return False

    # UserFlashcard ni topish
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
        return False

    # Quality aniqlash
    quality = Quality.GOOD if is_correct else Quality.AGAIN

    # Tanlangan algoritm bilan hisoblash
    result = SpacedRepetitionService.calculate_next_review(
        algorithm=algorithm,
        quality=quality,
        current_interval=user_card.interval,
        current_easiness=user_card.easiness_factor,
        current_repetitions=user_card.repetitions,
        is_learning=user_card.is_learning
    )

    # Natijalarni saqlash
    user_card.interval = result.interval
    user_card.easiness_factor = result.easiness
    user_card.repetitions = result.repetitions
    user_card.next_review_date = result.next_review
    user_card.last_review_date = date.today()
    user_card.total_reviews += 1
    user_card.is_learning = not result.is_graduated

    if is_correct:
        user_card.correct_reviews += 1

    # Arxivga tushish
    if result.is_suspended:
        user_card.is_suspended = True

    await session.commit()
    return True


class QuizStates(StatesGroup):
    """Quiz FSM states"""
    selecting_language = State()
    selecting_level = State()
    selecting_day = State()
    selecting_count = State()
    in_quiz = State()


# ============================================================
# QUIZ SELECTION FLOW
# ============================================================

@router.callback_query(F.data == "quiz:start")
async def quiz_start(callback: CallbackQuery, state: FSMContext, db_user: User):
    """Start quiz selection"""
    languages = await quiz_service.get_languages()
    
    if not languages:
        await callback.answer("❌ Tillar mavjud emas.", show_alert=True)
        return
    
    await state.set_state(QuizStates.selecting_language)
    await callback.message.edit_text(
        "📚 <b>Quiz boshlash</b>\n\nTilni tanlang:",
        reply_markup=await language_keyboard(languages)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("quiz:lang:"), QuizStates.selecting_language)
async def select_language(callback: CallbackQuery, state: FSMContext):
    """Language selected"""
    lang_id = int(callback.data.split(":")[-1])
    await state.update_data(language_id=lang_id)
    
    levels = await quiz_service.get_levels(lang_id)
    
    if not levels:
        await callback.answer("❌ Darajalar mavjud emas.", show_alert=True)
        return
    
    await state.set_state(QuizStates.selecting_level)
    await callback.message.edit_text(
        "📊 <b>Darajani tanlang:</b>",
        reply_markup=await level_keyboard(levels, lang_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("quiz:level:"), QuizStates.selecting_level)
async def select_level(callback: CallbackQuery, state: FSMContext):
    """Level selected"""
    level_id = int(callback.data.split(":")[-1])
    data = await state.get_data()
    await state.update_data(level_id=level_id)
    
    days = await quiz_service.get_days(level_id)
    
    if not days:
        await callback.answer("❌ Kunliklar mavjud emas.", show_alert=True)
        return
    
    await state.set_state(QuizStates.selecting_day)
    await callback.message.edit_text(
        "📅 <b>Kunlikni tanlang:</b>",
        reply_markup=await day_keyboard(days, level_id=level_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("quiz:day:"))
async def select_day(callback: CallbackQuery, state: FSMContext):
    """Day selected - works with or without state"""
    parts = callback.data.split(":")
    day_id = int(parts[2])
    # Optional level_id for direct access (e.g., from "Next day" button)
    level_id = int(parts[3]) if len(parts) > 3 else None

    if level_id:
        await state.update_data(level_id=level_id)
    await state.update_data(day_id=day_id)
    
    await state.set_state(QuizStates.selecting_count)
    
    builder = InlineKeyboardBuilder()
    for count in [5, 10, 15, 20]:
        builder.add(InlineKeyboardButton(
            text=f"📝 {count} ta",
            callback_data=f"quiz:count:{count}"
        ))
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="◀️ Orqaga", callback_data="quiz:start"))
    
    await callback.message.edit_text(
        "🔢 <b>Nechta savol?</b>",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("quiz:count:"), QuizStates.selecting_count)
async def start_quiz(callback: CallbackQuery, state: FSMContext, db_user: User):
    """Start the quiz"""
    count = int(callback.data.split(":")[-1])
    data = await state.get_data()
    day_id = data.get("day_id")
    
    # Get questions
    async with get_session() as session:
        repo = QuestionRepository(session)
        questions = await repo.get_random_questions(day_id=day_id, count=count)
    
    if not questions:
        await callback.answer("❌ Savollar topilmadi.", show_alert=True)
        return
    
    # Prepare quiz data
    quiz_data = {
        "questions": [
            {
                "id": q.id,
                "text": q.question_text,
                "options": [q.option_a, q.option_b, q.option_c, q.option_d],
                "correct": q.correct_index,
                "explanation": q.explanation
            }
            for q in questions
        ],
        "current": 0,
        "correct_count": 0,
        "wrong_count": 0,
        "answers": [],
        "start_time": datetime.utcnow().isoformat(),
        "language_id": data.get("language_id"),
        "level_id": data.get("level_id"),
        "day_id": day_id
    }
    
    await state.update_data(quiz=quiz_data)
    await state.set_state(QuizStates.in_quiz)
    
    # Send first question
    await send_question(callback.message, quiz_data, 0)
    await callback.answer()


async def send_question(message: Message, quiz_data: Dict, index: int):
    """Send question with inline buttons"""
    questions = quiz_data["questions"]
    q = questions[index]
    total = len(questions)
    
    # Shuffle options
    options = list(enumerate(q["options"]))  # [(0, "A"), (1, "B"), ...]
    random.shuffle(options)
    
    # Build keyboard
    builder = InlineKeyboardBuilder()
    for orig_idx, option_text in options:
        builder.row(InlineKeyboardButton(
            text=option_text,
            callback_data=f"answer:{index}:{orig_idx}"
        ))
    
    # Add skip button
    builder.row(InlineKeyboardButton(
        text="⏭ O'tkazib yuborish",
        callback_data=f"skip:{index}"
    ))
    
    text = (
        f"📝 <b>Savol {index + 1}/{total}</b>\n\n"
        f"{q['text']}"
    )
    
    try:
        await message.edit_text(text, reply_markup=builder.as_markup())
    except Exception:
        await message.answer(text, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("answer:"), QuizStates.in_quiz)
async def handle_answer(callback: CallbackQuery, state: FSMContext, db_user: User):
    """Handle answer selection"""
    parts = callback.data.split(":")
    q_index = int(parts[1])
    selected = int(parts[2])
    
    data = await state.get_data()
    quiz_data = data.get("quiz", {})
    questions = quiz_data.get("questions", [])
    
    if q_index >= len(questions):
        await callback.answer("❌ Xatolik!", show_alert=True)
        return
    
    q = questions[q_index]
    is_correct = selected == q["correct"]
    
    # Update stats
    if is_correct:
        quiz_data["correct_count"] += 1
        emoji = "✅"
    else:
        quiz_data["wrong_count"] += 1
        emoji = "❌"
    
    quiz_data["answers"].append({
        "question_id": q["id"],
        "selected": selected,
        "correct": q["correct"],
        "is_correct": is_correct
    })

    # SM-2: Record answer for spaced repetition
    try:
        async with get_session() as session:
            sr_repo = SpacedRepetitionRepository(session)
            await sr_repo.record_answer(
                user_id=db_user.user_id,
                question_id=q["id"],
                is_correct=is_correct
            )
    except Exception as e:
        logger.debug(f"SM-2 record error: {e}")

    # Flashcard: Update UserFlashcard if word exists
    try:
        async with get_session() as session:
            await update_flashcard_from_quiz(
                session=session,
                user_id=db_user.user_id,
                question_text=q["text"],
                is_correct=is_correct
            )
    except Exception as e:
        logger.debug(f"Flashcard update error: {e}")

    # Show result briefly
    correct_text = q["options"][q["correct"]]
    explanation = q.get("explanation", "")
    
    result_text = f"{emoji} "
    if is_correct:
        result_text += "<b>To'g'ri!</b>"
    else:
        result_text += f"<b>Noto'g'ri!</b>\n✅ To'g'ri javob: {correct_text}"
    
    if explanation:
        result_text += f"\n\n💡 {explanation}"
    
    await callback.answer(
        "✅ To'g'ri!" if is_correct else f"❌ Noto'g'ri! Javob: {correct_text}",
        show_alert=False
    )
    
    # Move to next question or finish
    next_index = q_index + 1
    quiz_data["current"] = next_index
    await state.update_data(quiz=quiz_data)
    
    if next_index >= len(questions):
        # Quiz finished
        await finish_quiz(callback.message, quiz_data, db_user, state)
    else:
        # Next question
        await send_question(callback.message, quiz_data, next_index)


@router.callback_query(F.data.startswith("skip:"), QuizStates.in_quiz)
async def handle_skip(callback: CallbackQuery, state: FSMContext, db_user: User):
    """Skip current question"""
    parts = callback.data.split(":")
    q_index = int(parts[1])
    
    data = await state.get_data()
    quiz_data = data.get("quiz", {})
    questions = quiz_data.get("questions", [])
    
    if q_index >= len(questions):
        return
    
    q = questions[q_index]
    
    # Count as wrong
    quiz_data["wrong_count"] += 1
    quiz_data["answers"].append({
        "question_id": q["id"],
        "selected": -1,
        "correct": q["correct"],
        "is_correct": False
    })

    # Flashcard: Update as wrong answer
    try:
        async with get_session() as session:
            await update_flashcard_from_quiz(
                session=session,
                user_id=db_user.user_id,
                question_text=q["text"],
                is_correct=False
            )
    except Exception as e:
        logger.debug(f"Flashcard update error: {e}")

    await callback.answer("⏭ O'tkazib yuborildi", show_alert=False)
    
    # Move to next
    next_index = q_index + 1
    quiz_data["current"] = next_index
    await state.update_data(quiz=quiz_data)
    
    if next_index >= len(questions):
        await finish_quiz(callback.message, quiz_data, db_user, state)
    else:
        await send_question(callback.message, quiz_data, next_index)


async def finish_quiz(message: Message, quiz_data: Dict, db_user: User, state: FSMContext):
    """Finish quiz and show results"""
    correct = quiz_data["correct_count"]
    wrong = quiz_data["wrong_count"]
    total = correct + wrong
    percentage = (correct / total * 100) if total > 0 else 0

    # Determine rating
    if percentage >= 90:
        rating = "🏆 A'lo!"
        emoji = "🌟"
    elif percentage >= 70:
        rating = "👍 Yaxshi!"
        emoji = "⭐"
    elif percentage >= 50:
        rating = "📚 O'rtacha"
        emoji = "💪"
    else:
        rating = "📖 Ko'proq mashq qiling"
        emoji = "💡"

    # Xato javoblarni Redis'ga saqlash (takrorlash uchun)
    wrong_questions = []
    for answer in quiz_data.get("answers", []):
        if not answer.get("is_correct"):
            wrong_questions.append(answer.get("question_id"))

    if wrong_questions:
        try:
            from src.core.redis import redis_client
            import json
            # Oxirgi 50 ta xatoni saqlash
            key = f"wrong_answers:{db_user.user_id}"
            existing = await redis_client.get(key)
            if existing:
                existing_list = json.loads(existing)
            else:
                existing_list = []
            # Yangilarini qo'shish (dublikatlar yo'q)
            for qid in wrong_questions:
                if qid not in existing_list:
                    existing_list.append(qid)
            # Oxirgi 50 tasini saqlash
            existing_list = existing_list[-50:]
            await redis_client.set(key, json.dumps(existing_list), ex=604800)  # 7 kun
        except Exception as e:
            logger.debug(f"Wrong answers save error: {e}")

    # Save to database
    try:
        async with get_session() as session:
            progress_repo = ProgressRepository(session)
            await progress_repo.save_quiz_result(
                user_id=db_user.user_id,
                correct=correct,
                wrong=wrong,
                total=total,
                score=percentage,
                language_id=quiz_data.get("language_id"),
                level_id=quiz_data.get("level_id"),
                day_id=quiz_data.get("day_id"),
                quiz_type="personal"
            )
            
            # Update streak
            streak_repo = StreakRepository(session)
            streak_result = await streak_repo.update_streak(db_user.user_id)
            streak_text = ""
            if streak_result.get("streak_increased"):
                current = streak_result.get("current_streak", 1)
                streak_text = f"\n\n🔥 Streak: {current} kun"
    except Exception as e:
        logger.error(f"Error saving quiz result: {e}")
        streak_text = ""
    
    # Get next day suggestion
    next_day_text = ""
    next_day_callback = None
    current_day_id = quiz_data.get("day_id")
    level_id = quiz_data.get("level_id")

    if current_day_id and level_id:
        try:
            async with get_session() as session:
                from src.services.quiz_service import QuizService
                quiz_service = QuizService(session)
                days = await quiz_service.get_days(level_id)

                # Find current day index and get next day
                current_idx = -1
                for i, day in enumerate(days):
                    if day["id"] == current_day_id:
                        current_idx = i
                        break

                if current_idx >= 0 and current_idx < len(days) - 1:
                    next_day = days[current_idx + 1]
                    next_day_text = f"\n\n📚 <b>Keyingi:</b> {next_day['topic']}"
                    next_day_callback = f"quiz:day:{next_day['id']}:{level_id}"
                elif current_idx == len(days) - 1:
                    next_day_text = "\n\n🎉 <b>Bu daraja tugadi! Keyingi darajaga o'ting!</b>"
        except Exception as e:
            logger.debug(f"Error getting next day: {e}")

    # Build result message
    text = (
        f"{emoji} <b>Quiz yakunlandi!</b>\n\n"
        f"📊 <b>Natija:</b>\n"
        f"✅ To'g'ri: {correct}\n"
        f"❌ Noto'g'ri: {wrong}\n"
        f"📈 Foiz: {percentage:.0f}%\n\n"
        f"<b>{rating}</b>"
        f"{streak_text}"
        f"{next_day_text}"
    )

    # Build keyboard
    builder = InlineKeyboardBuilder()

    # Add "Next day" button if available
    if next_day_callback:
        builder.row(InlineKeyboardButton(
            text="▶️ Keyingi kun",
            callback_data=next_day_callback
        ))

    builder.row(InlineKeyboardButton(
        text="🔄 Yana o'ynash",
        callback_data="quiz:start"
    ))
    builder.row(InlineKeyboardButton(
        text="📋 Xatolarni ko'rish",
        callback_data="quiz:review"
    ))
    builder.row(InlineKeyboardButton(
        text="🏠 Bosh menyu",
        callback_data="menu:main"
    ))
    
    await state.clear()

    try:
        await message.edit_text(text, reply_markup=builder.as_markup())
    except Exception:
        await message.answer(text, reply_markup=builder.as_markup())


@router.callback_query(F.data == "quiz:review")
async def review_mistakes(callback: CallbackQuery, db_user: User):
    """Review wrong answers"""
    try:
        from src.core.redis import redis_client
        import json

        key = f"wrong_answers:{db_user.user_id}"
        data = await redis_client.get(key)

        if not data:
            await callback.answer("✅ Xato javoblar yo'q! Ajoyib!", show_alert=True)
            return

        wrong_ids = json.loads(data)

        if not wrong_ids:
            await callback.answer("✅ Xato javoblar yo'q!", show_alert=True)
            return

        # So'nggi 10 ta xatoni ko'rsatish
        async with get_session() as session:
            repo = QuestionRepository(session)
            questions = []
            for qid in wrong_ids[-10:]:
                q = await repo.get_by_id(qid)
                if q:
                    questions.append(q)

        if not questions:
            await callback.answer("❌ Savollar topilmadi", show_alert=True)
            return

        text = "📋 <b>Oxirgi xatolar</b>\n\n"
        for i, q in enumerate(questions, 1):
            correct_answer = [q.option_a, q.option_b, q.option_c, q.option_d][q.correct_index]
            text += f"<b>{i}.</b> {q.question_text}\n"
            text += f"   ✅ <i>{correct_answer}</i>\n\n"

        text += f"\n📊 Jami xatolar: <b>{len(wrong_ids)}</b> ta"

        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(
            text="🔄 Xatolarni takrorlash",
            callback_data="quiz:retry_mistakes"
        ))
        builder.row(InlineKeyboardButton(
            text="🗑 Xatolarni tozalash",
            callback_data="quiz:clear_mistakes"
        ))
        builder.row(InlineKeyboardButton(
            text="🏠 Bosh menyu",
            callback_data="menu:main"
        ))

        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()

    except Exception as e:
        logger.error(f"Review mistakes error: {e}")
        await callback.answer("❌ Xatolik yuz berdi", show_alert=True)


@router.callback_query(F.data == "quiz:retry_mistakes")
async def retry_mistakes(callback: CallbackQuery, state: FSMContext, db_user: User):
    """Quiz from wrong answers"""
    try:
        from src.core.redis import redis_client
        import json

        key = f"wrong_answers:{db_user.user_id}"
        data = await redis_client.get(key)

        if not data:
            await callback.answer("✅ Xato javoblar yo'q!", show_alert=True)
            return

        wrong_ids = json.loads(data)

        if not wrong_ids:
            await callback.answer("✅ Xato javoblar yo'q!", show_alert=True)
            return

        # Savollarni olish
        async with get_session() as session:
            repo = QuestionRepository(session)
            questions = []
            for qid in wrong_ids[-20:]:  # Maksimum 20 ta
                q = await repo.get_by_id(qid)
                if q:
                    questions.append(q)

        if not questions:
            await callback.answer("❌ Savollar topilmadi", show_alert=True)
            return

        random.shuffle(questions)
        questions = questions[:min(len(questions), 10)]  # 10 tagacha

        # Quiz boshlash
        quiz_data = {
            "questions": [
                {
                    "id": q.id,
                    "text": q.question_text,
                    "options": [q.option_a, q.option_b, q.option_c, q.option_d],
                    "correct": q.correct_index,
                    "explanation": q.explanation
                }
                for q in questions
            ],
            "current": 0,
            "correct_count": 0,
            "wrong_count": 0,
            "answers": [],
            "start_time": datetime.utcnow().isoformat(),
            "is_retry": True
        }

        await state.update_data(quiz=quiz_data)
        await state.set_state(QuizStates.in_quiz)

        await callback.answer("🔄 Xatolarni takrorlash boshlanmoqda!")
        await send_question(callback.message, quiz_data, 0)

    except Exception as e:
        logger.error(f"Retry mistakes error: {e}")
        await callback.answer("❌ Xatolik yuz berdi", show_alert=True)


@router.callback_query(F.data == "quiz:clear_mistakes")
async def clear_mistakes(callback: CallbackQuery, db_user: User):
    """Clear wrong answers"""
    try:
        from src.core.redis import redis_client

        key = f"wrong_answers:{db_user.user_id}"
        await redis_client.delete(key)

        await callback.answer("🗑 Xatolar tozalandi!", show_alert=True)

        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(
            text="🎯 Yangi quiz",
            callback_data="quiz:start"
        ))
        builder.row(InlineKeyboardButton(
            text="🏠 Bosh menyu",
            callback_data="menu:main"
        ))

        await callback.message.edit_text(
            "✅ <b>Xatolar tozalandi!</b>\n\n"
            "Endi yangi quizda omad!",
            reply_markup=builder.as_markup()
        )

    except Exception as e:
        logger.error(f"Clear mistakes error: {e}")
        await callback.answer("❌ Xatolik yuz berdi", show_alert=True)


@router.callback_query(F.data == "quiz:cancel")
async def cancel_quiz(callback: CallbackQuery, state: FSMContext):
    """Cancel current quiz"""
    await state.clear()

    from src.keyboards.inline import main_menu_keyboard
    await callback.message.edit_text(
        "❌ Quiz bekor qilindi.",
        reply_markup=await main_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("quiz:audio:"))
async def play_audio(callback: CallbackQuery):
    """Play audio for question"""
    await callback.answer("🔊 Audio funksiyasi tez orada qo'shiladi!", show_alert=True)


@router.callback_query(F.data.startswith("quiz:retry:"))
async def retry_quiz(callback: CallbackQuery, state: FSMContext):
    """Retry quiz with same day"""
    day_id = int(callback.data.split(":")[-1])

    # Set state and redirect to day selection
    await state.set_state(QuizStates.selecting_count)
    await state.update_data(day_id=day_id)

    builder = InlineKeyboardBuilder()
    for count in [5, 10, 15, 20]:
        builder.add(InlineKeyboardButton(
            text=f"📝 {count} ta",
            callback_data=f"quiz:count:{count}"
        ))
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="◀️ Orqaga", callback_data="quiz:start"))

    await callback.message.edit_text(
        "🔄 <b>Qayta urinish</b>\n\nNechta savol?",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data == "quiz:skip", QuizStates.in_quiz)
async def quiz_skip_current(callback: CallbackQuery, state: FSMContext, db_user: User):
    """Skip current question (alternative callback)"""
    data = await state.get_data()
    quiz_data = data.get("quiz", {})
    current = quiz_data.get("current", 0)

    # Redirect to existing skip handler
    callback.data = f"skip:{current}"
    await handle_skip(callback, state, db_user)


@router.callback_query(F.data.startswith("vote:up:"))
async def vote_up(callback: CallbackQuery, db_user: User):
    """Upvote a question"""
    question_id = int(callback.data.split(":")[-1])

    try:
        async with get_session() as session:
            question_repo = QuestionRepository(session)
            question = await question_repo.get_by_id(question_id)
            if question:
                # Increment upvotes
                question.upvotes = (question.upvotes or 0) + 1
                await session.commit()
                logger.debug(f"Question {question_id} upvoted by user {db_user.user_id}")
    except Exception as e:
        logger.error(f"Vote save error: {e}")

    await callback.answer("👍 Rahmat! Ovozingiz qabul qilindi.", show_alert=False)


@router.callback_query(F.data.startswith("vote:down:"))
async def vote_down(callback: CallbackQuery, db_user: User):
    """Downvote a question"""
    question_id = int(callback.data.split(":")[-1])

    try:
        async with get_session() as session:
            question_repo = QuestionRepository(session)
            question = await question_repo.get_by_id(question_id)
            if question:
                # Increment downvotes
                question.downvotes = (question.downvotes or 0) + 1
                await session.commit()
                logger.debug(f"Question {question_id} downvoted by user {db_user.user_id}")
    except Exception as e:
        logger.error(f"Vote save error: {e}")

    await callback.answer("👎 Rahmat! Fikringiz qabul qilindi.", show_alert=False)
