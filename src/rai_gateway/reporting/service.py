"""Report orchestration service layer."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.reporting import reports
from rai_gateway.reporting.schemas import (
    AISystemReport,
    AssuranceReport,
    BudgetReport,
    ConversationReport,
    PolicyReport,
    ReportSummary,
    RiskReport,
    RuntimeReport,
)

if TYPE_CHECKING:
    from rai_gateway.reporting.schemas import ReportFilters


class ReportingService:
    """Service for report generation and orchestration."""

    def __init__(self, db: Session):
        self.db = db

    def get_summary_report(
        self,
        filters: ReportFilters,
    ) -> ReportSummary:
        """Get executive summary report."""
        return reports.build_report_summary(self.db, filters)

    def get_risk_report(
        self,
        filters: ReportFilters,
    ) -> RiskReport:
        """Get risk analysis report."""
        return reports.build_risk_report(self.db, filters)

    def get_policy_report(
        self,
        filters: ReportFilters,
    ) -> PolicyReport:
        """Get policy effectiveness report."""
        return reports.build_policy_report(self.db, filters)

    def get_budget_report(
        self,
        filters: ReportFilters,
    ) -> BudgetReport:
        """Get budget and cost report."""
        return reports.build_budget_report(self.db, filters)

    def get_runtime_report(
        self,
        filters: ReportFilters,
    ) -> RuntimeReport:
        """Get runtime governance activity report."""
        return reports.build_runtime_report(self.db, filters)

    def get_assurance_report(
        self,
        filters: ReportFilters,
    ) -> AssuranceReport:
        """Get assurance and control coverage report."""
        return reports.build_assurance_report(self.db, filters)

    def get_ai_system_report(
        self,
        ai_system_id: UUID,
        filters: ReportFilters,
    ) -> AISystemReport:
        """Get AI System detailed report."""
        return reports.build_ai_system_report(self.db, ai_system_id, filters)

    def get_conversation_report(
        self,
        conversation_id: UUID,
        filters: ReportFilters,
    ) -> ConversationReport:
        """Get conversation detailed report."""
        return reports.build_conversation_report(self.db, conversation_id, filters)
