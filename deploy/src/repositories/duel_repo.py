"""
Duel Repository - Duel CRUD operations
"""
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy import select, update, and_, or_, desc
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Duel, DuelStats, DuelStatus
from src.repositories.base import BaseRepository


class DuelRepository(BaseRepository):
    """Duel repository"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, Duel)
    
    async def create_duel(
        self,
        challenger_id: int,
        language_id: Optional[int] = None,
        level_id: Optional[int] = None,
        questions_count: int = 5,
        time_per_question: int = 10,
        stake_stars: int = 0
    ) -> Duel:
        """Yangi duel yaratish"""
        duel = Duel(
            challenger_id=challenger_id,
            language_id=language_id,
            level_id=level_id,
            questions_count=questions_count,
            time_per_question=time_per_question,
            stake_stars=stake_stars,
            status=DuelStatus.PENDING,
            challenge_expires_at=datetime.utcnow() + timedelta(minutes=5)
        )
        self.session.add(duel)
        await self.session.commit()
        await self.session.refresh(duel)
        return duel
    
    async def get_by_id(self, duel_id: int) -> Optional[Duel]:
        """ID bo'yicha duel olish"""
        result = await self.session.execute(
            select(Duel).where(Duel.id == duel_id)
        )
        return result.scalar_one_or_none()
    
    async def get_pending_duel(self, challenger_id: int) -> Optional[Duel]:
        """Foydalanuvchining kutayotgan duelini olish"""
        result = await self.session.execute(
            select(Duel).where(
                and_(
                    Duel.challenger_id == challenger_id,
                    Duel.status == DuelStatus.PENDING,
                    Duel.challenge_expires_at > datetime.utcnow()
                )
            )
        )
        return result.scalar_one_or_none()
    
    async def find_waiting_opponent(self, user_id: int) -> Optional[Duel]:
        """Raqib kutayotgan duelni topish (o'zimizdan boshqa)"""
        result = await self.session.execute(
            select(Duel).where(
                and_(
                    Duel.challenger_id != user_id,
                    Duel.opponent_id.is_(None),
                    Duel.status == DuelStatus.PENDING,
                    Duel.challenge_expires_at > datetime.utcnow()
                )
            ).order_by(Duel.created_at.asc()).limit(1)
        )
        return result.scalar_one_or_none()
    
    async def accept_duel(self, duel_id: int, opponent_id: int) -> Optional[Duel]:
        """Duelni qabul qilish - race condition himoyasi bilan

        SELECT FOR UPDATE orqali row lock qo'yiladi,
        ikki kishi bir vaqtda qabul qilishini oldini oladi.
        """
        # SELECT FOR UPDATE - row'ni lock qilish
        result = await self.session.execute(
            select(Duel)
            .where(
                and_(
                    Duel.id == duel_id,
                    Duel.status == DuelStatus.PENDING,
                    Duel.opponent_id.is_(None)  # Hali qabul qilinmagan
                )
            )
            .with_for_update(nowait=True)  # Lock yoki xato
        )
        duel = result.scalar_one_or_none()

        if not duel:
            return None

        duel.accept(opponent_id)
        await self.session.commit()
        await self.session.refresh(duel)
        return duel
    
    async def decline_duel(self, duel_id: int) -> Optional[Duel]:
        """Duelni rad etish"""
        duel = await self.get_by_id(duel_id)
        if not duel or duel.status != DuelStatus.PENDING:
            return None
        
        duel.decline()
        await self.session.commit()
        return duel
    
    async def update_challenger_result(
        self,
        duel_id: int,
        score: float,
        correct: int,
        time_taken: float
    ) -> Optional[Duel]:
        """Challenger natijasini yangilash - race condition himoyasi bilan"""
        # SELECT FOR UPDATE - atomik yangilash uchun
        result = await self.session.execute(
            select(Duel)
            .where(Duel.id == duel_id)
            .with_for_update()
        )
        duel = result.scalar_one_or_none()
        if not duel:
            return None

        duel.challenger_score = score
        duel.challenger_correct = correct
        duel.challenger_time = time_taken
        duel.challenger_completed = True

        if duel.opponent_completed:
            duel.complete()

        await self.session.commit()
        await self.session.refresh(duel)
        return duel
    
    async def update_opponent_result(
        self,
        duel_id: int,
        score: float,
        correct: int,
        time_taken: float
    ) -> Optional[Duel]:
        """Opponent natijasini yangilash - race condition himoyasi bilan"""
        # SELECT FOR UPDATE - atomik yangilash uchun
        result = await self.session.execute(
            select(Duel)
            .where(Duel.id == duel_id)
            .with_for_update()
        )
        duel = result.scalar_one_or_none()
        if not duel:
            return None

        duel.opponent_score = score
        duel.opponent_correct = correct
        duel.opponent_time = time_taken
        duel.opponent_completed = True

        if duel.challenger_completed:
            duel.complete()

        await self.session.commit()
        await self.session.refresh(duel)
        return duel
    
    async def set_question_ids(self, duel_id: int, question_ids: List[int]) -> None:
        """Duel savollarini saqlash"""
        duel = await self.get_by_id(duel_id)
        if duel:
            duel.question_ids = ",".join(map(str, question_ids))
            await self.session.commit()
    
    async def get_question_ids(self, duel_id: int) -> List[int]:
        """Duel savollarini olish"""
        duel = await self.get_by_id(duel_id)
        if duel and duel.question_ids:
            return [int(x) for x in duel.question_ids.split(",")]
        return []
    
    async def get_user_active_duel(self, user_id: int) -> Optional[Duel]:
        """Foydalanuvchining faol duelini olish"""
        result = await self.session.execute(
            select(Duel).where(
                and_(
                    or_(
                        Duel.challenger_id == user_id,
                        Duel.opponent_id == user_id
                    ),
                    Duel.status == DuelStatus.ACTIVE
                )
            )
        )
        return result.scalar_one_or_none()
    
    async def get_user_duels(
        self,
        user_id: int,
        limit: int = 10,
        offset: int = 0
    ) -> List[Duel]:
        """Foydalanuvchi duellari tarixi"""
        result = await self.session.execute(
            select(Duel).where(
                or_(
                    Duel.challenger_id == user_id,
                    Duel.opponent_id == user_id
                )
            ).order_by(desc(Duel.created_at)).limit(limit).offset(offset)
        )
        return list(result.scalars().all())
    
    async def expire_old_duels(self) -> int:
        """Eski duellarni expire qilish"""
        result = await self.session.execute(
            update(Duel)
            .where(
                and_(
                    Duel.status == DuelStatus.PENDING,
                    Duel.challenge_expires_at < datetime.utcnow()
                )
            )
            .values(status=DuelStatus.EXPIRED)
        )
        await self.session.commit()
        return result.rowcount


