// =============================================================================
// graph/init_rels.cypher —— 图谱关系初始化（自动生成，请勿手改）
// 由 scripts/gen_cypher.py 从 data/triples.csv 生成
// 幂等：MERGE (a)-[r:PREDICATE {sid: ...}]->(b) —— 可重复执行
// 统计：共 71 条关系（REQUIRES 14，CONTRA_INDICATED_FOR 3，AFFECTS 19，SUSCEPTIBLE_TO 8，PREVENTED_BY 8，INDUCED_BY 6，ALTERNATIVE_TO 3，INDICATES 2，HAS_INDICATOR_VALUE 8）
// 关系属性含 source_ids/locator/quote/status/confidence（证据溯源必需）
// =============================================================================

// 节点须先由 graph/init_nodes.cypher 建立；按谓词分组，顺序执行即可
MATCH (n) RETURN count(n) AS node_count_before;


// ---------------- REQUIRES（14 条） ----------------
MATCH (a:Variety {id: 'crimson_seedless'}), (b:Condition {id: 'ice_temp'})
MERGE (a)-[r:REQUIRES]->(b)
  SET r.sid = 'a_crimson_ice',
         r.subject = '克瑞森无核',
         r.predicate = 'REQUIRES',
         r.object = '冰温贮藏 -0.5~0℃',
         r.value_min = -0.5,
         r.value_max = 0,
         r.unit = '℃',
         r.stage = '贮藏',
         r.reason = '克瑞森无核晚熟耐贮，近冰温贮藏可进一步延长货架期',
         r.source_ids = ['paper_ice_temp', 'review_grape_storage'],
         r.locator = '《1-MCP结合ClO2处理对冰温贮藏红提葡萄生理品质的影响》结果章节；页码待补',
         r.status = 'anchor',
         r.confidence = 0.58,
         r.note = '待核验点：冰温实证对象为红提，克瑞森无核需另行验证；冻害临界温度待查';
MATCH (a:Variety {id: 'hutai_8'}), (b:Condition {id: 'cold_0'})
MERGE (a)-[r:REQUIRES]->(b)
  SET r.sid = 'a_hutai8_cold0',
         r.subject = '户太八号',
         r.predicate = 'REQUIRES',
         r.object = '低温冷藏 0±0.5℃',
         r.value_min = -0.5,
         r.value_max = 0.5,
         r.unit = '℃',
         r.stage = '贮藏',
         r.reason = '户太八号冷藏以 0±0.5℃ 为主，配合预冷可减少果梗褐变',
         r.source_ids = ['gbt16862_2026', 'review_grape_storage'],
         r.locator = 'GB/T 16862-2026 冷藏技术要求相关条款（openstd 在线预览；条款号/页码待获取原文后补）',
         r.status = 'anchor',
         r.confidence = 0.62,
         r.note = '待核验点：户太八号冷藏温度文献数据少，按通用冷藏区间填写，需试验验证';
MATCH (a:Variety {id: 'kyoho'}), (b:Condition {id: 'cold_neg1'})
MERGE (a)-[r:REQUIRES]->(b)
  SET r.sid = 'a_kyoho_cold_neg1',
         r.subject = '巨峰',
         r.predicate = 'REQUIRES',
         r.object = '低温冷藏 -1~0℃',
         r.value_min = -1,
         r.value_max = 0,
         r.unit = '℃',
         r.stage = '贮藏',
         r.reason = '巨峰冷藏适温偏向 -1~0℃，低于 -1℃ 有冻伤风险，高于 0℃ 呼吸与落粒加快',
         r.source_ids = ['gbt16862_2026', 'review_grape_storage'],
         r.locator = '7.3 冷藏条件',
         r.quote = '葡萄适宜冷藏温度为-1℃~0℃,相对湿度为90%~95%。',
         r.status = 'verified',
         r.confidence = 0.68,
         r.note = '待核验点：巨峰品种专属温度区间原文（标准为通用范围，品种差异需原文支持）；按 GB/T 16862-2026（用户提供 PDF 全文，文本经 pdfminer 提取） 升级：通用冷藏区间，与条文一致';
MATCH (a:Variety {id: 'muscat_hamburg'}), (b:Condition {id: 'rh_90_95'})
MERGE (a)-[r:REQUIRES]->(b)
  SET r.sid = 'a_muscat_rh',
         r.subject = '玫瑰香',
         r.predicate = 'REQUIRES',
         r.object = '相对湿度 90~95%',
         r.value_min = 90,
         r.value_max = 95,
         r.unit = '%',
         r.stage = '贮藏',
         r.reason = '玫瑰香果梗细、易失水干枯，需 90~95% 高湿配合低温冷藏',
         r.source_ids = ['gbt16862_2026', 'review_grape_storage'],
         r.locator = '7.3 冷藏条件',
         r.quote = '葡萄适宜冷藏温度为-1℃~0℃,相对湿度为90%~95%。',
         r.status = 'verified',
         r.confidence = 0.66,
         r.note = '待核验点：玫瑰香湿度需求原文；高湿结露与灰霉风险的平衡点待核；按 GB/T 16862-2026（用户提供 PDF 全文，文本经 pdfminer 提取） 升级：相对湿度与条文一致';
MATCH (a:Variety {id: 'red_globe'}), (b:Condition {id: 'cold_neg1'})
MERGE (a)-[r:REQUIRES]->(b)
  SET r.sid = 'a_red_globe_cold_neg1',
         r.subject = '红地球',
         r.predicate = 'REQUIRES',
         r.object = '低温冷藏 -1~0℃',
         r.value_min = -1,
         r.value_max = 0,
         r.unit = '℃',
         r.stage = '贮藏',
         r.reason = '红地球晚熟、果梗粗，-1~0℃ 冷藏可长期保持果梗绿色与硬度',
         r.source_ids = ['gbt16862_2026', 'review_grape_storage'],
         r.locator = '7.3 冷藏条件',
         r.quote = '葡萄适宜冷藏温度为-1℃~0℃,相对湿度为90%~95%。',
         r.status = 'verified',
         r.confidence = 0.68,
         r.note = '待核验点：红地球最适冷藏温度原文；与冰温/气调组合条件待补；按 GB/T 16862-2026（用户提供 PDF 全文，文本经 pdfminer 提取） 升级：通用冷藏区间，与条文一致';
MATCH (a:Variety {id: 'summer_black'}), (b:Condition {id: 'cold_0'})
MERGE (a)-[r:REQUIRES]->(b)
  SET r.sid = 'a_summer_black_cold0',
         r.subject = '夏黑',
         r.predicate = 'REQUIRES',
         r.object = '低温冷藏 0±0.5℃',
         r.value_min = -0.5,
         r.value_max = 0.5,
         r.unit = '℃',
         r.stage = '贮藏',
         r.reason = '夏黑早熟皮薄，0±0.5℃ 冷藏可抑制呼吸并减少落粒',
         r.source_ids = ['gbt16862_2026', 'review_grape_storage'],
         r.locator = 'GB/T 16862-2026 冷藏技术要求相关条款（openstd 在线预览；条款号/页码待获取原文后补）',
         r.status = 'anchor',
         r.confidence = 0.64,
         r.note = '待核验点：夏黑冷藏温度原文数据缺失，按通用冷藏区间填写，需试验验证';
MATCH (a:Variety {id: 'victoria'}), (b:Condition {id: 'cold_chain_transport'})
MERGE (a)-[r:REQUIRES]->(b)
  SET r.sid = 'a_victoria_coldchain',
         r.subject = '维多利亚',
         r.predicate = 'REQUIRES',
         r.object = '冷链运输',
         r.stage = '出库',
         r.reason = '维多利亚早熟黄绿色品种，出库后需全程冷链，断冷即迅速褐变与落粒',
         r.source_ids = ['gbt16862_2026', 'review_packaging_logistics'],
         r.locator = '8.1 运输',
         r.quote = '葡萄宜采用冷藏车或保温车运输,运输温度宜控制在0℃~5℃,装运工具应清洁、干燥,不应与有毒、有害物质混装混运。',
         r.status = 'verified',
         r.confidence = 0.62,
         r.note = '待核验点：冷链温度上限与断冷时限原文；维多利亚专属数据待补；按 GB/T 16862-2026（用户提供 PDF 全文，文本经 pdfminer 提取） 升级：运输温度 0℃~5℃ 为条文原文';
