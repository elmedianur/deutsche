"""
Flashcard Maintenance Service
Avtomatik texnik xizmat vazifalari: auto-suspend, cleanup va boshqalar
"""
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.flashcard_repo import UserFlashcardRepository

logger = logging.getLogger(__name__)


class FlashcardMaintenanceService:
    """Flashcard tizimi uchun texnik xizmat"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_flashcard_repo = UserFlashcardRepository(session)
    
    async def run_auto_suspend(self, threshold_days: int = 180) -> dict:
        """
        Barcha foydalanuvchilar uchun mastered kartochkalarni suspend qilish.
        Har kuni 03:00 da ishga tushadi.
        
        Args:
            threshold_days: Minimal interval (default: 180 kun = 6 oy)
        
        Returns:
            {"total_suspended": int, "threshold_days": int, "run_at": datetime}
        """
        logger.info(f"Auto-suspend boshlandi (threshold: {threshold_days} kun)")
        
        try:
            result = await self.user_flashcard_repo.auto_suspend_all_users(
                threshold_days=threshold_days
            )
            
            result["run_at"] = datetime.now().isoformat()
            result["status"] = "success"
            
            logger.info(
                f"Auto-suspend tugadi: {result['total_suspended']} ta kartochka arxivlandi"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Auto-suspend xatolik: {e}")
            return {
                "status": "error",
                "error": str(e),
                "run_at": datetime.now().isoformat()
            }
    
    async def get_maintenance_stats(self) -> dict:
        """Texnik xizmat statistikasi"""
        from sqlalchemy import select, func
        from src.database.models.flashcard import UserFlashcard
        
        # Suspended kartochkalar soni
        result = await self.session.execute(
            select(func.count(UserFlashcard.id)).where(
                UserFlashcard.is_suspended == True
            )
        )
        suspended_count = result.scalar() or 0
        
        # Suspend qilinishi kerak bo'lgan kartochkalar (180+ kun)
        result = await self.session.execute(
            select(func.count(UserFlashcard.id)).where(
                UserFlashcard.interval >= 180,
                UserFlashcard.is_suspended == False
            )
        )
        pending_suspend = result.scalar() or 0
        
        return {
            "total_suspended": suspended_count,
            "pending_suspend": pending_suspend,
            "threshold_days": 180
        }
