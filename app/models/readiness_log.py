"""Daily readiness log — stores user-reported morning wellness signals."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, relationship

from app.core.time_utils import local_today
from app.models.base import Base


class ReadinessLog(Base):
    __tablename__ = "readiness_logs"
    __table_args__ = (
        Index("idx_readiness_user_date", "user_id", "log_date", unique=True),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    log_date = Column(Date, nullable=False, default=lambda: local_today())

    sleep = Column(Integer, nullable=False)
    soreness = Column(Integer, nullable=False)
    energy = Column(Integer, nullable=False)
    stress = Column(Integer, nullable=False)

    score = Column(Integer, nullable=False, default=50)

    status = Column(String(16), nullable=False, default="ready")

    notes = Column(Text, nullable=True)

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    user: Mapped["User"] = relationship("User", back_populates="readiness_logs")

    @staticmethod
    def compute_score(sleep: int, soreness: int, energy: int, stress: int) -> int:
        s_sleep = (sleep - 1) / 4
        s_sore = (soreness - 1) / 4
        s_energy = (energy - 1) / 4
        s_stress = 1.0 - (stress - 1) / 4
        weighted = s_sleep * 0.25 + s_sore * 0.30 + s_energy * 0.30 + s_stress * 0.15
        return int(round(weighted * 100))

    @staticmethod
    def status_from_score(score: int) -> str:
        if score >= 70:
            return "ready"
        if score >= 45:
            return "caution"
        return "rest"
