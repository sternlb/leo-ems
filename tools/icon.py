"""Erzeugt `icon.png` und `logo.png` für das Add-on (Issue #3).

**Warum ein Skript und keine abgelegte Bilddatei.** Ein PNG im Repo ist ein
Endzustand, den niemand mehr ändern kann, ohne dieselbe Software wie beim
ersten Mal zu haben. Der Zeichenweg hier ist die Quelle: Farben, Größen und
Formen stehen als Zahlen da, das Ergebnis lässt sich jederzeit in einer anderen
Auflösung neu erzeugen — und wenn das Add-on irgendwann ein Favicon oder ein
Play-Store-Bild braucht, ist es eine Zeile.

**Motiv** (nach Leos Entwurf): ein dunkelblauer Kreis als Haus, in dem vier
Verbraucher/Erzeuger um eine Mitte liegen — Wallbox und Wärme in Orange links,
PV und Batterie in Blau rechts. Die Bögen dazwischen sind der Fluss, den das
EMS verteilt; die Mitte trägt das „L" mit dem Blitz. Genau das tut das Gerät:
Es sitzt zwischen den vier Punkten und entscheidet, wohin die Energie geht.

**Gezeichnet wird vierfach vergrößert und dann verkleinert** (Supersampling).
PIL kann keine Kantenglättung beim Zeichnen; über den Umweg wird sie geschenkt,
und das Ergebnis hält auch bei 48 px in der HA-Seitenleiste noch zusammen.

    python tools/icon.py            # schreibt icon.png und logo.png in die Wurzel
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WURZEL = Path(__file__).resolve().parents[1]
SS = 4                       # Supersampling-Faktor

# --- Farben (Leos Entwurf) ---------------------------------------------------
WEISS = (255, 255, 255, 255)
NAVY_HELL = (30, 64, 110, 255)      # oben links im Kreis
NAVY_DUNKEL = (11, 24, 44, 255)     # unten rechts
NAVY_KNOTEN = (22, 45, 78, 255)
ORANGE = (245, 146, 51, 255)
ORANGE_HELL = (255, 178, 92, 255)
BLAU = (79, 168, 232, 255)
BLAU_HELL = (130, 200, 245, 255)
TEXT_DUNKEL = (23, 42, 71, 255)
TEXT_GRAU = (108, 125, 145, 255)

SCHRIFT_FETT = r"C:\Windows\Fonts\segoeuib.ttf"
SCHRIFT_NORMAL = r"C:\Windows\Fonts\segoeui.ttf"


# --- Bausteine ---------------------------------------------------------------

def kreis(d: ImageDraw.ImageDraw, x, y, r, fill=None, outline=None, breite=0):
    d.ellipse([x - r, y - r, x + r, y + r], fill=fill, outline=outline, width=breite)


def verlaufskreis(groesse: int, r: int, von, bis) -> Image.Image:
    """Kreis mit diagonalem Verlauf.

    Gerechnet wird auf einem kleinen Raster und danach hochskaliert: Ein Verlauf
    hat keine Kanten, die beim Vergrößern kaputtgehen könnten, und 64×64 Pixel
    sind sofort fertig. Der erste Versuch zeichnete stattdessen versetzte Linien
    über die volle Fläche — der ließ Ecken unbedeckt, und der Kreis bekam
    abgeschnittene Ränder.
    """
    k = 64
    klein = Image.new("RGBA", (k, k))
    klein.putdata([
        tuple(round(von[c] + (bis[c] - von[c]) * ((x + y) / (2 * (k - 1)))) for c in range(4))
        for y in range(k) for x in range(k)
    ])
    flaeche = klein.resize((groesse, groesse), Image.BICUBIC)
    maske = Image.new("L", (groesse, groesse), 0)
    ImageDraw.Draw(maske).ellipse(
        [groesse // 2 - r, groesse // 2 - r, groesse // 2 + r, groesse // 2 + r], fill=255)
    aus = Image.new("RGBA", (groesse, groesse), (0, 0, 0, 0))
    aus.paste(flaeche, (0, 0), maske)
    return aus


def bogen_punkte(p0, p1, p2, n=64):
    """Quadratische Bézierkurve als Punktliste."""
    return [(
        (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0],
        (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1],
    ) for t in (i / n for i in range(n + 1))]


def fluss(d, p0, p1, p2, farbe, breite):
    """Ein Energiefluss: weiche Kurve mit runden Enden."""
    pts = bogen_punkte(p0, p1, p2)
    d.line(pts, fill=farbe, width=breite, joint="curve")
    for p in (pts[0], pts[-1]):
        kreis(d, p[0], p[1], breite / 2, fill=farbe)


def gestrichelter_bogen(d, cx, cy, r, start, ende, farbe, breite, segmente=9, luecke=0.38):
    """Gestrichelter Kreisbogen — der „Ring" um die Mitte."""
    spanne = (ende - start) / segmente
    for i in range(segmente):
        a0 = start + i * spanne
        a1 = a0 + spanne * (1 - luecke)
        d.arc([cx - r, cy - r, cx + r, cy + r], a0, a1, fill=farbe, width=breite)


