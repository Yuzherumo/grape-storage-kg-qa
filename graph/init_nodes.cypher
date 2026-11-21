// =============================================================================
// graph/init_nodes.cypher —— 图谱节点初始化（自动生成，请勿手改）
// 由 scripts/gen_cypher.py 从 data/entities.csv + data/sources.csv 生成
// 幂等：MERGE (n:Label {id: ...}) —— 可重复执行
// 统计：共 74 个节点（Variety 8，Condition 30，QualityIndicator 13，Disease 7，Source 16）
// 生成后校验：python scripts/gen_cypher.py --check
// =============================================================================

// 先执行 graph/schema.cypher 建立唯一约束/索引（可重复执行）
// cypher-shell -f graph/schema.cypher


// ---------------- Variety（8 个） ----------------
MERGE (n:Variety {id: 'shine_muscat'})
  SET n.label = 'Variety',
         n.name = '阳光玫瑰',
         n.aliases = ['Shine Muscat', '香印', '晴王', '青提', '香印青提'],
         n.species = '欧美杂交种',
         n.berry_color = '黄绿',
         n.seedless = '无核（GA处理）',
         n.maturity = '中熟',
         n.region = '云南;四川;陕西;江苏',
         n.source_ids = ['gbt16862_2026', 'review_shine_muscat', 'paper_so2_1mcp_shine'],
         n.note = '主线品种：对SO2敏感、采后易落粒与果梗褐变';
MERGE (n:Variety {id: 'kyoho'})
  SET n.label = 'Variety',
         n.name = '巨峰',
         n.aliases = ['Kyoho', '巨峰葡萄', '乒乓葡萄'],
         n.species = '欧美杂交种',
         n.berry_color = '紫黑',
         n.seedless = '有核',
         n.maturity = '中熟',
         n.region = '辽宁;河北;山东',
         n.source_ids = ['review_grape_storage', 'review_packaging_logistics'],
         n.note = '北方主栽中熟品种，耐贮性中等';
MERGE (n:Variety {id: 'red_globe'})
  SET n.label = 'Variety',
         n.name = '红地球',
         n.aliases = ['Red Globe', '红提', '红提子'],
         n.species = '欧亚种',
         n.berry_color = '红',
         n.seedless = '有核',
         n.maturity = '晚熟',
         n.region = '新疆;甘肃;云南',
         n.source_ids = ['review_grape_storage', 'paper_ice_temp'],
         n.note = '晚熟耐贮品种，果粒大、果梗粗';
MERGE (n:Variety {id: 'summer_black'})
  SET n.label = 'Variety',
         n.name = '夏黑',
         n.aliases = ['夏黑无核', '黑夏'],
         n.species = '欧美杂交种',
         n.berry_color = '紫黑',
         n.seedless = '无核',
         n.maturity = '早熟',
         n.region = '江苏;浙江;云南',
         n.source_ids = ['review_grape_storage', 'review_packaging_logistics'],
         n.note = '早熟无核，采后易落粒';
MERGE (n:Variety {id: 'muscat_hamburg'})
  SET n.label = 'Variety',
         n.name = '玫瑰香',
         n.aliases = ['Muscat Hamburg', '紫玫瑰香'],
         n.species = '欧亚种',
         n.berry_color = '紫红',
         n.seedless = '有核',
         n.maturity = '中熟',
         n.region = '河北;天津;山东',
         n.source_ids = ['review_grape_storage'],
         n.note = '浓玫瑰香味，但易落粒、不耐SO2';
MERGE (n:Variety {id: 'crimson_seedless'})
  SET n.label = 'Variety',
         n.name = '克瑞森无核',
         n.aliases = ['Crimson Seedless', '克伦生', '克瑞森'],
         n.species = '欧亚种',
         n.berry_color = '红',
         n.seedless = '无核',
         n.maturity = '晚熟',
         n.region = '新疆;山东;云南',
         n.source_ids = ['review_grape_storage'],
         n.note = '晚熟无核，果肉脆';
MERGE (n:Variety {id: 'hutai_8'})
  SET n.label = 'Variety',
         n.name = '户太八号',
         n.aliases = ['户太8号', '户太'],
         n.species = '欧美杂交种',
         n.berry_color = '紫黑',
         n.seedless = '有核',
         n.maturity = '中熟',
         n.region = '陕西',
         n.source_ids = ['review_grape_storage'],
         n.note = '陕西主栽，多次结果能力强';
MERGE (n:Variety {id: 'victoria'})
  SET n.label = 'Variety',
         n.name = '维多利亚',
         n.aliases = ['Victoria', '维多利亚葡萄'],
         n.species = '欧亚种',
         n.berry_color = '黄绿',
         n.seedless = '有核',
         n.maturity = '早熟',
         n.region = '云南;河北',
         n.source_ids = ['review_grape_storage'],
         n.note = '早熟黄绿色品种，易褐变';

