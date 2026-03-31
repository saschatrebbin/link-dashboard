"""Link Dashboard Backend API."""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Any, Optional
import uvicorn

from models import (
    init_db,
    create_link,
    get_link,
    get_all_links,
    update_link,
    delete_link,
    create_dashboard,
    get_dashboard,
    get_all_dashboards,
    update_dashboard,
    delete_dashboard,
    reorder_dashboards,
    add_link_to_dashboard,
    remove_link_from_dashboard,
    save_check_result,
    get_latest_check_result,
    cleanup_old_check_results,
    add_change_log,
    get_change_logs,
    dismiss_change_log,
)
from checks import perform_check, detect_changes, get_status_indicator

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_INDEX_PATH = Path(
    os.getenv("LINKBOARD_FRONTEND_INDEX", str(BASE_DIR / "frontend" / "index.html"))
)

# Initialize database
init_db()

# Create FastAPI app
app = FastAPI(
    title="Link Dashboard API",
    description="Backend API for Link Dashboard with monitoring capabilities",
    version="0.1.0",
)

# CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", include_in_schema=False)
def root_frontend():
    """Serve the single-page frontend."""
    return FileResponse(FRONTEND_INDEX_PATH)


@app.get("/frontend", include_in_schema=False)
@app.get("/frontend/", include_in_schema=False)
def frontend_alias():
    """Serve the frontend from the legacy path too."""
    return FileResponse(FRONTEND_INDEX_PATH)


# ============================================================================
# Pydantic Models
# ============================================================================


class LinkCreate(BaseModel):
    url: str
    port: int = 443
    custom_icon: Optional[str] = None
    title: Optional[str] = None


class LinkUpdate(BaseModel):
    url: Optional[str] = None
    port: Optional[int] = None
    custom_icon: Optional[str] = None
    favicon_url: Optional[str] = None
    title: Optional[str] = None


class DashboardCreate(BaseModel):
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None


class DashboardUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None


class DashboardLinkAdd(BaseModel):
    link_id: str
    position: Optional[int] = None


class DashboardReorder(BaseModel):
    dashboard_ids: list[str]


class CheckResponse(BaseModel):
    link_id: str
    status: str  # 'ok', 'warn', 'error'
    check_result: dict


class ChangeLogResponse(BaseModel):
    id: int
    link_id: str
    change_type: str
    old_value: Optional[Any]
    new_value: Optional[Any]
    detected_at: str
    dismissed: bool


# ============================================================================
# Links API
# ============================================================================


@app.post("/api/links", response_model=dict)
def create_link_endpoint(link: LinkCreate):
    """Create a new link in the registry."""
    try:
        return create_link(link.url, link.port, link.custom_icon, link.title)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/links", response_model=list[dict])
def get_links_endpoint():
    """Get all links."""
    return get_all_links()


@app.get("/api/links/{link_id}", response_model=dict)
def get_link_endpoint(link_id: str):
    """Get a single link by ID."""
    link = get_link(link_id)
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    return link


