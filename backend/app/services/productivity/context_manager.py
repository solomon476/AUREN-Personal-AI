"""Productivity Context Manager for Controlled Conversational AI Assistance.

Constructs bounded, read-only system prompt context from the authenticated user's
active projects, pending/urgent tasks, overdue commitments, and active goals.
Strictly read-only: does not execute writes or modify productivity records.
"""

import logging
from typing import Optional, Tuple
from uuid import UUID

from app.models.productivity import ProductivityContextSummary
from app.services.productivity.base_repository import BaseProductivityRepository

logger = logging.getLogger(__name__)


class ProductivityContextManager:
    """Manages injection of productivity state into chat prompts."""

    def __init__(self, repository: BaseProductivityRepository):
        self.repository = repository

    async def assemble_productivity_context(
        self,
        user_id: UUID,
        query_text: Optional[str] = None,
        max_budget_tokens: int = 1000,
    ) -> Tuple[Optional[str], ProductivityContextSummary]:
        """Assemble a bounded productivity context block for system prompt injection.

        Returns:
            Tuple of (formatted_context_string, summary_model)
        """
        try:
            summary = await self.repository.get_productivity_context(user_id=user_id, max_items=10)
        except Exception as exc:
            logger.warning("Failed assembling productivity context for user %s: %s", user_id, exc)
            return None, ProductivityContextSummary()

        # If user has no active productivity commitments, omit context block
        if (
            summary.total_active_tasks == 0
            and summary.total_active_projects == 0
            and summary.total_active_goals == 0
        ):
            return None, summary

        lines = [
            "--- USER PRODUCTIVITY CONTEXT (READ-ONLY) ---",
            "The following structured data reflects the user's current productivity records.",
            "Use this context to accurately answer questions about their tasks, projects, and goals.",
            "POLICY: You are strictly read-only on this context block itself—to create, update, reschedule, complete, or manage tasks, projects, or goals at the user's request, emit a structured `auren-action` JSON block so the command executor runs it and reports verified results (or prompts confirmation for deletes).",
            "",
        ]

        if summary.overdue_tasks_summary:
            lines.append("OVERDUE TASKS (Needs Immediate Attention):")
            for item in summary.overdue_tasks_summary:
                lines.append(f"- {item}")
            lines.append("")

        if summary.active_projects_summary:
            lines.append("ACTIVE PROJECTS:")
            for item in summary.active_projects_summary:
                lines.append(f"- {item}")
            lines.append("")

        if summary.pending_tasks_summary:
            lines.append("PENDING & UPCOMING TASKS:")
            for item in summary.pending_tasks_summary:
                lines.append(f"- {item}")
            lines.append("")

        if summary.active_goals_summary:
            lines.append("STRATEGIC GOALS:")
            for item in summary.active_goals_summary:
                lines.append(f"- {item}")
            lines.append("")

        lines.append("--- END PRODUCTIVITY CONTEXT ---")
        context_str = "\n".join(lines)
        return context_str, summary

