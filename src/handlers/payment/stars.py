"""
Payment Handler - Telegram Stars payments
"""
from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery,
    PreCheckoutQuery, SuccessfulPayment
)
from aiogram.filters import Command

from src.database.models import User
from src.services import payment_service, PAYMENT_PLANS
from src.keyboards.inline import (
    premium_menu_keyboard,
    back_button,
    confirm_keyboard,
)
from src.core.logging import get_logger

logger = get_logger(__name__)
router = Router(name="payment")


# ============================================================
# PREMIUM MENU
# ============================================================

@router.callback_query(F.data == "premium:menu")
async def premium_menu(callback: CallbackQuery, db_user: User, is_premium: bool):
    """Show premium menu"""
    if is_premium:
        # Get subscription info
        sub_info = await payment_service.check_subscription(db_user.user_id)
        
        text = f"""
⭐ <b>Premium Status</b>

✅ <b>Sizda Premium obuna mavjud!</b>

📅 Holat: {sub_info['status_text']}
📆 Qolgan kun: {sub_info['days_remaining']}
💰 Jami to'langan: {sub_info['total_paid']} ⭐

<b>Premium afzalliklari:</b>
• 📚 Premium savollar
• 🔊 Audio talaffuz
• 🛡 Streak himoyasi
• ♾ Cheksiz quiz
"""
    else:
        text = """
⭐ <b>Premium obuna</b>

Premium bilan til o'rganish ancha samarali!

<b>Premium afzalliklari:</b>
• 📚 <b>Premium savollar</b> - qo'shimcha kontentga kirish
• 🔊 <b>Audio talaffuz</b> - to'g'ri talaffuzni tinglash
• 🛡 <b>Streak himoyasi</b> - 1 kun o'tkazib yuborish mumkin
• ♾ <b>Cheksiz quiz</b> - limitlarsiz o'rganish
• 📊 <b>Batafsil statistika</b>

<b>💰 Narxlar (Telegram Stars):</b>
"""
        for plan_id, plan in PAYMENT_PLANS.items():
            text += f"\n⭐ <b>{plan['title']}</b> - {plan['stars']} yulduz"
    
    await callback.message.edit_text(
        text,
        reply_markup=premium_menu_keyboard(is_premium)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("premium:buy:"))
async def buy_premium(callback: CallbackQuery, db_user: User, bot: Bot):
    """Initiate premium purchase"""
    plan_id = callback.data.split(":")[-1]
    
    plan = payment_service.get_plan(plan_id)
    if not plan:
        await callback.answer("Noto'g'ri tarif", show_alert=True)
        return
    
    # Confirm purchase
    text = f"""
💳 <b>To'lovni tasdiqlang</b>

📦 Tarif: <b>{plan['title']}</b>
💰 Narxi: <b>{plan['stars']} ⭐</b>
📅 Muddat: <b>{plan['days']} kun</b>

Telegram Stars orqali to'laysizmi?
"""
    
    await callback.message.edit_text(
        text,
        reply_markup=confirm_keyboard(
            confirm_data=f"premium:confirm:{plan_id}",
            cancel_data="premium:menu",
            confirm_text="💳 To'lash",
            cancel_text="❌ Bekor qilish"
        )
    )
    await callback.answer()


