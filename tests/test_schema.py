"""数据 schema 契约测试（docs/api.md §1、docs/spec.md §1/§2、data/schema.json）。

覆盖：
- schema.json 枚举闭合（标签/谓词/类型-谓词组合/status/confidence/来源枚举）
- entities.csv / sources.csv / triples.csv 列与枚举、id 与 spec.md 冻结清单一致
- B/G/H 双来源规则、数值区间、locator 非空
- Cypher 文件存在（schema/查询模板/生成结果）与「CSV 行数 ↔ MERGE 数」一致
"""
from __future__ import annotations

import json
import re

import pytest

from _support import DATA, GRAPH, SCRIPTS, csv_header, read_csv, read_text, split_ids

# ---------------------------------------------------------------- spec.md 冻结清单
VARIETY_IDS = {
    "shine_muscat",
    "kyoho",
    "red_globe",
    "summer_black",
    "muscat_hamburg",
    "crimson_seedless",
    "hutai_8",
    "victoria",
}
CONDITION_IDS = {
    "cold_0",
    "cold_neg1",
    "ice_temp",
    "rh_90_95",
    "rh_low",
    "ca_o2",
    "ca_co2",
    "high_co2",
    "so2_fumigation",
    "so2_pad",
    "mcp_1",
    "ozone",
    "precool_fast",
    "no_damage_harvest",
    "mechanical_injury",
    "room_temp_storage",
    "high_humid_condensation",
    "high_temp_humid",
    "microperforated_film",
    "cold_chain_transport",
    "wound",
    # M8 国标全文入图新增（docs/spec.md §1.2 共 30 个）
    "temp_fluctuation",
    "daily_intake_limit",
    "storage_density",
    "precool_forced",
    "sales_env",
    "archive_record",
    "package_weight",
    "pre_harvest_rain",
    "warehouse_disinfection",
}
QI_IDS = {
    "respiration",
    "ethylene",
    "decay_rate",
    "berry_drop",
    "browning_index",
    "weight_loss",
    "stem_browning",
    "off_flavor",
    "shelf_life",
    "ssc",
    "ta",
    "firmness",
    "vc",
}
DISEASE_IDS = {
    "gray_mold",
    "rhizopus_rot",
    "blue_mold",
    "anthracnose",
    "sour_rot",
    "black_mold",
    "green_mold",  # M8：新增绿霉病（docs/spec.md §1.4 共 7 个）
}
# docs/spec.md §1.4（M8 校正）：id 不变，名称按国标附录B 更正
DISEASE_NAMES = {
    "gray_mold": "灰霉病",
    "rhizopus_rot": "根霉腐败病",
    "blue_mold": "青霉病",
    "anthracnose": "炭疽病",
    "sour_rot": "酸腐病",
    "black_mold": "黑斑病",
    "green_mold": "绿霉病",
}
EXPECTED_IDS = {
    "Variety": VARIETY_IDS,
    "Condition": CONDITION_IDS,
    "QualityIndicator": QI_IDS,
    "Disease": DISEASE_IDS,
}