MATCH (a:Variety {id: 'shine_muscat'}), (b:Condition {id: 'mcp_1'})
MERGE (a)-[r:REQUIRES]->(b)
  SET r.sid = 'sm_req_1mcp',
         r.subject = '阳光玫瑰',
         r.predicate = 'REQUIRES',
         r.object = '1-MCP 处理',
         r.value = 1,
         r.unit = 'μL/L',
         r.stage = '贮藏',
         r.reason = '1 μL/L 1-MCP 熏蒸 12h 可抑制乙烯作用，减轻落粒与软化',
         r.source_ids = ['paper_so2_1mcp_shine', 'paper_so2_pad_1mcp_shine'],
         r.locator = '《1-MCP和SO2处理对阳光玫瑰葡萄贮藏品质及风味的影响》结果与分析章节；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.65,
         r.note = '待核验点：浓度（1 μL/L）与处理时长（12h）原文数值待核；两篇论文处理条件可能不同，需以原文实验设计为准';
MATCH (a:Variety {id: 'shine_muscat'}), (b:Condition {id: 'ca_co2'})
MERGE (a)-[r:REQUIRES]->(b)
  SET r.sid = 'sm_req_co2',
         r.subject = '阳光玫瑰',
         r.predicate = 'REQUIRES',
         r.object = '气调 CO₂ 1~3%',
         r.value_min = 1,
         r.value_max = 3,
         r.unit = '%',
         r.stage = '贮藏',
         r.reason = '1~3% CO₂ 抑制灰霉等真菌生长，超过 5% 易致果肉褐变与异味',
         r.source_ids = ['review_packaging_logistics', 'review_grape_storage'],
         r.locator = '《葡萄物流及贮藏保鲜包装技术研究现状与展望》（包装工程 2023, 44(23)）综述正文；页码待补',
         r.status = 'anchor',
         r.confidence = 0.68,
         r.note = '待核验点：CO₂ 适宜区间与伤害阈值原文；阳光玫瑰对 CO₂ 敏感性数据待查';
MATCH (a:Variety {id: 'shine_muscat'}), (b:Condition {id: 'cold_0'})
MERGE (a)-[r:REQUIRES]->(b)
  SET r.sid = 'sm_req_cold0',
         r.subject = '阳光玫瑰',
         r.predicate = 'REQUIRES',
         r.object = '低温冷藏 0±0.5℃',
         r.value = 0,
         r.value_min = -0.5,
         r.value_max = 0.5,
         r.unit = '℃',
         r.stage = '贮藏',
         r.reason = '0±0.5℃ 抑制呼吸与灰霉扩展，是鲜食葡萄冷藏的基准温度区间',
         r.source_ids = ['gbt16862_2026', 'review_grape_storage'],
         r.locator = 'GB/T 16862-2026 冷藏技术要求相关条款（openstd 在线预览；条款号/页码待获取原文后补）',
         r.status = 'anchor',
         r.confidence = 0.78,
         r.note = '待核验点：标准正文规定的冷藏温度区间原文、条款号与页码；±0.5℃ 为工程化表述，需与标准条款逐字核对';
MATCH (a:Variety {id: 'shine_muscat'}), (b:Condition {id: 'ice_temp'})
MERGE (a)-[r:REQUIRES]->(b)
  SET r.sid = 'sm_req_ice',
         r.subject = '阳光玫瑰',
         r.predicate = 'REQUIRES',
         r.object = '冰温贮藏 -0.5~0℃',
         r.value_min = -0.5,
         r.value_max = 0,
         r.unit = '℃',
         r.stage = '贮藏',
         r.reason = '近冰温（-0.5~0℃）可进一步抑制呼吸与腐烂，但需精准控温避免冻伤',
         r.source_ids = ['paper_ice_temp', 'review_grape_storage'],
         r.locator = '《1-MCP结合ClO2处理对冰温贮藏红提葡萄生理品质的影响》结果章节；页码待补',
         r.status = 'anchor',
         r.confidence = 0.6,
         r.note = '待核验点：冰温数据来自红地球（红提）实证，阳光玫瑰需另行验证；冻害临界温度待查';
MATCH (a:Variety {id: 'shine_muscat'}), (b:Condition {id: 'ca_o2'})
MERGE (a)-[r:REQUIRES]->(b)
  SET r.sid = 'sm_req_o2',
         r.subject = '阳光玫瑰',
         r.predicate = 'REQUIRES',
         r.object = '气调 O₂ 3~5%',
         r.value_min = 3,
         r.value_max = 5,
         r.unit = '%',
         r.stage = '贮藏',
         r.reason = '低氧（3~5% O₂）抑制呼吸与乙烯合成，可延长货架期',
         r.source_ids = ['review_packaging_logistics', 'review_grape_storage'],
         r.locator = '《葡萄物流及贮藏保鲜包装技术研究现状与展望》（包装工程 2023, 44(23)）综述正文；页码待补',
         r.status = 'anchor',
         r.confidence = 0.68,
         r.note = '待核验点：综述给出的葡萄最适 O₂ 区间原文；不同品种/包装差异需核对，低于 2% 有无氧呼吸风险';
MATCH (a:Variety {id: 'shine_muscat'}), (b:Condition {id: 'precool_fast'})
MERGE (a)-[r:REQUIRES]->(b)
  SET r.sid = 'sm_req_precool',
         r.subject = '阳光玫瑰',
         r.predicate = 'REQUIRES',
         r.object = '快速预冷（12h 内至 0℃）',
         r.stage = '预冷',
         r.reason = '采后 12h 内预冷至 0℃ 可显著降低呼吸热与灰霉侵染率',
         r.source_ids = ['gbt16862_2026', 'review_grape_storage'],
         r.locator = '5.3.2 预冷条件',
         r.quote = '冷库预冷时环境温度为-1℃~0℃,压差预冷时环境温度为0℃~1℃。宜在采后12h内将葡萄果实中心温度降至0℃。',
         r.status = 'verified',
         r.confidence = 0.72,
         r.note = '待核验点：标准/综述中预冷时限（12h 或 24h）与终温原文；实际以库房降温能力为准；按 GB/T 16862-2026（用户提供 PDF 全文，文本经 pdfminer 提取） 升级：12h 内降至 0℃ 为条文原文';
MATCH (a:Variety {id: 'shine_muscat'}), (b:Condition {id: 'rh_90_95'})
MERGE (a)-[r:REQUIRES]->(b)
  SET r.sid = 'sm_req_rh',
         r.subject = '阳光玫瑰',
         r.predicate = 'REQUIRES',
         r.object = '相对湿度 90~95%',
         r.value_min = 90,
         r.value_max = 95,
         r.unit = '%',
         r.stage = '贮藏',
         r.reason = '90~95% RH 可减少浆果失水与果梗干枯，同时避免结露诱发灰霉',
         r.source_ids = ['gbt16862_2026', 'review_grape_storage'],
         r.locator = '7.3 冷藏条件',
         r.quote = '葡萄适宜冷藏温度为-1℃~0℃,相对湿度为90%~95%。',
         r.status = 'verified',
         r.confidence = 0.75,
         r.note = '待核验点：标准中相对湿度上限/下限原文；高湿结露风险需与通风条款一并核对；按 GB/T 16862-2026（用户提供 PDF 全文，文本经 pdfminer 提取） 升级：相对湿度与条文一致';

// ---------------- CONTRA_INDICATED_FOR（3 条） ----------------
MATCH (a:Condition {id: 'so2_fumigation'}), (b:Variety {id: 'muscat_hamburg'})
MERGE (a)-[r:CONTRA_INDICATED_FOR]->(b)
  SET r.sid = 'b_kyoho_contra_so2',
         r.subject = 'SO₂ 熏蒸',
         r.predicate = 'CONTRA_INDICATED_FOR',
         r.object = '玫瑰香',
         r.stage = '贮藏',
         r.severity = '中',
         r.reason = '玫瑰香对 SO₂ 较敏感，熏蒸剂量偏高易致果梗褐变与风味劣变，宜改用低剂量缓释',
         r.source_ids = ['gbt16862_2026', 'ops_grape_ny1199'],
         r.locator = 'GB/T 16862-2026 冷藏技术要求相关条款（openstd 在线预览；条款号/页码待获取原文后补）',
         r.status = 'anchor',
         r.confidence = 0.66,
         r.note = '待核验点：玫瑰香 SO₂ 敏感性与伤害阈值原文；本条目为禁忌组（B），已备 2 个来源待核对';