@router.callback_query(F.data.startswith("premium:confirm:"))
async def confirm_purchase(callback: CallbackQuery, db_user: User, bot: Bot):
    """Send invoice for confirmed purchase"""
    plan_id = callback.data.split(":")[-1]
    
    try:
        # Delete confirmation message
        await callback.message.delete()
        
        # Send invoice
        await payment_service.create_invoice(
            chat_id=callback.message.chat.id,
            user_id=db_user.user_id,
            plan_id=plan_id
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Invoice creation failed: {e}")
        await callback.answer(
            "❌ Xatolik yuz berdi. Keyinroq urinib ko'ring.",
            show_alert=True
        )


# ============================================================
# PAYMENT PROCESSING
# ============================================================

@router.pre_checkout_query(F.invoice_payload.startswith("premium:"))
async def process_pre_checkout(pre_checkout: PreCheckoutQuery):
    """Handle pre-checkout query"""
    try:
        await payment_service.process_pre_checkout(pre_checkout)
    except Exception as e:
        logger.error(f"Pre-checkout error: {e}", exc_info=True)
        try:
            await pre_checkout.answer(ok=False, error_message="Xatolik yuz berdi")
        except Exception:
            pass


@router.message(F.successful_payment.invoice_payload.startswith("premium:"))
async def process_successful_payment(message: Message, db_user: User):
    """Handle successful payment"""
    payment = message.successful_payment
    
    try:
        result = await payment_service.process_successful_payment(message, payment)
        
        if result.get("success"):
            text = f"""
🎉 <b>To'lov muvaffaqiyatli!</b>

✅ Sizga Premium obuna berildi!

📦 Tarif: {result.get('plan', 'unknown')}
📅 Tugash sanasi: {result.get('expires_at', 'N/A')}

Endi barcha Premium imkoniyatlardan foydalanishingiz mumkin! 🚀
"""
            await message.answer(text, reply_markup=back_button())
        else:
            await message.answer(
                "❌ To'lovni qayta ishlashda xatolik. Admin bilan bog'laning.",
                reply_markup=back_button()
            )
            
    except Exception as e:
        logger.error(f"Payment processing error: {e}")
        await message.answer(
            "❌ Xatolik yuz berdi. Iltimos, admin bilan bog'laning.",
            reply_markup=back_button()
        )


# ============================================================
# PROMO CODE
# ============================================================

@router.callback_query(F.data == "premium:promo")
async def promo_menu(callback: CallbackQuery):
    """Show promo code input"""
    await callback.message.edit_text(
        "🎁 <b>Promo kod</b>\n\n"
        "Promo kodni yuboring:",
        reply_markup=back_button("premium:menu")
    )
    await callback.answer()


@router.message(F.text.regexp(r'^[A-Za-z0-9]{4,20}$'))
async def apply_promo(message: Message, db_user: User):
    """Try to apply promo code"""
    code = message.text.strip().upper()
    
    result = await payment_service.apply_promo_code(db_user.user_id, code)
    
    if result.get("success"):
        rewards_text = ", ".join(result.get("rewards", []))
        await message.answer(
            f"🎉 <b>Promo kod qabul qilindi!</b>\n\n"
            f"🎁 Sovg'alar: {rewards_text}",
            reply_markup=back_button()
        )
    else:
        await message.answer(
            f"❌ {result.get('message', 'Xatolik')}",
            reply_markup=back_button("premium:menu")
        )


# ============================================================
# REFERRAL SYSTEM
# ============================================================

@router.callback_query(F.data == "referral:menu")
async def referral_menu(callback: CallbackQuery, db_user: User, bot: Bot):
    """Show referral menu"""
    me = await bot.get_me()
    
    referral_link = f"https://t.me/{me.username}?start=ref_{db_user.referral_code}"
    
    text = f"""
👥 <b>Referal dasturi</b>

Do'stlaringizni taklif qiling va Premium oling!

🔗 <b>Sizning havolangiz:</b>
<code>{referral_link}</code>

📊 <b>Statistika:</b>
• Taklif qilganlar: {db_user.referral_count}
• Sovg'a kunlari: {db_user.referral_count * 3}

<b>Qanday ishlaydi?</b>
1. Havolani do'stingizga yuboring
2. Do'stingiz botga kirsin va 5 ta quiz tugatsin
3. Ikkalangiz ham 3 kun Premium olasiz! 🎁

<i>Tap to copy the link above ☝️</i>
"""
    
    await callback.message.edit_text(
        text,
        reply_markup=back_button("premium:menu")
    )
    await callback.answer()


@router.callback_query(F.data == "premium:status")
async def premium_status(callback: CallbackQuery, db_user: User):
    """Show detailed premium status"""
    sub_info = await payment_service.check_subscription(db_user.user_id)
    
    text = f"""
⭐ <b>Premium Status</b>

📊 <b>Ma'lumotlar:</b>
• Holat: {sub_info['status_text']}
• Tarif: {sub_info['plan']}
• Qolgan kun: {sub_info['days_remaining']}
• Auto-uzaytirish: {'✅' if sub_info['auto_renew'] else '❌'}

💰 <b>To'lov tarixi:</b>
• Jami to'langan: {sub_info['total_paid']} ⭐
"""
    
    await callback.message.edit_text(
        text,
        reply_markup=back_button("premium:menu")
    )
    await callback.answer()
