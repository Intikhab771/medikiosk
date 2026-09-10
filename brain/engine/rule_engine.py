"""Safe, deterministic evaluation of Question Bank conditions."""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from .errors import MalformedRuleError, UnknownRuleOperatorError

_SIMPLE_EQ_PATTERN = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*==\s*'([^']*)'\s*$")


class EvaluationOutcome(str, Enum):
    TRUE = "true"
    FALSE = "false"
    UNPARSEABLE = "unparseable"


@dataclass(frozen=True)
class RuleResult:
    outcome: EvaluationOutcome
    detail: str

    @property
    def is_true(self) -> bool:
        return self.outcome is EvaluationOutcome.TRUE


class RuleEngine:
    _STRUCTURED_OPS: dict[str, Callable[[Any, Any], bool]] = {
        "equals": lambda a, b: a == b,
        "not_equals": lambda a, b: a != b,
        "contains": lambda a, b: b in a if a is not None else False,
        "not_contains": lambda a, b: b not in a if a is not None else True,
        "exists": lambda a, b: a is not None,
        "not_exists": lambda a, b: a is None,
        "greater_than": lambda a, b: a is not None and a > b,
        "less_than": lambda a, b: a is not None and a < b,
        "greater_than_or_equal": lambda a, b: a is not None and a >= b,
        "less_than_or_equal": lambda a, b: a is not None and a <= b,
        "in": lambda a, b: a in b,
        "not_in": lambda a, b: a not in b,
    }

    def __init__(self, answer_lookup: Callable[[str], Any]):
        self._answer_lookup = answer_lookup

    def evaluate_ask_when(self, ask_when: Any) -> RuleResult:
        if ask_when is None:
            raise MalformedRuleError("ask_when is missing (None).")
        if isinstance(ask_when, dict):
            value = self.evaluate_structured(ask_when)
            return RuleResult(
                EvaluationOutcome.TRUE if value else EvaluationOutcome.FALSE,
                f"structured rule evaluated to {value}",
            )
        if not isinstance(ask_when, str):
            raise MalformedRuleError(f"Unsupported ask_when type: {type(ask_when).__name__}")
        if ask_when.strip().lower() == "always":
            return RuleResult(EvaluationOutcome.TRUE, "ask_when == 'always'")

        match = _SIMPLE_EQ_PATTERN.match(ask_when)
        if match:
            ref_id, expected = match.group(1), match.group(2)
            actual = self._answer_lookup(ref_id)
            result = _normalize(actual) == _normalize(expected)
            return RuleResult(
                EvaluationOutcome.TRUE if result else EvaluationOutcome.FALSE,
                f"{ref_id} == '{expected}' -> recorded answer was {actual!r}, so condition is {result}",
            )

        return RuleResult(
            EvaluationOutcome.UNPARSEABLE,
            f"ask_when is free text, not a machine-evaluable condition: {ask_when!r}",
        )

    def evaluate_structured(self, rule: dict) -> bool:
        if not isinstance(rule, dict) or not rule:
            raise MalformedRuleError(f"Structured rule must be a non-empty dict: {rule!r}")
        if "and" in rule:
            values = rule["and"]
            if not isinstance(values, list):
                raise MalformedRuleError("'and' must contain a list of rules")
            return all(self.evaluate_structured(r) for r in values)
        if "or" in rule:
            values = rule["or"]
            if not isinstance(values, list):
                raise MalformedRuleError("'or' must contain a list of rules")
            return any(self.evaluate_structured(r) for r in values)
        if "not" in rule:
            return not self.evaluate_structured(rule["not"])

        op = rule.get("op")
        if op not in self._STRUCTURED_OPS:
            raise UnknownRuleOperatorError(f"Unknown rule operator '{op}'.")
        parameter = rule.get("parameter")
        if not isinstance(parameter, str) or not parameter:
            raise MalformedRuleError(f"Structured rule missing 'parameter': {rule}")
        actual = self._answer_lookup(parameter)
        expected = rule.get("value")
        try:
            return self._STRUCTURED_OPS[op](actual, expected)
        except (TypeError, ValueError) as exc:
            raise MalformedRuleError(f"Cannot evaluate rule {rule!r}: {exc}") from exc


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().lower()
    return value
