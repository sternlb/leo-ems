# Leo-EMS — Android-App

Native LAN-App (ADR-003) für das EMS-Dashboard. Design nach dem **Basel-AI-Consulting-Branding** (`../docs/app-design.md`).

## Status

Projektgerüst mit **Theme (Branding), API-Vertrag und Dashboard-Screen**. Der Build erfordert **Android Studio** (Gradle/AGP + Android SDK) — hier im Repo liegt der Quellcode, kompiliert/aufs Gerät gebracht wird in Android Studio.

## Struktur

```
app/
├── build.gradle.kts                  Modul-Build (Compose, Retrofit)
└── src/main/
    ├── AndroidManifest.xml           LAN-only, Cleartext-HTTP im Heimnetz
    └── java/de/baselai/leoems/
        ├── MainActivity.kt
        ├── data/EmsApi.kt            Retrofit-Vertrag gegen API v1
        └── ui/
            ├── DashboardScreen.kt    Dashboard (Spec §9.2)
            └── theme/                Basel-AI-Branding: Color, Type, Theme
```

## Nächste Schritte

- Status-Abruf verdrahten (`EmsApi.status` + WebSocket `/api/v1/live`).
- Einstellungs-Screen: Backend-Adresse (mDNS `homeassistant.local:8099` + manuelle IP) und API-Token.
- Screens Laderegeln, Einstellungen, Protokoll (Spec §9.2).
- Fontdateien (Space Grotesk / Inter / Space Mono) nach `res/font/` und in `Type.kt` binden.
- Projekt-Root-Gradle-Dateien (`settings.gradle.kts`, `gradle-wrapper`) beim ersten Öffnen in Android Studio generieren lassen.
