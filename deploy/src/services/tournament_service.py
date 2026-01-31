"""
Tournament Service - Tournament business logic
"""
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from src.database import get_session
from src.database.models import Tournament, TournamentParticipant, TournamentStatus
from src.repositories.tournament_repo import TournamentRepository, TournamentParticipantRepository
from src.core.logging import get_logger

logger = get_logger(__name__)


class TournamentService:
    """Tournament business logic"""
    
    async def get_current_tournament(self) -> Optional[Dict[str, Any]]:
        """Joriy turnirni olish"""
        async with get_session() as session:
            repo = TournamentRepository(session)
            tournament = await repo.get_current_tournament()
            
            if not tournament:
                return None
            
            participant_repo = TournamentParticipantRepository(session)
            participants_count = await participant_repo.get_participants_count(tournament.id)
            
            return {
                "id": tournament.id,
                "name": tournament.name,
                "type": tournament.tournament_type,
                "status": tournament.status.value,
                "start_time": tournament.start_time,
                "end_time": tournament.end_time,
                "participants_count": participants_count,
                "is_active": tournament.is_active,
                "is_registration_open": tournament.is_registration_open,
                "time_remaining": self._format_time_remaining(tournament.end_time)
            }
    
    async def get_or_create_weekly_tournament(self) -> Tournament:
        """Haftalik turnirni olish yoki yaratish"""
        async with get_session() as session:
            repo = TournamentRepository(session)
            
            # Faol turnirni qidirish
            tournament = await repo.get_active_tournament()
            
            if tournament:
                return tournament
            
            # Yangi haftalik turnir yaratish
            now = datetime.utcnow()
            
            # Dushanba kunidan boshlanadi
            days_until_monday = (7 - now.weekday()) % 7
            if days_until_monday == 0 and now.hour >= 10:
                days_until_monday = 7
            
            start_time = (now + timedelta(days=days_until_monday)).replace(
                hour=10, minute=0, second=0, microsecond=0
            )
            end_time = start_time + timedelta(days=6, hours=23, minutes=59)
            
            tournament = await repo.create_tournament(
                name=f"Haftalik turnir #{int(now.timestamp())}",
                tournament_type="weekly",
                registration_start=now,
                registration_end=start_time,
                start_time=start_time,
                end_time=end_time,
                prize_1st_stars=500,
                prize_1st_premium_days=7,
                prize_2nd_stars=250,
                prize_2nd_premium_days=3,
                prize_3rd_stars=100,
                prize_3rd_premium_days=1
            )
            
            # Faol qilish
            tournament.status = TournamentStatus.ACTIVE
            await session.commit()
            
            logger.info(f"New weekly tournament created: {tournament.id}")
            return tournament
    
    async def register_participant(
        self,
        tournament_id: int,
        user_id: int,
        username: Optional[str] = None,
        full_name: str = "Foydalanuvchi"
    ) -> Dict[str, Any]:
        """Ishtirokchini ro'yxatga olish"""
        async with get_session() as session:
            repo = TournamentParticipantRepository(session)
            
            participant, is_new = await repo.get_or_register(tournament_id, user_id)
            
            if is_new:
                # Ishtirokchilar sonini oshirish
                tournament_repo = TournamentRepository(session)
                await tournament_repo.increment_participants(tournament_id)
            
            return {
                "success": True,
                "is_new": is_new,
                "participant_id": participant.id,
                "score": participant.score,
                "rank": await repo.get_user_rank(tournament_id, user_id)
            }
    
    async def add_quiz_score(
        self,
        user_id: int,
        correct: int,
        total: int,
        time_taken: float
    ) -> Optional[Dict[str, Any]]:
        """Quiz natijasini turnirga qo'shish"""
        async with get_session() as session:
            tournament_repo = TournamentRepository(session)
            tournament = await tournament_repo.get_active_tournament()
            
            if not tournament:
                return None
            
            participant_repo = TournamentParticipantRepository(session)
            
            # Avval ro'yxatga olish (agar yo'q bo'lsa)
            participant, _ = await participant_repo.get_or_register(
                tournament.id, user_id
            )
            
            # Natijani qo'shish
            participant = await participant_repo.update_score(
                tournament.id,
                user_id,
                correct,
                total,
                time_taken
            )
            
            if not participant:
                return None
            
            rank = await participant_repo.get_user_rank(tournament.id, user_id)
            
            return {
                "tournament_id": tournament.id,
                "tournament_name": tournament.name,
                "score_added": correct * 10 + (20 if correct == total else 0),
                "total_score": participant.score,
                "rank": rank
            }
    
    async def get_leaderboard(
        self,
        tournament_id: Optional[int] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Reyting jadvali"""
        async with get_session() as session:
            tournament_repo = TournamentRepository(session)
            
            if tournament_id:
                tournament = await tournament_repo.get_by_id(tournament_id)
            else:
                tournament = await tournament_repo.get_active_tournament()
            
            if not tournament:
                return []
            
            participant_repo = TournamentParticipantRepository(session)
            participants = await participant_repo.get_leaderboard(
                tournament.id, limit=limit
            )
            
            result = []
            for i, p in enumerate(participants, 1):
                result.append({
                    "rank": i,
                    "user_id": p.user_id,
                    "score": p.score,
                    "correct_answers": p.correct_answers,
                    "total_questions": p.total_questions,
                    "accuracy": p.accuracy
                })
            
            return result
    
    async def get_user_tournament_stats(
        self,
        user_id: int,
        tournament_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """Foydalanuvchi turnir statistikasi"""
        async with get_session() as session:
            tournament_repo = TournamentRepository(session)
            
            if tournament_id:
                tournament = await tournament_repo.get_by_id(tournament_id)
            else:
                tournament = await tournament_repo.get_active_tournament()
            
            if not tournament:
                return None
            
            participant_repo = TournamentParticipantRepository(session)
            participant = await participant_repo.get_participant(
                tournament.id, user_id
            )
            
            if not participant:
                return {
                    "registered": False,
                    "tournament_id": tournament.id,
                    "tournament_name": tournament.name
                }
            
            rank = await participant_repo.get_user_rank(tournament.id, user_id)
            total_participants = await participant_repo.get_participants_count(tournament.id)
            
            return {
                "registered": True,
                "tournament_id": tournament.id,
                "tournament_name": tournament.name,
                "score": participant.score,
                "rank": rank,
                "total_participants": total_participants,
                "correct_answers": participant.correct_answers,
                "total_questions": participant.total_questions,
                "accuracy": participant.accuracy
            }
    
    async def finish_tournament(self, tournament_id: int) -> Dict[str, Any]:
        """Turnirni tugatish va g'oliblarni aniqlash"""
        async with get_session() as session:
            tournament_repo = TournamentRepository(session)
            tournament = await tournament_repo.get_by_id(tournament_id)
            
            if not tournament:
                return {"success": False, "error": "Tournament not found"}
            
            participant_repo = TournamentParticipantRepository(session)
            
            # Reytinglarni yangilash
            await participant_repo.update_ranks(tournament_id)
            
            # Top 3 ni olish
            top_3 = await participant_repo.get_top_3(tournament_id)
            
            winners = []
            for i, participant in enumerate(top_3, 1):
                prize_info = tournament.get_prize_info(i)
                
                await participant_repo.give_prize(
                    tournament_id,
                    participant.user_id,
                    prize_info["stars"],
                    prize_info["premium_days"]
                )
                
                winners.append({
                    "rank": i,
                    "user_id": participant.user_id,
                    "score": participant.score,
                    "prize_stars": prize_info["stars"],
                    "prize_premium_days": prize_info["premium_days"]
                })
            
            # Turnirni tugatish
            await tournament_repo.update_status(tournament_id, TournamentStatus.COMPLETED)
            
            if top_3:
                await tournament_repo.set_winner(tournament_id, top_3[0].user_id)
            
            logger.info(f"Tournament {tournament_id} completed with {len(winners)} winners")
            
            return {
                "success": True,
                "tournament_id": tournament_id,
                "winners": winners
            }
    
    def _format_time_remaining(self, end_time: datetime) -> str:
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


# Standalone funksiya - TournamentService dan oldin
async def finish_expired_tournaments():
    """Tugagan turnirlarni yakunlash va g'oliblarni mukofotlash"""
    from datetime import datetime
    from src.database import get_session
    from src.database.models import Tournament, TournamentStatus
    from src.repositories.tournament_repo import TournamentRepository, TournamentParticipantRepository
    from src.repositories import SubscriptionRepository
    from sqlalchemy import select, and_
    
    try:
        async with get_session() as session:
            # Tugagan lekin yakunlanmagan turnirlarni topish
            result = await session.execute(
                select(Tournament).where(
                    and_(
                        Tournament.end_time < datetime.utcnow(),
                        Tournament.status == TournamentStatus.ACTIVE
                    )
                )
            )
            expired = result.scalars().all()
            
            finished_tournaments = []
            
            for tournament in expired:
                # G'oliblarni aniqlash
                participant_repo = TournamentParticipantRepository(session)
                winners = await participant_repo.get_top_participants(tournament.id, limit=3)
                
                # Mukofotlar
                prizes = [
                    {"premium_days": 7, "stars": 500},   # 1-o'rin
                    {"premium_days": 3, "stars": 250},   # 2-o'rin
                    {"premium_days": 1, "stars": 100},   # 3-o'rin
                ]
                
                sub_repo = SubscriptionRepository(session)
                
                for i, winner in enumerate(winners):
                    if i < len(prizes):
                        prize = prizes[i]
                        # Premium berish
                        await sub_repo.extend_premium(
                            winner.user_id, 
                            days=prize["premium_days"]
                        )
                        # TODO: Stars berish (wallet tizimi kerak)
                
                # Turnir statusini yangilash
                tournament.status = TournamentStatus.FINISHED
                finished_tournaments.append(tournament.name)
            
            await session.commit()
            return finished_tournaments if finished_tournaments else None
            
    except Exception as e:
        logger.error(f"Error finishing tournaments: {e}")
        return None


# Global instance
tournament_service = TournamentService()
