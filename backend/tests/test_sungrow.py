"""Sungrow SG 6.0RT über Modbus TCP (REQ-042, Fail-Safe E5).

Zwei Ebenen: die reine Registerdekodierung (schnell, deckt die Fallstricke ab)
und ein Ende-zu-Ende-Lauf gegen einen nachgebauten WiNet-S. Der Nachbau ist die
Mühe wert — der Adapter spricht Modbus selbst statt über pymodbus, also muss
auch der Rahmenbau getestet werden, nicht nur die Auswertung.

Die Sollwerte im Dekodier-Test sind die **real gemessenen Werte** der Anlage
vom 2026-08-22, nicht ausgedachte Zahlen.
"""

import asyncio
import struct

import pytest

from leo_ems.devices.factory import build_adapters
from leo_ems.devices.sungrow import (
    BLOCK_ANZAHL,
    BLOCK_START,
    ERTRAG_ANZAHL,
    ERTRAG_START,
    SungrowAdapter,
    baue_anfrage,
    dekodiere_ertragsblock,
    dekodiere_messblock,
    pruefe_kopf,
    pruefe_nutzlast,
    u32,
)


def block(werte: dict[int, int], start: int, anzahl: int) -> bytes:
    """Registerblock bauen: {Registernummer: Rohwert} → Bytes wie vom Gerät."""
    regs = [werte.get(start + i, 0) for i in range(anzahl)]
    return struct.pack(f">{anzahl}H", *regs)


# Reale Messung 2026-08-22, 851 W AC bei 938 W DC
MESSUNG = {
    5011: 2686, 5012: 18,      # MPPT1: 268,6 V / 1,8 A
    5013: 2678, 5014: 17,      # MPPT2: 267,8 V / 1,7 A
    5017: 938, 5018: 0,        # DC-Leistung 938 W (u32, Low-Word zuerst)
    5019: 2304, 5020: 2320, 5021: 2321,
    5031: 851, 5032: 0,        # AC-Wirkleistung 851 W
    5036: 499,                 # 49,9 Hz — Skalierung 0,1 (nicht 0,01!)
}
ERTRAG = {5003: 8, 5004: 0, 5005: 0, 5008: 314}


# --- Dekodierung -------------------------------------------------------------

def test_messblock_ergibt_die_realen_messwerte():
    d = dekodiere_messblock(block(MESSUNG, BLOCK_START, BLOCK_ANZAHL))
    assert d["power_w"] == 851.0
    assert d["dc_leistung_w"] == 938.0
    assert (d["mppt1_v"], d["mppt1_a"]) == (268.6, 1.8)
    assert (d["mppt2_v"], d["mppt2_a"]) == (267.8, 1.7)


def test_netzfrequenz_skaliert_mit_0_1_hz():
    """Registerkarten nennen teils 0,01 Hz. Kontrollwert ist immer ~50 Hz —
    mit 0,01 käme hier 4,99 heraus, und das ist keine Netzfrequenz."""
    d = dekodiere_messblock(block(MESSUNG, BLOCK_START, BLOCK_ANZAHL))
    assert d["frequenz_hz"] == 49.9
    assert 45.0 < d["frequenz_hz"] < 55.0


def test_u32_liest_low_word_zuerst():
    """Sungrows Wortreihenfolge — die häufigste Fehlerquelle bei diesen Geräten.

    100.000 = 0x000186A0: Low-Word 0x86A0 steht im ERSTEN Register. Wer die
    Reihenfolge dreht, bekommt 0x86A00001 = gut 2,2 Milliarden statt 100.000
    und merkt es beim Gesamtertrag erst nach Jahren nicht mehr.
    """
    roh = struct.pack(">HH", 0x86A0, 0x0001)
    assert u32(roh, 5004, 5004) == 100_000


def test_ertragsblock_mit_vorzeichenbehafteter_temperatur():
    d = dekodiere_ertragsblock(block(ERTRAG, ERTRAG_START, ERTRAG_ANZAHL))
    assert d["tagesertrag_kwh"] == 0.8
    assert d["gesamtertrag_kwh"] == 0.0      # frisch in Betrieb
    assert d["temperatur_c"] == 31.4
    # Minusgrade: 0xFFCE = -50 → -5,0 °C. Als u16 gelesen wären es +6553,4 °C.
    kalt = {**ERTRAG, 5008: 0xFFCE}
    assert dekodiere_ertragsblock(block(kalt, ERTRAG_START, ERTRAG_ANZAHL))["temperatur_c"] == -5.0


