"""Sungrow SG 6.0RT — Wechselrichter der Garagendach-Anlage (REQ-040/042).

Die Anlage (12× Trina 470 Wp = 5,64 kWp, 2 Strings à 6, Ost/West) ist seit
2026-08-22 in Betrieb und hängt AC-seitig am selben Anschlusspunkt wie die
E3DC. Für die Regelung ist der Wechselrichter ein **reiner Erzeuger**: Es gibt
nichts zu steuern, und sein Beitrag erscheint ohnehin am Netzpunkt der E3DC.
Der gelesene Wert geht deshalb in die Gesamterzeugungs-Anzeige (REQ-040/051)
und **nicht** in die Überschussformel — sonst zählte die Erzeugung doppelt.

Fail-Safe E5 (Leo, 2026-07-12): Ausfall → Werte 0, Betrieb läuft weiter. Der
Adapter signalisiert den Ausfall als Exception, bewertet wird in core/loop.py.

Warum kein pymodbus: Gebraucht wird ausschließlich „Input-Register lesen".
Das sind die ~40 Zeilen unten, gegen die reale Anlage verifiziert. pymodbus
hat den Slave-Parameter zwischen 3.7 und 3.9 von `slave` auf `device_id`
umbenannt — diese Fallhöhe lohnt für einen einzigen Funktionscode nicht.

Registerkarte und Fallstricke: docs/systems/sungrow.md
"""

from __future__ import annotations

import asyncio
import struct
from datetime import datetime

from .base import DeviceAdapter

# --- Register (Nummern wie im Sungrow-Datenblatt, also 1-basiert) -------------
# Auf dem Draht sind sie 0-basiert; das -1 passiert zentral in baue_anfrage().
REG_TAGESERTRAG = 5003      # 0,1 kWh
REG_GESAMTERTRAG = 5004     # kWh, u32
REG_TEMPERATUR = 5008       # 0,1 °C, vorzeichenbehaftet
REG_MPPT1_V = 5011          # 0,1 V   (5012 = Strom, 0,1 A)
REG_MPPT2_V = 5013          # 0,1 V   (5014 = Strom, 0,1 A)
REG_DC_LEISTUNG = 5017      # W, u32
REG_AC_LEISTUNG = 5031      # W, u32  ← der eine Wert, auf den es ankommt
REG_FREQUENZ = 5036         # 0,1 Hz  (NICHT 0,01 — siehe docs/systems/sungrow.md)

FC_INPUT_REGISTER = 4

# Ein Block deckt alles von MPPT1 bis Frequenz ab: 5011..5036 sind 26 Register,
# deutlich unter dem Modbus-Limit von 125. Ein Lesevorgang statt sechs — der
# WiNet-S antwortet träge und nimmt ohnehin nur eine Verbindung an.
BLOCK_START = REG_MPPT1_V
BLOCK_ANZAHL = REG_FREQUENZ - REG_MPPT1_V + 1

# Zweiter, unkritischer Block: Ertragszähler und Temperatur (nur Anzeige).
ERTRAG_START = REG_TAGESERTRAG
ERTRAG_ANZAHL = REG_TEMPERATUR - REG_TAGESERTRAG + 1


# --- Reine Dekodierung (ohne I/O, damit ohne Hardware testbar) ---------------

def u16(block: bytes, reg: int, basis: int) -> int:
    """Ein 16-Bit-Register aus einem Antwortblock, adressiert per Registernummer."""
    return struct.unpack_from(">H", block, (reg - basis) * 2)[0]


def s16(block: bytes, reg: int, basis: int) -> int:
    return struct.unpack_from(">h", block, (reg - basis) * 2)[0]


def u32(block: bytes, reg: int, basis: int) -> int:
    """32-Bit-Wert. Sungrow legt das **Low-Word zuerst** ab — die mit Abstand
    häufigste Fehlerquelle beim Lesen dieser Geräte."""
    lo, hi = struct.unpack_from(">HH", block, (reg - basis) * 2)
    return (hi << 16) | lo


def dekodiere_messblock(block: bytes) -> dict:
    """Block ab REG_MPPT1_V in Messwerte übersetzen."""
    b = BLOCK_START
    return {
        "power_w": float(u32(block, REG_AC_LEISTUNG, b)),
        "dc_leistung_w": float(u32(block, REG_DC_LEISTUNG, b)),
        "mppt1_v": u16(block, REG_MPPT1_V, b) / 10,
        "mppt1_a": u16(block, REG_MPPT1_V + 1, b) / 10,
        "mppt2_v": u16(block, REG_MPPT2_V, b) / 10,
        "mppt2_a": u16(block, REG_MPPT2_V + 1, b) / 10,
        "frequenz_hz": u16(block, REG_FREQUENZ, b) / 10,
    }


def dekodiere_ertragsblock(block: bytes) -> dict:
    b = ERTRAG_START
    return {
        "tagesertrag_kwh": u16(block, REG_TAGESERTRAG, b) / 10,
        "gesamtertrag_kwh": float(u32(block, REG_GESAMTERTRAG, b)),
        "temperatur_c": s16(block, REG_TEMPERATUR, b) / 10,
    }


def baue_anfrage(unit_id: int, fc: int, start_reg: int, anzahl: int) -> bytes:
    """Modbus-TCP-Rahmen. `start_reg` ist 1-basiert wie im Datenblatt."""
    pdu = struct.pack(">BHH", fc, start_reg - 1, anzahl)
    return struct.pack(">HHHB", 1, 0, len(pdu) + 1, unit_id) + pdu