// ---------------- Condition（30 个） ----------------
MERGE (n:Condition {id: 'cold_0'})
  SET n.label = 'Condition',
         n.name = '低温冷藏 0±0.5℃',
         n.aliases = ['0度冷藏', '零度库', '零度存放', '0℃冷藏', '冷库', '冷藏库'],
         n.category = '温度',
         n.value_min = -0.5,
         n.value_max = 0.5,
         n.unit = '℃',
         n.stage = '贮藏',
         n.source_ids = ['gbt16862_2026', 'review_grape_storage'],
         n.note = '鲜食葡萄冷藏基准温度区间；国标7.3通用冷藏区间为-1℃~0℃（verified）；0±0.5℃为文献/工程口径，anchor，见 sm_req_cold0。';
MERGE (n:Condition {id: 'cold_neg1'})
  SET n.label = 'Condition',
         n.name = '低温冷藏 -1~0℃',
         n.aliases = ['-1~0℃', '零下1度', '负1度冷藏'],
         n.category = '温度',
         n.value_min = -1,
         n.value_max = 0,
         n.unit = '℃',
         n.stage = '贮藏',
         n.source_ids = ['gbt16862_2026', 'review_grape_storage'],
         n.note = '部分品种可用的更低冷藏温度；与GB/T 16862-2026 7.3「-1℃~0℃」一致，相关三元组已 verified。';
MERGE (n:Condition {id: 'ice_temp'})
  SET n.label = 'Condition',
         n.name = '冰温贮藏 -0.5~0℃',
         n.aliases = ['冰温', '近冰温', '冰温库'],
         n.category = '温度',
         n.value_min = -0.5,
         n.value_max = 0,
         n.unit = '℃',
         n.stage = '贮藏',
         n.source_ids = ['paper_ice_temp', 'review_grape_storage'],
         n.note = '接近冰点的精准控温贮藏';
MERGE (n:Condition {id: 'rh_90_95'})
  SET n.label = 'Condition',
         n.name = '相对湿度 90~95%',
         n.aliases = ['湿度90', '高湿', '加湿', '90湿度'],
         n.category = '湿度',
         n.value_min = 90,
         n.value_max = 95,
         n.unit = '%',
         n.stage = '贮藏',
         n.source_ids = ['gbt16862_2026', 'review_grape_storage'],
         n.note = '减少失水与果梗干枯；与GB/T 16862-2026 7.3「相对湿度90%~95%」一致，相关三元组已 verified。';
MERGE (n:Condition {id: 'rh_low'})
  SET n.label = 'Condition',
         n.name = '低湿环境 RH<90%',
         n.aliases = ['低湿', '干冷', '湿度不够'],
         n.category = '湿度',
         n.value_min = 0,
         n.value_max = 90,
         n.unit = '%',
         n.stage = '贮藏',
         n.source_ids = ['gbt16862_2026', 'review_grape_storage'],
         n.note = '失重与果梗褐变风险升高';
MERGE (n:Condition {id: 'ca_o2'})
  SET n.label = 'Condition',
         n.name = '气调 O₂ 3~5%',
         n.aliases = ['气调', '低氧', 'O2 3~5%', '降氧', 'O2', '氧气'],
         n.category = '气调',
         n.value_min = 3,
         n.value_max = 5,
         n.unit = '%',
         n.stage = '贮藏',
         n.source_ids = ['review_packaging_logistics', 'review_grape_storage'],
         n.note = '低氧抑制呼吸但需防无氧呼吸';
MERGE (n:Condition {id: 'ca_co2'})
  SET n.label = 'Condition',
         n.name = '气调 CO₂ 1~3%',
         n.aliases = ['二氧化碳', 'CO2 1~3%', '气调CO2', 'CO2'],
         n.category = '气调',
         n.value_min = 1,
         n.value_max = 3,
         n.unit = '%',
         n.stage = '贮藏',
         n.source_ids = ['review_packaging_logistics', 'review_grape_storage'],
         n.note = '适宜CO2抑制灰霉但过量致伤害';
MERGE (n:Condition {id: 'high_co2'})
  SET n.label = 'Condition',
         n.name = '高 CO₂ >5%',
         n.aliases = ['高二氧化碳', 'CO2伤害', '二氧化碳伤害', '高浓度二氧化碳', '过高二氧化碳', 'CO2过高', '高CO2'],
         n.category = '气调',
         n.value_min = 5,
         n.value_max = 10,
         n.unit = '%',
         n.stage = '贮藏',
         n.source_ids = ['review_packaging_logistics', 'review_grape_storage'],
         n.note = '易致果肉褐变与异味';
