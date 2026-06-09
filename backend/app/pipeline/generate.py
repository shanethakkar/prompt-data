"""SQL generation and the self-correction loop.

generate_sql makes one structured LLM call and returns a typed {sql, explanation}.
generate_with_self_correction wraps it in the execute loop: generate, run through
the Phase 0 SELECT-only sandbox, and on a validation or SQLite error feed the
error back and regenerate, up to a capped number of attempts. Whether correction
fired is recorded as a confidence signal for Phase 2.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from pydantic import BaseModel, Field

from backend.app.config import Settings
from backend.app.llm import LLMClient
from backend.app.pipeline.execute import ExecutionResult, ValidationError, execute_query

_RULES = """\
You translate questions about an Olist e-commerce SQLite database into a single \
read-only SQL query.

Rules:
- Output exactly one SQL statement: a single SELECT (a WITH ... SELECT CTE is allowed).
- Read-only only. Never INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, ATTACH, or PRAGMA.
- Use only the tables and columns that appear in the schema below. Do not invent columns.
- Prefer the semantic-layer resolutions below when the question uses those business terms.
- SQLite dialect. No trailing semicolon. No SQL comments.
- Do not declare named columns on a CTE: write "WITH c AS (SELECT 1 AS n ...)", \
never "WITH c(n) AS ...".
- The explanation field must be one plain sentence describing what the query computes."""


class SqlGeneration(BaseModel):
    """Structured model output: the query and a one-line explanation."""

    sql: str = Field(description="A single read-only SQLite SELECT statement.")
    explanation: str = Field(description="One sentence describing what the query computes.")


@dataclass
class SelfCorrectionResult:
    """Outcome of the generate/validate/execute loop."""

    sql: str
    explanation: str
    execution: ExecutionResult | None
    attempts: int
    self_correction_fired: bool
    error: str | None


def build_system_prompt(schema_context: str, semantic_context: str) -> str:
    """Assemble the stable (cacheable) system prompt."""
    return (
        f"{_RULES}\n\n"
        f"<schema>\n{schema_context}\n</schema>\n\n"
        f"<semantic_layer>\n{semantic_context}\n</semantic_layer>"
    )


def _build_user_message(question: str, prior_sql: str | None, prior_error: str | None) -> str:
    if prior_sql is None or prior_error is None:
        return f"Question: {question}"
    return (
        f"Question: {question}\n\n"
        f"Your previous query failed and must be corrected.\n"
        f"Previous SQL:\n{prior_sql}\n\n"
        f"Error:\n{prior_error}\n\n"
        f"Return a corrected single read-only SELECT."
    )


def generate_sql(
    question: str,
    *,
    client: LLMClient,
    model: str,
    schema_context: str,
    semantic_context: str,
    prior_sql: str | None = None,
    prior_error: str | None = None,
    temperature: float = 0.0,
) -> SqlGeneration:
    """One structured generation call. Includes repair context when retrying."""
    system = build_system_prompt(schema_context, semantic_context)
    user = _build_user_message(question, prior_sql, prior_error)
    return client.generate_structured(
        model=model,
        system=system,
        user=user,
        output_format=SqlGeneration,
        temperature=temperature,
    )


def generate_with_self_correction(
    question: str,
    *,
    client: LLMClient,
    model: str,
    db_path: str,
    schema_context: str,
    semantic_context: str,
    settings: Settings,
) -> SelfCorrectionResult:
    """Generate, execute through the sandbox, and repair on error up to the cap."""
    max_attempts = 1 + settings.max_self_correction_attempts
    prior_sql: str | None = None
    prior_error: str | None = None
    last = SqlGeneration(sql="", explanation="")

    for attempt in range(1, max_attempts + 1):
        last = generate_sql(
            question,
            client=client,
            model=model,
            schema_context=schema_context,
            semantic_context=semantic_context,
            prior_sql=prior_sql,
            prior_error=prior_error,
        )
        try:
            execution = execute_query(
                last.sql,
                db_path,
                default_limit=settings.sql_default_limit,
                timeout_seconds=settings.sql_timeout_seconds,
            )
        except ValidationError as exc:
            prior_sql, prior_error = last.sql, f"The read-only validator rejected it: {exc.reason}"
            continue
        except sqlite3.Error as exc:
            prior_sql, prior_error = last.sql, f"SQLite could not run it: {exc}"
            continue

        return SelfCorrectionResult(
            sql=execution.sql_executed,
            explanation=last.explanation,
            execution=execution,
            attempts=attempt,
            self_correction_fired=attempt > 1,
            error=None,
        )

    return SelfCorrectionResult(
        sql=last.sql,
        explanation=last.explanation,
        execution=None,
        attempts=max_attempts,
        self_correction_fired=max_attempts > 1,
        error=prior_error,
    )
