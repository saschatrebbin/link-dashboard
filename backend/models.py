"""
Database models and schema for Link Dashboard.
Uses SQLite with direct SQL for simplicity.
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
import json

DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "linkdashboard.db"


def get_db() -> sqlite3.Connection:
    """Get database connection with row factory."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Initialize database with schema."""
    conn = get_db()
    cursor = conn.cursor()

    # Links table - central registry
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS links (
            id TEXT PRIMARY KEY,
            url TEXT NOT NULL UNIQUE,
            port INTEGER DEFAULT 443,
            custom_icon TEXT,
            favicon_url TEXT,
            title TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Dashboards table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dashboards (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Dashboard-Link relationship (many-to-many via position)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_links (
            dashboard_id TEXT NOT NULL,
            link_id TEXT NOT NULL,
            position INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (dashboard_id, link_id),
            FOREIGN KEY (dashboard_id) REFERENCES dashboards(id) ON DELETE CASCADE,
            FOREIGN KEY (link_id) REFERENCES links(id) ON DELETE CASCADE
        )
    """)

    # Check results - recent monitoring data (last 30 min)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS check_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            link_id TEXT NOT NULL,
            checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            dns_ips TEXT,  -- JSON array
            host_reachable INTEGER,  -- 0/1 boolean
            http_status INTEGER,
            http_response_time REAL,  -- milliseconds
            ssl_valid INTEGER,  -- 0/1 boolean
            ssl_issuer TEXT,
            ssl_sans TEXT,  -- JSON array
            ssl_not_before TEXT,
            ssl_not_after TEXT,
            ssl_chain_valid INTEGER,
            error_message TEXT,
            FOREIGN KEY (link_id) REFERENCES links(id) ON DELETE CASCADE
        )
    """)

    # Create index for efficient queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_check_results_link_time 
        ON check_results(link_id, checked_at DESC)
    """)

    # Change log - persistent record of changes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS change_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            link_id TEXT NOT NULL,
            change_type TEXT NOT NULL,  -- 'dns' or 'ssl'
            old_value TEXT,  -- JSON
            new_value TEXT,  -- JSON
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            dismissed INTEGER DEFAULT 0,
            FOREIGN KEY (link_id) REFERENCES links(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_change_logs_link 
        ON change_logs(link_id, detected_at DESC)
    """)

    conn.commit()
    conn.close()
    return DB_PATH


# ============================================================================
# Link CRUD Operations
# ============================================================================


def create_link(url: str, port: int = 443, custom_icon: str = None) -> dict:
    """Create a new link."""
    import uuid

    conn = get_db()
    link_id = str(uuid.uuid4())[:8]

    try:
        conn.execute(
            "INSERT INTO links (id, url, port, custom_icon) VALUES (?, ?, ?, ?)",
            (link_id, url, port, custom_icon),
        )
        conn.commit()
        result = get_link(link_id)
        conn.close()
        return result
    except sqlite3.IntegrityError:
        conn.close()
        raise ValueError(f"Link with URL '{url}' already exists")


