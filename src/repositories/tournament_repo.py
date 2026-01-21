"""
Tournament Repository - Tournament CRUD operations
"""
from datetime import datetime
from typing import Optional, List, Tuple
from sqlalchemy import select, update, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Tournament, TournamentParticipant, TournamentStatus
from src.repositories.base import BaseRepository


class TournamentRepository(BaseRepository):
    model = Tournament
    """Tournament repository"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session)
    
    async def create_tournament(
        self,
        name: str,
        tournament_type: str,
        registration_start: datetime,
        registration_end: datetime,
        start_time: datetime,
        end_time: datetime,
        **kwargs
    ) -> Tournament:
        """Yangi turnir yaratish"""
        tournament = Tournament(
            name=name,
            tournament_type=tournament_type,
            registration_start=registration_start,
            registration_end=registration_end,
            start_time=start_time,
            end_time=end_time,
            status=TournamentStatus.UPCOMING,
            **kwargs
        )
        self.session.add(tournament)
        await self.session.commit()
        await self.session.refresh(tournament)
        return tournament
    
    async def get_by_id(self, tournament_id: int) -> Optional[Tournament]:
        """ID bo'yicha turnir olish"""
        result = await self.session.execute(
            select(Tournament).where(Tournament.id == tournament_id)
        )
        return result.scalar_one_or_none()
    
    async def get_active_tournament(self) -> Optional[Tournament]:
        """Faol turnirni olish"""
        result = await self.session.execute(
            select(Tournament).where(
                Tournament.status == TournamentStatus.ACTIVE
            ).order_by(desc(Tournament.start_time)).limit(1)
        )
        return result.scalar_one_or_none()
    
    async def get_current_tournament(self) -> Optional[Tournament]:
        """Joriy turnirni olish (faol yoki ro'yxatga olish)"""
        now = datetime.utcnow()
        
        # Avval faol turnirni qidirish
        result = await self.session.execute(
            select(Tournament).where(
                and_(
                    Tournament.status.in_([
                        TournamentStatus.ACTIVE,
                        TournamentStatus.REGISTRATION
                    ]),
                    Tournament.end_time > now
                )
            ).order_by(Tournament.start_time.asc()).limit(1)
        )
        tournament = result.scalar_one_or_none()
        
        if tournament:
            return tournament
        
        # Yaqinlashayotgan turnirni qidirish
        result = await self.session.execute(
            select(Tournament).where(
                and_(
                    Tournament.status == TournamentStatus.UPCOMING,
                    Tournament.start_time > now
                )
            ).order_by(Tournament.start_time.asc()).limit(1)
        )
        return result.scalar_one_or_none()
    
    async def get_upcoming_tournaments(self, limit: int = 5) -> List[Tournament]:
        """Kelayotgan turnirlar"""
        result = await self.session.execute(
            select(Tournament).where(
                Tournament.status == TournamentStatus.UPCOMING
            ).order_by(Tournament.start_time.asc()).limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_completed_tournaments(self, limit: int = 10) -> List[Tournament]:
        """Tugallangan turnirlar"""
        result = await self.session.execute(
            select(Tournament).where(
                Tournament.status == TournamentStatus.COMPLETED
            ).order_by(desc(Tournament.end_time)).limit(limit)
        )
        return list(result.scalars().all())
    
    async def update_status(
        self,
        tournament_id: int,
        status: TournamentStatus
    ) -> Optional[Tournament]:
        """Turnir holatini yangilash"""
        tournament = await self.get_by_id(tournament_id)
        if tournament:
            tournament.status = status
            await self.session.commit()
            await self.session.refresh(tournament)
        return tournament
    
    async def set_winner(self, tournament_id: int, winner_id: int) -> None:
        """G'olibni belgilash"""
        tournament = await self.get_by_id(tournament_id)
        if tournament:
            tournament.winner_id = winner_id
            await self.session.commit()
    
    async def increment_participants(self, tournament_id: int) -> None:
        """Ishtirokchilar sonini oshirish"""
        await self.session.execute(
            update(Tournament)
            .where(Tournament.id == tournament_id)
            .values(participants_count=Tournament.participants_count + 1)
        )
        await self.session.commit()


class TournamentParticipantRepository(BaseRepository):
    model = TournamentParticipant
    """Tournament participant repository"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session)
    
    async def register_participant(
        self,
        tournament_id: int,
        user_id: int
    ) -> TournamentParticipant:
        """Ishtirokchini ro'yxatga olish"""
        participant = TournamentParticipant(
            tournament_id=tournament_id,
            user_id=user_id,
            registered_at=datetime.utcnow()
        )
        self.session.add(participant)
        await self.session.commit()
        await self.session.refresh(participant)
        return participant
    
    async def get_participant(
        self,
        tournament_id: int,
        user_id: int
    ) -> Optional[TournamentParticipant]:
        """Ishtirokchini olish"""
        result = await self.session.execute(
            select(TournamentParticipant).where(
                and_(
                    TournamentParticipant.tournament_id == tournament_id,
                    TournamentParticipant.user_id == user_id
                )
            )
        )
        return result.scalar_one_or_none()
    
    async def get_or_register(
        self,
        tournament_id: int,
        user_id: int
    ) -> Tuple[TournamentParticipant, bool]:
        """Ishtirokchini olish yoki ro'yxatga olish"""
        participant = await self.get_participant(tournament_id, user_id)
        
        if participant:
            return participant, False
        
        participant = await self.register_participant(tournament_id, user_id)
        return participant, True
    
    async def update_score(
        self,
        tournament_id: int,
        user_id: int,
        correct: int,
        total: int,
        time_taken: float
    ) -> Optional[TournamentParticipant]:
        """Ishtirokchi natijasini yangilash"""
        participant = await self.get_participant(tournament_id, user_id)
        
        if not participant:
            return None
        
        # Yangi natijalarni qo'shish
        participant.correct_answers += correct
        participant.total_questions += total
        participant.total_time += time_taken
        
        # Ball hisoblash: to'g'ri javob * 10 + tezlik bonusi
        base_score = correct * 10
        
        # 100% natija uchun bonus
        perfect_bonus = 20 if correct == total and total >= 5 else 0
        
        participant.score += base_score + perfect_bonus
        
        # O'rtacha vaqt
        if participant.total_questions > 0:
            participant.avg_time = participant.total_time / participant.total_questions
        
        participant.last_played_at = datetime.utcnow()
        
        await self.session.commit()
        await self.session.refresh(participant)
        return participant
    
    async def get_leaderboard(
        self,
        tournament_id: int,
        limit: int = 20,
        offset: int = 0
    ) -> List[TournamentParticipant]:
        """Reyting jadvali"""
        result = await self.session.execute(
            select(TournamentParticipant).where(
                TournamentParticipant.tournament_id == tournament_id
            ).order_by(
                desc(TournamentParticipant.score),
                TournamentParticipant.avg_time.asc()
            ).limit(limit).offset(offset)
        )
        return list(result.scalars().all())
    
    async def get_user_rank(
        self,
        tournament_id: int,
        user_id: int
    ) -> int:
        """Foydalanuvchi o'rni"""
        participant = await self.get_participant(tournament_id, user_id)
        
        if not participant:
            return 0
        
        # O'zidan yuqori ballga ega ishtirokchilar soni
        result = await self.session.execute(
            select(func.count(TournamentParticipant.id)).where(
                and_(
                    TournamentParticipant.tournament_id == tournament_id,
                    TournamentParticipant.score > participant.score
                )
            )
        )
        higher_count = result.scalar() or 0
        return higher_count + 1
    
    async def get_top_3(
        self,
        tournament_id: int
    ) -> List[TournamentParticipant]:
        """Top 3 ishtirokchi"""
        return await self.get_leaderboard(tournament_id, limit=3)
    
    async def get_participants_count(self, tournament_id: int) -> int:
        """Ishtirokchilar soni"""
        result = await self.session.execute(
            select(func.count(TournamentParticipant.id)).where(
                TournamentParticipant.tournament_id == tournament_id
            )
        )
        return result.scalar() or 0
    
    async def update_ranks(self, tournament_id: int) -> None:
        """Barcha ishtirokchilar reytingini yangilash"""
        leaderboard = await self.get_leaderboard(tournament_id, limit=10000)
        
        for rank, participant in enumerate(leaderboard, 1):
            participant.final_rank = rank
        
        await self.session.commit()
    
    async def mark_completed(
        self,
        tournament_id: int,
        user_id: int
    ) -> Optional[TournamentParticipant]:
        """Ishtirokchini tugatgan deb belgilash"""
        participant = await self.get_participant(tournament_id, user_id)
        
        if participant:
            participant.is_completed = True
            participant.completed_at = datetime.utcnow()
            await self.session.commit()
            await self.session.refresh(participant)
        
        return participant
    
    async def give_prize(
        self,
        tournament_id: int,
        user_id: int,
        stars: int,
        premium_days: int
    ) -> Optional[TournamentParticipant]:
        """Sovrin berish"""
        participant = await self.get_participant(tournament_id, user_id)
        
        if participant:
            participant.prize_received = True
            participant.prize_stars = stars
            participant.prize_premium_days = premium_days
            await self.session.commit()
            await self.session.refresh(participant)
        
        return participant