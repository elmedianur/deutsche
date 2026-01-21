"""
Structured logging with structlog
Professional logging for production
"""
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional
import structlog
from structlog.types import Processor

from src.config import settings

# Log rotation settings
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT = 5  # 5 ta backup fayl


def setup_logging() -> None:
    """Configure structured logging"""
    
    # Create logs directory if needed
    if settings.LOG_FILE:
        log_path = Path(settings.LOG_FILE)
        log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Shared processors
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    
    if settings.LOG_FORMAT == "json":
        # JSON format for production
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer()
        ]
    else:
        # Console format for development
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True)
        ]
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.LOG_LEVEL)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Configure standard logging with rotation
    handlers = [logging.StreamHandler(sys.stdout)]

    if settings.LOG_FILE:
        # RotatingFileHandler - disk to'lib qolishini oldini oladi
        file_handler = RotatingFileHandler(
            settings.LOG_FILE,
            maxBytes=MAX_LOG_SIZE,
            backupCount=BACKUP_COUNT,
            encoding="utf-8"
        )
        handlers.append(file_handler)

    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, settings.LOG_LEVEL),
        handlers=handlers
    )
    
    # Reduce noise from libraries
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: Optional[str] = None) -> structlog.BoundLogger:
    """Get a logger instance"""
    return structlog.get_logger(name)


class LoggerMixin:
    """Mixin for classes that need logging"""
    
    @property
    def logger(self) -> structlog.BoundLogger:
        if not hasattr(self, "_logger"):
            self._logger = get_logger(self.__class__.__name__)
        return self._logger


# Context helpers
def bind_user_context(user_id: int, username: Optional[str] = None) -> None:
    """Bind user context to all subsequent logs"""
    structlog.contextvars.bind_contextvars(
        user_id=user_id,
        username=username
    )


def bind_chat_context(chat_id: int, chat_type: Optional[str] = None) -> None:
    """Bind chat context to all subsequent logs"""
    structlog.contextvars.bind_contextvars(
        chat_id=chat_id,
        chat_type=chat_type
    )


def clear_context() -> None:
    """Clear all context variables"""
    structlog.contextvars.clear_contextvars()


# Audit logging
class AuditLogger:
    """Special logger for audit events"""
    
    def __init__(self):
        self._logger = get_logger("audit")
    
    def log_admin_action(
        self,
        admin_id: int,
        action: str,
        target: Optional[str] = None,
        details: Optional[dict] = None
    ) -> None:
        """Log admin action"""
        self._logger.info(
            "admin_action",
            admin_id=admin_id,
            action=action,
            target=target,
            details=details
        )
    
    def log_payment(
        self,
        user_id: int,
        amount: int,
        currency: str,
        status: str,
        payment_id: Optional[str] = None
    ) -> None:
        """Log payment event"""
        self._logger.info(
            "payment",
            user_id=user_id,
            amount=amount,
            currency=currency,
            status=status,
            payment_id=payment_id
        )
    
    def log_subscription_change(
        self,
        user_id: int,
        old_status: str,
        new_status: str,
        reason: str
    ) -> None:
        """Log subscription change"""
        self._logger.info(
            "subscription_change",
            user_id=user_id,
            old_status=old_status,
            new_status=new_status,
            reason=reason
        )
    
    def log_security_event(
        self,
        event_type: str,
        user_id: Optional[int] = None,
        details: Optional[dict] = None
    ) -> None:
        """Log security event"""
        self._logger.warning(
            "security_event",
            event_type=event_type,
            user_id=user_id,
            details=details
        )


# Global audit logger instance
audit_logger = AuditLogger()