def pruefe_kopf(kopf: bytes) -> tuple[int, int]:
    """MBAP-Kopf zerlegen → (Restlänge, Funktionscode). Wirft bei Schrott."""
    if len(kopf) < 8:
        raise ConnectionError(f"Sungrow: abgeschnittene Antwort ({len(kopf)} Byte)")
    _, proto, laenge, _, fc = struct.unpack(">HHHBB", kopf)
    if proto != 0:
        raise ConnectionError(f"Sungrow: kein Modbus-TCP (Protokoll-ID {proto})")
    return laenge, fc


def pruefe_nutzlast(fc: int, rest: bytes, anzahl: int) -> bytes:
    """Ausnahmecodes und Länge prüfen, sonst die reinen Registerbytes liefern."""
    if fc & 0x80:
        code = rest[0] if rest else 0
        hinweis = "unzulaessige Registeradresse" if code == 2 else "siehe Modbus-Spezifikation"
        raise ConnectionError(f"Sungrow: Modbus-Ausnahme 0x{code:02X} ({hinweis})")
    nutzlast = rest[1:]
    if len(nutzlast) != anzahl * 2:
        raise ConnectionError(
            f"Sungrow: {len(nutzlast)} Byte erhalten, {anzahl * 2} erwartet"
        )
    return nutzlast


# --- Adapter -----------------------------------------------------------------

class SungrowAdapter(DeviceAdapter):
    """Liest den SG 6.0RT über Modbus TCP (WiNet-S-Dongle).

    Die Verbindung bleibt über Ticks hinweg offen: Der WiNet-S nimmt nur
    **eine** Modbus-Verbindung an, und ein Verbindungsaufbau je Tick provoziert
    genau das Gedränge, das er nicht verträgt.
    """

    name = "sungrow"

    def __init__(self, host: str, port: int = 502, unit_id: int = 1, timeout_s: float = 5.0):
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self._timeout_s = timeout_s
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._sperre = asyncio.Lock()
        self._last: datetime | None = None
        self.letzter_fehler: str | None = None

    async def _verbinde(self) -> None:
        if self._writer is not None:
            return
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), timeout=self._timeout_s
        )

    async def trenne(self) -> None:
        """Verbindung schließen — nach jedem Fehler, damit der nächste Tick sauber
        neu aufbaut statt auf einem halb toten Socket zu warten."""
        writer, self._writer, self._reader = self._writer, None, None
        if writer is None:
            return
        try:
            writer.close()
            await writer.wait_closed()
        except (OSError, asyncio.TimeoutError):  # pragma: no cover — reines Aufräumen
            pass

    async def _lies_block(self, start_reg: int, anzahl: int) -> bytes:
        await self._verbinde()
        assert self._reader is not None and self._writer is not None
        self._writer.write(baue_anfrage(self.unit_id, FC_INPUT_REGISTER, start_reg, anzahl))
        await self._writer.drain()
        kopf = await asyncio.wait_for(self._reader.readexactly(8), timeout=self._timeout_s)
        laenge, fc = pruefe_kopf(kopf)
        rest = await asyncio.wait_for(
            self._reader.readexactly(max(laenge - 2, 0)), timeout=self._timeout_s
        )
        return pruefe_nutzlast(fc, rest, anzahl)

    async def read(self) -> dict:
        """Ein Messbild lesen. Wirft bei Nichterreichbarkeit (Fail-Safe E5)."""
        async with self._sperre:
            try:
                mess = dekodiere_messblock(await self._lies_block(BLOCK_START, BLOCK_ANZAHL))
            except ConnectionError:
                await self.trenne()
                raise
            except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError,
                    struct.error) as e:
                await self.trenne()
                self.letzter_fehler = f"{type(e).__name__}: {e}"
                raise ConnectionError(
                    f"Sungrow {self.host}:{self.port} nicht lesbar — {e}"
                ) from e

            # Die Ertragszähler sind reine Anzeige. Klemmt dieser Block, darf das
            # die Leistungsmessung nicht mitreißen — die braucht die Regelschleife.
            ertrag: dict = {}
            fehler = None
            try:
                ertrag = dekodiere_ertragsblock(
                    await self._lies_block(ERTRAG_START, ERTRAG_ANZAHL)
                )
            except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError,
                    ConnectionError, struct.error) as e:
                fehler = f"Ertragszaehler nicht lesbar: {type(e).__name__}: {e}"

            self._last = datetime.now()
            self.letzter_fehler = fehler
            return {"installiert": True, **mess, **ertrag}

    @property
    def last_update(self) -> datetime | None:
        return self._last


class SungrowStub(DeviceAdapter):
    """Platzhalter ohne konfigurierten Host — konstant 0 W.

    Bleibt auch nach der Installation bestehen: Er ist der definierte Zustand,
    wenn `sungrow_host` leer ist, und hält die Entwicklung ohne Anlage im Netz
    lauffähig.
    """

    name = "sungrow"

    def __init__(self):
        self._last: datetime | None = None

    async def read(self) -> dict:
        self._last = datetime.now()
        return {"power_w": 0.0, "installiert": False}

    @property
    def last_update(self) -> datetime | None:
        return self._last
