"""Integration tests for area storage and its HTTP API."""

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

# main initializes the database on import. Keep it outside the project data dir.
_import_dir = tempfile.TemporaryDirectory()
_previous_db_path = os.environ.get("LINKBOARD_DB_PATH")
os.environ["LINKBOARD_DB_PATH"] = str(Path(_import_dir.name) / "import.db")

from fastapi.testclient import TestClient
import main
import models

if _previous_db_path is None:
    os.environ.pop("LINKBOARD_DB_PATH", None)
else:
    os.environ["LINKBOARD_DB_PATH"] = _previous_db_path


class AreaApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        models.DB_PATH = Path(self.tmp.name) / "test.db"
        models.init_db()
        self.client = TestClient(main.app)

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def create_area(self, name):
        response = self.client.post("/api/areas", json={"name": name})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def create_link(self, url="https://admin.example.com"):
        response = self.client.post("/api/links", json={"url": url})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["id"]

    def create_dashboard(self, name="Microsoft 365"):
        response = self.client.post("/api/dashboards", json={"name": name})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["id"]

    def test_independent_many_to_many_memberships(self):
        private = self.create_area("Private")
        work = self.create_area("Work")
        link = self.create_link()
        context = self.create_dashboard()
        other_context = self.create_dashboard("Documentation")

        for area in (private, work):
            self.assertEqual(self.client.put(f"/api/areas/{area}/links/{link}").status_code, 200)
            self.assertEqual(self.client.put(f"/api/areas/{area}/dashboards/{context}").status_code, 200)
        # Repeated PUT does not create duplicate memberships.
        self.assertEqual(self.client.put(f"/api/areas/{private}/links/{link}").status_code, 200)
        self.client.put(f"/api/areas/{work}/dashboards/{other_context}")
        self.client.post(f"/api/dashboards/{context}/links", json={"link_id": link})
        self.client.post(f"/api/dashboards/{other_context}/links", json={"link_id": link})

        self.assertEqual({a["id"] for a in self.client.get(f"/api/links/{link}/areas").json()}, {private, work})
        self.assertEqual({a["id"] for a in self.client.get(f"/api/dashboards/{context}/areas").json()}, {private, work})
        self.assertEqual([l["id"] for l in self.client.get(f"/api/areas/{private}/links").json()], [link])
        self.assertEqual([d["id"] for d in self.client.get(f"/api/areas/{private}/dashboards").json()], [context])

        # The link's and context's area memberships need not match.
        self.assertEqual(self.client.delete(f"/api/areas/{private}/dashboards/{context}").status_code, 200)
        self.assertEqual([l["id"] for l in self.client.get(f"/api/areas/{private}/links").json()], [link])
        self.assertEqual(self.client.get(f"/api/areas/{private}/dashboards").json(), [])
        self.client.put(f"/api/areas/{private}/dashboards/{context}")

        # Removing a single membership must not remove either entity or other memberships.
        self.assertEqual(self.client.delete(f"/api/areas/{private}/links/{link}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/links/{link}").status_code, 200)
        self.assertEqual([a["id"] for a in self.client.get(f"/api/links/{link}/areas").json()], [work])
        self.assertEqual([l["id"] for l in self.client.get(f"/api/dashboards/{context}").json()["links"]], [link])
        self.assertEqual([d["id"] for d in self.client.get(f"/api/areas/{private}/dashboards").json()], [context])

        # Deleting an area removes its memberships, not shared links or contexts.
        self.assertEqual(self.client.delete(f"/api/areas/{work}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/links/{link}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/dashboards/{context}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/links/{link}/areas").json(), [])
        self.assertEqual([a["id"] for a in self.client.get(f"/api/dashboards/{context}/areas").json()], [private])

    def test_area_validation_and_missing_entities(self):
        for name in ("", "  ", None):
            self.assertEqual(self.client.post("/api/areas", json={"name": name}).status_code, 422)
        area = self.create_area("  Work  ")
        self.assertEqual(self.client.get(f"/api/areas/{area}").json()["name"], "Work")
        self.assertEqual(self.client.patch(f"/api/areas/{area}", json={"name": None}).status_code, 422)
        self.assertEqual(self.client.patch(f"/api/areas/{area}", json={"name": " "}).status_code, 422)
        self.assertEqual(self.client.patch(f"/api/areas/{area}", json={"description": "Notes"}).json()["description"], "Notes")
        self.assertIsNone(self.client.patch(f"/api/areas/{area}", json={"description": None}).json()["description"])
        self.assertEqual(self.client.get("/api/areas/missing/links").status_code, 404)
        self.assertEqual(self.client.get("/api/links/missing/areas").status_code, 404)
        self.assertEqual(self.client.get("/api/dashboards/missing/areas").status_code, 404)
        self.assertEqual(self.client.put(f"/api/areas/{area}/links/missing").status_code, 404)
        self.assertEqual(self.client.put(f"/api/areas/{area}/dashboards/missing").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/areas/{area}/links/missing").status_code, 404)
        self.assertEqual(self.client.delete("/api/areas/missing").status_code, 404)

    def test_deleting_members_cascades_only_their_assignments(self):
        area = self.create_area("Area")
        link = self.create_link()
        context = self.create_dashboard()
        self.client.put(f"/api/areas/{area}/links/{link}")
        self.client.put(f"/api/areas/{area}/dashboards/{context}")
        self.client.delete(f"/api/links/{link}")
        self.assertEqual(self.client.get(f"/api/areas/{area}/links").json(), [])
        self.assertEqual(len(self.client.get(f"/api/areas/{area}/dashboards").json()), 1)
        self.client.delete(f"/api/dashboards/{context}")
        self.assertEqual(self.client.get(f"/api/areas/{area}/dashboards").json(), [])
        self.assertEqual(self.client.get(f"/api/areas/{area}").status_code, 200)

    def test_existing_database_is_preserved_on_reinitialization(self):
        link = self.create_link()
        context = self.create_dashboard()
        self.client.post(f"/api/dashboards/{context}/links", json={"link_id": link})
        # Simulate a database from before the new area tables existed.
        with sqlite3.connect(models.DB_PATH) as conn:
            conn.executescript("DROP TABLE area_links; DROP TABLE area_dashboards; DROP TABLE areas;")
        models.init_db()
        models.init_db()
        self.assertEqual(self.client.get(f"/api/links/{link}").status_code, 200)
        self.assertEqual([l["id"] for l in self.client.get(f"/api/dashboards/{context}").json()["links"]], [link])
        self.assertEqual(self.client.get("/api/areas").json(), [])
        self.assertEqual(self.client.get(f"/api/links/{link}/areas").json(), [])


if __name__ == "__main__":
    unittest.main()
