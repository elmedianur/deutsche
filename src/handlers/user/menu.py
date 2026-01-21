"""
Menu handler - Main menu and navigation
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from src.database import get_session
from src.database.models import User
from src.repositories import ProgressRepository, StreakRepository
from src.services import achievement_service
from src.keyboards.inline import (
    main_menu_keyboard,
    settings_keyboard,
    back_button,
)
from src.core.logging import get_logger

logger = get_logger(__name__)
router = Router(name="menu")


@router.callback_query(F.data == "menu:main")
async def main_menu(callback: CallbackQuery, db_user: User):
    """Show main menu"""
    text = f"""
🏠 <b>Asosiy menyu</b>

👤 {db_user.full_name}
📊 Quiz'lar: {db_user.total_quizzes} | To'g'ri: {db_user.total_correct}

Quyidagi menyudan tanlang 👇
"""
    
    await callback.message.edit_text(
        text,
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "stats:menu")
async def stats_menu(callback: CallbackQuery, db_user: User):
    """Show statistics menu"""
    async with get_session() as session:
        progress_repo = ProgressRepository(session)
        streak_repo = StreakRepository(session)
        
        stats = await progress_repo.get_user_stats(db_user.user_id)
        streak = await streak_repo.get_or_create(db_user.user_id)
        
        # Get achievement stats
        ach_stats = await achievement_service.get_achievement_stats(db_user.user_id)
    user_rank = await get_user_rank(db_user.user_id)
    
    text = f"""
📊 <b>Sizning statistikangiz</b>

<b>Quiz natijalari:</b>
• Jami quiz: {stats['total_quizzes']}
• To'g'ri javoblar: {stats['total_correct']}
• Jami savollar: {stats['total_questions']}
• Aniqlik: {stats['accuracy']:.1f}%
• O'rtacha vaqt: {stats['avg_time']:.1f}s

<b>Streak:</b>
🔥 Joriy streak: {streak.current_streak} kun
🏆 Eng uzun streak: {streak.longest_streak} kun

<b>Yutuqlar:</b>
🏅 {ach_stats['earned']}/{ach_stats['total']} ({ach_stats['percentage']:.0f}%)

<b>Reyting:</b>
🥇 #{user_rank} o'rin
"""
    
    await callback.message.edit_text(
        text,
        reply_markup=back_button()
    )
    await callback.answer()


async def get_user_rank(user_id: int) -> int:
    """Get user's rank"""
    async with get_session() as session:
        from src.repositories import UserRepository
        user_repo = UserRepository(session)
        return await user_repo.get_user_rank(user_id)


@router.callback_query(F.data == "streak:info")
async def streak_info(callback: CallbackQuery, db_user: User):
    """Show streak information"""
    async with get_session() as session:
        streak_repo = StreakRepository(session)
        streak = await streak_repo.get_or_create(db_user.user_id)
    
    days_left, milestone = streak.days_until_milestone
    
    if streak.current_streak > 0:
        status_emoji = "🔥"
        status_text = f"Ajoyib! {streak.current_streak} kunlik streak!"
    else:
        status_emoji = "❄️"
        status_text = "Streak yo'q. Bugun quizni boshlang!"
    
    freeze_text = f"🛡 Freeze: {streak.freeze_count} ta" if streak.freeze_count > 0 else ""
    
    text = f"""
{status_emoji} <b>Streak ma'lumotlari</b>

{status_text}

📅 Joriy streak: <b>{streak.current_streak}</b> kun
🏆 Eng uzun streak: <b>{streak.longest_streak}</b> kun
{freeze_text}

<b>Keyingi milestone:</b>
🎯 {milestone} kun - yana {days_left} kun qoldi

<b>Streak bonuslari:</b>
• 7 kun - 50 ⭐
• 30 kun - 200 ⭐ + 7 kun Premium
• 100 kun - 500 ⭐ + 30 kun Premium
• 365 kun - 2000 ⭐ + 90 kun Premium
"""
    
    await callback.message.edit_text(
        text,
        reply_markup=back_button()
    )
    await callback.answer()


@router.callback_query(F.data == "achievements:menu")
async def achievements_menu(callback: CallbackQuery, db_user: User):
    """Show achievements - page 0"""
    await show_achievements_page(callback, db_user, page=0)


@router.callback_query(F.data.startswith("achievements:page:"))
async def achievements_page(callback: CallbackQuery, db_user: User):
    """Show achievements - specific page"""
    page = int(callback.data.split(":")[2])
    await show_achievements_page(callback, db_user, page=page)


