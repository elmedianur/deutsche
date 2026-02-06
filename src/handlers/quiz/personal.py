"""
Personal Quiz Handler - Telegram Native Poll/Quiz with Auto-advance
TO'G'RILANGAN VERSIYA - day_keyboard chaqiruvida level_id qo'shildi
YANGILANGAN: Thread-safe session management, memory leak tuzatildi
"""
import asyncio
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any

from aiogram import Router, F, Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery, PollAnswer
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from src.database import get_session
from src.database.models import User, Question
from src.database.models.flashcard import Flashcard, UserFlashcard
from src.services import quiz_service
from src.repositories import QuestionRepository, ProgressRepository, StreakRepository, UserRepository
from src.repositories.spaced_rep_repo import SpacedRepetitionRepository
from src.services.sr_algorithm import SpacedRepetitionService, Quality
from src.keyboards.inline import (
    language_keyboard,
    level_keyboard,
    day_keyboard,
    question_count_keyboard,
    quiz_result_keyboard,
    back_button,
)
from src.core.logging import get_logger
from src.core.utils import utc_today
from src.services.audio_service import AudioService
from src.services.xp_service import XPService
from src.config import settings

logger = get_logger(__name__)
router = Router(name="personal_quiz")


# ============================================================
# FLASHCARD INTEGRATION
# ============================================================

async def update_flashcard_from_quiz(
    session,
    user_id: int,
    question_text: str,
    is_correct: bool,
    algorithm: str = None
) -> bool:
    """Quiz javobiga qarab UserFlashcard ni yangilash."""
    from sqlalchemy import select, and_
    from datetime import date, timedelta

    if algorithm is None:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_user_id(user_id)
        algorithm = user.sr_algorithm if user else "sm2"

    result = await session.execute(
        select(Flashcard).where(Flashcard.front_text == question_text)
    )
    card = result.scalar_one_or_none()
    if not card:
        return False

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

    quality = Quality.GOOD if is_correct else Quality.AGAIN
    result = SpacedRepetitionService.calculate_next_review(
        algorithm=algorithm,
        quality=quality,
        current_interval=user_card.interval,
        current_easiness=user_card.easiness_factor,
        current_repetitions=user_card.repetitions,
        is_learning=user_card.is_learning
    )

    user_card.interval = result.interval
    user_card.easiness_factor = result.easiness
    user_card.repetitions = result.repetitions
    user_card.next_review_date = result.next_review
    user_card.last_review_date = utc_today()
    user_card.total_reviews += 1
    user_card.is_learning = not result.is_graduated

    if is_correct:
        user_card.correct_reviews += 1

    if result.is_suspended:
        user_card.is_suspended = True

    await session.flush()
    return True


# ============================================================
# THREAD-SAFE SESSION MANAGER - Memory leak va race condition tuzatildi
# ============================================================

