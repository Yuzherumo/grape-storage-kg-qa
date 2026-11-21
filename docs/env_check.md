# 环境自检（docs/env_check.md）

> 由 `scripts/env_check.py` 自动生成（不联网）。
> 重新生成：`.\.venv\Scripts\python.exe scripts\env_check.py`

- 采集时间：2026-11-21 19:09:32
- 操作系统：`Windows-11-10.0.26100-SP0`
- Python：`3.12.14`（`C:\Users\21629\Desktop\农课松\.venv\Scripts\python.exe`）
- 工作目录：`C:\Users\21629\Desktop\农课松`
- .env：无 .env 文件

## 1. 依赖版本

依赖 | 版本
---|---
pytest | 9.2.0
streamlit | 1.67.0
openai | 3.57.0
pandas | 3.1.1
python-dotenv | 1.2.4
neo4j | 未安装

## 2. 关键环境变量

变量 | 状态
---|---
GRAPH_BACKEND | 未设置
DATA_DIR | 未设置
DEEPSEEK_API_KEY | 未设置
DEEPSEEK_MODEL | 未设置
DEEPSEEK_BASE_URL | 未设置
NEO4J_URI | 未设置
NEO4J_USER | 未设置
NEO4J_PASSWORD | 未设置
UI_PORT | 未设置

## 3. 图谱后端

- 配置后端（GRAPH_BACKEND）：`local`
- 本地后端可用性：✅ 可用 —— local: 48 节点 / 71 条边（triples_shine_muscat.csv、triples.csv，data_dir=C:\Users\21629\Desktop\农课松\data）
- 图谱统计：`{'backend': 'local', 'nodes': 48, 'rels': 71, 'varieties': 8, 'conditions': 21, 'indicators': 13, 'diseases': 6, 'sources': 11, 'unresolved_edges': 0, 'data_files': ['triples_shine_muscat.csv', 'triples.csv']}`
- Neo4j：未安装 neo4j 驱动（可选，本地后端已足够离线演示）

## 4. LLM 可用性（不发起真实请求）

- 状态：⭕ 不可用（预期行为）—— 未配置 DEEPSEEK_API_KEY，问答自动走离线模板模式（模型 deepseek-chat）

## 5. 数据与图谱文件

文件 | 状态
---|---
data/entities.csv | 存在（9313 B，49 行）
data/triples.csv | 存在（31227 B，72 行）
data/sources.csv | 存在（3468 B，12 行）
data/schema.json | 存在（9901 B，225 行）
data/triples_shine_muscat.csv | 存在（9305 B，21 行）
graph/schema.cypher | 存在（3298 B，70 行）
graph/init_nodes.cypher | 存在（25838 B，534 行）
graph/init_rels.cypher | 存在（59020 B，1069 行）
graph/queries/*.cypher | 10 个查询模板

## 6. 结论

- ✅ **无网络、无 API key 也能完成离线演示**：本地图谱后端可用，LLM 不可用时问答自动走模板模式（答案仍带 `[E#]` 引用与分步动作）。
- pytest：9.2.0；运行全量测试：`.\.venv\Scripts\python.exe -m pytest tests -q`
