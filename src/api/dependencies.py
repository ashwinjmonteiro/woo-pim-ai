"""API-level service dependencies."""

# FastAPI dependency calls are intentionally expressed as parameter defaults.
# ruff: noqa: B008

from fastapi import Depends
from sqlalchemy.orm import Session

from src.database import get_db
from src.services.pim_service import PimService


def get_pim_service(session: Session = Depends(get_db)) -> PimService:
    """Build a PIM service for the current request session."""
    return PimService(session)
