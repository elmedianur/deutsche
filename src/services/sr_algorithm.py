"""
Spaced Repetition Algorithm Service
SM-2 va Anki algoritmlarini qo'llab-quvvatlaydi
"""
from datetime import date, timedelta
from typing import Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum


class Algorithm(str, Enum):
    SM2 = "sm2"
    ANKI = "anki"


class Quality(int, Enum):
    """Javob sifati (4 ta tugma uchun)"""
    AGAIN = 0      # ❌ Bilmadim - qayta o'rganish
    HARD = 3       # 🤔 Qiyin - qiyinchilik bilan esladim
    GOOD = 4       # ✅ Bildim - to'g'ri javob
    EASY = 5       # 💯 Oson - juda oson


@dataclass
class ReviewResult:
    """Takrorlash natijasi"""
    interval: int           # Keyingi takrorlash intervali (kun)
    easiness: float         # Yangi easiness factor
    repetitions: int        # Takrorlashlar soni
    next_review: date       # Keyingi takrorlash sanasi
    is_graduated: bool      # O'rganish bosqichidan chiqdimi
    is_suspended: bool      # Arxivga tushdimi (180+ kun)


class SM2Algorithm:
    """
    SM-2 (SuperMemo 2) algoritmi

    Intervallar:
    - 1-muvaffaqiyat: 1 kun
    - 2-muvaffaqiyat: 6 kun
    - Keyingi: interval * easiness_factor

    Easiness factor: 1.3 - 2.5 oralig'ida
    """

    MIN_EASINESS = 1.3
    MAX_EASINESS = 2.5
    INITIAL_EASINESS = 2.5
    FIRST_INTERVAL = 1
    SECOND_INTERVAL = 6
    SUSPEND_THRESHOLD = 180  # 180+ kun = arxiv

    @classmethod
    def calculate(
        cls,
        quality: int,
        current_interval: int,
        current_easiness: float,
        current_repetitions: int
    ) -> ReviewResult:
        """
        SM-2 algoritmi bilan keyingi takrorlashni hisoblash

        Args:
            quality: 0-5 (0=bilmadim, 5=juda oson)
            current_interval: Hozirgi interval (kun)
            current_easiness: Hozirgi easiness factor
            current_repetitions: Takrorlashlar soni

        Returns:
            ReviewResult
        """
        if quality < 3:
            # Noto'g'ri javob - qaytadan boshlash
            new_interval = 1
            new_repetitions = 0
        else:
            # To'g'ri javob
            if current_repetitions == 0:
                new_interval = cls.FIRST_INTERVAL
            elif current_repetitions == 1:
                new_interval = cls.SECOND_INTERVAL
            else:
                new_interval = int(current_interval * current_easiness)

            new_repetitions = current_repetitions + 1

        # Easiness factor yangilash
        new_easiness = current_easiness + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        new_easiness = max(cls.MIN_EASINESS, min(cls.MAX_EASINESS, new_easiness))

        # Arxivga tushish tekshiruvi
        is_suspended = new_interval >= cls.SUSPEND_THRESHOLD

        return ReviewResult(
            interval=new_interval,
            easiness=new_easiness,
            repetitions=new_repetitions,
            next_review=date.today() + timedelta(days=new_interval),
            is_graduated=new_repetitions >= 2,
            is_suspended=is_suspended
        )


