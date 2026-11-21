// graph/queries/variety_compare.cypher
// 意图：variety_compare —— 多品种对比：耐贮性/指标值 + 温度要求 + 禁忌，证据必须覆盖每个品种
// 执行方：app/store/neo4j_store.py（参数化）；LocalStore.query_cypher 复用做展示
// 参数（均必传；列表可为空 []，不可为 null）：
//   $variety_ids list[str]  品种 id（对比通常是 2 个）；[] = 所有品种
//   $limit       int        返回条数上限
// 语义与 LocalStore._load_variety_compare 一致；
// 覆盖保证由 LocalStore._select_with_coverage 完成，Neo4j 侧按 confidence 排序后由 qa 呈现，
// 若需要严格覆盖请在 store 层复用同一选择器（见 app/store/neo4j_store.py::execute 注释）。
CALL {
  MATCH (s:Variety)-[r:HAS_INDICATOR_VALUE]->(o:QualityIndicator)
  WHERE size($variety_ids) = 0 OR s.id IN $variety_ids
  RETURN s, r, o
  UNION ALL
  MATCH (s:Variety)-[r:REQUIRES]->(o:Condition)
  WHERE (size($variety_ids) = 0 OR s.id IN $variety_ids)
    AND o.category = '温度'
  RETURN s, r, o
  UNION ALL
  MATCH (s:Condition)-[r:CONTRA_INDICATED_FOR]->(o:Variety)
  WHERE size($variety_ids) = 0 OR o.id IN $variety_ids
  RETURN s, r, o
}
RETURN s.id AS subject_id,
       coalesce(s.name, s.id) AS subject,
       labels(s)[0] AS subject_label,
       type(r) AS predicate,
       o.id AS object_id,
       coalesce(o.name, o.id) AS object,
       labels(o)[0] AS object_label,
       o.category AS object_category,
       coalesce(r.value, o.value) AS value,
       coalesce(r.unit, o.unit) AS unit,
       coalesce(r.value_min, o.value_min) AS value_min,
       coalesce(r.value_max, o.value_max) AS value_max,
       coalesce(r.status, 'anchor') AS status,
       coalesce(r.confidence, 0.5) AS confidence,
       r.source_ids AS source_ids,
       r.locator AS locator,
       r.quote AS quote,
       properties(r) AS properties
ORDER BY confidence DESC, subject_id, object_id
LIMIT $limit
