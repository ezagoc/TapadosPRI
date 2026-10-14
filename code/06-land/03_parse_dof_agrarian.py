"""
Parse the agrarian notes of the Diario Oficial (harvested by 02_harvest_dof_agrarian.py) into clean tables.

Inputs
  config.DOF_SIDOF_INDEX_DIR     daily index (titles) of every DOF note, 1916-1992 as far as harvested
  config.DOF_SIDOF_FULLTEXT_DIR  full text (slimmed HTML) of the agrarian notes, 1975-1992

Outputs (config.LAND_REFORM_DIR)
  dof_agrarian_index_1916_1992.csv   one row per agrarian DOF note in the index, any year: date, issuing body,
                                     title, document type, action type, poblado, municipality, state (all
                                     parsed from the title). This is what links names to Sanderson 1916-1976.
  dof_agrarian_notes_1975_1992.csv   one row per agrarian DOF note 1975-1992: the title fields plus, from the
                                     full text, the signing date and signing president, grant/denial,
                                     hectares (total and by land class when printed), beneficiaries,
                                     expropriation beneficiary and indemnity, and parse diagnostics.

Parsing rules (all on accent-stripped lower-case text; see the functions below)
  title    document type = first word(s) (resolucion, decreto, acuerdo, solicitud, aviso, iniciacion, ...; 1917-20s
           titles that open with "Dotacion/Restitucion de ejidos" count as resoluciones); action type by keyword
           priority (inconformidad > nulidad > expropiacion > privacion > nueva adjudicacion > perdida /
           reconocimiento de derechos > NCPE > restitucion > ampliacion > accesion > dotacion > bienes comunales
           > incorporacion > zona urbana > division/fusion/permuta > inafectabilidad > terrenos nacionales);
           poblado after "poblado (denominado)", "nucleo de poblacion", "ejido (de/denominado)", "pueblo",
           "comunidad", "vecinos de", "tribu" (searched before the municipality phrase, then after it); aliases
           from "(antes|hoy X)"; NCPE name after "que se denominara"; municipality after "Municipio /
           Municipalidad / Mpio. / Delegacion (de)" or, in 1917-60s titles, ", en X, <state>"; "del mismo
           nombre" = the poblado; state = the LAST state name or abbreviation (Pue., Chis., S. L. P., Tam.,
           B. Cfa. Sur, Estado de Veracruz, ...).
  heading  the body opens with its own printed heading; if it names another action than the index title
           (SIDOF mix-up or abridged title) the heading's fields are used and `title_body_mismatch` = 1.
  signing  the last "Dada/Dado en ..." clause (else the last date in the closing 1,500 characters): day and year
           in words or digits, month name, common typos tolerated; the president is the known surname in the
           400 characters after the date. `signer_body` = president / tribunal_agrario / comision_agraria_mixta
           / secretaria_reforma_agraria from the closing lines; only presidential acts get a president.
  operative section = text after the last "resuelve" / "siguiente decreto|acuerdo" before the signature
           (OCR digits repaired: "2, 500-00-00", "2,5o0").
  hectares the first amount after the first concession verb (se concede / dota / amplia / restituye / reconoce /
           confirma / incorpora / crea / expropia). Amounts are printed as ha-a-ca ("104-63-63 Has." = 104.6363
           ha) or as decimals, and each is checked against the amount written in words that follows it; when
           they disagree the re-reading of the digits that matches the words is used (hyphen-less 1979-83
           texts: "4868000 has." = 486-80-00; dot thousands "65.239 has."), else the digits are kept and flagged
           (`ha_parse_flag`). Land classes (riego, temporal, agostadero, monte, desertico) from the words right
           after each amount ("temporal y agostadero" = mixed); unclassified remainder = indefinido.
  grant    1 if a concession verb and hectares > 0 (or water granted); 0 if the operative section denies
           ("se niega", "no ha lugar", "improcedente") with no concession; else empty.
  beneficiaries the first "<n> capacitados / campesinos / beneficiados / comuneros / ejidatarios / jefes de
           familia" in the operative section, else the census count ("arrojo un total de <n> ...").
  expropriations: beneficiary agency after "a favor de"; indemnity = first peso amount after "indemnizacion".

Run:  python -I code/06-land/03_parse_dof_agrarian.py
"""
from __future__ import annotations

import collections
import datetime as dt
import re
import sys
from pathlib import Path

import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (  # noqa: E402
    DOF_SIDOF_INDEX_DIR, DOF_SIDOF_FULLTEXT_DIR, DOF_AGRARIAN_INDEX_CSV, DOF_AGRARIAN_NOTES_CSV,
)
from dof_agrarian_utils import (  # noqa: E402
    fulltext_files, html_to_text, is_agrarian, iter_index_notes, iter_jsonl, norm, priority_class,
)

