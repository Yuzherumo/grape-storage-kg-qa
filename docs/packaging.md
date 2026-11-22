# 交付打包说明（docs/packaging.md）

> 目标：把「什么该交、什么不该交、怎么交、评委怎么跑」一次说清，避免把密钥或第三方 PDF 打包出去。

## 1. 交付物对照（比赛要求 → 本仓库位置）

| 比赛要求 | 交付形式 | 位置 |
|---|---|---|
| 在线 Demo | 本机可运行演示（无公网时按录屏/现场演示） | `.\run.ps1` → `http://127.0.0.1:8501` |
| 200 字简介 | Markdown 定稿（200 字以内） | `docs/submission.md` |
| 代码仓库 / ANS 作品快照 | 干净 zip 快照 + 可选 git bundle（开发历史） | `.\scripts\make_release.ps1` → `dist/` |
| 原创与 AI 使用说明 | Markdown | `docs/ai_usage.md` |
| 3 分钟录屏（建议） | 分镜脚本（视频待录） | `docs/demo_script.md` |
| 评测证据 | 自动生成报告 | `docs/eval_results.md` |
| 来源清单 | 19 条来源；69 条 verified（51 条按国标条文、10 条按综述原文、8 条按 MOA/2018 论文升级） | `docs/sources.md`、`docs/data.md` |

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
.\scripts\make_release.ps1 -Version v1.1

# 跳过测试（时间紧）
.\scripts\make_release.ps1 -Version v1.1 -SkipTests

# 额外保留开发历史（原创性证据）
.\scripts\make_release.ps1 -Version v1.1 -WithGitBundle
```

产物（`dist/`，已 gitignore）：
- `grape-storage-kg-qa-v1.1.zip` —— 干净快照
- `grape-storage-kg-qa-v1.1.zip.sha256` —— 校验和
- `MANIFEST-v1.1.md` —— 包含/排除清单 + 评审运行步骤
- 可选 `grape-storage-kg-qa-v1.1.bundle` —— git 历史

## 4. 本机资料（不随包分发）

- 5 篇综述 PDF 与国标 PDF 统一放在 **`.refs/`**（已 gitignore），仅用于本机核对引文；打包脚本不会收录。
- 若需要把原件给评委核对，单独用赛事平台附件/网盘提供，并注明版权归属。

## 5. 打包后自检清单

1. 解压到**全新目录**，运行 `.\install.ps1` → 应成功建 `.venv` 并装依赖；
2. `.\run.ps1 -Check` → 十项数据校验 + Cypher 静态校验 + 图谱加载（77 节点 / 115 关系）全过；
3. `.\run.ps1` → 8501 打开，6 个示例问题可答（离线模式）；
4. `python -m pytest tests -q` → 287 passed / 2 skipped；
5. 搜索包内不应出现 `sk-`、`.env`、`*.pdf`。

## 6. 验收记录（2026-11-22 第三轮实跑，正式交付包 v1.1）

1. `make_release.ps1 -Version v1.1` → `dist/grape-storage-kg-qa-v1.1.zip`（**约 937 KB / 94 文件**；精确大小与 SHA256 以 `MANIFEST-v1.1.md` 和同名 `.sha256` 为准）+ `MANIFEST-v1.1.md` + `.sha256`；
2. 包内检查：无 `.env`、无真实密钥、无 `*.pdf`、无 `.git/.venv/.tmp/.refs`、无 `__pycache__`；含 `app/graph_interactive.py`、`app/graph_view.py`、`data/descriptions.csv`、`.streamlit/config.toml`、5 个 `.ps1`；
3. `install.ps1` 修复后回归（本机 3.12）：
   - 负路径（`PIP_NO_INDEX=1`，模拟装不上）：**exit 1、~12.6s、无 REPL 挂起、无 `--python` 顺序错误**；
   - fallback 路径（venv 无 pip + ensurepip 失败 + 本地 wheel）：`Successfully installed six-1.17.0`，venv 内 `import six` OK，依赖自检按预期 exit 1；
   - 现有 `.venv`（无 pip）走 fallback：pip 退出 0，6 包 import 自检 `DEPS_OK streamlit 1.67.0 / openai 3.57.0 / pandas 3.1.1 / dotenv 1.2.4 / pytest 9.2.0 / kuzu 0.11.3` 通过（20s）；
4. `run.ps1 -Check`（现有 .venv）→ exit 0、约 1s：十项数据校验 ✅、Cypher 静态校验 ✅、图谱加载 ✅（77 节点 / 115 关系）；
5. **未完成项（如实记录）**：本机 DSH 沙箱对 Python `tempfile(0o700)` 目录有 ACL 限制，全新 venv 的**真实全量联网安装**无法在本环境完成（pip 卡住/报 PermissionError，日志 `.tmp/install_test_logs/`）；需在正常 Windows + Python 3.12 机器上复跑一次 `install.ps1` 做最终确认。`install.ps1` 的负路径/fallback/现有 venv 路径均已实测通过。

## 7. 已知未完成项

- 公网 Demo 已上线，但**线上版本落后于本地工作树**（2026-11-22 10:40 实测：线上仓库 28 文件/最后提交 09:10，缺 `.streamlit/config.toml`；与本地 16 个文件不同），需用有账号者上传 `dist/modelscope-studio-upload.zip` 后按 `docs/deploy.md` §E 复核；
- 3 分钟录屏与截图素材（脚本已就绪，需人工录制）；
- ANS 平台快照需按平台要求上传（本仓库提供 `dist/grape-storage-kg-qa-v1.1.zip` + 可选 git bundle 作为快照内容）。
