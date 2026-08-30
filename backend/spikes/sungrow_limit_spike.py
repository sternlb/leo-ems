"""Spike: Nimmt der Sungrow SG 6.0RT eine Leistungsbegrenzung über Modbus an?

Zwei Fragen, beide offen aus `docs/einspeisegrenze.md` (Issue #15):

1. **Schreibzugriff.** Der Adapter liest bisher nur Input-Register (FC04).
   Die Begrenzung liegt auf Holding-Registern und braucht FC03/FC06 — ob der
   WiNet-S-Dongle das zulässt oder nur lesend freigeschaltet ist, ist unbelegt.
2. **Bezugsgröße von Register 5008.** Das Handbuch sagt „0,1 % der
   Nennleistung". Welche Nennleistung — 6,0 kW (Wechselrichter) oder 5,64 kWp
   (Module)? Der Unterschied sind 6 %, und er entscheidet, ob die
   Einspeisegrenze eingehalten wird oder um 200 W verfehlt.

**Vorgehen.** Der Spike misst die aktuelle Leistung, setzt eine Grenze auf die
*Hälfte* davon und schaut nach, wo sich die Anlage einpendelt. Aus
gemessener Leistung geteilt durch den gesetzten Anteil fällt die Bezugsgröße
heraus — bei 6,7 % Sollwert und 400 W Ergebnis sind es 6,0 kW, bei 376 W wären
es 5,64 kWp. Eine Grenze *über* der aktuellen Leistung würde gar nichts zeigen.

**Sicherheit.** Der ursprüngliche Zustand von 5007 und 5008 wird vorher gelesen
und im `finally` bedingungslos zurückgeschrieben — auch bei Strg+C oder einem
Fehler. Die Anlage ist für die Dauer des Tests (gut eine Minute) gedrosselt;
verloren geht die Energie, die in dieser Minute nicht erzeugt wird.

    python spikes/sungrow_limit_spike.py            # nur lesen, nichts anfassen
    python spikes/sungrow_limit_spike.py --schreiben # der eigentliche Test
"""

from __future__ import annotations

import argparse
import asyncio
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from leo_ems.devices.sungrow import (  # noqa: E402
    REG_AC_LEISTUNG, baue_anfrage, pruefe_kopf, pruefe_nutzlast,
)

HOST, PORT, UNIT = "192.168.178.51", 502, 1

FC_HOLDING = 3
FC_SCHREIBEN = 6

REG_SCHALTER = 5007      # 0xAA = Begrenzung an, 0x55 = aus
REG_SOLLWERT = 5008      # in 0,1 % der Nennleistung
NENN_W = 6000.0          # Annahme, die dieser Spike prüft

AN, AUS = 0xAA, 0x55
TESTDAUER_S = 60
ABTASTUNG_S = 5


class Modbus:
    """Minimaler Client — dieselbe Rahmenlogik wie der Adapter, nur zusätzlich
    mit Holding-Registern und dem Schreibbefehl."""

    def __init__(self, host: str, port: int, unit: int, timeout_s: float = 5.0):
        self.host, self.port, self.unit, self.timeout_s = host, port, unit, timeout_s
        self._r: asyncio.StreamReader | None = None
        self._w: asyncio.StreamWriter | None = None

    async def verbinde(self) -> None:
        self._r, self._w = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), timeout=self.timeout_s)

    async def trenne(self) -> None:
        if self._w is None:
            return
        self._w.close()
        try:
            await self._w.wait_closed()
        except OSError:
            pass
        self._r = self._w = None

    async def _antwort(self, anzahl: int) -> bytes:
        assert self._r is not None
        kopf = await asyncio.wait_for(self._r.readexactly(8), timeout=self.timeout_s)
        laenge, fc = pruefe_kopf(kopf)
        rest = await asyncio.wait_for(
            self._r.readexactly(max(laenge - 2, 0)), timeout=self.timeout_s)
        return pruefe_nutzlast(fc, rest, anzahl)

    async def lies(self, fc: int, start: int, anzahl: int) -> list[int]:
        assert self._w is not None
        self._w.write(baue_anfrage(self.unit, fc, start, anzahl))
        await self._w.drain()
        roh = await self._antwort(anzahl)
        return [struct.unpack_from(">H", roh, i * 2)[0] for i in range(anzahl)]

    async def schreibe(self, reg: int, wert: int) -> int:
        """FC06 — ein Holding-Register. Die Antwort spiegelt Adresse und Wert;
        eine Ausnahme (0x80er-Funktionscode) wirft `pruefe_nutzlast`."""
        assert self._r is not None and self._w is not None
        pdu = struct.pack(">BHH", FC_SCHREIBEN, reg - 1, wert)
        self._w.write(struct.pack(">HHHB", 1, 0, len(pdu) + 1, self.unit) + pdu)
        await self._w.drain()
        kopf = await asyncio.wait_for(self._r.readexactly(8), timeout=self.timeout_s)
        laenge, fc = pruefe_kopf(kopf)
        rest = await asyncio.wait_for(
            self._r.readexactly(max(laenge - 2, 0)), timeout=self.timeout_s)
        if fc & 0x80:
            code = rest[0] if rest else 0
            raise ConnectionError(f"Modbus-Ausnahme 0x{code:02X} beim Schreiben von {reg}")
        _, echo = struct.unpack(">HH", rest)
        return echo


