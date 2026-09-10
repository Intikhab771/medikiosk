import json
from pathlib import Path

import pytest

from engine.errors import InvalidComplaintFlowError
from engine.loader import load_question_bank
from engine.rule_engine import EvaluationOutcome, RuleEngine

ROOT = Path(__file__).resolve().parents[1]


def test_rule_engine_normalizes_simple_equality():
    r = RuleEngine(lambda key: "YES" if key == "CP_001" else None)
    result = r.evaluate_ask_when("CP_001 == 'yes'")
    assert result.outcome is EvaluationOutcome.TRUE


def test_rule_engine_supports_structured_rules():
    values = {"severity": 8, "course": "getting_worse"}
    r = RuleEngine(values.get)
    assert r.evaluate_structured({"op": "greater_than", "parameter": "severity", "value": 7})
    assert r.evaluate_structured({"and": [
        {"op": "greater_than", "parameter": "severity", "value": 7},
        {"op": "equals", "parameter": "course", "value": "getting_worse"},
    ]})


def test_cross_flow_branch_is_rejected(tmp_path):
    raw = {
        "shared_question_groups": [],
        "complaint_flows": [
            {"complaint_id": "a", "questions": [
                {"id": "A1", "text": "A", "parameter": "a", "answer_type": "free_text",
                 "required": True, "ask_when": "always", "branches": {"default": "B1"}}
            ]},
            {"complaint_id": "b", "questions": [
                {"id": "B1", "text": "B", "parameter": "b", "answer_type": "free_text",
                 "required": True, "ask_when": "always", "branches": {"default": "END"}}
            ]},
        ],
    }
    path = tmp_path / "qb.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(InvalidComplaintFlowError):
        load_question_bank(path)