MERGE (n:Condition {id: 'so2_fumigation'})
  SET n.label = 'Condition',
         n.name = 'SO₂ 熏蒸',
         n.aliases = ['二氧化硫', '熏硫', '硫熏', 'SO2熏蒸'],
         n.category = '化学',
         n.stage = '贮藏',
         n.source_ids = ['gbt16862_2026', 'paper_so2_1mcp_shine', 'paper_so2_pad_1mcp_shine'],
         n.note = '传统葡萄保鲜手段，但对阳光玫瑰易致漂白与风味劣变；国标6.3.4仅规范二氧化硫类缓释保鲜剂，未写熏蒸方式；熏蒸风险依据3.1「二氧化硫伤害」定义+文献，仍 anchor。';
MERGE (n:Condition {id: 'so2_pad'})
  SET n.label = 'Condition',
         n.name = '焦亚硫酸盐缓释片',
         n.aliases = ['保鲜片', '缓释片', '焦亚硫酸钠', 'SO2缓释'],
         n.category = '化学',
         n.stage = '贮藏',
         n.source_ids = ['paper_so2_pad_1mcp_shine', 'ops_grape_ny1199'],
         n.note = '市场常用SO2类保鲜剂形式；与GB/T 16862-2026 6.3.4「二氧化硫类缓释保鲜剂(纸)」一致，已 verified。';
MERGE (n:Condition {id: 'mcp_1'})
  SET n.label = 'Condition',
         n.name = '1-MCP 处理',
         n.aliases = ['1-MCP', '1甲基环丙烯', '乙烯抑制剂', 'MCP'],
         n.category = '化学',
         n.stage = '贮藏',
         n.source_ids = ['paper_so2_1mcp_shine', 'paper_so2_pad_1mcp_shine'],
         n.note = '乙烯作用抑制剂，常与SO2/气调联用';
MERGE (n:Condition {id: 'ozone'})
  SET n.label = 'Condition',
         n.name = '臭氧处理',
         n.aliases = ['臭氧', '臭氧杀菌', 'O3'],
         n.category = '化学',
         n.stage = '贮藏',
         n.source_ids = ['review_grape_storage', 'review_packaging_logistics'],
         n.note = '抑菌但高浓度伤果';
MERGE (n:Condition {id: 'precool_fast'})
  SET n.label = 'Condition',
         n.name = '快速预冷（12h 内至 0℃）',
         n.aliases = ['预冷', '快速降温', '打冷', '12小时预冷'],
         n.category = '采后操作',
         n.stage = '预冷',
         n.source_ids = ['gbt16862_2026', 'review_grape_storage'],
         n.note = '采后12h内降至0℃可显著减轻灰霉与失水；与GB/T 16862-2026 5.3.2「宜在采后12h内将果实中心温度降至0℃」一致，已 verified。';
MERGE (n:Condition {id: 'no_damage_harvest'})
  SET n.label = 'Condition',
         n.name = '无伤采收',
         n.aliases = ['轻拿轻放', '无伤采摘', '带梗剪'],
         n.category = '采后操作',
         n.stage = '预冷',
         n.source_ids = ['gbt16862_2026', 'ops_grape_ny1199'],
         n.note = '减少伤口即减少侵染位点；与GB/T 16862-2026 4.2.3/附录B「轻采轻放、防止机械损伤」一致，相关防治三元组已 verified。';
MERGE (n:Condition {id: 'mechanical_injury'})
  SET n.label = 'Condition',
         n.name = '机械伤',
         n.aliases = ['磕碰', '碰伤', '机械损伤', '挤压'],
         n.category = '环境风险',
         n.source_ids = ['review_grape_storage', 'review_packaging_logistics'],
         n.note = '伤口溢出汁液诱发根霉/灰霉';
MERGE (n:Condition {id: 'room_temp_storage'})
  SET n.label = 'Condition',
         n.name = '常温贮运',
         n.aliases = ['常温', '室温', '堆放', '不进冷库'],
         n.category = '环境风险',
         n.source_ids = ['gbt16862_2026', 'review_grape_storage'],
         n.note = '24h内即明显失水落粒';
MERGE (n:Condition {id: 'high_humid_condensation'})
  SET n.label = 'Condition',
         n.name = '高湿结露',
         n.aliases = ['结露', '返潮', '出汗', '水珠'],
         n.category = '环境风险',
         n.source_ids = ['review_grape_storage', 'review_packaging_logistics'],
         n.note = '温差结露促进灰霉与青霉侵染';
MERGE (n:Condition {id: 'high_temp_humid'})
  SET n.label = 'Condition',
         n.name = '高温高湿',
         n.aliases = ['闷热', '高温', '湿热'],
         n.category = '环境风险',
         n.source_ids = ['review_grape_storage'],
         n.note = '加速呼吸、乙烯释放与腐烂';