MATCH (a:Condition {id: 'high_co2'}), (b:Variety {id: 'shine_muscat'})
MERGE (a)-[r:CONTRA_INDICATED_FOR]->(b)
  SET r.sid = 'b_redglobe_contra_highco2',
         r.subject = '高 CO₂ >5%',
         r.predicate = 'CONTRA_INDICATED_FOR',
         r.object = '阳光玫瑰',
         r.stage = '贮藏',
         r.severity = '中',
         r.reason = '阳光玫瑰对高 CO₂ 敏感，>5% 易致果肉褐变、异味与落粒，气调应控制在 1~3% CO₂',
         r.source_ids = ['review_packaging_logistics', 'review_shine_muscat'],
         r.locator = '《葡萄物流及贮藏保鲜包装技术研究现状与展望》（包装工程 2023, 44(23)）综述正文；页码待补',
         r.status = 'anchor',
         r.confidence = 0.64,
         r.note = '待核验点：阳光玫瑰 CO₂ 伤害阈值（%）与褐变/异味原文数据；本条目为禁忌组（B），已备 2 个来源';
MATCH (a:Condition {id: 'so2_fumigation'}), (b:Variety {id: 'shine_muscat'})
MERGE (a)-[r:CONTRA_INDICATED_FOR]->(b)
  SET r.sid = 'sm_contra_so2',
         r.subject = 'SO₂ 熏蒸',
         r.predicate = 'CONTRA_INDICATED_FOR',
         r.object = '阳光玫瑰',
         r.stage = '贮藏',
         r.severity = '高',
         r.reason = '阳光玫瑰对 SO₂ 敏感，熏蒸高剂量易致果皮漂白、果梗褐变与风味劣变，生产上宜改用低剂量缓释',
         r.source_ids = ['paper_so2_1mcp_shine', 'paper_clo2_so2_shine', 'paper_so2_pad_1mcp_shine'],
         r.locator = 'An integrated transcriptomic and metabolomic analysis of Shine Muscat grapes ... ClO2/SO2 storage（SCI）结果章节；页码待补',
         r.status = 'anchor',
         r.confidence = 0.72,
         r.note = '待核验点：SO₂ 熏蒸剂量-伤害阈值（ppm·h）与漂白/异味的原文数据；本条目为禁忌（B 组），已备 3 篇来源待逐条核对';

// ---------------- AFFECTS（19 条） ----------------
MATCH (a:Condition {id: 'ca_co2'}), (b:QualityIndicator {id: 'decay_rate'})
MERGE (a)-[r:AFFECTS]->(b)
  SET r.sid = 'c_caco2_decay',
         r.subject = '气调 CO₂ 1~3%',
         r.predicate = 'AFFECTS',
         r.object = '腐烂率',
         r.stage = '贮藏',
         r.effect = 'decrease',
         r.level = '中',
         r.reason = '适宜 CO₂ 抑制灰霉/青霉生长，降低腐烂率',
         r.source_ids = ['review_packaging_logistics', 'review_grape_storage'],
         r.locator = '《葡萄物流及贮藏保鲜包装技术研究现状与展望》（包装工程 2023, 44(23)）综述正文；页码待补',
         r.status = 'anchor',
         r.confidence = 0.7,
         r.note = '待核验点：CO₂ 1~3% 抑菌效果原文数据';
MATCH (a:Condition {id: 'ca_o2'}), (b:QualityIndicator {id: 'respiration'})
MERGE (a)-[r:AFFECTS]->(b)
  SET r.sid = 'c_cao2_resp',
         r.subject = '气调 O₂ 3~5%',
         r.predicate = 'AFFECTS',
         r.object = '呼吸强度',
         r.stage = '贮藏',
         r.effect = 'decrease',
         r.level = '中',
         r.reason = '低氧抑制有氧呼吸，降低呼吸强度',
         r.source_ids = ['review_packaging_logistics', 'review_grape_storage'],
         r.locator = '《葡萄物流及贮藏保鲜包装技术研究现状与展望》（包装工程 2023, 44(23)）综述正文；页码待补',
         r.status = 'anchor',
         r.confidence = 0.7,
         r.note = '待核验点：O₂ 浓度与呼吸强度对应数据原文';
MATCH (a:Condition {id: 'ca_o2'}), (b:QualityIndicator {id: 'vc'})
MERGE (a)-[r:AFFECTS]->(b)
  SET r.sid = 'c_cao2_vc',
         r.subject = '气调 O₂ 3~5%',
         r.predicate = 'AFFECTS',
         r.object = '维生素C',
         r.stage = '贮藏',
         r.effect = 'decrease',
         r.level = '中',
         r.reason = '低氧环境降低抗坏血酸氧化酶活性，减缓 VC 氧化损失',
         r.source_ids = ['review_packaging_logistics', 'review_grape_storage'],
         r.locator = '《葡萄物流及贮藏保鲜包装技术研究现状与展望》（包装工程 2023, 44(23)）综述正文；页码待补',
         r.status = 'anchor',
         r.confidence = 0.64,
         r.note = '待核验点：气调 vs 空气贮藏 VC 含量变化原文数据。effect=decrease 语义为『VC 损失（下降）减缓』，非低氧导致 VC 绝对值下降';
MATCH (a:Condition {id: 'cold_0'}), (b:QualityIndicator {id: 'decay_rate'})
MERGE (a)-[r:AFFECTS]->(b)
  SET r.sid = 'c_cold0_decay',
         r.subject = '低温冷藏 0±0.5℃',
         r.predicate = 'AFFECTS',
         r.object = '腐烂率',
         r.stage = '贮藏',
         r.effect = 'decrease',
         r.level = '强',
         r.reason = '低温显著抑制灰霉等真菌生长，冷藏期腐烂率远低于常温',
         r.source_ids = ['gbt16862_2026', 'review_grape_storage'],
         r.locator = 'GB/T 16862-2026 冷藏技术要求相关条款（openstd 在线预览；条款号/页码待获取原文后补）',
         r.status = 'anchor',
         r.confidence = 0.7,
         r.note = '待核验点：不同温度下腐烂率对比数据原文';
MATCH (a:Condition {id: 'cold_0'}), (b:QualityIndicator {id: 'ethylene'})
MERGE (a)-[r:AFFECTS]->(b)
  SET r.sid = 'c_cold0_ethylene',
         r.subject = '低温冷藏 0±0.5℃',
         r.predicate = 'AFFECTS',
         r.object = '乙烯释放率',
         r.stage = '贮藏',
         r.effect = 'decrease',
         r.level = '中',
         r.reason = '低温降低 ACC 氧化酶活性，减少乙烯合成与释放',
         r.source_ids = ['review_grape_storage', 'review_table_grape_en'],
         r.locator = '《鲜食葡萄采后保鲜技术研究进展》（保鲜与加工 2024, 24(12)）综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.7,
         r.note = '待核验点：低温下乙烯释放率下降幅度原文数据';
MATCH (a:Condition {id: 'cold_0'}), (b:QualityIndicator {id: 'firmness'})
MERGE (a)-[r:AFFECTS]->(b)
  SET r.sid = 'c_cold0_firmness',
         r.subject = '低温冷藏 0±0.5℃',
         r.predicate = 'AFFECTS',
         r.object = '硬度',
         r.stage = '贮藏',
         r.effect = 'decrease',
         r.level = '中',
         r.reason = '低温降低果胶酶与纤维素酶活性，减缓果肉软化，使贮藏期硬度下降幅度明显减小',
         r.source_ids = ['review_grape_storage', 'review_table_grape_en'],
         r.locator = '《鲜食葡萄采后保鲜技术研究进展》（保鲜与加工 2024, 24(12)）综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.7,
         r.note = '待核验点：不同温度下硬度（N）随时间变化曲线原文。effect=decrease 语义为『硬度下降（软化）减缓』，即低温使硬度降幅变小，非硬度绝对值降低方向本身';
MATCH (a:Condition {id: 'cold_0'}), (b:QualityIndicator {id: 'shelf_life'})
MERGE (a)-[r:AFFECTS]->(b)
  SET r.sid = 'c_cold0_shelf',
         r.subject = '低温冷藏 0±0.5℃',
         r.predicate = 'AFFECTS',
         r.object = '耐贮性',
         r.stage = '贮藏',
         r.effect = 'increase',
         r.level = '强',
         r.reason = '规范冷藏可将货架期从常温数天延长至数月',
         r.source_ids = ['gbt16862_2026', 'review_grape_storage'],
         r.locator = 'GB/T 16862-2026 冷藏技术要求相关条款（openstd 在线预览；条款号/页码待获取原文后补）',
         r.status = 'anchor',
         r.confidence = 0.7,
         r.note = '待核验点：冷藏期与耐贮期对应原文数据';
