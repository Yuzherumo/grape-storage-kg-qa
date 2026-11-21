// graph/queries/contraindication.cypher
// 意图：contraindication —— 条件 -CONTRA_INDICATED_FOR-> 品种（禁忌）∪ 条件 -ALTERNATIVE_TO-> 替代条件
// 执行方：app/store/neo4j_store.py（参数化）；LocalStore.query_cypher 复用做展示
// 参数（均必传；列表可为空 []，不可为 null）：
//   $variety_ids   list[str]  品种 id；[] = 不限品种
//   $condition_ids list[str]  条件 id；非空时只返回该条件的禁忌与替代
//   $limit         int        返回条数上限
// 语义与 LocalStore._load_contraindication 一致。
CALL {
  MATCH (s:Condition)-[r:CONTRA_INDICATED_FOR]->(o:Variety)
  WHERE (size($variety_ids) = 0 OR o.id IN $variety_ids)
    AND (size($condition_ids) = 0 OR s.id IN $condition_ids)
  RETURN s, r, o
  UNION ALL
  MATCH (s:Condition)-[r:ALTERNATIVE_TO]->(o:Condition)
  WHERE (
          (size($condition_ids) > 0 AND (s.id IN $condition_ids OR o.id IN $condition_ids))
       OR (size($condition_ids) = 0 AND size($variety_ids) > 0 AND (
              EXISTS {
                MATCH (o)-[:CONTRA_INDICATED_FOR]->(v:Variety)
                WHERE v.id IN $variety_ids
              }
           OR EXISTS {
                MATCH (s)-[:CONTRA_INDICATED_FOR]->(v:Variety)
                WHERE v.id IN $variety_ids
              }
          ))
       OR (size($condition_ids) = 0 AND size($variety_ids) = 0)
      )
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
