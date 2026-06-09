"""Assumption surfacing.

Extracts the concrete assumptions a query embodies directly from the executed SQL,
so the panel can never drift from what actually ran. Structural facts (tables,
join path, filters, grain, row cap) come straight from the sqlglot AST. Matched
semantic-layer terms are detected by comparing the columns, functions, and string
literals each term resolves to against those present in the query, which is
alias-independent (a query using `oi.price` still matches `order_items.price`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import expressions as exp

from backend.app.semantic_layer import SEMANTIC_LAYER, TermMapping


@dataclass
class Assumptions:
    """The concrete choices a query made, surfaced for the user."""

    term_mappings: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    joins: list[str] = field(default_factory=list)
    filters: list[str] = field(default_factory=list)
    group_by: list[str] = field(default_factory=list)
    row_limit: int | None = None


def _split_and(node: exp.Expression) -> list[exp.Expression]:
    """Flatten a top-level AND into its conjuncts (typed; avoids sqlglot's flatten())."""
    if isinstance(node, exp.And):
        left = node.args.get("this")
        right = node.args.get("expression")
        parts: list[exp.Expression] = []
        if isinstance(left, exp.Expression):
            parts += _split_and(left)
        if isinstance(right, exp.Expression):
            parts += _split_and(right)
        return parts
    return [node]


def _func_names(tree: exp.Expression) -> set[str]:
    # type(node).__name__ ("Sum" -> "sum") avoids sqlglot's untyped sql_name().
    return {type(f).__name__.lower() for f in tree.find_all(exp.Func)}


def _signature(expression: str) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    """(columns, functions, string-literals) a semantic-layer expression resolves to."""
    tree = sqlglot.parse_one(expression, dialect="sqlite")
    cols = frozenset(c.name.lower() for c in tree.find_all(exp.Column))
    funcs = frozenset(_func_names(tree))
    lits = frozenset(lit.this.lower() for lit in tree.find_all(exp.Literal) if lit.is_string)
    return cols, funcs, lits


def _matched_terms(tree: exp.Expression, layer: tuple[TermMapping, ...]) -> list[str]:
    sql_cols = {c.name.lower() for c in tree.find_all(exp.Column)}
    sql_funcs = _func_names(tree)
    sql_lits = {lit.this.lower() for lit in tree.find_all(exp.Literal) if lit.is_string}

    matched: list[str] = []
    for mapping in layer:
        cols, funcs, lits = _signature(mapping.sql_expression)
        if cols <= sql_cols and funcs <= sql_funcs and lits <= sql_lits:
            matched.append(f"{mapping.term} -> {mapping.sql_expression}")
    return matched


def extract_assumptions(sql: str, layer: tuple[TermMapping, ...] = SEMANTIC_LAYER) -> Assumptions:
    """Parse the executed SQL and surface its structural and semantic assumptions."""
    tree = sqlglot.parse_one(sql, dialect="sqlite")

    tables = sorted({t.name for t in tree.find_all(exp.Table)})

    joins: list[str] = []
    for join in tree.find_all(exp.Join):
        on = join.args.get("on")
        rendered = join.this.sql(dialect="sqlite")
        if on is not None:
            rendered += f" ON {on.sql(dialect='sqlite')}"
        joins.append(rendered)

    filters: list[str] = []
    where = tree.find(exp.Where)
    if where is not None:
        filters = [p.sql(dialect="sqlite") for p in _split_and(where.this)]

    group = tree.find(exp.Group)
    group_by = [e.sql(dialect="sqlite") for e in group.expressions] if group else []

    limit = tree.args.get("limit")
    row_limit: int | None = None
    if limit is not None and isinstance(limit.expression, exp.Literal):
        row_limit = int(limit.expression.this)

    return Assumptions(
        term_mappings=_matched_terms(tree, layer),
        tables=tables,
        joins=joins,
        filters=filters,
        group_by=group_by,
        row_limit=row_limit,
    )