MATCH (a:Condition {id: 'high_co2'}), (b:QualityIndicator {id: 'browning_index'})
MERGE (a)-[r:AFFECTS]->(b)
  SET r.sid = 'c_highco2_browning',
         r.subject = '高 CO₂ >5%',
         r.predicate = 'AFFECTS',
         r.object = '褐变指数',
         r.stage = '贮藏',
         r.effect = 'increase',
         r.level = '中',
         r.reason = 'CO₂ 伤害导致果肉/果皮褐变，褐变指数上升',
         r.source_ids = ['review_packaging_logistics', 'review_grape_storage'],
         r.locator = '《葡萄物流及贮藏保鲜包装技术研究现状与展望》（包装工程 2023, 44(23)）综述正文；页码待补',
         r.status = 'anchor',
         r.confidence = 0.7,
         r.note = '待核验点：CO₂ 伤害与褐变指数阈值原文';
MATCH (a:Condition {id: 'high_co2'}), (b:QualityIndicator {id: 'off_flavor'})
MERGE (a)-[r:AFFECTS]->(b)
  SET r.sid = 'c_highco2_offflavor',
         r.subject = '高 CO₂ >5%',
         r.predicate = 'AFFECTS',
         r.object = '异味/风味偏离',
         r.stage = '贮藏',
         r.effect = 'increase',
         r.level = '强',
         r.reason = '高 CO₂ 诱导无氧呼吸与乙醇/乙醛积累，产生异味',
         r.source_ids = ['review_packaging_logistics', 'review_grape_storage'],
         r.locator = '《葡萄物流及贮藏保鲜包装技术研究现状与展望》（包装工程 2023, 44(23)）综述正文；页码待补',
         r.status = 'anchor',
         r.confidence = 0.7,
         r.note = '待核验点：CO₂ 浓度与异味评分原文曲线';
MATCH (a:Condition {id: 'ozone'}), (b:QualityIndicator {id: 'decay_rate'})
MERGE (a)-[r:AFFECTS]->(b)
  SET r.sid = 'c_ozone_decay',
         r.subject = '臭氧处理',
         r.predicate = 'AFFECTS',
         r.object = '腐烂率',
         r.stage = '贮藏',
         r.effect = 'decrease',
         r.level = '中',
         r.reason = '臭氧（O₃）破坏病原菌细胞膜并降低表面菌量，可延缓腐烂发展；需控制浓度避免伤果',
         r.source_ids = ['review_grape_storage', 'review_packaging_logistics'],
         r.locator = '《葡萄物流及贮藏保鲜包装技术研究现状与展望》（包装工程 2023, 44(23)）综述正文；页码待补',
         r.status = 'anchor',
         r.confidence = 0.66,
         r.note = '待核验点：臭氧浓度/处理时长与腐烂率下降幅度的原文数据；effect=decrease 指腐烂率下降（抑制），非臭氧使腐烂增加';
MATCH (a:Condition {id: 'precool_fast'}), (b:QualityIndicator {id: 'decay_rate'})
MERGE (a)-[r:AFFECTS]->(b)
  SET r.sid = 'c_precool_decay',
         r.subject = '快速预冷（12h 内至 0℃）',
         r.predicate = 'AFFECTS',
         r.object = '腐烂率',
         r.stage = '预冷',
         r.effect = 'decrease',
         r.level = '中',
         r.reason = '快速预冷缩短高温窗口期，抑制孢子萌发，降低腐烂率',
         r.source_ids = ['review_grape_storage', 'gbt16862_2026'],
         r.locator = '《鲜食葡萄采后保鲜技术研究进展》（保鲜与加工 2024, 24(12)）综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.7,
         r.note = '待核验点：预冷时限与腐烂率下降对应数据';
MATCH (a:Condition {id: 'rh_low'}), (b:QualityIndicator {id: 'weight_loss'})
MERGE (a)-[r:AFFECTS]->(b)
  SET r.sid = 'c_rh_low_weightloss',
         r.subject = '低湿环境 RH<90%',
         r.predicate = 'AFFECTS',
         r.object = '失重率',
         r.stage = '贮藏',
         r.effect = 'increase',
         r.level = '强',
         r.reason = '低湿加大水汽压差，蒸腾失水加快、失重率显著上升',
         r.source_ids = ['gbt16862_2026', 'review_grape_storage'],
         r.locator = 'GB/T 16862-2026 冷藏技术要求相关条款（openstd 在线预览；条款号/页码待获取原文后补）',
         r.status = 'anchor',
         r.confidence = 0.7,
         r.note = '待核验点：RH<90% 时失重率量化数据原文';
MATCH (a:Condition {id: 'rh_90_95'}), (b:QualityIndicator {id: 'stem_browning'})
MERGE (a)-[r:AFFECTS]->(b)
  SET r.sid = 'c_rh_stem',
         r.subject = '相对湿度 90~95%',
         r.predicate = 'AFFECTS',
         r.object = '果梗褐变',
         r.stage = '贮藏',
         r.effect = 'decrease',
         r.level = '中',
         r.reason = '高湿减少果梗蒸腾失水，延缓果梗干枯褐变',
         r.source_ids = ['gbt16862_2026', 'review_grape_storage'],
         r.locator = 'GB/T 16862-2026 冷藏技术要求相关条款（openstd 在线预览；条款号/页码待获取原文后补）',
         r.status = 'anchor',
         r.confidence = 0.7,
         r.note = '待核验点：湿度梯度与果梗褐变对应原文';
MATCH (a:Condition {id: 'room_temp_storage'}), (b:QualityIndicator {id: 'shelf_life'})
MERGE (a)-[r:AFFECTS]->(b)
  SET r.sid = 'c_roomtemp_shelf',
         r.subject = '常温贮运',
         r.predicate = 'AFFECTS',
         r.object = '耐贮性',
         r.stage = '贮藏',
         r.effect = 'decrease',
         r.level = '强',
         r.reason = '常温下呼吸与腐烂迅速，货架期缩短至数天',
         r.source_ids = ['review_grape_storage', 'review_table_grape_en'],
         r.locator = '《鲜食葡萄采后保鲜技术研究进展》（保鲜与加工 2024, 24(12)）综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.7,
         r.note = '待核验点：常温货架期天数原文数据';
MATCH (a:Condition {id: 'mcp_1'}), (b:QualityIndicator {id: 'berry_drop'})
MERGE (a)-[r:AFFECTS]->(b)
  SET r.sid = 'sm_aff_berrydrop_1mcp',
         r.subject = '1-MCP 处理',
         r.predicate = 'AFFECTS',
         r.object = '落粒率',
         r.stage = '贮藏',
         r.effect = 'decrease',
         r.level = '强',
         r.reason = '1-MCP 竞争性结合乙烯受体，延缓果梗离层形成，显著降低落粒率',
         r.source_ids = ['paper_so2_1mcp_shine', 'paper_so2_pad_1mcp_shine'],
         r.locator = '《1-MCP和SO2处理对阳光玫瑰葡萄贮藏品质及风味的影响》结果与分析章节；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.72,
         r.note = '待核验点：落粒率下降百分比与对照组的原文数据、处理浓度';
MATCH (a:Condition {id: 'so2_fumigation'}), (b:QualityIndicator {id: 'browning_index'})
MERGE (a)-[r:AFFECTS]->(b)
  SET r.sid = 'sm_aff_browning_so2',
         r.subject = 'SO₂ 熏蒸',
         r.predicate = 'AFFECTS',
         r.object = '褐变指数',
         r.stage = '贮藏',
         r.effect = 'increase',
         r.level = '中',
         r.reason = 'SO₂ 剂量偏高时造成果皮漂白与果梗褐变，褐变指数上升',
         r.source_ids = ['paper_so2_1mcp_shine', 'paper_clo2_so2_shine'],
         r.locator = 'An integrated transcriptomic and metabolomic analysis of Shine Muscat grapes ... ClO2/SO2 storage（SCI）结果章节；页码待补',
         r.status = 'anchor',
         r.confidence = 0.68,
         r.note = '待核验点：SO₂ 处理与褐变指数的剂量-效应原文曲线；低剂量缓释是否反向减轻褐变待核';
