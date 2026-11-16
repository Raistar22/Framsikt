from __future__ import annotations


class SnackCounterError(Exception):
    """Base exception for all snack counter domain errors."""


class InvalidTransitionError(SnackCounterError):
    """Raised when an invalid state transition is attempted."""


class BudgetExceededError(SnackCounterError):
    """Raised when a purchase exceeds the remaining budget."""


class VolunteerNotEligibleError(SnackCounterError):
    """Raised when a volunteer is not eligible for assignment."""


class VolunteerAlreadyAssignedError(SnackCounterError):
    """Raised when a volunteer already has an active assignment."""


class RefillNotFoundError(SnackCounterError):
    """Raised when a refill is not found."""


class RefillAlreadyExistsError(SnackCounterError):
    """Raised when trying to create a refill that already exists for a box."""


class PurchaseNotFoundError(SnackCounterError):
    """Raised when a purchase is not found."""


class ClaimNotFoundError(SnackCounterError):
    """Raised when a reimbursement claim is not found."""


class CrossCurrencyError(SnackCounterError):
    """Raised when a cross-currency purchase is attempted without a policy."""


class AssignmentExpiredError(SnackCounterError):
    """Raised when an assignment has expired."""