MERGE (n:Condition {id: 'microperforated_film'})
  SET n.label = 'Condition',
         n.name = '微孔保鲜膜',
         n.aliases = ['微孔膜', '保鲜膜', '打孔袋', 'MAP袋'],
         n.category = '包装',
         n.stage = '贮藏',
         n.source_ids = ['review_packaging_logistics', 'paper_ca_water_crystal'],
         n.note = '自发气调包装，调节O2/CO2与湿度';
MERGE (n:Condition {id: 'cold_chain_transport'})
  SET n.label = 'Condition',
         n.name = '冷链运输',
         n.aliases = ['冷链', '冷藏车', '冷链物流'],
         n.category = '采后操作',
         n.stage = '出库',
         n.source_ids = ['gbt16862_2026', 'review_packaging_logistics'],
         n.note = '出库至销售全程不断冷；与GB/T 16862-2026 8.1「运输温度0℃~5℃」一致，已 verified。';
MERGE (n:Condition {id: 'wound'})
  SET n.label = 'Condition',
         n.name = '伤口',
         n.aliases = ['伤口', '破损', '剪口', '破皮'],
         n.category = '环境风险',
         n.source_ids = ['review_grape_storage', 'ops_grape_ny1199'],
         n.note = '病原菌主要侵染入口';
MERGE (n:Condition {id: 'temp_fluctuation'})
  SET n.label = 'Condition',
         n.name = '冷藏温度波动 ±0.5℃',
         n.aliases = ['温度波动', '库温波动', '波动范围'],
         n.category = '温度',
         n.source_ids = ['gbt16862_2026'],
         n.note = '国标7.4.1：温度波动幅度不超过±0.5℃；条文口径，已 verified';
MERGE (n:Condition {id: 'daily_intake_limit'})
  SET n.label = 'Condition',
         n.name = '每天入库量 ≤ 库容 10%',
         n.aliases = ['入库量', '每天入库', '每日入库', '每天入多少', '入多少库'],
         n.category = '采后操作',
         n.source_ids = ['gbt16862_2026'],
         n.note = '国标5.2：每天入库量不超过库容量的10%；条文口径，已 verified';
MERGE (n:Condition {id: 'storage_density'})
  SET n.label = 'Condition',
         n.name = '冷藏密度 ≤ 200 kg/m³',
         n.aliases = ['堆码密度', '冷藏密度', '堆码', '码垛'],
         n.category = '采后操作',
         n.source_ids = ['gbt16862_2026'],
         n.note = '国标7.2：有效空间冷藏密度不超过200kg/m3；条文口径，已 verified';
MERGE (n:Condition {id: 'precool_forced'})
  SET n.label = 'Condition',
         n.name = '压差预冷 0~1℃',
         n.aliases = ['压差预冷', '预冷方式'],
         n.category = '采后操作',
         n.source_ids = ['gbt16862_2026'],
         n.note = '国标5.3.2：压差预冷时环境温度为0℃~1℃；条文口径，已 verified';
MERGE (n:Condition {id: 'sales_env'})
  SET n.label = 'Condition',
         n.name = '销售环境 0~10℃',
         n.aliases = ['销售温度', '销售环境', '卖场温度'],
         n.category = '温度',
         n.source_ids = ['gbt16862_2026'],
         n.note = '国标8.2：销售环境温度宜控制在0℃~10℃；条文口径，已 verified';
MERGE (n:Condition {id: 'archive_record'})
  SET n.label = 'Condition',
         n.name = '档案记录保存 ≥2 年',
         n.aliases = ['档案', '记录保存', '档案记录', '留档'],
         n.category = '采后操作',
         n.source_ids = ['gbt16862_2026'],
         n.note = '国标第9章：记录应保存两年以上；条文口径，已 verified';
MERGE (n:Condition {id: 'package_weight'})
  SET n.label = 'Condition',
         n.name = '包装容重 ≤ 8 kg',
         n.aliases = ['包装', '包装要求', '装箱', '纸箱', '箱重'],
         n.category = '包装',
         n.source_ids = ['gbt16862_2026'],
         n.note = '国标6.1.1.2：纸箱容重不宜超过8kg；条文口径，已 verified';
MERGE (n:Condition {id: 'pre_harvest_rain'})
  SET n.label = 'Condition',
         n.name = '采前降雨',
         n.aliases = ['采前降雨', '采前雨', '采收前降雨'],
         n.category = '环境风险',
         n.source_ids = ['gbt16862_2026'],
         n.note = '国标附录B：田间下雨/采前降雨是黑斑病诱因；条文口径，已 verified';
MERGE (n:Condition {id: 'warehouse_disinfection'})
  SET n.label = 'Condition',
         n.name = '库房消杀',
         n.aliases = ['库房消杀', '库房消毒', '消毒'],
         n.category = '化学',
         n.source_ids = ['gbt16862_2026'],
         n.note = '国标附录B：库房消杀为病害防治措施；条文口径，已 verified';