# ----------------------------------------------------------------------------------------------- states
STATE_NAMES = {
    "01": "Aguascalientes", "02": "Baja California", "03": "Baja California Sur", "04": "Campeche",
    "05": "Coahuila", "06": "Colima", "07": "Chiapas", "08": "Chihuahua", "09": "Distrito Federal",
    "10": "Durango", "11": "Guanajuato", "12": "Guerrero", "13": "Hidalgo", "14": "Jalisco",
    "15": "Mexico", "16": "Michoacan", "17": "Morelos", "18": "Nayarit", "19": "Nuevo Leon",
    "20": "Oaxaca", "21": "Puebla", "22": "Queretaro", "23": "Quintana Roo", "24": "San Luis Potosi",
    "25": "Sinaloa", "26": "Sonora", "27": "Tabasco", "28": "Tamaulipas", "29": "Tlaxcala",
    "30": "Veracruz", "31": "Yucatan", "32": "Zacatecas",
}
# regex (on normalised text) -> state code. Abbreviations need a following dot/comma/end to avoid words.
_E = r"(?=[\s\.,;:\)]|$)"
STATE_PATTERNS = [
    (r"\baguascalientes\b|\bags\b\.?", "01"),
    (r"\bbaja california sur\b|\bb\.?\s?c\.?\s?s\b\.?|\bbaja california del sur\b|\bterritorio sur de la baja california\b", "03"),
    (r"\bbaja california(?! sur)(?: norte| del norte)?\b|\bb\.?\s?c\.?\s?n\b\.?|\bb\.\s?c\.(?!\s?s)", "02"),
    (r"\bcampeche\b|\bcamp\b\.|\bcam\b\.", "04"),
    (r"\bcoahuila\b|\bcoah\b\.?", "05"),
    (r"\bcolima\b|\bcol\b\.", "06"),
    (r"\bchiapas\b|\bchis\b\.?", "07"),
    (r"\bchihuahua\b|\bchih\b\.?", "08"),
    (r"\bdistrito federal\b|\bd\.\s?f\b\.?" + _E, "09"),
    (r"\bdurango\b|\bdgo\b\.?", "10"),
    (r"\bguanajuato\b|\bgto\b\.?", "11"),
    (r"\bguerrero\b|\bgro\b\.?", "12"),
    (r"\bestado de hidalgo\b|\bhgo\b\.?|\bhidalgo\s*\.?\s*$", "13"),
    (r"\bjalisco\b|\bjal\b\.?", "14"),
    (r"\bestado de mexico\b|\bedo\.? de mex\b\.?|\bedo\.? mex\b\.?|\bmex\b\.|\bmexico\s*\.?\s*$|\bmex\s*$", "15"),
    (r"\bmichoacan\b|\bmich\b\.?", "16"),
    (r"\bestado de morelos\b|\bmor\b\.?" + _E + r"|\bmorelos\s*\.?\s*$", "17"),
    (r"\bnayarit\b|\bnay\b\.?", "18"),
    (r"\bnuevo leon\b|\bn\.\s?l\b\.?" + _E, "19"),
    (r"\boaxaca\b|\boax\b\.?", "20"),
    (r"\bestado de puebla\b|\bpue\b\.?|\bpuebla\s*\.?\s*$", "21"),
    (r"\bqueretaro\b|\bqro\b\.?(?!\s?o)", "22"),
    (r"\bquintana roo\b|\bq\.\s?roo\b\.?|\bqroo\b\.?|\bq\.\s?r\b\.?", "23"),
    (r"\bsan luis potosi\b|\bs\.\s?l\.\s?p\b\.?|\bslp\b\.?", "24"),
    (r"\bsinaloa\b|\bsin\b\." + _E, "25"),
    (r"\bsonora\b|\bson\b\." + _E, "26"),
    (r"\btabasco\b|\btab\b\.?", "27"),
    (r"\btamaulipas\b|\btamps?\b\.?", "28"),
    (r"\btlaxcala\b|\btlax\b\.?", "29"),
    (r"\bveracruz\b|\bver\b\.?" + _E, "30"),
    (r"\byucatan\b|\byuc\b\.?", "31"),
    (r"\bzacatecas\b|\bzac\b\.?", "32"),
]
STATE_PATTERNS += [   # abbreviations printed without a dot at the very end, and frequent variants / typos
    (r"\bb\.?\s?cfa\.?\s?sur\b", "03"), (r"\bb\.?\s?cfa\b(?!\.?\s?sur)", "02"),
    (r"\bcamp?[\s\.]*$", "04"), (r"\bcol[\s\.]*$", "06"), (r"\bmex[\s\.]*$", "15"),
    (r"\bsin[\s\.]*$", "25"), (r"\bson[\s\.]*$", "26"), (r"\btam\b\.?", "28"), (r"\bveracuz\b", "30"),
]
STATE_PATTERNS = [(re.compile(p), c) for p, c in STATE_PATTERNS]


def find_state(t: str) -> str | None:
    """State code of the LAST state mention in a normalised title (the state closes the place phrase)."""
    t = re.sub(r"\((reg|registrad)[^)]*\)?", " ", t)
    best = None
    for rx, code in STATE_PATTERNS:
        for m in rx.finditer(t):
            key = (m.end(), m.end() - m.start())
            if best is None or key > best[0]:
                best = (key, code)
    return best[1] if best else None


# ------------------------------------------------------------------------------------ title parsing
DOC_TYPES = [
    ("fe_de_erratas", r"^(fe de erratas|fede erratas|fe de errata|aclaracion|aclaratoria)"),
    ("resolucion", r"^(resolucion|resoluciones|resolucon|resolucio|resulucion|rescolucion|resclucion|reso1ucion|resolucin)"),
    ("resolucion", r"^(dotacion|dotaciones|restitucion|ampliacion|se revoca|se confirma|se modifica)\b"),   # 1917-20s titles
    ("decreto", r"^decreto"),
    ("iniciacion", r"^(iniciacion|inicio|acuerdo de (?:la )?(?:iniciacion|reposicion|inicio)|oficio de iniciacion)"),
    ("acuerdo", r"^acuerdo"),
    ("sentencia", r"^sentencia"),
    ("declaratoria", r"^declaratoria"),
    ("solicitud", r"^(solicitud|solicitudes)"),
    ("aviso", r"^(aviso|avisos)"),
    ("notificacion", r"^(notificacion|notificaciones)"),
    ("edicto", r"^(edicto|edictos)"),
    ("convocatoria", r"^convocatoria"),
]
DOC_TYPES = [(n, re.compile(p)) for n, p in DOC_TYPES]

ACTION_RULES = [
    ("inconformidad", r"recurso de inconformidad|curso de inconformidad"),
    ("nulidad", r"nulidad de (?:los )?fraccionamientos?|procedimiento de nulidad|nulidad de actos"),
    ("expropiacion", r"expropia"),
    ("privacion_nueva_adjudicacion", r"privacion.{0,120}adjudicacion|adjudicacion.{0,80}privacion"),
    ("privacion_derechos", r"privacion|privativo"),
    ("nueva_adjudicacion", r"nuevas? adjudicaci"),
    ("cancelacion_certificados", r"cancelacion de(?:l)? certificados? de derechos"),
    ("perdida_derechos", r"perdida de (?:los )?derechos agrarios|derechos agrarios que perdio"),
    ("reconocimiento_derechos", r"reconocimiento de derechos agrarios|reconocimiento y nueva adjudicacion|"
                                r"confirmacion de derechos agrarios|reconocimiento y confirmacion de derechos"),
    ("ncpe", r"nuevo centro de poblacion|nuevos centros de poblacion|centro de poblacion ejidal|"
             r"creacion de(?:l| un)? centro de poblacion"),
    ("restitucion_aguas", r"restitucion de aguas"),
    ("restitucion", r"restitucion"),
    ("ampliacion_aguas", r"ampliacion de (dotacion de )?aguas|ampliacion de las aguas"),
    ("ampliacion", r"ampliacion"),
    ("accesion_aguas", r"accesion de aguas"),
    ("dotacion_aguas", r"dotacion de aguas|dotacion de las aguas|aguas.{0,40}dotacion"),
    ("dotacion", r"dotacion|\bejidos al\b|\bdotar\b|expediente de tierras"),
    ("bienes_comunales", r"bienes comunales|terrenos comunales|confirmacion y titulacion|titulacion de bienes"),
    ("incorporacion", r"incorporacion de tierras|incorporacion al regimen"),
    ("bienes_comunales", r"\bconfirmacion\b(?!.*derechos)"),
    ("zona_urbana", r"zona urbana|zona de urbanizacion|fundo legal"),
    ("division", r"division de(l)? ejido|division del ejido|\bdivision\b"),
    ("fusion", r"\bfusion\b"),
    ("permuta", r"\bpermuta"),
    ("segregacion", r"segregacion"),
    ("acomodo", r"\bacomodo"),
    ("inafectabilidad", r"inafectabilidad|inafectable"),
    ("terrenos_nacionales", r"propiedad nacional|terrenos? nacional|presunta propiedad|deslinde"),
    ("conflicto_limites", r"conflicto por limites|limites entre"),
    ("nulidad", r"nulidad"),
    ("colonias", r"\bcolonia\b|colonizacion"),
]
ACTION_RULES = [(n, re.compile(p)) for n, p in ACTION_RULES]

