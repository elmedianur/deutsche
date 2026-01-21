# 📱 Quiz Bot Pro

Til o'rganish uchun professional Telegram quiz boti.

---

## 🚀 Botni Ishga Tushirish

### 1-qadam: Bot yaratish
1. Telegram'da @BotFather ga boring
2. `/newbot` buyrug'ini yuboring
3. Bot nomini kiriting (masalan: "Nemis Quiz")
4. Username kiriting (masalan: `german_quiz_bot`)
5. **BOT_TOKEN** ni saqlang

### 2-qadam: Admin ID olish
1. @userinfobot ga boring
2. ID raqamingizni oling (masalan: 123456789)

### 3-qadam: Sozlash
```bash
# Papkaga kiring
cd quiz_bot_pro

# .env faylini yarating
```

**.env** fayli:
```env
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
BOT_USERNAME=german_quiz_bot
DATABASE_URL=sqlite+aiosqlite:///quiz_bot.db
REDIS_URL=redis://localhost:6379/0
SUPER_ADMIN_IDS=[123456789]
ADMIN_IDS=[111111111,222222222]
LOG_LEVEL=INFO
STARS_ENABLED=true
```

### 4-qadam: Kutubxonalar o'rnatish
```bash
pip install -r requirements.txt
```

### 5-qadam: Savollar yuklash
```bash
python seed.py
```

### 6-qadam: Botni ishga tushirish
```bash
python start.py
```

---

## 👑 Admin Tizimi

### Lavozimlar

| Lavozim | Huquqlar |
|---------|----------|
| **Super Admin** | Barcha huquqlar + admin boshqaruvi |
| **Admin** | Kontent, foydalanuvchilar, broadcast |

### Super Admin huquqlari:
- ✅ Til qo'shish/o'chirish
- ✅ Admin qo'shish/o'chirish
- ✅ Premium berish
- ✅ Foydalanuvchi bloklash
- ✅ Barcha statistikalar
- ✅ To'lovlarni ko'rish
- ✅ Promo kodlar yaratish

### Admin huquqlari:
- ✅ Savol qo'shish
- ✅ Daraja/Kun qo'shish
- ✅ Excel import
- ✅ Broadcast yuborish
- ✅ Statistika ko'rish
- ✅ Foydalanuvchi qidirish

### Admin buyruqlari:
```
/admin          - Admin panel
/stats          - Batafsil statistika
/broadcast      - Xabar yuborish
/grant [id] [days] - Premium berish
/block [id]     - Bloklash
/unblock [id]   - Blokdan chiqarish
/user [id]      - Foydalanuvchi ma'lumoti
```

---

## 📝 Savol Qo'shish

### 1-usul: Admin panel orqali
1. `/admin` buyrug'i
2. "❓ Savollar" tugmasi
3. "➕ Savol qo'shish"
4. Til → Daraja → Kun tanlash
5. Savol va variantlarni kiritish

### 2-usul: Excel import
1. Excel fayl tayyorlang:
   - question (Savol)
   - correct (To'g'ri javob)
   - wrong1, wrong2, wrong3 (Xato variantlar)
   - explanation (Tushuntirish)
2. Faylni botga yuboring
3. `/import [day_id]` buyrug'i

### 3-usul: seed.py orqali
`seed.py` faylini tahrirlang va savollar qo'shing.

---

## 💰 Daromad Tizimi

### Premium obuna:
| Reja | Narx | Muddat |
|------|------|--------|
| Oylik | 100 ⭐ | 30 kun |
| Yillik | 600 ⭐ | 365 kun |
| Lifetime | 5000 ⭐ | Umrbod |

### Do'kon mahsulotlari:
| Mahsulot | Narx |
|----------|------|
| 2x XP Boost | 10 ⭐ |
| Streak Freeze | 20 ⭐ |
| 5 ta Hint | 15 ⭐ |
| Audio Pack | 100 ⭐ |

---

## 📂 Fayl Tuzilishi

```
quiz_bot_pro/
├── src/
│   ├── handlers/
│   │   ├── admin/      # Admin panel
│   │   ├── quiz/       # Quiz handler
│   │   ├── flashcard/  # Flashcard
│   │   ├── duel/       # Duel
│   │   ├── tournament/ # Turnir
│   │   ├── shop/       # Do'kon
│   │   └── payment/    # To'lov
│   ├── services/       # Biznes logika
│   ├── repositories/   # Database
│   └── core/           # Config, logging
├── seed.py             # Savollar yuklash
├── start.py            # Bot ishga tushirish
└── .env                # Sozlamalar
```

---

## ❓ Savollar

### Telegram Premium kerakmi?
**Yo'q!** Bot barcha foydalanuvchilar uchun ishlaydi.

### To'lov qanday ishlaydi?
Telegram Stars orqali. Foydalanuvchi Stars sotib oladi va bot ichida sarflaydi.

### Admin qanday qo'shiladi?
`.env` faylidagi `ADMIN_IDS` ga ID qo'shing:
```env
ADMIN_IDS=[123456789,987654321]
```

---

## 📞 Yordam

Muammo bo'lsa: @Printline_admin

---

© 2024 Quiz Bot Pro
