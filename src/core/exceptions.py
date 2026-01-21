"""
Custom exceptions for the application
Proper error handling with meaningful messages
"""
from typing import Optional, Any


class QuizBotException(Exception):
    """Base exception for Quiz Bot"""
    
    def __init__(
        self,
        message: str = "An error occurred",
        code: str = "UNKNOWN_ERROR",
        details: Optional[dict] = None
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self) -> dict:
        return {
            "error": self.code,
            "message": self.message,
            "details": self.details
        }


# ============================================================
# Database Exceptions
# ============================================================

class DatabaseException(QuizBotException):
    """Database related errors"""
    
    def __init__(self, message: str = "Database error", details: Optional[dict] = None):
        super().__init__(message, "DATABASE_ERROR", details)


class EntityNotFoundError(DatabaseException):
    """Entity not found in database"""
    
    def __init__(self, entity: str, identifier: Any):
        super().__init__(
            f"{entity} not found: {identifier}",
            {"entity": entity, "identifier": str(identifier)}
        )
        self.code = "ENTITY_NOT_FOUND"


class DuplicateEntityError(DatabaseException):
    """Duplicate entity error"""
    
    def __init__(self, entity: str, field: str, value: Any):
        super().__init__(
            f"{entity} with {field}={value} already exists",
            {"entity": entity, "field": field, "value": str(value)}
        )
        self.code = "DUPLICATE_ENTITY"


# ============================================================
# Quiz Exceptions
# ============================================================

class QuizException(QuizBotException):
    """Quiz related errors"""
    
    def __init__(self, message: str = "Quiz error", details: Optional[dict] = None):
        super().__init__(message, "QUIZ_ERROR", details)


class QuizNotFoundError(QuizException):
    """Quiz not found"""
    
    def __init__(self, quiz_id: Any):
        super().__init__(f"Quiz not found: {quiz_id}", {"quiz_id": str(quiz_id)})
        self.code = "QUIZ_NOT_FOUND"


class QuizAlreadyActiveError(QuizException):
    """Quiz already active"""
    
    def __init__(self, chat_id: int):
        super().__init__(
            "Quiz already active in this chat",
            {"chat_id": chat_id}
        )
        self.code = "QUIZ_ALREADY_ACTIVE"


class NoQuestionsError(QuizException):
    """No questions available"""
    
    def __init__(self, message: str = "No questions available"):
        super().__init__(message)
        self.code = "NO_QUESTIONS"


class QuizTimeoutError(QuizException):
    """Quiz timeout"""
    
    def __init__(self, question_id: int):
        super().__init__(
            "Question timeout",
            {"question_id": question_id}
        )
        self.code = "QUIZ_TIMEOUT"


# ============================================================
# User Exceptions
# ============================================================

class UserException(QuizBotException):
    """User related errors"""
    
    def __init__(self, message: str = "User error", details: Optional[dict] = None):
        super().__init__(message, "USER_ERROR", details)


class UserBlockedError(UserException):
    """User is blocked"""
    
    def __init__(self, user_id: int):
        super().__init__(f"User is blocked: {user_id}", {"user_id": user_id})
        self.code = "USER_BLOCKED"


class UserNotSubscribedError(UserException):
    """User not subscribed to required channels"""
    
    def __init__(self, user_id: int, channels: list):
        super().__init__(
            "User not subscribed to required channels",
            {"user_id": user_id, "channels": channels}
        )
        self.code = "USER_NOT_SUBSCRIBED"


class InsufficientPermissionError(UserException):
    """Insufficient permission"""
    
    def __init__(self, user_id: int, required_role: str):
        super().__init__(
            f"Insufficient permission. Required: {required_role}",
            {"user_id": user_id, "required_role": required_role}
        )
        self.code = "INSUFFICIENT_PERMISSION"


# ============================================================
# Payment Exceptions
# ============================================================

class PaymentException(QuizBotException):
    """Payment related errors"""
    
    def __init__(self, message: str = "Payment error", details: Optional[dict] = None):
        super().__init__(message, "PAYMENT_ERROR", details)


class InsufficientStarsError(PaymentException):
    """Not enough stars"""
    
    def __init__(self, required: int, available: int):
        super().__init__(
            f"Insufficient stars. Required: {required}, Available: {available}",
            {"required": required, "available": available}
        )
        self.code = "INSUFFICIENT_STARS"


class PaymentFailedError(PaymentException):
    """Payment failed"""
    
    def __init__(self, reason: str):
        super().__init__(f"Payment failed: {reason}", {"reason": reason})
        self.code = "PAYMENT_FAILED"


class SubscriptionExpiredError(PaymentException):
    """Subscription expired"""
    
    def __init__(self, user_id: int):
        super().__init__(
            "Premium subscription expired",
            {"user_id": user_id}
        )
        self.code = "SUBSCRIPTION_EXPIRED"


# ============================================================
# Rate Limit Exceptions
# ============================================================

class RateLimitException(QuizBotException):
    """Rate limit errors"""
    
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: int = 60
    ):
        super().__init__(message, "RATE_LIMIT_EXCEEDED", {"retry_after": retry_after})
        self.retry_after = retry_after


# ============================================================
# Validation Exceptions
# ============================================================

class ValidationException(QuizBotException):
    """Validation errors"""
    
    def __init__(self, message: str, field: Optional[str] = None):
        details = {"field": field} if field else {}
        super().__init__(message, "VALIDATION_ERROR", details)


class InvalidInputError(ValidationException):
    """Invalid input"""
    
    def __init__(self, field: str, message: str):
        super().__init__(f"Invalid {field}: {message}", field)
        self.code = "INVALID_INPUT"


# ============================================================
# External Service Exceptions
# ============================================================

class ExternalServiceException(QuizBotException):
    """External service errors"""
    
    def __init__(
        self,
        service: str,
        message: str = "External service error",
        details: Optional[dict] = None
    ):
        d = details or {}
        d["service"] = service
        super().__init__(message, "EXTERNAL_SERVICE_ERROR", d)


class TelegramAPIError(ExternalServiceException):
    """Telegram API error"""
    
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__("telegram", message, details)
        self.code = "TELEGRAM_API_ERROR"


class AudioServiceError(ExternalServiceException):
    """Audio service error"""
    
    def __init__(self, message: str, provider: str):
        super().__init__("audio", message, {"provider": provider})
        self.code = "AUDIO_SERVICE_ERROR"


class RedisError(ExternalServiceException):
    """Redis error"""
    
    def __init__(self, message: str):
        super().__init__("redis", message)
        self.code = "REDIS_ERROR"