LEDGER_ACTIONS = {
    "dotacion", "ampliacion", "restitucion", "ncpe", "bienes_comunales", "dotacion_aguas", "ampliacion_aguas",
    "accesion_aguas", "restitucion_aguas", "incorporacion", "privacion_nueva_adjudicacion", "privacion_derechos",
    "reconocimiento_derechos", "perdida_derechos", "nueva_adjudicacion", "cancelacion_certificados", "expropiacion",
    "division", "fusion", "permuta", "segregacion", "acomodo", "zona_urbana",
}
LAND_GRANT_ACTIONS = {"dotacion", "ampliacion", "restitucion", "ncpe", "bienes_comunales"}


def doc_type_of(t: str) -> str:
    for name, rx in DOC_TYPES:
        if rx.search(t):
            return name
    return "other"


def action_type_of(t: str) -> str:
    for name, rx in ACTION_RULES:
        if rx.search(t):
            return name
    return "other"


_STOP = (r"(?=\s*(?:,|;|\.\s|\.$|\(|\bubicad[oa]s?\b|\bmunicipios?\b|\bmpio\b|\bmunic\b|\ben el municipio\b|"
         r"\bdel municipio\b|\bperteneciente\b|\bdel estado\b|\bestado de\b|\bedo\b|\bque se denominara\b|"
         r"\bsolicitad[oa]\b|\ba favor\b|\bdestinad|\bpara\b|\by quedara\b|\ben el estado\b|$))")
POBLADO_PATTERNS = [
    r"\bpoblados?\s+(?:de\s+)?denominad[oa]s?\s+(?:de\s+)?\"?(?P<n>.+?)\"?" + _STOP,
    r"\bnucleos?\s+de\s+poblacion\s+(?:ejidal\s+|comunal\s+)?(?:denominad[oa]\s+)?(?:de\s+)?\"?(?P<n>.+?)\"?" + _STOP,
    r"\bejidos?\s+(?:del\s+poblado\s+)?denominad[oa]\s+\"?(?P<n>.+?)\"?" + _STOP,
    r"\bpoblados?\s+(?:de\s+)?\"?(?P<n>.+?)\"?" + _STOP,
    r"\b(?:pueblo|rancheria|congregacion|comunidad|villa|hacienda|ranchos?|cuadrilla|localidad)\s+(?:de\s+|denominad[oa]\s+)?\"?(?P<n>.+?)\"?" + _STOP,
    r"\bejidos?\s+(?:de(?:l)?\s+)?\"?(?P<n>.+?)\"?" + _STOP,
    r"\bterrenos ejidales (?:de(?:l)?\s+)(?:poblado\s+)?\"?(?P<n>.+?)\"?" + _STOP,
    r"\bfraccionamiento (?:ejidal |del ejido )?de(?:l)?\s+\"?(?P<n>.+?)\"?" + _STOP,
    r"\bvecinos (?:del poblado |de(?:l)? )\"?(?P<n>.+?)\"?" + _STOP,
    r"\btribu\s+\"?(?P<n>.+?)\"?" + _STOP,
]
POBLADO_PATTERNS = [re.compile(p) for p in POBLADO_PATTERNS]
NCPE_RE = re.compile(r"que se denominar[ai]\s+\"?(?P<n>.+?)\"?" + _STOP)
MUN_RE = re.compile(
    r"\b(?:municipios?|municipalidad|mpio|munic|delegacion)\b\.?\s*,?\s*(?:de\s+|del\s+(?!mismo)|de\s+la\s+(?=\w))?"
    r"(?P<m>.+?)\s*(?=,|;|\.\s|\.$|\(|\bdel estado\b|\bestado de\b|\bedo\b|\ben el estado\b|\bdistrito\b|\bdto\b|"
    r"\bex-?distrito\b|\bantes\b|\bperteneciente\b|\bpara\b|\ba favor\b|\by quedara\b|$)")
EN_MUN_RE = re.compile(r"\ben\s+(?P<m>[a-z][^,;()]{1,50}?)\s*,(?P<tail>[^,;]{1,45})$")
GENERIC_NAMES = {"de", "del", "la", "el", "los", "las", "ejido", "ejidos", "poblado", "terrenos", "referencia", "que se trata",
                 "su ejido", "este ejido", "dicho poblado", "el mismo", "mismo nombre", ""}


ABBR_RE = re.compile(r"\b(lic|gral|ing|dr|dra|profr|profra|prof|cnel|crnel|tte|cap|sta|sto|sn|gpe|fco|ma|pdte|pte|cd|"
                     r"gob|mtro|no|num|ex|hda|rcho|cong|pob|sr|sra|srita|grl|presb|fray|fr|dn|ant)\.")
ALIAS_RE = re.compile(r"\(?\s*\b(?:antes|hoy|ahora|tambien conocido como|conocido como)\s+\"?(?P<a>[^)\",]+)\"?\)?")


