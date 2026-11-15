"""Universal Quality AI (C5): Zero-shot manufacturing defect detection."""

from cportal_c5.engine import QualityInspectionEngine
from cportal_c5.schemas import InspectionRequest, InspectionResponse
from cportal_c5.service import QualityInspectionService

__all__ = [
    "QualityInspectionEngine",
    "InspectionRequest",
    "InspectionResponse",
    "QualityInspectionService",
]
