// graph/queries/disease_risk.cypher
// 意图：disease_risk —— 病害 -INDUCED_BY-> 条件  ∪  品种 -SUSCEPTIBLE_TO-> 病害（风险来源/易感品种）
// 执行方：app/store/neo4j_store.py（参数化）；LocalStore.query_cypher 复用做展示
// 参数（均必传；列表可为空 []，不可为 null）：
//   $disease_ids list[str]  病害 id；[] = 不限
//   $variety_ids list[str]  品种 id；[] = 不限
//   $limit       int        返回条数上限
// 语义与 LocalStore._load_disease_risk 一致。
CALL {
  MATCH (s:Disease)-[r:INDUCED_BY]->(o:Condition)
  WHERE (size($disease_ids) = 0 OR s.id IN $disease_ids)
  RETURN s, r, o
  UNION ALL
  MATCH (s:Variety)-[r:SUSCEPTIBLE_TO]->(o:Disease)
  WHERE (size($variety_ids) = 0 OR s.id IN $variety_ids)
    AND (size($disease_ids) = 0 OR o.id IN $disease_ids)
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