MATCH (a:Condition {id: 'mcp_1'}), (b:QualityIndicator {id: 'ethylene'})
MERGE (a)-[r:AFFECTS]->(b)
  SET r.sid = 'sm_aff_ethylene_1mcp',
         r.subject = '1-MCP 处理',
         r.predicate = 'AFFECTS',
         r.object = '乙烯释放率',
         r.stage = '贮藏',
         r.effect = 'decrease',
         r.level = '强',
         r.reason = '1-MCP 阻断乙烯受体信号，反馈抑制乙烯合成与释放',
         r.source_ids = ['paper_so2_1mcp_shine', 'review_shine_muscat'],
         r.locator = '《1-MCP和SO2处理对阳光玫瑰葡萄贮藏品质及风味的影响》结果与分析章节；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.7,
         r.note = '待核验点：乙烯释放率（μL/(kg·h)）下降幅度原文数据';
MATCH (a:Condition {id: 'cold_0'}), (b:QualityIndicator {id: 'respiration'})
MERGE (a)-[r:AFFECTS]->(b)
  SET r.sid = 'sm_aff_resp',
         r.subject = '低温冷藏 0±0.5℃',
         r.predicate = 'AFFECTS',
         r.object = '呼吸强度',
         r.stage = '贮藏',
         r.effect = 'decrease',
         r.level = '强',
         r.reason = '低温降低酶活性与呼吸速率，0℃ 附近呼吸强度显著低于常温',
         r.source_ids = ['review_grape_storage', 'review_table_grape_en'],
         r.locator = '《鲜食葡萄采后保鲜技术研究进展》（保鲜与加工 2024, 24(12)）综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.75,
         r.note = '待核验点：呼吸强度下降的量化数据（mg CO2/(kg·h)）原文待补';
MATCH (a:Condition {id: 'rh_90_95'}), (b:QualityIndicator {id: 'weight_loss'})
MERGE (a)-[r:AFFECTS]->(b)
  SET r.sid = 'sm_aff_weightloss_rh',
         r.subject = '相对湿度 90~95%',
         r.predicate = 'AFFECTS',
         r.object = '失重率',
         r.stage = '贮藏',
         r.effect = 'decrease',
         r.level = '中',
         r.reason = '高湿降低水汽压差，减少蒸腾失水；但需防结露',
         r.source_ids = ['gbt16862_2026', 'review_grape_storage'],
         r.locator = 'GB/T 16862-2026 冷藏技术要求相关条款（openstd 在线预览；条款号/页码待获取原文后补）',
         r.status = 'anchor',
         r.confidence = 0.75,
         r.note = '待核验点：不同 RH 下失重率对比数据原文；结露与灰霉风险的平衡点';

// ---------------- SUSCEPTIBLE_TO（8 条） ----------------
MATCH (a:Variety {id: 'kyoho'}), (b:Disease {id: 'gray_mold'})
MERGE (a)-[r:SUSCEPTIBLE_TO]->(b)
  SET r.sid = 'd_kyoho_gray',
         r.subject = '巨峰',
         r.predicate = 'SUSCEPTIBLE_TO',
         r.object = '灰霉病',
         r.stage = '贮藏',
         r.severity = '高',
         r.reason = '巨峰果穗紧密、果皮薄，灰霉病为冷藏期主要病害',
         r.source_ids = ['review_grape_storage', 'gbt16862_2026'],
         r.locator = '《鲜食葡萄采后保鲜技术研究进展》（保鲜与加工 2024, 24(12)）综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.66,
         r.note = '待核验点：巨峰灰霉发病率原文数据；高 为定性分级';
MATCH (a:Variety {id: 'muscat_hamburg'}), (b:Disease {id: 'blue_mold'})
MERGE (a)-[r:SUSCEPTIBLE_TO]->(b)
  SET r.sid = 'd_muscat_blue',
         r.subject = '玫瑰香',
         r.predicate = 'SUSCEPTIBLE_TO',
         r.object = '青霉病',
         r.stage = '贮藏',
         r.severity = '中',
         r.reason = '玫瑰香果梗细、库房带菌时青霉易从果梗侵入',
         r.source_ids = ['review_grape_storage', 'review_packaging_logistics'],
         r.locator = '《鲜食葡萄采后保鲜技术研究进展》（保鲜与加工 2024, 24(12)）综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.66,
         r.note = '待核验点：玫瑰香青霉发生程度原文';
MATCH (a:Variety {id: 'red_globe'}), (b:Disease {id: 'black_mold'})
MERGE (a)-[r:SUSCEPTIBLE_TO]->(b)
  SET r.sid = 'd_redglobe_black',
         r.subject = '红地球',
         r.predicate = 'SUSCEPTIBLE_TO',
         r.object = '黑霉病',
         r.stage = '贮藏',
         r.severity = '低',
         r.reason = '黑霉多在高温高湿条件下发生，规范冷藏发生率低',
         r.source_ids = ['review_grape_storage', 'ops_grape_ny1199'],
         r.locator = '《鲜食葡萄采后保鲜技术研究进展》（保鲜与加工 2024, 24(12)）综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.66,
         r.note = '待核验点：红地球黑霉发生率原文；低 为定性判断';
MATCH (a:Variety {id: 'red_globe'}), (b:Disease {id: 'gray_mold'})
MERGE (a)-[r:SUSCEPTIBLE_TO]->(b)
  SET r.sid = 'd_redglobe_gray',
         r.subject = '红地球',
         r.predicate = 'SUSCEPTIBLE_TO',
         r.object = '灰霉病',
         r.stage = '贮藏',
         r.severity = '中',
         r.reason = '红地球果梗粗、较耐贮，但伤口与结露条件下仍易感灰霉',
         r.source_ids = ['review_grape_storage', 'gbt16862_2026'],
         r.locator = '《鲜食葡萄采后保鲜技术研究进展》（保鲜与加工 2024, 24(12)）综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.66,
         r.note = '待核验点：红地球灰霉敏感性原文比较数据';
MATCH (a:Variety {id: 'summer_black'}), (b:Disease {id: 'rhizopus_rot'})
MERGE (a)-[r:SUSCEPTIBLE_TO]->(b)
  SET r.sid = 'd_summerblack_rhizopus',
         r.subject = '夏黑',
         r.predicate = 'SUSCEPTIBLE_TO',
         r.object = '根霉病',
         r.stage = '贮藏',
         r.severity = '高',
         r.reason = '夏黑皮薄易裂果，裂口果汁诱发根霉快速扩展',
         r.source_ids = ['review_grape_storage', 'ops_grape_ny1199'],
         r.locator = '《鲜食葡萄采后保鲜技术研究进展》（保鲜与加工 2024, 24(12)）综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.66,
         r.note = '待核验点：夏黑根霉发病率数据；高 为定性分级';
MATCH (a:Variety {id: 'shine_muscat'}), (b:Disease {id: 'anthracnose'})
MERGE (a)-[r:SUSCEPTIBLE_TO]->(b)
  SET r.sid = 'sm_susc_anthracnose',
         r.subject = '阳光玫瑰',
         r.predicate = 'SUSCEPTIBLE_TO',
         r.object = '炭疽病',
         r.stage = '贮藏',
         r.severity = '中',
         r.reason = '潜伏侵染，采后成熟期显症，形成凹陷褐斑并扩展',
         r.source_ids = ['review_shine_muscat', 'review_grape_storage'],
         r.locator = '《阳光玫瑰葡萄采后保鲜研究进展》综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.68,
         r.note = '待核验点：阳光玫瑰炭疽病发生程度原文数据；中 为定性分级';
MATCH (a:Variety {id: 'shine_muscat'}), (b:Disease {id: 'gray_mold'})
MERGE (a)-[r:SUSCEPTIBLE_TO]->(b)
  SET r.sid = 'sm_susc_gray',
         r.subject = '阳光玫瑰',
         r.predicate = 'SUSCEPTIBLE_TO',
         r.object = '灰霉病',
         r.stage = '贮藏',
         r.severity = '高',
         r.reason = '冷藏期最主要病害，0℃ 下仍缓慢发病，果梗与伤口为主要侵染位点',
         r.source_ids = ['review_shine_muscat', 'review_grape_storage', 'gbt16862_2026'],
         r.locator = '《阳光玫瑰葡萄采后保鲜研究进展》综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.82,
         r.note = '待核验点：品种抗性/敏感性分级原文表述；高 为依据生产经验与综述描述的定性分级';
MATCH (a:Variety {id: 'shine_muscat'}), (b:Disease {id: 'sour_rot'})
MERGE (a)-[r:SUSCEPTIBLE_TO]->(b)
  SET r.sid = 'sm_susc_sour',
         r.subject = '阳光玫瑰',
         r.predicate = 'SUSCEPTIBLE_TO',
         r.object = '酸腐病',
         r.stage = '贮藏',
         r.severity = '低',
         r.reason = '多继发于裂果、果蝇危害与机械伤，规范冷藏条件下发生率较低',
         r.source_ids = ['review_shine_muscat', 'review_packaging_logistics'],
         r.locator = '《阳光玫瑰葡萄采后保鲜研究进展》综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.6,
         r.note = '待核验点：酸腐病在阳光玫瑰上的发生率数据缺失；低 为定性判断，需田间/贮藏调查支持';

