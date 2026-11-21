// =============================================================================
// graph/schema.cypher —— 鲜食葡萄采后贮藏知识图谱 · 约束与索引
// 项目：农客松 2026 主赛道 · 方向二「生命系统」
// 归属：kg-builder    语法基线：Neo4j 5.x（CREATE ... IF NOT EXISTS，可重复执行）
// 用法：cypher-shell -f graph/schema.cypher
//      或 scripts/load_neo4j.py 启动时先执行本文件
// 说明：5 类业务节点各一个 id 唯一约束 + name/category 索引；
//       标签枚举与 data/schema.json 保持一致（Variety/Condition/QualityIndicator/Disease/Source）。
// =============================================================================

// -----------------------------------------------------------------------------
// 1. 唯一约束（5 类标签 × id）—— 幂等，可重复执行
// -----------------------------------------------------------------------------
CREATE CONSTRAINT variety_id_unique IF NOT EXISTS
FOR (n:Variety) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT condition_id_unique IF NOT EXISTS
FOR (n:Condition) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT quality_indicator_id_unique IF NOT EXISTS
FOR (n:QualityIndicator) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT disease_id_unique IF NOT EXISTS
FOR (n:Disease) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT source_id_unique IF NOT EXISTS
FOR (n:Source) REQUIRE n.id IS UNIQUE;

// -----------------------------------------------------------------------------
// 2. name 索引（中文规范名直查；实体链接/管理后台用）
// -----------------------------------------------------------------------------
CREATE INDEX variety_name_idx IF NOT EXISTS
FOR (n:Variety) ON (n.name);

CREATE INDEX condition_name_idx IF NOT EXISTS
FOR (n:Condition) ON (n.name);

CREATE INDEX quality_indicator_name_idx IF NOT EXISTS
FOR (n:QualityIndicator) ON (n.name);

CREATE INDEX disease_name_idx IF NOT EXISTS
FOR (n:Disease) ON (n.name);

CREATE INDEX source_title_idx IF NOT EXISTS
FOR (n:Source) ON (n.title);

// -----------------------------------------------------------------------------
// 3. category 索引（按 温度/湿度/气调/化学/包装/采后操作/环境风险 分类检索）
// -----------------------------------------------------------------------------
CREATE INDEX condition_category_idx IF NOT EXISTS
FOR (n:Condition) ON (n.category);

// -----------------------------------------------------------------------------
// 4. 关系属性索引（证据溯源常用：status / source_ids 用于过滤）
//    Neo4j 5 关系索引；若目标实例为 4.x，可注释掉本节（不影响的语义）。
// -----------------------------------------------------------------------------
CREATE INDEX rel_status_idx IF NOT EXISTS
FOR ()-[r:REQUIRES]-() ON (r.status);

CREATE INDEX rel_affects_status_idx IF NOT EXISTS
FOR ()-[r:AFFECTS]-() ON (r.status);

CREATE INDEX rel_contra_status_idx IF NOT EXISTS
FOR ()-[r:CONTRA_INDICATED_FOR]-() ON (r.status);

// -----------------------------------------------------------------------------
// 5. 自检（可选执行，确认约束/索引已生效）
//    SHOW CONSTRAINTS;
//    SHOW INDEXES;
// =============================================================================