async def show_achievements_page(callback: CallbackQuery, db_user: User, page: int = 0):
    """Show achievements with pagination"""
    per_page = 8
    
    achievements = await achievement_service.get_user_achievements(
        db_user.user_id,
        include_unearned=True
    )

    # Group by earned/not earned
    earned = [a for a in achievements if a["is_earned"]]
    unearned = [a for a in achievements if not a["is_earned"] and not a["is_secret"]]
    
    # All achievements for pagination
    all_achs = earned + unearned
    total_pages = (len(all_achs) + per_page - 1) // per_page
    
    # Get current page items
    start = page * per_page
    end = start + per_page
    current_achs = all_achs[start:end]
    
    # Stats
    stats = await achievement_service.get_achievement_stats(db_user.user_id)
    
    text = f"🏅 <b>Yutuqlar</b> ({page + 1}/{total_pages})\n"
    text += f"📊 Progress: {stats['earned']}/{stats['total']} ({stats['percentage']:.0f}%)\n\n"
    
    for ach in current_achs:
        if ach["is_earned"]:
            text += f"✅ {ach['icon']} {ach['name']} {ach['rarity_icon']}\n"
        else:
            text += f"🔒 ⬜ {ach['name']}\n   <i>{ach['description']}</i>\n"
    
    # Build keyboard with pagination
    builder = InlineKeyboardBuilder()
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="◀️", callback_data=f"achievements:page:{page-1}")
        )
    nav_buttons.append(
        InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop")
    )
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton(text="▶️", callback_data=f"achievements:page:{page+1}")
        )
    
    if nav_buttons:
        builder.row(*nav_buttons)
    
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="menu:main")
    )
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "settings:menu")
async def settings_menu(callback: CallbackQuery, db_user: User):
    """Show settings menu"""
    settings_data = {
        "notifications": db_user.notifications_enabled,
        "daily_reminder": db_user.daily_reminder_enabled,
    }
    
    text = f"""
⚙️ <b>Sozlamalar</b>

O'zgartirmoqchi bo'lgan sozlamani tanlang:
"""
    
    await callback.message.edit_text(
        text,
        reply_markup=settings_keyboard(settings_data)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("settings:toggle:"))
async def toggle_setting(callback: CallbackQuery, db_user: User):
    """Toggle a setting"""
    setting = callback.data.split(":")[-1]
    
    async with get_session() as session:
        from src.repositories import UserRepository
        user_repo = UserRepository(session)
        
        user = await user_repo.get_by_user_id(db_user.user_id)
        
        if setting == "notifications":
            user.notifications_enabled = not user.notifications_enabled
            new_value = user.notifications_enabled
        elif setting == "daily_reminder":
            user.daily_reminder_enabled = not user.daily_reminder_enabled
            new_value = user.daily_reminder_enabled
        else:
            await callback.answer("Noma'lum sozlama", show_alert=True)
            return
        
        await user_repo.save(user)
    
    status = "yoqildi ✅" if new_value else "o'chirildi ❌"
    await callback.answer(f"Sozlama {status}")
    
    # Refresh settings menu
    await settings_menu(callback, db_user)


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery):
    """No operation callback (for disabled buttons)"""
    await callback.answer()


@router.callback_query(F.data == "settings:language")
async def settings_language(callback: CallbackQuery, db_user: User):
    """Show language settings"""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="settings:set_lang:uz"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="settings:set_lang:ru")
    )
    builder.row(
        InlineKeyboardButton(text="🇬🇧 English", callback_data="settings:set_lang:en")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="settings:menu")
    )
    
    await callback.message.edit_text(
        "🌐 <b>Til sozlamalari</b>\n\n"
        "Bot tilini tanlang:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("settings:set_lang:"))
async def set_language(callback: CallbackQuery, db_user: User):
    """Set user language"""
    lang = callback.data.split(":")[-1]

    lang_names = {"uz": "O'zbekcha", "ru": "Русский", "en": "English"}

    # Save to database
    async with get_session() as session:
        from src.repositories import UserRepository
        user_repo = UserRepository(session)
        user = await user_repo.get_by_user_id(db_user.user_id)
        if user:
            user.language = lang
            await user_repo.save(user)

    await callback.answer(f"✅ Til o'zgartirildi: {lang_names.get(lang, lang)}", show_alert=True)
    await settings_menu(callback, db_user)


@router.callback_query(F.data == "settings:learning_path")
async def settings_learning_path(callback: CallbackQuery):
    """O'rganish yo'li - daraja tanlash"""
    text = """
📚 <b>O'rganish yo'li</b>

🎓 <b>Darajalar:</b>
┌─ 🟢 <b>A1</b> - Boshlang'ich (Boshlovchilar uchun)
├─ 🟡 <b>A2</b> - Elementar
├─ 🔵 <b>B1</b> - O'rta
├─ 🟣 <b>B2</b> - Yuqori o'rta
├─ 🟠 <b>C1</b> - Ilg'or
└─ 🔴 <b>C2</b> - Mutaxassis

💡 <b>Tavsiya:</b> A1 dan boshlang va har kuni kamida 1 ta quiz yeching!

Darajangizni tanlang 👇
"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🟢 A1", callback_data="onboard:level:A1"),
        InlineKeyboardButton(text="🟡 A2", callback_data="onboard:level:A2")
    )
    builder.row(
        InlineKeyboardButton(text="🔵 B1", callback_data="onboard:level:B1"),
        InlineKeyboardButton(text="🟣 B2", callback_data="onboard:level:B2")
    )
    builder.row(
        InlineKeyboardButton(text="🟠 C1", callback_data="onboard:level:C1"),
        InlineKeyboardButton(text="🔴 C2", callback_data="onboard:level:C2")
    )
    builder.row(
        InlineKeyboardButton(text="📖 Qo'llanma", callback_data="onboard:guide")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="settings:menu")
    )

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()
