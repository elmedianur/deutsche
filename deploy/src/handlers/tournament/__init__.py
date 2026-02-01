"""
Tournament Handler - Haftalik/Oylik turnirlar (Database bilan)
TO'G'RILANGAN VERSIYA - Avtomatik turnir yaratish va xatolarni to'g'ri ushlash
"""
from datetime import datetime
from typing import Optional

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.database.models import User
from src.core.logging import get_logger

logger = get_logger(__name__)
router = Router(name="tournament")


async def tournament_menu_keyboard() -> InlineKeyboardMarkup:
    """Tournament menu keyboard - DINAMIK TUGMALAR"""
    from src.services.button_service import ButtonTextService

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=await ButtonTextService.get("btn_tournament_current"),
        callback_data="tournament:current"
    ))
    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_tournament_leaderboard"),
            callback_data="tournament:leaderboard"
        ),
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_tournament_prizes"),
            callback_data="tournament:prizes"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_tournament_rules"),
            callback_data="tournament:rules"
        ),
        InlineKeyboardButton(
            text=await ButtonTextService.get("btn_tournament_my_stats"),
            callback_data="tournament:my_stats"
        )
    )
    builder.row(InlineKeyboardButton(
        text=await ButtonTextService.get("btn_back"),
        callback_data="menu:main"
    ))
    return builder.as_markup()


async def back_keyboard() -> InlineKeyboardMarkup:
    """Back button keyboard - DINAMIK"""
    from src.services.button_service import ButtonTextService

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=await ButtonTextService.get("btn_back"),
        callback_data="tournament:menu"
    ))
    return builder.as_markup()


async def get_or_create_tournament():
    """Turnirni olish yoki yangi yaratish - xavfsiz versiya"""
    try:
        from src.services import tournament_service
        
        # Avval mavjud turnirni tekshirish
        tournament = await tournament_service.get_current_tournament()
        
        if tournament:
            return tournament
        
        # Turnir yo'q - yangi yaratamiz
        logger.info("No active tournament found, creating new weekly tournament...")
        new_tournament = await tournament_service.get_or_create_weekly_tournament()
        
        if new_tournament:
            # Yangi yaratilgan turnirni dict formatda qaytarish
            from src.database import get_session
            from src.repositories.tournament_repo import TournamentParticipantRepository
            
            async with get_session() as session:
                participant_repo = TournamentParticipantRepository(session)
                participants_count = await participant_repo.get_participants_count(new_tournament.id)
            
            return {
                "id": new_tournament.id,
                "name": new_tournament.name,
                "type": new_tournament.tournament_type,
                "status": new_tournament.status.value,
                "start_time": new_tournament.start_time,
                "end_time": new_tournament.end_time,
                "participants_count": participants_count,
                "is_active": new_tournament.is_active,
                "is_registration_open": new_tournament.is_registration_open,
                "time_remaining": _format_time_remaining(new_tournament.end_time)
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Error getting/creating tournament: {e}")
        return None


def _format_time_remaining(end_time: datetime) -> str:
    """Qolgan vaqtni formatlash"""
    remaining = end_time - datetime.utcnow()
    
    if remaining.total_seconds() <= 0:
        return "Tugagan"
    
    days = remaining.days
    hours = remaining.seconds // 3600
    minutes = (remaining.seconds % 3600) // 60
    
    if days > 0:
        return f"{days} kun {hours} soat"
    elif hours > 0:
        return f"{hours} soat {minutes} daqiqa"
    else:
        return f"{minutes} daqiqa"


@router.callback_query(F.data == "tournament:menu")
async def tournament_menu(callback: CallbackQuery, state: FSMContext, db_user: User):
    """Tournament main menu"""
    await state.clear()

    try:
        tournament = await get_or_create_tournament()

        if tournament:
            text = f"""
🏆 <b>Turnirlar</b>

<b>Joriy turnir:</b> {tournament['name']}
📊 Holat: {'🟢 Faol' if tournament.get('is_active') else '🟡 Kutilmoqda'}
⏰ Qolgan vaqt: {tournament['time_remaining']}
👥 Ishtirokchilar: {tournament['participants_count']}

🎁 G'oliblar Premium va yulduzlar yutadi!

💡 <i>Quiz o'ynab ball to'plang va g'olib bo'ling!</i>
"""
        else:
            text = """
🏆 <b>Turnirlar</b>

⚠️ Hozirda faol turnir yo'q.

Tez orada yangi turnir boshlanadi!
Bildirishnomalarni yoqib qo'ying.
"""

        await callback.message.edit_text(text, reply_markup=await tournament_menu_keyboard())

    except Exception as e:
        logger.error(f"Tournament menu error: {e}")
        await callback.message.edit_text(
            "🏆 <b>Turnirlar</b>\n\n"
            "⚠️ Xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring.",
            reply_markup=await tournament_menu_keyboard()
        )

    await callback.answer()


@router.callback_query(F.data == "tournament:current")
async def current_tournament(callback: CallbackQuery, db_user: User):
    """Current tournament info"""
    from src.services.button_service import ButtonTextService

    try:
        tournament = await get_or_create_tournament()

        if not tournament:
            await callback.answer("❌ Hozirda faol turnir yo'q!", show_alert=True)
            return

        # Leaderboard olish
        from src.services import tournament_service
        leaderboard = await tournament_service.get_leaderboard(tournament['id'], limit=5)

        lb_text = ""
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]

        if leaderboard:
            for i, player in enumerate(leaderboard):
                lb_text += f"{medals[i]} #{player['rank']}: {player['score']} ball\n"
        else:
            lb_text = "<i>Hali ishtirokchilar yo'q</i>\n"

        text = f"""
🏆 <b>{tournament['name']}</b>

📊 <b>Holat:</b> {'🟢 Faol' if tournament.get('is_active') else '🟡 Kutilmoqda'}
⏰ <b>Qolgan vaqt:</b> {tournament['time_remaining']}
👥 <b>Ishtirokchilar:</b> {tournament['participants_count']}

<b>🏅 Top 5:</b>
{lb_text}
💡 Quiz o'ynab ball to'plang!
"""

        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(
            text=await ButtonTextService.get("btn_tournament_play"),
            callback_data="quiz:start"
        ))
        builder.row(InlineKeyboardButton(
            text=await ButtonTextService.get("btn_tournament_leaderboard"),
            callback_data="tournament:leaderboard"
        ))
        builder.row(InlineKeyboardButton(
            text=await ButtonTextService.get("btn_back"),
            callback_data="tournament:menu"
        ))

        await callback.message.edit_text(text, reply_markup=builder.as_markup())

    except Exception as e:
        logger.error(f"Current tournament error: {e}")
        await callback.answer("❌ Xatolik yuz berdi!", show_alert=True)

    await callback.answer()


