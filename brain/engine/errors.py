"""Exceptions used by the MediKiosk deterministic questioning engine."""
from __future__ import annotations


class MediKioskError(Exception):
    """Base class for engine errors."""


class QuestionBankLoadError(MediKioskError):
    pass


class DuplicateQuestionIdError(MediKioskError):
    pass


class MissingQuestionReferenceError(MediKioskError):
    pass


class CircularDependencyError(MediKioskError):
    pass


class InvalidComplaintFlowError(MediKioskError):
    pass


class UnknownComplaintError(MediKioskError):
    pass


class UnknownRuleOperatorError(MediKioskError):
    pass


class MalformedRuleError(MediKioskError):
    pass


class InvalidAnswerTypeError(MediKioskError):
    """Answer shape/value does not match the question definition."""


class QuestionNotActiveError(MediKioskError):
    """An answer was submitted for a question that is not currently active."""


class InvalidBranchAnswerError(MediKioskError):
    """A valid question answer has no valid branch and no explicit default."""


class MissingParameterError(MediKioskError):
    pass


class UnsafeParameterResolutionError(MediKioskError):
    pass
