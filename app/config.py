from __future__ import annotations


class Settings:
    """Application configuration settings.

    Kept simple to avoid pydantic-settings dependency.
    Values can be overridden via environment variables or direct assignment.
    """

    # Office budgets (minor units per month)
    oslo_monthly_budget_minor: int = 600000  # 6,000 NOK in øre
    bengaluru_monthly_budget_minor: int = 1500000  # 15,000 INR in paise

    # Default deadline for assignment completion (hours)
    assignment_deadline_hours: float = 96.0

    # Volunteer fairness configuration
    fairness_rolling_days: int = 30

    # Clock and timezone
    utc_offset_hours: float = 0.0

    @classmethod
    def reset(cls) -> None:
        """Reset all settings to defaults."""
        cls.oslo_monthly_budget_minor = 600000
        cls.bengaluru_monthly_budget_minor = 1500000
        cls.assignment_deadline_hours = 96.0
        cls.fairness_rolling_days = 30
        cls.utc_offset_hours = 0.0


settings = Settings()