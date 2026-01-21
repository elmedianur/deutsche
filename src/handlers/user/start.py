"""
Start handler - /start command and onboarding
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from src.database import get_session
from src.database.models import User, Referral, ReferralStatus
from src.repositories import UserRepository, SubscriptionRepository
from src.keyboards.inline import (
    main_menu_keyboard,
    channel_subscription_keyboard,
    premium_features_keyboard,
    onboarding_keyboard,
    onboarding_guide_keyboard,
    learning_path_keyboard
)
from src.core.logging import get_logger
from src.config import settings

logger = get_logger(__name__)
router = Router(name="start")


@router.message(CommandStart(deep_link=True))
async def start_with_referral(
    message: Message,
    command: CommandObject,
    db_user: User
):
    """Handle /start with referral code"""
    referral_code = command.args
    
    if not referral_code:
        return await start_command(message, db_user)
    
    # Check if it's a referral code
    if referral_code.startswith("ref_"):
        code = referral_code[4:]
        
        async with get_session() as session:
            user_repo = UserRepository(session)
            
            # Find referrer
            referrer = await user_repo.get_by_referral_code(code)
            
            if referrer and referrer.user_id != message.from_user.id:
                # Check if already referred
                if db_user.referred_by_id is None:
                    # Save referral
                    db_user.referred_by_id = referrer.user_id
                    await user_repo.save(db_user)
                    
                    # Create referral record
                    from sqlalchemy import select
                    from src.database.models import Referral
                    
                    existing = await session.execute(
                        select(Referral).where(
                            Referral.referred_id == message.from_user.id
                        )
                    )
                    
                    if not existing.scalar_one_or_none():
                        referral = Referral(
                            referrer_id=referrer.user_id,
                            referred_id=message.from_user.id,
                            referral_code=code,
                            status=ReferralStatus.PENDING,
                            required_quizzes=settings.REFERRAL_MIN_QUIZZES
                        )
                        session.add(referral)
                        await session.commit()
                    
                    await message.answer(
                        f"🎉 Siz {referrer.full_name} orqali ro'yxatdan o'tdingiz!\n\n"
                        f"📚 {settings.REFERRAL_MIN_QUIZZES} ta quiz tugatganingizda "
                        f"ikkalangiz ham sovg'a olasiz!"
                    )
                    
                    logger.info(
                        "Referral registered",
                        referrer_id=referrer.user_id,
                        referred_id=message.from_user.id
                    )
    
    return await start_command(message, db_user)


@router.message(CommandStart())
async def start_command(message: Message, db_user: User, **kwargs):
    """Handle /start command"""

    # Check for required channels
    not_subscribed = kwargs.get("not_subscribed_channels", [])

    if not_subscribed:
        channels_text = "\n".join(
            f"• {ch.icon} {ch.title}"
            for ch in not_subscribed
        )

        await message.answer(
            f"👋 Assalomu alaykum, {db_user.full_name}!\n\n"
            f"📢 Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:\n\n"
            f"{channels_text}",
            reply_markup=channel_subscription_keyboard(not_subscribed)
        )
        return

    # Always show main menu
    # Get streak info
    streak_count = 0
    if db_user.streak:
        streak_count = db_user.streak.current_streak

    welcome_text = f"""
👋 <b>Assalomu alaykum, {db_user.full_name}!</b>

🎓 <b>Quiz Bot Pro</b> - til o'rganish uchun eng yaxshi bot!

📊 <b>Sizning statistikangiz:</b>
├ 📝 Quiz'lar: {db_user.total_quizzes}
├ ✅ To'g'ri javoblar: {db_user.total_correct}
├ 🎯 Aniqlik: {db_user.accuracy:.1f}%
└ 🔥 Streak: {streak_count} kun

