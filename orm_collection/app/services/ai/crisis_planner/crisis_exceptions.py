class CrisisPlannerException(Exception):
    """Base exception for AI Crisis Planner."""
    pass

class CrisisAPIException(CrisisPlannerException):
    """Raised when the LLM provider API call fails."""
    pass

class CrisisValidationException(CrisisPlannerException):
    """Raised when the LLM response fails validation, schema parsing, or grounding checks."""
    pass
