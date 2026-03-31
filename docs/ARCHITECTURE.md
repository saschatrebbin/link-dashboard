# Architecture

## Overview

Link Dashboard is a single-user web application with three main responsibilities:

1. manage a personal registry of links
2. group those links into contexts
3. perform lightweight monitoring and record important changes

The application is intentionally simple.

- one FastAPI process
- one SQLite database
- one static frontend document
- one container in the deployment target

## Runtime Shape

### Application Process

The application runs as a single Python process using `uvicorn`.

That process serves:

- frontend on `/`
- API on `/api/*`

This avoids a separate frontend web server inside the container.

### Persistence

Persistent state is stored in SQLite.

Default location:

```text
/data/linkdashboard.db
```

The path is configurable with `LINKBOARD_DB_PATH`.

## Backend

### Stack

- FastAPI
- Uvicorn
- SQLite via `sqlite3`
- `httpx` for HTTP checks
- `cryptography` for SSL parsing

### Main Responsibilities

- CRUD for links
- CRUD for contexts dashboards
- context membership management
- monitoring checks per link
- change log persistence
- health endpoint for orchestration

### API Shape

Key routes:

- `GET /` frontend
- `GET /api/health`
- `GET /api/links`
- `POST /api/links`
- `PATCH /api/links/{id}`
- `GET /api/dashboards`
- `POST /api/dashboards`
- `PATCH /api/dashboards/{id}`
- `DELETE /api/dashboards/{id}`
- `POST /api/dashboards/reorder`
- `POST /api/links/{id}/check`

### Configuration

Environment variables:

- `LINKBOARD_HOST`
- `LINKBOARD_PORT`
- `LINKBOARD_DB_PATH`
- `LINKBOARD_FRONTEND_INDEX`

## Frontend

### Shape

The frontend is intentionally shipped as a single `index.html` file containing:

- semantic CSS with theme variables
- built-in themes
- vanilla JavaScript state and UI logic

### Frontend Responsibilities

- render contexts and link cards
- manage create and edit modals
- call the REST API
- persist active theme in browser local storage

### Theme Model

Built-in themes are part of the frontend source.

Browser local storage stores only:

- the currently selected theme
- optional custom themes if those are defined later

## Data Model

### links

Stores the canonical registry of URLs.

Important fields:

- `id`
- `url`
- `port`
- `title`
- `custom_icon`
- `favicon_url`

### dashboards

Represents contexts shown in the UI.

Important fields:

- `id`
- `name`
- `description`
- `icon`
- `position`

### dashboard_links

Many-to-many mapping between contexts and links.

### check_results

Stores latest and historical check outputs.

Fields include:

- DNS IPs
- response time
- HTTP status
- SSL metadata
- timestamps

### change_logs

Stores important changes detected between checks.

Current focus:

- DNS changes
- SSL changes

## Monitoring Flow

1. user triggers a check or UI loads links without recent state
2. backend resolves DNS and requests the target over HTTP
3. backend inspects SSL data when HTTPS is used
4. backend compares current values with previous values
5. backend writes fresh results and change logs
6. frontend refreshes visible state

The monitoring model is intentionally lightweight. It is not a replacement for a full observability stack.

## Container Strategy

The intended deployment target is a single container.

Reasons:

- simple deployment
- low operational overhead
- enough for a personal dashboard
- no scaling requirement between frontend and backend

The container exposes one internal port:

```text
8080
```

Expected reverse proxy routing:

- `/` -> app container `:8080`
- `/api/*` -> same container `:8080`

## Operational Notes

### Health Check

Container health is based on:

```text
GET /api/health
```

### Data Directory Validation

Startup performs a write test against the configured data directory so bad mounts fail early.

### Limitations

- single-user design
- no built-in authentication
- no distributed scheduling
- no background worker process
- no multi-node coordination

These are intentional tradeoffs for a private, low-maintenance deployment.
