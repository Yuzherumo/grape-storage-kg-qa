// graph/queries/shelf_life.cypher
// 意图：shelf_life —— 品种 -HAS_INDICATOR_VALUE-> 耐贮性  ∪  条件 -AFFECTS-> 耐贮性
// 执行方：app/store/neo4j_store.py（参数化）；LocalStore.query_cypher 复用做展示
// 参数（均必传；列表可为空 []，不可为 null）：
//   $variety_ids list[str]  品种 id；[] = 不限品种
//   $limit       int        返回条数上限
// 语义与 LocalStore._load_shelf_life 一致：
//   1) 目标品种的耐贮性数值（耐贮性 id=shelf_life 或 name 含「耐贮性」）
//   2) 所有影响耐贮性的条件（便于给「怎么存得更久」的依据）
CALL {
  MATCH (s:Variety)-[r:HAS_INDICATOR_VALUE]->(o:QualityIndicator)
  WHERE (size($variety_ids) = 0 OR s.id IN $variety_ids)
    AND (o.id = 'shelf_life' OR o.name CONTAINS '耐贮性')
  RETURN s, r, o
  UNION ALL
  MATCH (s:Condition)-[r:AFFECTS]->(o:QualityIndicator)
  WHERE o.id = 'shelf_life' OR o.name CONTAINS '耐贮性'
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