def blitz(d, cx, cy, h, farbe):
    """Klassischer Blitz, an der Mitte ausgerichtet."""
    b = h * 0.52
    p = [(cx + b * 0.10, cy - h / 2), (cx - b * 0.50, cy + h * 0.10),
         (cx - b * 0.05, cy + h * 0.10), (cx - b * 0.14, cy + h / 2),
         (cx + b * 0.52, cy - h * 0.12), (cx + b * 0.05, cy - h * 0.12)]
    d.polygon(p, fill=farbe)


# --- Die vier Knoten-Symbole -------------------------------------------------
# Bewusst grob: Bei 512 px ist ein Knoten rund 50 px groß, in der HA-Seitenleiste
# noch keine 6 px. Was dort nicht als Silhouette funktioniert, ist Dekoration.

def sym_wallbox(d, cx, cy, s, farbe):
    d.rounded_rectangle([cx - s * 0.40, cy - s * 0.56, cx + s * 0.16, cy + s * 0.56],
                        radius=s * 0.17, fill=farbe)
    # Kabel: ein kurzer Bogen zur Seite, mehr braucht es bei dieser Größe nicht.
    d.line(bogen_punkte((cx + s * 0.16, cy + s * 0.10), (cx + s * 0.48, cy + s * 0.16),
                        (cx + s * 0.44, cy - s * 0.34), 20),
           fill=farbe, width=max(2, int(s * 0.13)), joint="curve")
    blitz(d, cx - s * 0.12, cy - s * 0.02, s * 0.66, (13, 27, 48, 255))


def sym_pv(d, cx, cy, s, farbe):
    d.polygon([(cx - s * 0.55, cy + s * 0.34), (cx - s * 0.34, cy - s * 0.34),
               (cx + s * 0.55, cy - s * 0.34), (cx + s * 0.34, cy + s * 0.34)], fill=farbe)
    w = max(2, int(s * 0.10))
    d.line([(cx - s * 0.45, cy), (cx + s * 0.45, cy)], fill=(13, 27, 48, 255), width=w)
    for t in (-0.16, 0.16):
        d.line([(cx + s * t - s * 0.07, cy - s * 0.34), (cx + s * t + s * 0.07, cy + s * 0.34)],
               fill=(13, 27, 48, 255), width=w)


def sym_flamme(d, cx, cy, s, farbe):
    p = bogen_punkte((cx, cy - s * 0.58), (cx + s * 0.62, cy + s * 0.02), (cx, cy + s * 0.52), 26)
    p += bogen_punkte((cx, cy + s * 0.52), (cx - s * 0.62, cy + s * 0.02), (cx, cy - s * 0.58), 26)
    d.polygon(p, fill=farbe)
    q = bogen_punkte((cx, cy - s * 0.10), (cx + s * 0.30, cy + s * 0.16), (cx, cy + s * 0.44), 20)
    q += bogen_punkte((cx, cy + s * 0.44), (cx - s * 0.30, cy + s * 0.16), (cx, cy - s * 0.10), 20)
    d.polygon(q, fill=(13, 27, 48, 255))


def sym_batterie(d, cx, cy, s, farbe):
    d.rounded_rectangle([cx - s * 0.34, cy - s * 0.46, cx + s * 0.34, cy + s * 0.56],
                        radius=s * 0.14, fill=farbe)
    d.rounded_rectangle([cx - s * 0.13, cy - s * 0.62, cx + s * 0.13, cy - s * 0.44],
                        radius=s * 0.05, fill=farbe)
    blitz(d, cx, cy + s * 0.05, s * 0.62, (13, 27, 48, 255))


# --- Das Zeichen -------------------------------------------------------------

