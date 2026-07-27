class AdvisorException(Exception):
    """Base exception for AI Reputation Advisor."""
    pass

class GroqAPIException(AdvisorException):
    """Raised when the Groq API call fails."""
    pass

class ContextMissingException(AdvisorException):
    """Raised when required client context is missing."""
    pass

class ValidationException(AdvisorException):
    """Raised when the LLM response fails validation or schema parsing."""
    pass