@router.callback_query(F.data == "tournament:leaderboard")
async def leaderboard(callback: CallbackQuery, db_user: User):
    """Full leaderboard"""
    try:
        tournament = await get_or_create_tournament()

        if not tournament:
            await callback.answer("❌ Hozirda faol turnir yo'q!", show_alert=True)
            return

        from src.services import tournament_service
        leaderboard_data = await tournament_service.get_leaderboard(tournament['id'], limit=15)

        if not leaderboard_data:
            text = f"📊 <b>Reyting - {tournament['name']}</b>\n\n<i>Hali ishtirokchilar yo'q</i>\n\n💡 Birinchi bo'lib qatnashing!"
        else:
            text = f"📊 <b>Reyting - {tournament['name']}</b>\n\n"
            medals = ["🥇", "🥈", "🥉"]

            for player in leaderboard_data:
                rank = player['rank']
                prefix = medals[rank - 1] if rank <= 3 else f"{rank}."
                accuracy = f"{player['accuracy']:.0f}%" if player['accuracy'] > 0 else "-"
                text += f"{prefix} <b>{player['score']:.0f}</b> ball | {accuracy} aniqlik\n"

        await callback.message.edit_text(text, reply_markup=await back_keyboard())

    except Exception as e:
        logger.error(f"Leaderboard error: {e}")
        await callback.answer("❌ Xatolik yuz berdi!", show_alert=True)

    await callback.answer()


@router.callback_query(F.data == "tournament:prizes")
async def prizes(callback: CallbackQuery):
    """Tournament prizes"""
    text = """
🎁 <b>Turnir sovrinlari</b>

<b>Haftalik turnir:</b>
🥇 1-o'rin: 500 ⭐ + 7 kun Premium
🥈 2-o'rin: 250 ⭐ + 3 kun Premium
🥉 3-o'rin: 100 ⭐ + 1 kun Premium

<b>Ball hisoblash:</b>
• To'g'ri javob: <b>10 ball</b>
• 100% natija bonusi: <b>+20 ball</b>
• Tezlik bonusi: <b>+1-5 ball</b>

<b>Qanday g'alaba qozonish mumkin?</b>
1. Ko'proq quiz o'ynang
2. Aniqlikni oshiring
3. Tezroq javob bering

💡 <i>Har hafta yangi turnir boshlanadi!</i>
"""
    await callback.message.edit_text(text, reply_markup=await back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "tournament:rules")