class SessionManager:
    """
    Thread-safe session manager with TTL and max size limits.
    Memory leak va race condition muammolarini hal qiladi.
    """

    def __init__(self, max_size: int = 10000, default_ttl: int = 1800):
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._max_size = max_size
        self._default_ttl = default_ttl  # 30 daqiqa default

    def set(self, key: str, value: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Session qo'shish - thread-safe"""
        with self._lock:
            # Max size tekshirish - eng eski sessionlarni o'chirish
            if len(self._sessions) >= self._max_size:
                self._evict_oldest(count=self._max_size // 10)  # 10% o'chirish

            value["_created_at"] = datetime.utcnow()
            value["_ttl"] = ttl or self._default_ttl
            self._sessions[key] = value
            return True

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Session olish - TTL tekshirish bilan"""
        with self._lock:
            if key not in self._sessions:
                return None

            session = self._sessions[key]
            created_at = session.get("_created_at", datetime.utcnow())
            ttl = session.get("_ttl", self._default_ttl)

            # TTL tekshirish
            if (datetime.utcnow() - created_at).total_seconds() > ttl:
                del self._sessions[key]
                return None

            return session

    def delete(self, key: str) -> bool:
        """Session o'chirish"""
        with self._lock:
            if key in self._sessions:
                del self._sessions[key]
                return True
            return False

    def pop(self, key: str) -> Optional[Dict[str, Any]]:
        """Session olish va o'chirish"""
        with self._lock:
            return self._sessions.pop(key, None)

    def cleanup_expired(self) -> int:
        """Muddati o'tgan sessionlarni tozalash"""
        with self._lock:
            now = datetime.utcnow()
            expired_keys = []

            for key, session in self._sessions.items():
                created_at = session.get("_created_at", now)
                ttl = session.get("_ttl", self._default_ttl)

                if (now - created_at).total_seconds() > ttl:
                    expired_keys.append(key)

            for key in expired_keys:
                del self._sessions[key]

            return len(expired_keys)

    def _evict_oldest(self, count: int = 100):
        """Eng eski sessionlarni o'chirish (max size uchun)"""
        if not self._sessions:
            return

        # created_at bo'yicha saralash
        sorted_keys = sorted(
            self._sessions.keys(),
            key=lambda k: self._sessions[k].get("_created_at", datetime.min)
        )

        # Eng eskilarini o'chirish
        for key in sorted_keys[:count]:
            del self._sessions[key]

        logger.warning(f"Session eviction: {count} sessions removed due to max size limit")

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None


class TimerManager:
    """Thread-safe timer manager"""

    def __init__(self, max_timers: int = 5000):
        self._timers: Dict[int, asyncio.Task] = {}
        self._lock = threading.RLock()
        self._max_timers = max_timers

    def set(self, user_id: int, task: asyncio.Task) -> None:
        """Timer qo'shish - avvalgisini bekor qilish bilan"""
        with self._lock:
            # Avvalgi timerni bekor qilish
            if user_id in self._timers:
                old_task = self._timers[user_id]
                if not old_task.done() and not old_task.cancelled():
                    old_task.cancel()

            self._timers[user_id] = task

            # Max limit tekshirish
            if len(self._timers) > self._max_timers:
                self._cleanup_done_timers()

    def cancel(self, user_id: int) -> bool:
        """Timerni bekor qilish"""
        with self._lock:
            if user_id in self._timers:
                task = self._timers[user_id]
                if not task.done() and not task.cancelled():
                    task.cancel()
                del self._timers[user_id]
                return True
            return False

    def get(self, user_id: int) -> Optional[asyncio.Task]:
        """Timer olish"""
        with self._lock:
            return self._timers.get(user_id)

    def _cleanup_done_timers(self) -> int:
        """Tugagan timerlarni tozalash"""
        done_keys = [
            uid for uid, task in self._timers.items()
            if task.done() or task.cancelled()
        ]
        for key in done_keys:
            del self._timers[key]
        return len(done_keys)

    def cleanup(self) -> int:
        """Manual cleanup"""
        with self._lock:
            return self._cleanup_done_timers()

    def __len__(self) -> int:
        with self._lock:
            return len(self._timers)

    def __contains__(self, user_id: int) -> bool:
        with self._lock:
            return user_id in self._timers


# Global manager instances - thread-safe
_poll_sessions = SessionManager(max_size=10000, default_ttl=settings.QUIZ_MAX_SESSION_AGE)
_active_timers = TimerManager(max_timers=5000)

# Settings dan olinadi (magic numbers emas)
QUESTION_TIME = settings.QUIZ_QUESTION_TIME
SESSION_CLEANUP_INTERVAL = settings.QUIZ_SESSION_CLEANUP_INTERVAL
MAX_SESSION_AGE = settings.QUIZ_MAX_SESSION_AGE


def cleanup_old_sessions():
    """Eski sessionlarni va timerlarni tozalash - memory leak oldini olish"""
    expired_sessions = _poll_sessions.cleanup_expired()
    done_timers = _active_timers.cleanup()

    if expired_sessions or done_timers:
        logger.info(f"Cleanup: {expired_sessions} sessions, {done_timers} timers removed")

    logger.debug(f"Active: {len(_poll_sessions)} sessions, {len(_active_timers)} timers")


def get_memory_stats() -> dict:
    """Xotira statistikasi - monitoring uchun"""
    return {
        "poll_sessions": len(_poll_sessions),
        "active_timers": len(_active_timers)
    }

# Audio service
audio_service = AudioService()


class QuizStates(StatesGroup):
    selecting_language = State()
    selecting_level = State()
    selecting_day = State()
    selecting_count = State()
    in_quiz = State()


# ============================================================
# QUIZ SELECTION FLOW
# ============================================================

@router.callback_query(F.data == "quiz:start")
async def quiz_start(callback: CallbackQuery, state: FSMContext):
    """Start quiz selection - directly show levels (skip language selection)"""
    await state.clear()

    # Cancel any active timer (thread-safe)
    user_id = callback.from_user.id
    _active_timers.cancel(user_id)

    # Get all levels directly (skip language selection)
    levels = await quiz_service.get_levels()

    if not levels:
        await callback.answer("❌ Hozircha darajalar mavjud emas.", show_alert=True)
        return

    await state.set_state(QuizStates.selecting_level)

    try:
        await callback.message.edit_text(
            "📚 <b>Quiz boshlash</b>\n\n"
            "📊 Darajani tanlang:",
            reply_markup=level_keyboard(levels)
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("quiz:lang:"))
async def select_language(callback: CallbackQuery, state: FSMContext):
    """Handle language selection"""
    language_id = int(callback.data.split(":")[-1])
    await state.update_data(language_id=language_id)
    
    levels = await quiz_service.get_levels(language_id)
    
    if not levels:
        await callback.answer("❌ Bu til uchun darajalar topilmadi.", show_alert=True)
        return
    
    await state.set_state(QuizStates.selecting_level)
    
    await callback.message.edit_text(
        "📚 <b>Quiz boshlash</b>\n\n"
        "📊 Darajani tanlang:",
        reply_markup=level_keyboard(levels, language_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("quiz:level:"))
async def select_level(callback: CallbackQuery, state: FSMContext):
    """Handle level selection"""
    level_id = int(callback.data.split(":")[-1])
    await state.update_data(level_id=level_id)

    days = await quiz_service.get_days(level_id)

    if not days:
        await callback.answer("❌ Bu daraja uchun kunlar topilmadi.", show_alert=True)
        return

    await state.set_state(QuizStates.selecting_day)

    await callback.message.edit_text(
        "📚 <b>Quiz boshlash</b>\n\n"
        "📅 Kunni tanlang:",
        reply_markup=day_keyboard(days, level_id=level_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("quiz:day:"))
async def select_day_direct(callback: CallbackQuery, state: FSMContext):
    """Handle day selection - works with or without state (from shop, etc.)"""
    # "quiz:day:all:{level_id}" yoki "quiz:day:{day_id}" formatlarini qo'llab-quvvatlash
    parts = callback.data.split(":")

    if len(parts) == 4 and parts[2] == "all":
        # Barcha kunlar tanlangan
        level_id = int(parts[3])
        await state.update_data(day_id=None, all_days=True, selected_level_id=level_id)
    else:
        # Bitta kun tanlangan
        day_id = int(parts[-1])
        await state.update_data(day_id=day_id, all_days=False)

    await state.set_state(QuizStates.selecting_count)

    await callback.message.edit_text(
        "📚 <b>Quiz boshlash</b>\n\n"
        "🔢 Savollar sonini tanlang:",
        reply_markup=question_count_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("quiz:count:"), QuizStates.selecting_count)
async def select_count_and_start(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Handle count selection and start quiz"""
    count = int(callback.data.split(":")[-1])
    data = await state.get_data()
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    # Get questions from database
    async with get_session() as session:
        question_repo = QuestionRepository(session)
        
        # Agar barcha kunlar tanlangan bo'lsa
        if data.get("all_days"):
            questions = await question_repo.get_random_questions(
                level_id=data.get("selected_level_id"),
                count=count
            )
        else:
            questions = await question_repo.get_random_questions(
                day_id=data.get("day_id"),
                count=count
            )
    
    if not questions:
        await callback.answer("❌ Savollar topilmadi!", show_alert=True)
        return
    
    # Prepare questions data
    questions_data = []
    for q in questions:
        options, correct_idx = q.get_shuffled_options()
        questions_data.append({
            "id": q.id,
            "text": q.question_text,
            "options": options,
            "correct_index": correct_idx,
            "explanation": q.explanation or "Tushuntirish mavjud emas"
        })
    
    # Check premium status
    is_premium = data.get("is_premium", False)
    
    # Save to FSM state
    await state.update_data(
        user_id=user_id,
        chat_id=chat_id,
        questions=questions_data,
        current_index=0,
        correct_count=0,
        wrong_count=0,
        start_time=datetime.utcnow().isoformat(),
        answers=[],
        answered_current=False,
        is_premium=is_premium
    )
    await state.set_state(QuizStates.in_quiz)
    
    # Delete selection message
    await callback.message.delete()
    
    # Send first question
    await send_question(chat_id, user_id, state, bot)
    await callback.answer()


async def send_question(chat_id: int, user_id: int, state: FSMContext, bot: Bot):
    """Send current question as Telegram Quiz Poll"""
    data = await state.get_data()
    questions = data.get("questions", [])
    current_index = data.get("current_index", 0)
    is_premium = data.get("is_premium", False)
    
    if current_index >= len(questions):
        await finish_quiz(chat_id, user_id, state, bot)
        return
    
    question = questions[current_index]
    total = len(questions)
    
    # Mark as not answered yet
    await state.update_data(answered_current=False)
    
    # Send audio if premium and enabled
    if is_premium and settings.AUDIO_ENABLED:
        try:
            audio_path = await audio_service.get_audio(question['text'])
            if audio_path:
                from aiogram.types import FSInputFile
                await bot.send_voice(
                    chat_id=chat_id,
                    voice=FSInputFile(audio_path),
                    caption="🔊 Savolni tinglang"
                )
        except Exception as e:
            logger.debug(f"Audio error (non-critical): {e}")
    
    # Send quiz poll
    poll_message = await bot.send_poll(
        chat_id=chat_id,
        question=f"📝 Savol {current_index + 1}/{total}\n\n{question['text']}",
        options=question["options"],
        type="quiz",
        correct_option_id=question["correct_index"],
        explanation=question["explanation"],
        is_anonymous=False,
        open_period=QUESTION_TIME
    )
    
    # Store poll -> state mapping (thread-safe)
    _poll_sessions.set(poll_message.poll.id, {
        "chat_id": chat_id,
        "user_id": user_id,
        "question_index": current_index,
        "question_id": question["id"],
        "question_text": question["text"],  # Flashcard uchun
        "correct_index": question["correct_index"],
    }, ttl=MAX_SESSION_AGE)
    
    await state.update_data(current_poll_id=poll_message.poll.id)
    
    # Cancel previous timer if exists and start new one (thread-safe)
    _active_timers.cancel(user_id)

    # Start auto-advance timer
    new_timer = asyncio.create_task(
        auto_advance_timer(chat_id, user_id, current_index, state, bot)
    )
    _active_timers.set(user_id, new_timer)


async def auto_advance_timer(chat_id: int, user_id: int, question_index: int, state: FSMContext, bot: Bot):
    """Timer to auto-advance if user doesn't answer"""
    try:
        # Wait for poll to close + small buffer
        await asyncio.sleep(QUESTION_TIME + 2)
        
        # Check if still on same question and not answered
        data = await state.get_data()
        current_index = data.get("current_index", 0)
        answered = data.get("answered_current", False)
        
        if current_index == question_index and not answered:
            # User didn't answer - mark as wrong and advance
            wrong_count = data.get("wrong_count", 0) + 1
            answers = data.get("answers", [])
            questions = data.get("questions", [])
            
            answers.append({
                "question_index": question_index,
                "selected": -1,  # No answer
                "correct": questions[question_index]["correct_index"] if question_index < len(questions) else 0,
                "is_correct": False,
                "timeout": True
            })
            
            new_index = current_index + 1
            
            await state.update_data(
                current_index=new_index,
                wrong_count=wrong_count,
                answers=answers,
                answered_current=True
            )
            
            # Check if this was the last question
            if new_index >= len(questions):
                # Oxirgi savol edi - quizni tugatish
                # MUHIM: Yangilangan data ni olish kerak!
                updated_data = await state.get_data()
                await finish_quiz(chat_id, user_id, state, bot, timer_data=updated_data)
            else:
                # Keyingi savolga darhol o'tish (xabar yo'q!)
                await send_question(chat_id, user_id, state, bot)
            
    except asyncio.CancelledError:
        # Timer was cancelled (user answered)
        pass
    except Exception as e:
        import traceback
        logger.error(f"Timer error: {e}\n{traceback.format_exc()}")


async def _handle_duel_poll_answer(poll_id: str, user_id: int, poll_answer: PollAnswer, bot: Bot) -> bool:
    """
    Duel poll javoblarini qayta ishlash.
    Circular import ni oldini olish uchun alohida funksiya.

    Returns:
        bool: True agar duel poll topilgan va qayta ishlangan bo'lsa
    """
    try:
        # Lazy import - circular import ni oldini olish
        from src.handlers.duel import _active_duels, start_duel_round, finish_duel
    except ImportError as e:
        logger.debug(f"Duel module import error: {e}")
        return False

    for duel_id, duel in list(_active_duels.items()):
        polls = duel.get("polls", {})
        if poll_id not in polls:
            continue

        duel_poll_data = polls[poll_id]
        if duel_poll_data["player_id"] != user_id:
            continue

        selected_index = poll_answer.option_ids[0] if poll_answer.option_ids else -1
        is_correct = selected_index == duel_poll_data["correct_index"]

        if is_correct:
            elapsed = (datetime.utcnow() - duel_poll_data["sent_at"]).total_seconds()
            speed_bonus = max(0, int((10 - elapsed) / 2))
            score = 10 + speed_bonus
        else:
            score = 0

        for player_key in ["player1", "player2"]:
            if duel[player_key]["id"] == user_id:
                duel[player_key]["score"] += score
                duel[player_key]["answers"].append({
                    "question_index": duel_poll_data["question_index"],
                    "is_correct": is_correct,
                    "score": score
                })
                break

        # Ikkalasi ham javob berdimi tekshir
        current_q = duel_poll_data["question_index"]
        p1_answered = any(a["question_index"] == current_q for a in duel["player1"]["answers"])
        p2_answered = any(a["question_index"] == current_q for a in duel["player2"]["answers"])

        if p1_answered and p2_answered:
            # Ikkalasi ham javob berdi - keyingi savolga o't
            next_index = current_q + 1
            if next_index < len(duel["questions"]):
                duel["current_index"] = next_index
                asyncio.create_task(start_duel_round(duel_id, bot))
            else:
                asyncio.create_task(finish_duel(duel_id, bot))

        logger.info(f"Duel poll answer: user={user_id}, correct={is_correct}, score={score}")
        return True

    return False


@router.poll_answer()
async def handle_poll_answer(poll_answer: PollAnswer, bot: Bot, state: FSMContext):
    """Handle quiz poll answer - auto advance to next question"""
    poll_id = poll_answer.poll_id
    user_id = poll_answer.user.id

    # Thread-safe session olish
    poll_data = _poll_sessions.get(poll_id)

    # Agar personal quiz poll bo'lmasa, duel poll tekshir
    if not poll_data:
        handled = await _handle_duel_poll_answer(poll_id, user_id, poll_answer, bot)
        if handled:
            return
        return

    
    
    # Verify user
    if poll_data["user_id"] != user_id:
        return
    
    chat_id = poll_data["chat_id"]
    correct_index = poll_data["correct_index"]
    question_index = poll_data["question_index"]
    
    # Cancel the auto-advance timer (thread-safe)
    _active_timers.cancel(user_id)
    
    # Check if already processed
    data = await state.get_data()
    if data.get("answered_current", False):
        return
    
    selected_index = poll_answer.option_ids[0] if poll_answer.option_ids else -1
    is_correct = selected_index == correct_index
    
    correct_count = data.get("correct_count", 0)
    wrong_count = data.get("wrong_count", 0)
    answers = data.get("answers", [])
    current_index = data.get("current_index", 0)
    
    if is_correct:
        correct_count += 1
    else:
        wrong_count += 1
    
    # XP berish
    try:
        await XPService.reward_quiz_answer(user_id, is_correct)
    except Exception as e:
        logger.error(f"Quiz XP error: {e}")
    
    answers.append({
        "question_index": current_index,
        "selected": selected_index,
        "correct": correct_index,
        "is_correct": is_correct
    })

    current_index += 1

    # SM-2: Record answer for spaced repetition
    question_id = poll_data.get("question_id")
    if question_id:
        try:
            async with get_session() as session:
                sr_repo = SpacedRepetitionRepository(session)
                await sr_repo.record_answer(
                    user_id=user_id,
                    question_id=question_id,
                    is_correct=is_correct
                )
        except Exception as e:
            logger.debug(f"SM-2 record error: {e}")

    # Flashcard: Update UserFlashcard if word exists
    question_text = poll_data.get("question_text")
    if question_text:
        try:
            async with get_session() as session:
                await update_flashcard_from_quiz(
                    session=session,
                    user_id=user_id,
                    question_text=question_text,
                    is_correct=is_correct
                )
        except Exception as e:
            logger.debug(f"Flashcard update error: {e}")

    logger.info(f"handle_poll_answer: user={user_id}, correct={is_correct}, index={current_index}")
    
    await state.update_data(
        current_index=current_index,
        correct_count=correct_count,
        wrong_count=wrong_count,
        answers=answers,
        answered_current=True
    )
    
    # Clean up poll session (thread-safe)
    _poll_sessions.delete(poll_id)
    
    # Small delay for user to see result
    await asyncio.sleep(1.5)
    
    # Send next question
    await send_question(chat_id, user_id, state, bot)


async def save_quiz_to_db(user_id, correct, wrong, total, percentage, time_taken, data):
    """Background task for saving quiz results"""
    try:
        async with get_session() as session:
            progress_repo = ProgressRepository(session)
            streak_repo = StreakRepository(session)
            user_repo = UserRepository(session)
            
            await progress_repo.save_quiz_result(
                user_id=user_id,
                correct=correct,
                wrong=wrong,
                total=total,
                score=percentage,
                avg_time=time_taken / total if total > 0 else 0,
                total_time=time_taken,
                language_id=data.get("language_id"),
                level_id=data.get("level_id"),
                day_id=data.get("day_id"),
                quiz_type="personal"
            )
            await user_repo.update_stats(user_id, correct=correct, total=total)
            await streak_repo.update_streak(user_id)
            logger.info(f"save_quiz_to_db: saved for user={user_id}")

            # Yutuqlarni tekshirish - jami quizlar sonini olish
            from src.services import achievement_service
            user = await user_repo.get_by_user_id(user_id)
            total_quizzes = user.total_quizzes if user else 1
            is_perfect = (percentage == 100)
            await achievement_service.on_quiz_completed(user_id, total_quizzes, is_perfect)
    except Exception as e:
        logger.error(f"save_quiz_to_db error: {e}")


async def finish_quiz(chat_id: int, user_id: int, state: FSMContext, bot: Bot, timer_data: dict = None):
    """Finish quiz and show results"""
    logger.info(f"finish_quiz called: user={user_id}, chat={chat_id}")

    # Cancel active timer (thread-safe)
    _active_timers.cancel(user_id)
    
    # Timer dan data kelgan bo'lsa ishlatamiz
    if timer_data:
        data = timer_data
        logger.info("finish_quiz: using timer_data")
    else:
        data = await state.get_data()
        logger.info("finish_quiz: got data from state")
    
    correct = data.get("correct_count", 0)
    wrong = data.get("wrong_count", 0)
    total = correct + wrong
    
    if total == 0:
        total = len(data.get("questions", []))
        wrong = total
    
    percentage = (correct / total * 100) if total > 0 else 0
    
    if percentage >= 90:
        rating = "🌟 A'lo!"
        emoji = "🎉"
    elif percentage >= 70:
        rating = "👍 Yaxshi"
        emoji = "😊"
    elif percentage >= 50:
        rating = "📚 O'rtacha"
        emoji = "🤔"
    else:
        rating = "💪 Mashq qiling"
        emoji = "😅"
    
    start_time = datetime.fromisoformat(data.get("start_time", datetime.utcnow().isoformat()))
    time_taken = (datetime.utcnow() - start_time).total_seconds()
    
    streak_text = ""
    tournament_text = ""
    # Database saqlash - background task
    asyncio.create_task(save_quiz_to_db(user_id, correct, wrong, total, percentage, time_taken, data))
    
    # Count timeouts
    answers = data.get("answers", [])
    timeouts = sum(1 for a in answers if a.get("timeout", False))
    timeout_text = f"\n⏰ Vaqt tugagan: {timeouts}" if timeouts > 0 else ""
    
    text = f"""
{emoji} <b>Quiz tugadi!</b>

📊 <b>Natija: {rating}</b>

✅ To'g'ri: {correct}/{total}
❌ Xato: {wrong}/{total}{timeout_text}
📈 Ball: {percentage:.1f}%
⏱ Vaqt: {time_taken:.1f} soniya
{streak_text}{tournament_text}
{"🏆 Mukammal natija!" if correct == total else ""}
"""
    logger.info(f"finish_quiz: sending result message to chat_id={chat_id}")
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=quiz_result_keyboard(show_review=wrong > 0)
        )
        logger.info("finish_quiz: result message sent successfully")
    except Exception as send_err:
        logger.error(f"finish_quiz: send_message error: {send_err}")
        import traceback
        logger.error(traceback.format_exc())
    
    # Keep only review data, clear the rest
    questions = data.get("questions", [])
    answers = data.get("answers", [])
    await state.clear()
    
    # Save review data back
    if wrong > 0:
        await state.update_data(
            questions=questions,
            answers=answers,
            review_available=True
        )

@router.callback_query(F.data == "quiz:restart")
async def restart_quiz(callback: CallbackQuery, state: FSMContext):
    """Restart quiz"""
    await state.clear()
    await quiz_start(callback, state)


@router.callback_query(F.data == "quiz:cancel")
async def cancel_quiz(callback: CallbackQuery, state: FSMContext):
    """Cancel quiz"""
    user_id = callback.from_user.id

    # Cancel timer (thread-safe)
    _active_timers.cancel(user_id)
    
    await state.clear()
    await callback.message.edit_text(
        "❌ Quiz bekor qilindi.\n\n"
        "/start - Qaytadan boshlash"
    )
    await callback.answer()


@router.callback_query(F.data == "quiz:review")
async def review_mistakes(callback: CallbackQuery, state: FSMContext):
    """Review wrong answers"""
    data = await state.get_data()
    answers = data.get("answers", [])
    questions = data.get("questions", [])
    
    if not answers or not questions:
        await callback.answer("❌ Ko'rish uchun ma'lumot yo'q!", show_alert=True)
        return
    
    # Find wrong answers
    wrong_answers = [a for a in answers if not a.get("is_correct", True)]
    
    if not wrong_answers:
        await callback.answer("✅ Barcha javoblar to'g'ri edi!", show_alert=True)
        return
    
    # Build review text
    text = "📝 <b>Xatolarni ko'rish</b>\n\n"
    
    for i, wrong in enumerate(wrong_answers[:10], 1):  # Limit to 10
        q_index = wrong.get("question_index", 0)
        if q_index < len(questions):
            q = questions[q_index]
            correct_idx = wrong.get("correct", 0)
            selected_idx = wrong.get("selected", -1)
            
            # Get correct answer text
            correct_answer = q["options"][correct_idx] if correct_idx < len(q["options"]) else "?"
            
            # Get user's answer text
            if selected_idx == -1 or wrong.get("timeout"):
                user_answer = "⏰ Vaqt tugadi"
            elif selected_idx < len(q["options"]):
                user_answer = q["options"][selected_idx]
            else:
                user_answer = "?"
            
            text += f"<b>{i}. {q['text']}</b>\n"
            text += f"❌ Sizning javob: {user_answer}\n"
            text += f"✅ To'g'ri javob: {correct_answer}\n\n"
    
    if len(wrong_answers) > 10:
        text += f"<i>... va yana {len(wrong_answers) - 10} ta xato</i>\n"
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Qaytadan o'ynash", callback_data="quiz:start"),
        InlineKeyboardButton(text="🏠 Menyu", callback_data="menu:main")
    )
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


# ============================================================
# QUIZ SETTINGS HANDLERS
# ============================================================

@router.callback_query(F.data == "quiz:settings")
async def show_quiz_settings(callback: CallbackQuery, db_user: User):
    """Quiz sozlamalari"""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    from datetime import date
    
    # Kunlik limitni tekshirish
    today = utc_today()
    if db_user.quiz_last_date != today:
        db_user.quizzes_today = 0
    
    difficulty_names = {
        "easy": "🟢 Oson",
        "medium": "🟡 O'rta", 
        "hard": "🔴 Qiyin",
        "mixed": "🔀 Aralash"
    }
    
    text = f"""
⚙️ <b>Quiz sozlamalari</b>

<b>Joriy sozlamalar:</b>
- ⏱ Vaqt limiti: <b>{db_user.quiz_time_limit}</b> soniya
- 📊 Kunlik limit: <b>{db_user.quiz_daily_limit if db_user.quiz_daily_limit > 0 else "Cheksiz"}</b>
- 🎯 Qiyinlik: <b>{difficulty_names.get(db_user.quiz_difficulty, "Aralash")}</b>

<b>Bugun:</b> {db_user.quizzes_today}/{db_user.quiz_daily_limit if db_user.quiz_daily_limit > 0 else "∞"} quiz o'ynaldi
"""
    
    builder = InlineKeyboardBuilder()
    
    # Vaqt limiti
    builder.row(
        InlineKeyboardButton(text="⏱ Vaqt (soniya):", callback_data="noop")
    )
    builder.row(
        InlineKeyboardButton(text="10" + (" ✓" if db_user.quiz_time_limit == 10 else ""), callback_data="quiz:set_time:10"),
        InlineKeyboardButton(text="15" + (" ✓" if db_user.quiz_time_limit == 15 else ""), callback_data="quiz:set_time:15"),
        InlineKeyboardButton(text="20" + (" ✓" if db_user.quiz_time_limit == 20 else ""), callback_data="quiz:set_time:20"),
        InlineKeyboardButton(text="30" + (" ✓" if db_user.quiz_time_limit == 30 else ""), callback_data="quiz:set_time:30"),
    )
    
    # Kunlik limit
    builder.row(
        InlineKeyboardButton(text="📊 Kunlik limit:", callback_data="noop")
    )
    builder.row(
        InlineKeyboardButton(text="20" + (" ✓" if db_user.quiz_daily_limit == 20 else ""), callback_data="quiz:set_daily:20"),
        InlineKeyboardButton(text="50" + (" ✓" if db_user.quiz_daily_limit == 50 else ""), callback_data="quiz:set_daily:50"),
        InlineKeyboardButton(text="100" + (" ✓" if db_user.quiz_daily_limit == 100 else ""), callback_data="quiz:set_daily:100"),
        InlineKeyboardButton(text="∞" + (" ✓" if db_user.quiz_daily_limit == 0 else ""), callback_data="quiz:set_daily:0"),
    )
    
    # Qiyinlik
    builder.row(
        InlineKeyboardButton(text="🎯 Qiyinlik:", callback_data="noop")
    )
    builder.row(
        InlineKeyboardButton(text="🟢" + (" ✓" if db_user.quiz_difficulty == "easy" else ""), callback_data="quiz:set_diff:easy"),
        InlineKeyboardButton(text="🟡" + (" ✓" if db_user.quiz_difficulty == "medium" else ""), callback_data="quiz:set_diff:medium"),
        InlineKeyboardButton(text="🔴" + (" ✓" if db_user.quiz_difficulty == "hard" else ""), callback_data="quiz:set_diff:hard"),
        InlineKeyboardButton(text="🔀" + (" ✓" if db_user.quiz_difficulty == "mixed" else ""), callback_data="quiz:set_diff:mixed"),
    )
    
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="menu:main")
    )
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("quiz:set_time:"))
async def set_quiz_time(callback: CallbackQuery, db_user: User):
    """Vaqt limitini o'zgartirish"""
    time_limit = int(callback.data.split(":")[2])
    
    async with get_session() as session:
        from sqlalchemy import update
        await session.execute(
            update(User).where(User.user_id == db_user.user_id).values(quiz_time_limit=time_limit)
        )
        await session.flush()
    
    db_user.quiz_time_limit = time_limit
    await callback.answer(f"✅ Vaqt limiti: {time_limit} soniya", show_alert=True)
    await show_quiz_settings(callback, db_user)