PREDICATES = {
    "REQUIRES",
    "CONTRA_INDICATED_FOR",
    "AFFECTS",
    "SUSCEPTIBLE_TO",
    "PREVENTED_BY",
    "INDUCED_BY",
    "ALTERNATIVE_TO",
    "INDICATES",
    "HAS_INDICATOR_VALUE",
}
TYPE_PREDICATE = {
    "REQUIRES": ("Variety", "Condition"),
    "CONTRA_INDICATED_FOR": ("Condition", "Variety"),
    "AFFECTS": ("Condition", "QualityIndicator"),
    "SUSCEPTIBLE_TO": ("Variety", "Disease"),
    "PREVENTED_BY": ("Disease", "Condition"),
    "INDUCED_BY": ("Disease", "Condition"),
    "ALTERNATIVE_TO": ("Condition", "Condition"),
    "INDICATES": ("QualityIndicator", "Disease"),
    "HAS_INDICATOR_VALUE": ("Variety", "QualityIndicator"),
}
MULTI_SOURCE_PREDICATES = {"CONTRA_INDICATED_FOR", "ALTERNATIVE_TO", "INDICATES"}
STATUS_ENUM = {"verified", "anchor"}
SOURCE_TYPES = {"国标", "综述", "论文", "行业资料"}
ACCESS_ENUM = {"public", "paywalled"}
ENTITY_COLUMNS = [  # api.md §1.1
    "id", "label", "name", "aliases", "category", "value_min", "value_max", "unit",
    "stage", "direction", "method", "species", "berry_color", "seedless", "maturity",
    "region", "pathogen_latin", "symptom", "source_ids", "note",
]
TRIPLE_COLUMNS = [  # api.md §1.2
    "sid", "subject", "subject_type", "predicate", "object", "object_type",
    "value", "value_min", "value_max", "unit", "stage", "effect", "level",
    "severity", "efficacy", "reason", "source_ids", "locator", "quote",
    "status", "confidence", "note",
]
SOURCE_COLUMNS = ["id", "title", "authors", "year", "venue", "type", "doi_url", "access", "note"]

ENTITIES_CSV = DATA / "entities.csv"
SOURCES_CSV = DATA / "sources.csv"
TRIPLES_CSV = DATA / "triples.csv"
SCHEMA_JSON = DATA / "schema.json"


# ---------------------------------------------------------------- 工具
def _schema() -> dict:
    assert SCHEMA_JSON.is_file(), f"缺少 {SCHEMA_JSON}（S1 交付物）"
    with SCHEMA_JSON.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def _entities() -> list[dict]:
    assert ENTITIES_CSV.is_file(), f"缺少 {ENTITIES_CSV}（S1 交付物）"
    return read_csv(ENTITIES_CSV)


def _sources() -> list[dict]:
    assert SOURCES_CSV.is_file(), f"缺少 {SOURCES_CSV}（S1 交付物）"
    return read_csv(SOURCES_CSV)


def _triples() -> list[dict]:
    assert TRIPLES_CSV.is_file(), f"缺少 {TRIPLES_CSV}（S2a 交付物）"
    return read_csv(TRIPLES_CSV)


def _by_label(rows: list[dict], label: str) -> list[dict]:
    return [row for row in rows if str(row.get("label") or "").strip() == label]


# ---------------------------------------------------------------- schema.json
def test_schema_json_parses_and_has_all_required_sections() -> None:
    schema = _schema()
    for key in (
        "labels",
        "predicates",
        "predicate_type_combos",
        "source_rules",
        "status",
        "confidence",
        "entity_targets",
        "csv_columns",
    ):
        assert key in schema, f"schema.json 缺少顶层键 {key!r}"


def test_schema_json_label_enum_closed() -> None:
    schema = _schema()
    labels = set(schema["labels"])
    assert labels == {"Variety", "Condition", "QualityIndicator", "Disease", "Source"}
    targets = schema["entity_targets"]
    assert targets["Variety"] == len(VARIETY_IDS)
    assert targets["Condition"] == len(CONDITION_IDS)
    assert targets["QualityIndicator"] == len(QI_IDS)
    assert targets["Disease"] == len(DISEASE_IDS)


def test_schema_json_predicate_enum_closed() -> None:
    schema = _schema()
    assert set(schema["predicates"]) == PREDICATES
    combos = schema["predicate_type_combos"]
    assert set(combos) == PREDICATES
    for predicate, expected in TYPE_PREDICATE.items():
        actual = combos[predicate]
        assert (actual["subject_type"], actual["object_type"]) == expected, (
            f"schema.json predicate_type_combos[{predicate}] 类型组合不符（api.md §1.2）"
        )


def test_schema_json_status_confidence_and_source_enums() -> None:
    schema = _schema()
    assert set(schema["status"]["enum"]) == STATUS_ENUM
    assert schema["confidence"]["min"] == 0.0 and schema["confidence"]["max"] == 1.0
    assert set(schema["source_types"]) == SOURCE_TYPES
    assert set(schema["access_enum"]) == ACCESS_ENUM
    assert set(schema["source_rules"]["multi_source_predicates"]) == MULTI_SOURCE_PREDICATES


