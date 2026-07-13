"""Spike: RSCP-Schreibzugriff auf die echte E3DC verifizieren (Architektur, offener Punkt 3).

RISIKO-CHECK für die zentralste Annahme des EMS: Entladesperre setzen und
wieder lösen — inkl. Verhalten beim "Vergessen" (TTL-Prinzip, Spec §5.1).

VORBEREITUNG (macht Leo, Zugangsdaten NICHT ins Repo!):
  1. Datei backend/spikes/.env.e3dc anlegen (steht in .gitignore):
        E3DC_HOST=<IP der E3DC>
        E3DC_USER=<E3DC-Portal-Benutzer>
        E3DC_PASSWORD=<E3DC-Portal-Passwort>
        E3DC_RSCP_KEY=<RSCP-Passwort aus Personalisierung > Benutzerprofil>
  2. pip install pye3dc python-dotenv
  3. python spikes/e3dc_spike.py            (nur lesen)
     python spikes/e3dc_spike.py --schreiben (Sperre 60 s setzen, dann lösen)

ERWARTUNG laut Spike-Ziel:
  - Lesen: PV/Netz/Batterie/Haus-Leistungen + SoC plausibel gegen E3DC-Display
  - Schreiben: Entladesperre greift (Batterie-Entladung → 0 W), Lösen stellt
    Normalbetrieb wieder her; nach Skript-Abbruch ohne Lösen kehrt die E3DC
    selbstständig zurück (dokumentieren, WIE schnell — Input für Lease-TTL!)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def lade_env() -> dict:
    env_file = Path(__file__).parent / ".env.e3dc"
    if not env_file.exists():
        sys.exit(f"Fehlt: {env_file} — siehe Docstring oben.")
    werte = {}
    for zeile in env_file.read_text(encoding="utf-8").splitlines():
        if "=" in zeile and not zeile.strip().startswith("#"):
            k, v = zeile.split("=", 1)
            werte[k.strip()] = v.strip()
    return werte


def main() -> None:
    parser = argparse.ArgumentParser(description="E3DC-RSCP-Spike")
    parser.add_argument("--schreiben", action="store_true", help="Entladesperre 60 s setzen und lösen")
    args = parser.parse_args()

    env = lade_env()
    from e3dc import E3DC  # pye3dc

    e3dc = E3DC(
        E3DC.CONNECT_LOCAL,
        username=env["E3DC_USER"],
        password=env["E3DC_PASSWORD"],
        ipAddress=env["E3DC_HOST"],
        key=env["E3DC_RSCP_KEY"],
    )

    print("== Lesen ==")
    data = e3dc.poll()
    for k in ("production", "consumption", "stateOfCharge"):
        print(f"  {k}: {data.get(k)}")

    if not args.schreiben:
        print("\nNur-Lese-Modus. Für den Schreibtest: --schreiben")
        return

    print("\n== Schreiben: Entladesperre 60 s ==")
    # set_power_limits: discharge auf minimal begrenzen = faktische Entladesperre
    e3dc.set_power_limits(enable=True, max_discharge=0)
    print("  Sperre gesetzt — prüfe am E3DC-Display/Portal: Entladung sollte 0 W sein.")
    time.sleep(60)
    e3dc.set_power_limits(enable=False)
    print("  Sperre gelöst — Normalbetrieb wiederhergestellt.")
    print("\nZUSATZTEST (manuell): Skript mit gesetzter Sperre per Strg+C abbrechen und")
    print("beobachten, wann die E3DC selbstständig in den Normalbetrieb zurückkehrt.")
    print("Das Ergebnis bestimmt, ob unser Lease-TTL von 15 min passt (Spec §5.1).")


if __name__ == "__main__":
    main()
