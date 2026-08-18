# Expert Content Studio

将公开专家内容沉淀为可检索、可编辑、可导出的知识库。输入一条公开 HTTPS 链接，服务端会抓取并规范化内容；配置兼容 OpenAI 的 AI 服务后，可生成中文翻译、知识摘要和可复用 Skill Markdown。

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

- GitHub imports public repository metadata and README when available; private/restricted repositories are not imported.
- arXiv imports record metadata and abstract, not the paper PDF.
- Hugging Face imports public model/dataset metadata and cards where available.
- YouTube imports oEmbed metadata plus a public transcript only when it can be retrieved. Missing captions yield a `partial` source, not fabricated content.
- X uses X API v2 only when `X_BEARER_TOKEN` is configured. If text cannot be legally retrieved, the source is partial or blocked with an explicit reason.

Provider/API access can change independently of the application. A successful URL submission does not imply the source is accessible, and a partial source cannot be used to fabricate AI material.

Imports run synchronously within the HTTP request in this version. There is no
background job queue or automatic retry worker: slow or restricted sources return
their current status/error, and callers may retry intentionally.

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

cd ../frontend
npm run lint
npm run test -- --run
npm run build

cd ..
# Structure check only. Do not run `docker compose config` without `--quiet`:
# Compose interpolation can print the bootstrap secret into terminal or CI logs.
docker compose config --quiet
```
