# Expert Content Studio API

Base URL: `/api`. The Vite development server proxies this path to `http://127.0.0.1:8000`; the production Docker frontend reverse-proxies it to its companion backend.

Documented endpoint-domain and request-validation failures use the following safe envelope:

```json
{"detail":{"code":"source_unavailable","message":"The source is temporarily unavailable or could not be read."}}
```

Unknown routes and unsupported HTTP methods use FastAPI's standard HTTP error
response, whose `detail` is a string rather than this domain envelope.

AI, X, and GitHub credentials are server-side environment settings only. No endpoint accepts or returns those provider credentials.

## Public health

### `GET /health`

This endpoint is public and does not require an administrator session. It returns `{ "status": "ok", "database": "uninitialized", "aiConfigured": false }`. `aiConfigured` reports readiness only; it never reveals a key.

## Authentication

Authentication is enabled by default. When it is enabled, other than public
health and the login endpoint, routes require the opaque
`expert_content_studio_session` cookie. The cookie is `HttpOnly`,
`SameSite=Strict`, scoped to `/`, and uses the configured `Secure` attribute.
JavaScript cannot read the cookie value.

Successful login, current-session, and password-change responses all return the
same browser-safe shape. They never return a password or opaque session token:

```json
{
  "user": {"id": 1, "username": "admin"},
  "csrfToken": "<CSRF token>"
}
```

### `POST /auth/login`

Creates a new administrator session. Request body:

```json
{"username":"admin","password":"<administrator secret>"}
```

On `200`, sets the `HttpOnly` session cookie and returns the safe session shape.
Incorrect username or password returns `401 invalid_credentials`.

### `GET /auth/me`

Returns the safe current-session shape and a current `csrfToken`. A missing,
expired, revoked, or otherwise invalid session returns `401 authentication_required`.

### `POST /auth/logout`

Requires the current session and a valid CSRF header. It revokes that server-side
session, clears the browser cookie, and returns `204 No Content`.

### `POST /auth/change-password`

Requires the current session and a valid CSRF header. Request body:

```json
{
  "currentPassword": "<current administrator secret>",
  "newPassword": "<new administrator secret, at least 12 characters>"
}
```

On `200`, invalidates prior sessions, sets a replacement session cookie, and
returns the safe session shape. An incorrect current password returns
`401 invalid_credentials`; an absent or invalid session returns
`401 authentication_required`. `newPassword` has a minimum length of 12
characters.

### CSRF for state-changing routes

After obtaining `csrfToken` from a successful authentication response, send it
as `X-CSRF-Token` on every state-changing authenticated request, including
logout, password change, imports, derivations, source chat, artifact edits, and
settings changes. A missing or mismatched token returns `403 csrf_invalid`.
`POST /auth/login` establishes a session and does not require a pre-existing
CSRF token.

## Authenticated library routes

### `GET /settings`

Returns browser-safe presentation settings, `aiConfigured`, and `{ "research": { "autoStart": false } }`.

### `PATCH /settings`

Updates the supplied typed, non-secret presentation and automatic-research preferences; omitted groups retain their persisted value. Existing presentation-only requests remain valid:

```json
{"presentation":{"theme":"dark","preview_device":"mobile"}}
```

To enable automatic enqueueing after a successful supported import, send `{"research":{"autoStart":true}}`. The worker starts on the next application lifespan; it is disabled by default. Allowed themes are `system`, `light`, `dark`; allowed preview devices are `desktop`, `mobile`. Extra fields are rejected with `422 invalid_request`.

## Import and library

### `POST /imports`

Imports a public HTTPS URL and returns a canonical `Source`.

```json
{"url":"https://github.com/owner/repository"}
```

The canonical URL is idempotent: repeated requests return the existing source. A source has `import_status` `ready`, `partial`, or `blocked`; blocked imports return an error instead of storing material. A partial source is stored with its `failure_reason` and may contain only metadata.

### `GET /sources`

Lists sources. Query parameters:

- `q`: title or canonical URL text search (maximum 512 characters)
- `platform`: exact platform filter
- `tag`: an accepted governed tag filter; selecting a taxonomy parent includes accepted descendants
- `page`: one-based page, default `1`
- `page_size`: default `20`, maximum `100`