@app.patch("/api/links/{link_id}", response_model=dict)
def update_link_endpoint(link_id: str, link: LinkUpdate):
    """Update a link."""
    existing = get_link(link_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Link not found")

    updates = link.model_dump(exclude_unset=True)
    return update_link(link_id, **updates)


@app.delete("/api/links/{link_id}")
def delete_link_endpoint(link_id: str):
    """Delete a link."""
    if not delete_link(link_id):
        raise HTTPException(status_code=404, detail="Link not found")
    return {"message": "Link deleted"}


# ============================================================================
# Dashboards API
# ============================================================================


@app.post("/api/dashboards", response_model=dict)
def create_dashboard_endpoint(dashboard: DashboardCreate):
    """Create a new dashboard."""
    return create_dashboard(dashboard.name, dashboard.description, dashboard.icon)


@app.get("/api/dashboards", response_model=list[dict])
def get_dashboards_endpoint():
    """Get all dashboards."""
    return get_all_dashboards()


@app.get("/api/dashboards/{dashboard_id}", response_model=dict)
def get_dashboard_endpoint(dashboard_id: str):
    """Get a dashboard with its links and status."""
    dashboard = get_dashboard(dashboard_id)
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    # Enrich links with status
    for link in dashboard.get("links", []):
        check_result = get_latest_check_result(link["id"])
        if check_result:
            link["status"] = get_status_indicator(check_result)
            link["last_check"] = check_result.get("checked_at")
        else:
            link["status"] = "unknown"
            link["last_check"] = None

    return dashboard


@app.patch("/api/dashboards/{dashboard_id}", response_model=dict)
def update_dashboard_endpoint(dashboard_id: str, dashboard: DashboardUpdate):
    """Update a dashboard."""
    existing = get_dashboard(dashboard_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    updates = dashboard.model_dump(exclude_unset=True)
    return update_dashboard(dashboard_id, **updates)


@app.delete("/api/dashboards/{dashboard_id}")
def delete_dashboard_endpoint(dashboard_id: str):
    """Delete a dashboard."""
    if not delete_dashboard(dashboard_id):
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return {"message": "Dashboard deleted"}


@app.post("/api/dashboards/reorder", response_model=list[dict])
def reorder_dashboards_endpoint(payload: DashboardReorder):
    """Persist dashboard order."""
    existing_ids = {dashboard["id"] for dashboard in get_all_dashboards()}
    if set(payload.dashboard_ids) != existing_ids:
        raise HTTPException(
            status_code=400,
            detail="Dashboard list must include all dashboards exactly once",
        )
    return reorder_dashboards(payload.dashboard_ids)


@app.post("/api/dashboards/{dashboard_id}/links")
def add_link_to_dashboard_endpoint(dashboard_id: str, link_data: DashboardLinkAdd):
    """Add a link to a dashboard."""
    if not get_dashboard(dashboard_id):
        raise HTTPException(status_code=404, detail="Dashboard not found")
    if not get_link(link_data.link_id):
        raise HTTPException(status_code=404, detail="Link not found")

    if not add_link_to_dashboard(dashboard_id, link_data.link_id, link_data.position):
        raise HTTPException(status_code=400, detail="Link already on dashboard")

    return {"message": "Link added to dashboard"}


@app.delete("/api/dashboards/{dashboard_id}/links/{link_id}")
def remove_link_from_dashboard_endpoint(dashboard_id: str, link_id: str):
    """Remove a link from a dashboard."""
    if not remove_link_from_dashboard(dashboard_id, link_id):
        raise HTTPException(status_code=404, detail="Link not on dashboard")
    return {"message": "Link removed from dashboard"}


# ============================================================================
# Monitoring API
# ============================================================================


def run_check_for_link(link_id: str):
    """Background task to run check and detect changes."""
    link = get_link(link_id)
    if not link:
        return

    # Get previous check result for change detection
    previous = get_latest_check_result(link_id)

    # Perform new check
    result = perform_check(link["url"], link["port"])

    # Save result
    save_check_result(link_id, result)

    # Detect and log changes
    changes = detect_changes(previous, result)
    for change in changes:
        add_change_log(link_id, change["type"], change.get("old"), change.get("new"))


@app.post("/api/links/{link_id}/check", response_model=CheckResponse)
def check_link_endpoint(link_id: str):
    """Run a monitoring check for a link and return the fresh result."""
    link = get_link(link_id)
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    run_check_for_link(link_id)
    check_result = get_latest_check_result(link_id)
    status = get_status_indicator(check_result) if check_result else "unknown"

    return {"link_id": link_id, "status": status, "check_result": check_result or {}}


@app.get("/api/links/{link_id}/check", response_model=CheckResponse)
def get_latest_check_endpoint(link_id: str):
    """Get the latest check result for a link."""
    link = get_link(link_id)
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    check_result = get_latest_check_result(link_id)
    if not check_result:
        raise HTTPException(status_code=404, detail="No check results yet")

    status = get_status_indicator(check_result)

    return {"link_id": link_id, "status": status, "check_result": check_result}


@app.post("/api/check-all")
def check_all_links_endpoint(background_tasks: BackgroundTasks):
    """Run checks for all links."""
    links = get_all_links()
    for link in links:
        background_tasks.add_task(run_check_for_link, link["id"])
    return {"message": f"Scheduled checks for {len(links)} links"}


# ============================================================================
# Change Logs API
# ============================================================================


@app.get("/api/links/{link_id}/changes", response_model=list[ChangeLogResponse])
def get_link_changes_endpoint(link_id: str, include_dismissed: bool = False):
    """Get change logs for a link."""
    link = get_link(link_id)
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    return get_change_logs(link_id, include_dismissed)


@app.get("/api/changes", response_model=list[ChangeLogResponse])
def get_all_changes_endpoint(include_dismissed: bool = False):
    """Get all change logs."""
    return get_change_logs(include_dismissed=include_dismissed)


@app.post("/api/changes/{change_id}/dismiss")
def dismiss_change_endpoint(change_id: int):
    """Dismiss a change log entry."""
    if not dismiss_change_log(change_id):
        raise HTTPException(status_code=404, detail="Change log not found")
    return {"message": "Change log dismissed"}


# ============================================================================
# System API
# ============================================================================


@app.post("/api/cleanup")
def cleanup_old_results_endpoint(max_age_minutes: int = 30):
    """Clean up old check results."""
    deleted = cleanup_old_check_results(max_age_minutes)
    return {"message": f"Cleaned up {deleted} old check results"}


@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


# ============================================================================
# Main
# ============================================================================


def run_server(host: Optional[str] = None, port: Optional[int] = None):
    """Run the API server."""
    host = host or os.getenv("LINKBOARD_HOST", "0.0.0.0")
    port = port or int(os.getenv("LINKBOARD_PORT", "8080"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
