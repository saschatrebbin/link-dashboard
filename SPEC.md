# Link Dashboard — Projektspezifikation

## Überblick

Ein schlankes, selbstgehostetes Dashboard zur Verwaltung von Web-Links mit integriertem Monitoring. Ziel ist es, eine Alternative zu vollwertigen Monitoring-Lösungen zu bieten, die sich auf die wesentlichen Fragen konzentriert: Ist das Ziel erreichbar, antwortet es korrekt, und gab es Änderungen?

## Kernkonzepte

### 1. Link Registry (Zentrale Verwaltung)
- Jedes Link-Ziel wird **einmalig** erfasst
- Pflichtfelder: URL, Port (optional, Default: 80/443)
- Automatisch extrahiert: Favicon, Website-Titel
- Optional: Eigenes Icon

### 2. Dashboard (Kontextuelle Ansicht)
- Mehrere Dashboards möglich
- Jedes Dashboard zeigt eine ausgewählte Teilmenge der Registry
- Grid-Layout mit Icon, URL und Status-Farbe (rot/gelb/grün)

### 3. Monitoring-Checks (pro Link)
| Check | Beschreibung |
|-------|--------------|
| DNS-Auflösung | IP-Adressen ermitteln |
| Host-Erreichbarkeit | Ping/TCP-Verbindung |
| HTTP-Status | 200er = ok, 400er = Problem, 500er = Fehler |
| SSL-Zertifikat | Aussteller, SANs, Gültigkeit, Ketten完整性 |

### 4. Change Log (Änderungserkennung)
- DNS-Änderungen: Alte vs. neue IPs, Zeitstempel
- Zertifikatsänderungen: Altes vs. neues Zertifikat
- Persistiert bis vom Nutzer gelöscht
- Getrenntes Logbuch pro Link

## Architektur

### Backend
- **Python** (FastAPI oder Flask)
- **SQLite** oder **DuckDB** für Persistenz
- Background-Tasks für periodische Checks

### Frontend
- **JavaScript** (Vanilla oder leichtes Framework)
- Single-Page-Application
- Client-seitiges Rendering

### Checks
- Python-Bibliotheken für:
  - DNS-Lookup (`dns.resolver`)
  - HTTP-Requests (`httpx`)
  - SSL-Zertifikate (`ssl`, `cryptography`)

## Datenmodell

### Link
```
- id: UUID
- url: String (Pflicht)
- port: Integer (optional, Default 443)
- custom_icon: String (optional)
- created_at: Timestamp
```

### Dashboard
```
- id: UUID
- name: String
- created_at: Timestamp
```

### DashboardLink (Relation)
```
- dashboard_id: FK
- link_id: FK
- position: Integer
```

### CheckResult
```
- link_id: FK
- timestamp: Timestamp
- dns_ips: JSON
- http_status: Integer
- ssl_info: JSON
```

### ChangeLog
```
- id: UUID
- link_id: FK
- type: Enum (DNS, SSL)
- old_value: JSON
- new_value: JSON
- timestamp: Timestamp
- dismissed: Boolean
```

## Benutzeroberfläche

### Grid-Ansicht (Dashboard)
- Karten mit: Icon, URL, Status-Indikator
- Status-Farben:
  - 🟢 Grün: Alles ok (200er + gültiges Zertifikat)
  - 🟡 Gelb: Warnung (z.B. Zertifikat läuft bald ab)
  - 🔴 Rot: Fehler (nicht erreichbar, 400/500er)

### Link-Interaktionen
- **Linksklick**: Öffnet Ziel-URL in neuem Tab
- **Lupen-Symbol**: Öffnet Detail-Panel mit Monitoring-Infos und Change Log

### Verwaltungsoberfläche
- Link Registry: Hinzufügen, Bearbeiten, Löschen
- Dashboards: Erstellen, Konfigurieren, Links zuweisen
- Change Logs: Einsehen, Archivieren

## Technische Anforderungen

### Laufzeitumgebung
- Python 3.x via `uv` (Tool-Umgebung)
- Node.js/NPM für Frontend-Build
- SQLite oder DuckDB als Datenbank

### Keine Root-Rechte
- Docker **nicht** nutzen
- Lokale Installation bevorzugen

## Projektstruktur
```
link-dashboard/
├── SPEC.md
├── backend/
│   ├── main.py
│   ├── models.py
│   ├── checks.py
│   └── database.py
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── styles.css
└── data/
    └── linkdashboard.db
```