# --- Rahmenbau und Antwortprüfung -------------------------------------------

def test_anfrage_rechnet_registernummer_auf_die_drahtadresse_um():
    """Datenblatt zählt ab 1, das Protokoll ab 0. Register 5031 → Adresse 5030."""
    rahmen = baue_anfrage(unit_id=1, fc=4, start_reg=5031, anzahl=2)
    _, proto, laenge, unit, fc, adresse, anzahl = struct.unpack(">HHHBBHH", rahmen)
    assert (proto, laenge, unit, fc) == (0, 6, 1, 4)
    assert adresse == 5030
    assert anzahl == 2


def test_modbus_ausnahme_wird_zum_klartext_fehler():
    """Ausnahme 0x02 ist der Normalfall bei falscher Unit-ID oder falschem Offset."""
    with pytest.raises(ConnectionError) as f:
        pruefe_nutzlast(fc=0x84, rest=bytes([0x02]), anzahl=2)
    assert "0x02" in str(f.value) and "Registeradresse" in str(f.value)


def test_zu_kurze_antwort_wird_nicht_stillschweigend_akzeptiert():
    """Ein halber Block darf nicht als Messwert durchgehen — sonst entstünden
    aus Bytemüll plausibel aussehende Leistungswerte."""
    with pytest.raises(ConnectionError):
        pruefe_nutzlast(fc=4, rest=bytes([8]) + b"\x00" * 4, anzahl=4)


def test_kopf_prueft_protokoll_und_laenge():
    with pytest.raises(ConnectionError):
        pruefe_kopf(b"\x00\x01\x00")                                # abgeschnitten
    with pytest.raises(ConnectionError):
        pruefe_kopf(struct.pack(">HHHBB", 1, 99, 5, 1, 4))          # kein Modbus-TCP
    assert pruefe_kopf(struct.pack(">HHHBB", 1, 0, 55, 1, 4)) == (55, 4)


# --- Ende zu Ende gegen einen nachgebauten WiNet-S ---------------------------

class FakeWiNetS:
    """Minimaler Modbus-TCP-Server, der sich wie der Dongle verhält.

    Kennt bewusst nur die Unit-ID 1 und antwortet allen anderen gar nicht —
    genau das Verhalten, das die Unit-ID-Suche am realen Gerät so mühsam macht.
    """

    def __init__(self, register: dict[int, int], *, unit_id: int = 1, ertrag_kaputt: bool = False):
        self.register = register
        self.unit_id = unit_id
        self.ertrag_kaputt = ertrag_kaputt
        self.anfragen: list[tuple[int, int]] = []
        self._server = None
        self.port = 0

    async def __aenter__(self):
        self._server = await asyncio.start_server(self._bediene, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *_):
        self._server.close()
        await self._server.wait_closed()

    async def _bediene(self, reader, writer):
        try:
            while True:
                kopf = await reader.readexactly(8)
                tid, _, _, unit, fc = struct.unpack(">HHHBB", kopf)
                adresse, anzahl = struct.unpack(">HH", await reader.readexactly(4))
                start = adresse + 1
                self.anfragen.append((start, anzahl))
                if unit != self.unit_id:
                    continue                                  # schweigt wie das echte Gerät
                if self.ertrag_kaputt and start == ERTRAG_START:
                    pdu = struct.pack(">BB", fc | 0x80, 0x02)  # Ausnahme statt Daten
                else:
                    nutz = block(self.register, start, anzahl)
                    pdu = struct.pack(">BB", fc, len(nutz)) + nutz
                writer.write(struct.pack(">HHHB", tid, 0, len(pdu) + 1, unit) + pdu)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            writer.close()


def test_adapter_liest_ein_vollstaendiges_messbild():
    async def lauf():
        async with FakeWiNetS({**MESSUNG, **ERTRAG}) as srv:
            adapter = SungrowAdapter("127.0.0.1", port=srv.port, unit_id=1)
            d = await adapter.read()
            await adapter.trenne()
            return d, srv.anfragen

    d, anfragen = asyncio.run(lauf())
    assert d["installiert"] is True
    assert d["power_w"] == 851.0
    assert d["tagesertrag_kwh"] == 0.8
    assert d["temperatur_c"] == 31.4
    # Zwei Lesevorgänge je Tick, nicht acht: der WiNet-S ist langsam.
    assert anfragen == [(BLOCK_START, BLOCK_ANZAHL), (ERTRAG_START, ERTRAG_ANZAHL)]