Davom etamizmi? 👇
"""
    await message.answer(
        welcome_text,
        reply_markup=main_menu_keyboard()
    )


@router.callback_query(F.data == "check:subscription")
async def check_subscription(callback: CallbackQuery, db_user: User, **kwargs):
    """Check subscription and show main menu"""
    not_subscribed = kwargs.get("not_subscribed_channels", [])
    
    if not_subscribed:
        await callback.answer(
            "❌ Siz hali barcha kanallarga obuna bo'lmadingiz!",
            show_alert=True
        )
        return
    
    await callback.message.edit_text(
        f"✅ Ajoyib! Endi botdan foydalanishingiz mumkin.\n\n"
        f"Quyidagi menyudan tanlang 👇",
        reply_markup=main_menu_keyboard()
    )


@router.message(Command("help"))
async def help_command(message: Message):
    """Help command"""
    help_text = """
📚 <b>Yordam</b>

<b>Asosiy buyruqlar:</b>
/start - Botni boshlash
/quiz - Quiz boshlash
/stats - Statistika
/streak - Streak ma'lumotlari
/premium - Premium obuna
/settings - Sozlamalar
/help - Yordam

<b>Premium afzalliklari:</b>
⭐ Premium savollar
⭐ Cheksiz quiz
⭐ Streak himoyasi
⭐ Audio talaffuz
⭐ Reklamsiz

Savollar bo'lsa: @admin_username
"""
    
    await message.answer(help_text, reply_markup=main_menu_keyboard())


@router.message(Command("premium"))
async def premium_command(message: Message, db_user: User, is_premium: bool):
    """Premium command"""
    if is_premium:
        text = """
⭐ <b>Sizda Premium obuna mavjud!</b>

✅ Barcha premium imkoniyatlardan foydalanishingiz mumkin.

Premium afzalliklari:
• 📚 Premium savollar
• 🔊 Audio talaffuz
• 🛡 Streak himoyasi
• ♾ Cheksiz quiz
"""
    else:
        text = """
⭐ <b>Premium obuna</b>

Premium afzalliklari:
• 📚 Premium savollar - qo'shimcha kontentga kirish
• 🔊 Audio talaffuz - to'g'ri talaffuzni tinglash
• 🛡 Streak himoyasi - 1 kun o'tkazib yuborish mumkin
• ♾ Cheksiz quiz - limitlarsiz o'rganish
• 📊 Batafsil statistika

<b>Narxlar:</b>
⭐ 1 oy - 100 yulduz
⭐ 1 yil - 1000 yulduz (40% chegirma!)
💎 Lifetime - 5000 yulduz
"""
    
    from src.keyboards.inline import premium_menu_keyboard
    await message.answer(text, reply_markup=premium_menu_keyboard(is_premium))


@router.message(Command("quiz"))
async def quiz_command(message: Message):
    """Quiz boshlash"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎯 Quiz boshlash", callback_data="quiz:start"))
    builder.row(InlineKeyboardButton(text="🏠 Menyu", callback_data="menu:main"))
    
    await message.answer(
        "📚 <b>Quiz</b>\n\n"
        "Til o'rganish quizini boshlash uchun tugmani bosing:",
        reply_markup=builder.as_markup()
    )