def test_schema_json_csv_columns_match_api_md() -> None:
    schema = _schema()
    assert schema["csv_columns"]["entities"] == ENTITY_COLUMNS
    assert schema["csv_columns"]["triples"] == TRIPLE_COLUMNS
    assert schema["csv_columns"]["sources"] == SOURCE_COLUMNS


# ---------------------------------------------------------------- entities.csv
def test_entities_csv_columns_and_label_counts() -> None:
    assert csv_header(ENTITIES_CSV) == ENTITY_COLUMNS, "entities.csv 列与 api.md §1.1 不一致"
    rows = _entities()
    labels = {str(row.get("label") or "").strip() for row in rows}
    # 按 schema.json note：Source 节点由 sources.csv 承载，不写入 entities.csv
    assert labels <= {"Variety", "Condition", "QualityIndicator", "Disease"}
    for label, expected_ids in EXPECTED_IDS.items():
        assert len(_by_label(rows, label)) == len(expected_ids), (
            f"{label} 节点数不符：期望 {len(expected_ids)}，实际 {len(_by_label(rows, label))}"
        )


def test_entities_ids_match_spec_frozen_list() -> None:
    rows = _entities()
    for label, expected_ids in EXPECTED_IDS.items():
        actual = {str(row.get("id") or "").strip() for row in _by_label(rows, label)}
        assert actual == expected_ids, (
            f"{label} 的 id 与 spec.md §1 冻结清单不一致；缺失={sorted(expected_ids - actual)} "
            f"多余={sorted(actual - expected_ids)}"
        )


def test_entities_condition_category_and_indicator_direction_enums() -> None:
    schema = _schema()
    categories = set(schema["condition_categories"])
    directions = set(schema["indicator_directions"])
    stages = set(schema["stages"])
    for row in _by_label(_entities(), "Condition"):
        assert row["category"] in categories, f"{row['id']} category={row['category']!r} 不在枚举内"
        if row.get("stage"):
            assert row["stage"] in stages, f"{row['id']} stage={row['stage']!r} 不在枚举内"
    for row in _by_label(_entities(), "QualityIndicator"):
        assert row["direction"] in directions, f"{row['id']} direction={row['direction']!r} 不在枚举内"


def test_entities_names_unique_and_disease_symptom_has_colloquial_words() -> None:
    rows = _entities()
    names = [row["name"] for row in rows]
    assert len(names) == len(set(names)), "entities.csv 存在重复 name"
    # spec.md §1.4：symptom 必须含农户口述症状（长白毛/软烂 至少覆盖灰霉与根霉）
    symptoms = " ".join(row.get("symptom", "") for row in _by_label(rows, "Disease"))
    for word in ("长白毛", "软烂"):
        assert word in symptoms, f" Disease.symptom 缺少农户口语 {word!r}"


def test_disease_names_match_spec_m8_correction() -> None:
    """docs/spec.md §1.4（M8 校正）：id 冻结，但名称必须与国标附录B 对齐（改名要锁住）。"""
    actual = {row["id"]: row["name"] for row in _by_label(_entities(), "Disease")}
    assert actual == DISEASE_NAMES, (
        f"病害 id→name 与 spec.md §1.4 不一致；"
        f"缺失/不符={ {k: v for k, v in DISEASE_NAMES.items() if actual.get(k) != v} }，"
        f"多余={sorted(set(actual) - set(DISEASE_NAMES))}"
    )


def test_entities_source_ids_are_foreign_keys() -> None:
    source_ids = {str(row.get("id") or "").strip() for row in _sources()}
    for row in _entities():
        for source_id in split_ids(row.get("source_ids")):
            assert source_id in source_ids, f"{row['id']} 引用了 sources.csv 中不存在的来源 {source_id!r}"


