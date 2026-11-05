from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Verdict:
    accepte: bool
    texte: str
    motif: str = ""


def _ok(texte: str) -> Verdict:
    return Verdict(True, texte, "")


def _non(motif: str) -> Verdict:
    return Verdict(False, "", motif)


_LEET = str.maketrans(
    {
        "0": "o",
        "1": "i",
        "3": "e",
        "4": "a",
        "5": "s",
        "7": "t",
        "8": "b",
        "@": "a",
        "$": "s",
        "!": "i",
        "|": "i",
    }
)
_INVISIBLES = re.compile(
    "[\xad\u200b-\u200f\u202a-\u202e\u2060-\u2064\u206a-\u206f\ufeff]"
)
_REPETITIONS = re.compile("(.)\\1{2,}")


def normaliser(texte: object) -> str:
    if not isinstance(texte, str):
        return ""
    propre = _INVISIBLES.sub("", texte)
    propre = unicodedata.normalize("NFKD", propre.casefold())
    propre = "".join(c for c in propre if not unicodedata.combining(c))
    propre = propre.replace("’", "'").translate(_LEET)
    return _REPETITIONS.sub("\\1\\1", propre)


_SEPARATEURS = re.compile("[^a-z0-9']+")


def _mots(normalise: str) -> list[str]:
    return [mot for mot in _SEPARATEURS.split(normalise) if mot]


def _recoller_les_lettres_isolees(mots: list[str]) -> list[str]:
    recolles: list[str] = []
    tampon: list[str] = []
    for mot in mots + [""]:
        if len(mot) == 1 and mot.isalpha():
            tampon.append(mot)
            continue
        if len(tampon) >= 3:
            recolles.append("".join(tampon))
        tampon = []
    return recolles


def formes_comparables(texte: object) -> frozenset[str]:
    mots = _mots(normaliser(texte))
    return frozenset(mots) | frozenset(_recoller_les_lettres_isolees(mots))


_INTERDITS_BRUTS = (
    "negre",
    "negresse",
    "bougnoule",
    "bicot",
    "youpin",
    "chinetoque",
    "niakoue",
    "feuj",
    "nigger",
    "nigga",
    "chink",
    "kike",
    "spic",
    "wetback",
    "pedale",
    "tapette",
    "tarlouze",
    "gouine",
    "faggot",
    "tranny",
    "shemale",
    "mongol",
    "mongolien",
    "retarded",
    "trisomique",
)


def _racine(mot: str) -> str:
    if len(mot) > 3 and mot[-1] in "sxz":
        return mot[:-1]
    return mot


TERMES_INTERDITS: frozenset[str] = frozenset(
    _racine(normaliser(terme)) for terme in _INTERDITS_BRUTS
)
_EXPRESSIONS_BRUTES = (
    "sale arabe",
    "sale noir",
    "sale juif",
    "sale race",
    "sale pd",
    "sous race",
    "sous homme",
    "sieg heil",
    "heil hitler",
    "white power",
    "gas the jews",
    "kill yourself",
    "tue toi",
    "va te pendre",
    "suicide toi",
    "va te suicider",
    "pends toi",
)
EXPRESSIONS_INTERDITES: tuple[str, ...] = tuple(
    normaliser(expression) for expression in _EXPRESSIONS_BRUTES
)
_MENACES = tuple(
    re.compile(motif)
    for motif in (
        "\\bje vais te (tuer|buter|crever|defoncer)\\b",
        "\\bje sais ou tu (habites|vis|travailles)\\b",
        "\\bon va te retrouver\\b",
        "\\bi will (kill|find) you\\b",
    )
)
_LIENS = re.compile(
    "(https?://|www\\.|\\b[a-z0-9-]{2,}\\.[a-z]{2,6}/|\\b[a-z0-9-]+\\.(?:com|fr|net|org|io|gg|tv|be|me|xyz|link|ly|co)\\b)"
)
_FUITES = tuple(
    re.compile(motif, re.IGNORECASE)
    for motif in (
        "\\[[^\\]]{4,}\\]",
        "(?m)^\\s*[-*•]\\s+\\S",
        "\\(note\\s*:",
        "⚠",
        "\\b(system|assistant|user)\\s*:",
        "\\bdonnee de capteur ephemere\\b",
        "\\bcontexte ephemere\\b",
        "\\bmessage du chat twitch\\b",
    )
)
MAX_ENTREE = 240
_INJECTIONS = tuple(
    re.compile(motif)
    for motif in (
        "\\b(ignore|oublie|efface|annule)[a-z]*\\s+(tes|les|toutes?\\s+tes|ton|the|your|all)\\b",
        "\\b(instruction|consigne|regle|prompt|systeme|system)[a-z]*\\b.{0,24}\\b(precedent|dessus|avant|previous|above|initial)[a-z]*\\b",
        "\\btu es (maintenant|desormais)\\b",
        "\\btu n'?es plus\\b",
        "\\b(you are|act as|pretend to be) (now )?an? \\b",
        "\\bnouvelle (regle|consigne|instruction)\\b",
        "\\brepete (exactement|apres moi|mot pour mot)\\b",
        "\\bdis (exactement|litteralement|mot pour mot)\\b",
        "\\bmode (developpeur|debug|dan|admin|sans filtre)\\b",
        "\\bjailbreak\\b",
        "\\b(affiche|montre|donne|revele)[a-z]*\\s+(moi\\s+)?(ton|tes|le|la|ta)\\s+(prompt|consigne|instruction|systeme|memoire|mot de passe|jeton|token)",
        "\\[/?(system|inst|assistant|user)\\]",
        "<\\|.{0,20}\\|>",
        "(?m)^\\s*#{2,}\\s",
    )
)
BOTS_CONNUS: frozenset[str] = frozenset(
    {
        "nightbot",
        "streamelements",
        "streamlabs",
        "moobot",
        "fossabot",
        "wizebot",
        "sery_bot",
        "serybot",
        "creatisbot",
        "commanderroot",
        "soundalerts",
        "kofistreambot",
        "own3d",
        "botisimo",
        "phantombot",
        "supibot",
        "streamlabs_chatbot",
    }
)


