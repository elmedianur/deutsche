"""
Duel Service - Duel business logic
"""
from datetime import datetime
from typing import Optional, List, Dict, Any

from src.database import get_session
from src.database.models import Duel, DuelStats, DuelStatus
from src.repositories.duel_repo import DuelRepository, DuelStatsRepository
from src.repositories.question_repo import QuestionRepository
from src.core.logging import get_logger

logger = get_logger(__name__)


class DuelService:
    """Duel business logic"""
    
    async def create_duel(
        self,
        challenger_id: int,
        language_id: Optional[int] = None,
        level_id: Optional[int] = None,
        questions_count: int = 5
    ) -> Dict[str, Any]:
        """Yangi duel yaratish"""
        async with get_session() as session:
            repo = DuelRepository(session)
            
            # Foydalanuvchining faol dueli bormi?
            active_duel = await repo.get_user_active_duel(challenger_id)
            if active_duel:
                return {
                    "success": False,
                    "error": "Sizda faol duel mavjud",
                    "duel_id": active_duel.id
                }
            
            # Kutayotgan dueli bormi?
            pending_duel = await repo.get_pending_duel(challenger_id)
            if pending_duel:
                return {
                    "success": False,
                    "error": "Sizda kutayotgan duel mavjud",
                    "duel_id": pending_duel.id
                }
            
            # Yangi duel yaratish
            duel = await repo.create_duel(
                challenger_id=challenger_id,
                language_id=language_id,
                level_id=level_id,
                questions_count=questions_count
            )
            
            logger.info(f"Duel created: {duel.id} by user {challenger_id}")
            
            return {
                "success": True,
                "duel_id": duel.id,
                "status": duel.status.value
            }
    
    async def find_opponent(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Raqib qidirish"""
        async with get_session() as session:
            repo = DuelRepository(session)
            
            # Kutayotgan duelni topish
            duel = await repo.find_waiting_opponent(user_id)
            
            if duel:
                return {
                    "found": True,
                    "duel_id": duel.id,
                    "challenger_id": duel.challenger_id
                }
            
            return {"found": False}
    
    async def accept_duel(
        self,
        duel_id: int,
        opponent_id: int
    ) -> Dict[str, Any]:
        """Duelni qabul qilish"""
        async with get_session() as session:
            repo = DuelRepository(session)
            
            duel = await repo.accept_duel(duel_id, opponent_id)
            
            if not duel:
                return {
                    "success": False,
                    "error": "Duel topilmadi yoki allaqachon boshlangan"
                }
            
            # Savollarni tayyorlash
            question_repo = QuestionRepository(session)
            questions = await question_repo.get_random_questions(
                language_id=duel.language_id,
                level_id=duel.level_id,
                count=duel.questions_count
            )
            
            if not questions:
                # Default savollar
                questions = await question_repo.get_random_questions(count=duel.questions_count)
            
            if questions:
                question_ids = [q.id for q in questions]
                await repo.set_question_ids(duel_id, question_ids)
            
            logger.info(f"Duel {duel_id} accepted by user {opponent_id}")
            
            return {
                "success": True,
                "duel_id": duel.id,
                "challenger_id": duel.challenger_id,
                "opponent_id": duel.opponent_id,
                "questions_count": duel.questions_count
            }
    
    async def decline_duel(self, duel_id: int) -> Dict[str, Any]:
        """Duelni rad etish"""
        async with get_session() as session:
            repo = DuelRepository(session)
            
            duel = await repo.decline_duel(duel_id)
            
            if not duel:
                return {
                    "success": False,
                    "error": "Duel topilmadi"
                }
            
            return {"success": True, "duel_id": duel_id}
    
    async def get_duel_questions(self, duel_id: int) -> List[Dict[str, Any]]:
        """Duel savollarini olish"""
        async with get_session() as session:
            repo = DuelRepository(session)
            question_ids = await repo.get_question_ids(duel_id)
            
            if not question_ids:
                return []
            
            question_repo = QuestionRepository(session)
            questions = []
            
            for q_id in question_ids:
                question = await question_repo.get_by_id(q_id)
                if question:
                    options, correct_idx = question.get_shuffled_options()
                    questions.append({
                        "id": question.id,
                        "text": question.question_text,
                        "options": options,
                        "correct_index": correct_idx
                    })
            
            return questions
    
    async def submit_result(
        self,
        duel_id: int,
        user_id: int,
        score: float,
        correct: int,
        time_taken: float
    ) -> Dict[str, Any]:
        """Natijani yuborish"""
        async with get_session() as session:
            repo = DuelRepository(session)
            duel = await repo.get_by_id(duel_id)
            
            if not duel:
                return {"success": False, "error": "Duel topilmadi"}
            
            # Kim natija yubordi?
            if user_id == duel.challenger_id:
                duel = await repo.update_challenger_result(
                    duel_id, score, correct, time_taken
                )
            elif user_id == duel.opponent_id:
                duel = await repo.update_opponent_result(
                    duel_id, score, correct, time_taken
                )
            else:
                return {"success": False, "error": "Siz bu duelda qatnashmayapsiz"}
            
            # Duel tugadimi?
            if duel.status == DuelStatus.COMPLETED:
                # Statistikani yangilash
                await self._update_stats_after_duel(duel)
                
                return {
                    "success": True,
                    "completed": True,
                    "winner_id": duel.winner_id,
                    "is_draw": duel.is_draw,
                    "challenger_score": duel.challenger_score,
                    "opponent_score": duel.opponent_score
                }
            
            return {
                "success": True,
                "completed": False,
                "waiting_for_opponent": True
            }
    
    async def _update_stats_after_duel(self, duel: Duel) -> None:
        """Duel tugagandan keyin statistikani yangilash"""
        async with get_session() as session:
            stats_repo = DuelStatsRepository(session)
            
            if duel.is_draw:
                # Durrang
                await stats_repo.record_duel_result(
                    duel.challenger_id, won=False, is_draw=True
                )
                await stats_repo.record_duel_result(
                    duel.opponent_id, won=False, is_draw=True
                )
            else:
                # G'olib va mag'lub
                winner_id = duel.winner_id
                loser_id = (
                    duel.opponent_id if winner_id == duel.challenger_id
                    else duel.challenger_id
                )
                
                await stats_repo.record_duel_result(
                    winner_id, won=True, stars_change=duel.stake_stars
                )
                await stats_repo.record_duel_result(
                    loser_id, won=False, stars_change=duel.stake_stars
                )
    
    async def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Foydalanuvchi duel statistikasi"""
        async with get_session() as session:
            repo = DuelStatsRepository(session)
            stats = await repo.get_or_create(user_id)
            rank = await repo.get_user_rank(user_id)
            
            return {
                "total_duels": stats.total_duels,
                "wins": stats.wins,
                "losses": stats.losses,
                "draws": stats.draws,
                "win_rate": stats.win_rate,
                "current_streak": stats.current_win_streak,
                "longest_streak": stats.longest_win_streak,
                "rating": stats.rating,
                "peak_rating": stats.peak_rating,
                "rank": rank
            }
    
    async def get_top_players(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Top o'yinchilar"""
        async with get_session() as session:
            repo = DuelStatsRepository(session)
            top_players = await repo.get_top_players(limit)
            
            result = []
            for i, stats in enumerate(top_players, 1):
                result.append({
                    "rank": i,
                    "user_id": stats.user_id,
                    "rating": stats.rating,
                    "wins": stats.wins,
                    "total_duels": stats.total_duels,
                    "win_rate": stats.win_rate
                })
            
            return result
    
    async def get_user_duel_history(
        self,
        user_id: int,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Foydalanuvchi duel tarixi"""
        async with get_session() as session:
            repo = DuelRepository(session)
            duels = await repo.get_user_duels(user_id, limit)
            
            result = []
            for duel in duels:
                opponent_id = (
                    duel.opponent_id if duel.challenger_id == user_id
                    else duel.challenger_id
                )
                
                if duel.is_draw:
                    user_result = "draw"
                elif duel.winner_id == user_id:
                    user_result = "win"
                else:
                    user_result = "loss"
                
                result.append({
                    "duel_id": duel.id,
                    "opponent_id": opponent_id,
                    "result": user_result,
                    "user_score": (
                        duel.challenger_score if duel.challenger_id == user_id
                        else duel.opponent_score
                    ),
                    "opponent_score": (
                        duel.opponent_score if duel.challenger_id == user_id
                        else duel.challenger_score
                    ),
                    "date": duel.completed_at or duel.created_at
                })
            
            return result
    
    async def cleanup_expired_duels(self) -> int:
        """Muddati o'tgan duellarni tozalash"""
        async with get_session() as session:
            repo = DuelRepository(session)
            count = await repo.expire_old_duels()
            
            if count > 0:
                logger.info(f"Expired {count} duels")
            
            return count


# Global instance
duel_service = DuelService()