def get_link(link_id: str) -> Optional[dict]:
    """Get a single link by ID."""
    conn = get_db()
    cursor = conn.execute("SELECT * FROM links WHERE id = ?", (link_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_links() -> list[dict]:
    """Get all links ordered by created_at."""
    conn = get_db()
    cursor = conn.execute("SELECT * FROM links ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_link(link_id: str, **kwargs) -> Optional[dict]:
    """Update link fields."""
    allowed = ["url", "port", "custom_icon", "favicon_url", "title"]
    updates = {k: v for k, v in kwargs.items() if k in allowed}

    if not updates:
        return get_link(link_id)

    updates["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
    values = list(updates.values()) + [link_id]

    conn = get_db()
    conn.execute(f"UPDATE links SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return get_link(link_id)


def delete_link(link_id: str) -> bool:
    """Delete a link and its related data."""
    conn = get_db()
    cursor = conn.execute("DELETE FROM links WHERE id = ?", (link_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


# ============================================================================
# Dashboard CRUD Operations
# ============================================================================


def create_dashboard(name: str, description: str = None) -> dict:
    """Create a new dashboard."""
    import uuid

    conn = get_db()
    dashboard_id = str(uuid.uuid4())[:8]

    conn.execute(
        "INSERT INTO dashboards (id, name, description) VALUES (?, ?, ?)",
        (dashboard_id, name, description),
    )
    conn.commit()
    result = get_dashboard(dashboard_id)
    conn.close()
    return result


def get_dashboard(dashboard_id: str) -> Optional[dict]:
    """Get a dashboard with its links."""
    conn = get_db()

    # Get dashboard
    cursor = conn.execute("SELECT * FROM dashboards WHERE id = ?", (dashboard_id,))
    dashboard = cursor.fetchone()

    if not dashboard:
        conn.close()
        return None

    dashboard = dict(dashboard)

    # Get links for this dashboard with latest check results
    cursor = conn.execute(
        """
        SELECT l.*, dl.position, cr.http_status, cr.ssl_valid, cr.checked_at
        FROM links l
        JOIN dashboard_links dl ON l.id = dl.link_id
        LEFT JOIN (
            SELECT link_id, http_status, ssl_valid, checked_at,
                   ROW_NUMBER() OVER (PARTITION BY link_id ORDER BY checked_at DESC) as rn
            FROM check_results
        ) cr ON l.id = cr.link_id AND cr.rn = 1
        WHERE dl.dashboard_id = ?
        ORDER BY dl.position
    """,
        (dashboard_id,),
    )

    dashboard["links"] = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return dashboard


def get_all_dashboards() -> list[dict]:
    """Get all dashboards with link count."""
    conn = get_db()
    cursor = conn.execute("""
        SELECT d.*, COUNT(dl.link_id) as link_count
        FROM dashboards d
        LEFT JOIN dashboard_links dl ON d.id = dl.dashboard_id
        GROUP BY d.id
        ORDER BY d.created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def add_link_to_dashboard(
    dashboard_id: str, link_id: str, position: int = None
) -> bool:
    """Add a link to a dashboard."""
    conn = get_db()

    if position is None:
        cursor = conn.execute(
            "SELECT MAX(position) FROM dashboard_links WHERE dashboard_id = ?",
            (dashboard_id,),
        )
        max_pos = cursor.fetchone()[0]
        position = (max_pos or 0) + 1

    try:
        conn.execute(
            "INSERT INTO dashboard_links (dashboard_id, link_id, position) VALUES (?, ?, ?)",
            (dashboard_id, link_id, position),
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False  # Link already on dashboard


def remove_link_from_dashboard(dashboard_id: str, link_id: str) -> bool:
    """Remove a link from a dashboard."""
    conn = get_db()
    cursor = conn.execute(
        "DELETE FROM dashboard_links WHERE dashboard_id = ? AND link_id = ?",
        (dashboard_id, link_id),
    )
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


# ============================================================================
# Check Results Operations
# ============================================================================


def save_check_result(link_id: str, result: dict) -> int:
    """Save a check result."""
    conn = get_db()
    cursor = conn.execute(
        """
        INSERT INTO check_results 
        (link_id, dns_ips, host_reachable, http_status, http_response_time,
         ssl_valid, ssl_issuer, ssl_sans, ssl_not_before, ssl_not_after, 
         ssl_chain_valid, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            link_id,
            json.dumps(result.get("dns_ips")),
            int(result.get("host_reachable", False)),
            result.get("http_status"),
            result.get("http_response_time"),
            int(result.get("ssl_valid", False)),
            result.get("ssl_issuer"),
            json.dumps(result.get("ssl_sans", [])),
            result.get("ssl_not_before"),
            result.get("ssl_not_after"),
            int(result.get("ssl_chain_valid", False)),
            result.get("error_message"),
        ),
    )
    conn.commit()
    check_id = cursor.lastrowid
    conn.close()
    return check_id


def get_latest_check_result(link_id: str) -> Optional[dict]:
    """Get the most recent check result for a link."""
    conn = get_db()
    cursor = conn.execute(
        "SELECT * FROM check_results WHERE link_id = ? ORDER BY checked_at DESC LIMIT 1",
        (link_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    result = dict(row)
    if result["dns_ips"]:
        result["dns_ips"] = json.loads(result["dns_ips"])
    if result["ssl_sans"]:
        result["ssl_sans"] = json.loads(result["ssl_sans"])
    return result


def cleanup_old_check_results(max_age_minutes: int = 30):
    """Remove check results older than max_age_minutes."""
    conn = get_db()
    conn.execute(
        """
        DELETE FROM check_results 
        WHERE checked_at < datetime('now', '-' || ? || ' minutes')
    """,
        (max_age_minutes,),
    )
    conn.commit()
    deleted = conn.total_changes
    conn.close()
    return deleted


# ============================================================================
# Change Log Operations
# ============================================================================


def add_change_log(
    link_id: str, change_type: str, old_value: dict, new_value: dict
) -> int:
    """Add a change log entry."""
    conn = get_db()
    cursor = conn.execute(
        """
        INSERT INTO change_logs (link_id, change_type, old_value, new_value)
        VALUES (?, ?, ?, ?)
    """,
        (link_id, change_type, json.dumps(old_value), json.dumps(new_value)),
    )
    conn.commit()
    log_id = cursor.lastrowid
    conn.close()
    return log_id


def get_change_logs(link_id: str = None, include_dismissed: bool = False) -> list[dict]:
    """Get change logs, optionally filtered by link."""
    conn = get_db()

    query = "SELECT * FROM change_logs"
    params = []

    conditions = []
    if link_id:
        conditions.append("link_id = ?")
        params.append(link_id)
    if not include_dismissed:
        conditions.append("dismissed = 0")

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY detected_at DESC"

    cursor = conn.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    logs = []
    for row in rows:
        log = dict(row)
        log["old_value"] = json.loads(log["old_value"]) if log["old_value"] else None
        log["new_value"] = json.loads(log["new_value"]) if log["new_value"] else None
        logs.append(log)

    return logs


def dismiss_change_log(log_id: int) -> bool:
    """Mark a change log entry as dismissed."""
    conn = get_db()
    conn.execute("UPDATE change_logs SET dismissed = 1 WHERE id = ?", (log_id,))
    conn.commit()
    updated = conn.total_changes > 0
    conn.close()
    return updated


if __name__ == "__main__":
    # Initialize database when run directly
    db_path = init_db()
    print(f"Database initialized at: {db_path}")
