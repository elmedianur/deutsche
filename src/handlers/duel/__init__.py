"""
Duel Handler - Foydalanuvchilar o'rtasida bellashuv
"""
import random
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, PollAnswer
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.database import get_session
from src.repositories import QuestionRepository, UserRepository, ProgressRepository
from src.database.models import User
from src.core.logging import get_logger

logger = get_logger(__name__)
router = Router(name="duel")

# Active duels storage
_active_duels: Dict[str, Dict[str, Any]] = {}
_waiting_players: Dict[int, Dict[str, Any]] = {}  # user_id -> duel info

# Duel timeout settings
DUEL_MAX_AGE = 600  # 10 daqiqa maksimal duel vaqti
WAITING_MAX_AGE = 120  # 2 daqiqa kutish vaqti


def cleanup_old_duels():
    """Eski duellar va waiting players tozalash - memory leak oldini olish"""
    from datetime import datetime
    now = datetime.utcnow()

    # 1. Eski waiting players tozalash
    old_waiting = [
        uid for uid, data in list(_waiting_players.items())
        if (now - data.get("started_at", now)).total_seconds() > WAITING_MAX_AGE
    ]
    for uid in old_waiting:
        try:
            del _waiting_players[uid]
        except KeyError:
            pass

    # 2. Eski duellar tozalash (timeout bo'lgan)
    old_duels = [
        did for did, data in list(_active_duels.items())
        if (now - data.get("started_at", now)).total_seconds() > DUEL_MAX_AGE
    ]
    for did in old_duels:
        try:
            del _active_duels[did]
        except KeyError:
            pass

    if old_waiting or old_duels:
        logger.info(f"Duel cleanup: {len(old_waiting)} waiting, {len(old_duels)} duels removed")

    logger.debug(f"Active: {len(_active_duels)} duels, {len(_waiting_players)} waiting")


def get_duel_stats() -> dict:
    """Duel statistikasi - monitoring uchun"""
    return {
        "active_duels": len(_active_duels),
        "waiting_players": len(_waiting_players)
    }


class DuelStates(StatesGroup):
    """Duel FSM states"""
    waiting_opponent = State()
    in_duel = State()


def duel_menu_keyboard() -> InlineKeyboardMarkup:
    """Duel main menu keyboard"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎯 Tasodifiy raqib", callback_data="duel:random")
    )
    builder.row(
        InlineKeyboardButton(text="👥 Do'stni taklif qilish", callback_data="duel:invite")
    )
    builder.row(
        InlineKeyboardButton(text="📊 Duel statistikasi", callback_data="duel:stats"),
        InlineKeyboardButton(text="🏆 Top raqiblar", callback_data="duel:top")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="menu:main")
    )
    return builder.as_markup()


def waiting_keyboard() -> InlineKeyboardMarkup:
    """Waiting for opponent keyboard"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data="duel:cancel_wait")
    )
    return builder.as_markup()


def duel_invite_keyboard(duel_id: str) -> InlineKeyboardMarkup:
    """Duel invitation keyboard"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"duel:accept:{duel_id}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"duel:decline:{duel_id}")
    )
    return builder.as_markup()


def duel_result_keyboard() -> InlineKeyboardMarkup:
    """Duel result keyboard"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Yana o'ynash", callback_data="duel:random"),
        InlineKeyboardButton(text="🏠 Menyu", callback_data="menu:main")
    )
    return builder.as_markup()


# ============================================================
# HANDLERS
# ============================================================

@router.callback_query(F.data == "duel:menu")
async def duel_menu(callback: CallbackQuery, state: FSMContext):
    """Duel main menu"""
    await state.clear()
    
    user_id = callback.from_user.id
    
    # Check if user has active duel
    if user_id in _waiting_players:
        del _waiting_players[user_id]
    
    text = """
⚔️ <b>Duel</b>

Boshqa o'yinchilar bilan bellashing!

<b>Qoidalar:</b>
• 5 ta savol, har biri 10 soniya
• To'g'ri javob = 10 ball
• Tez javob = bonus ball (+5)
• G'olib = eng ko'p ball

🏆 G'oliblar reytingda ko'tariladi!
"""
    
    await callback.message.edit_text(text, reply_markup=duel_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "duel:random")