@router.message(Command("stats"))
async def stats_command(message: Message):
    """Statistika ko'rsatish"""
    user_id = message.from_user.id
    
    from src.database import get_session
    from src.repositories import UserRepository
    
    async with get_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_user_id(user_id)
    
    if not user:
        await message.answer("❌ Foydalanuvchi topilmadi!")
        return
    
    # SM-2 statistikasi
    try:
        from src.repositories.spaced_rep_repo import SpacedRepetitionRepository
        async with get_session() as session:
            sr_repo = SpacedRepetitionRepository(session)
            sm2_stats = await sr_repo.get_user_stats(user_id)
    except Exception as e:
        logger.debug(f"SM-2 stats error: {e}")
        sm2_stats = {"total": 0, "mastered": 0, "learning": 0, "due_today": 0, "accuracy": 0}
    
    # Hisoblash
    total_answered = user.total_correct + (user.total_questions - user.total_correct)
    accuracy = round(user.total_correct / user.total_questions * 100, 1) if user.total_questions > 0 else 0
    
    text = f"""
📊 <b>Sizning statistikangiz</b>

👤 <b>Umumiy:</b>
├ 📝 Quizlar: {user.total_quizzes}
├ ✅ To'g'ri javoblar: {user.total_correct}
├ 📊 Jami savollar: {user.total_questions}
├ 🎯 Aniqlik: {accuracy}%
└ 💎 Premium: {'Ha' if user.is_premium else "Yo'q"}

📚 <b>O'rganish (SM-2):</b>
├ 📖 Jami savollar: {sm2_stats['total']}
├ ✅ O'zlashtirilgan: {sm2_stats['mastered']}
├ 📝 O'rganilmoqda: {sm2_stats['learning']}
├ 🔄 Bugun takrorlash: {sm2_stats['due_today']}
└ 🎯 Aniqlik: {sm2_stats['accuracy']}%
"""
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎯 Quiz", callback_data="quiz:start"))
    builder.row(InlineKeyboardButton(text="🏠 Menyu", callback_data="menu:main"))
    
    await message.answer(text, reply_markup=builder.as_markup())


# ============================================================
# ONBOARDING HANDLERS
# ============================================================

@router.callback_query(F.data == "onboard:menu")
async def onboard_menu(callback: CallbackQuery, db_user: User):
    """Show onboarding menu"""
    welcome_text = f"""
👋 <b>Xush kelibsiz, {db_user.full_name}!</b>

🎓 <b>Quiz Bot Pro</b> - nemis tilini o'rganish uchun eng yaxshi bot!

📚 <b>O'rganish yo'li:</b>
┌─ 🟢 <b>A1</b> - Boshlang'ich (Boshlovchilar uchun)
├─ 🟡 <b>A2</b> - Elementar
├─ 🔵 <b>B1</b> - O'rta
├─ 🟣 <b>B2</b> - Yuqori o'rta
├─ 🟠 <b>C1</b> - Ilg'or
└─ 🔴 <b>C2</b> - Mutaxassis

💡 <b>Tavsiya:</b> A1 dan boshlang va har kuni kamida 1 ta quiz yeching!

Qayerdan boshlaysiz? 👇
"""
    await callback.message.edit_text(
        welcome_text,
        reply_markup=onboarding_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "onboard:guide")
async def onboard_guide(callback: CallbackQuery):
    """Show learning guide"""
    guide_text = """
📖 <b>O'rganish yo'riqnomasi</b>

<b>1️⃣ Daraja tanlang:</b>
   Boshlang'ich bo'lsangiz → <b>A1</b>
   Biroz bilsangiz → <b>A2</b> yoki <b>B1</b>

<b>2️⃣ Kun/Mavzu tanlang:</b>
   Har bir daraja 30-70 kungacha bo'lingan
   Har kuni yangi mavzu bor

<b>3️⃣ Quiz yeching:</b>
   5, 10, 15 yoki 20 ta savol tanlang
   Har bir to'g'ri javob uchun ball olasiz

<b>4️⃣ Takrorlang:</b>
   🃏 Flashcards - so'zlarni eslab qolish
   🔄 SM-2 tizimi avtomatik takrorlash

<b>5️⃣ Raqobatlashing:</b>
   ⚔️ Duel - do'stlar bilan bellashish
   🏆 Turnir - haftalik musobaqalar

<b>💡 Maslahat:</b>
Har kuni 15-30 daqiqa o'rganing va
🔥 streak ni yo'qotmang!
"""
    await callback.message.edit_text(
        guide_text,
        reply_markup=onboarding_guide_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "onboard:start_a1")
