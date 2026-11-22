# 公网 Demo 部署指南（docs/deploy.md）

## 已部署实例（2026-11-21 首次上线；2026-11-22 真实复核）

| 项 | 值 |
|---|---|
| 平台 | 魔搭 ModelScope 创空间（免费 CPU 2vCPU/8GB，Streamlit SDK） |
| 应用直达地址 | **https://yuzherumo-grape-storage-kg-qa.ms.show** |
| 空间主页 | https://www.modelscope.cn/studios/YUZHERUMO/grape-storage-kg-qa |
| 服务可达性 | Running（2026-11-22 10:40 实测：`/`=HTTP 200、`/_stcore/health`=ok） |
| 线上代码版本 | **未同步到本地最新工作树**：线上仓库最后提交 2026-11-22 09:10（28 个文件）；本轮修复后本地与线上有 16 个文件内容差异，且线上缺 `.streamlit/config.toml` |
| 待办（需账号） | 登录魔搭 → 上传 `dist/modelscope-studio-upload.zip`（26 个运行必需文件，SHA256 见 §E）→ 重启/构建 → 按 §E 复核；**上传成功前不得声称线上已更新** |
| 环境变量 | `DEEPSEEK_API_KEY`（密文）+ `DEEPSEEK_MODEL` / `DEEPSEEK_BASE_URL` / `GRAPH_BACKEND`（明文） |

> 注：Streamlit Community Cloud 在该网络登录被 403 拦截（平台反滥用误伤），故改走魔搭；详见下文方案 B。

> 目标：把本地 Streamlit 应用变成一个**评委/投票者能直接打开的 https 链接**。
> 数据只读（`data/` 约 1MB），不需要数据库、不需要 GPU；无 API Key 时自动走离线模板模式，**任何方案都能跑**。

## 0. 先决条件（三选一，按你的账号情况挑）

| 方案 | 需要什么 | 适合 | 国内访问 |
|---|---|---|---|
| **A. Streamlit Community Cloud** | GitHub 账号 | 最省事、免费、自动更新 | 一般可访问，偶尔慢 |
| **B. 魔搭 ModelScope 创空间** | 阿里云账号 | 国内访问快、比赛常用 | 快 |
| **C. 本地 + 内网穿透** | 无需账号（cloudflared 快速隧道） | 临时投票/现场演示 | 取决于隧道域名 |
| D. 云服务器自建（可选） | 云主机 + 域名（需实名/付费） | 最稳定 | 快 |

本仓库已为 A/B 准备好：根目录 `app.py`（平台默认入口）、`.streamlit/config.toml`（主题）、
`.streamlit/secrets.toml.example`（Secrets 模板）；`app/ui.py` 会自动把 `st.secrets` 注入环境变量，
因此**云端不需要 `.env`**。

---

## A. Streamlit Community Cloud（推荐，免费）

### A1. 推送到 GitHub

```powershell
cd C:\Users\21629\Desktop\农课松
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git branch -M main
git push -u origin main
```

> 仓库里不要提交 `.env`、`*.pdf`、`dist/`、`.refs/`（已在 `.gitignore`）。

### A2. 建应用

1. 打开 <https://share.streamlit.io>，用 GitHub 登录；
2. **New app** → 选仓库 + 分支 `main` + 主文件路径填 **`app.py`**（或 `app/ui.py`）；
3. **Advanced settings**：Python 选 **3.12**；
4. **Secrets** 粘贴（没有 key 就留空，应用会自动离线模式）：

```toml
DEEPSEEK_API_KEY = "sk-你的key"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
GRAPH_BACKEND = "local"
```

5. **Deploy**，等 1~2 分钟，得到 `https://<名字>.streamlit.app`。

### A3. 注意事项

- 免费实例空闲会**休眠**，第一次访问冷启动 20~60 秒；投票期间保持一次访问即可；
- 修改代码 push 后自动重新部署；
- 内存 1GB 足够（应用常驻约 100~200MB）；
- 若依赖安装失败：把 `requirements.txt` 里的 `kuzu` 那行注释掉即可（只有命令行验证脚本用到它，页面不需要）。
- Secrets 里的 key 不会出现在前端代码里；**赛事结束后去 DeepSeek 控制台吊销**。

---

## B. 魔搭 ModelScope 创空间（国内访问快）

1. 注册/登录 <https://modelscope.cn>（阿里云账号）；
2. **创建创空间** → SDK 选 **Streamlit** → 可见性选公开；
3. 上传代码（网页上传 zip 或 `git clone` 后 push），入口文件用根目录 **`app.py`**；
4. 在创空间 **设置 → 环境变量/Secrets** 加 `DEEPSEEK_API_KEY` 等；
5. 构建完成后得到 `https://modelscope.cn/studios/<用户>/<空间名>` 形式的访问地址。

> 与 A 的代码完全一致；`requirements.txt` 里的 `kuzu` 若在创空间装不上，同样注释掉即可。

---

## C. 本地 + 内网穿透（临时 URL，无需注册）