// ---------------- PREVENTED_BY（8 条） ----------------
MATCH (a:Disease {id: 'anthracnose'}), (b:Condition {id: 'cold_0'})
MERGE (a)-[r:PREVENTED_BY]->(b)
  SET r.sid = 'e_anthracnose_cold0',
         r.subject = '炭疽病',
         r.predicate = 'PREVENTED_BY',
         r.object = '低温冷藏 0±0.5℃',
         r.stage = '贮藏',
         r.efficacy = '中',
         r.reason = '低温延缓炭疽病潜伏侵染显症与病斑扩展',
         r.source_ids = ['review_shine_muscat', 'review_grape_storage'],
         r.locator = '《阳光玫瑰葡萄采后保鲜研究进展》综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.7,
         r.note = '待核验点：低温对炭疽病斑扩展抑制的原文数据';
MATCH (a:Disease {id: 'blue_mold'}), (b:Condition {id: 'microperforated_film'})
MERGE (a)-[r:PREVENTED_BY]->(b)
  SET r.sid = 'e_blue_film',
         r.subject = '青霉病',
         r.predicate = 'PREVENTED_BY',
         r.object = '微孔保鲜膜',
         r.stage = '贮藏',
         r.efficacy = '中',
         r.reason = '微孔膜调节袋内湿度与气体，减少结露与青霉侵染',
         r.source_ids = ['review_packaging_logistics', 'paper_ca_water_crystal'],
         r.locator = '《基于主成分和相关性分析不同自发气调袋包装对水晶葡萄采后贮藏品质的影响》结果章节；页码待补',
         r.status = 'anchor',
         r.confidence = 0.72,
         r.note = '待核验点：微孔膜内湿度与青霉发生率原文';
MATCH (a:Disease {id: 'gray_mold'}), (b:Condition {id: 'cold_0'})
MERGE (a)-[r:PREVENTED_BY]->(b)
  SET r.sid = 'e_gray_cold0',
         r.subject = '灰霉病',
         r.predicate = 'PREVENTED_BY',
         r.object = '低温冷藏 0±0.5℃',
         r.stage = '贮藏',
         r.efficacy = '中',
         r.reason = '0℃ 附近灰霉扩展极慢；单靠低温不能完全抑制，需配合防腐',
         r.source_ids = ['gbt16862_2026', 'review_grape_storage'],
         r.locator = 'GB/T 16862-2026 冷藏技术要求相关条款（openstd 在线预览；条款号/页码待获取原文后补）',
         r.status = 'anchor',
         r.confidence = 0.74,
         r.note = '待核验点：0℃ 下灰霉病斑扩展速率原文';
MATCH (a:Disease {id: 'gray_mold'}), (b:Condition {id: 'no_damage_harvest'})
MERGE (a)-[r:PREVENTED_BY]->(b)
  SET r.sid = 'e_gray_nodamage',
         r.subject = '灰霉病',
         r.predicate = 'PREVENTED_BY',
         r.object = '无伤采收',
         r.stage = '预冷',
         r.efficacy = '中',
         r.reason = '无伤采收减少伤口与汁液外渗，降低灰霉侵染位点',
         r.source_ids = ['gbt16862_2026', 'ops_grape_ny1199'],
         r.locator = '附录B 表B.1 灰霉病防治措施',
         r.quote = '灰霉病防治措施:1)花期前、后及采前,按农药登记批准的使用方法,喷施GB23200(所有部分)允许使用的低毒杀菌剂;2)防止机械损伤;3)库房消杀,入库时使用二氧化硫类缓释保鲜剂;4)冷藏温度-1℃~0℃,温度波动±0.5℃以内',
         r.status = 'verified',
         r.confidence = 0.72,
         r.note = '待核验点：无伤采收与灰霉发病率对应数据；按 GB/T 16862-2026（用户提供 PDF 全文，文本经 pdfminer 提取） 升级：「防止机械损伤」为条文防治措施第 2 项';
MATCH (a:Disease {id: 'gray_mold'}), (b:Condition {id: 'so2_pad'})
MERGE (a)-[r:PREVENTED_BY]->(b)
  SET r.sid = 'e_gray_so2pad',
         r.subject = '灰霉病',
         r.predicate = 'PREVENTED_BY',
         r.object = '焦亚硫酸盐缓释片',
         r.stage = '贮藏',
         r.efficacy = '高',
         r.reason = 'SO₂ 缓释片持续释放低浓度 SO₂ 抑制灰霉，为葡萄商业贮藏主用手段',
         r.source_ids = ['ops_grape_ny1199', 'paper_so2_pad_1mcp_shine'],
         r.locator = '6.3.4 保鲜剂(纸)使用要求;附录B 表B.1',
         r.quote = '待果实温度降至贮藏温度后,应在上层吸水纸上方放置二氧化硫类缓释保鲜剂(纸)并封袋/箱。葡萄不应产生二氧化硫伤害。',
         r.status = 'verified',
         r.confidence = 0.8,
         r.note = '待核验点：缓释片剂量与灰霉抑制率原文数据；按 GB/T 16862-2026（用户提供 PDF 全文，文本经 pdfminer 提取） 升级：条文使用「二氧化硫类缓释保鲜剂(纸)」';
MATCH (a:Disease {id: 'rhizopus_rot'}), (b:Condition {id: 'cold_chain_transport'})
MERGE (a)-[r:PREVENTED_BY]->(b)
  SET r.sid = 'e_rhizopus_coldchain',
         r.subject = '根霉病',
         r.predicate = 'PREVENTED_BY',
         r.object = '冷链运输',
         r.stage = '出库',
         r.efficacy = '中',
         r.reason = '冷链维持低温抑制根霉孢子萌发与菌丝扩展',
         r.source_ids = ['gbt16862_2026', 'review_packaging_logistics'],
         r.locator = 'GB/T 16862-2026 冷藏技术要求相关条款（openstd 在线预览；条款号/页码待获取原文后补）',
         r.status = 'anchor',
         r.confidence = 0.7,
         r.note = '待核验点：断冷时长与根霉扩展速率原文';
MATCH (a:Disease {id: 'rhizopus_rot'}), (b:Condition {id: 'no_damage_harvest'})
MERGE (a)-[r:PREVENTED_BY]->(b)
  SET r.sid = 'e_rhizopus_nodamage',
         r.subject = '根霉病',
         r.predicate = 'PREVENTED_BY',
         r.object = '无伤采收',
         r.stage = '预冷',
         r.efficacy = '高',
         r.reason = '根霉主要经伤口侵染，无伤采收可显著降低发病率',
         r.source_ids = ['review_grape_storage', 'ops_grape_ny1199'],
         r.locator = '《鲜食葡萄采后保鲜技术研究进展》（保鲜与加工 2024, 24(12)）综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.74,
         r.note = '待核验点：根霉发病率与机械伤程度对应原文';
MATCH (a:Disease {id: 'gray_mold'}), (b:Condition {id: 'precool_fast'})
MERGE (a)-[r:PREVENTED_BY]->(b)
  SET r.sid = 'sm_prev_gray_precool',
         r.subject = '灰霉病',
         r.predicate = 'PREVENTED_BY',
         r.object = '快速预冷（12h 内至 0℃）',
         r.stage = '预冷',
         r.efficacy = '中',
         r.reason = '快速降温抑制孢子萌发与菌丝扩展，缩短高温窗口期即降低灰霉发病率',
         r.source_ids = ['review_shine_muscat', 'gbt16862_2026'],
         r.locator = '《阳光玫瑰葡萄采后保鲜研究进展》综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.76,
         r.note = '待核验点：预冷时限与灰霉发病率下降的对应原文数据；单靠预冷不能替代药剂/气调';

// ---------------- INDUCED_BY（6 条） ----------------
MATCH (a:Disease {id: 'black_mold'}), (b:Condition {id: 'high_temp_humid'})
MERGE (a)-[r:INDUCED_BY]->(b)
  SET r.sid = 'f_black_hot',
         r.subject = '黑霉病',
         r.predicate = 'INDUCED_BY',
         r.object = '高温高湿',
         r.stage = '贮藏',
         r.reason = '黑霉（黑曲霉）在高温高湿条件下大量繁殖',
         r.source_ids = ['review_grape_storage', 'ops_grape_ny1199'],
         r.locator = '《鲜食葡萄采后保鲜技术研究进展》（保鲜与加工 2024, 24(12)）综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.7,
         r.note = '待核验点：温湿度与黑霉发生率对应原文';