async def onboard_start_a1(callback: CallbackQuery, state: FSMContext):
    """Start from A1 level - redirect to quiz with A1"""
    from src.services import quiz_service

    try:
        languages = await quiz_service.get_languages()

        # Find German (or first language)
        german = None
        for lang in languages:
            if "german" in lang["name"].lower() or "nemis" in lang["name"].lower():
                german = lang
                break

        if not german and languages:
            german = languages[0]

        if german:
            # Get levels for this language
            levels = await quiz_service.get_levels(german["id"])

            # Find A1 level
            a1_level = None
            for level in levels:
                if "A1" in level["name"].upper():
                    a1_level = level
                    break

            if a1_level:
                # Redirect to A1 days selection
                from src.keyboards.inline import day_keyboard
                days = await quiz_service.get_days(a1_level["id"])

                # Set state for quiz flow
                from src.handlers.quiz.simple import QuizStates
                await state.set_state(QuizStates.selecting_day)
                await state.update_data(language_id=german["id"], level_id=a1_level["id"])

                text = f"""
🎯 <b>{german['flag']} {german['name']} - {a1_level['name']}</b>

📚 Kunni tanlang (1-kundan boshlash tavsiya etiladi):

💡 Har bir kun yangi mavzuni o'z ichiga oladi.
Ketma-ket o'rganish eng yaxshi natija beradi!
"""
                await callback.message.edit_text(
                    text,
                    reply_markup=day_keyboard(days, level_id=a1_level["id"])
                )
                await callback.answer("🎯 A1 darajasi tanlandi!")
                return

        # No languages or levels found
        await callback.answer("❌ Tillar yoki darajalar topilmadi!", show_alert=True)

    except Exception as e:
        logger.error(f"Onboard start A1 error: {e}")
        await callback.answer("❌ Xatolik yuz berdi!", show_alert=True)


@router.callback_query(F.data == "onboard:level_test")
async def onboard_level_test(callback: CallbackQuery):
    """Show level test info"""
    text = """
📊 <b>Darajangizni aniqlash</b>

Hozircha avtomatik test mavjud emas.

<b>O'zingiz baholang:</b>

🟢 <b>A1</b> - Hech narsa bilmayman
🟡 <b>A2</b> - Oddiy so'zlar va iboralarni bilaman
🔵 <b>B1</b> - Oddiy gaplar tuza olaman
🟣 <b>B2</b> - Erkin muloqot qila olaman

💡 Ishonchsiz bo'lsangiz, <b>A1</b> dan boshlang!
"""
    await callback.message.edit_text(
        text,
        reply_markup=learning_path_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("onboard:level:"))
async def onboard_select_level(callback: CallbackQuery, state: FSMContext):
    """Handle level selection from onboarding"""
    level_name = callback.data.split(":")[-1]  # A1, A2, B1, etc.

    from src.services import quiz_service

    try:
        languages = await quiz_service.get_languages()

        # Find German (or first language)
        german = None
        for lang in languages:
            if "german" in lang["name"].lower() or "nemis" in lang["name"].lower():
                german = lang
                break

        if not german and languages:
            german = languages[0]

        if german:
            levels = await quiz_service.get_levels(german["id"])

            # Find selected level
            selected_level = None
            for level in levels:
                if level_name.upper() in level["name"].upper():
                    selected_level = level
                    break

            if selected_level:
                from src.keyboards.inline import day_keyboard
                days = await quiz_service.get_days(selected_level["id"])

                # Set state for quiz flow
                from src.handlers.quiz.simple import QuizStates
                await state.set_state(QuizStates.selecting_day)
                await state.update_data(language_id=german["id"], level_id=selected_level["id"])

                text = f"""
🎯 <b>{german['flag']} {german['name']} - {selected_level['name']}</b>

📚 Kunni tanlang:

💡 1-kundan ketma-ket o'rganish tavsiya etiladi!
"""
                await callback.message.edit_text(
                    text,
                    reply_markup=day_keyboard(days, level_id=selected_level["id"])
                )
                await callback.answer(f"📚 {level_name} darajasi tanlandi!")
                return

        await callback.answer("Daraja topilmadi", show_alert=True)

    except Exception as e:
        logger.error(f"Onboard select level error: {e}")
        await callback.answer("❌ Xatolik yuz berdi!", show_alert=True)