class AnkiAlgorithm:
    """
    Anki algoritmi (Modified SM-2) - Moslashuvchan o'rganish

    Asosiy farqlar:
    - Again bosilganda so'z DARHOL qayta chiqadi (shu sessiyada)
    - Lapse (xato) qilgan so'zlar tez-tez takrorlanadi
    - Easy bonus katta (1.3x)
    - Easiness tezroq o'zgaradi

    Intervallar:
    - Again: 0 kun (shu kun qayta) + lapse_count oshadi
    - Hard: interval * 1.2 (sekin o'sish)
    - Good: interval * ease
    - Easy: interval * ease * 1.3
    """

    MIN_EASINESS = 1.3
    MAX_EASINESS = 3.0
    INITIAL_EASINESS = 2.5

    # Interval multipliers
    HARD_MULTIPLIER = 1.2    # Qiyin - sekin o'sish
    EASY_BONUS = 1.3         # Oson bonus

    # Graduating intervals
    GRADUATING_INTERVAL = 1   # Birinchi muvaffaqiyat (kun)
    EASY_INTERVAL = 4         # Easy bosilsa darhol (kun)

    # Lapse (xato) sozlamalari
    LAPSE_NEW_INTERVAL = 0    # Xato qilganda interval (0 = shu kun)
    LAPSE_MIN_INTERVAL = 1    # Relearning dan keyin minimal interval

    # Limits
    MAX_INTERVAL = 36500      # 100 yil
    SUSPEND_THRESHOLD = 180   # 180+ kun = arxiv

    @classmethod
    def calculate(
        cls,
        quality: int,
        current_interval: int,
        current_easiness: float,
        current_repetitions: int,
        is_learning: bool = False,
        lapse_count: int = 0
    ) -> ReviewResult:
        """
        Anki algoritmi bilan keyingi takrorlashni hisoblash

        Moslashuvchan xususiyatlar:
        - Again: darhol qayta ko'rsatish (interval=0)
        - Ko'p xato = easiness tezroq pasayadi
        - Interval o'sishi easiness ga bog'liq
        """
        if quality == Quality.AGAIN:
            # ❌ Bilmadim - DARHOL qayta chiqadi
            new_interval = cls.LAPSE_NEW_INTERVAL  # 0 = shu kun
            new_repetitions = 0
            is_graduated = False

            # Easiness kuchli pasayadi (ko'p xato = ko'proq pasayadi)
            penalty = 0.2 + (lapse_count * 0.05)  # Har xato uchun qo'shimcha jazo
            new_easiness = max(cls.MIN_EASINESS, current_easiness - penalty)

        elif quality == Quality.HARD:
            # 🤔 Qiyin - sekin o'sish
            if current_repetitions == 0:
                new_interval = 1
            else:
                new_interval = max(1, int(current_interval * cls.HARD_MULTIPLIER))

            new_repetitions = current_repetitions + 1
            is_graduated = new_repetitions >= 1

            # Easiness biroz pasayadi
            new_easiness = max(cls.MIN_EASINESS, current_easiness - 0.15)

        elif quality == Quality.GOOD:
            # ✅ Bildim - normal o'sish
            if current_repetitions == 0:
                new_interval = cls.GRADUATING_INTERVAL
            elif current_repetitions == 1:
                new_interval = 3  # 1 -> 3 kun
            else:
                new_interval = int(current_interval * current_easiness)

            new_repetitions = current_repetitions + 1
            is_graduated = True
            new_easiness = current_easiness

        else:  # Quality.EASY
            # 💯 Oson - tez o'sish
            if current_repetitions == 0:
                new_interval = cls.EASY_INTERVAL
            else:
                new_interval = int(current_interval * current_easiness * cls.EASY_BONUS)

            new_repetitions = current_repetitions + 1
            is_graduated = True

            # Easiness oshadi
            new_easiness = min(cls.MAX_EASINESS, current_easiness + 0.15)

        # Maximum interval cheklash
        new_interval = min(new_interval, cls.MAX_INTERVAL)

        # Arxivga tushish tekshiruvi
        is_suspended = new_interval >= cls.SUSPEND_THRESHOLD

        return ReviewResult(
            interval=new_interval,
            easiness=new_easiness,
            repetitions=new_repetitions,
            next_review=date.today() + timedelta(days=new_interval),
            is_graduated=is_graduated,
            is_suspended=is_suspended
        )