class DuelStatsRepository(BaseRepository):
    """Duel statistikasi repository"""
    model = DuelStats
    
    def __init__(self, session: AsyncSession):
        super().__init__(session)
    
    async def get_or_create(self, user_id: int) -> DuelStats:
        """Statistikani olish yoki yaratish"""
        result = await self.session.execute(
            select(DuelStats).where(DuelStats.user_id == user_id)
        )
        stats = result.scalar_one_or_none()
        
        if not stats:
            stats = DuelStats(user_id=user_id)
            self.session.add(stats)
            await self.session.commit()
            await self.session.refresh(stats)
        
        return stats
    
    async def record_duel_result(
        self,
        user_id: int,
        won: bool,
        is_draw: bool = False,
        stars_change: int = 0
    ) -> DuelStats:
        """Duel natijasini yozish"""
        stats = await self.get_or_create(user_id)
        
        if is_draw:
            stats.record_draw()
        elif won:
            stats.record_win(stars_change)
        else:
            stats.record_loss(stars_change)
        
        await self.session.commit()
        await self.session.refresh(stats)
        return stats
    
    async def get_top_players(self, limit: int = 10) -> List[DuelStats]:
        """Top o'yinchilar (reyting bo'yicha)"""
        result = await self.session.execute(
            select(DuelStats)
            .where(DuelStats.total_duels >= 5)
            .order_by(desc(DuelStats.rating))
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_user_rank(self, user_id: int) -> int:
        """Foydalanuvchi reytingdagi o'rni"""
        stats = await self.get_or_create(user_id)
        
        result = await self.session.execute(
            select(DuelStats)
            .where(DuelStats.rating > stats.rating)
        )
        higher_ranked = len(result.scalars().all())
        return higher_ranked + 1