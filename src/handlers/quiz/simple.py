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
from src.services import quiz_service
from src.repositories import QuestionRepository, ProgressRepository, StreakRepository
from src.repositories.spaced_rep_repo import SpacedRepetitionRepository
from src.keyboards.inline import language_keyboard, level_keyboard, day_keyboard, back_button
from src.core.logging import get_logger

logger = get_logger(__name__)
router = Router(name="simple_quiz")


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
        reply_markup=language_keyboard(languages)
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
        reply_markup=level_keyboard(levels, lang_id)
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
        reply_markup=day_keyboard(days, level_id)
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
async def review_mistakes(callback: CallbackQuery):
    """Review mistakes - simplified"""
    await callback.answer("📋 Xatolarni ko'rish tez orada qo'shiladi!", show_alert=True)


@router.callback_query(F.data == "quiz:cancel")
async def cancel_quiz(callback: CallbackQuery, state: FSMContext):
    """Cancel current quiz"""
    await state.clear()

    from src.keyboards.inline import main_menu_keyboard
    await callback.message.edit_text(
        "❌ Quiz bekor qilindi.",
        reply_markup=main_menu_keyboard()
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
    # TODO: Save vote to database
    await callback.answer("👍 Rahmat! Ovozingiz qabul qilindi.", show_alert=False)


@router.callback_query(F.data.startswith("vote:down:"))
async def vote_down(callback: CallbackQuery, db_user: User):
    """Downvote a question"""
    question_id = int(callback.data.split(":")[-1])
    # TODO: Save vote to database
    await callback.answer("👎 Rahmat! Fikringiz qabul qilindi.", show_alert=False)
