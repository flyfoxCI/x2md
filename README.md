# Expert Content Studio

将公开专家内容沉淀为可检索、可编辑、可导出的知识库。输入一条公开 HTTPS 链接，服务端会抓取并规范化内容；配置兼容 OpenAI 的 AI 服务后，可生成中文翻译、知识摘要和可复用 Skill Markdown。

对于 GitHub、arXiv 和 Hugging Face，产品还提供“深度研究”工作流：它不是 README 或摘要的改写，而是从版本固定、预算受限的公开材料中建立证据集，逐条生成研究笔记，并产出有章节和可验证 `[E<n>]` 引文的中文研究报告。每次运行都会保存覆盖范围、没有采集的材料及其原因；AI 推荐标签必须经用户接受后才会影响知识库筛选。

支持的来源包括通用公开网页、GitHub 公开仓库、arXiv 论文、Hugging Face 模型/数据集页面、可公开获得字幕的 YouTube 视频，以及配置 X API bearer token 后的 X 帖子。详细 API 合同见 [docs/api.md](docs/api.md)。

## Quick start (development)

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), Node 24+ and npm.

```sh
cp .env.example .env
# Before starting an empty database, set a unique AUTH_INITIAL_ADMIN_PASSWORD
# in this untracked file (or inject it from your deployment secret manager).
# For this local HTTP server only, set AUTH_COOKIE_SECURE=false in .env.
cd backend
uv sync
uv run --env-file ../.env alembic upgrade head
uv run --env-file ../.env uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
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

The default development database is `backend/expert-content-studio.db`. It is intentionally ignored by Git. Use `DATABASE_URL` in `.env` for another SQLite file or PostgreSQL. Migrations must be run from `backend` with the same dotenv parser:

```sh
uv run --env-file ../.env alembic upgrade head
```

## Deep research workflow

1. 导入公开 GitHub 仓库、arXiv 论文或 Hugging Face 模型/数据集，打开该来源。
2. 在工作区顶部选择“开始深度研究”。运行会持久化为 queued/running/terminal 状态，离开页面后仍可恢复查看。
3. 在“深度研究”tab 阅读报告；报告中的 `[E<n>]` 只会在对应证据已持久化时显示为可点击证据控制。
4. 展开证据清单查看采集和排除记录；在“标签治理”中接受/拒绝 AI 建议，或添加/移除自定义标签。只有已接受标签参与侧栏筛选。

自动研究默认开启。新导入的受支持来源会自动进入深度研究队列，也可在界面关闭自动研究。单一后台 worker 始终运行，因此手动任务和已经排队的任务无需依赖自动研究开关或重启服务。自动模式仅处理来源成功导入且确有公开内容的情况；手动启动始终可用。

| 平台 | 研究证据 | 固定上限 | 明确不采集 |
| --- | --- | --- | --- |
| GitHub | README、manifest、入口、架构文档和优先级最高的源文件；定位到 commit | 20 个文本文件、1.5 MiB、32 请求/run | 私有仓库、vendor、二进制、minified/generated 文件 |
| arXiv | 版本化公开 PDF 的页级文本 | 25 MiB PDF、60 页、50 万字符、32 请求/run | OCR、加密/无文本 PDF 的伪造文本 |
| Hugging Face | card、配置和小型源码文本；定位到 revision | 12 个文件、1 MiB、32 请求/run | 模型权重、数据集载荷及其他二进制对象 |

报告在写入前接受固定章节和引文校验：背景与目标、核心贡献、方法或架构、实现/实验与配置、关键结果、局限与风险、复现与应用建议等实质段落必须引用同一运行中的证据。编辑研究报告会创建普通的 `user_edit` 版本，界面会明确标注该版本不再自动验证引用。

Do not `source` or dot-execute `.env`: it is configuration data, not shell
code. `uv run --env-file ../.env` parses it without executing it. For a secret
containing shell metacharacters such as `$`, backticks, `;`, or `$()`, use valid
single-quoted dotenv syntax so those characters stay literal rather than being
expanded by a shell.

## Authentication and deployment security

Authentication is enabled by default and this release intentionally supports one
administrator only. Before the first startup against an empty database, inject a
unique `AUTH_INITIAL_ADMIN_PASSWORD` from the deployment environment or an
untracked local `.env` file. `.env.example` deliberately leaves that value empty;
the repository and Compose file never supply a usable administrator password.
`AUTH_INITIAL_ADMIN_USERNAME` defaults to `admin`, and
`AUTH_SESSION_TTL_SECONDS` defaults to 43,200 seconds (12 hours; accepted range
900–2,592,000).

If authentication is enabled and an empty database starts without a non-empty
bootstrap secret, the backend stops with
`AUTH_INITIAL_ADMIN_PASSWORD must be set before starting an empty database`.
This is intentional: it prevents a first administrator from being created with a
known or missing password.

Sign in once as the bootstrap administrator, change the password immediately in
the application, then remove `AUTH_INITIAL_ADMIN_PASSWORD` from the host
environment or local `.env` and restart when practical. The bootstrap secret is
only needed to create the first user; it is not a replacement for ongoing
credential rotation.

For an internet-facing deployment, terminate HTTPS at a reverse proxy and expose
the frontend and `/api` through the same scheme and host. Keep
`AUTH_COOKIE_SECURE=true` there so browsers only send the session cookie over
HTTPS. Configure login rate limiting at that edge/proxy by client IP. The
loopback-only Docker Compose example is HTTP local development and deliberately
sets `AUTH_COOKIE_SECURE=false`; it is not a production TLS configuration.

There is no self-service registration, second administrator, role model,
tenant isolation, SSO, or built-in login rate limiter in this release. Those are
explicit non-goals rather than security guarantees provided by the application.

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

Initial imports run synchronously within the HTTP request. Deep research is intentionally separate: it uses a durable database queue and a single lifecycle-owned worker. Collected evidence, individual evidence notes, and a validated final report are durable checkpoints, so retries resume at the missing note, report, or tag stage instead of repeating completed collection and analysis. The report is committed before tag generation, so a tag-provider timeout cannot discard correct research output; if every tag retry is exhausted, the run remains `partial` with the report available instead of becoming a report-less failure. Each AI request allows a longer read window and retries transient timeouts, network failures, rate limits, and all server failures with exponential backoff; the worker retains two additional run-level recovery attempts and renews its lease during long provider calls. This worker is a local single-instance design, not a distributed job system.

For DeepSeek V4 model names, report and structured-tag requests use DeepSeek's official non-thinking control and a larger report output budget. This prevents default high-effort reasoning from consuming the entire completion budget before any report text is emitted; other OpenAI-compatible model names do not receive this provider-specific field.

## Docker Compose (local HTTP development)

Docker Compose runs production-built frontend, backend, and an internal PostgreSQL service on loopback addresses only. The frontend Nginx server reverse-proxies `/api` to the backend, so the browser uses a same-origin API path. It does not configure TLS. No build-time AI or source-provider secrets are required.

```sh
cp .env.example .env
docker compose up --build
```

Before `docker compose up`, place the unique bootstrap secret in the untracked
`.env` file or provide `AUTH_INITIAL_ADMIN_PASSWORD` through the host environment;
the host value is passed through without being baked into the image. It is still
an ordinary container environment variable, not a Docker secret: anyone with
access to the Docker host/daemon may be able to inspect it. Use a deployment
secret mechanism appropriate to that host for production. If the named database
volume is new, authentication is enabled, and that secret is absent or blank,
the backend fails closed rather than serving an uninitialized administrator
account.

The app is available at <http://127.0.0.1:5173>; the backend health endpoint is available only locally at <http://127.0.0.1:8000/api/health>. Compose deliberately sets `AUTH_COOKIE_SECURE=false` because these local endpoints use HTTP. Compose runs Alembic before serving the API and stores PostgreSQL data in the named `expert-content-studio-data` volume. The database has no host port. `POSTGRES_HOST_AUTH_METHOD=trust` is used only for this isolated local Compose network; use real credentials and a managed database for a production deployment. Stop services with `docker compose down`; include `--volumes` only if you intentionally want to delete all local knowledge data.

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
# Structure check only. Do not run `docker compose config` without `--quiet`:
# Compose interpolation can print the bootstrap secret into terminal or CI logs.
docker compose config --quiet
```
