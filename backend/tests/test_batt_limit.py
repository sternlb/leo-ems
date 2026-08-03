"""Dynamische Entladegrenze der Hausbatterie (Spec §5.1, planner/batt_limit.py).

Die Frage hinter diesen Tests: Deckt die Batterie den Netzbezug beim Laden — und
hört sie da auf, wo sie anfinge, das Auto zu füttern?
"""

from leo_ems.config import RegelConfig
from leo_ems.planner.batt_limit import EntladeLimitRegler


def regler(**kwargs) -> EntladeLimitRegler:
    return EntladeLimitRegler(RegelConfig(**kwargs))


def tick(r, *, netz=0.0, batt=0.0, soc=60.0, charging=True, netz_gewollt=False):
    return r.update(charging=charging, netz_gewollt=netz_gewollt, soc_batt=soc,
                    p_netz_w=netz, p_batterie_w=batt)


def test_ohne_ladung_keine_begrenzung():
    e = tick(regler(), charging=False)
    assert e.limit_w is None and e.art == "aus"


def test_netzbezug_gibt_die_batterie_frei():
    e = tick(regler(), netz=800)
    assert e.art == "dynamisch"
    assert e.limit_w == 1000                 # 800 Bedarf + 200 Puffer


def test_grenze_bleibt_stehen_wenn_die_batterie_deckt():
    """Kern der Regelform: die Deckung darf sich nicht selbst wegregeln.

    Ein Regler, der nur auf den Netzbezug schaut, würde hier schwingen — Grenze
    hoch, Netz auf 0, Grenze auf 0, Netzbezug zurück.
    """
    r = regler()
    tick(r, netz=800)
    e = tick(r, netz=0, batt=-800)           # Batterie deckt jetzt, Netz ist bei 0
    assert e.limit_w == 1000


def test_lastsprung_sofort_hoch_und_gedaempft_zurueck():
    r = regler()
    e = tick(r, netz=2500)
    assert e.limit_w == 2700                 # hoch: ohne Verzögerung, Netzbezug kostet

    e = tick(r, netz=0)                      # Last weg
    assert e.limit_w == 2200                 # runter: max. batt_dyn_abbau_w (500 W) je Tick
    assert tick(r, netz=0).limit_w == 1700


def test_grenze_hat_einen_deckel():
    e = tick(regler(), netz=9000)
    assert e.limit_w == 3000                 # batt_dyn_max_w


def test_kleinstbedarf_wird_zu_null():
    """Unter ~65 W entlädt die E3DC ohnehin nicht — solche Grenzen sind Schein."""
    e = tick(regler(batt_dyn_puffer_w=0), netz=40)
    assert e.limit_w == 0


def test_gewollter_netzbezug_bleibt_hart_gesperrt():
    """Schnell, Garantieladung, das Minimum in PV+Min: dort ist Netz die Absicht."""
    e = tick(regler(), netz=5000, netz_gewollt=True)
    assert e.limit_w == 0 and e.art == "hart"


def test_unter_dem_vorrang_soc_bleibt_es_hart():
    e = tick(regler(), netz=800, soc=20)
    assert e.limit_w == 0 and e.art == "hart"
    assert "Hausbatterie zuerst" in e.grund


def test_soc_hysterese_verhindert_flattern_an_der_grenze():
    """25 % ist die Schwelle — zurück in den dynamischen Betrieb erst bei 27 %."""
    r = regler()
    assert tick(r, netz=800, soc=20).art == "hart"
    assert tick(r, netz=800, soc=25).art == "hart"     # gerade drüber reicht nicht
    assert tick(r, netz=800, soc=26).art == "hart"
    assert tick(r, netz=800, soc=27).art == "dynamisch"


def test_abschalter_stellt_das_alte_verhalten_wieder_her():
    """batt_dyn_aktiv=False = harte Sperre wie in v0.8.0 — Notausstieg ohne Deployment."""
    e = tick(regler(batt_dyn_aktiv=False), netz=800)
    assert e.limit_w == 0 and e.art == "hart"


def test_ladeende_setzt_den_regler_zurueck():
    r = regler()
    tick(r, netz=2500)
    tick(r, charging=False)
    assert tick(r, netz=0).limit_w == 200     # beginnt wieder beim reinen Puffer
