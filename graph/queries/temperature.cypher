// graph/queries/temperature.cypher
// 意图：temperature —— 品种 → REQUIRES → 温度类 Condition
// 执行方：app/store/neo4j_store.py（参数化，禁止拼接）；LocalStore.query_cypher 复用本文件做 UI 展示
// 参数（Neo4j 驱动均必传；列表可为空 []，不可为 null）：
//   $variety_ids   list[str]  品种 node id；[] = 不限品种
//   $condition_ids list[str]  条件 node id；非空时按精确条件过滤（忽略 category）
//   $limit         int        返回条数上限（store 传 k，默认 6）
// 返回列与 app/store/base.py::build_evidence 对齐（subject_id/subject/predicate/object/.../properties）。
// 语义与 LocalStore._load_condition_intent(温度) 一致。
MATCH (s:Variety)-[r:REQUIRES]->(o:Condition)
WHERE (size($variety_ids) = 0 OR s.id IN $variety_ids)
  AND o.category = '温度'
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
