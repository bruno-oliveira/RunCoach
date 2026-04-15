"""Daily readiness log — stores user-reported morning wellness signals."""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Integer, String, Text

from app.models.base import Base


class ReadinessLog(Base):
    __tablename__ = "readiness_logs"
    __table_args__ = (
        Index("idx_readiness_user_date", "user_id", "log_date", unique=True),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    log_date = Column(Date, nullable=False, default=lambda: date.today())

    # 1-5 scale: 1 = very poor, 5 = excellent
    sleep = Column(Integer, nullable=False)
    soreness = Column(Integer, nullable=False)
    energy = Column(Integer, nullable=False)
    stress = Column(Integer, nullable=False)

    # Computed composite score (0-100)
    score = Column(Integer, nullable=False, default=50)

    # "ready", "caution", "rest"
    status = Column(String(16), nullable=False, default="ready")

    notes = Column(Text, nullable=True)

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    @staticmethod
    def compute_score(sleep: int, soreness: int, energy: int, stress: int) -> int:
        """Weighted composite on a 0-100 scale.

        Soreness and energy carry slightly more weight because they correlate
        most directly with injury risk and training capacity. Stress is
        inverted (higher reported stress = lower contribution).
        """
        # Normalize each to 0-1
        s_sleep = (sleep - 1) / 4
        s_sore = (soreness - 1) / 4
        s_energy = (energy - 1) / 4
        s_stress = 1.0 - (stress - 1) / 4  # inverted
        weighted = (
            s_sleep * 0.25
            + s_sore * 0.30
            + s_energy * 0.30
            + s_stress * 0.15
        )
        return int(round(weighted * 100))

    @staticmethod
    def status_from_score(score: int) -> str:
        if score >= 70:
            return "ready"
        if score >= 45:
            return "caution"
        return "rest"