def test_adapter_haelt_die_verbindung_ueber_mehrere_ticks():
    """Der Dongle nimmt nur EINE Verbindung an. Neuaufbau je Tick provoziert
    genau das Gedränge, an dem das Auslesen sonst scheitert."""
    async def lauf():
        async with FakeWiNetS({**MESSUNG, **ERTRAG}) as srv:
            adapter = SungrowAdapter("127.0.0.1", port=srv.port)
            erste = await adapter.read()
            writer_nach_erstem = adapter._writer
            zweite = await adapter.read()
            gleich = adapter._writer is writer_nach_erstem
            await adapter.trenne()
            return erste["power_w"], zweite["power_w"], gleich

    p1, p2, gleiche_verbindung = asyncio.run(lauf())
    assert p1 == p2 == 851.0
    assert gleiche_verbindung, "Adapter hat die Verbindung zwischen Ticks neu aufgebaut"


def test_ertragszaehler_duerfen_ausfallen_ohne_die_leistung_mitzureissen():
    """Die Regelschleife braucht `power_w`. Ein klemmender Anzeigewert darf den
    Tick nicht zum Fail-Safe E5 machen — sonst fiele die Erzeugung auf 0."""
    async def lauf():
        async with FakeWiNetS({**MESSUNG, **ERTRAG}, ertrag_kaputt=True) as srv:
            adapter = SungrowAdapter("127.0.0.1", port=srv.port)
            d = await adapter.read()
            fehler = adapter.letzter_fehler
            await adapter.trenne()
            return d, fehler

    d, fehler = asyncio.run(lauf())
    assert d["power_w"] == 851.0                 # Messung steht
    assert "tagesertrag_kwh" not in d            # Anzeigewert fehlt ehrlich
    assert fehler and "Ertragszaehler" in fehler  # und wird benannt, nicht verschluckt


def test_falsche_unit_id_laeuft_in_den_fail_safe():
    """E5: Ausfall → Exception, die Regelschleife setzt die Erzeugung auf 0 und
    arbeitet weiter. Ein stiller 0-W-Wert wäre hier das gefährlichere Verhalten."""
    async def lauf():
        async with FakeWiNetS({**MESSUNG}, unit_id=1) as srv:
            adapter = SungrowAdapter("127.0.0.1", port=srv.port, unit_id=247, timeout_s=0.3)
            try:
                await adapter.read()
                return None
            except ConnectionError as e:
                return str(e)
            finally:
                await adapter.trenne()

    fehler = asyncio.run(lauf())
    assert fehler is not None and "nicht lesbar" in fehler


def test_unerreichbarer_wechselrichter_meldet_klartext():
    async def lauf():
        # Port 1 ist auf keinem üblichen System belegt
        adapter = SungrowAdapter("127.0.0.1", port=1, timeout_s=0.5)
        try:
            await adapter.read()
            return None
        except ConnectionError as e:
            return str(e)

    fehler = asyncio.run(lauf())
    assert fehler and "127.0.0.1:1" in fehler


def test_verbindung_wird_nach_fehler_verworfen():
    """Sonst hinge der nächste Tick an einem toten Socket und liefe in den Timeout."""
    async def lauf():
        adapter = SungrowAdapter("127.0.0.1", port=1, timeout_s=0.5)
        try:
            await adapter.read()
        except ConnectionError:
            pass
        return adapter._writer, adapter._reader

    assert asyncio.run(lauf()) == (None, None)


# --- Factory ----------------------------------------------------------------

def test_factory_baut_echten_adapter_mit_port_und_unit_id():
    adapters = build_adapters(
        {"sungrow_host": "192.168.178.51", "sungrow_port": "502", "sungrow_unit_id": "1"}
    )
    sg = adapters["sungrow"]
    assert isinstance(sg, SungrowAdapter)
    assert (sg.host, sg.port, sg.unit_id) == ("192.168.178.51", 502, 1)


def test_factory_faellt_auf_standardwerte_zurueck():
    """Add-on-Optionen kommen als Strings und können leer sein — ein leeres Feld
    darf nicht zu int('') führen, sondern muss den Standard nehmen."""
    sg = build_adapters({"sungrow_host": "192.168.178.51", "sungrow_port": "", "sungrow_unit_id": ""})["sungrow"]
    assert (sg.port, sg.unit_id) == (502, 1)
