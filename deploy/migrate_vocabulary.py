"""
Migration script: Create vocabulary table and link existing data.

Bu skript:
1. vocabulary jadvalini yaratadi
2. Mavjud questions dan so'zlarni vocabulary ga qo'shadi
3. Mavjud flashcards dan so'zlarni vocabulary ga qo'shadi
4. questions va flashcards ni vocabulary_id bilan bog'laydi
"""
import asyncio
import sys
sys.path.insert(0, '/app')

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker


DATABASE_URL = "postgresql+asyncpg://postgres:quiz_secure_2024@postgres:5432/quiz_bot"


async def migrate():
    engine = create_async_engine(DATABASE_URL, echo=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        print("=" * 50)
        print("VOCABULARY MIGRATION")
        print("=" * 50)

        # 1. Create vocabulary table
        print("\n[1/5] Creating vocabulary table...")
        await session.execute(text("""
            CREATE TABLE IF NOT EXISTS vocabulary (
                id SERIAL PRIMARY KEY,
                word VARCHAR(500) NOT NULL,
                translation VARCHAR(500) NOT NULL,
                alt_translations TEXT,
                part_of_speech VARCHAR(50),
                gender VARCHAR(10),
                example_de TEXT,
                example_uz TEXT,
                pronunciation VARCHAR(200),
                audio_url VARCHAR(500),
                image_url VARCHAR(500),
                level_id INTEGER REFERENCES levels(id) ON DELETE SET NULL,
                day_id INTEGER REFERENCES days(id) ON DELETE SET NULL,
                difficulty INTEGER DEFAULT 3,
                frequency INTEGER DEFAULT 5,
                tags VARCHAR(500),
                times_shown INTEGER DEFAULT 0,
                times_correct INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))
        await session.execute(text("CREATE INDEX IF NOT EXISTS idx_vocabulary_word ON vocabulary(word)"))
        await session.execute(text("CREATE INDEX IF NOT EXISTS idx_vocabulary_level ON vocabulary(level_id)"))
        await session.execute(text("CREATE INDEX IF NOT EXISTS idx_vocabulary_day ON vocabulary(day_id)"))
        await session.commit()
        print("   Done!")

        # 2. Add vocabulary_id to questions
        print("\n[2/5] Adding vocabulary_id to questions...")
        try:
            await session.execute(text("""
                ALTER TABLE questions
                ADD COLUMN IF NOT EXISTS vocabulary_id INTEGER REFERENCES vocabulary(id) ON DELETE SET NULL
            """))
            await session.execute(text("CREATE INDEX IF NOT EXISTS idx_questions_vocabulary ON questions(vocabulary_id)"))
            await session.commit()
            print("   Done!")
        except Exception as e:
            print(f"   Already exists or error: {e}")
            await session.rollback()

        # 3. Add vocabulary_id to flashcards
        print("\n[3/5] Adding vocabulary_id to flashcards...")
        try:
            await session.execute(text("""
                ALTER TABLE flashcards
                ADD COLUMN IF NOT EXISTS vocabulary_id INTEGER REFERENCES vocabulary(id) ON DELETE SET NULL
            """))
            await session.execute(text("CREATE INDEX IF NOT EXISTS idx_flashcards_vocabulary ON flashcards(vocabulary_id)"))
            await session.commit()
            print("   Done!")
        except Exception as e:
            print(f"   Already exists or error: {e}")
            await session.rollback()

        # 4. Migrate data from questions
        print("\n[4/5] Migrating words from questions...")
        result = await session.execute(text("""
            SELECT DISTINCT
                q.question_text as word,
                COALESCE(
                    CASE
                        WHEN q.correct_option = 'A' THEN q.option_a
                        WHEN q.correct_option = 'B' THEN q.option_b
                        WHEN q.correct_option = 'C' THEN q.option_c
                        WHEN q.correct_option = 'D' THEN q.option_d
                    END,
                    q.option_a
                ) as translation,
                q.explanation as example_de,
                q.audio_url,
                q.image_url,
                d.level_id,
                q.day_id,
                q.difficulty
            FROM questions q
            LEFT JOIN days d ON q.day_id = d.id
            WHERE q.question_text IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM vocabulary v WHERE v.word = q.question_text
            )
        """))
        questions_data = result.fetchall()
        print(f"   Found {len(questions_data)} unique words from questions")

        for row in questions_data:
            await session.execute(text("""
                INSERT INTO vocabulary (word, translation, example_de, audio_url, image_url, level_id, day_id, difficulty)
                VALUES (:word, :translation, :example_de, :audio_url, :image_url, :level_id, :day_id, :difficulty)
                ON CONFLICT DO NOTHING
            """), {
                "word": row[0],
                "translation": row[1],
                "example_de": row[2],
                "audio_url": row[3],
                "image_url": row[4],
                "level_id": row[5],
                "day_id": row[6],
                "difficulty": row[7] or 3
            })
        await session.commit()
        print("   Done!")

        # 5. Migrate data from flashcards
        print("\n[5/5] Migrating words from flashcards...")
        result = await session.execute(text("""
            SELECT DISTINCT
                f.front_text as word,
                f.back_text as translation,
                f.example_sentence as example_de,
                f.front_audio_url as audio_url,
                f.front_image_url as image_url,
                fd.level_id,
                fd.day_id
            FROM flashcards f
            LEFT JOIN flashcard_decks fd ON f.deck_id = fd.id
            WHERE f.front_text IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM vocabulary v WHERE v.word = f.front_text
            )
        """))
        flashcards_data = result.fetchall()
        print(f"   Found {len(flashcards_data)} unique words from flashcards")

        for row in flashcards_data:
            await session.execute(text("""
                INSERT INTO vocabulary (word, translation, example_de, audio_url, image_url, level_id, day_id)
                VALUES (:word, :translation, :example_de, :audio_url, :image_url, :level_id, :day_id)
                ON CONFLICT DO NOTHING
            """), {
                "word": row[0],
                "translation": row[1],
                "example_de": row[2],
                "audio_url": row[3],
                "image_url": row[4],
                "level_id": row[5],
                "day_id": row[6]
            })
        await session.commit()
        print("   Done!")

        # 6. Link questions to vocabulary
        print("\n[6/6] Linking questions and flashcards to vocabulary...")
        await session.execute(text("""
            UPDATE questions q
            SET vocabulary_id = v.id
            FROM vocabulary v
            WHERE q.question_text = v.word
            AND q.vocabulary_id IS NULL
        """))

        await session.execute(text("""
            UPDATE flashcards f
            SET vocabulary_id = v.id
            FROM vocabulary v
            WHERE f.front_text = v.word
            AND f.vocabulary_id IS NULL
        """))
        await session.commit()
        print("   Done!")

        # Stats
        print("\n" + "=" * 50)
        print("MIGRATION COMPLETE!")
        print("=" * 50)

        result = await session.execute(text("SELECT COUNT(*) FROM vocabulary"))
        vocab_count = result.scalar()
        print(f"Total vocabulary entries: {vocab_count}")

        result = await session.execute(text("SELECT COUNT(*) FROM questions WHERE vocabulary_id IS NOT NULL"))
        linked_q = result.scalar()
        print(f"Questions linked: {linked_q}")

        result = await session.execute(text("SELECT COUNT(*) FROM flashcards WHERE vocabulary_id IS NOT NULL"))
        linked_f = result.scalar()
        print(f"Flashcards linked: {linked_f}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