// ---------------- QualityIndicator（13 个） ----------------
MERGE (n:QualityIndicator {id: 'respiration'})
  SET n.label = 'QualityIndicator',
         n.name = '呼吸强度',
         n.aliases = ['呼吸速率', '呼吸作用', '呼吸'],
         n.unit = 'mgCO2/(kg·h)',
         n.direction = 'lower_better',
         n.method = '红外CO2分析仪/静态法',
         n.source_ids = ['review_grape_storage', 'review_table_grape_en'],
         n.note = '越低越耐贮';
MERGE (n:QualityIndicator {id: 'ethylene'})
  SET n.label = 'QualityIndicator',
         n.name = '乙烯释放率',
         n.aliases = ['乙烯', '乙烯量', '乙烯释放'],
         n.unit = 'μL/(kg·h)',
         n.direction = 'lower_better',
         n.method = '气相色谱法',
         n.source_ids = ['paper_so2_1mcp_shine', 'review_grape_storage'],
         n.note = '与落粒、软化正相关';
MERGE (n:QualityIndicator {id: 'decay_rate'})
  SET n.label = 'QualityIndicator',
         n.name = '腐烂率',
         n.aliases = ['烂果率', '腐烂', '烂果', '坏果率'],
         n.unit = '%',
         n.direction = 'lower_better',
         n.method = '计数法（腐烂果数/总果数）',
         n.source_ids = ['review_grape_storage', 'review_shine_muscat'],
         n.note = '病害处置效果核心指标';
MERGE (n:QualityIndicator {id: 'berry_drop'})
  SET n.label = 'QualityIndicator',
         n.name = '落粒率',
         n.aliases = ['掉粒', '落粒', '脱粒', '掉粒率'],
         n.unit = '%',
         n.direction = 'lower_better',
         n.method = '计数法（脱落果粒/总果粒）',
         n.source_ids = ['paper_so2_1mcp_shine', 'review_shine_muscat'],
         n.note = '阳光玫瑰采后最直观的品质损失';
MERGE (n:QualityIndicator {id: 'browning_index'})
  SET n.label = 'QualityIndicator',
         n.name = '褐变指数',
         n.aliases = ['褐变', '变褐', '褐变度'],
         n.direction = 'lower_better',
         n.method = '感官分级/色差计',
         n.source_ids = ['paper_so2_1mcp_shine', 'paper_clo2_so2_shine'],
         n.note = 'SO2伤害与果梗褐变主要表现';
MERGE (n:QualityIndicator {id: 'weight_loss'})
  SET n.label = 'QualityIndicator',
         n.name = '失重率',
         n.aliases = ['失水', '失重', '掉秤', '水分损失'],
         n.unit = '%',
         n.direction = 'lower_better',
         n.method = '称重法',
         n.source_ids = ['gbt16862_2026', 'review_grape_storage'],
         n.note = '主要由蒸腾失水引起';
MERGE (n:QualityIndicator {id: 'stem_browning'})
  SET n.label = 'QualityIndicator',
         n.name = '果梗褐变',
         n.aliases = ['果梗干枯', '梗褐变', '果柄褐变', '梗发黑'],
         n.direction = 'lower_better',
         n.method = '感官分级',
         n.source_ids = ['review_shine_muscat', 'paper_so2_1mcp_shine'],
         n.note = '果梗鲜活度是货架期关键';
MERGE (n:QualityIndicator {id: 'off_flavor'})
  SET n.label = 'QualityIndicator',
         n.name = '异味/风味偏离',
         n.aliases = ['异味', '酒味', '怪味', '风味劣变'],
         n.direction = 'lower_better',
         n.method = '感官评价/GC-MS',
         n.source_ids = ['paper_so2_1mcp_shine', 'paper_clo2_so2_shine'],
         n.note = 'SO2残留与无氧呼吸是主因';
MERGE (n:QualityIndicator {id: 'shelf_life'})
  SET n.label = 'QualityIndicator',
         n.name = '耐贮性',
         n.aliases = ['能存多久', '储藏期', '保鲜期', '存放时间', '货架期'],
         n.unit = '月',
         n.direction = 'higher_better',
         n.method = '达到商品率下限的贮藏时长',
         n.source_ids = ['review_shine_muscat', 'review_grape_storage'],
         n.note = '品种对比核心指标';
MERGE (n:QualityIndicator {id: 'ssc'})
  SET n.label = 'QualityIndicator',
         n.name = '可溶性固形物SSC',
         n.aliases = ['糖度', '甜度', 'SSC', '可溶性固形物'],
         n.unit = '%',
         n.direction = 'higher_better',
         n.method = '手持折光仪',
         n.source_ids = ['review_shine_muscat', 'review_grape_storage'],
         n.note = '阳光玫瑰优质果通常≥16%；阳光玫瑰 SSC≥16.00% 与GB/T 16862-2026 附录A 表A.1一致，已 verified。';