async def find_random_opponent(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Find random opponent"""
    user_id = callback.from_user.id
    await callback.answer()
    username = callback.from_user.username or callback.from_user.first_name
    
    # Check if someone is waiting
    available_opponents = [
        uid for uid, data in _waiting_players.items()
        if uid != user_id and (datetime.utcnow() - data['started_at']).seconds < 120
    ]
    
    if available_opponents:
        # Match with waiting player
        opponent_id = available_opponents[0]
        opponent_data = _waiting_players.pop(opponent_id)
        
        # Create duel
        duel_id = f"{user_id}_{opponent_id}_{int(datetime.utcnow().timestamp())}"

        # Get questions based on both players' error history
        async with get_session() as session:
            question_repo = QuestionRepository(session)
            # Xatolik tarixi asosida savollarni olish
            questions = await question_repo.get_duel_questions(
                user1_id=user_id,
                user2_id=opponent_id,
                count=5
            )

        if not questions:
            await callback.answer("❌ Savollar topilmadi!", show_alert=True)
            return
        
        # Prepare questions
        questions_data = []
        for q in questions:
            options, correct_idx = q.get_shuffled_options()
            questions_data.append({
                "id": q.id,
                "text": q.question_text,
                "options": options,
                "correct_index": correct_idx
            })
        
        _active_duels[duel_id] = {
            "player1": {"id": opponent_id, "name": opponent_data['username'], "score": 0, "answers": []},
            "player2": {"id": user_id, "name": username, "score": 0, "answers": []},
            "questions": questions_data,
            "current_index": 0,
            "started_at": datetime.utcnow(),
            "chat_ids": {opponent_id: opponent_data['chat_id'], user_id: callback.message.chat.id}
        }
        
        # Notify both players
        await callback.message.edit_text(
            f"⚔️ <b>Duel topildi!</b>\n\n"
            f"👤 Siz vs 👤 {opponent_data['username']}\n\n"
            f"🎮 Duel 3 soniyada boshlanadi...",
        )
        
        await bot.send_message(
            opponent_data['chat_id'],
            f"⚔️ <b>Raqib topildi!</b>\n\n"
            f"👤 Siz vs 👤 {username}\n\n"
            f"🎮 Duel 3 soniyada boshlanadi...",
        )
        
        # Start duel after delay
        await asyncio.sleep(3)
        await start_duel_round(duel_id, bot, state)
        
    else:
        # Add to waiting list
        _waiting_players[user_id] = {
            "username": username,
            "chat_id": callback.message.chat.id,
            "started_at": datetime.utcnow()
        }
        
        await state.set_state(DuelStates.waiting_opponent)
        
        await callback.message.edit_text(
            "⏳ <b>Raqib qidirilmoqda...</b>\n\n"
            "Boshqa o'yinchi kutilmoqda.\n"
            "Bu 2 daqiqagacha davom etishi mumkin.\n\n"
            "💡 Do'stingizni taklif qilishingiz ham mumkin!",
            reply_markup=waiting_keyboard()
        )
    try:
        await callback.answer()
    except Exception:
        pass


async def start_duel_round(duel_id: str, bot: Bot, state: FSMContext = None):
    """Start a duel round"""
    if duel_id not in _active_duels:
        return
    
    duel = _active_duels[duel_id]
    questions = duel["questions"]
    current_index = duel["current_index"]
    
    if current_index >= len(questions):
        # Duel finished
        await finish_duel(duel_id, bot)
        return
    
    question = questions[current_index]
    player1 = duel["player1"]
    player2 = duel["player2"]
    
    # Initialize polls dict if not exists
    if "polls" not in duel:
        duel["polls"] = {}
    
    # Send poll to both players
    for player in [player1, player2]:
        chat_id = duel["chat_ids"].get(player["id"])
        if not chat_id:
            continue
        
        try:
            poll_msg = await bot.send_poll(
                chat_id=chat_id,
                question=f"⚔️ Savol {current_index + 1}/5: {question['text']}",
                options=question["options"],
                type="quiz",
                correct_option_id=question["correct_index"],
                
                is_anonymous=False,
                open_period=10
            )
            
            # Store poll info
            duel["polls"][poll_msg.poll.id] = {
                "player_id": player["id"],
                "question_index": current_index,
                "correct_index": question["correct_index"],
                "sent_at": datetime.utcnow()
            }
        except Exception as e:
            logger.error(f"Error sending duel poll: {e}")
    
    # Schedule next question after 12 seconds
    await asyncio.sleep(12)
    
    # Move to next question
    duel["current_index"] = current_index + 1
    await start_duel_round(duel_id, bot, state)


async def finish_duel(duel_id: str, bot: Bot):
    """Finish duel and show results"""
    if duel_id not in _active_duels:
        return
    
    duel = _active_duels.pop(duel_id)
    player1 = duel["player1"]
    player2 = duel["player2"]
    
    # Determine winner
    if player1["score"] > player2["score"]:
        winner = player1
        loser = player2
        result_emoji = "🏆"
    elif player2["score"] > player1["score"]:
        winner = player2
        loser = player1
        result_emoji = "🏆"
    else:
        winner = None
        result_emoji = "🤝"
    # Database'ga natijalarni saqlash
    try:
        async with get_session() as session:
            progress_repo = ProgressRepository(session)

            # DuelStats repository
            from src.repositories.duel_repo import DuelStatsRepository
            from src.database.models import SpacedRepetition
            from sqlalchemy import select, and_
            from datetime import date, timedelta

            duel_stats_repo = DuelStatsRepository(session)

            for p in [player1, player2]:
                correct = sum(1 for a in p.get("answers", []) if a.get("is_correct"))
                total = len(duel["questions"])
                wrong = total - correct
                score = (correct / total * 100) if total > 0 else 0

                await progress_repo.save_quiz_result(
                    user_id=p["id"],
                    correct=correct,
                    wrong=wrong,
                    total=total,
                    score=score,
                    quiz_type="duel"
                )

                # SpacedRepetition ma'lumotlarini saqlash (xatolik tarixi uchun)
                for answer in p.get("answers", []):
                    q_index = answer.get("question_index", 0)
                    if q_index < len(duel["questions"]):
                        question_id = duel["questions"][q_index]["id"]
                        is_correct = answer.get("is_correct", False)

                        # Mavjud SpacedRepetition ni topish yoki yangi yaratish
                        result = await session.execute(
                            select(SpacedRepetition).where(
                                and_(
                                    SpacedRepetition.user_id == p["id"],
                                    SpacedRepetition.question_id == question_id
                                )
                            )
                        )
                        sr = result.scalar_one_or_none()

                        if sr:
                            # Mavjud - yangilash
                            sr.total_reviews += 1
                            if is_correct:
                                sr.correct_reviews += 1
                                # SM-2: to'g'ri javob
                                if sr.repetitions == 0:
                                    sr.interval = 1
                                elif sr.repetitions == 1:
                                    sr.interval = 6
                                else:
                                    sr.interval = int(sr.interval * sr.easiness_factor)
                                sr.repetitions += 1
                                sr.easiness_factor = min(2.5, sr.easiness_factor + 0.1)
                            else:
                                # SM-2: xato javob
                                sr.repetitions = 0
                                sr.interval = 1
                                sr.easiness_factor = max(1.3, sr.easiness_factor - 0.2)

                            sr.last_review_date = date.today()
                            sr.next_review_date = date.today() + timedelta(days=sr.interval)
                        else:
                            # Yangi yaratish
                            sr = SpacedRepetition(
                                user_id=p["id"],
                                question_id=question_id,
                                total_reviews=1,
                                correct_reviews=1 if is_correct else 0,
                                easiness_factor=2.5 if is_correct else 2.3,
                                repetitions=1 if is_correct else 0,
                                interval=1,
                                last_review_date=date.today(),
                                next_review_date=date.today() + timedelta(days=1)
                            )
                            session.add(sr)

            await session.flush()

            # Duel statistikasini saqlash
            if winner:
                await duel_stats_repo.record_duel_result(winner["id"], won=True)
                await duel_stats_repo.record_duel_result(loser["id"], won=False)
            else:  # Durrang
                await duel_stats_repo.record_duel_result(player1["id"], won=False, is_draw=True)
                await duel_stats_repo.record_duel_result(player2["id"], won=False, is_draw=True)

            await session.commit()
            logger.info(f"Duel results and stats saved: {player1['id']} vs {player2['id']}")
    except Exception as e:
        logger.error(f"Error saving duel results: {e}")

    for player in [player1, player2]:
        chat_id = duel["chat_ids"].get(player["id"])
        if not chat_id:
            continue
        
        if winner is None:
            result_text = "🤝 <b>Durrang!</b>"
            player_result = "Ikkala o'yinchi teng ball to'pladi"
        elif player["id"] == winner["id"]:
            result_text = "🎉🏆🎊 <b>Tabriklaymiz! Siz g'olib bo'ldingiz!</b>"
            player_result = f"Tabriklaymiz! 👏 Siz {loser['name']}ni yengdingiz"
        
        else:
            result_text = "😔 <b>Afsuski, yutqazdingiz</b>"
            player_result = f"Hechqisi yo'q! 💪 Keyingi safar albatta yutasiz"
        
        # To'g'ri javoblar sonini hisoblash
        p1_correct = sum(1 for a in player1.get("answers", []) if a.get("is_correct"))
        p2_correct = sum(1 for a in player2.get("answers", []) if a.get("is_correct"))
        total_q = len(duel["questions"])
        
        text = f"""
⚔️ <b>Duel tugadi!</b>

{result_text}

📊 <b>Natijalar:</b>
👤 {player1['name']}: {p1_correct}/{total_q} ✅ ({player1['score']} ball)
👤 {player2['name']}: {p2_correct}/{total_q} ✅ ({player2['score']} ball)

{player_result}
"""
        try:
            await bot.send_message(
                chat_id,
                text,
                reply_markup=duel_result_keyboard()
            )
        except Exception as e:
            logger.error(f"Error sending duel result: {e}")


@router.poll_answer()
async def handle_duel_poll_answer(poll_answer: PollAnswer, bot: Bot):
    """Handle duel poll answers"""
    poll_id = poll_answer.poll_id
    user_id = poll_answer.user.id
    logger.info(f"Poll answer received: poll_id={poll_id}, user_id={user_id}")
    
    # Find the duel this poll belongs to
    for duel_id, duel in _active_duels.items():
        polls = duel.get("polls", {})
        if poll_id in polls:
            poll_data = polls[poll_id]
            
            if poll_data["player_id"] != user_id:
                continue
            
            selected_index = poll_answer.option_ids[0] if poll_answer.option_ids else -1
            is_correct = selected_index == poll_data["correct_index"]
            
            # Calculate score
            if is_correct:
                # Base score + speed bonus
                elapsed = (datetime.utcnow() - poll_data["sent_at"]).total_seconds()
                speed_bonus = max(0, int((10 - elapsed) / 2))  # Up to 5 bonus points
                score = 10 + speed_bonus
            else:
                score = 0
            
            # Update player score
            for player_key in ["player1", "player2"]:
                if duel[player_key]["id"] == user_id:
                    duel[player_key]["score"] += score
                    duel[player_key]["answers"].append({
                        "question_index": poll_data["question_index"],
                        "is_correct": is_correct,
                        "score": score
                    })
                    break

            # Ikkalasi ham javob berdimi tekshir
            current_q = poll_data["question_index"]
            p1_answered = len([a for a in duel["player1"]["answers"] if a["question_index"] == current_q]) > 0
            p2_answered = len([a for a in duel["player2"]["answers"] if a["question_index"] == current_q]) > 0

            if p1_answered and p2_answered:
                # Ikkalasi ham javob berdi - keyingi savolga o't
                next_index = current_q + 1
                if next_index < len(duel["questions"]):
                    duel["current_index"] = next_index
                    # Keyingi savolni yuborish
                    asyncio.create_task(start_duel_round(duel_id, bot))
                else:
                    # Duel tugadi
                    asyncio.create_task(finish_duel(duel_id, bot))

            break


@router.callback_query(F.data == "duel:cancel_wait")
async def cancel_waiting(callback: CallbackQuery, state: FSMContext):
    """Cancel waiting for opponent"""
    user_id = callback.from_user.id
    
    if user_id in _waiting_players:
        del _waiting_players[user_id]
    
    await state.clear()
    
    await callback.message.edit_text(
        "❌ Qidiruv bekor qilindi.",
        reply_markup=duel_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "duel:invite")
async def invite_friend(callback: CallbackQuery):
    """Invite friend to duel"""
    bot_username = (await callback.bot.get_me()).username
    invite_link = f"https://t.me/{bot_username}?start=duel_{callback.from_user.id}"
    
    text = f"""
👥 <b>Do'stni taklif qilish</b>

Quyidagi havolani do'stingizga yuboring:

<code>{invite_link}</code>

Do'stingiz havolani bosganda, duel avtomatik boshlanadi!
"""
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📤 Ulashish", switch_inline_query=f"Menga duel qilamizmi? {invite_link}")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="duel:menu")
    )
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "duel:stats")
async def duel_stats(callback: CallbackQuery, db_user: User):
    """Show duel statistics"""
    try:
        async with get_session() as session:
            from src.repositories.duel_repo import DuelStatsRepository
            stats_repo = DuelStatsRepository(session)
            stats = await stats_repo.get_or_create(db_user.user_id)
            
            win_rate = (stats.wins / stats.total_duels * 100) if stats.total_duels > 0 else 0
            
            text = f"""
📊 <b>Duel statistikasi</b>

🎮 Jami duellar: {stats.total_duels}
🏆 G'olibliklar: {stats.wins}
😔 Mag'lubiyatlar: {stats.losses}
🤝 Duranglar: {stats.draws}

📈 G'oliblik foizi: {win_rate:.1f}%
⭐ Reyting: {stats.rating}

🔥 Eng uzun g'oliblik seriyasi: {stats.longest_win_streak}
🔥 Joriy seria: {stats.current_win_streak}
"""
    except Exception as e:
        logger.error(f"Duel stats error: {e}")
        text = """
📊 <b>Duel statistikasi</b>

🎮 Jami duellar: 0
🏆 G'olibliklar: 0
😔 Mag'lubiyatlar: 0
🤝 Duranglar: 0

📈 G'oliblik foizi: 0%

<i>Duel o'ynab statistikani to'plang!</i>
"""
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="duel:menu")
    )
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "duel:top")
async def duel_top(callback: CallbackQuery):
    """Show top duel players"""
    try:
        async with get_session() as session:
            from src.repositories.duel_repo import DuelStatsRepository
            stats_repo = DuelStatsRepository(session)
            top_players = await stats_repo.get_top_players(limit=10)
            
            if top_players:
                medals = ["🥇", "🥈", "🥉"]
                text = "🏆 <b>Top raqiblar</b>\n\n"
                for i, player in enumerate(top_players):
                    medal = medals[i] if i < 3 else f"{i+1}."
                    win_rate = (player.wins / player.total_duels * 100) if player.total_duels > 0 else 0
                    text += f"{medal} ID:{player.user_id} - ⭐{player.rating} ({win_rate:.0f}%)\n"
            else:
                text = """🏆 <b>Top raqiblar</b>\n\n<i>Hali ma'lumot yo'q.\nDuel o'ynang va reytingda ko'taring!</i>"""
    except Exception as e:
        logger.error(f"Duel top error: {e}")
        text = """🏆 <b>Top raqiblar</b>\n\n<i>Ma'lumotlarni yuklashda xatolik</i>"""

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="duel:menu")
    )

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("duel:accept:"))
async def accept_duel(callback: CallbackQuery, state: FSMContext, db_user: User):
    """Accept duel invitation"""
    duel_id = callback.data.split(":")[-1]

    # Check if duel exists
    if duel_id not in _active_duels:
        await callback.answer("❌ Bu duel allaqachon tugagan yoki bekor qilingan!", show_alert=True)
        return

    duel = _active_duels[duel_id]
    challenger_id = duel.get("challenger_id")
    opponent_id = callback.from_user.id

    # Check if this is the right opponent
    if duel.get("opponent_id") and duel.get("opponent_id") != opponent_id:
        await callback.answer("❌ Bu duel sizga emas!", show_alert=True)
        return

    # Can't duel yourself
    if challenger_id == opponent_id:
        await callback.answer("❌ O'zingiz bilan duel o'ynay olmaysiz!", show_alert=True)
        return

    # Set opponent
    duel["opponent_id"] = opponent_id
    duel["status"] = "active"
    duel["scores"] = {challenger_id: 0, opponent_id: 0}

    await callback.answer("✅ Duel qabul qilindi!")

    # Notify both players
    text = f"""
⚔️ <b>Duel boshlandi!</b>

👤 Raqib: {db_user.full_name}
📝 5 ta savol
⏱ Har bir savol uchun 15 soniya

Tayyor bo'ling...
"""
    await callback.message.edit_text(text)

    # Start duel after 3 seconds
    await asyncio.sleep(3)
    await start_duel_round(duel_id, callback.bot)


@router.callback_query(F.data.startswith("duel:decline:"))
async def decline_duel(callback: CallbackQuery):
    """Decline duel invitation"""
    duel_id = callback.data.split(":")[-1]

    # Remove duel if exists
    if duel_id in _active_duels:
        duel = _active_duels[duel_id]
        challenger_id = duel.get("challenger_id")
        del _active_duels[duel_id]

        # Remove from waiting
        if challenger_id in _waiting_players:
            del _waiting_players[challenger_id]

    await callback.answer("❌ Duel rad etildi")
    await callback.message.edit_text(
        "❌ <b>Duel rad etildi</b>\n\n"
        "Raqib taklifni qabul qilmadi.",
        reply_markup=duel_menu_keyboard()
    )
