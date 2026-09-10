"""
Loading and validating the two existing JSON data files.

This module is the only place that reads the raw JSON. Everything past
this layer works with the typed `Question` / `ClinicalParameter` objects
from engine/models.py.

Validation performed here (see engineering constraint "fail safely, never
silently continue with corrupted clinical rules"):
    * JSON is well-formed and has the expected top-level keys
    * every question id is globally unique
    * every complaint flow's `branches` graph:
        - has exactly one unambiguous entry point (root)
        - never targets an unknown question id
        - never contains a cycle
    * every `applies_to` complaint id used by a complaint-specific question
      matches that flow's own complaint_id (internal consistency)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .errors import (
    CircularDependencyError,
    DuplicateQuestionIdError,
    InvalidComplaintFlowError,
    MissingQuestionReferenceError,
    QuestionBankLoadError,
)
from .models import ClinicalParameter, Question, RedFlagRule, Stage

_VALID_ANSWER_TYPES = {
    "free_text", "integer", "scale", "yes_no_unknown", "single_choice",
    "multiple_choice", "structured_list",
}


class QuestionBank:
    """In-memory, validated representation of question_bank.json."""

    def __init__(self, raw: dict):
        if not isinstance(raw, dict):
            raise QuestionBankLoadError("Question Bank root must be an object.")
        self.schema_version: str = raw.get("schema_version", "unknown")
        self.status: str = raw.get("status", "unknown")
        self.selection_rules: list[str] = raw.get("selection_rules", [])

        self.questions_by_id: dict[str, Question] = {}
        # group_id -> ordered list of question ids, for shared groups
        self.shared_group_order: dict[str, list[str]] = {}
        # complaint_id -> ordered list of question ids (source array order)
        self.complaint_flow_order: dict[str, list[str]] = {}
        # complaint_id -> root question id (computed)
        self.complaint_flow_root: dict[str, str] = {}

        groups = raw.get("shared_question_groups", [])
        flows = raw.get("complaint_flows", [])
        if not isinstance(groups, list) or not isinstance(flows, list):
            raise QuestionBankLoadError("shared_question_groups and complaint_flows must be arrays.")
        self._parse_shared_groups(groups)
        self._parse_complaint_flows(flows)
        self._validate_applies_to_values()
        self._validate_branch_graphs()

    def _validate_applies_to_values(self) -> None:
        valid_complaints = set(self.complaint_flow_order)
        for question in self.questions_by_id.values():
            for complaint_id in question.applies_to:
                if complaint_id != "all" and complaint_id not in valid_complaints:
                    raise InvalidComplaintFlowError(
                        f"Question '{question.id}' references unknown complaint '{complaint_id}'."
                    )

    # -- parsing -----------------------------------------------------
    def _parse_shared_groups(self, groups: list[dict]) -> None:
        stage_map = {
            "opening": Stage.OPENING,
            "shared_symptom_history": Stage.SHARED_SYMPTOM_HISTORY,
            "health_background": Stage.HEALTH_BACKGROUND,
        }
        for group in groups:
            if not isinstance(group, dict):
                raise QuestionBankLoadError("Each shared question group must be an object.")
            gid = group.get("id")
            if gid not in stage_map:
                raise QuestionBankLoadError(
                    f"Unknown shared question group id '{gid}'. Refusing to "
                    "guess its stage ordering."
                )
            stage = stage_map[gid]
            order: list[str] = []
            for q in group.get("questions", []):
                question = self._build_question(q, stage=stage, group_id=gid)
                self._register(question)
                order.append(question.id)
            self.shared_group_order[gid] = order

    def _parse_complaint_flows(self, flows: list[dict]) -> None:
        for flow in flows:
            if not isinstance(flow, dict):
                raise QuestionBankLoadError("Each complaint flow must be an object.")
            complaint_id = flow.get("complaint_id")
            if not complaint_id:
                raise QuestionBankLoadError(
                    "A complaint_flow entry is missing 'complaint_id'."
                )
            if complaint_id in self.complaint_flow_order:
                raise QuestionBankLoadError(f"Duplicate complaint flow '{complaint_id}'.")
            order: list[str] = []
            for q in flow.get("questions", []):
                question = self._build_question(
                    q, stage=Stage.COMPLAINT_SPECIFIC, group_id=complaint_id
                )
                if question.applies_to and question.applies_to != (complaint_id,):
                    raise InvalidComplaintFlowError(
                        f"Question '{question.id}' in flow '{complaint_id}' has invalid applies_to "
                        f"{question.applies_to}; it must apply only to its own complaint."
                    )
                self._register(question)
                order.append(question.id)
            self.complaint_flow_order[complaint_id] = order

    def _build_question(self, q: dict, stage: Stage, group_id: str) -> Question:
        if not isinstance(q, dict):
            raise QuestionBankLoadError(f"Question in group '{group_id}' must be an object.")
        required_fields = ["id", "text", "parameter", "answer_type", "required", "ask_when"]
        missing = [f for f in required_fields if f not in q]
        if missing:
            raise QuestionBankLoadError(
                f"Question in group '{group_id}' is missing required "
                f"field(s) {missing}: {q}"
            )
        if not isinstance(q["id"], str) or not q["id"]:
            raise QuestionBankLoadError("Question ids must be non-empty strings.")
        if q["answer_type"] not in _VALID_ANSWER_TYPES:
            raise QuestionBankLoadError(f"Unsupported answer_type '{q['answer_type']}' for '{q['id']}'.")
        applies_to = q.get("applies_to", [])
        if not isinstance(applies_to, list) or any(not isinstance(x, str) for x in applies_to):
            raise QuestionBankLoadError(f"Question '{q['id']}' has invalid applies_to.")
        options = q.get("options", [])
        if not isinstance(options, list) or len({str(x).strip().lower() for x in options}) != len(options):
            raise QuestionBankLoadError(f"Question '{q['id']}' has invalid or duplicate options.")
        branches = q.get("branches", {})
        if not isinstance(branches, dict):
            raise QuestionBankLoadError(f"Question '{q['id']}' branches must be an object.")
        if q["answer_type"] in {"single_choice", "multiple_choice", "yes_no_unknown", "scale"} and not options:
            raise QuestionBankLoadError(f"Choice question '{q['id']}' must declare options.")
        red_flag = q.get("red_flag")
        if red_flag is not None and (
            not isinstance(red_flag, dict)
            or not isinstance(red_flag.get("is_red_flag"), bool)
            or not isinstance(red_flag.get("trigger_answers", []), list)
            or not isinstance(red_flag.get("action"), str)
            or not isinstance(red_flag.get("rationale"), str)
        ):
            raise QuestionBankLoadError(f"Question '{q['id']}' has malformed red_flag data.")
        return Question(
            id=q["id"],
            text=q["text"],
            parameter=q["parameter"],
            answer_type=q["answer_type"],
            required=bool(q["required"]),
            stage=stage,
            ask_when=q["ask_when"],
            applies_to=tuple(q.get("applies_to", [])),
            group_id=group_id,
            options=tuple(q.get("options", [])),
            item_fields=tuple(q.get("item_fields", [])),
            priority=q.get("priority"),
            branches=dict(q.get("branches", {})),
            red_flag=RedFlagRule.from_json(q.get("red_flag")),
            rationale=q.get("rationale", ""),
            clinical_review_status=q.get("clinical_review_status", ""),
        )

    def _register(self, question: Question) -> None:
        if question.id in self.questions_by_id:
            raise DuplicateQuestionIdError(
                f"Question id '{question.id}' appears more than once in "
                "the Question Bank."
            )
        self.questions_by_id[question.id] = question

    # -- branch graph validation --------------------------------------
    def _validate_branch_graphs(self) -> None:
        for complaint_id, ids in self.complaint_flow_order.items():
            id_set = set(ids)

            # 1. every branch target must be a real question id or "END"
            targets: set[str] = set()
            for qid in ids:
                q = self.questions_by_id[qid]
                for target in q.branches.values():
                    if not isinstance(target, str):
                        raise InvalidComplaintFlowError(
                            f"Question '{qid}' has a non-string branch target: {target!r}."
                        )
                    if target != "END" and target not in self.questions_by_id:
                        raise MissingQuestionReferenceError(
                            f"Complaint flow '{complaint_id}' question "
                            f"'{qid}' branches to unknown question id "
                            f"'{target}'."
                        )
                    if target != "END":
                        if target not in id_set:
                            raise InvalidComplaintFlowError(
                                f"Complaint flow '{complaint_id}' question '{qid}' "
                                f"branches to question '{target}' outside its own flow."
                            )
                        targets.add(target)

            # 2. exactly one root: a question in this flow that is never
            #    a branch target of a sibling question in the same flow.
            roots = [qid for qid in ids if qid not in targets]
            if len(roots) != 1:
                raise InvalidComplaintFlowError(
                    f"Complaint flow '{complaint_id}' must have exactly one "
                    f"entry point (a question no sibling branches to); "
                    f"found {len(roots)}: {roots}"
                )
            self.complaint_flow_root[complaint_id] = roots[0]

            # 3. no cycles: walk every possible path from root, bounded by
            #    the number of nodes in the flow.
            self._check_acyclic(complaint_id, roots[0], id_set)

    def _check_acyclic(self, complaint_id: str, root: str, id_set: set[str]) -> None:
        # DFS over all branch targets (a node can have multiple outgoing
        # branches depending on the answer given).
        visiting: set[str] = set()

        def dfs(qid: str, path: tuple[str, ...]) -> None:
            if qid in visiting:
                raise CircularDependencyError(
                    f"Complaint flow '{complaint_id}' has a circular "
                    f"branch dependency: {' -> '.join(path + (qid,))}"
                )
            visiting.add(qid)
            q = self.questions_by_id[qid]
            for target in q.branches.values():
                if target == "END":
                    continue
                dfs(target, path + (qid,))
            visiting.discard(qid)

        dfs(root, ())

    # -- convenience accessors -----------------------------------------
    def get(self, question_id: str) -> Optional[Question]:
        return self.questions_by_id.get(question_id)

    def has_complaint(self, complaint_id: str) -> bool:
        return complaint_id in self.complaint_flow_order

    def all_complaint_ids(self) -> list[str]:
        return list(self.complaint_flow_order.keys())


class ClinicalParameters:
    """In-memory representation of clinical_parameters.json. Used as
    secondary reference data (validation ranges, high/routine priority
    tiers) -- see README for why it is not the primary driver of question
    selection."""

    def __init__(self, raw: dict):
        self.schema_version: str = raw.get("schema_version", "unknown")
        self.answer_types: dict = raw.get("answer_types", {})
        self.complaint_profiles: dict = raw.get("complaint_profiles", {})

        self.by_id: dict[str, ClinicalParameter] = {}
        for p in raw.get("shared_parameters", []):
            param = self._build(p)
            self.by_id[param.id] = param
        for p in raw.get("complaint_specific_parameters", []):
            param = self._build(p)
            self.by_id[param.id] = param

    def _build(self, p: dict) -> ClinicalParameter:
        return ClinicalParameter(
            id=p["id"],
            label=p.get("label", p["id"]),
            answer_type=p.get("answer_type", "free_text"),
            required=p.get("required", False),
            priority=p.get("priority") if isinstance(p.get("priority"), str) else None,
            validation=p.get("validation"),
            options=tuple(p.get("options", [])),
            applies_to=tuple(p.get("applies_to", [])),
        )

    def get(self, parameter_id: str) -> Optional[ClinicalParameter]:
        return self.by_id.get(parameter_id)


def load_question_bank(path: str | Path) -> QuestionBank:
    raw = _load_json(path)
    if "shared_question_groups" not in raw or "complaint_flows" not in raw:
        raise QuestionBankLoadError(
            f"'{path}' does not look like a question_bank.json file "
            "(missing shared_question_groups / complaint_flows)."
        )
    return QuestionBank(raw)


def load_clinical_parameters(path: str | Path) -> ClinicalParameters:
    raw = _load_json(path)
    if "shared_parameters" not in raw:
        raise QuestionBankLoadError(
            f"'{path}' does not look like a clinical_parameters.json file "
            "(missing shared_parameters)."
        )
    return ClinicalParameters(raw)


def _load_json(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        raise QuestionBankLoadError(f"File not found: {p}")
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise QuestionBankLoadError(f"Malformed JSON in '{p}': {e}") from e
