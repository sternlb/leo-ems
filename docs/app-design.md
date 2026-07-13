# Android-App — Design & Branding

**Grundlage:** ADR-003 (native Android-App, Kotlin/Compose, LAN-only) und das **Basel-AI-Consulting-Branding** (Leo, 2026-07-12). Das Firmen-Branding gilt laut Leos Branding-Regeln für alle privaten Tools & Dashboards — die Leo-EMS-App folgt ihm.

## Marken-Tokens (Basel-AI Consulting)

| Rolle | Name | HEX |
|---|---|---|
| Primär | Waldgrün | `#14532D` |
| Dunkel | Deep Forest | `#0C1F15` |
| Akzent | Lime | `#A3E635` |
| Highlight | Frisches Gelb | `#FDE047` |
| Fläche hell | Off-White | `#FAFAF5` |
| Text | Fast-Schwarz | `#0A0F0C` |
| Gedimmt | Grau | `#6B7280` |

**Schriften:** Display = **Space Grotesk** (700), Body = **Inter**, Mono/Zahlen/Labels = **Space Mono**.

## Design-Prinzipien (aus dem Branding übernommen)

- **Flache Farben, keine Verläufe.** Großzügiger Weißraum.
- **Scharfe Kanten:** Radius max. `2px` (Cards, Buttons, Chips).
- **Lime nie als Textfarbe auf Weiß** — nur als Strich, Fläche oder auf Waldgrün/Deep Forest (z. B. CTAs auf dunklem Grund, Akzentlinien, aktive Ladeanzeige).
- **Gelb nur als Funke / Mikro-Akzent** (z. B. „Garantieladung aktiv"), nie großflächig.
- **Dunkel-Variante** nutzt Deep Forest als Grund, Off-White als Text, Lime als Akzent — passt gut zu einem Energie-Dashboard (dunkler Grund, elektrische Lime-Akzente, „Vitesco-Look").

## Anwendung im EMS-Dashboard

| Element | Branding-Umsetzung |
|---|---|
| App-Hintergrund | Deep Forest `#0C1F15` (Dashboard dunkel) |
| Cards (Verbraucher/Erzeuger) | Waldgrün-getönte Fläche, 2px Radius, Off-White-Text |
| Aktive Ladung / Fluss | Lime `#A3E635` (Balken, Linien, Icons) |
| Leistungszahlen | Space Mono, groß, Off-White |
| „Garantieladung aktiv" | Gelber Funke/Chip `#FDE047` |
| Statusgrund (Klartext) | Inter, gedimmt `#6B7280` bzw. Off-White-70% |
| Modus-Buttons / CTAs | Lime-Fläche mit Waldgrün-Text (Lime nie Text auf Weiß) |
| Warnung (z. B. Ziel-SoC nicht erreichbar) | Gelb/roter Akzent, sparsam |

## Screens (Spec §9.2)

1. **Dashboard** — Energiefluss (Erzeugung, Hausverbrauch, Wallbox, Batterie inkl. Sperr-Status), Prognose, Klartext-Begründung.
2. **Laderegeln** — Regelliste (Wochentage, Uhrzeit, Mindest-SoC): anlegen/ändern/deaktivieren/löschen.
3. **Einstellungen** — Lademodus, SoC-Reserve, residualPower/prioritySoc, harte Grenzen, Backend-Adresse + API-Token.
4. **Protokoll** — Entscheidungs-Log + Kennzahlen.

## Technische Umsetzung

- **Theme:** `app/.../ui/theme/` — `Color.kt` (Tokens oben), `Type.kt` (Space Grotesk / Inter / Space Mono), `Theme.kt` (Material3, Deep-Forest-Schema).
- **API-Client:** Retrofit gegen die lokale API v1 (`docs/api-token-auth.md`); Bearer-Token aus den App-Einstellungen. Live-Werte per WebSocket (`/api/v1/live`) oder Polling `/api/v1/status`.
- **Backend-Discovery:** mDNS (`homeassistant.local`), manuelle IP als Fallback.
- **Fonts:** als Bundled Font Resources (Google-Fonts-Dateien) in `app/.../res/font/`.

> Der Build erfordert Android Studio (Gradle/AGP, Android SDK) — im Repo liegt das Projektgerüst inkl. Theme und API-Vertrag; kompiliert und aufs Gerät gebracht wird in Android Studio.