def examiner_entree(texte: object, *, auteur: object = "") -> Verdict:
    if not isinstance(texte, str):
        return _non("entree non textuelle")
    propre = _INVISIBLES.sub("", texte)
    propre = "".join(c for c in propre if unicodedata.category(c)[0] != "C")
    propre = " ".join(propre.split())
    if not propre:
        return _non("message vide")
    if len(propre) > MAX_ENTREE:
        return _non("message trop long")
    if normaliser(auteur) in BOTS_CONNUS:
        return _non("message d'un robot")
    if propre.startswith(("!", "/", ".")):
        return _non("commande de chat")
    normalise = normaliser(propre)
    if _LIENS.search(normalise):
        return _non("lien dans le message")
    if any(motif.search(normalise) for motif in _INJECTIONS):
        return _non("tentative de detournement de consigne")
    if propre.count("@") > 2:
        return _non("trop de mentions")
    if sum(1 for c in normalise if c.isalpha()) < 3:
        return _non("message sans contenu")
    mots = [mot for mot in _mots(normalise) if any(c.isalpha() for c in mot)]
    if len(mots) > 1 and len(set(mots)) == 1:
        return _non("message repete")
    if propre == propre.upper() and len(mots) <= 3 and ("?" not in propre):
        return _non("emote ou cri sans contenu")
    return _ok(propre)


MAX_SORTIE = 400
MIN_APRES_NETTOYAGE = 12
MIN_SORTIE = 2
_FIN_DE_PHRASE = re.compile("[.!?…]['\\\")»]?(?=\\s|$)")


def _couper_proprement(texte: str, maximum: int) -> str:
    if len(texte) <= maximum:
        return texte
    tete = texte[: maximum + 1]
    coupes = [m.end() for m in _FIN_DE_PHRASE.finditer(tete)]
    if coupes and coupes[-1] >= MIN_APRES_NETTOYAGE:
        return texte[: coupes[-1]].rstrip()
    espace = tete.rfind(" ")
    if espace >= MIN_APRES_NETTOYAGE:
        return texte[:espace].rstrip() + "."
    return ""


@dataclass(frozen=True)
class Reglages:
    secrets: frozenset[str] = frozenset()
    interdits: frozenset[str] = frozenset()


REGLAGES_VIDES = Reglages()


def examiner_sortie(
    texte: object,
    *,
    reglages: Reglages = REGLAGES_VIDES,
    dernieres_repliques: object = (),
) -> Verdict:
    if not isinstance(texte, str):
        return _non("sortie non textuelle")
    propre = _INVISIBLES.sub("", texte)
    propre = "".join(c for c in propre if unicodedata.category(c)[0] != "C")
    propre = " ".join(propre.split())
    if not propre:
        return _non("replique vide")
    normalise = normaliser(propre)
    formes = formes_comparables(propre)
    recolle = "".join(_mots(normalise))
    interdits = TERMES_INTERDITS | frozenset(
        _racine(normaliser(t))
        for t in reglages.interdits
        if isinstance(t, str) and t.strip()
    )
    if {_racine(mot) for mot in formes} & interdits:
        return _non("terme interdit")
    if any(expression in normalise for expression in EXPRESSIONS_INTERDITES):
        return _non("expression interdite")
    if any(motif.search(normalise) for motif in _MENACES):
        return _non("menace")
    for secret in reglages.secrets:
        aiguille = normaliser(secret)
        if not aiguille:
            continue
        colle = "".join(_mots(aiguille))
        if not colle:
            continue
        if aiguille in formes or colle in formes or colle in recolle:
            return _non("donnee personnelle")
    if _LIENS.search(normalise):
        return _non("lien dans la replique")
    avant_nettoyage = propre
    for motif in _FUITES:
        propre = motif.sub(" ", propre)
    propre = " ".join(propre.split()).strip(" -:;,")
    if propre != avant_nettoyage and len(propre) < MIN_APRES_NETTOYAGE:
        return _non("il ne reste rien apres nettoyage")
    if len(propre) < MIN_SORTIE or not any(c.isalpha() for c in propre):
        return _non("replique sans contenu")
    if isinstance(dernieres_repliques, str):
        dernieres_repliques = (dernieres_repliques,)
    deja_dites = {
        normaliser(ancienne)
        for ancienne in dernieres_repliques or ()
        if isinstance(ancienne, str) and ancienne.strip()
    }
    if normaliser(propre) in deja_dites:
        return _non("replique deja dite recemment")
    propre = _couper_proprement(propre, MAX_SORTIE)
    if len(propre) < MIN_SORTIE:
        return _non("replique trop courte")
    return _ok(propre)


_DECOR = re.compile("^[_\\-.\\d]+|[_\\-.\\d]+$")
_COUPURES = re.compile("[_\\-.]+")


def pseudo_dicible(pseudo: object) -> str:
    if not isinstance(pseudo, str):
        return ""
    brut = pseudo.strip()
    if not brut or len(brut) > 25:
        return ""
    morceaux = [
        propre
        for propre in (_DECOR.sub("", morceau) for morceau in _COUPURES.split(brut))
        if propre.isalpha() and len(propre) > 2
    ]
    if not morceaux:
        return ""
    return " ".join(morceaux[:2]).casefold()
