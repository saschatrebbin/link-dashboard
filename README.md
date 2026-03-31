# Link Dashboard

An opinionated personal link dashboard with lightweight monitoring.

This project is my own mixture of homepage, link collection, context-based dashboard, and minimal service monitoring. It is built for a single user, runs behind a reverse proxy, and is optimized for my own workflow first.

## What It Does

- Stores links in a central registry
- Organizes links into multiple contexts
- Opens links directly in a new tab
- Runs DNS, HTTP, and SSL checks
- Records DNS and certificate changes
- Shows health state in a compact dashboard UI
- Supports multiple built-in UI themes

## Intended Use

This repository is maintained for private use.

- It is not designed as a multi-user platform
- It is not designed as a generic SaaS product
- Compatibility decisions are driven by my needs, not by external consumers

## Run With Docker Compose

Prerequisites:

- Docker
- Docker Compose

Start:

```bash
./scripts/manage.sh up
```

Build only:

```bash
./scripts/manage.sh build
```

Stop:

```bash
./scripts/manage.sh down
```

Logs:

```bash
./scripts/manage.sh logs
```

Health check:

```bash
./scripts/manage.sh health
```

Syntax check:

```bash
./scripts/manage.sh check
```

The container uses a bind mount for persistent data:

```text
./data -> /data
```

The SQLite database lives at:

```text
/data/linkdashboard.db
```

## Configuration

Supported environment variables:

- `LINKBOARD_HOST` default `0.0.0.0`
- `LINKBOARD_PORT` default `8080`
- `LINKBOARD_DB_PATH` default `/data/linkdashboard.db`
- `LINKBOARD_FRONTEND_INDEX` default `/app/frontend/index.html`

The included `docker-compose.yml` already sets the relevant defaults for container usage.

## Reverse Proxy

The application now serves both frontend and backend from the same process.

- `/` serves the frontend
- `/api/*` serves the API

That means a reverse proxy only needs to forward to the application container on port `8080`.

## Repository Layout

```text
backend/              FastAPI backend, checks, SQLite access
frontend/             Single-file frontend
data/                 Persistent SQLite data
docs/                 Project documentation
scripts/manage.sh     Small maintenance wrapper
Dockerfile            Container image build
docker-compose.yml    Local container runtime
CHANGELOG.md          Keep a Changelog file
```

## Documentation

- Architecture: `docs/ARCHITECTURE.md`
- Changelog: `CHANGELOG.md`

## Commit Style

Use Conventional Commits for future history if you want clean changelog maintenance.

Examples:

- `feat: add context icon picker`
- `fix: handle change log arrays in API response`
- `docs: add container usage notes`
