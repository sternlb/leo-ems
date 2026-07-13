# API-Token-Authentifizierung — Konzept und Begründung

**Entschieden:** 2026-07-12 (Leo folgt der Empfehlung). Dieses Dokument erklärt das Verfahren von Grund auf, damit es später nachvollziehbar ist.

## 1. Warum überhaupt Absicherung im eigenen LAN?

Die Leo-EMS-API nimmt **Steuerbefehle** entgegen: Lademodus ändern, Regeln löschen, Batterie-Reserve verstellen. „Im LAN" heißt nicht „nur vertrauenswürdige Geräte":

- Im Heimnetz hängen **dutzende Fremdgeräte** (siehe HA: Smart-TVs, Saugroboter, Miele, Sonos, Gäste-Handys, IoT-Steckdosen). Jedes kompromittierte IoT-Gerät könnte sonst die Wallbox steuern.
- Browser auf jedem Gerät im LAN könnten die API über präparierte Webseiten ansprechen (CSRF-artige Angriffe auf lokale Dienste sind ein reales Muster).
- Die EVCC-Erfahrung zeigt das Gegenmodell: EVCCs API ist im LAN offen — für ein reines Lade-Tool vertretbar, für ein System, das auch die **Hausbatterie** übersteuert, wollten wir die Hürde höher legen.

Kurz: Der Token schützt nicht gegen einen professionellen Angreifer *im* Netz (dafür bräuchte es TLS + mehr), sondern stellt sicher, dass **nur Geräte steuern können, denen du den Token explizit gegeben hast**.

## 2. Wie es funktioniert (Bearer-Token)

Das Muster heißt **statischer Bearer-Token** — dasselbe Prinzip wie bei den Long-Lived Access Tokens von Home Assistant.

```
Android-App                            Leo-EMS-Backend (Port 8099)
     │  GET /api/v1/status                       │
     │  Authorization: Bearer NZq3…xK8w  ───────►│  vergleicht mit /data/api_token
     │                                           │  gleich?  → 200 + Daten
     │◄──────────────────────────────────────────│  ungleich → 401 Unauthorized
```

1. **Erzeugung:** Beim allerersten Start generiert das Backend einen Zufallstoken — `secrets.token_urlsafe(32)` = 256 Bit Kryptografie-Zufall, praktisch unratbar — und speichert ihn in `/data/api_token` (überlebt Add-on-Updates, liegt im HA-Backup).
2. **Übertragung an die App:** Der Token wird beim Start **einmal ins Add-on-Log geschrieben**. Du kopierst ihn von dort in den Einstellungs-Screen der Android-App (einmalig pro Gerät). Später denkbar: QR-Code-Anzeige.
3. **Jede Anfrage** der App trägt den Header `Authorization: Bearer <token>`. Der WebSocket (`/api/v1/live`) authentifiziert sich beim Verbindungsaufbau genauso.
4. **Prüfung:** Das Backend vergleicht mit `hmac.compare_digest()` — einem **konstantzeitigen Vergleich**. Ein normaler String-Vergleich bricht beim ersten falschen Zeichen ab; aus den Antwortzeiten könnte man den Token Zeichen für Zeichen erraten (Timing-Angriff). `compare_digest` braucht immer gleich lang.
5. **Ausnahme:** `GET /api/v1/health` ist tokenfrei — der HA-Supervisor-Watchdog (addon/config.yaml) muss ohne Geheimnis prüfen können, ob der Dienst lebt. Der Endpunkt verrät nichts außer „läuft" + Version.

## 3. Was der Token bewusst NICHT leistet

| Bedrohung | Abgedeckt? | Einordnung |
|---|---|---|
| Fremdes IoT-Gerät ruft Steuer-API auf | ✅ | Hauptzweck |
| Mitlesen des Tokens durch Netzwerk-Sniffing | ❌ | HTTP ohne TLS — im geswitchten Heim-LAN schwierig, aber möglich. TLS im LAN bedeutet Zertifikats-Gefrickel auf jedem Gerät; bewusst verzichtet (LAN-only-System). |
| Physischer Zugriff aufs Handy mit installierter App | ❌ | Wie bei jeder App — Geräte-Sperre ist die Verteidigung. |
| Zugriff von außerhalb des LAN | ✅ (indirekt) | Kein Port-Forwarding, keine Cloud — die API ist von außen schlicht nicht erreichbar (REQ-074). |

## 4. Verworfene Alternativen

- **Keine Auth (wie EVCC):** verworfen — die API steuert auch die Hausbatterie, siehe §1.
- **HA-Ingress-Auth:** Zugriff liefe durch die HA-Oberfläche — kollidiert mit der nativen App (ADR-003), die direkt mit dem Backend spricht.
- **mTLS / Client-Zertifikate:** kryptografisch stärker, aber Zertifikats-Rollout und -Erneuerung auf jedem Familien-Handy ist unverhältnismäßig für ein Heimsystem.
- **OAuth2/Benutzerkonten:** Mehrbenutzer-Verwaltung mit Login-Flows — massiv überdimensioniert für einen Haushalt; ein gemeinsamer Token genügt.

## 5. Betrieb

- **Token einsehen:** Add-on-Log beim Start, oder per SSH: `cat /addon_configs/…/api_token` bzw. im Container `/data/api_token`.
- **Token rotieren** (z.B. Handy verloren): Datei `/data/api_token` löschen, Add-on neu starten → neuer Token wird erzeugt, alle Apps müssen ihn neu eintragen.
- **Fehlerbild:** App zeigt „401 Unauthorized" → Token in den App-Einstellungen prüfen (Tippfehler/Rotation).

## 6. Implementierung im Code

- Erzeugung/Persistierung: [`backend/leo_ems/config.py`](../backend/leo_ems/config.py) → `get_or_create_token()`
- Prüfung: [`backend/leo_ems/api/app.py`](../backend/leo_ems/api/app.py) → `require_token()` (FastAPI-Dependency, `hmac.compare_digest`)
- Watchdog-Ausnahme: `GET /api/v1/health` ebendort
