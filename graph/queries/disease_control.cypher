// graph/queries/disease_control.cypher
// 意图：disease_control —— 病害 → PREVENTED_BY / INDUCED_BY → 条件（怎么防 / 什么导致）
// 执行方：app/store/neo4j_store.py（参数化）；LocalStore.query_cypher 复用做展示
// 参数（均必传；列表可为空 []，不可为 null）：
//   $disease_ids list[str]  病害 id；[] = 全部病害
//   $limit       int        返回条数上限
// 语义与 LocalStore._load_disease_control 一致。
// 注：LocalStore 在「只命中品种、未命中病害」时会用 SUSCEPTIBLE_TO 推出相关病害，
//     这段推断由 planner 负责；Neo4j 侧请由 planner 把病害 id 传进 $disease_ids。
MATCH (s:Disease)-[r]->(o:Condition)
WHERE type(r) IN ['PREVENTED_BY', 'INDUCED_BY']
  AND (size($disease_ids) = 0 OR s.id IN $disease_ids)
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