MERGE (n:QualityIndicator {id: 'ta'})
  SET n.label = 'QualityIndicator',
         n.name = '可滴定酸TA',
         n.aliases = ['酸度', 'TA', '滴定酸', '含酸量'],
         n.unit = '%',
         n.direction = 'target',
         n.method = 'NaOH滴定法',
         n.source_ids = ['paper_so2_1mcp_shine', 'review_shine_muscat'],
         n.note = '过高偏酸、过低寡淡；阳光玫瑰 TA≤0.35% 与GB/T 16862-2026 附录A 表A.1一致；原0.4~0.6%无条文依据已更正。';
MERGE (n:QualityIndicator {id: 'firmness'})
  SET n.label = 'QualityIndicator',
         n.name = '硬度',
         n.aliases = ['果肉硬度', '果肉弹性', '捏着软'],
         n.unit = 'N',
         n.direction = 'target',
         n.method = '质构仪/穿刺法',
         n.source_ids = ['paper_so2_pad_1mcp_shine', 'review_shine_muscat'],
         n.note = '与软化、落粒相关';
MERGE (n:QualityIndicator {id: 'vc'})
  SET n.label = 'QualityIndicator',
         n.name = '维生素C',
         n.aliases = ['VC', '维C', '抗坏血酸'],
         n.unit = 'mg/100g',
         n.direction = 'higher_better',
         n.method = '2,6-二氯靛酚滴定法',
         n.source_ids = ['review_grape_storage', 'paper_ice_temp'],
         n.note = '贮藏期易氧化下降';

// ---------------- Disease（7 个） ----------------
MERGE (n:Disease {id: 'gray_mold'})
  SET n.label = 'Disease',
         n.name = '灰霉病',
         n.aliases = ['灰霉', '长白毛', '白毛', '发霉', '灰霉层'],
         n.pathogen_latin = 'Botrytis cinerea',
         n.symptom = ['长白毛、灰霉层、果梗发霉、软腐水渍'],
         n.source_ids = ['review_shine_muscat', 'review_grape_storage', 'gbt16862_2026'],
         n.note = '冷库中最主要采后病害，0℃仍可缓慢发病；附录B 表B.1 已核对，症状/防治条文入图';
MERGE (n:Disease {id: 'rhizopus_rot'})
  SET n.label = 'Disease',
         n.name = '根霉腐败病',
         n.aliases = ['根霉', '软烂', '黑毛', '破皮流水'],
         n.pathogen_latin = 'Rhizopus migricans',
         n.symptom = ['软烂、破皮流水、常温下长粗白色丝体（黑毛）'],
         n.source_ids = ['review_grape_storage', 'ops_grape_ny1199', 'gbt16862_2026'],
         n.note = '多由机械伤/裂果诱发，扩展极快；按GB/T 16862-2026 附录B 对齐：原名「根霉病 R. stolonifer」不符，更正为「根霉腐败病 R. migricans」；根霉腐败病 Rhizopus migricans；软烂/破皮流水为农户口语';
MERGE (n:Disease {id: 'blue_mold'})
  SET n.label = 'Disease',
         n.name = '青霉病',
         n.aliases = ['青霉', '绿霉', '霉味'],
         n.pathogen_latin = 'Penicillium spp.',
         n.symptom = ['青绿色霉斑、霉味'],
         n.source_ids = ['review_grape_storage', 'review_packaging_logistics', 'gbt16862_2026'],
         n.note = '常与高湿、库房带菌相关；附录B 表B.1 已核对，症状/防治条文入图';
MERGE (n:Disease {id: 'anthracnose'})
  SET n.label = 'Disease',
         n.name = '炭疽病',
         n.aliases = ['炭疽', '凹陷褐斑', '褐斑'],
         n.pathogen_latin = 'Colletotrichum gloeosporioides',
         n.symptom = ['凹陷褐斑、腐烂斑扩展'],
         n.source_ids = ['review_shine_muscat', 'review_grape_storage'],
         n.note = '潜伏侵染，采后成熟期显症';
MERGE (n:Disease {id: 'sour_rot'})
  SET n.label = 'Disease',
         n.name = '酸腐病',
         n.aliases = ['酸腐', '酸臭', '流汁', '发酸'],
         n.symptom = ['酸臭味、流汁、发软'],
         n.source_ids = ['review_shine_muscat', 'review_packaging_logistics'],
         n.note = '常继发于裂果与果蝇危害';
