# 🔐 Sentinel

**Production-ready authentication gateway, RBAC service, and API reverse proxy built with FastAPI.**

Sentinel is a standalone microservice that centralizes authentication, authorization, and rate limiting — so your downstream services don't have to. Deploy it in front of any number of backend APIs, and they receive authenticated requests with user context injected via headers.

---

## Features

- **JWT Authentication** — Short-lived access tokens (15m) + rotating refresh tokens (7d) with Redis blacklisting
- **OAuth2 Social Login** — Google, GitHub, and Discord — auto-creates users, links existing accounts by email
- **Role-Based Access Control** — Many-to-many User ↔ Role ↔ Permission model with composable `require_permissions()` FastAPI dependency
- **Rate Limiting** — Redis-backed sliding window algorithm with per-route, per-user configurable limits and brute-force protection on auth endpoints
- **API Gateway / Reverse Proxy** — YAML-configured route definitions with middleware chain: Rate Limit → Auth → RBAC → Proxy. Injects user context headers into upstream requests
- **Production Polish** — Structured JSON logging (structlog), health/readiness endpoints, Alembic migrations, Docker Compose, GitHub Actions CI

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | [FastAPI](https://fastapi.tiangolo.com/) (async) |
| Database | PostgreSQL 17 + [SQLAlchemy 2.0](https://www.sqlalchemy.org/) (async) |
| Migrations | [Alembic](https://alembic.sqlalchemy.org/) |
| Cache | [Redis 7](https://redis.io/) |
| Auth | [python-jose](https://github.com/mpdavis/python-jose) (JWT), [Passlib](https://passlib.readthedocs.io/) (bcrypt), [Authlib](https://authlib.org/) (OAuth2) |
| Proxy | [httpx](https://www.python-httpx.org/) (async) |
| Config | [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) |
| Logging | [structlog](https://www.structlog.org/) |
| Package Manager | [uv](https://docs.astral.sh/uv/) |
| Containerization | Docker + Docker Compose |
| CI | GitHub Actions |

---

## Quick Start

```bash
# Clone
git clone https://github.com/zxaylex/sentinel.git
cd sentinel

# Install dependencies
uv sync

# Start Postgres + Redis
docker compose up -d

# Copy env and configure
cp .env.example .env

# Run migrations
uv run alembic revision --autogenerate -m "initial"
uv run alembic upgrade head

# Seed default roles and permissions
uv run python -m app.seeds.run

# Start the server
make dev
```

Open **http://localhost:8000/docs** for the interactive Swagger UI.

---

## API Reference

### Auth

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/auth/register` | Create account (email + password) |
| `POST` | `/api/v1/auth/login` | Returns access + refresh tokens |
| `POST` | `/api/v1/auth/refresh` | Rotate refresh token |
| `POST` | `/api/v1/auth/logout` | Revoke refresh token + blacklist access token |

### OAuth2

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/oauth/{provider}/login` | Redirect to Google / GitHub / Discord |
| `GET` | `/api/v1/oauth/{provider}/callback` | Handle callback, issue tokens |

### Users

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/users/me` | JWT | Current user profile |
| `GET` | `/api/v1/users/` | `users:read` | List all users |
| `GET` | `/api/v1/users/{id}` | `users:read` | Get user by ID |
| `PATCH` | `/api/v1/users/{id}` | `users:write` | Update user |
| `PUT` | `/api/v1/users/{id}/roles` | `roles:manage` | Assign roles to user |

### RBAC

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/roles/` | `roles:read` | List all roles |
| `POST` | `/api/v1/roles/` | `roles:manage` | Create custom role |
| `PUT` | `/api/v1/roles/{id}` | `roles:manage` | Update role |
| `DELETE` | `/api/v1/roles/{id}` | `roles:manage` | Delete role (not built-ins) |
| `GET` | `/api/v1/roles/permissions` | `roles:read` | List all permissions |
| `GET` | `/api/v1/roles/me/permissions` | JWT | Current user's effective permissions |

### Health

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Liveness — is the process alive? |
| `GET` | `/health/ready` | Readiness — DB + Redis connectivity |

---

## Project Structure

```
sentinel/
├── app/
│   ├── main.py                 # FastAPI app + lifespan (Redis, CORS, logging)
│   ├── config.py               # Pydantic Settings (22 env vars)
│   ├── database.py             # Async SQLAlchemy engine + session
│   ├── api/
│   │   ├── router.py           # Route aggregation
│   │   └── v1/
│   │       ├── auth.py         # Register, login, refresh, logout
│   │       ├── oauth.py        # Google / GitHub / Discord OAuth2
│   │       ├── users.py        # User CRUD + role assignment
│   │       └── roles.py        # Role & permission management
│   ├── core/
│   │   ├── security.py         # JWT creation/validation, bcrypt, token hashing
│   │   ├── rbac.py             # require_permissions() dependency
│   │   ├── rate_limiter.py     # Redis sliding window algorithm
│   │   ├── proxy.py            # httpx reverse proxy
│   │   ├── gateway.py          # YAML route config loader + matcher
│   │   └── exceptions.py       # Custom HTTP exceptions
│   ├── middleware/
│   │   ├── auth_middleware.py   # Bearer token extraction + validation
│   │   ├── rate_limit_mw.py    # Rate limit enforcement
│   │   └── logging_mw.py       # Structured request logging
│   ├── models/                 # SQLAlchemy models (User, Role, Permission, RefreshToken)
│   ├── schemas/                # Pydantic request/response models
│   ├── seeds/                  # Default roles + permissions seeder
│   └── utils/                  # Health checks, logging config
├── alembic/                    # Database migrations
├── tests/                      # pytest + httpx AsyncClient
├── gateway.yml                 # Proxy route definitions
├── docker-compose.yml          # Postgres 17 + Redis 7
├── Dockerfile                  # uv-based production image
├── Makefile                    # Dev shortcuts
└── .github/workflows/ci.yml   # Lint → Test → Build pipeline
```

---

## Gateway Configuration

Define upstream routes in `gateway.yml`:

```yaml
routes:
  - path: "/api/orders/**"
    upstream: "http://orders-service:8000"
    require_auth: true
    permissions:
      - "orders:read"
    rate_limit: 50

  - path: "/api/public/**"
    upstream: "http://public-service:8000"
    require_auth: false
    rate_limit: 200
```

Sentinel's middleware chain processes each proxied request:

**Rate Limit → Auth → RBAC → Proxy**

Authenticated requests arrive at your upstream service with these headers injected:

```
X-User-Id: 550e8400-e29b-41d4-a716-446655440000
X-User-Email: user@example.com
X-User-Roles: admin,user
```

---

## Default Roles & Permissions

| Role | Permissions |
|---|---|
| `superadmin` | All permissions |
| `admin` | `users:read`, `users:write`, `roles:read`, `roles:manage`, `orders:*`, `products:*` |
| `moderator` | `users:read`, `orders:read`, `products:read` |
| `user` | `orders:read`, `products:read` |

New users are automatically assigned the `user` role on registration.

---

## Environment Variables

See [`.env.example`](.env.example) for all variables. The essentials:

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | ✅ | PostgreSQL async connection string |
| `REDIS_URL` | ✅ | Redis connection string |
| `JWT_SECRET_KEY` | ✅ | Secret for signing JWTs (use a 64+ char random string) |
| `GOOGLE_CLIENT_ID` | | OAuth2 — enable by setting ID + secret |
| `GITHUB_CLIENT_ID` | | OAuth2 — enable by setting ID + secret |
| `DISCORD_CLIENT_ID` | | OAuth2 — enable by setting ID + secret |

---

## Development

```bash
make dev            # Start with hot-reload
make test           # Run test suite
make lint           # Ruff + mypy
make format         # Auto-format with Ruff
make migrate        # Apply pending migrations
make migration msg="add X"  # Generate new migration
make seed           # Seed roles + permissions
make up / make down # Toggle Docker services
```

---

## License

MIT