MATCH (a:Disease {id: 'blue_mold'}), (b:Condition {id: 'wound'})
MERGE (a)-[r:INDUCED_BY]->(b)
  SET r.sid = 'f_blue_wound',
         r.subject = '青霉病',
         r.predicate = 'INDUCED_BY',
         r.object = '伤口',
         r.stage = '贮藏',
         r.reason = '青霉多由伤口或果梗剪口侵入，无伤采收可显著降低发病率',
         r.source_ids = ['review_grape_storage', 'review_packaging_logistics'],
         r.locator = '《鲜食葡萄采后保鲜技术研究进展》（保鲜与加工 2024, 24(12)）综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.7,
         r.note = '待核验点：青霉经伤口侵染的原文证据与发病率数据';
MATCH (a:Disease {id: 'gray_mold'}), (b:Condition {id: 'high_humid_condensation'})
MERGE (a)-[r:INDUCED_BY]->(b)
  SET r.sid = 'f_gray_condensation',
         r.subject = '灰霉病',
         r.predicate = 'INDUCED_BY',
         r.object = '高湿结露',
         r.stage = '贮藏',
         r.reason = '库温波动导致袋内/果面结露，为灰霉孢子萌发提供自由水',
         r.source_ids = ['review_grape_storage', 'review_packaging_logistics'],
         r.locator = '《鲜食葡萄采后保鲜技术研究进展》（保鲜与加工 2024, 24(12)）综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.7,
         r.note = '待核验点：结露时长与灰霉发病率对应原文';
MATCH (a:Disease {id: 'gray_mold'}), (b:Condition {id: 'room_temp_storage'})
MERGE (a)-[r:INDUCED_BY]->(b)
  SET r.sid = 'f_gray_roomtemp',
         r.subject = '灰霉病',
         r.predicate = 'INDUCED_BY',
         r.object = '常温贮运',
         r.stage = '贮藏',
         r.reason = '常温贮运下灰霉扩展极快，是采后短期腐烂的主要诱因',
         r.source_ids = ['review_shine_muscat', 'review_packaging_logistics'],
         r.locator = '《阳光玫瑰葡萄采后保鲜研究进展》综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.7,
         r.note = '待核验点：常温贮运时长与灰霉发病率对应原文数据';
MATCH (a:Disease {id: 'gray_mold'}), (b:Condition {id: 'wound'})
MERGE (a)-[r:INDUCED_BY]->(b)
  SET r.sid = 'f_gray_wound',
         r.subject = '灰霉病',
         r.predicate = 'INDUCED_BY',
         r.object = '伤口',
         r.stage = '贮藏',
         r.reason = '伤口渗出汁液为灰霉提供营养与侵入门户',
         r.source_ids = ['review_grape_storage', 'ops_grape_ny1199'],
         r.locator = '《鲜食葡萄采后保鲜技术研究进展》（保鲜与加工 2024, 24(12)）综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.7,
         r.note = '待核验点：伤口数与灰霉发病率对应数据';
MATCH (a:Disease {id: 'rhizopus_rot'}), (b:Condition {id: 'mechanical_injury'})
MERGE (a)-[r:INDUCED_BY]->(b)
  SET r.sid = 'f_rhizopus_mech',
         r.subject = '根霉病',
         r.predicate = 'INDUCED_BY',
         r.object = '机械伤',
         r.stage = '贮藏',
         r.reason = '机械伤造成果皮破裂，根霉由伤口快速侵染并软腐',
         r.source_ids = ['review_grape_storage', 'ops_grape_ny1199'],
         r.locator = '《鲜食葡萄采后保鲜技术研究进展》（保鲜与加工 2024, 24(12)）综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.7,
         r.note = '待核验点：机械伤程度与根霉发病率原文';

// ---------------- ALTERNATIVE_TO（3 条） ----------------
MATCH (a:Condition {id: 'microperforated_film'}), (b:Condition {id: 'ca_o2'})
MERGE (a)-[r:ALTERNATIVE_TO]->(b)
  SET r.sid = 'g_film_alt_ca',
         r.subject = '微孔保鲜膜',
         r.predicate = 'ALTERNATIVE_TO',
         r.object = '气调 O₂ 3~5%',
         r.stage = '贮藏',
         r.reason = '自发气调包装（微孔膜）以更低成本在包装内形成低氧环境，可部分替代主动气调库',
         r.source_ids = ['review_packaging_logistics', 'paper_ca_water_crystal'],
         r.locator = '《葡萄物流及贮藏保鲜包装技术研究现状与展望》（包装工程 2023, 44(23)）综述正文；页码待补',
         r.status = 'anchor',
         r.confidence = 0.66,
         r.note = '待核验点：微孔膜袋内 O₂/CO₂ 实测值与主动气调效果对比原文';
MATCH (a:Condition {id: 'ice_temp'}), (b:Condition {id: 'cold_neg1'})
MERGE (a)-[r:ALTERNATIVE_TO]->(b)
  SET r.sid = 'g_ice_alt_cold_neg1',
         r.subject = '冰温贮藏 -0.5~0℃',
         r.predicate = 'ALTERNATIVE_TO',
         r.object = '低温冷藏 -1~0℃',
         r.stage = '贮藏',
         r.reason = '近冰温精准控温（-0.5~0℃）可在避免冻伤前提下替代更低温度的 -1~0℃ 冷藏',
         r.source_ids = ['paper_ice_temp', 'review_grape_storage'],
         r.locator = '《1-MCP结合ClO2处理对冰温贮藏红提葡萄生理品质的影响》结果章节；页码待补',
         r.status = 'anchor',
         r.confidence = 0.6,
         r.note = '待核验点：冰温与 -1~0℃ 冷藏的品质对比原文；实证对象为红提，需扩展验证';
MATCH (a:Condition {id: 'so2_pad'}), (b:Condition {id: 'so2_fumigation'})
MERGE (a)-[r:ALTERNATIVE_TO]->(b)
  SET r.sid = 'g_so2pad_alt_fumigation',
         r.subject = '焦亚硫酸盐缓释片',
         r.predicate = 'ALTERNATIVE_TO',
         r.object = 'SO₂ 熏蒸',
         r.stage = '贮藏',
         r.reason = '缓释片低剂量持续释放 SO₂，较熏蒸更安全，适合阳光玫瑰等敏感品种替代高剂量熏蒸',
         r.source_ids = ['paper_so2_pad_1mcp_shine', 'paper_so2_1mcp_shine', 'ops_grape_ny1199'],
         r.locator = '1-MCP pretreatment combined with SO2 preservation pad ... Shine Muscat grapes（Food Chemistry, PII S0308814626027688）摘要/结果；页码待补',
         r.status = 'anchor',
         r.confidence = 0.68,
         r.note = '待核验点：缓释片与熏蒸的剂量-残留对比数据原文；替代关系为工艺建议，需原文剂量支持';

// ---------------- INDICATES（2 条） ----------------
MATCH (a:QualityIndicator {id: 'decay_rate'}), (b:Disease {id: 'gray_mold'})
MERGE (a)-[r:INDICATES]->(b)
  SET r.sid = 'h_decay_indicates_gray',
         r.subject = '腐烂率',
         r.predicate = 'INDICATES',
         r.object = '灰霉病',
         r.stage = '贮藏',
         r.reason = '冷藏期腐烂以灰霉病为主，腐烂率突增通常指示灰霉流行',
         r.source_ids = ['review_shine_muscat', 'review_grape_storage'],
         r.locator = '《阳光玫瑰葡萄采后保鲜研究进展》综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.66,
         r.note = '待核验点：腐烂果病原分离比例原文（灰霉占比）；指示关系需病原学数据支持';
MATCH (a:QualityIndicator {id: 'off_flavor'}), (b:Disease {id: 'sour_rot'})
MERGE (a)-[r:INDICATES]->(b)
  SET r.sid = 'h_offflavor_indicates_sourrot',
         r.subject = '异味/风味偏离',
         r.predicate = 'INDICATES',
         r.object = '酸腐病',
         r.stage = '贮藏',
         r.reason = '酸臭味与流汁是酸腐病的典型感官指示，可作为田间/库房快速判别依据',
         r.source_ids = ['review_shine_muscat', 'review_packaging_logistics'],
         r.locator = '《阳光玫瑰葡萄采后保鲜研究进展》综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.6,
         r.note = '待核验点：酸腐病感官描述与挥发性成分对应原文；指示关系为定性判断';

