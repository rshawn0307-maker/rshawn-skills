#!/usr/bin/env python3
"""Zero-dependency structural validator for question-schema-v1 JSON files."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


TYPE_CODES = {"ca", "op", "ir", "er", "sa", "ve"}
STATUSES = {"draft", "reviewed", "published", "retired"}
DIFFICULTIES = {"basic", "standard", "advanced"}
EXAM_SCOPES = {"civil_service", "public_institution"}
SOURCE_TYPES = {"simulated", "official", "adapted"}
SEVERITIES = {"minor", "major", "critical"}
ROOT_FIELDS = {
    "schema_version", "question_id", "content_version", "status", "question_type",
    "subtype", "title", "prompt", "materials", "difficulty", "exam_scopes",
    "source", "competencies", "timing", "scoring", "reference_answer",
    "retest", "tags", "metadata",
}
ROOT_REQUIRED = ROOT_FIELDS - {"materials", "tags"}
CODE_RE = re.compile(r"^[a-z][a-z0-9_.]{1,79}$")
VERSION_RE = re.compile(r"^[a-z][a-z0-9_.-]{2,79}$")
SUBTYPE_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
QUESTION_ID_RE = re.compile(r"^gkq_(ca|op|ir|er|sa|ve)_[0-9]{6}$")


def validate(data: Any) -> list[str]:
    errors: list[str] = []

    def error(path: str, message: str) -> None:
        errors.append(f"{path}: {message}")

    def object_at(value: Any, path: str, required: set[str], allowed: set[str]) -> dict[str, Any]:
        if not isinstance(value, dict):
            error(path, "必须是对象")
            return {}
        missing = required - value.keys()
        extra = value.keys() - allowed
        for key in sorted(missing):
            error(path, f"缺少字段 {key}")
        for key in sorted(extra):
            error(path, f"不允许字段 {key}")
        return value

    def text(value: Any, path: str, minimum: int, maximum: int) -> str:
        if not isinstance(value, str):
            error(path, "必须是字符串")
            return ""
        if not minimum <= len(value) <= maximum:
            error(path, f"长度必须在 {minimum}—{maximum} 之间")
        return value

    def code(value: Any, path: str) -> str:
        result = text(value, path, 2, 80)
        if result and not CODE_RE.fullmatch(result):
            error(path, "必须是小写稳定编码，只能使用字母、数字、下划线和点")
        return result

    root = object_at(data, "$", ROOT_REQUIRED, ROOT_FIELDS)
    if root.get("schema_version") != "question-schema-v1":
        error("$.schema_version", "必须等于 question-schema-v1")

    question_id = text(root.get("question_id"), "$.question_id", 1, 80)
    match = QUESTION_ID_RE.fullmatch(question_id)
    if question_id and not match:
        error("$.question_id", "格式必须为 gkq_<题型代码>_<6位序号>")

    version = root.get("content_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        error("$.content_version", "必须是大于等于1的整数")

    if root.get("status") not in STATUSES:
        error("$.status", f"必须是 {sorted(STATUSES)} 之一")
    question_type = root.get("question_type")
    if question_type not in TYPE_CODES:
        error("$.question_type", f"必须是 {sorted(TYPE_CODES)} 之一")
    if match and question_type in TYPE_CODES and match.group(1) != question_type:
        error("$.question_id", "题型代码必须与 question_type 一致")

    subtype = text(root.get("subtype"), "$.subtype", 2, 64)
    if subtype and not SUBTYPE_RE.fullmatch(subtype):
        error("$.subtype", "必须是小写 snake_case 编码")
    text(root.get("title"), "$.title", 2, 60)
    text(root.get("prompt"), "$.prompt", 10, 500)
    if root.get("difficulty") not in DIFFICULTIES:
        error("$.difficulty", f"必须是 {sorted(DIFFICULTIES)} 之一")

    scopes = root.get("exam_scopes")
    if not isinstance(scopes, list) or not scopes:
        error("$.exam_scopes", "必须是非空数组")
    elif len(scopes) != len(set(scopes)) or not set(scopes) <= EXAM_SCOPES:
        error("$.exam_scopes", "存在重复或非法考试范围")

    materials = root.get("materials", [])
    if not isinstance(materials, list) or len(materials) > 5:
        error("$.materials", "必须是最多5项的数组")
    else:
        for index, item in enumerate(materials):
            path = f"$.materials[{index}]"
            obj = object_at(item, path, {"material_id", "title", "content"}, {"material_id", "title", "content"})
            material_id = text(obj.get("material_id"), f"{path}.material_id", 5, 68)
            if material_id and not re.fullmatch(r"^mat_[a-z0-9_]{3,64}$", material_id):
                error(f"{path}.material_id", "格式不正确")
            text(obj.get("title"), f"{path}.title", 1, 80)
            text(obj.get("content"), f"{path}.content", 10, 3000)

    source = object_at(root.get("source"), "$.source", {"type", "name"}, {"type", "name", "reference_url", "exam_date", "copyright_note"})
    if source.get("type") not in SOURCE_TYPES:
        error("$.source.type", f"必须是 {sorted(SOURCE_TYPES)} 之一")
    text(source.get("name"), "$.source.name", 2, 120)

    competencies = object_at(root.get("competencies"), "$.competencies", {"primary", "secondary"}, {"primary", "secondary"})
    primary = validate_coded_label(competencies.get("primary"), "$.competencies.primary", object_at, code, text)
    secondary = competencies.get("secondary")
    secondary_codes: list[str] = []
    if not isinstance(secondary, list) or len(secondary) > 6:
        error("$.competencies.secondary", "必须是最多6项的数组")
    else:
        for index, item in enumerate(secondary):
            secondary_codes.append(validate_coded_label(item, f"$.competencies.secondary[{index}]", object_at, code, text))
        if len(secondary_codes) != len(set(secondary_codes)):
            error("$.competencies.secondary", "能力编码不能重复")

    timing = object_at(root.get("timing"), "$.timing", {"thinking_seconds", "answering_seconds"}, {"thinking_seconds", "answering_seconds"})
    integer_range(timing.get("thinking_seconds"), "$.timing.thinking_seconds", 0, 600, error)
    integer_range(timing.get("answering_seconds"), "$.timing.answering_seconds", 30, 1200, error)

    scoring = object_at(root.get("scoring"), "$.scoring", {"rubric_version", "total_points", "score_points", "losing_points"}, {"rubric_version", "total_points", "score_points", "losing_points"})
    rubric_version = text(scoring.get("rubric_version"), "$.scoring.rubric_version", 3, 80)
    if rubric_version and not VERSION_RE.fullmatch(rubric_version):
        error("$.scoring.rubric_version", "必须是小写版本编码，只能使用字母、数字、下划线、点和连字符")
    if scoring.get("total_points") != 100:
        error("$.scoring.total_points", "必须等于100")
    score_points = scoring.get("score_points")
    score_codes: list[str] = []
    score_total = 0
    if not isinstance(score_points, list) or not 2 <= len(score_points) <= 12:
        error("$.scoring.score_points", "必须包含2—12项")
    else:
        for index, item in enumerate(score_points):
            path = f"$.scoring.score_points[{index}]"
            obj = object_at(item, path, {"code", "description", "max_points", "evidence_required"}, {"code", "description", "max_points", "evidence_required"})
            score_codes.append(code(obj.get("code"), f"{path}.code"))
            text(obj.get("description"), f"{path}.description", 5, 300)
            points = integer_range(obj.get("max_points"), f"{path}.max_points", 1, 100, error)
            score_total += points or 0
            if obj.get("evidence_required") is not True:
                error(f"{path}.evidence_required", "首版必须为 true")
        if score_total != 100:
            error("$.scoring.score_points", f"max_points 合计必须为100，当前为{score_total}")
        if len(score_codes) != len(set(score_codes)):
            error("$.scoring.score_points", "评分点编码不能重复")

    losing_points = scoring.get("losing_points")
    if not isinstance(losing_points, list) or not 1 <= len(losing_points) <= 12:
        error("$.scoring.losing_points", "必须包含1—12项")
    else:
        for index, item in enumerate(losing_points):
            path = f"$.scoring.losing_points[{index}]"
            obj = object_at(item, path, {"code", "description", "severity", "error_tag_candidates"}, {"code", "description", "severity", "error_tag_candidates"})
            code(obj.get("code"), f"{path}.code")
            text(obj.get("description"), f"{path}.description", 5, 300)
            if obj.get("severity") not in SEVERITIES:
                error(f"{path}.severity", f"必须是 {sorted(SEVERITIES)} 之一")
            validate_code_list(obj.get("error_tag_candidates"), f"{path}.error_tag_candidates", code, error, minimum=1)

    answer = object_at(root.get("reference_answer"), "$.reference_answer", {"outline", "sample_answer"}, {"outline", "sample_answer"})
    outline = answer.get("outline")
    if not isinstance(outline, list) or not 2 <= len(outline) <= 12:
        error("$.reference_answer.outline", "必须包含2—12项")
    else:
        for index, item in enumerate(outline):
            text(item, f"$.reference_answer.outline[{index}]", 5, 300)
    text(answer.get("sample_answer"), "$.reference_answer.sample_answer", 200, 5000)

    retest = object_at(root.get("retest"), "$.retest", {"target_competency_codes", "target_error_tag_codes", "variation_requirements", "related_question_ids"}, {"target_competency_codes", "target_error_tag_codes", "variation_requirements", "related_question_ids"})
    target_competencies = validate_code_list(retest.get("target_competency_codes"), "$.retest.target_competency_codes", code, error, minimum=1)
    validate_code_list(retest.get("target_error_tag_codes"), "$.retest.target_error_tag_codes", code, error, minimum=1)
    if primary and primary not in target_competencies:
        error("$.retest.target_competency_codes", "必须包含主能力编码")
    requirements = retest.get("variation_requirements")
    if not isinstance(requirements, list) or not 1 <= len(requirements) <= 10:
        error("$.retest.variation_requirements", "必须包含1—10项")
    else:
        for index, item in enumerate(requirements):
            text(item, f"$.retest.variation_requirements[{index}]", 5, 300)
    related = retest.get("related_question_ids")
    if not isinstance(related, list):
        error("$.retest.related_question_ids", "必须是数组")
    else:
        if len(related) != len(set(related)):
            error("$.retest.related_question_ids", "题目ID不能重复")
        for index, item in enumerate(related):
            if not isinstance(item, str) or not QUESTION_ID_RE.fullmatch(item):
                error(f"$.retest.related_question_ids[{index}]", "题目ID格式不正确")
            elif item == question_id:
                error(f"$.retest.related_question_ids[{index}]", "不能关联自身")

    tags = root.get("tags", [])
    if not isinstance(tags, list) or len(tags) > 20 or any(not isinstance(item, str) or not 1 <= len(item) <= 40 for item in tags):
        error("$.tags", "必须是最多20项、每项1—40字的字符串数组")
    elif len(tags) != len(set(tags)):
        error("$.tags", "标签不能重复")

    metadata = object_at(root.get("metadata"), "$.metadata", {"created_at", "updated_at", "created_by", "reviewed_by", "language"}, {"created_at", "updated_at", "created_by", "reviewed_by", "language"})
    for key in ("created_at", "updated_at"):
        value = metadata.get(key)
        if not isinstance(value, str) or not valid_datetime(value):
            error(f"$.metadata.{key}", "必须是带时区的 ISO 8601 时间")
    text(metadata.get("created_by"), "$.metadata.created_by", 1, 80)
    reviewed_by = metadata.get("reviewed_by")
    if reviewed_by is not None:
        text(reviewed_by, "$.metadata.reviewed_by", 1, 80)
    if metadata.get("language") != "zh-CN":
        error("$.metadata.language", "首版必须为 zh-CN")

    return errors


def validate_coded_label(value: Any, path: str, object_at: Any, code: Any, text: Any) -> str:
    obj = object_at(value, path, {"code", "name"}, {"code", "name"})
    result = code(obj.get("code"), f"{path}.code")
    text(obj.get("name"), f"{path}.name", 2, 50)
    return result


def integer_range(value: Any, path: str, minimum: int, maximum: int, error: Any) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        error(path, f"必须是 {minimum}—{maximum} 之间的整数")
        return None
    return value


def validate_code_list(value: Any, path: str, code: Any, error: Any, minimum: int) -> list[str]:
    if not isinstance(value, list) or len(value) < minimum:
        error(path, f"必须是至少{minimum}项的数组")
        return []
    result = [code(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if len(result) != len(set(result)):
        error(path, "编码不能重复")
    return result


def valid_datetime(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.tzinfo is not None
    except ValueError:
        return False


def validate_product_contracts(data: dict[str, Any], script_path: Path) -> list[str]:
    errors: list[str] = []
    contract_dir = script_path.parent.parent / "references" / "product"
    try:
        rubric = json.loads((contract_dir / "interview-rubric-v1-draft.json").read_text(encoding="utf-8"))
        taxonomy = json.loads((contract_dir / "error-tags-v1.json").read_text(encoding="utf-8"))
        retest_policy = json.loads((contract_dir / "retest-policy-v1.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"$.contracts: 无法读取产品合同: {exc}"]

    question_type = data.get("question_type")
    type_rubric = rubric.get("type_rubrics", {}).get(question_type, {})
    common_dimensions = rubric.get("common_dimensions", [])
    type_dimensions = type_rubric.get("dimensions", []) if isinstance(type_rubric, dict) else []
    expected_weights = {
        item["code"]: item["weight"]
        for item in [*common_dimensions, *type_dimensions]
        if isinstance(item, dict) and isinstance(item.get("code"), str) and isinstance(item.get("weight"), int)
    }
    score_points = data.get("scoring", {}).get("score_points", [])
    actual_weights = {
        item.get("code"): item.get("max_points")
        for item in score_points if isinstance(item, dict)
    }
    if actual_weights != expected_weights:
        errors.append("$.scoring.score_points: 必须与当前题型的4个公共维度和3个专属维度完全一致，分值使用量表权重")
    if data.get("scoring", {}).get("rubric_version") != rubric.get("rubric_version"):
        errors.append("$.scoring.rubric_version: 必须与随附评分量表版本一致")

    competency_codes: list[str] = []
    competencies = data.get("competencies", {})
    primary = competencies.get("primary", {})
    if isinstance(primary, dict) and isinstance(primary.get("code"), str):
        competency_codes.append(primary["code"])
    for item in competencies.get("secondary", []) if isinstance(competencies, dict) else []:
        if isinstance(item, dict) and isinstance(item.get("code"), str):
            competency_codes.append(item["code"])
    if not set(competency_codes) <= set(expected_weights):
        errors.append("$.competencies: 能力编码必须来自当前题型评分维度")

    allowed_tags = {
        item["code"]
        for item in taxonomy.get("tags", [])
        if isinstance(item, dict)
        and isinstance(item.get("code"), str)
        and question_type in item.get("question_types", [])
    }
    losing_tag_codes = {
        tag
        for item in data.get("scoring", {}).get("losing_points", [])
        if isinstance(item, dict)
        for tag in item.get("error_tag_candidates", [])
        if isinstance(tag, str)
    }
    if not losing_tag_codes <= allowed_tags:
        errors.append("$.scoring.losing_points: 存在不适用于当前题型或标签库中不存在的错因编码")

    retest = data.get("retest", {})
    retest_competencies = set(retest.get("target_competency_codes", [])) if isinstance(retest, dict) else set()
    if not retest_competencies <= set(competency_codes):
        errors.append("$.retest.target_competency_codes: 必须来自本题 competencies")
    retest_tags = set(retest.get("target_error_tag_codes", [])) if isinstance(retest, dict) else set()
    if not retest_tags <= losing_tag_codes:
        errors.append("$.retest.target_error_tag_codes: 必须来自本题失分点的错因候选")

    policy_map = {
        item["error_tag_code"]: item
        for item in retest_policy.get("rules", [])
        if isinstance(item, dict) and isinstance(item.get("error_tag_code"), str)
    }
    if not retest_tags <= set(policy_map):
        errors.append("$.retest.target_error_tag_codes: 存在没有复测规则的错因编码")
    return errors


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python3 scripts/validate_product_question.py <question.json> [...]", file=sys.stderr)
        return 2
    failed = False
    for argument in sys.argv[1:]:
        path = Path(argument)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"FAIL {path}: 无法读取JSON: {exc}")
            failed = True
            continue
        errors = validate(data)
        if isinstance(data, dict):
            errors.extend(validate_product_contracts(data, Path(__file__).resolve()))
        if errors:
            failed = True
            print(f"FAIL {path}: {len(errors)} 个问题")
            for item in errors:
                print(f"  - {item}")
        else:
            print(f"PASS {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
