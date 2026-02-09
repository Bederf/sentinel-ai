from decimal import Decimal

from app.models.contract import PenaltyType, SLABreachSeverity, SLAMetricType
from app.services.sla_compliance_service import SLAComplianceService


def test_detect_breach_severity_and_clawbacks():
    service = SLAComplianceService()

    breach = service.detect_breach(
        metric_type=SLAMetricType.RESPONSE_TIME,
        target=Decimal("4"),
        actual=Decimal("10"),
    )

    assert breach is not None
    assert breach.breach_severity == SLABreachSeverity.CRITICAL

    fixed = service.calculate_clawback(
        breach=breach,
        penalty_type=PenaltyType.FIXED,
        penalty_amount=Decimal("5000"),
        contract_value=Decimal("100000"),
    )
    assert fixed == Decimal("5000")

    percentage = service.calculate_clawback(
        breach=breach,
        penalty_type=PenaltyType.PERCENTAGE,
        penalty_amount=Decimal("10"),
        contract_value=Decimal("100000"),
    )
    assert percentage == Decimal("10000")

    breach.breach_severity = SLABreachSeverity.MAJOR
    tiered = service.calculate_clawback(
        breach=breach,
        penalty_type=PenaltyType.TIERED,
        penalty_amount=Decimal("2000"),
        contract_value=Decimal("100000"),
    )
    assert tiered == Decimal("4000")
