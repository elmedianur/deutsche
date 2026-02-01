"""
CSV Import Script - SQLite version

CSV formatidan ma'lumotlarni import qiladi:
- Questions jadvaliga savolni qo'shadi

CSV format:
savol,javob,izoh,variant_a,variant_b,variant_c,variant_d,togri_javob,daraja,kun,gender,turi,audio_url

Ishlatish:
  python import_csv_sqlite.py                    # default: data/import.csv
  python import_csv_sqlite.py yangi_sozlar.csv   # maxsus fayl
"""
import csv
import sqlite3
import sys
from datetime import datetime

# Database path
DB_PATH = "/root/quiz_bot/quiz_bot.db"

# CSV file (argument or default)
CSV_FILE = sys.argv[1] if len(sys.argv) > 1 else "/root/quiz_bot/data/import.csv"


def get_or_create_day(cursor, level_id, day_number):
    """Day ID ni olish yoki yaratish"""
    # First get language_id from level
    cursor.execute("SELECT language_id FROM levels WHERE id = ?", (level_id,))
    row = cursor.fetchone()
    if not row:
        # Create default level if not exists
        cursor.execute("""
            INSERT INTO levels (language_id, name, order_num, time_per_question, is_active, sort_order)
            VALUES (1, ?, ?, 30, 1, ?)
        """, (f"Level {level_id}", level_id, level_id))
        language_id = 1
        level_id = cursor.lastrowid
    else:
        language_id = row[0]

    # Check if day exists
    cursor.execute("""
        SELECT id FROM days
        WHERE level_id = ? AND day_number = ?
        LIMIT 1
    """, (level_id, day_number))
    row = cursor.fetchone()

    if row:
        return row[0]

    # Create new day
    cursor.execute("""
        INSERT INTO days (level_id, day_number, name, is_active, created_at)
        VALUES (?, ?, ?, 1, ?)
    """, (level_id, day_number, f"{day_number}-kun", datetime.now()))

    return cursor.lastrowid


def import_csv():
    print("=" * 60)
    print("CSV IMPORT - SQLite")
    print("=" * 60)
    print(f"Database: {DB_PATH}")
    print(f"CSV fayl: {CSV_FILE}")

    # Read CSV
    try:
        with open(CSV_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except FileNotFoundError:
        print(f"XATO: {CSV_FILE} fayl topilmadi!")
        return
    except Exception as e:
        print(f"XATO: CSV o'qishda xatolik: {e}")
        return

    print(f"Topilgan qatorlar: {len(rows)}")

    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Stats
    stats = {
        "questions_added": 0,
        "questions_exists": 0,
        "errors": 0
    }

    for i, row in enumerate(rows, 1):
        try:
            # Get CSV columns
            savol = row.get('savol', '').strip()
            javob = row.get('javob', '').strip()
            izoh = row.get('izoh', '').strip()
            variant_a = row.get('variant_a', '').strip()
            variant_b = row.get('variant_b', '').strip()
            variant_c = row.get('variant_c', '').strip()
            variant_d = row.get('variant_d', '').strip()
            togri_javob = row.get('togri_javob', 'A').strip().upper()
            daraja = int(row.get('daraja', 1) or 1)
            kun = int(row.get('kun', 1) or 1)
            # gender and turi are ignored for this simple version
            # audio_url is also not used in this db schema

            if not savol:
                print(f"  [{i}] SKIP: Bo'sh savol")
                continue

            # Get or create day
            day_id = get_or_create_day(cursor, daraja, kun)

            # Check if question already exists
            cursor.execute("""
                SELECT id FROM questions
                WHERE question_text = ? AND day_id = ?
                LIMIT 1
            """, (savol, day_id))

            if cursor.fetchone():
                stats["questions_exists"] += 1
                continue

            # Insert question
            cursor.execute("""
                INSERT INTO questions
                (day_id, question_text, option_a, option_b, option_c, option_d,
                 correct_option, explanation, is_active, created_at, difficulty)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 1)
            """, (
                day_id, savol, variant_a, variant_b, variant_c, variant_d,
                togri_javob, izoh, datetime.now()
            ))

            stats["questions_added"] += 1

            # Commit every 100 rows
            if i % 100 == 0:
                conn.commit()
                print(f"  [{i}/{len(rows)}] Jarayonda...")

        except Exception as e:
            print(f"  [{i}] XATO: {e}")
            stats["errors"] += 1
            continue

    # Final commit
    conn.commit()

    # Results
    print("\n" + "=" * 60)
    print("IMPORT YAKUNLANDI!")
    print("=" * 60)
    print(f"  Yangi savollar qo'shildi: {stats['questions_added']}")
    print(f"  Mavjud savollar (skip): {stats['questions_exists']}")
    print(f"  Xatolar: {stats['errors']}")

    # Total stats
    print("\n" + "-" * 60)
    print("UMUMIY BAZADAGI MA'LUMOTLAR:")

    cursor.execute("SELECT COUNT(*) FROM questions")
    print(f"  Jami savollar: {cursor.fetchone()[0]}")

    cursor.execute("SELECT COUNT(*) FROM days")
    print(f"  Jami kunlar: {cursor.fetchone()[0]}")

    cursor.execute("SELECT COUNT(*) FROM levels")
    print(f"  Jami darajalar: {cursor.fetchone()[0]}")

    conn.close()


if __name__ == "__main__":
    import_csv()