async def ac_leistung(m: Modbus) -> float:
    """AC-Leistung aus dem Input-Register (u32, W).

    Sungrow legt das **Low-Word zuerst** ab (siehe `devices/sungrow.u32`) —
    andersherum gelesen kommen hier 17 MW heraus statt 263 W.
    """
    lo, hi = await m.lies(4, REG_AC_LEISTUNG, 2)
    return float((hi << 16) | lo)


async def main(schreiben: bool) -> int:
    m = Modbus(HOST, PORT, UNIT)
    await m.verbinde()
    print(f"verbunden mit {HOST}:{PORT} (Unit {UNIT})\n")

    try:
        schalter, sollwert = await m.lies(FC_HOLDING, REG_SCHALTER, 2)
    except ConnectionError as e:
        print(f"Holding-Register {REG_SCHALTER}/{REG_SOLLWERT} nicht lesbar: {e}")
        await m.trenne()
        return 1

    zustand = {AN: "an", AUS: "aus"}.get(schalter, f"unbekannt (0x{schalter:02X})")
    print(f"5007 Begrenzung : 0x{schalter:02X} ({zustand})")
    print(f"5008 Sollwert   : {sollwert} -> {sollwert / 10:.1f} %")

    p0 = await ac_leistung(m)
    print(f"5031 AC-Leistung: {p0:.0f} W\n")

    if not schreiben:
        print("Nur gelesen. Für den Schreibtest: --schreiben")
        await m.trenne()
        return 0

    if p0 < 200:
        print(f"Abbruch: bei {p0:.0f} W ist keine Drosselung sichtbar.")
        print("Der Test braucht Sonne — bei mindestens ~500 W wiederholen.")
        await m.trenne()
        return 2

    ziel_w = p0 / 2.0
    promille = max(1, round(ziel_w / NENN_W * 1000))
    print(f"Test: Grenze auf {promille / 10:.1f} % — das wären {promille / 1000 * NENN_W:.0f} W,")
    print(f"      wenn sich die Prozente auf {NENN_W:.0f} W beziehen.")
    print(f"      Bezögen sie sich auf 5.640 W (Module), wären es {promille / 1000 * 5640:.0f} W.\n")

    try:
        echo = await m.schreibe(REG_SOLLWERT, promille)
        print(f"5008 geschrieben: {promille} (Echo {echo})")
        echo = await m.schreibe(REG_SCHALTER, AN)
        print(f"5007 geschrieben: 0x{AN:02X} (Echo 0x{echo:02X})\n")

        print("Zeit   Leistung   Anteil an der gesetzten Grenze")
        for t in range(0, TESTDAUER_S + 1, ABTASTUNG_S):
            if t:
                await asyncio.sleep(ABTASTUNG_S)
            p = await ac_leistung(m)
            bezug = p / (promille / 1000.0) if promille else 0.0
            print(f"{t:4d}s  {p:7.0f} W   => Bezugsgröße {bezug:6.0f} W")
        p_ende = await ac_leistung(m)
    finally:
        # Bedingungslos zurück — auch nach Strg+C oder einem Fehler oben.
        print("\nZurücksetzen ...")
        try:
            await m.schreibe(REG_SOLLWERT, sollwert)
            await m.schreibe(REG_SCHALTER, schalter)
            zurueck = await m.lies(FC_HOLDING, REG_SCHALTER, 2)
            print(f"5007/5008 wieder: 0x{zurueck[0]:02X} / {zurueck[1]}")
        except (ConnectionError, OSError, asyncio.TimeoutError) as e:
            print(f"!!! Zurücksetzen fehlgeschlagen: {e}")
            print(f"!!! Von Hand setzen: 5008={sollwert}, 5007=0x{schalter:02X}")
        await m.trenne()

    print(f"\nErgebnis: {p0:.0f} W vorher -> {p_ende:.0f} W unter der Grenze.")
    print(f"Bezugsgröße rechnerisch {p_ende / (promille / 1000.0):.0f} W "
          f"(6.000 W = Wechselrichter, 5.640 W = Module).")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--schreiben", action="store_true",
                    help="Grenze wirklich setzen (drosselt die Anlage ~1 Minute)")
    raise SystemExit(asyncio.run(main(ap.parse_args().schreiben)))