class SpacedRepetitionService:
    """
    Spaced Repetition xizmati
    Foydalanuvchi tanlagan algoritmga qarab hisoblash
    """

    @staticmethod
    def calculate_next_review(
        algorithm: str,
        quality: int,
        current_interval: int,
        current_easiness: float,
        current_repetitions: int,
        is_learning: bool = False
    ) -> ReviewResult:
        """
        Keyingi takrorlashni hisoblash

        Args:
            algorithm: "sm2" yoki "anki"
            quality: 0, 3, 4, 5
            current_interval: Hozirgi interval
            current_easiness: Hozirgi easiness
            current_repetitions: Takrorlashlar soni
            is_learning: O'rganish bosqichidami

        Returns:
            ReviewResult
        """
        if algorithm == Algorithm.ANKI:
            return AnkiAlgorithm.calculate(
                quality=quality,
                current_interval=current_interval,
                current_easiness=current_easiness,
                current_repetitions=current_repetitions,
                is_learning=is_learning
            )
        else:  # Default: SM-2
            return SM2Algorithm.calculate(
                quality=quality,
                current_interval=current_interval,
                current_easiness=current_easiness,
                current_repetitions=current_repetitions
            )

    @staticmethod
    def get_initial_values(algorithm: str, quality: int) -> Tuple[int, float, int]:
        """
        Yangi so'z uchun boshlang'ich qiymatlar

        Args:
            algorithm: "sm2" yoki "anki"
            quality: Birinchi baholash (3, 4, 5)

        Returns:
            (interval, easiness, repetitions)
        """
        if algorithm == Algorithm.ANKI:
            if quality == Quality.EASY:
                return (AnkiAlgorithm.EASY_INTERVAL, 2.6, 1)
            elif quality == Quality.GOOD:
                return (AnkiAlgorithm.GRADUATING_INTERVAL, 2.5, 1)
            else:  # HARD
                return (1, 2.3, 0)
        else:  # SM-2
            if quality == Quality.EASY:
                return (4, 2.6, 2)
            elif quality == Quality.GOOD:
                return (1, 2.5, 1)
            else:  # HARD
                return (1, 2.3, 0)

    @staticmethod
    def get_algorithm_info(algorithm: str) -> Dict[str, Any]:
        """
        Algoritm haqida ma'lumot

        Returns:
            {name, description, intervals}
        """
        if algorithm == Algorithm.ANKI:
            return {
                "name": "Anki",
                "description": "Anki moslashuvchan algoritmi",
                "intervals": {
                    "again": "🔄 Darhol qayta (shu sessiyada)",
                    "hard": "interval × 1.2 (sekin)",
                    "good": "interval × ease",
                    "easy": "interval × ease × 1.3 (tez)"
                },
                "features": [
                    "❌ Xato = darhol qayta chiqadi",
                    "📈 Moslashuvchan o'rganish",
                    "🎯 Ko'p xato = ko'p takror",
                    "⚡ 7 takrorlashda arxivga"
                ]
            }
        else:
            return {
                "name": "SM-2",
                "description": "SuperMemo 2 algoritmi (klassik)",
                "intervals": {
                    "1-muvaffaqiyat": "1 kun",
                    "2-muvaffaqiyat": "6 kun",
                    "keyingi": "interval × easiness"
                },
                "features": [
                    "Klassik spaced repetition",
                    "Barqaror interval o'sishi",
                    "1.3-2.5 easiness diapazoni"
                ]
            }


# Interval taqqoslash jadvali
ALGORITHM_COMPARISON = """
┌─────────────┬──────────────────┬──────────────────┐
│ Takrorlash  │      SM-2        │      Anki        │
├─────────────┼──────────────────┼──────────────────┤
│ 1           │ 1 kun            │ 1 kun            │
│ 2           │ 6 kun            │ 3 kun            │
│ 3           │ ~15 kun          │ ~8 kun           │
│ 4           │ ~38 kun          │ ~20 kun          │
│ 5           │ ~95 kun          │ ~50 kun          │
│ 6           │ Arxiv ✓          │ ~125 kun         │
│ 7           │ -                │ Arxiv ✓          │
└─────────────┴──────────────────┴──────────────────┘

📌 Arxiv qoidasi: Interval 180+ kunga yetganda so'z arxivga tushadi
📌 SM-2: 5 ta muvaffaqiyatli takrorlashdan keyin arxivga (interval 180+)
📌 Anki: 6 ta muvaffaqiyatli takrorlashdan keyin arxivga (interval 180+)

❌ Xato qilganda farq:
• SM-2: 1 kun kutish, qaytadan boshlash
• Anki: DARHOL qayta chiqadi + tez-tez takrorlanadi
"""