MERGE (n:Disease {id: 'black_mold'})
  SET n.label = 'Disease',
         n.name = '黑斑病',
         n.aliases = ['黑霉', '黑毛霉', '粉霉'],
         n.pathogen_latin = 'Alternaria spp.',
         n.symptom = ['果刷棕褐色凹陷斑、后期掉粒'],
         n.source_ids = ['review_grape_storage', 'ops_grape_ny1199', 'gbt16862_2026'],
         n.note = '高温高湿条件下发生重；按GB/T 16862-2026 附录B 对齐：原「黑霉病 Aspergillus niger」无国标依据，更正为「黑斑病 Alternaria spp.」；黑斑病 Alternaria spp.；掉粒为农户口语';
MERGE (n:Disease {id: 'green_mold'})
  SET n.label = 'Disease',
         n.name = '绿霉病',
         n.aliases = ['绿霉'],
         n.pathogen_latin = 'Cladosporium herbarum',
         n.symptom = ['果梗黑褐色腐烂斑、出库后长绿色霉层'],
         n.source_ids = ['gbt16862_2026'],
         n.note = '国标附录B 表B.1 列入（原图谱缺）；4℃~30℃、伤口/果梗裂纹处发病；绿霉病 Cladosporium herbarum；绿色霉层为农户口语';

// ---------------- Source（16 个，来自 data/sources.csv） ----------------
MERGE (n:Source {id: 'gbt16862_2026'})
  SET n.title = '鲜食葡萄冷藏技术（GB/T 16862-2026）',
         n.authors = '国家市场监督管理总局;国家标准化管理委员会（发布单位）',
         n.year = '2026',
         n.venue = '全国标准信息公共服务平台（openstd）',
         n.type = '国标',
         n.doi_url = 'https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno=FC4C3274BF7AE61A5DDB9203CC0E249B',
         n.access = 'paywalled',
         n.note = 'P0权威来源。2026-03-31发布、2026-10-01实施，代替GB/T 16862-2008；已获取标准全文PDF（用户提供，pdfminer提取文本），7.3/5.3.2/6.3.4/8.1/附录A/附录B 条文已用于升级 verified。';
MERGE (n:Source {id: 'review_grape_storage'})
  SET n.title = '鲜食葡萄采后保鲜技术研究进展',
         n.authors = '郑瑞帆',
         n.year = '2024',
         n.venue = '保鲜与加工',
         n.type = '综述',
         n.doi_url = 'https://doi.org/10.3969/j.issn.1009-6221.2024.12.019',
         n.access = 'paywalled',
         n.note = '中文综述（《保鲜与加工》2024年24卷12期）。第一作者据检索结果，合作者与页码待获取原文补全。';
MERGE (n:Source {id: 'review_shine_muscat'})
  SET n.title = '阳光玫瑰葡萄采后保鲜研究进展',
         n.year = '2023',
         n.type = '综述',
         n.access = 'paywalled',
         n.note = '中文综述，万方/维普可检索（万方检索号 ncqjg-xk202324017）。年份据检索号推断；作者、期刊、DOI 待获取原文补全（待补链接）。';
MERGE (n:Source {id: 'review_packaging_logistics'})
  SET n.title = '葡萄物流及贮藏保鲜包装技术研究现状与展望',
         n.year = '2023',
         n.venue = '包装工程',
         n.type = '综述',
         n.access = 'paywalled',
         n.note = '中文综述（《包装工程》2023年44卷23期，CNKI 可检索）。作者与 DOI 待获取原文补全（待补链接）。覆盖自发气调与微孔膜包装。';
MERGE (n:Source {id: 'review_table_grape_en'})
  SET n.title = 'Postharvest Preservation Strategies for Table Grapes: A Comprehensive Review from Practical Methods to Future Developments',
         n.year = '2025',
         n.type = '综述',
         n.doi_url = 'https://pubmed.ncbi.nlm.nih.gov/40872088/',
         n.access = 'public',
         n.note = '英文综述，PubMed 收录（PMID 40872088）。期刊/年份/作者待补链接。';
MERGE (n:Source {id: 'paper_so2_1mcp_shine'})
  SET n.title = '1-MCP和SO2处理对阳光玫瑰葡萄贮藏品质及风味的影响',
         n.type = '论文',
         n.access = 'paywalled',
         n.note = '阳光玫瑰实证论文，中国农业学术服务平台（agri.nais.net.cn）可检索。作者/期刊/年份/DOI 待获取原文补全（待补链接）。';
MERGE (n:Source {id: 'paper_so2_pad_1mcp_shine'})
  SET n.title = '1-MCP pretreatment combined with SO2 preservation pad delays postharvest senescence and softening of Shine Muscat grapes by regulating cell-wall metabolism and antioxidant activity',
         n.year = '2026',
         n.venue = 'Food Chemistry',
         n.type = '论文',
         n.doi_url = 'https://www.sciencedirect.com/science/article/abs/pii/S0308814626027688',
         n.access = 'paywalled',
         n.note = '阳光玫瑰实证论文（SCI，Food Chemistry 在线，PII S0308814626027688）。作者列表与卷期待补链接。';
