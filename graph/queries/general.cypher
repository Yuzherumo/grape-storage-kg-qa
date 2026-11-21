// graph/queries/general.cypher
// 意图：general —— 命中实体的任意相连边（兜底），辅以关键词命中 name/quote
// 执行方：app/store/neo4j_store.py（参数化）；LocalStore.query_cypher 复用做展示
// 参数（均必传；列表可为空 []，不可为 null）：
//   $entity_ids list[str]  命中实体 id（任意标签）
//   $keywords   list[str]  关键词兜底（可为空）
//   $limit      int        返回条数上限
// 语义与 LocalStore._load_general 一致（local 额外会用 params["question"] 做实体名兜底，
// 该推断本应由 planner 转成 $entity_ids/$keywords；本地后端为容错保留）。
MATCH (s)-[r]->(o)
WHERE (
        (size($entity_ids) > 0 AND (s.id IN $entity_ids OR o.id IN $entity_ids))
     OR (size($keywords) > 0 AND any(
            kw IN $keywords
            WHERE size(kw) >= 2
              AND (
                   toLower(coalesce(s.name, '')) CONTAINS toLower(kw)
                OR toLower(coalesce(o.name, '')) CONTAINS toLower(kw)
                OR toLower(coalesce(r.quote, '')) CONTAINS toLower(kw)
              )
        ))
     OR (size($entity_ids) = 0 AND size($keywords) = 0)
      )
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
