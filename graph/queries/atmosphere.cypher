// graph/queries/atmosphere.cypher
// 意图：atmosphere —— 品种 → REQUIRES → 气调类 Condition（O₂/CO₂ 等）
// 执行方：app/store/neo4j_store.py（参数化）；LocalStore.query_cypher 复用做展示
// 参数（均必传；列表可为空 []，不可为 null）：
//   $variety_ids   list[str]  品种 id；[] = 不限品种
//   $condition_ids list[str]  条件 id；非空时按精确条件过滤
//   $limit         int        返回条数上限
// 语义与 LocalStore._load_condition_intent(气调) 一致。
MATCH (s:Variety)-[r:REQUIRES]->(o:Condition)
WHERE (size($variety_ids) = 0 OR s.id IN $variety_ids)
  AND o.category = '气调'
  AND (size($condition_ids) = 0 OR o.id IN $condition_ids)
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
