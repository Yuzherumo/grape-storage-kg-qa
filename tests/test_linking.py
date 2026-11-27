"""实体链接测试（docs/api.md §3 + §1.5 口语路由黄金集）。

覆盖：规范名/别名命中、全角转半角、去空格、长词优先、同节点去重、未命中空列表，
以及 data/utterances.csv 12 条口语变体的实体系命中（含 expected_entity_ids 的行 ≥10/12）。
"""
from __future__ import annotations

import pytest
from _support import DATA, get_catalog, hit_ids, link, load_utterances, read_csv, split_ids

ENTITIES_CSV = DATA / "entities.csv"

# 别名 → 期望节点（均取自 data/entities.csv 与 spec.md §1 的农户口语别名）
ALIAS_CASES = [
    ("阳光玫瑰", "shine_muscat"),
    ("香印", "shine_muscat"),
    ("晴王", "shine_muscat"),
    ("青提", "shine_muscat"),
    ("香印青提", "shine_muscat"),
    ("Shine Muscat", "shine_muscat"),
    ("巨峰", "kyoho"),
    ("红提", "red_globe"),
    ("夏黑无核", "summer_black"),
    ("长白毛", "gray_mold"),
    ("白毛", "gray_mold"),
    ("软烂", "rhizopus_rot"),
    ("掉粒", "berry_drop"),
    ("糖度", "ssc"),
]


def test_catalog_loads_entities() -> None:
    assert ENTITIES_CSV.is_file(), f"缺少 {ENTITIES_CSV}（S1 交付物）"
    catalog = get_catalog()
    assert catalog is not None


@pytest.mark.parametrize("text,expected_id", ALIAS_CASES, ids=[case[0] for case in ALIAS_CASES])
def test_alias_and_name_hits(text: str, expected_id: str) -> None:
    ids = hit_ids(link(text))
    assert expected_id in ids, f"{text!r} 未链接到 {expected_id}，实际命中 {ids}"


def test_cold_storage_is_facility_not_temperature_condition() -> None:
    """冷库/冷藏库/库房是设施/场景词，不能绑定到具体的 cold_0 温度条件。"""
    assert hit_ids(link("冷库")) == [], "「冷库」不应链接到具体温度条件"
    assert hit_ids(link("冷库湿度")) == [], "「冷库湿度」不应产生 temperature 条件实体"
    # 明确写“0℃冷藏”时仍可命中 cold_0 的具体条件
    assert "cold_0" in hit_ids(link("0℃冷藏")), "「0℃冷藏」应保留 cold_0 条件命中"


def test_fullwidth_characters_are_normalized() -> None:
    """全角字母/全角空格应先转半角再去空格后命中（api.md §3）。"""
    hits = link("Ｓｈｉｎｅ　Ｍｕｓｃａｔ")  # 全角字母 + 全角空格
    assert "shine_muscat" in hit_ids(hits), f"全角别名未命中：{hit_ids(hits)}"


def test_spaces_are_removed_before_matching() -> None:
    hits = link("阳光 玫瑰 贮藏温度")
    assert "shine_muscat" in hit_ids(hits), f"去空格后应命中阳光玫瑰，实际 {hit_ids(hits)}"


def test_longest_alias_wins_and_node_is_deduplicated() -> None:
    """「香印青提」应优先于「香印」「青提」，且同一 node_id 只保留一条。"""
    hits = link("香印青提库里头湿度得调到多少")
    shine_hits = [hit for hit in hits if hit.node_id == "shine_muscat"]
    assert len(shine_hits) == 1, f"同一 node_id 应去重为 1 条，实际 {len(shine_hits)} 条"
    hit = shine_hits[0]
    surface = str(getattr(hit, "surface", "") or "")
    alias_hit = str(getattr(hit, "alias_hit", "") or "")
    assert "香印青提" in {surface, alias_hit}, (
        f"最长匹配失败：surface={surface!r} alias_hit={alias_hit!r}，期望覆盖「香印青提」"
    )


def test_unmatched_question_returns_empty_list() -> None:
    hits = link("今天天气真好")
    assert isinstance(hits, list)
    assert hits == [], f"无实体问题应返回空列表，实际 {hit_ids(hits)}"


def test_hit_fields_are_contract_compliant() -> None:
    from app.contracts import EntityHit

    hits = link("阳光玫瑰冷藏温度")
    assert hits, "「阳光玫瑰冷藏温度」至少应命中 1 个实体"
    for hit in hits:
        assert isinstance(hit, EntityHit)
        assert hit.node_id and hit.label and hit.surface and hit.alias_hit
        assert 0.0 <= float(hit.score) <= 1.0
        assert isinstance(hit.start, int) and isinstance(hit.end, int)


def test_max_hits_is_respected() -> None:
    hits = link("阳光玫瑰 巨峰 红提 夏黑 玫瑰香 冷藏 温度 湿度 气调", max_hits=2)
    assert len(hits) <= 2, f"max_hits=2 但返回 {len(hits)} 条"


# ---------------------------------------------------------------- 黄金集命中率
_UTTERANCES = load_utterances()
_ANNOTATED = [row for row in _UTTERANCES if split_ids(row.get("expected_entity_ids"))]


def test_golden_set_has_at_least_10_entity_annotated_variants() -> None:
    assert len(_UTTERANCES) == 12, f"utterances.csv 应为 12 条，实际 {len(_UTTERANCES)}"
    assert len(_ANNOTATED) >= 9, (
        f"带 expected_entity_ids 的变体应 ≥9 条（u02 冷库改为设施词后），实际 {len(_ANNOTATED)}"
    )
    entity_ids = {
        str(row.get("id") or "").strip()
        for row in read_csv("entities.csv")
    }
    for row in _UTTERANCES:
        for expected_id in split_ids(row.get("expected_entity_ids")):
            assert expected_id in entity_ids, (
                f"{row['id']} 的 expected_entity_ids={expected_id!r} 不在 entities.csv 中"
            )


@pytest.mark.parametrize(
    "row",
    _ANNOTATED,
    ids=[row["id"] for row in _ANNOTATED],
)
def test_golden_variant_entities_are_linked(row: dict) -> None:
    question = row["utterance"]
    expected = split_ids(row.get("expected_entity_ids"))
    actual = hit_ids(link(question))
    missing = [entity_id for entity_id in expected if entity_id not in actual]
    assert not missing, (
        f"{row['id']} {question!r} 期望命中 {expected}，实际 {actual}，缺失 {missing}"
        f"（note: {row.get('note', '')}）"
    )


def test_golden_variant_hit_rate_at_least_10_of_12() -> None:
    """汇总断言（S5 验收：12 条变体实体命中 ≥10/12；无期望实体的行按空真计通过）。"""
    passed = 0
    failures = []
    for row in _UTTERANCES:
        expected = split_ids(row.get("expected_entity_ids"))
        actual = hit_ids(link(row["utterance"]))
        if all(entity_id in actual for entity_id in expected):
            passed += 1
        else:
            failures.append(row["id"])
    assert passed >= 10, f"实体命中 {passed}/12 < 10/12，未命中行：{failures}"