Response shape: `{ "items": [Source], "total": 1, "page": 1, "page_size": 20 }`.

### `GET /sources/{source_id}`

Returns `{ "source": Source, "artifacts": [Artifact], "research_runs": [ResearchRun], "tag_assignments": [TagAssignment] }`, including the immutable imported material and append-only artifact history.

## Deep research and taxonomy

### `POST /sources/{source_id}/research`

Queues a manual deep-research run for a GitHub repository, arXiv paper, or Hugging Face model/dataset. Returns `202` with the persisted `ResearchRun`; when a run is already queued/running for that source, returns the same run. The request never invokes external collection or the AI provider inline.

### `GET /research-runs/{run_id}`

Returns durable run state, phase, bounded budget/coverage snapshots, retry counts, safe failure code and provider/model metadata. Worker leases are never returned.

### `GET /research-runs/{run_id}/evidence`

Returns paginated evidence in deterministic collection order: `{ "items": [ResearchEvidence], "total": 1, "page": 1, "page_size": 20 }`. Included evidence carries its stable locator and content/digest; excluded evidence carries its reason.

### `GET /tags`

Returns the controlled hierarchical taxonomy. A fresh database is seeded with the standard object, method and capability nodes without deleting custom labels.

### `POST /sources/{source_id}/tags`

Creates a custom user label and attaches it as an accepted assignment:

```json
{"label":"内部评审"}
```

### `PATCH /tag-assignments/{assignment_id}` and `DELETE /tag-assignments/{assignment_id}`

Confirms or rejects an AI suggestion with `{"status":"accepted"}` or `{"status":"rejected"}`, or removes an assignment. Deletion removes assignment/evidence join rows only; the shared tag definition remains available.

## Derived knowledge and chat

### `POST /sources/{source_id}/derive`

Creates a new immutable `Artifact` from imported material. Request:

```json
{"kind":"translation"}
```

`kind` must be `translation`, `summary`, or `skill`. The configured OpenAI-compatible provider is called by the backend only. The response is an `Artifact` with provider/model metadata but no secret. A source with no actual material returns `422 source_unavailable`.

### `POST /sources/{source_id}/chat`

Creates a source-scoped chat turn. Request:

```json
{"question":"这篇内容的关键限制是什么？"}
```

The response has `answer_markdown` and `citations_json`; citations reference only the source and artifact sections supplied to the provider.

## Artifact versions and export

### `PATCH /artifacts/{artifact_id}`

Creates a new `user_edit` version; it never updates raw source content or overwrites the parent artifact.

```json
{"title":"我的 Skill","markdown":"# 我的 Skill","language":"zh"}
```

`markdown` is required and capped at 100,000 characters. `title` and `language` are optional.

### `GET /artifacts/{artifact_id}/download`

Streams the stored Markdown as a `text/markdown` attachment with a safe `.md` filename.

## Error codes

| HTTP | Code | Meaning |
| --- | --- | --- |
| 401 | `authentication_required` | A protected route has no valid current session. |
| 401 | `invalid_credentials` | Login credentials or the current password are incorrect. |
| 403 | `csrf_invalid` | A state-changing authenticated request has no valid `X-CSRF-Token`. |
| 404 | `source_not_found`, `artifact_not_found`, `research_run_not_found`, `tag_assignment_not_found` | The requested stored entity does not exist. |
| 422 | `invalid_request` | Payload or query validation failed. |
| 422 | `unsupported_url` | URL is not public HTTPS or is an unsupported platform form. |
| 422 | `restricted_source` | The provider reports a private/restricted source. |
| 422 | `source_unavailable` | Source material is unavailable, incomplete for the operation, rate-limited, or could not be safely parsed. |
| 422 | `provider_not_configured` | AI derivation/chat lacks a complete server provider configuration. |
| 502 | `provider_error` | Configured AI provider could not complete a request safely. |

The internal connector reason is intentionally not reflected verbatim to clients. See the [README](../README.md) for supported-source constraints.