# ---------------------------------------------------------------- sources.csv
def test_sources_csv_contract() -> None:
    assert csv_header(SOURCES_CSV) == SOURCE_COLUMNS, "sources.csv 列与 api.md §1.3 不一致"
    rows = _sources()
    ids = [str(row.get("id") or "").strip() for row in rows]
    assert len(ids) == len(set(ids)), "sources.csv 存在重复 id"
    assert 10 <= len(rows) <= 12, f"来源数量应为 10~12 条，实际 {len(rows)}"
    for row in rows:
        assert row["type"] in SOURCE_TYPES, f"{row['id']} type={row['type']!r} 非法"
        assert row["access"] in ACCESS_ENUM, f"{row['id']} access={row['access']!r} 非法"
        assert str(row.get("title") or "").strip(), f"{row['id']} 缺少 title"


# ---------------------------------------------------------------- triples.csv
def test_triples_csv_columns_and_enums_closed() -> None:
    assert csv_header(TRIPLES_CSV) == TRIPLE_COLUMNS, "triples.csv 列与 api.md §1.2 不一致"
    rows = _triples()
    assert rows, "triples.csv 没有数据行"
    sids = set()
    for row in rows:
        sid = str(row.get("sid") or "").strip()
        assert sid, f"存在空 sid 的三元组：{row}"
        assert sid not in sids, f"sid 重复：{sid}"
        sids.add(sid)
        predicate = row["predicate"]
        assert predicate in PREDICATES, f"{sid} predicate={predicate!r} 不在枚举内"
        assert row["status"] in STATUS_ENUM, f"{sid} status={row['status']!r} 不在枚举内"
        confidence = float(row["confidence"])
        assert 0.0 <= confidence <= 1.0, f"{sid} confidence 越界：{confidence}"
        assert str(row.get("locator") or "").strip(), f"{sid} locator 为空（api.md §1.2 必填）"


def test_triples_type_predicate_combos_valid() -> None:
    for row in _triples():
        predicate = row["predicate"]
        expected_subject, expected_object = TYPE_PREDICATE[predicate]
        assert row["subject_type"] == expected_subject, (
            f"{row['sid']} {predicate} subject_type={row['subject_type']!r} 期望 {expected_subject!r}"
        )
        assert row["object_type"] == expected_object, (
            f"{row['sid']} {predicate} object_type={row['object_type']!r} 期望 {expected_object!r}"
        )


def test_triples_numeric_range_order() -> None:
    for row in _triples():
        low, value, high = row.get("value_min"), row.get("value"), row.get("value_max")
        numeric = {}
        for key, raw in (("value_min", low), ("value", value), ("value_max", high)):
            text = str(raw or "").strip()
            if text:
                numeric[key] = float(text)
        if "value_min" in numeric and "value_max" in numeric:
            assert numeric["value_min"] <= numeric["value_max"], f"{row['sid']} value_min > value_max"
        if "value" in numeric:
            if "value_min" in numeric:
                assert numeric["value"] >= numeric["value_min"], f"{row['sid']} value < value_min"
            if "value_max" in numeric:
                assert numeric["value"] <= numeric["value_max"], f"{row['sid']} value > value_max"


def test_triples_bgh_double_source_rule() -> None:
    for row in _triples():
        if row["predicate"] not in MULTI_SOURCE_PREDICATES:
            continue
        source_ids = split_ids(row.get("source_ids"))
        note = str(row.get("note") or "")
        assert len(source_ids) >= 2 or "单来源" in note, (
            f"{row['sid']} 属 B/G/H 组，必须 ≥2 来源或在 note 声明单来源（api.md §1.2）"
        )


def test_triples_source_ids_are_foreign_keys() -> None:
    source_ids = {str(row.get("id") or "").strip() for row in _sources()}
    for row in _triples():
        for source_id in split_ids(row.get("source_ids")):
            assert source_id in source_ids, f"{row['sid']} 引用了不存在的来源 {source_id!r}"


def test_triples_subject_object_names_resolvable_in_entities() -> None:
    by_name = {}
    for row in _entities():
        by_name[str(row["name"]).strip()] = str(row["label"]).strip()
    for row in _triples():
        assert row["subject"] in by_name, f"{row['sid']} subject={row['subject']!r} 在 entities 中找不到"
        assert row["object"] in by_name, f"{row['sid']} object={row['object']!r} 在 entities 中找不到"
        assert by_name[row["subject"]] == row["subject_type"], (
            f"{row['sid']} subject 类型不符：entities 为 {by_name[row['subject']]!r}"
        )
        assert by_name[row["object"]] == row["object_type"], (
            f"{row['sid']} object 类型不符：entities 为 {by_name[row['object']]!r}"
        )


