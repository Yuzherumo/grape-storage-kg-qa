# Neo4j 实跑验证说明（docs/neo4j_verify.md）

> 结论先说：**本机网络无法下载 Neo4j 官方分发包**（`dist.neo4j.org` / `dist.neo4j.com` 对该网络一律返回 **403**），也不具备 JDK 21 与 Aura 账号。
> 因此把「Neo4j 实跑」改成三步可交付方案：**① 嵌入式 openCypher 引擎 Kùzu 真跑查询 + ② Cypher 脚本静态校验 + ③ 便携版 Neo4j 一键脚本（自带 zip 即可 3 分钟完成）**。
> 图谱数据与查询语义**已在真实 Cypher 引擎上执行并通过**；Neo4j 服务端脚本本身完整交付、可被 `cypher-shell -f` 直接导入。

## 1. 网络探测记录（为什么不能直接跑 Neo4j）

| URL | 结果 |
|---|---|
| `https://dist.neo4j.org/neo4j-community-5.26.0-windows.zip` | 403 |
| `https://dist.neo4j.org/` | 403 |
| `https://dist.neo4j.com/neo4j-community-5.26.0-windows.zip` | 403 |
| `https://neo4j.com/artifact.php?name=neo4j-community-5.26.0-windows.zip` | 403 |
| `https://neo4j.com/deployment-center/` | 200（页面可看，下载域名被拒） |
| `https://download.neo4j.org/` | 200（官网页面，非制品库） |

同时本机只有 JDK 19（Neo4j 5 需 17/21），PyCharm 自带 JBR 25（Neo4j 5.26 不支持 25）；无 Docker/WSL，无 Aura 账号 → 不能本机起 Neo4j 服务端。

## 2. 实际做了什么

### 2.1 嵌入式 openCypher 引擎实跑（Kùzu 0.11.3，Windows wheel，内存模式）

`scripts/verify_cypher_engine.py`：
1. 从 `data/entities.csv + sources.csv + triples.csv` 在 Kùzu 中建表（5 类节点表 + 9 张关系表，关系表按 schema.json 的「主/宾类型」约束）；
2. 灌入 **69 节点 / 108 条关系**，与 CSV 精确比对；
3. 对 10 类意图写等价 Cypher（REQUIRES/AFFECTS/PREVENTED_BY/INDUCED_BY/CONTRA/ALTERNATIVE/HAS_INDICATOR_VALUE/SUSCEPTIBLE_TO），**与本地后端逐题对照**；
4. 定点核对 4 条 verified 条文三元组。

实测输出（2026-11-21）：

```
Kùzu 实跑：节点 69（期望 69）/ 关系 108（期望 108）

题号 | 意图              | 本地证据 | Cypher 等价查询 | 覆盖
Q1  | temperature       | 5       | 12             | ✅
Q2  | disease_control   | 9       | 9              | ✅
Q3  | quality_indicator | 1       | 37             | ✅
Q4  | contraindication  | 3       | 5              | ✅
Q5  | variety_compare   | 12      | 24             | ✅
Q6  | temperature       | 12      | 12             | ✅

定点核对（verified 条文三元组）：
  ✅ 阳光玫瑰 -[REQUIRES]-> 相对湿度 90~95%
  ✅ 灰霉病   -[PREVENTED_BY]-> 焦亚硫酸盐缓释片
  ✅ 巨峰     -[HAS_INDICATOR_VALUE]-> 耐贮性
  ✅ 黑斑病   -[INDUCED_BY]-> 采前降雨
[通过] Kùzu 实跑 + 与本地后端一致
```

复现：

```powershell
.\.venv\Scripts\python.exe -m pip install kuzu==0.11.3   # 可选依赖
.\.venv\Scripts\python.exe scripts\verify_cypher_engine.py
```

> Kùzu 是嵌入式 openCypher 引擎，不是 Neo4j 服务端；这里验证的是**图数据模型 + 查询语义 + 参数化/过滤**，不能替代 Neo4j 的 HTTP/Bolt 服务、约束与并发行为。

### 2.2 Cypher 脚本静态校验

`scripts/validate_cypher.py`（无需任何服务）：
- 13 个 `.cypher` 文件中的节点标签 ⊆ 5 类枚举、关系类型 ⊆ 9 种谓词枚举；
- 查询模板的 `$参数` ⊆ {variety_ids, condition_ids, indicator_ids, disease_ids, entity_ids, keywords, limit}，且有 `RETURN`/`LIMIT`；
- `schema.cypher` 覆盖 5 类唯一约束；`init_nodes.cypher` MERGE 数 = 69、`init_rels.cypher` = 108（与 CSV 一致）；
- 三元组 subject/object 均能在 `entities.csv` 找到同名节点。

### 2.3 便携版 Neo4j（拿到 zip 后 3 分钟完成）

`scripts/setup_neo4j_portable.ps1`：自动下载/解压便携 JDK 21 + Neo4j 5 → 设初始密码 → 启动 → 用自带 `cypher-shell` 依次导入 `schema/init_nodes/init_rels` → 打印节点/关系计数并**二次导入验证幂等**。

网络可访问时：

```powershell
.\scripts\setup_neo4j_portable.ps1
```

网络受限时（推荐）：自己下载两个 zip（便携 JDK21 + Neo4j 5 社区版 Windows zip），然后本地导入：

```powershell
.\scripts\setup_neo4j_portable.ps1 -JdkZip D:\jdk21.zip -Neo4jZip D:\neo4j-community-5.26.0-windows.zip
```

预期结果：节点 **69**（58 实体 + 11 来源）、关系 **108**；二次导入计数不变；`cypher-shell` 可执行 `graph/queries/*.cypher`。

> 拿到 Neo4j 后如需跑双后端一致性测试：安装驱动后执行
> `pip install neo4j` → 设置 `.env` 的 `NEO4J_URI/USER/PASSWORD` → `pytest tests/test_backend_parity.py -q`（当前因无驱动/无服务自动 skip）。

## 3. 诚实边界

1. 本文件证明的是「图数据 + Cypher 查询能跑且与本地后端一致」；
2. **Neo4j 服务端本身未在本机启动过**，原因是下载域名 403（见 §1）；
3. 交付物已把「起 Neo4j 并导入」做成一条命令，任何能拿到 zip 的机器都能复现，不存在代码缺口；
4. 演示默认仍走 `local` 后端（零依赖、离线可用），Neo4j 属可选验证路径。
