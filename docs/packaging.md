# 交付打包说明（docs/packaging.md）

> 目标：把「什么该交、什么不该交、怎么交、评委怎么跑」一次说清，避免把密钥或第三方 PDF 打包出去。

## 1. 交付物对照（比赛要求 → 本仓库位置）

| 比赛要求 | 交付形式 | 位置 |
|---|---|---|
| 在线 Demo | 本机可运行演示（无公网时按录屏/现场演示） | `.\run.ps1` → `http://127.0.0.1:8501` |
| 200 字简介 | Markdown 定稿（195 字） | `docs/submission.md` |
| 代码仓库 / ANS 作品快照 | 干净 zip 快照 + 可选 git bundle（开发历史） | `.\scripts\make_release.ps1` → `dist/` |
| 原创与 AI 使用说明 | Markdown | `docs/ai_usage.md` |
| 3 分钟录屏（建议） | 分镜脚本（视频待录） | `docs/demo_script.md` |
| 评测证据 | 自动生成报告 | `docs/eval_results.md` |
| 来源清单 | 16 条来源 + 51 条国标引文 + 10 条综述引文 | `docs/sources.md` |

## 2. 打包原则：白名单收录、黑名单强校验

**收录（白名单）**：`app/ data/ graph/ scripts/ tests/ docs/ .github/ .streamlit/`、`README.md`、`LICENSE`、`requirements.txt`、`pyproject.toml`、`pytest.ini`、`.env.example`、`.gitignore`、`run.ps1`、`install.ps1`、`app.py`（云端入口）。

**排除（黑名单）**：
| 项 | 原因 |
|---|---|
| `.env` | 含真实 `DEEPSEEK_API_KEY`；只保留 `.env.example` |
| `.streamlit/secrets.toml` | 云端密钥文件；只保留 `.streamlit/secrets.toml.example` |
| `*.pdf` | 第三方标准/论文原件，版权原因不随包分发；只保留题录与条级摘录 |
| `.venv/ .tools/ .refs/ .tmp/` | 本机环境、下载物、缓存 |
| `.git/` | 如需开发历史，用 `-WithGitBundle` 另生成 `git bundle` |
| `__pycache__/ .pytest_cache/ dist/ *.log` | 缓存与产物 |

打包脚本会对生成后的 zip **再解包校验一次**：一旦发现 `.env`、`*.pdf`、`.venv`、`.refs`、`.git` 等文件，直接失败退出。

## 3. 一键打包

```powershell
# 校验 + 测试 + 打包（推荐）
.\scripts\make_release.ps1 -Version v1.0

# 跳过测试（时间紧）
.\scripts\make_release.ps1 -Version v1.0 -SkipTests

# 额外保留开发历史（原创性证据）
.\scripts\make_release.ps1 -Version v1.0 -WithGitBundle
```

产物（`dist/`，已 gitignore）：
- `grape-storage-kg-qa-v1.0.zip` —— 干净快照
- `grape-storage-kg-qa-v1.0.zip.sha256` —— 校验和
- `MANIFEST-v1.0.md` —— 包含/排除清单 + 评审运行步骤
- 可选 `grape-storage-kg-qa-v1.0.bundle` —— git 历史

## 4. 本机资料（不随包分发）

- 5 篇综述 PDF 与国标 PDF 统一放在 **`.refs/`**（已 gitignore），仅用于本机核对引文；打包脚本不会收录。
- 若需要把原件给评委核对，单独用赛事平台附件/网盘提供，并注明版权归属。

## 5. 打包后自检清单

1. 解压到**全新目录**，运行 `.\install.ps1` → 应成功建 `.venv` 并装依赖；
2. `.\run.ps1 -Check` → 十项数据校验 + Cypher 静态校验 + 图谱加载（74 节点 / 108 关系）全过；
3. `.\run.ps1` → 8501 打开，6 个示例问题可答（离线模式）；
4. `python -m pytest tests -q` → 118 passed / 2 skipped；
5. 搜索包内不应出现 `sk-`、`.env`、`*.pdf`。

## 6. 验收记录（2026-11-21 实跑）

1. `make_release.ps1 -Version v1.0` → `dist/grape-storage-kg-qa-v1.0.zip`（**241.3 KB / 71 文件**）+ `MANIFEST-v1.0.md` + `.sha256`；
2. 解压到**全新空目录**逐项检查：无 `.env`、无 `*.pdf`、无 `.venv/.refs/.tools`；
3. 在空目录运行 `install.ps1 -PythonExe <本机3.12>` → 成功创建 `.venv` 并装齐依赖（该 3.12 是无 pip 的打包版，验证了 `pip --python` 兜底路径）；
4. 在空目录运行 `run.ps1 -Check` → 十项数据校验 ✅、Cypher 静态校验 ✅、图谱加载 ✅（74 节点 / 108 关系）；
5. 因此「评委拿到 zip → 解压 → install → run」的完整链路已实测可走通。

## 7. 已知未完成项

- 公网可访问 Demo（需账号/部署，比赛投票环节要求）；
- 3 分钟录屏与截图素材（脚本已就绪，需人工录制）；
- ANS 平台快照需按平台要求上传（本仓库提供 zip + git bundle 作为快照内容）。
