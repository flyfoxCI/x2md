# Expert Content Studio

将公开专家内容沉淀为可检索、可编辑、可导出的知识库。输入一条公开 HTTPS 链接，服务端会抓取并规范化内容；配置兼容 OpenAI 的 AI 服务后，可生成中文翻译、知识摘要和可复用 Skill Markdown。

对于 GitHub、arXiv 和 Hugging Face，产品还提供“深度研究”工作流：它不是 README 或摘要的改写，而是从版本固定、预算受限的公开材料中建立证据集，逐条生成研究笔记，并产出有章节和可验证 `[E<n>]` 引文的中文研究报告。每次运行都会保存覆盖范围、没有采集的材料及其原因；AI 推荐标签必须经用户接受后才会影响知识库筛选。

支持的来源包括通用公开网页、GitHub 公开仓库、arXiv 论文、Hugging Face 模型/数据集页面、可公开获得字幕的 YouTube 视频，以及配置 X API bearer token 后的 X 帖子。详细 API 合同见 [docs/api.md](docs/api.md)。

## Quick start (development)

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), Node 24+ and npm.

```sh
cp .env.example .env
cd backend
set -a; . ../.env; set +a
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```sh
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

Open <http://127.0.0.1:5173>. Vite proxies `/api` to `http://127.0.0.1:8000` by default. To use another local backend, run `VITE_DEV_API_PROXY_TARGET=http://127.0.0.1:9000 npm run dev -- --host 127.0.0.1 --port 5173`. Check the API directly with:

```sh
curl -fsS http://127.0.0.1:8000/api/health
```

The default development database is `backend/expert-content-studio.db`. It is intentionally ignored by Git. Use `DATABASE_URL` for another SQLite file or PostgreSQL. Migrations must be run from `backend`:

```sh
DATABASE_URL='postgresql://USER:PASSWORD@HOST:5432/DB' uv run alembic upgrade head
```

## Deep research workflow

1. 导入公开 GitHub 仓库、arXiv 论文或 Hugging Face 模型/数据集，打开该来源。
2. 在工作区顶部选择“开始深度研究”。运行会持久化为 queued/running/terminal 状态，离开页面后仍可恢复查看。
3. 在“深度研究”tab 阅读报告；报告中的 `[E<n>]` 只会在对应证据已持久化时显示为可点击证据控制。
4. 展开证据清单查看采集和排除记录；在“标签治理”中接受/拒绝 AI 建议，或添加/移除自定义标签。只有已接受标签参与侧栏筛选。

自动研究默认关闭。选中受支持来源后可勾选“新导入后自动研究”；设置会保存，**重启后端服务**后单一后台 worker 会处理此后导入的受支持来源。自动模式仅处理来源成功导入且确有公开内容的情况；手动启动始终可用。

| 平台 | 研究证据 | 固定上限 | 明确不采集 |
| --- | --- | --- | --- |
| GitHub | README、manifest、入口、架构文档和优先级最高的源文件；定位到 commit | 20 个文本文件、1.5 MiB、32 请求/run | 私有仓库、vendor、二进制、minified/generated 文件 |
| arXiv | 版本化公开 PDF 的页级文本 | 25 MiB PDF、60 页、50 万字符、32 请求/run | OCR、加密/无文本 PDF 的伪造文本 |
| Hugging Face | card、配置和小型源码文本；定位到 revision | 12 个文件、1 MiB、32 请求/run | 模型权重、数据集载荷及其他二进制对象 |

报告在写入前接受固定章节和引文校验：背景与目标、核心贡献、方法或架构、实现/实验与配置、关键结果、局限与风险、复现与应用建议等实质段落必须引用同一运行中的证据。编辑研究报告会创建普通的 `user_edit` 版本，界面会明确标注该版本不再自动验证引用。

## AI and provider configuration

Derivation and source-scoped chat are disabled until all three server environment values are present:

```dotenv
AI_BASE_URL=https://your-compatible-provider.example/v1
AI_API_KEY=
AI_MODEL=
```

`AI_BASE_URL` must be an OpenAI-compatible API base URL: the backend calls its `/chat/completions` path. `AI_API_KEY` is read only by the backend and is never returned by any API response. With an incomplete configuration, import/search/edit/export continue to work and AI endpoints return `provider_not_configured`.

`X_BEARER_TOKEN` is optional and is also server-only. Without it, X imports retain only public metadata when available; no post text is invented. `GITHUB_TOKEN` is optional and only improves GitHub API access for public repositories.

## Source restrictions and safety

Only public HTTPS URLs are accepted. The importer rejects localhost, private/link-local/loopback addresses, URL credentials and unsafe redirect targets before fetching. Platform behavior is deliberately conservative:

- GitHub imports public repository metadata and README when available; private/restricted repositories are not imported. Deep research may additionally read the bounded text evidence listed above.
- arXiv imports record metadata and abstract. Deep research may additionally parse a bounded public text-layer PDF; it does not use OCR.
- Hugging Face imports public model/dataset metadata and cards where available. Deep research may additionally read selected small config/source files, never weights or dataset payloads.
- YouTube imports oEmbed metadata plus a public transcript only when it can be retrieved. Missing captions yield a `partial` source, not fabricated content.
- X uses X API v2 only when `X_BEARER_TOKEN` is configured. If text cannot be legally retrieved, the source is partial or blocked with an explicit reason.

Provider/API access can change independently of the application. A successful URL submission does not imply the source is accessible, and a partial source cannot be used to fabricate AI material.

Initial imports run synchronously within the HTTP request. Deep research is intentionally separate: it uses a durable database queue and a single lifecycle-owned worker, with a lease and at most two retries after the initial attempt for transient collection/provider failures. This worker is a local single-instance design, not a distributed job system.

## Docker Compose

Docker Compose runs production-built frontend, backend, and an internal PostgreSQL service locally. The frontend Nginx server reverse-proxies `/api` to the backend, so the browser uses the same-origin production API path. No build-time AI or source-provider secrets are required.

```sh
cp .env.example .env
docker compose up --build
```

The app is available at <http://127.0.0.1:5173>; the backend health endpoint is available only locally at <http://127.0.0.1:8000/api/health>. Compose runs Alembic before serving the API and stores PostgreSQL data in the named `expert-content-studio-data` volume. The database has no host port. `POSTGRES_HOST_AUTH_METHOD=trust` is used only for this isolated local Compose network; use real credentials and a managed database for a production deployment. Stop services with `docker compose down`; include `--volumes` only if you intentionally want to delete all local knowledge data.

For a local production-client check after startup:

```sh
curl -fsS http://127.0.0.1:8000/api/health
curl -I http://127.0.0.1:5173/
```

## Verification

```sh
cd backend
uv run pytest -q -W error
uv run ruff check .
TASK_DB=$(mktemp)
DATABASE_URL="sqlite+pysqlite:///$TASK_DB" uv run alembic upgrade head

cd ../frontend
npm run lint
npm run test -- --run
npm run build

cd ..
docker compose config
```