async def rules(callback: CallbackQuery):
    """Tournament rules"""
    text = """
📜 <b>Turnir qoidalari</b>

<b>Asosiy qoidalar:</b>
1. Quiz o'ynab ball to'plang
2. Eng ko'p ball to'plagan - g'olib
3. Teng ball bo'lsa, aniqlik hisoblanadi
4. Sovrinlar avtomatik beriladi

<b>Ball hisoblash:</b>
• Har bir to'g'ri javob = 10 ball
• 5+ savolli 100% natija = +20 bonus
• Tezlik hisobga olinadi

<b>Muhim:</b>
• Bir foydalanuvchi - bir akkaunt
• Hiyla ishlatish taqiqlangan
• Adminlar qarorini hurmat qiling

⚠️ Qoidabuzarlar diskvalifikatsiya qilinadi!
"""
    await callback.message.edit_text(text, reply_markup=await back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "tournament:my_stats")
async def my_stats(callback: CallbackQuery, db_user: User):
    """User's tournament stats"""
    from src.services.button_service import ButtonTextService

    try:
        from src.services import tournament_service
        stats = await tournament_service.get_user_tournament_stats(db_user.user_id)

        if not stats:
            tournament = await get_or_create_tournament()
            if tournament:
                text = f"""
📈 <b>Turnir statistikasi</b>

<b>Turnir:</b> {tournament['name']}

❌ Siz hali qatnashmadingiz!

Quiz o'ynab turnirda qatnashing va sovrinlar yuting!
"""
            else:
                text = "📈 <b>Turnir statistikasi</b>\n\n❌ Hozirda faol turnir yo'q."

            builder = InlineKeyboardBuilder()
            builder.row(InlineKeyboardButton(
                text=await ButtonTextService.get("btn_tournament_join"),
                callback_data="quiz:start"
            ))
            builder.row(InlineKeyboardButton(
                text=await ButtonTextService.get("btn_back"),
                callback_data="tournament:menu"
            ))
            await callback.message.edit_text(text, reply_markup=builder.as_markup())
            await callback.answer()
            return

        if not stats.get('registered'):
            text = f"""
📈 <b>Turnir statistikasi</b>

<b>Turnir:</b> {stats['tournament_name']}

❌ Siz hali qatnashmadingiz!

Quiz o'ynab turnirda qatnashing va sovrinlar yuting!
"""
            builder = InlineKeyboardBuilder()
            builder.row(InlineKeyboardButton(
                text=await ButtonTextService.get("btn_tournament_join"),
                callback_data="quiz:start"
            ))
            builder.row(InlineKeyboardButton(
                text=await ButtonTextService.get("btn_back"),
                callback_data="tournament:menu"
            ))
        else:
            accuracy = f"{stats['accuracy']:.1f}%" if stats['accuracy'] > 0 else "0%"

            # Reyting bo'yicha emoji
            if stats['rank'] == 1:
                rank_emoji = "🥇"
            elif stats['rank'] == 2:
                rank_emoji = "🥈"
            elif stats['rank'] == 3:
                rank_emoji = "🥉"
            elif stats['rank'] <= 10:
                rank_emoji = "🔥"
            else:
                rank_emoji = "📍"

            text = f"""
📈 <b>Turnir statistikasi</b>

<b>Turnir:</b> {stats['tournament_name']}

{rank_emoji} <b>O'rnim:</b> #{stats['rank']} / {stats['total_participants']}
⭐ <b>Ball:</b> {stats['score']:.0f}
✅ <b>To'g'ri javoblar:</b> {stats['correct_answers']} / {stats['total_questions']}
📊 <b>Aniqlik:</b> {accuracy}

{"🏆 Top 3 da ekansiz! Davom eting!" if stats["rank"] <= 3 else "💪 Ko'proq quiz o'ynab reytingda ko'tariling!"}
"""
            builder = InlineKeyboardBuilder()
            builder.row(InlineKeyboardButton(
                text=await ButtonTextService.get("btn_tournament_play_more"),
                callback_data="quiz:start"
            ))
            builder.row(InlineKeyboardButton(
                text=await ButtonTextService.get("btn_back"),
                callback_data="tournament:menu"
            ))

        await callback.message.edit_text(text, reply_markup=builder.as_markup())

    except Exception as e:
        logger.error(f"My stats error: {e}")
        await callback.answer("❌ Xatolik yuz berdi!", show_alert=True)

    await callback.answer()


async def add_tournament_score(
    user_id: int, 
    correct: int, 
    total: int, 
    time_taken: float
) -> Optional[dict]:
    """
    Quiz tugaganda turnirga ball qo'shish.
    Bu funksiya quiz handler'dan chaqiriladi.
    """
    try:
        from src.services import tournament_service
        result = await tournament_service.add_quiz_score(
            user_id=user_id,
            correct=correct,
            total=total,
            time_taken=time_taken
        )
        return result
    except Exception as e:
        logger.error(f"Error adding tournament score: {e}")
        return None