@router.callback_query(F.data.startswith("quiz:set_daily:"))
async def set_quiz_daily(callback: CallbackQuery, db_user: User):
    """Kunlik limitni o'zgartirish"""
    daily_limit = int(callback.data.split(":")[2])
    
    async with get_session() as session:
        from sqlalchemy import update
        await session.execute(
            update(User).where(User.user_id == db_user.user_id).values(quiz_daily_limit=daily_limit)
        )
        await session.flush()
    
    db_user.quiz_daily_limit = daily_limit
    limit_text = str(daily_limit) if daily_limit > 0 else "Cheksiz"
    await callback.answer(f"✅ Kunlik limit: {limit_text}", show_alert=True)
    await show_quiz_settings(callback, db_user)


@router.callback_query(F.data.startswith("quiz:set_diff:"))
async def set_quiz_difficulty(callback: CallbackQuery, db_user: User):
    """Qiyinlik darajasini o'zgartirish"""
    difficulty = callback.data.split(":")[2]
    
    async with get_session() as session:
        from sqlalchemy import update
        await session.execute(
            update(User).where(User.user_id == db_user.user_id).values(quiz_difficulty=difficulty)
        )
        await session.flush()
    
    db_user.quiz_difficulty = difficulty
    diff_names = {"easy": "Oson", "medium": "O'rta", "hard": "Qiyin", "mixed": "Aralash"}
    await callback.answer(f"✅ Qiyinlik: {diff_names.get(difficulty, difficulty)}", show_alert=True)
    await show_quiz_settings(callback, db_user)