def clean_place(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip(" \"'.,;:-")
    if '"' in s:                      # a closing quote ends the name ('la esperanza" y su anexo ...')
        s = s.split('"')[0]
    s = re.sub(r"^(denominad[oa]s?|de|del|el poblado|poblado)\s+", "", s)
    s = re.sub(r"\s+", " ", s).strip(" \"'.,;:-()")
    if s in GENERIC_NAMES or len(s) < 2 or len(s) > 90:
        return None
    return s


def split_alias(name: str | None) -> tuple[str | None, str | None]:
    """'guadalupe victoria (antes huixquilar)' -> ('guadalupe victoria', 'huixquilar')."""
    if not name:
        return name, None
    m = ALIAS_RE.search(name)
    if not m:
        return name, None
    main = clean_place(name[:m.start()])
    return (main or name), clean_place(m.group("a"))


def place_text(t: str) -> str:
    """Normalised title prepared for place extraction: registry numbers removed, dots after abbreviations
    and single-letter initials dropped ('lic. adolfo lopez mateos', 'othon p. blanco')."""
    t = re.sub(r"\((reg|registrad)[^)]*\)?", " ", t)
    t = ABBR_RE.sub(lambda m: m.group(1), t)
    t = re.sub(r"\b([a-z])\.(?=\s*[a-z])", r"\1", t)
    return re.sub(r"\s+", " ", t)


def parse_title(title: str) -> dict:
    t = norm(title)
    t = t.replace("“", '"').replace("”", '"')
    out = {"title_norm": t, "doc_type": doc_type_of(t), "action_type": action_type_of(t)}
    m = re.search(r"\(?reg(?:istrad[oa])?\.?\s*(?:con el (?:numero|no\.?)\s*)?-?\s*(\d+)", t)
    out["dof_reg_no"] = m.group(1) if m else None
    tp = place_text(t)
    mm = MUN_RE.search(tp)
    mun = clean_place(mm.group("m")) if mm else None
    same_name = bool(mm and re.search(r"(mismo|igual|su) nombre", tp[mm.start():mm.start() + 45]))
    pob, pob_alias = None, None
    # the poblado is looked for before the municipality phrase, then after it (never inside it)
    for zone in ([tp[:mm.start()], tp[mm.end():]] if mm else [tp]):
        for rx in POBLADO_PATTERNS:
            pm = rx.search(zone)
            if pm and clean_place(pm.group("n")):
                pob = clean_place(pm.group("n"))
                am = re.match(r"\s*\"?\s*,?\s*\(?\s*(?:antes|hoy|ahora)\s+\"?(?P<a>[^),;\"]+)", zone[pm.end():pm.end() + 90])
                if am:
                    pob_alias = clean_place(am.group("a"))
                break
        if pob:
            break
    ncpe = None
    nm = NCPE_RE.search(tp)
    if nm:
        ncpe = clean_place(nm.group("n"))
    pob, alias2 = split_alias(pob)
    pob_alias = pob_alias or alias2
    ncpe, _ = split_alias(ncpe)
    if mun:
        mun, _ = split_alias(mun)
    if same_name:
        mun = ncpe or pob
    if not mun:   # 1930s-60s titles: "... al poblado La Siria, en Ocosingo, Chis."
        em = EN_MUN_RE.search(tp.strip(" ."))
        if em and find_state(em.group("tail")) and not re.match(r"(el|la|los|las) (ejido|poblado|colonia|predio)|favor", em.group("m")):
            mun = clean_place(em.group("m"))
    out["poblado"] = pob
    out["poblado_alias"] = pob_alias
    out["ncpe_name"] = ncpe
    out["municipality"] = mun
    out["state_code"] = find_state(re.sub(r"\((reg|registrad)[^)]*\)?", " ", t))
    return out


# ------------------------------------------------------------------------------------ number words
NUM_WORDS = {
    "cero": 0, "un": 1, "uno": 1, "una": 1, "primero": 1, "primer": 1, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13,
    "catorce": 14, "quince": 15, "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19,
    "veinte": 20, "veintiun": 21, "veintiuno": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24,
    "veinticinco": 25, "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
    "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90,
    "cien": 100, "ciento": 100, "doscientos": 200, "trescientos": 300, "cuatrocientos": 400, "quinientos": 500,
    "seiscientos": 600, "setecientos": 700, "ochocientos": 800, "novecientos": 900, "mil": 1000, "mi": 1000,
    "doscientas": 200, "trescientas": 300, "cuatrocientas": 400, "quinientas": 500, "seiscientas": 600,
    "setecientas": 700, "ochocientas": 800, "novecientas": 900, "veintiuna": 21, "treintaiun": 31,
}
MONTHS = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
          "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}


def words_to_int(s: str) -> int | None:
    """Spanish number words -> int ('mil novecientos setenta y cuatro', 'quinientas diecinueve mil')."""
    s = s.strip()
    if re.fullmatch(r"\d{1,4}", s):
        return int(s)
    total, cur, ok = 0, 0, False
    for w in re.findall(r"[a-z]+", s):
        if w in ("y", "de", "del", "dia", "dias", "los", "el", "ano"):
            continue
        if w not in NUM_WORDS:
            return None
        v = NUM_WORDS[w]
        if v == 1000:
            total += (cur or 1) * 1000
            cur = 0
        else:
            cur += v
        ok = True
    return total + cur if ok else None


HECT_WORD_RE = re.compile(r"\bh[a-z]{3}areas?\b")
NUMWORD_RUN_RE = re.compile(r"((?:\b(?:" + "|".join(sorted(set(list(NUM_WORDS) + ["y"]), key=len, reverse=True)) +
                            r")\b[\s,]*)+)$")


def word_amount(window: str) -> float | None:
    """Hectares written in words right after a printed amount: '(cuatrocientas ochenta y seis hectareas,
    ochenta areas)' -> 486.80. None if not found or not parsable."""
    m = HECT_WORD_RE.search(window[:260])
    if not m:
        return None
    run = NUMWORD_RUN_RE.search(window[:m.start()].rstrip(" ,("))
    if not run:
        return None
    ha = words_to_int(run.group(1))
    if ha is None:
        return None
    rest = window[m.end(): m.end() + 120]
    val = float(ha)
    am = re.match(r"[\s,]*((?:[a-z]+[\s,]*){1,4}?)areas?\b", rest)
    if am:
        a = words_to_int(am.group(1))
        if a is not None and a < 100:
            val += a / 100
            rest = rest[am.end():]
            cm = re.match(r"[\s,y]*((?:[a-z]+[\s,]*){1,4}?)centiareas?\b", rest)
            if cm:
                c = words_to_int(cm.group(1))
                if c is not None and c < 100:
                    val += c / 10000
    return val


SIGN_RE = re.compile(r"\bdad[oa]s?\s+en\b")
DATE_RE = re.compile(
    r"\bal?\s+(?:los?\s+|las?\s+|el\s+)?(?P<day>(?:[a-z]+\s+){0,3}?[a-z]+|\d{1,2})\.?\s+(?:\(\d+\)\s+)?(?:dias?\s+)?(?:del?\s+mes\s+)?de(?:l)?\s+"
    r"(?P<month>enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)s?"
    r"\s+(?:del?\s+)?(?:ano\s+(?:de\s+)?)?(?P<year>mil?\s+novecientos(?:\s+[a-z]+){0,3}?|\d{4}|\d\.\d{3})"
    r"(?=\s*[\.\-,;:–—]|\s+el\s|\s+-|\s*$)")
# (surname key in normalised text, canonical name, term start, term end)
PRESIDENTS = [
    ("carranza", "Venustiano Carranza", "1915-01-06", "1920-05-21"),
    ("de la huerta", "Adolfo de la Huerta", "1920-06-01", "1920-11-30"),
    ("obregon", "Alvaro Obregon", "1920-12-01", "1924-11-30"),
    ("calles", "Plutarco Elias Calles", "1924-12-01", "1928-11-30"),
    ("portes gil", "Emilio Portes Gil", "1928-12-01", "1930-02-04"),
    ("ortiz rubio", "Pascual Ortiz Rubio", "1930-02-05", "1932-09-03"),
    ("rodriguez", "Abelardo L. Rodriguez", "1932-09-04", "1934-11-30"),
    ("cardenas", "Lazaro Cardenas", "1934-12-01", "1940-11-30"),
    ("avila camacho", "Manuel Avila Camacho", "1940-12-01", "1946-11-30"),
    ("aleman", "Miguel Aleman Valdes", "1946-12-01", "1952-11-30"),
    ("ruiz cortines", "Adolfo Ruiz Cortines", "1952-12-01", "1958-11-30"),
    ("lopez mateos", "Adolfo Lopez Mateos", "1958-12-01", "1964-11-30"),
    ("diaz ordaz", "Gustavo Diaz Ordaz", "1964-12-01", "1970-11-30"),
    ("echeverria", "Luis Echeverria Alvarez", "1970-12-01", "1976-11-30"),
    ("lopez portillo", "Jose Lopez Portillo", "1976-12-01", "1982-11-30"),
    ("de la madrid", "Miguel de la Madrid Hurtado", "1982-12-01", "1988-11-30"),
    ("salinas", "Carlos Salinas de Gortari", "1988-12-01", "1994-11-30"),
    ("zedillo", "Ernesto Zedillo Ponce de Leon", "1994-12-01", "2000-11-30"),
]
PRES_RE = re.compile(r"(lopez portillo|de la madrid|madrid h|salinas de gortari|salinas|echeverria|diaz ordaz|"
                     r"lopez mateos|ruiz cortines|aleman|avila camacho|cardenas|zedillo)")
PRES_KEY = {"madrid h": "de la madrid", "salinas de gortari": "salinas"}
PRES_CANON = {k: name for k, name, _, _ in PRESIDENTS}


def president_on(d: dt.date | None) -> str | None:
    if d is None or pd.isna(d):
        return None
    for _, name, a, b in PRESIDENTS:
        if dt.date.fromisoformat(a) <= d <= dt.date.fromisoformat(b):
            return name
    return None


def signer_body_of(tail: str, president_found: bool) -> str | None:
    """Who signed, from the last ~1,500 characters of the text."""
    if president_found or "presidente constitucional de los estados unidos mexicanos" in tail:
        return "president"
    if "magistrados" in tail or "tribunal superior agrario" in tail or "tribunal unitario agrario" in tail:
        return "tribunal_agrario"
    if "comision agraria mixta" in tail[-900:]:
        return "comision_agraria_mixta"
    if re.search(r"(?:el|la) secretari[oa] de la reforma agraria", tail[-500:]) or "jefe del departamento" in tail[-500:]:
        return "secretaria_reforma_agraria"
    return None


def parse_signing(t: str) -> dict:
    """Signing clause: last 'Dada en ...' with a parsable date (else the last date in the closing 1,500
    characters, e.g. tribunal sentences); the president is the known surname in the 400 characters after the
    date. `signer_body` says whether the President, a tribunal, a Comision Agraria Mixta or the SRA signed."""
    out = {"signing_date": None, "signing_place_found": 0, "president_signing_text": None, "signing_text": None}
    tail = t[-1500:]
    dm, win = None, None
    for m in reversed(list(SIGN_RE.finditer(t))):
        win = t[m.start(): m.start() + 600]
        dm = DATE_RE.search(win)
        if dm:
            out["signing_place_found"] = 1
            break
    if not dm:
        cands = list(DATE_RE.finditer(tail))
        if cands:
            dm, win = cands[-1], tail
    if dm:
        day = words_to_int(dm.group("day"))
        yr = words_to_int(dm.group("year").replace(".", ""))
        mon = MONTHS[dm.group("month")]
        try:
            if day and yr and 1900 < yr < 2001:
                out["signing_date"] = dt.date(yr, mon, day)
        except ValueError:
            pass
        after = win[dm.end(): dm.end() + 400]
        pm = PRES_RE.search(after)
        if pm and "magistrados" not in after:
            key = PRES_KEY.get(pm.group(1), pm.group(1))
            out["president_signing_text"] = PRES_CANON.get(key)
        out["signing_text"] = win[max(0, dm.start() - 120): dm.end() + 160].strip()
    out["signer_body"] = signer_body_of(tail, out["president_signing_text"] is not None)
    return out


# ----------------------------------------------------------------------------------- operative text
OPER_RE = re.compile(r"\b(?:se\s+)?r\s?e\s?s\s?u\s?e\s?l\s?v\s?e\b|\bsiguiente\s+(?:decreto|acuerdo|resolucion)\b|"
                     r"\bhe tenido a bien (?:dictar|expedir)\b")
CONCESSION_RE = re.compile(
    r"\bse\s+(?:le\s+|les\s+)?(?:concede|conceden|dota|amplia|restituye|restituyen|reconocer?|confirma|confirman|crea|"
    r"incorpora|incorporan|expropia|expropian|titula|declara procedente|otorga)\b|\bse\s+dota\b|\bpor concepto de\b")
DENIAL_RE = re.compile(r"\bse\s+niega\b|\bno\s+ha\s+lugar\b|\bse\s+declara\s+improcedente\b|\bes\s+improcedente\b|"
                       r"\bimprocedente\s+la\b|\bse\s+niegan\b|\bse\s+desecha\b|\bno\s+procede\b")
HA_HYPHEN = re.compile(r"(?<![\d\-])(?P<n>\d{1,3}(?:[,\.]\d{3})+|\d+)\s?-\s?(?P<a>\d{1,2})\s?-\s?(?P<ca>\d{1,2}|''|\"|o|oo)(?:[\.,](?P<f>\d+))?"
                       r"(?:\s*(?:\([^)]{0,200}\))?\s*,?\s*)(?:has?\b\.?|hs\b\.?|hect|hras?\b|\(\s*[a-z ,]*hectarea)")
# "7,619,20,00 has." -- commas printed instead of hyphens (only accepted right before the unit)
HA_COMMA = re.compile(r"(?<![\d\-,])(?P<n>\d{1,3}(?:,\d{3})*),(?P<a>\d{2}),(?P<ca>\d{2})(?P<f>)\s*(?:has?\b|hs\b|hect)")
HA_DEC = re.compile(r"(?<![\d\-,\.])(?P<n>\d{1,3},\d{4,}(?:\.\d+)?|\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+|\d+)\s*(?:\([^)]{0,200}\)\s*)?(?:has\b\.?|hs\b\.?|hectareas?\b)")
BENEF_RE = re.compile(r"(?<![\d\-\.])(?P<n>\d{1,3}(?:,\d{3})+|\d{1,5})\s+(?:\([a-z ]+\)\s+)?(?:campesinos?|capacitados?|beneficiados?|"
                      r"beneficiarios?|ejidatarios?|comuneros?|jefes de familia|individuos|solicitantes)\b")
CENSUS_RE = re.compile(r"arrojo\s+(?:un\s+total\s+de\s+|como\s+resultado\s+)?(?P<n>\d{1,3}(?:,\d{3})+|\d{1,5})\s+"
                       r"(?:campesinos|capacitados|individuos|jefes|comuneros|habitantes)")
CLASS_RULES = [
    ("riego", r"\briego\b"),
    ("temporal", r"\btemporal\b|\bhumedad\b|\blaborable"),
    ("agostadero", r"\bagostadero|\bpastal|\bpastizal"),
    ("monte", r"\bmonte\b|\bbosque|\bforestal|\bcerril|\bmontuos"),
    ("desertico", r"\bdesert|\barid[oa]s?\b"),
]
CLASS_RULES = [(n, re.compile(p)) for n, p in CLASS_RULES]
CLASSES = [n for n, _ in CLASS_RULES] + ["indefinido"]
NEXT_ITEM_RE = re.compile(r"\b(?:tercero|cuarto|quinto|sexto)\s*\.?\s*-|la anterior superficie|superficie que se distribuira|"
                          r"\bexpidanse\b|\bexpidase\b")


def fix_digits(t: str) -> str:
    """Repair OCR in printed amounts: '2, 500-00-00' -> '2,500-00-00'; '2,5o0-00-00' -> '2,500-00-00'."""
    t = re.sub(r"(\d),\s+(\d{3})(?=[-\d])", r"\1,\2", t)
    return re.sub(r"(?<=[\d,])[o](?=\d)|(?<=\d)[o](?=[\d,\-])", "0", t)


def to_num(s: str) -> float:
    return float(s.replace(",", "").replace(" ", "")) if s else 0.0


def ha_value(m) -> float:
    if "a" in m.groupdict() and m.groupdict().get("a") is not None:
        n = m.group("n")
        n = re.sub(r"[,\.](?=\d{3}\b)", "", n)
        ca = m.group("ca")
        ca = int(ca) if ca and ca.isdigit() else 0      # OCR '' / o in the centiare slot = 00
        v = float(n) + int(m.group("a")) / 100 + ca / 10000
        if m.group("f"):
            v += float("0." + m.group("f")) / 10000
        return v
    return to_num(m.group("n"))


def hyphenless(numtxt: str) -> float | None:
    """Reading of an amount whose ha-a-ca hyphens were lost in the electronic text (1979-83):
    '4868000' -> 486.80, '2,6728304.5' -> 2672.8304(5)."""
    whole, _, frac = numtxt.partition(".")
    digits = re.sub(r"\D", "", whole)
    if len(digits) < 5:
        return None
    v = int(digits[:-4]) + int(digits[-4:-2]) / 100 + int(digits[-2:]) / 10000
    if frac.isdigit():
        v += float("0." + frac) / 10000
    return v


AMOUNT_FLAGS: list = []   # parse flags of the last amounts_in call (diagnostics)


def amounts_in(s: str) -> list[tuple[int, int, float]]:
    """(start, end, hectares) of every printed area in s: hyphen form (ha-a-ca), comma form, then plain numbers.
    Each amount is checked against the amount written out in words right after it ("(seiscientas quince
    hectareas)"). When they disagree, the re-reading of the digits that matches the words within 2% is used:
    hyphen-less ha-a-ca ("4868000 has." = 486-80-00, 1979-83 texts), a dot used as thousands separator ("65.239
    has." = 65,239), or the integer part; if none matches, the digits are kept and flagged. Without words, a
    plain number of 6+ digits (no thousands commas) is read as hyphen-less."""
    AMOUNT_FLAGS.clear()
    found = [(m.start(), m.end(), ha_value(m), "hyphen", None) for m in HA_HYPHEN.finditer(s)]
    taken = [(a, b) for a, b, _, _, _ in found]
    for m in HA_COMMA.finditer(s):
        if not any(a <= m.start() < b or a < m.end() <= b for a, b in taken):
            found.append((m.start(), m.end(), ha_value(m), "comma", None))
            taken.append((m.start(), m.end()))
    for m in HA_DEC.finditer(s):
        if any(a <= m.start() < b or a < m.end() <= b for a, b in taken):
            continue
        found.append((m.start(), m.end(), to_num(m.group("n")), "decimal", m.group("n")))
    out = []
    for a, b, v, kind, numtxt in sorted(found):
        flag = kind
        w = word_amount(s[a: b + 260])
        if w is not None and w > 0 and abs(v - w) > 0.02 * w + 0.01:
            cands = [v * 1000, float(int(v))]
            if numtxt is not None:
                alt = hyphenless(numtxt)
                if alt is not None:
                    cands.insert(0, alt)
            ok = [c for c in cands if abs(c - w) <= 0.02 * w + 0.01]
            if ok:   # the hyphen-less reading keeps the printed fractions; otherwise take the words (with areas)
                v = ok[0] if (numtxt is not None and ok[0] == hyphenless(numtxt)) else w
                flag = kind + "_corrected_by_words"
            else:
                flag = kind + "_words_disagree"
        elif w is None and numtxt is not None and re.fullmatch(r"\d{6,}|\d{1,3},\d{4,}", numtxt.partition(".")[0]):
            alt = hyphenless(numtxt)
            if alt is not None:
                v, flag = alt, "hyphenless_assumed"
        out.append((a, b, v))
        AMOUNT_FLAGS.append(flag)
    return out


def classify_window(w: str) -> list[str]:
    """Land class named right after an amount. Several classes joined by 'y' / ',' ("de temporal y
    agostadero") = mixed -> []; otherwise the first one ("monte alto con proporciones laborables" -> monte)."""
    w = re.sub(r"\([^)]{0,200}\)", " ", w)
    hits = sorted((m.start(), m.end(), n) for n, rx in CLASS_RULES for m in [rx.search(w)] if m)
    if not hits:
        return []
    distinct = []
    for a, b, n in hits:
        if n not in [d[2] for d in distinct]:
            distinct.append((a, b, n))
    if len(distinct) > 1:
        between = w[distinct[0][1]:distinct[1][0]]
        # mixed only with an explicit connector: "temporal y agostadero", "riego, temporal"; adjacent words
        # ("agostadero cerril", "agostadero arido") describe one class
        if re.fullmatch(r"\s*(?:,\s*)?(?:y|e|o)\s+(?:de\s+|terrenos?\s+de\s+)?|\s*,\s*(?:de\s+)?", between):
            return []
    return [distinct[0][2]]


def parse_body(text: str, action: str) -> dict:
    t = norm(text)
    out = parse_signing(t)
    out["body_action_type"] = action_type_of(t[:400])
    sig = list(SIGN_RE.finditer(t))
    end = sig[-1].start() if sig else len(t)
    opers = [m for m in OPER_RE.finditer(t, 0, end)]
    oper_start = opers[-1].end() if opers else None
    if oper_start is None:   # fall back to the last "primero.-" in the second half
        firsts = [m for m in re.finditer(r"\bprimero\s*\.?\s*-", t[:end]) if m.start() > end * 0.4]
        oper_start = firsts[0].start() if firsts else int(end * 0.6)
    op = fix_digits(t[oper_start:end])
    out["operative_found"] = int(bool(opers))
    out["text_chars"] = len(t)
    conc = CONCESSION_RE.search(op)
    deny = DENIAL_RE.search(op)
    out["concession_verb"] = conc.group(0) if conc else None
    out["denial_phrase"] = deny.group(0) if deny else None
    # ---- hectares
    ha_total = None
    out["ha_parse_flag"] = None
    classes = {c: None for c in CLASSES}
    if conc:
        seg_end = NEXT_ITEM_RE.search(op, conc.end())
        seg = op[conc.start(): (seg_end.start() if seg_end else min(len(op), conc.start() + 3000))]
        if not amounts_in(seg):   # the amount can follow the concession sentence (e.g. in a list)
            seg = op[conc.start(): conc.start() + 3000]
        am = amounts_in(seg)
        out["ha_parse_flag"] = AMOUNT_FLAGS[0] if am else None
        if am:
            ha_total = am[0][2]
            cls_sum = collections.Counter()
            comps = []
            for i, (a, b, v) in enumerate(am[1:], start=1):
                nxt = am[i + 1][0] if i + 1 < len(am) else min(len(seg), b + 160)
                cl = classify_window(seg[b:min(nxt, b + 160)])
                if cl:
                    comps.append((cl[0], v))
            if comps and sum(v for _, v in comps) <= ha_total * 1.001 + 0.01:
                for c, v in comps:
                    cls_sum[c] += v
            else:
                nxt = am[1][0] if len(am) > 1 else min(len(seg), am[0][1] + 200)
                cl = classify_window(seg[am[0][1]:min(nxt, am[0][1] + 200)])
                if cl:
                    cls_sum[cl[0]] += ha_total
            rem = ha_total - sum(cls_sum.values())
            if rem > 0.01:
                cls_sum["indefinido"] += rem
            for c in CLASSES:
                classes[c] = round(cls_sum[c], 4) if ha_total is not None else None
    out["hectares_total"] = round(ha_total, 4) if ha_total is not None else None
    for c in CLASSES:
        out[f"ha_{c}"] = classes[c]
    # ---- water
    wm = re.search(r"(?P<n>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(?:m3|metros cubicos|m\.\s?3)", op)
    out["water_volume_m3"] = to_num(wm.group("n")) if wm else None
    lps = re.search(r"(?P<n>\d+(?:\.\d+)?)\s*(?:litros por segundo|lts?\.?\s*(?:por|x)\s*seg|l\.p\.s)", op)
    out["water_lps"] = to_num(lps.group("n")) if lps else None
    # ---- grant / denial
    water = action in ("dotacion_aguas", "ampliacion_aguas", "accesion_aguas", "restitucion_aguas")
    if conc and ((ha_total or 0) > 0 or (water and (out["water_volume_m3"] or out["water_lps"]))):
        grant = 1
    elif deny and not ((ha_total or 0) > 0):
        grant = 0
    else:
        grant = None
    out["grant"] = grant
    # ---- beneficiaries
    bm = BENEF_RE.search(op)
    if bm:
        out["beneficiaries"], out["beneficiaries_source"] = int(bm.group("n").replace(",", "")), "operative"
    else:
        cm = list(CENSUS_RE.finditer(t[:end]))
        if cm:
            out["beneficiaries"], out["beneficiaries_source"] = int(cm[-1].group("n").replace(",", "")), "census"
        else:
            out["beneficiaries"], out["beneficiaries_source"] = None, None
    # ---- expropriation details
    if action == "expropiacion":
        fm = re.search(r"\ba favor (?:de(?:l)?\s+)?(?:la\s+|el\s+|los\s+)?(?P<o>[a-z ,\.]+?)(?=,|\.\s|\bpara\b(?! la regularizacion)|\bque\b|\bubicad|\bdel ejido|\ben el\b|$)", op)
        out["expropriation_beneficiary"] = fm.group("o").strip()[:120] if fm else None
        im = re.search(r"indemniza[a-z]*[^$]{0,400}?\$\s?(?P<n>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)", op)
        out["indemnity_pesos"] = to_num(im.group("n")) if im else None
    else:
        out["expropriation_beneficiary"] = None
        out["indemnity_pesos"] = None
    return out


# ------------------------------------------------------------------------------------------- driver
def build_index_table() -> pd.DataFrame:
    rows = []
    for d, ed, n in iter_index_notes(DOF_SIDOF_INDEX_DIR):
        if not is_agrarian(n):
            continue
        title = n.get("titulo") or ""
        p = parse_title(title)
        rows.append({
            "codNota": int(n["codNota"]), "dof_date": d.isoformat(), "dof_year": d.year, "edition": ed,
            "issuing_body": n.get("codOrgaDos"), "title": re.sub(r"\s+", " ", title).strip(),
            "doc_type": p["doc_type"], "action_type": p["action_type"], "poblado": p["poblado"],
            "poblado_alias": p["poblado_alias"], "ncpe_name": p["ncpe_name"], "municipality": p["municipality"], "state_code": p["state_code"],
            "state_name": STATE_NAMES.get(p["state_code"]), "dof_reg_no": p["dof_reg_no"],
            "priority_class": priority_class(title), "has_html": int(n.get("existeHtml") == "S"),
            "dof_page": n.get("pagina"),
        })
    df = pd.DataFrame(rows).drop_duplicates("codNota").sort_values(["dof_date", "codNota"]).reset_index(drop=True)
    df["in_ledger_scope"] = (df["doc_type"].isin(["resolucion", "decreto", "acuerdo", "sentencia"])
                             & df["action_type"].isin(LEDGER_ACTIONS)).astype(int)
    return df


def build_notes_table(idx: pd.DataFrame) -> pd.DataFrame:
    full = {}
    for fn in fulltext_files(DOF_SIDOF_FULLTEXT_DIR):
        for rec in iter_jsonl(fn):
            if rec.get("codNota") is not None:
                full[int(rec["codNota"])] = rec.get("html") or ""
    sub = idx[(idx.dof_year >= 1975) & (idx.dof_year <= 1992)].copy()
    recs = []
    for r in sub.itertuples(index=False):
        h = full.get(r.codNota)
        base = {"codNota": r.codNota, "has_fulltext": int(bool(h))}
        if h:
            txt = html_to_text(h)
            # the body opens with its own printed heading (= the title). In ~1% of notes it names another
            # action or poblado than the index title (SIDOF attached the wrong text, or the index title is
            # abridged): then the body heading's fields are used and the note is flagged.
            nt = norm(txt)
            cut = nt.find("al margen")
            heading = nt[: cut if 40 < cut < 700 else 500]
            hp = parse_title(heading)
            mismatch = (hp["action_type"] != r.action_type and hp["action_type"] != "other")
            base["title_body_mismatch"] = int(mismatch)
            action = hp["action_type"] if mismatch else r.action_type
            if mismatch:
                base.update({"action_type_title": r.action_type, "action_type": action, "doc_type": hp["doc_type"],
                             "poblado": hp["poblado"], "poblado_alias": hp["poblado_alias"],
                             "ncpe_name": hp["ncpe_name"], "municipality": hp["municipality"],
                             "state_code": hp["state_code"] or r.state_code})
            base.update(parse_body(txt, action))
        recs.append(base)
    body = pd.DataFrame(recs)
    over = [c for c in ["action_type", "doc_type", "poblado", "poblado_alias", "ncpe_name", "municipality", "state_code"]
            if c in body.columns]
    notes = sub.merge(body, on="codNota", how="left", suffixes=("", "_body"))
    for c in over:
        if c + "_body" in notes.columns:
            m = notes["title_body_mismatch"].fillna(0).astype(int) == 1
            notes[c] = notes[c].astype(object)
            notes.loc[m, c] = notes.loc[m, c + "_body"].astype(object).where(notes.loc[m, c + "_body"].notna(), None)
            notes = notes.drop(columns=c + "_body")
    notes["state_name"] = notes["state_code"].map(STATE_NAMES)
    notes["in_ledger_scope"] = (notes["doc_type"].isin(["resolucion", "decreto", "acuerdo", "sentencia"])
                                & notes["action_type"].isin(LEDGER_ACTIONS)).astype(int)
    notes["signing_date"] = pd.to_datetime(notes["signing_date"], errors="coerce").dt.date
    dof = pd.to_datetime(notes["dof_date"]).dt.date
    notes["signing_lag_days"] = [(a - b).days if (b is not None and not pd.isna(b)) else None for a, b in zip(dof, notes["signing_date"])]
    # a signing date after publication, or before 1915, is a parse error (decades-long lags are real: a 1938
    # Cardenas resolution was published in 1979)
    bad = notes["signing_lag_days"].notna() & ((notes["signing_lag_days"] < 0) | (notes["signing_lag_days"] > 365 * 65))
    notes.loc[bad, ["signing_date", "signing_lag_days"]] = None
    notes["president_in_office_at_signing"] = [president_on(d) for d in notes["signing_date"]]
    notes["president_in_office_at_dof"] = [president_on(d) for d in dof]
    # the President signed: name from the signature, else the president in office on the signing date.
    # Acts signed by a tribunal, a Comision Agraria Mixta or the SRA get no president.
    by_pres = notes["signer_body"] == "president"
    notes["president_signing"] = notes["president_signing_text"].where(by_pres)
    fill = by_pres & notes["president_signing"].isna()
    notes.loc[fill, "president_signing"] = notes.loc[fill, "president_in_office_at_signing"]
    notes["president_source"] = None
    notes.loc[by_pres & notes["president_signing_text"].notna(), "president_source"] = "text_name"
    notes.loc[fill & notes["president_signing"].notna(), "president_source"] = "text_signing_date"
    nonpres = notes["signer_body"].notna() & ~by_pres
    notes.loc[nonpres, "president_source"] = "not_presidential_" + notes.loc[nonpres, "signer_body"]
    notes["president_name_date_conflict"] = (
        notes["president_signing_text"].notna() & notes["president_in_office_at_signing"].notna()
        & (notes["president_signing_text"] != notes["president_in_office_at_signing"])).astype(int)
    notes["is_land_grant_action"] = notes["action_type"].isin(LAND_GRANT_ACTIONS).astype(int)
    notes = notes.drop(columns=["text_excerpt_operative"], errors="ignore")
    return notes


def main():
    idx = build_index_table()
    DOF_AGRARIAN_INDEX_CSV.parent.mkdir(parents=True, exist_ok=True)
    idx.to_csv(DOF_AGRARIAN_INDEX_CSV, index=False)
    print(f"index: {len(idx):,} agrarian notes, {idx.dof_date.min()}..{idx.dof_date.max()} -> {DOF_AGRARIAN_INDEX_CSV.name}")
    print(idx.groupby("dof_year").size().to_string())
    notes = build_notes_table(idx)
    notes.to_csv(DOF_AGRARIAN_NOTES_CSV, index=False)
    print(f"notes 1975-1992: {len(notes):,} rows, {int(notes.has_fulltext.sum()):,} with full text -> {DOF_AGRARIAN_NOTES_CSV.name}")
    scope = notes[(notes.in_ledger_scope == 1) & (notes.has_fulltext == 1)]
    print("parse yield among in-scope notes with full text (share non-missing):")
    print(scope[["signing_date", "president_signing", "hectares_total", "beneficiaries", "grant"]].notna().mean().round(3).to_string())


if __name__ == "__main__":
    main()