MERGE (n:Source {id: 'paper_clo2_so2_shine'})
  SET n.title = 'An integrated transcriptomic and metabolomic analysis of Shine Muscat grapes: Flavor, appearance, and quality attributes under on-tree vs. low-temperature ClO2/SO2 storage',
         n.type = '论文',
         n.access = 'paywalled',
         n.note = '阳光玫瑰 ClO2/SO2 实证论文（SCI），CNKI Scholar 可检索。期刊/年份/DOI 待补链接。';
MERGE (n:Source {id: 'paper_ice_temp'})
  SET n.title = '1-MCP结合ClO2处理对冰温贮藏红提葡萄生理品质的影响',
         n.type = '论文',
         n.access = 'paywalled',
         n.note = '冰温贮藏实证论文（红地球/红提），sciencechina 可检索。作者/期刊/年份/DOI 待补链接。';
MERGE (n:Source {id: 'paper_ca_water_crystal'})
  SET n.title = '基于主成分和相关性分析不同自发气调袋包装对水晶葡萄采后贮藏品质的影响',
         n.type = '论文',
         n.access = 'paywalled',
         n.note = '自发气调袋包装实证论文，维普可检索。作者/期刊/年份/DOI 待补链接。';
MERGE (n:Source {id: 'ops_grape_ny1199'})
  SET n.title = '葡萄保鲜技术规范（NY/T 1199-2006）',
         n.year = '2006',
         n.venue = '农业行业标准',
         n.type = '行业资料',
         n.doi_url = 'https://cssn.net.cn/cssn/productDetail/e9237d9392c56e8f5129aae25f764a36',
         n.access = 'paywalled',
         n.note = '农业行业标准，中国标准服务网/国家数字标准馆可检索。正文待获取原文（待补链接）。';
MERGE (n:Source {id: 'review_gwq_2002'})
  SET n.title = '葡萄贮藏保鲜技术研究进展',
         n.authors = '关文强;张华云;刘兴华;修德仁',
         n.year = '2002',
         n.venue = '果树学报, 2002, 19(5): 326-329',
         n.type = '综述',
         n.access = 'paywalled',
         n.note = '用户提供 PDF 原文（已本地逐条核对）；覆盖贮藏温度/冷藏/冰温/辐照/保鲜剂/气调';
MERGE (n:Source {id: 'review_sqs_2024'})
  SET n.title = '鲜食葡萄保鲜技术研究进展',
         n.authors = '邵千朔;黄桂丽;梁慧敏;孙灵湘;全鑫瑶',
         n.year = '2024',
         n.venue = '江苏农业科学, 2024, 52(4): 17-22',
         n.type = '综述',
         n.doi_url = 'https://doi.org/10.15889/j.issn.1002-1302.2024.04.003',
         n.access = 'paywalled',
         n.note = '用户提供 PDF 原文；覆盖冰温/气调/臭氧/1-MCP/热处理/辐照/生物保鲜';
MERGE (n:Source {id: 'review_so2_zyf'})
  SET n.title = '二氧化硫在鲜食葡萄保鲜中的应用研究进展',
         n.authors = '张一帆;吴培文;朱本忠',
         n.year = '2024',
         n.venue = '现代食品科技, 2024, 40(6): 311-317',
         n.type = '综述',
         n.doi_url = 'https://doi.org/10.13982/j.mfst.1673-9078.2024.6.0645',
         n.access = 'paywalled',
         n.note = '用户提供 PDF 原文；SO2 抑菌机制/品质效应/过量伤害（漂白、落粒、裂果、风味劣变）';
MERGE (n:Source {id: 'review_plant_wy_2022'})
  SET n.title = '植物提取物在葡萄保鲜中的应用研究进展',
         n.authors = '王阳;佟伟;张文江;练华山;朱志强',
         n.year = '2022',
         n.venue = '保鲜与加工, 2022, 22(4): 116-120',
         n.type = '综述',
         n.doi_url = 'https://doi.org/10.3969/j.issn.1009-6221.2022.04.015',
         n.access = 'paywalled',
         n.note = '用户提供 PDF 原文；植物提取物抑菌/涂膜保鲜';
MERGE (n:Source {id: 'review_dy_2017'})
  SET n.title = '鲜食葡萄保鲜研究新进展',
         n.authors = '邓毅;杨雪莲;刘进平;王国立;吴素芳',
         n.year = '2017',
         n.venue = '绿色科技, 2017(5)',
         n.type = '综述',
         n.access = 'public',
         n.note = '用户提供 PDF 原文；品种耐贮性规律/茶多酚与壳聚糖';

// 节点写入完毕；随后执行 graph/init_rels.cypher
MATCH (n) RETURN labels(n)[0] AS label, count(*) AS cnt ORDER BY label;