### C1. cloudflared 快速隧道

```powershell
# 已装过：直接起
cloudflared tunnel --url http://127.0.0.1:8501
# 未装：winget install --id Cloudflare.cloudflared -e
# 或从 https://github.com/cloudflare/cloudflared/releases 下载 exe 放到 PATH
```

启动后终端会打印形如 `https://<随机>.trycloudflare.com` 的地址，把它发给评委即可。
本方法**不登录、不绑卡**，但：
- 你的电脑必须保持开机、服务保持运行；
- 地址是临时的，进程重启就变；
- 适合现场演示/录屏，不建议长期挂投票页。

仓库内封装了脚本：`.\scripts\run_public_tunnel.ps1`（自动找 cloudflared / 打印地址 / 写日志）。

### C2. 备选：localhost.run（需要本机有 ssh）

```powershell
ssh -R 80:127.0.0.1:8501 nokey@localhost.run
```

### C3. 国内穿透服务

花生壳 / natapp / cpolar：注册后映射本地 8501，拿到固定二级域名（免费版有限速/临时域名）。

---

## D. 云服务器（可选，最稳）

```bash
# Ubuntu 示例
git clone <仓库> && cd <仓库>
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

- 安全组放行 8501（或 Nginx 反代 80/443）；
- 用 `nssm`/`systemd` 守护进程；
- 环境变量里配 `DEEPSEEK_API_KEY`（不要写进代码）。

---

## 部署前检查清单

```powershell
.\run.ps1 -Check          # 数据十项 + Cypher 静态校验 + 图谱加载
.\scripts\make_release.ps1 -Version v1.1   # 生成干净快照（自动排除 .env / PDF）
```

1. 仓库/上传包里**没有** `.env`、`*.pdf`；
2. 平台 Secrets 里配好 `DEEPSEEK_API_KEY`（或故意不配，走离线模式）；
3. 打开公网地址：侧栏模型 chip 显示「在线」；提一个示例问题能出答案与「依据」；
4. 记录 Demo URL + 对应 commit（`git rev-parse --short HEAD`）写进提交材料；
5. 赛事结束后吊销 key、关闭实例。


## E. 线上核验与重新部署（2026-11-22 真实检查记录）

**检查方式（真实线上 API，不依赖本地文件）**：调用魔搭创空间仓库接口
`https://modelscope.cn/api/v1/studio/yuzherumo/grape-storage-kg-qa/repo/files?Revision=master` 列目录，再用
`.../repo?Revision=master&FilePath=<path>` 取文件内容，与本地工作树逐文件比对。

**核验结果**：
- 线上仓库 28 个文件，最后提交时间 **2026-11-22 09:10:24**；
- 线上**缺少** `.streamlit/config.toml`（网页上传隐藏目录的遗漏）；
- 与当前本地工作树相比，`app.py`、`app/config.py`、`app/contracts.py`、`app/graph_interactive.py`、`app/graph_view.py`、`app/linking.py`、`app/llm.py`、`app/planner.py`、`app/qa.py`、`app/store/*`、`app/ui.py`、`data/triples.csv` 等 **16 个文件内容不同**；
- 因此**当前线上不是最新版本**（README 中「演示桩/HTML 转义/引用回退/多轮继承」等第三轮行为尚未上线）。

**已准备好的上传包**（本地生成，未上传）：
- 路径：`dist/modelscope-studio-upload.zip`
- 文件数：**26**（`app.py`、`requirements.txt`、`.streamlit/config.toml`、`app/**`、`data/**` 全部运行必需文件；含 `app/graph_interactive.py`、`app/graph_view.py`、`data/descriptions.csv`）
- SHA256：`f2eff9990379dd9b384d0e86e92f02d02123aeadc9ff7c0737bbad8e55668cd3`
- 生成方式：按白名单从工作树打包（无 `.env`、无 PDF、无 `.git/.venv/.tmp/__pycache__`）。

**重新部署步骤（需魔搭账号，本环境无凭据，未执行）**：
1. 打开空间 → 设置/文件管理 → 上传上述 zip 或逐文件覆盖（务必包含 `.streamlit/config.toml`）；
2. 重启/重新构建空间，等待 Running；
3. 复检命令（PowerShell，无需账号）：
   ```powershell
   Invoke-WebRequest "https://yuzherumo-grape-storage-kg-qa.ms.show/_stcore/health" -UseBasicParsing
   # 再取线上 app/qa.py 与本地对比 SHA256（见上文的 repo API 方法）
   ```
4. 记录新的线上提交时间/文件数，回填本表「线上代码版本」。

## 已知限制

- 免费实例会休眠、并发低，不适合压测；
- 公网 Demo 当前**并非**与本地同一版本（线上 09:10，本地第三轮修复后更新）；重新上传后需按 §E 复核，PDF 原文不随部署上传（版权）；
- 若评委网络访问 Streamlit Cloud 慢，优先给 B（魔搭）或 C（临时隧道）地址。