// ---------------- HAS_INDICATOR_VALUE（8 条） ----------------
MATCH (a:Variety {id: 'crimson_seedless'}), (b:QualityIndicator {id: 'shelf_life'})
MERGE (a)-[r:HAS_INDICATOR_VALUE]->(b)
  SET r.sid = 'i_crimson_shelf',
         r.subject = '克瑞森无核',
         r.predicate = 'HAS_INDICATOR_VALUE',
         r.object = '耐贮性',
         r.value_min = 3,
         r.value_max = 5,
         r.unit = '月',
         r.stage = '贮藏',
         r.reason = '克瑞森无核晚熟耐贮，冷藏货架期较长',
         r.source_ids = ['review_grape_storage', 'review_table_grape_en'],
         r.locator = '《鲜食葡萄采后保鲜技术研究进展》（保鲜与加工 2024, 24(12)）综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.58,
         r.note = '待核验点：克瑞森无核耐贮期原文数据；无核品种差异待核';
MATCH (a:Variety {id: 'kyoho'}), (b:QualityIndicator {id: 'shelf_life'})
MERGE (a)-[r:HAS_INDICATOR_VALUE]->(b)
  SET r.sid = 'i_kyoho_shelf',
         r.subject = '巨峰',
         r.predicate = 'HAS_INDICATOR_VALUE',
         r.object = '耐贮性',
         r.value_min = 3,
         r.value_max = 4,
         r.unit = '月',
         r.stage = '贮藏',
         r.reason = '规范冷藏条件下巨峰商品果耐贮期约 3~4 个月',
         r.source_ids = ['review_grape_storage', 'review_table_grape_en'],
         r.locator = '《鲜食葡萄采后保鲜技术研究进展》（保鲜与加工 2024, 24(12)）综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.62,
         r.note = '待核验点：巨峰耐贮期 3~4 月为 Lead 领域口径，原文区间与贮藏前提（温度/SO2/包装）待核验';
MATCH (a:Variety {id: 'muscat_hamburg'}), (b:QualityIndicator {id: 'shelf_life'})
MERGE (a)-[r:HAS_INDICATOR_VALUE]->(b)
  SET r.sid = 'i_muscat_hamburg_shelf',
         r.subject = '玫瑰香',
         r.predicate = 'HAS_INDICATOR_VALUE',
         r.object = '耐贮性',
         r.unit = '月',
         r.stage = '贮藏',
         r.reason = '玫瑰香为中熟浓香品种，耐贮性偏短（具体月数原文缺失，本条仅登记为待补项）',
         r.source_ids = ['review_grape_storage', 'review_table_grape_en'],
         r.locator = '《鲜食葡萄采后保鲜技术研究进展》（保鲜与加工 2024, 24(12)）综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.5,
         r.note = '待核验点：玫瑰香耐贮期原文数值缺失，暂不填数值（避免编造），待补文献后回填 value_min/value_max';
MATCH (a:Variety {id: 'red_globe'}), (b:QualityIndicator {id: 'shelf_life'})
MERGE (a)-[r:HAS_INDICATOR_VALUE]->(b)
  SET r.sid = 'i_redglobe_shelf',
         r.subject = '红地球',
         r.predicate = 'HAS_INDICATOR_VALUE',
         r.object = '耐贮性',
         r.value_min = 4,
         r.value_max = 6,
         r.unit = '月',
         r.stage = '贮藏',
         r.reason = '红地球晚熟、果梗粗、较耐贮，规范冷藏可达 4~6 个月',
         r.source_ids = ['review_grape_storage', 'gbt16862_2026'],
         r.locator = '《鲜食葡萄采后保鲜技术研究进展》（保鲜与加工 2024, 24(12)）综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.64,
         r.note = '待核验点：红地球耐贮期 4~6 月为 Lead 领域口径，原文区间与 SO2 处理前提待核验';
MATCH (a:Variety {id: 'summer_black'}), (b:QualityIndicator {id: 'shelf_life'})
MERGE (a)-[r:HAS_INDICATOR_VALUE]->(b)
  SET r.sid = 'i_summer_black_shelf',
         r.subject = '夏黑',
         r.predicate = 'HAS_INDICATOR_VALUE',
         r.object = '耐贮性',
         r.value_min = 1,
         r.value_max = 2,
         r.unit = '月',
         r.stage = '贮藏',
         r.reason = '夏黑早熟皮薄、易落粒，规范冷藏耐贮期约 1~2 个月',
         r.source_ids = ['review_grape_storage', 'review_packaging_logistics'],
         r.locator = '《鲜食葡萄采后保鲜技术研究进展》（保鲜与加工 2024, 24(12)）综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.6,
         r.note = '待核验点：夏黑耐贮期 1~2 月为 Lead 领域口径，原文数据待核验；早熟品种耐贮性普遍短于晚熟品种';
MATCH (a:Variety {id: 'shine_muscat'}), (b:QualityIndicator {id: 'shelf_life'})
MERGE (a)-[r:HAS_INDICATOR_VALUE]->(b)
  SET r.sid = 'sm_ind_shelf',
         r.subject = '阳光玫瑰',
         r.predicate = 'HAS_INDICATOR_VALUE',
         r.object = '耐贮性',
         r.value_min = 2,
         r.value_max = 4,
         r.unit = '月',
         r.stage = '贮藏',
         r.reason = '规范化冷藏条件下阳光玫瑰商品果耐贮期约 2~4 个月',
         r.source_ids = ['review_shine_muscat', 'review_grape_storage'],
         r.locator = '《阳光玫瑰葡萄采后保鲜研究进展》综述正文；页码待获取原文后补',
         r.status = 'anchor',
         r.confidence = 0.66,
         r.note = '待核验点：综述给出的耐贮期原文区间与贮藏条件前提（温度/SO2/包装）';
MATCH (a:Variety {id: 'shine_muscat'}), (b:QualityIndicator {id: 'ssc'})
MERGE (a)-[r:HAS_INDICATOR_VALUE]->(b)
  SET r.sid = 'sm_ind_ssc',
         r.subject = '阳光玫瑰',
         r.predicate = 'HAS_INDICATOR_VALUE',
         r.object = '可溶性固形物SSC',
         r.value_min = 16,
         r.unit = '%',
         r.stage = '贮藏',
         r.reason = '优质阳光玫瑰 SSC 应 ≥16%，采后贮藏期 SSC 变化是品质核心判据',
         r.source_ids = ['review_shine_muscat', 'review_grape_storage'],
         r.locator = '附录A 表A.1',
         r.quote = '附录A 表A.1:阳光玫瑰 可溶性固形物/%≥16.00,可滴定酸/%≤0.35。',
         r.status = 'verified',
         r.confidence = 0.62,
         r.note = '待核验点：≥16% 为优质果分级/商品标准口径，标准原文条款待核；下限已填，无统一上限；按 GB/T 16862-2026（用户提供 PDF 全文，文本经 pdfminer 提取） 升级：按表A.1 还原为 SSC≥16.00%';
MATCH (a:Variety {id: 'shine_muscat'}), (b:QualityIndicator {id: 'ta'})
MERGE (a)-[r:HAS_INDICATOR_VALUE]->(b)
  SET r.sid = 'sm_ind_ta',
         r.subject = '阳光玫瑰',
         r.predicate = 'HAS_INDICATOR_VALUE',
         r.object = '可滴定酸TA',
         r.value_max = 0.35,
         r.unit = '%',
         r.stage = '贮藏',
         r.reason = '阳光玫瑰 TA 适宜区间约 0.4~0.6%，过低寡淡、过高偏酸',
         r.source_ids = ['review_shine_muscat', 'paper_so2_1mcp_shine'],
         r.locator = '附录A 表A.1',
         r.quote = '附录A 表A.1:阳光玫瑰 可溶性固形物/%≥16.00,可滴定酸/%≤0.35。',
         r.status = 'verified',
         r.confidence = 0.6,
         r.note = '待核验点：TA 区间原文数值与滴定方法；不同产区/成熟度差异待核；按 GB/T 16862-2026（用户提供 PDF 全文，文本经 pdfminer 提取） 升级：按表A.1 更正为 TA≤0.35%（原 0.4~0.6 无条文依据，已删）';

// 关系写入完毕，做一次统计自检
MATCH ()-[r]->() RETURN type(r) AS predicate, count(*) AS cnt ORDER BY predicate;