# ---------------------------------------------------------------- Cypher
SCHEMA_CYPHER = GRAPH / "schema.cypher"
QUERIES_DIR = GRAPH / "queries"


def test_schema_cypher_exists_with_five_constraints_and_indexes() -> None:
    assert SCHEMA_CYPHER.is_file(), f"缺少 {SCHEMA_CYPHER}（S1 交付物）"
    text = read_text(SCHEMA_CYPHER)
    constraint_count = len(re.findall(r"CREATE\s+CONSTRAINT", text, flags=re.IGNORECASE))
    index_count = len(re.findall(r"CREATE\s+INDEX", text, flags=re.IGNORECASE))
    assert constraint_count >= 5, f"schema.cypher 唯一约束数 {constraint_count} < 5 类标签"
    assert index_count >= 2, f"schema.cypher 索引数 {index_count} 太少（需 name/category 索引）"
    for label in ("Variety", "Condition", "QualityIndicator", "Disease", "Source"):
        assert f":{label})" in text, f"schema.cypher 缺少 {label} 标签的唯一约束"


def test_query_templates_exist_and_cover_intents() -> None:
    from app.contracts import INTENTS

    assert QUERIES_DIR.is_dir(), f"缺少查询模板目录 {QUERIES_DIR}（store-builder S3a 交付物）"
    files = sorted(path for path in QUERIES_DIR.glob("*.cypher") if path.is_file())
    assert len(files) >= 9, f"graph/queries 下只有 {len(files)} 个 .cypher，期望 ≥9 个意图模板"
    for path in files:
        text = read_text(path)
        assert text.strip(), f"{path.name} 是空文件"
        assert "MATCH" in text.upper() or "RETURN" in text.upper(), f"{path.name} 不像 Cypher 查询"
    stems = " ".join(path.stem.lower() for path in files)
    missing = [intent for intent in INTENTS if intent != "general" and intent not in stems]
    assert not missing, f"以下意图缺少同名/包含该名的查询模板文件：{missing}"


def test_generated_cypher_counts_match_csv_rows() -> None:
    """CSV 行数 ↔ 生成 Cypher 的 MERGE 计数一致（生成器未就绪时跳过并标注）。"""
    generator = SCRIPTS / "gen_cypher.py"
    nodes_cypher = GRAPH / "init_nodes.cypher"
    rels_cypher = GRAPH / "init_rels.cypher"
    if not (generator.is_file() and nodes_cypher.is_file() and rels_cypher.is_file()):
        pytest.skip(
            "生成器未就绪：scripts/gen_cypher.py 或 graph/init_nodes.cypher / graph/init_rels.cypher "
            "缺失，跳过「CSV 行数 ↔ MERGE 计数」一致性断言（待 S1/S2a 生成后自动启用）"
        )
    entity_rows = _entities()
    source_rows = _sources()
    triple_rows = _triples()
    node_merges = len(re.findall(r"^\s*MERGE\b", read_text(nodes_cypher), flags=re.MULTILINE | re.IGNORECASE))
    rel_merges = len(re.findall(r"^\s*MERGE\b", read_text(rels_cypher), flags=re.MULTILINE | re.IGNORECASE))
    # Source 节点可能由 sources.csv 追加到节点文件，两种口径都接受
    assert node_merges in (len(entity_rows), len(entity_rows) + len(source_rows)), (
        f"init_nodes.cypher MERGE 数 {node_merges} 与 entities({len(entity_rows)})"
        f" [+sources({len(source_rows)})] 不一致"
    )
    assert rel_merges == len(triple_rows), (
        f"init_rels.cypher MERGE 数 {rel_merges} 与 triples.csv 行数 {len(triple_rows)} 不一致"
    )