def zeichne_zeichen(groesse: int, kachel: bool = True) -> Image.Image:
    """Das Symbol allein (mit oder ohne weiße Kachel darunter)."""
    n = groesse * SS
    bild = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(bild)
    c = n / 2

    if kachel:
        d.rounded_rectangle([0, 0, n - 1, n - 1], radius=n * 0.225, fill=WEISS)

    r_kreis = n * (0.385 if kachel else 0.47)
    bild.alpha_composite(verlaufskreis(n, int(r_kreis), NAVY_HELL, NAVY_DUNKEL))

    # Ring aus zwei gestrichelten Bögen: links Orange (Verbrauch), rechts Blau
    # (Erzeugung/Speicher) — dieselbe Zuordnung wie im Dashboard.
    r_ring = r_kreis * 0.64
    w_ring = max(2, int(n * 0.011))
    gestrichelter_bogen(d, c, c, r_ring, 143, 217, ORANGE, w_ring, segmente=5)
    gestrichelter_bogen(d, c, c, r_ring, 323, 397, BLAU, w_ring, segmente=5)

    # Vier Knoten auf den Diagonalen
    r_bahn = r_kreis * 0.64
    r_knoten = r_kreis * 0.21
    w_fluss = max(3, int(n * 0.016))
    knoten = [
        (135, ORANGE, sym_wallbox),     # links oben  — Wallbox
        (45, BLAU, sym_pv),             # rechts oben — PV
        (225, ORANGE, sym_flamme),      # links unten — Wärme
        (315, BLAU, sym_batterie),      # rechts unten— Batterie
    ]
    for winkel, farbe, symbol in knoten:
        a = math.radians(winkel)
        kx, ky = c + r_bahn * math.cos(a), c - r_bahn * math.sin(a)
        # Fluss von der Mitte zum Knoten: Der Stützpunkt sitzt auf halber
        # Strecke, senkrecht zur Verbindung versetzt — dadurch schwingt die Bahn
        # aus, statt schnurgerade zu laufen. Alle vier schwingen gleichsinnig,
        # sonst sieht das Zeichen unruhig aus.
        mx, my = c + r_bahn * 0.5 * math.cos(a), c - r_bahn * 0.5 * math.sin(a)
        sx = mx + r_bahn * 0.34 * math.cos(a + math.radians(90))
        sy = my - r_bahn * 0.34 * math.sin(a + math.radians(90))
        fluss(d, (c, c), (sx, sy), (kx, ky), farbe, w_fluss)

    for winkel, farbe, symbol in knoten:
        a = math.radians(winkel)
        kx, ky = c + r_bahn * math.cos(a), c - r_bahn * math.sin(a)
        kreis(d, kx, ky, r_knoten, fill=NAVY_KNOTEN)
        kreis(d, kx, ky, r_knoten, outline=farbe, breite=max(2, int(n * 0.010)))
        symbol(d, kx, ky, r_knoten * 0.95, farbe)

    # Mitte: dunkler Kern mit Orangering, darin L und Blitz
    r_mitte = r_kreis * 0.245
    kreis(d, c, c, r_mitte, fill=(9, 20, 38, 255))
    kreis(d, c, c, r_mitte, outline=ORANGE, breite=max(2, int(n * 0.011)))
    f = ImageFont.truetype(SCHRIFT_FETT, int(r_mitte * 1.25))
    d.text((c - r_mitte * 0.34, c), "L", font=f, fill=ORANGE_HELL, anchor="mm")
    blitz(d, c + r_mitte * 0.36, c, r_mitte * 1.05, ORANGE_HELL)

    return bild.resize((groesse, groesse), Image.LANCZOS)


def zeichne_logo(breite: int = 800) -> Image.Image:
    """Zeichen plus Wortmarke — für die Store-Seite des Add-ons.

    Die Höhe ergibt sich aus dem Inhalt und steht nicht als Verhältnis fest:
    Beim ersten Versuch lief der Untertitel unten aus dem Bild, weil die
    Schriftgrößen sich ändern durften und die Leinwand nicht.
    """
    n = breite * SS
    rand = int(n * 0.045)
    zeichen_px = int(breite * 0.42)
    zeichen = zeichne_zeichen(zeichen_px, kachel=False)
    zeichen = zeichen.resize((zeichen_px * SS, zeichen_px * SS), Image.LANCZOS)

    f1 = ImageFont.truetype(SCHRIFT_FETT, int(n * 0.115))
    f2 = ImageFont.truetype(SCHRIFT_NORMAL, int(n * 0.042))
    h1 = f1.getbbox("LEO EMS")[3] - f1.getbbox("LEO EMS")[1]
    h2 = f2.getbbox("INTELLIGENT FLOW")[3] - f2.getbbox("INTELLIGENT FLOW")[1]
    luft1, luft2 = int(n * 0.045), int(n * 0.028)

    hoehe = rand + zeichen.height + luft1 + h1 + luft2 + h2 + rand
    bild = Image.new("RGBA", (n, hoehe), (0, 0, 0, 0))
    d = ImageDraw.Draw(bild)

    bild.alpha_composite(zeichen, ((n - zeichen.width) // 2, rand))

    y = rand + zeichen.height + luft1
    d.text((n / 2, y - f1.getbbox("LEO EMS")[1]), "LEO EMS", font=f1, fill=TEXT_DUNKEL, anchor="ma")

    # Sperrschrift von Hand: PIL kennt kein letter-spacing.
    y2 = y + h1 + luft2 - f2.getbbox("INTELLIGENT FLOW")[1]
    text, sperre = "INTELLIGENT FLOW", int(n * 0.018)
    gesamt = sum(d.textlength(z, font=f2) + sperre for z in text) - sperre
    x = n / 2 - gesamt / 2
    for z in text:
        d.text((x, y2), z, font=f2, fill=TEXT_GRAU)
        x += d.textlength(z, font=f2) + sperre

    return bild.resize((breite, round(hoehe / SS)), Image.LANCZOS)


if __name__ == "__main__":
    zeichne_zeichen(512).save(WURZEL / "icon.png")
    zeichne_logo(800).save(WURZEL / "logo.png")
    print(f"geschrieben: {WURZEL / 'icon.png'}, {WURZEL / 'logo.png'}")
