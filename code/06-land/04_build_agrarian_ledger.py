"""
Build the ejido-level ledger of agrarian actions 1916-1992 and its crosswalk to the PROCEDE ejido polygons.

Inputs
  config.SANDERSON_DTA            Sanderson (1984) village-level actions 1916-1976 (via the Garfias 2018 package)
  config.DOF_AGRARIAN_INDEX_CSV   every agrarian DOF title 1917-1992 (03_parse_dof_agrarian.py)
  config.DOF_AGRARIAN_NOTES_CSV   parsed DOF agrarian notes 1975-1992 (03)
  config.EJIDOS_ATTRIBUTES_CSV    PROCEDE nucleos (2006); config.RAN_CATALOGUE_CSV RAN catalogue (2019);
  config.LAND_REFORM_DIR / localities_2000_in_ejidos.csv   census localities inside each nucleo (aliases)
  config.EHM2014_ZIP              INEGI Estadisticas Historicas de Mexico 2014, tables 9.49-9.51 (needs `pdftotext`)
  config.DOF_TEXT_CORRECTIONS_CSV corrections to 03's parse of every DOF land-grant note with text, Nov 1976-1992
                                  (06_reparse_dof_texts.py): hectares and classes 03 misread, beneficiaries and signing
                                  date / signer of multi-document texts, notes that are not land grants in print
  config.DOF_SCANNED_RESOLUTIONS_CSV  DOF land grants without SIDOF text read on the scanned editions
                                  (05_recover_scanned_resolutions.py): hectares, classes, beneficiaries, signing date,
                                  signer, method / confidence, not land grants in print

Outputs (config.LAND_REFORM_DIR)
  agrarian_actions_1916_1992.csv  the ledger: Sanderson rows 1916 - 3 Nov 1976 (one per Sanderson row; the DOF
                                  title, poblado and codNota attached when the title links to the Sanderson
                                  event, plus the signing date / signer and file history for 1973-76) + DOF rows from the day after
                                  Sanderson's last date to 31 Dec 1992 (one per resolution / decree / acuerdo in
                                  scope). `president_signing` from the text when available, else the president in
                                  office on the DOF date (flagged, with the handover-window risk quantified from
                                  the 1975-92 signing lags). DOF land-grant resolutions without a readable text count as
                                  grants (`grant_imputed`; denials were practically not published after 1975). DOF rows
                                  carry 06's corrections and 05's scanned readings (apply_dof_corrections): every value
                                  has a source column (hectares_source, beneficiaries_source, signing_source: sanderson /
                                  dof_text_03 / dof_text_reparse / dof_scan) and the pre-correction value (*_prev); notes
                                  that are not land grants in print have land_grant_printed = 0 and do not count.
  ejido_action_crosswalk.csv      action_id -> nucleo_key (PROCEDE) / ran_claveunica, score, method, accepted;
                                  best candidate kept even when rejected (never forced).
  land_reform_validation.csv      Sanderson events vs DOF index titles by year x group; link rates and link
                                  plausibility; Sanderson vs DOF full text 1973-76 (aggregate by year x state and
                                  row level); ledger vs INEGI EHM 2014 by state x presidential term (hectares,
                                  beneficiaries, resolutions, land classes); president inferred from the DOF
                                  date vs the signer in the text; parse yields; crosswalk match rates by period
                                  and state; matched nucleos' granted hectares vs their PROCEDE surface; file-history
                                  (stage) yields, lags, files inherited by the signer, and the stage hand checks; value
                                  sources by term; DOF land grants with and without hectares by year; identical amounts
                                  booked twice on one DOF date (double-count check).
  ehm2014_land_by_state_term.csv  EHM 2014 tables 9.49 (national), 9.50 (hectares) and 9.51 (beneficiaries), long.

Linking DOF titles to Sanderson (1917-1976). Sanderson has no village names. A Sanderson *event* is the set of
rows with the same DOF date, municipality and village key (e.g. privacion + nueva adjudicacion; dotacion +
segregacion). Events and DOF titles are blocked on (DOF date, state, action group); see link_dof_to_sanderson
for the four tiers (unique block; municipality printed in the title, with full-text hectares breaking ties in
1975-76; poblado found, score >= 90, in exactly one event's municipality; elimination), then a second pass with
the land-grant groups pooled.

Crosswalk to nucleos. Names are normalised (accents, N.C.P.E. prefixes, "y anexos", honorifics, abbreviations,
articles, number words, roman numerals); aliases come from parentheses / "antes" / "hoy" / "x o y" and from the
RAN catalogue names and the census localities inside each nucleo. Search in the action's municipality
(Sanderson code, or the DOF municipality name resolved to an INEGI code), else in the state. Accepted: a unique
exact core-name match, or fuzzy score >= 90 with a 5-point margin over the next nucleo (locality aliases need
95; state-wide search needs 95 and no rival >= 90); exact ties broken by nucleo type, N.C.P.E. tag, full names,
polygon. Nothing else is accepted; the best candidate is still reported.

Run:  python -I code/06-land/04_build_agrarian_ledger.py
"""
from __future__ import annotations

import collections
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pyreadstat
from rapidfuzz import fuzz, process

CODE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (  # noqa: E402
    SANDERSON_DTA, DOF_AGRARIAN_INDEX_CSV, DOF_AGRARIAN_NOTES_CSV, EJIDOS_ATTRIBUTES_CSV, RAN_CATALOGUE_CSV,
    LAND_REFORM_DIR, EHM2014_ZIP, AGRARIAN_LEDGER_CSV, EJIDO_ACTION_CROSSWALK_CSV, LAND_REFORM_VALIDATION_CSV,
    DOF_TEXT_CORRECTIONS_CSV, DOF_SCANNED_RESOLUTIONS_CSV,
)
from dof_agrarian_utils import norm  # noqa: E402

LOCALITIES_CSV = LAND_REFORM_DIR / "localities_2000_in_ejidos.csv"
EHM_LONG_CSV = LAND_REFORM_DIR / "ehm2014_land_by_state_term.csv"

STATE_NAMES = {
    "01": "Aguascalientes", "02": "Baja California", "03": "Baja California Sur", "04": "Campeche",
    "05": "Coahuila", "06": "Colima", "07": "Chiapas", "08": "Chihuahua", "09": "Distrito Federal",
    "10": "Durango", "11": "Guanajuato", "12": "Guerrero", "13": "Hidalgo", "14": "Jalisco",
    "15": "Mexico", "16": "Michoacan", "17": "Morelos", "18": "Nayarit", "19": "Nuevo Leon",
    "20": "Oaxaca", "21": "Puebla", "22": "Queretaro", "23": "Quintana Roo", "24": "San Luis Potosi",
    "25": "Sinaloa", "26": "Sonora", "27": "Tabasco", "28": "Tamaulipas", "29": "Tlaxcala",
    "30": "Veracruz", "31": "Yucatan", "32": "Zacatecas",
}

# Sanderson resolution_desc -> harmonised action_type (same vocabulary as the DOF parser)
SANDERSON_ACTIONS = {
    "Outright grant (dotacion de tierras)": "dotacion",
    "Deprivation of agrarian rights (privacion de derechos agrarios)": "privacion_derechos",
    "New adjudication (nueva adjudicacion)": "nueva_adjudicacion",
    "Enlargement (ampliacion de tierras)": "ampliacion",
    "Segregation (Segregacion)": "segregacion",
    "Expropriation (expropriacion)": "expropiacion",
    "Restitution (restitucion de tierras)": "restitucion",
    "New population centers (nuevos centros de poblacion)": "ncpe",
    "Recognition and entitlement (reconocimiento y titulacion)": "bienes_comunales",
    "Outright grant of water (dotacion de aguas)": "dotacion_aguas",
    "Division of ejidos (division ejidos-resta)": "division",
    "Division of ejidos-additional (division ejidos-suma)": "division",
    "Exchange received (permuta recibe)": "permuta",
    "Exchange-delivered (permuta entrega)": "permuta",
    "Confirmation (confirmacion)": "bienes_comunales",
    "Accomodation (acomodo)": "acomodo",
    "Accesion of water (accesion de aguas)": "accesion_aguas",
    "Fusion de ejidos-resta": "fusion",
    "Fusion de ejidos-suma": "fusion",
    "Incorporation into ejidal regime (Incorporacion al reg ejidal)-suma": "incorporacion",
    "Incorporation into ejidal regime (Incorporacion al regimen ejidal)-resta": "incorporacion",
    "Creation of village center (creacion de fundo legal)": "zona_urbana",
    "Enlargement of water (ampliacion de aguas)": "ampliacion_aguas",
    "Colonization (colonizacion)": "colonizacion",
    "Loss of rights to land (perdida de derechos a las tierras)": "perdida_derechos",
    "Additional exproriations (expropriacion-suma)": "expropiacion",
    "Rectification of presidential resolution (rectificacion a la res-pres-resta)": "rectificacion",
    "Rectification of presidential resolution (rectificacion a la res-pres-suma)": "rectificacion",
    "Inejectabilidad)": "inejecutabilidad",
    "Donation (donacion)": "donacion",
    "Restitution of water (restitucion de aguas)": "restitucion_aguas",
    "Abolition of presidential resolution (derogacion de resolucion presidencial)": "derogacion",
    "Abolition of presidential resolution (derogacion de res-pre-suma)": "derogacion",
    "List of errors-sum (fe de erratas-suma)": "fe_de_erratas",
    "List of errors remainder (fe de erratas-resta)": "fe_de_erratas",
    "Authorization of common use of water (autorizacion provisional de aprovechamiento de aguas)": "aguas_otros",
    "Lack of parcels (deficit de parcelas)": "deficit_parcelas",
    "Contract to rent national lands (contrato de arrendamiento de terrenos nacionales)": "terrenos_nacionales",
    "Contract to buy and sell (contato compra-venta)": "terrenos_nacionales",
    "Realization of national application (Actualizacion de zonas urbanas)": "zona_urbana",
    "Results of national application (Acuerdo de aplicacion nacional)": "other",
}
ACTION_GROUP = {
    "dotacion": "dotacion", "ampliacion": "ampliacion", "restitucion": "restitucion", "ncpe": "ncpe",
    "bienes_comunales": "bienes_comunales", "dotacion_aguas": "aguas", "ampliacion_aguas": "aguas",
    "accesion_aguas": "aguas", "restitucion_aguas": "aguas", "privacion_derechos": "derechos",
    "nueva_adjudicacion": "derechos", "privacion_nueva_adjudicacion": "derechos",
    "reconocimiento_derechos": "derechos", "perdida_derechos": "derechos", "acomodo": "derechos",
    "expropiacion": "expropiacion", "division": "division", "fusion": "fusion", "permuta": "permuta",
    "incorporacion": "incorporacion", "cancelacion_certificados": "derechos", "zona_urbana": "zona_urbana",
}
# primary group of a Sanderson event with several rows (dotacion + segregacion -> dotacion, ...)
GROUP_PRIORITY = ["ncpe", "restitucion", "dotacion", "ampliacion", "bienes_comunales", "aguas", "expropiacion",
                  "derechos", "division", "fusion", "permuta", "incorporacion", "zona_urbana"]
LAND_GRANT_ACTIONS = {"dotacion", "ampliacion", "restitucion", "ncpe", "bienes_comunales"}   # = INEGI "dotacion de tierras"
LINK_DOC_TYPES = {"resolucion", "decreto", "acuerdo", "sentencia"}
# file-history ("stage") fields parsed by 03 from the resultandos, carried into the ledger
STAGE_FIELDS = ["petition_date", "petition_type", "petition_published_date", "cam_dictamen_date", "mandamiento_date",
                "mandamiento_outcome", "cca_approval_date", "governor_name", "lag_petition_to_mandamiento_days",
                "lag_mandamiento_to_signing_days", "lag_petition_to_signing_days", "lag_signing_to_publication_days",
                "stage_order_flag", "petition_predates_signer_term", "petition_predates_signer_term_basis"]
STAGE_HANDCHECK_CSV = LAND_REFORM_DIR / "dof_stage_dates_handcheck.csv"

PRESIDENTS = [
    ("Venustiano Carranza", "1915-01-06", "1920-05-21"), ("Adolfo de la Huerta", "1920-06-01", "1920-11-30"),
    ("Alvaro Obregon", "1920-12-01", "1924-11-30"), ("Plutarco Elias Calles", "1924-12-01", "1928-11-30"),
    ("Emilio Portes Gil", "1928-12-01", "1930-02-04"), ("Pascual Ortiz Rubio", "1930-02-05", "1932-09-03"),
    ("Abelardo L. Rodriguez", "1932-09-04", "1934-11-30"), ("Lazaro Cardenas", "1934-12-01", "1940-11-30"),
    ("Manuel Avila Camacho", "1940-12-01", "1946-11-30"), ("Miguel Aleman Valdes", "1946-12-01", "1952-11-30"),
    ("Adolfo Ruiz Cortines", "1952-12-01", "1958-11-30"), ("Adolfo Lopez Mateos", "1958-12-01", "1964-11-30"),
    ("Gustavo Diaz Ordaz", "1964-12-01", "1970-11-30"), ("Luis Echeverria Alvarez", "1970-12-01", "1976-11-30"),
    ("Jose Lopez Portillo", "1976-12-01", "1982-11-30"), ("Miguel de la Madrid Hurtado", "1982-12-01", "1988-11-30"),
    ("Carlos Salinas de Gortari", "1988-12-01", "1994-11-30"),
]
PRES_TABLE = [(n, pd.Timestamp(a), pd.Timestamp(b)) for n, a, b in PRESIDENTS]
# EHM 2014 presidential periods (columns of tables 9.50/9.51) -> president(s)
EHM_TERM_OF = {"Lazaro Cardenas": "1935-1940", "Manuel Avila Camacho": "1941-1946", "Miguel Aleman Valdes": "1947-1952",
               "Adolfo Ruiz Cortines": "1953-1958", "Adolfo Lopez Mateos": "1959-1964", "Gustavo Diaz Ordaz": "1965-1970",
               "Luis Echeverria Alvarez": "1971-1976", "Jose Lopez Portillo": "1977-1982",
               "Miguel de la Madrid Hurtado": "1983-1988", "Carlos Salinas de Gortari": "1989-1992"}
for _n in ("Venustiano Carranza", "Adolfo de la Huerta", "Alvaro Obregon", "Plutarco Elias Calles", "Emilio Portes Gil",
           "Pascual Ortiz Rubio", "Abelardo L. Rodriguez"):
    EHM_TERM_OF[_n] = "1915-1934"


def president_on(d) -> tuple[str | None, pd.Timestamp | None]:
    if d is None or pd.isna(d):
        return None, None
    for n, a, b in PRES_TABLE:
        if a <= d <= b:
            return n, a
    return None, None


# ------------------------------------------------------------------------------------- name handling
NUMBER_WORDS = {"uno": "1", "una": "1", "primero": "1", "dos": "2", "segundo": "2", "tres": "3", "tercero": "3",
                "cuatro": "4", "cinco": "5", "seis": "6", "siete": "7", "ocho": "8", "nueve": "9", "diez": "10"}
ABBREV = {"sta": "santa", "sto": "santo", "sn": "san", "fco": "francisco", "ma": "maria", "gpe": "guadalupe",
          "jose ma": "jose maria", "cd": "ciudad", "hda": "hacienda", "rcho": "rancho", "ej": "ejido",
          "pto": "puerto", "sra": "senora", "ntra": "nuestra", "stgo": "santiago", "mpio": "municipio"}
HONORIFICS = {"lic", "licenciado", "gral", "general", "ing", "ingeniero", "profr", "profra", "profesor", "profesora",
              "prof", "dr", "doctor", "cnel", "coronel", "tte", "teniente", "presidente", "pdte", "c", "don", "dona",
              "cap", "capitan", "mtro", "maestro", "senor", "sr", "presbitero", "fray", "gobernador", "diputado"}
ARTICLES = {"el", "la", "los", "las"}
ROMAN = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6"}   # only after the first word


def raw_name(raw) -> str:
    """Full normalised name (articles, prefixes and parentheses kept) -- used only to break ties."""
    if not isinstance(raw, str):
        return ""
    t = re.sub(r"\(\s*res\.?\s*pres[^)]*\)", " ", norm(raw))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t)).strip()


NCPE_TAG_RE = re.compile(r"^(?:n\s?c\s?p\s?[eagp]|ncp[eagp]|nuevo centro de poblacion)\b")
PREFIX_RE = re.compile(r"^(?:n\s?c\s?p\s?[eapg]|ncp[eapg]|nuevo centro de poblacion(?: ejidal| agricola| agropecuario| ganadero)?|"
                       r"ejido(?: de| del)?|comunidad(?: agraria| indigena)?(?: de| del)?|bienes comunales(?: de| del)?|"
                       r"poblado(?: de)?|rancheria(?: de)?|congregacion(?: de)?|colonia agricola(?: y ganadera)?(?: de)?|"
                       r"c\s?i|anexo)\s+")


def name_variants(raw) -> list[str]:
    """Normalised core name plus aliases for a place name (DOF poblado or nucleo/locality name)."""
    if not isinstance(raw, str) or not raw.strip():
        return []
    t = norm(raw).replace('"', " ")
    t = re.sub(r"\(\s*res\.?\s*pres[^)]*\)", " ", t)                    # "(RES. PRES. 02/10/40)"
    aliases = re.findall(r"\(([^)]+)\)", t)
    t = re.sub(r"\([^)]*\)", " ", t)
    t = re.sub(r"^.*\bse denominar[ai]\s+", "", t)                         # "que de constituirse se denominara x"
    t = re.sub(r"^(?:denomina\s?do|denominad[oa])\s+", "", t.strip())      # OCR "denomina do"
    m = re.search(r"\b(?:antes|hoy|ahora|o bien|alias|tambien conocido como)\b\s+(.+)$", t)
    if m:
        aliases.append(m.group(1))
        t = t[:m.start()]
    if re.search(r"\s(?:o|u)\s", t):                                       # "maymorita o maymora"
        parts = re.split(r"\s+(?:o|u)\s+", t)
        t, aliases = parts[0], aliases + parts[1:]
    out = []
    for s in [t] + aliases:
        s = re.sub(r"\b(?:antes|hoy|ahora)\b", " ", s)
        s = re.sub(r"\s+y\s+(?:sus?\s+)?anex[oa]s?\b.*$", " ", s)          # "x y anexos", "x y su anexo y"
        s = re.sub(r"\b(?:fracc?(?:ion)?|fraccionamiento)\b\.?", " ", s)
        s = re.sub(r"[^a-z0-9 ]", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        s = PREFIX_RE.sub("", s)
        for k, v in ABBREV.items():
            s = re.sub(rf"\b{k}\b", v, s)
        s = re.sub(r"\b(?:n c p [eagp]|ncp[eagp]|n p [ae]|npa|npe)\b", " ", s)       # stray N.C.P.E. / N.P.A. tags
        s = re.sub(r"^denomin[a-z]*\s+", "", s.strip())
        toks = [NUMBER_WORDS.get(w, ROMAN.get(w, w)) if i > 0 else NUMBER_WORDS.get(w, w)
                for i, w in enumerate(s.split()) if w not in HONORIFICS]
        toks = [w for w in toks if w not in {"no", "num", "numero"}]
        while toks and toks[0] in ARTICLES:
            toks = toks[1:]
        s = " ".join(toks)
        if len(s) >= 2 and s not in out:
            out.append(s)
    return out


def name_score(a: str, b: str) -> float:
    if a == b:
        return 100.0
    sc = max(fuzz.ratio(a, b), fuzz.token_sort_ratio(a, b))
    ta, tb = set(a.split()), set(b.split())
    short = ta if len(ta) <= len(tb) else tb
    if short and short <= (ta | tb) and (short == ta or short == tb) and len(short) >= 2 and ta != tb:
        sc = max(sc, 88.0)       # one name contains the other ("san pedro cieneguilla" vs "san pedro x"): capped
    return float(sc)


class NucleoIndex:
    """Names of nucleos (PROCEDE + RAN) and census localities, by municipality and by state."""

    def __init__(self):
        a = pd.read_csv(EJIDOS_ATTRIBUTES_CSV, dtype=str)
        r = pd.read_csv(RAN_CATALOGUE_CSV, dtype=str)
        r["ran_claveunica"] = r["scncve_unica"].str.rstrip("_")
        r["state_code"] = r["scncve_edo"].str.zfill(2)
        r["mun5"] = r["state_code"] + r["scncve_mun"].str.zfill(3)
        a["mun5"] = a["state_code"] + a["mun_code"]
        self.nucleos = a[["nucleo_key", "ran_claveunica", "state_code", "mun5", "mun_name", "nucleo_name", "nucleo_type",
                          "has_polygon"]].copy()
        ran_only = r[~r["ran_claveunica"].isin(a["ran_claveunica"])].copy()
        ran_only = ran_only.rename(columns={"NÚCLEO AGRARIO": "nucleo_name", "MUNICIPIO": "mun_name"})
        ran_only["nucleo_type"] = ran_only["TIPO"].str[0]
        ran_only["nucleo_key"] = None
        ran_only["has_polygon"] = "0"
        self.nucleos = pd.concat([self.nucleos, ran_only[self.nucleos.columns]], ignore_index=True)
        self.nucleos["nid"] = np.arange(len(self.nucleos))
        ranname = r.set_index("ran_claveunica")["NÚCLEO AGRARIO"].to_dict()
        self.raw_names = {nid: {raw_name(a_), raw_name(ranname.get(k))} - {""}
                          for nid, a_, k in zip(self.nucleos.nid, self.nucleos.nucleo_name, self.nucleos.ran_claveunica)}
        self.nucleos["is_ncpe"] = [bool(NCPE_TAG_RE.match(raw_name(x))) for x in self.nucleos.nucleo_name]
        rows = []   # (nid, variant, source)
        for nr in self.nucleos.itertuples(index=False):
            for v in name_variants(nr.nucleo_name):
                rows.append((nr.nid, v, "nucleo_name"))
        ranmap = r.set_index("ran_claveunica")["NÚCLEO AGRARIO"].to_dict()
        for nr in self.nucleos.itertuples(index=False):
            alt = ranmap.get(nr.ran_claveunica)
            if isinstance(alt, str):
                for v in name_variants(alt):
                    rows.append((nr.nid, v, "ran_name"))
        loc = pd.read_csv(LOCALITIES_CSV, dtype=str)
        key2nid = self.nucleos.dropna(subset=["nucleo_key"]).set_index("nucleo_key")["nid"].to_dict()
        for lr in loc.itertuples(index=False):
            nid = key2nid.get(lr.nucleo_key)
            if nid is None:
                continue
            for v in name_variants(lr.loc_name):
                rows.append((nid, v, "locality"))
        names = pd.DataFrame(rows, columns=["nid", "variant", "source"]).drop_duplicates()
        names = names.merge(self.nucleos[["nid", "mun5", "state_code"]], on="nid")
        # a locality name shared by several nucleos of a municipality is not informative
        locs = names[names.source == "locality"]
        amb = locs.groupby(["mun5", "variant"]).nid.nunique()
        amb = set(amb[amb > 1].index)
        is_amb = np.array([(m, v) in amb for m, v in zip(names.mun5, names.variant)], dtype=bool)
        names = names[~((names.source == "locality").to_numpy() & is_amb)]
        self.names = names
        self.by_mun = {k: g for k, g in names.groupby("mun5")}
        self.by_state = {k: g for k, g in names.groupby("state_code")}
        # municipality names by state (PROCEDE, RAN, localities)
        mn = pd.concat([a[["state_code", "mun5", "mun_name"]], r.rename(columns={"MUNICIPIO": "mun_name"})[["state_code", "mun5", "mun_name"]],
                        loc.assign(mun5=loc.state_code + loc.mun_code)[["state_code", "mun5", "mun_name"]]]).dropna().drop_duplicates()
        mn["mun_norm"] = [mun_norm(x) for x in mn.mun_name]
        self.mun_names = {k: g for k, g in mn.groupby("state_code")}
        self.mun_label = mn.drop_duplicates("mun5").set_index("mun5")["mun_name"].to_dict()

    def best(self, variants: list[str], pool: pd.DataFrame | None) -> list[tuple[int, float, str, str]]:
        """[(nid, score, matched_variant, source)], best per nucleo, sorted by score. Candidates are retrieved with
        rapidfuzz's C scorers (token_sort / token_set, top 15 each) and rescored with name_score."""
        if pool is None or pool.empty or not variants:
            return []
        choices = pool["variant"].tolist()
        nids = pool["nid"].tolist()
        srcs = pool["source"].tolist()
        best = {}
        for v in variants:
            cand = set()
            for scorer in (fuzz.token_sort_ratio, fuzz.token_set_ratio):
                for _, sc, i in process.extract(v, choices, scorer=scorer, limit=15, score_cutoff=60):
                    cand.add(i)
            for i in cand:
                sc = name_score(v, choices[i])
                if sc < 70:
                    continue
                adj = sc if srcs[i] != "locality" else sc - 3       # locality aliases are weaker evidence
                if nids[i] not in best or adj > best[nids[i]][0]:
                    best[nids[i]] = (adj, choices[i], srcs[i])
        return sorted(((nid, s_, ch, src) for nid, (s_, ch, src) in best.items()), key=lambda x: -x[1])

    def resolve_municipality(self, state_code, mun_text) -> tuple[str | None, float]:
        if not isinstance(mun_text, str) or not isinstance(state_code, str) or state_code not in self.mun_names:
            return None, 0.0
        g = self.mun_names[state_code]
        if norm(mun_text).strip(" .") in ("la capital", "capital") and state_code in CAPITAL_MUN:
            mun_text = CAPITAL_MUN[state_code]     # "Municipio de la Capital" = the state capital's municipality
        q = mun_norm(mun_text)
        if not q:
            return None, 0.0
        res = process.extract(q, g["mun_norm"].tolist(), scorer=mun_score, limit=8)
        if not res:
            return None, 0.0
        best = {}
        for ch, sc, i in res:
            m5 = g.iloc[i]["mun5"]
            best[m5] = max(best.get(m5, 0.0), sc)
        ranked = sorted(best.items(), key=lambda x: -x[1])
        mun5, top = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else 0.0
        if (top >= 88 and top - second >= 5) or (top >= 85 and top - second >= 8) or (top == 100 and second < 100):
            return mun5, float(top)
        return None, float(top)


STATE_ABBR_TAIL = re.compile(r"\b(?:ags|bc|bcs|camp?|coah|col|chis|chih|df|dgo|gto|gro|hgo|jal|mex|mich|mor|nay|nl|oax|pue|"
                             r"qro|qroo|slp|sin|son|tab|tamps?|tlax|ver|yuc|zac|edo|estado)\s*$")


MUN_ABBREV = {"dr": "doctor", "gral": "general", "ing": "ingeniero", "lic": "licenciado", "profr": "profesor",
              "fco": "francisco", "ma": "maria", "gpe": "guadalupe", "sn": "san", "sta": "santa", "sto": "santo"}
CAPITAL_MUN = {"01": "aguascalientes", "05": "saltillo", "06": "colima", "07": "tuxtla gutierrez", "08": "chihuahua",
               "10": "durango", "11": "guanajuato", "12": "chilpancingo de los bravo", "13": "pachuca de soto",
               "14": "guadalajara", "15": "toluca", "16": "morelia", "17": "cuernavaca", "18": "tepic",
               "19": "monterrey", "20": "oaxaca de juarez", "21": "puebla", "22": "queretaro", "24": "san luis potosi",
               "25": "culiacan", "26": "hermosillo", "27": "centro", "28": "victoria", "29": "tlaxcala",
               "30": "xalapa", "31": "merida", "32": "zacatecas", "02": "mexicali", "03": "la paz", "04": "campeche",
               "23": "othon p blanco"}


def mun_norm(s) -> str:
    if not isinstance(s, str):
        return ""
    t = norm(s)
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = STATE_ABBR_TAIL.sub("", t)
    t = " ".join(MUN_ABBREV.get(w, w) for w in t.split())
    t = re.sub(r"\b(h|heroica|villa de|villa|ciudad|cd|del|de|la|el|los|las|san|santa)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def mun_score(a: str, b: str, **_kw) -> float:
    """Municipality-name similarity: token-sort ratio, or 95 when one name is the other plus a suffix
    ('tepeji rio' vs 'tepeji rio ocampo', 'comitan' vs 'comitan dominguez')."""
    sc = float(fuzz.token_sort_ratio(a, b))
    ta, tb = a.split(), b.split()
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if short and len(" ".join(short)) >= 5 and long_[:len(short)] == short:
        sc = max(sc, 95.0)
    return sc


# ------------------------------------------------------------------------------------------ Sanderson
def load_sanderson() -> pd.DataFrame:
    s, _ = pyreadstat.read_dta(str(SANDERSON_DTA))
    s = s.reset_index(drop=True)

    def todate(x):
        try:
            x = int(x)
            return pd.Timestamp(1900 + x // 10000, (x // 100) % 100, x % 100)
        except (ValueError, TypeError):
            return pd.NaT
    out = pd.DataFrame({
        "action_id": [f"SAN{i:05d}" for i in range(len(s))],
        "source": "sanderson",
        "dof_date": [todate(x) for x in s["fechadepublicacion"]],
        "state_code": s["stateid"].astype("Int64").astype(str).str.zfill(2),
        "mun_code": s["municipio"].astype(int).astype(str).str.zfill(5),
        "sanderson_village": s["municipio"].astype(int).astype(str).str.zfill(5) + "-" + s["clave"].astype(int).astype(str),
        "sanderson_tipotramite": s["tipotramite"].astype(int),
        "action_detail": s["resolution_desc"],
        "grant": s["positive"].astype("Int64"),
        "beneficiaries": s["beneficiarios"].astype(float),
        "beneficiaries_rights_reserved": s["dersalv"].astype(float),
        "hectares_total": s["superficietotal"].astype(float),
        "ha_riego": s["riego"], "ha_temporal": s["temporal"], "ha_agostadero": s["agostadero"], "ha_monte": s["monte"],
        "ha_desertico": s["desertico"], "ha_indefinido": s["indefinido"],
        "sanderson_year": s["year"],
    })
    out["action_type"] = s["resolution_desc"].map(SANDERSON_ACTIONS).fillna("other")
    out["action_group"] = out["action_type"].map(ACTION_GROUP)
    out["dof_year"] = out["dof_date"].dt.year.astype("Int64")
    out["dof_year"] = out["dof_year"].fillna(out["sanderson_year"].astype("Int64"))
    # event = same DOF date, municipality and village key
    ev = out["dof_date"].dt.strftime("%Y%m%d").fillna("nodate") + "|" + out["sanderson_village"]
    out["sanderson_event"] = "SEV" + pd.Series(pd.factorize(ev)[0], index=out.index).astype(str).str.zfill(5)
    return out


def event_table(san: pd.DataFrame) -> pd.DataFrame:
    def primary(groups):
        gs = [g for g in groups if isinstance(g, str)]
        for g in GROUP_PRIORITY:
            if g in gs:
                return g
        return None
    ev = san.groupby("sanderson_event").agg(dof_date=("dof_date", "first"), state_code=("state_code", "first"),
                                            mun_code=("mun_code", "first"), groups=("action_group", list),
                                            n_rows=("action_id", "size"))
    ev["group"] = ev["groups"].apply(primary)
    # hectares of the event's primary action (segregacion rows are sub-areas of the same grant)
    prim = san.merge(ev[["group"]], left_on="sanderson_event", right_index=True)
    ev["ha"] = prim[prim["action_group"] == prim["group"]].groupby("sanderson_event")["hectares_total"].sum()
    return ev.drop(columns="groups").reset_index()


# --------------------------------------------------------------------------------- DOF <-> Sanderson
def link_dof_to_sanderson(ev: pd.DataFrame, idx: pd.DataFrame, nix: NucleoIndex, dof_ha: dict) -> pd.DataFrame:
    """One row per linked (sanderson_event, codNota) with method and score. Tiers within a block of the same
    DOF date, state and action group: (1) a single event and a single title; (2) the municipality printed in the
    title (1970s) matches exactly one event's municipality one-to-one -- when a municipality has k events and k
    titles, the full-text hectares (1975-76) pair them if every pair agrees within 2%; (3) the title's poblado
    is found (score >= 90) in exactly one event's municipality and no other open title points there; (4) the
    last title and event left in a block of equal size. A second pass repeats this on (date, state) with the
    land-grant groups pooled (e.g. "restitucion revertida a dotacion")."""
    d = idx[(idx.dof_year <= 1976) & idx.doc_type.isin(LINK_DOC_TYPES)].copy()
    d["group"] = d["action_type"].map(ACTION_GROUP)
    d = d[d["group"].notna() & d["state_code"].notna()].rename(columns={"dof_date": "date_s"})
    d["variants"] = [name_variants(p) + name_variants(a) + name_variants(n)
                     for p, a, n in zip(d.poblado, d.poblado_alias, d.ncpe_name)]
    d["ha"] = d["codNota"].map(dof_ha)
    e = ev[ev["group"].notna() & ev["dof_date"].notna()].copy()
    e["date_s"] = e["dof_date"].dt.strftime("%Y-%m-%d")
    name_cache: dict = {}
    mun_cache: dict = {}

    def name_in_mun(variants, mun5):
        key = (tuple(variants), mun5)
        if key not in name_cache:
            hits = nix.best(variants, nix.by_mun.get(mun5))
            name_cache[key] = hits[0][1] if hits else 0.0
        return name_cache[key]

    def mun_agrees(mun_text, mun5):
        if not isinstance(mun_text, str):
            return False
        key = (mun_text, mun5)
        if key not in mun_cache:
            if norm(mun_text).strip(" .") in ("la capital", "capital") and str(mun5)[:2] in CAPITAL_MUN:
                mun_text = CAPITAL_MUN[str(mun5)[:2]]
            a, b = mun_norm(mun_text), mun_norm(nix.mun_label.get(mun5, ""))
            mun_cache[key] = bool(a and b and mun_score(a, b) >= 85)
        return mun_cache[key]

    links = []
    land = ["dotacion", "ampliacion", "restitucion", "ncpe", "bienes_comunales"]
    for passno, keycols in ((1, ["date_s", "state_code", "group"]), (2, ["date_s", "state_code"])):
        done_e = {l[0] for l in links}
        done_d = {l[1] for l in links}
        ee = e[~e.sanderson_event.isin(done_e)]
        dd = d[~d.codNota.isin(done_d)]
        sfx = "" if passno == 1 else "_any_grant"
        if passno == 2:
            ee, dd = ee[ee.group.isin(land)], dd[dd.group.isin(land)]
        dgroups = {k: g for k, g in dd.groupby(keycols)}
        for k, ge in ee.groupby(keycols):
            gd = dgroups.get(k)
            if gd is None:
                continue
            E = list(ge[["sanderson_event", "mun_code", "ha"]].itertuples(index=False, name=None))
            D = list(gd[["codNota", "variants", "municipality", "ha"]].itertuples(index=False, name=None))
            if len(E) == 1 and len(D) == 1:
                links.append((E[0][0], int(D[0][0]), "unique_block" + sfx, name_in_mun(D[0][1], E[0][1])))
                continue
            open_e, open_d = set(range(len(E))), set(range(len(D)))
            # tier 2: municipality printed in the title
            by_mun_e = collections.defaultdict(list)
            for j, (_, m5, _) in enumerate(E):
                by_mun_e[m5].append(j)
            title_mun = {}
            for i, (_, _, mt, _) in enumerate(D):
                ms = [m5 for m5 in by_mun_e if mun_agrees(mt, m5)]
                if len(ms) == 1:
                    title_mun[i] = ms[0]
            by_mun_d = collections.defaultdict(list)
            for i, m5 in title_mun.items():
                by_mun_d[m5].append(i)
            for m5, ii in by_mun_d.items():
                jj = by_mun_e[m5]
                if len(ii) != len(jj):
                    continue
                if len(ii) == 1:
                    links.append((E[jj[0]][0], int(D[ii[0]][0]), "municipality_text" + sfx, name_in_mun(D[ii[0]][1], E[jj[0]][1])))
                    open_e.discard(jj[0]); open_d.discard(ii[0])
                    continue
                hd = [D[i][3] for i in ii]
                he = [E[j][2] for j in jj]
                if all(pd.notna(x) and x > 0 for x in hd + he):
                    best = None
                    for perm in (__import__("itertools").permutations(range(len(jj))) if len(jj) <= 6 else []):
                        cost = sum(abs(hd[a] - he[perm[a]]) / max(hd[a], he[perm[a]]) for a in range(len(ii)))
                        if best is None or cost < best[0]:
                            best = (cost, perm)
                    if best and all(abs(hd[a] - he[best[1][a]]) <= 0.02 * max(hd[a], he[best[1][a]]) for a in range(len(ii))):
                        for a, i in enumerate(ii):
                            j = jj[best[1][a]]
                            links.append((E[j][0], int(D[i][0]), "municipality_text_hectares" + sfx, name_in_mun(D[i][1], E[j][1])))
                            open_e.discard(j); open_d.discard(i)
            # tier 3: poblado name found in exactly one open event's municipality
            changed = True
            while changed:
                changed = False
                cand = {}
                for i in open_d:
                    good = [j for j in open_e if name_in_mun(D[i][1], E[j][1]) >= 90]
                    if len({E[j][1] for j in good}) == 1 and len(good) == 1:
                        cand[i] = good[0]
                tgt = collections.Counter(cand.values())
                for i, j in cand.items():
                    if tgt[j] == 1 and i in open_d and j in open_e:
                        links.append((E[j][0], int(D[i][0]), "name_in_municipality" + sfx, name_in_mun(D[i][1], E[j][1])))
                        open_e.discard(j); open_d.discard(i)
                        changed = True
            # tier 4: elimination
            if len(open_d) == 1 and len(open_e) == 1 and len(D) == len(E):
                i, j = next(iter(open_d)), next(iter(open_e))
                links.append((E[j][0], int(D[i][0]), "elimination" + sfx, name_in_mun(D[i][1], E[j][1])))
    return pd.DataFrame(links, columns=["sanderson_event", "codNota", "dof_link_method", "dof_link_score"])


# ------------------------------------------------------------------------------------------- EHM 2014
EHM_TERMS = ["1900-1914", "1915-1934", "1935-1940", "1941-1946", "1947-1952", "1953-1958", "1959-1964",
             "1965-1970", "1971-1976", "1977-1982", "1983-1988", "1989-1992", "1900-1992"]
EHM_STATE = {norm(v): k for k, v in STATE_NAMES.items()}
EHM_STATE.update({"coahuila de zaragoza": "05", "michoacan de ocampo": "16", "veracruz de ignacio de la llave": "30",
                  "mexico": "15", "estados unidos mexicanos": "00", "no especificado": "99"})


def load_ehm() -> pd.DataFrame:
    """Tables 9.50 (hectares) and 9.51 (beneficiaries) by state x presidential period, long format."""
    with zipfile.ZipFile(EHM2014_ZIP) as z, tempfile.TemporaryDirectory() as tmp:
        name = [n for n in z.namelist() if n.startswith("9.")][0]
        pdf = Path(tmp) / "ch9.pdf"
        pdf.write_bytes(z.read(name))
        txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    rows = []
    for table, measure in (("9.50", "hectares"), ("9.51", "beneficiaries")):
        starts = [m.start() for m in re.finditer(rf"Cuadro {re.escape(table)}\b", txt)]
        for part, st in enumerate(starts[-2:]):
            block = txt[st: st + 9000]
            cols = EHM_TERMS[:7] if part == 0 else EHM_TERMS[7:]
            pending = ""
            for line in block.splitlines():
                line_s = line.strip()
                if not line_s or line_s.startswith(("Cuadro", "INEGI", "Fuente", "Periodos", "Hect", "Entidad", "a")) and not re.search(r"\d{2}", line_s):
                    continue
                m = re.match(r"^([A-Za-zÁÉÍÓÚáéíóúÑñü\. ]+?)\s{2,}(.*)$", line_s)
                if not m:
                    if re.fullmatch(r"[A-Za-zÁÉÍÓÚáéíóúÑñü\. ]+", line_s):
                        pending = line_s
                    continue
                label, vals = m.group(1).strip(), m.group(2)
                if pending and label.lower().startswith("de la"):
                    label = pending + " " + label
                pending = ""
                key = EHM_STATE.get(norm(label))
                if key is None:
                    continue
                cells = re.split(r"\s{2,}", vals.strip())
                if len(cells) != len(cols):
                    continue
                for c, v in zip(cols, cells):
                    v = v.replace(" ", "")
                    rows.append({"table": table, "measure": measure, "state_code": key, "ehm_term": c,
                                 "value": float(v) if re.fullmatch(r"\d+(\.\d+)?", v) else np.nan})
    # table 9.49: national, by period: resolutions, beneficiaries, hectares total and by land class
    st = [m.start() for m in re.finditer(r"Cuadro 9\.49\b", txt)][-1]
    names949 = ["resolutions", "beneficiaries_949", "hectares_949", "ha_riego", "ha_temporal", "ha_agostadero",
                "ha_monte", "ha_desertico", "ha_indefinido"]
    for line in txt[st: st + 4000].splitlines():
        m = re.match(r"^\s*(\d{4}-\d{4}|Total)\s{2,}(.*)$", line)
        if not m:
            continue
        cells = re.split(r"\s{2,}", m.group(2).strip())
        if len(cells) != 9:
            continue
        term = "1900-1992" if m.group(1) == "Total" else m.group(1)
        for nm, v in zip(names949, cells):
            rows.append({"table": "9.49", "measure": nm, "state_code": "00", "ehm_term": term,
                         "value": float(v.replace(" ", ""))})
    ehm = pd.DataFrame(rows).drop_duplicates(["measure", "state_code", "ehm_term"])
    return ehm


# ---------------------------------------------------------------------------------------------- main
def lag_distribution(notes: pd.DataFrame) -> np.ndarray:
    x = notes[(notes.in_ledger_scope == 1) & notes.action_type.isin(LAND_GRANT_ACTIONS) & notes.signing_lag_days.notna()]
    return np.sort(x["signing_lag_days"].astype(float).values)


def add_president_columns(df: pd.DataFrame, lags: np.ndarray) -> pd.DataFrame:
    pres, start = zip(*[president_on(d) for d in df["dof_date"]]) if len(df) else ([], [])
    df["president_in_office_at_dof"] = list(pres)
    start = pd.to_datetime(pd.Series(start, index=df.index))
    df["days_since_handover"] = (df["dof_date"] - start).dt.days
    w95 = float(np.quantile(lags, 0.95)) if len(lags) else 365.0
    df["handover_window"] = (df["days_since_handover"] < w95).astype("Int64")
    dsh = df["days_since_handover"].values
    df["p_signed_by_predecessor"] = [float((lags > v).mean()) if (len(lags) and not np.isnan(v)) else np.nan for v in dsh]
    if "president_signing" not in df:
        df["president_signing"] = None
        df["president_source"] = None
    has_text = df["president_signing"].notna()
    # acts the text shows were not signed by the President (tribunal sentences, Comision Agraria Mixta) keep no
    # president; everything else without a signer in the text gets the president in office on the DOF date
    nonpres = df["president_source"].astype(str).str.startswith("not_presidential")
    inf = ~has_text & ~nonpres
    df.loc[inf, "president_signing"] = df.loc[inf, "president_in_office_at_dof"]
    df.loc[inf & df["president_in_office_at_dof"].notna(), "president_source"] = "inferred_dof_date"
    df.loc[~inf, "p_signed_by_predecessor"] = np.nan
    df.loc[~inf, "handover_window"] = pd.NA
    return df


def match_nucleo(variants, query_raw, mun5, state_code, action_group, nix: NucleoIndex, nuc: pd.DataFrame) -> dict | None:
    """Best nucleo for a place name: municipality first, then state. Equal scores are broken, in order, by
    nucleo type (comunidad for bienes comunales, else ejido), N.C.P.E. tag agreeing with the action, similarity
    of the full uncleaned names (>= 5 points) and polygon (PROCEDE) over a RAN-only record. Accepted: a unique
    exact core-name match, or score >= threshold with a 5-point margin. Returns the accepted match, or the best
    rejected candidate (accepted = 0)."""
    want_type = "C" if action_group == "bienes_comunales" else "E"
    want_ncpe = action_group == "ncpe"
    best_rejected = None
    scopes = []
    if mun5:
        scopes.append(("municipality", nix.by_mun.get(mun5), 90, False))
    scopes.append(("state", nix.by_state.get(state_code), 95, True))

    def raw_sim(nid):
        return max((fuzz.ratio(query_raw, x) for x in nix.raw_names.get(nid, ())), default=0.0)

    for scope, pool, thr, need_unique in scopes:
        hits = nix.best(variants, pool)
        if not hits:
            continue
        top_score = hits[0][1]
        tied = [h for h in hits if h[1] == top_score]
        rest = [h for h in hits if h[1] < top_score]
        tiebreak = None
        if len(tied) > 1:
            for name, keyf, min_gap in (
                    ("type", lambda h: nuc.at[h[0], "nucleo_type"] == want_type, 1),
                    ("ncpe_tag", lambda h: bool(nuc.at[h[0], "is_ncpe"]) == want_ncpe, 1),
                    ("full_name", lambda h: raw_sim(h[0]), 5),
                    ("polygon", lambda h: str(nuc.at[h[0], "has_polygon"]) == "1", 1)):
                vals = sorted(((float(keyf(h)), h) for h in tied), key=lambda x: -x[0])
                if vals[0][0] - vals[1][0] >= min_gap:
                    keep = [h for v, h in vals if vals[0][0] - v < min_gap]
                    if len(keep) == 1:
                        tied, tiebreak = keep, name
                        break
                    tied = keep
        top = tied[0]
        second = tied[1] if len(tied) > 1 else (rest[0] if rest else None)
        margin = top[1] - (second[1] if second else 0)
        thr_eff = thr + (5 if top[3] == "locality" and scope == "municipality" else 0)
        unique_exact = top[1] == 100 and (len(tied) == 1)
        accepted = top[1] >= thr_eff and len(tied) == 1 and (unique_exact or margin >= 5)
        if need_unique:
            accepted = accepted and (second is None or second[1] < 90 or tiebreak is not None)
        res = dict(nid=top[0], score=round(top[1], 1), matched_name=top[2], name_source=top[3], scope=scope,
                   second_score=round(second[1], 1) if second else None, accepted=int(accepted), tiebreak=tiebreak)
        if accepted:
            return res
        if best_rejected is None or res["score"] > best_rejected["score"]:
            best_rejected = res
    return best_rejected


def crosswalk(ledger: pd.DataFrame, nix: NucleoIndex) -> pd.DataFrame:
    rows = []
    cache = {}
    nuc = nix.nucleos.set_index("nid")
    for r in ledger[ledger["poblado_any"].notna()].itertuples(index=False):
        variants = []
        for x in (r.poblado, r.poblado_alias, r.ncpe_name):
            variants += [v for v in name_variants(x) if v not in variants]
        if not variants:
            continue
        mun5 = r.mun_code if isinstance(r.mun_code, str) and r.mun_code in nix.by_mun else None
        qraw = raw_name(r.poblado if isinstance(r.poblado, str) else r.ncpe_name)
        key = (tuple(variants), qraw, mun5, r.state_code, r.action_group)
        if key not in cache:
            cache[key] = match_nucleo(variants, qraw, mun5, r.state_code, r.action_group, nix, nuc)
        res = cache[key]
        if res is None:
            continue
        n = nuc.loc[res["nid"]]
        rows.append({
            "action_id": r.action_id, "source": r.source, "dof_year": r.dof_year, "state_code": r.state_code,
            "query_name": variants[0], "mun_code_query": mun5, "nucleo_key": n["nucleo_key"],
            "ran_claveunica": n["ran_claveunica"], "nucleo_name": n["nucleo_name"], "nucleo_type": n["nucleo_type"],
            "nucleo_mun_code": n["mun5"], "has_polygon": n["has_polygon"], "score": res["score"],
            "second_score": res["second_score"], "matched_variant": res["matched_name"],
            "method": f"{res['name_source']}_{res['scope']}" + (f"_tiebreak_{res['tiebreak']}" if res.get("tiebreak") else ""),
            "accepted": res["accepted"],
        })
    return pd.DataFrame(rows)


HA_CLASSES = ["ha_riego", "ha_temporal", "ha_agostadero", "ha_monte", "ha_desertico", "ha_indefinido"]
CHANGED = ["dof_text_reparse", "dof_scan"]
AUDIT_COLS = ["hectares_source", "hectares_method", "hectares_confidence", "hectares_prev", "beneficiaries_source",
              "beneficiaries_confidence", "beneficiaries_prev", "signing_source", "signing_date_confidence",
              "signing_date_prev", "president_signing_prev", "land_grant_printed", "not_land_grant_reason",
              "correction_note"]


def apply_dof_corrections(dof: pd.DataFrame) -> pd.DataFrame:
    """Write 06's corrections (notes with text) and 05's scanned readings (notes without text) into the DOF rows.
    Before: every value as 03 parsed it, kept in *_prev (president_signing_prev is filled later, once the DOF-date
    president is known). Sources: dof_text_03 = 03 unchanged; dof_text_reparse = 06's rules or a hand reading on the SIDOF
    text; dof_scan = read on the scanned edition (05, or 06's hand readings of scanned pages). A changed signing date or
    signer replaces president_signing / president_source as given (empty = inferred from the DOF date later).
    land_grant_printed: 1 the printed note is a land grant (text parsed, or the scan read), 0 it is another act (a
    privacion de derechos, a division, an initiation notice, a dotacion de aguas ...; it does not count as a land grant),
    empty not checked."""
    C = pd.read_csv(DOF_TEXT_CORRECTIONS_CSV, low_memory=False)
    B = pd.read_csv(DOF_SCANNED_RESOLUTIONS_CSV, low_memory=False)
    dof = dof.copy()
    dof["hectares_prev"] = dof["hectares_total"]
    dof["beneficiaries_prev"] = dof["beneficiaries"]
    dof["signing_date_prev"] = dof["signing_date"]
    dof["_president_03"], dof["_president_source_03"] = dof["president_signing"], dof["president_source"]
    dof["hectares_source"] = np.where(dof["hectares_total"].notna(), "dof_text_03", None)
    dof["hectares_method"] = np.where(dof["hectares_total"].notna(), "03", None)
    dof["beneficiaries_source"] = np.where(dof["beneficiaries"].notna(), "dof_text_03", None)
    dof["signing_source"] = np.where(dof["signing_date"].notna() | dof["president_signing"].notna(), "dof_text_03", None)
    for c in ("hectares_confidence", "beneficiaries_confidence", "signing_date_confidence", "land_grant_printed",
              "not_land_grant_reason", "correction_note"):
        dof[c] = None
    for c in ("hectares_total", *HA_CLASSES, "beneficiaries", "grant", "land_grant_printed"):
        dof[c] = dof[c].astype(float)
    for c in ("signing_date", "president_signing", "president_source", "signer_body", "hectares_source", "hectares_method",
              "hectares_confidence", "beneficiaries_source", "beneficiaries_confidence", "signing_source",
              "signing_date_confidence", "not_land_grant_reason", "correction_note"):
        dof[c] = dof[c].astype(object)
    pos = pd.Series(dof.index, index=dof["codNota"].astype(int).values)

    # ---- 06: notes with a full text (06 selects them from 03's notes with the same rule, so all must be here)
    assert C.codNota.isin(pos.index).all(), "06's corrections cover notes that are not DOF rows of the ledger: rerun 06"
    assert (dof.loc[pos[C.codNota].values, "has_fulltext"] == 1).all()
    for r in C.to_dict("records"):
        i = pos[int(r["codNota"])]
        if r["hectares_source"] in CHANGED:
            dof.at[i, "hectares_total"] = r["hectares"]
            for c in HA_CLASSES:
                dof.at[i, c] = r[c]
            for c in ("hectares_source", "hectares_method", "hectares_confidence"):
                dof.at[i, c] = r[c] if pd.notna(r[c]) else None
        if r["beneficiaries_source"] in CHANGED:
            dof.at[i, "beneficiaries"] = r["beneficiaries"]
            dof.at[i, "beneficiaries_source"] = r["beneficiaries_source"]
        if r["signing_source"] in CHANGED:
            for c in ("signing_date", "president_signing", "president_source", "signer_body"):
                dof.at[i, c] = r[c] if pd.notna(r[c]) else None
            dof.at[i, "signing_source"] = r["signing_source"]
        dof.at[i, "grant"] = r["grant"]
        dof.at[i, "land_grant_printed"] = r["land_grant_printed"]
        dof.at[i, "not_land_grant_reason"] = r["not_land_grant_reason"] if pd.notna(r["not_land_grant_reason"]) else None
        dof.at[i, "correction_note"] = r["note"] if pd.notna(r["note"]) else None

    # ---- 05: notes without a full text, read on the scanned editions
    assert B.codNota.isin(pos.index).all(), "05's table covers notes that are not DOF rows of the ledger"
    for r in B.to_dict("records"):
        i = pos[int(r["codNota"])]
        assert dof.at[i, "has_fulltext"] == 0, r["codNota"]
        if r["is_land_grant_printed"] == 0:
            dof.at[i, "land_grant_printed"] = 0
            dof.at[i, "grant"] = np.nan
            dof.at[i, "not_land_grant_reason"] = str(r["note"])
            continue
        if pd.isna(r["hectares"]):                       # not located in the scan (18 notes of 30 Nov 1976)
            dof.at[i, "correction_note"] = str(r["note"]) if pd.notna(r["note"]) else None
            continue
        dof.at[i, "land_grant_printed"] = 1
        dof.at[i, "grant"] = r["grant"]
        dof.at[i, "hectares_total"] = r["hectares"]
        for c in HA_CLASSES:
            dof.at[i, c] = r[c] if pd.notna(r[c]) else 0.0
        dof.at[i, "hectares_source"], dof.at[i, "hectares_method"] = "dof_scan", r["method"]
        dof.at[i, "hectares_confidence"] = r["confidence"]
        if pd.notna(r["beneficiaries"]):
            dof.at[i, "beneficiaries"] = r["beneficiaries"]
            dof.at[i, "beneficiaries_source"], dof.at[i, "beneficiaries_confidence"] = "dof_scan", r["beneficiaries_confidence"]
        if pd.notna(r["signing_date"]) or pd.notna(r["signer"]):
            dof.at[i, "signing_date"] = str(r["signing_date"])[:10] if pd.notna(r["signing_date"]) else None
            dof.at[i, "signing_date_confidence"] = r["signing_date_confidence"] if pd.notna(r["signing_date"]) else None
            if pd.notna(r["signer"]):
                dof.at[i, "president_signing"] = r["signer"]
                # the printed signature (text layer, second OCR or read on the page); else the president on the signing date
                dof.at[i, "president_source"] = "text_signing_date" if r["signer_source"] == "signing_date" else "text_name"
                dof.at[i, "signer_body"] = "president"
            dof.at[i, "signing_source"] = "dof_scan"
        dof.at[i, "correction_note"] = str(r["note"]) if pd.notna(r["note"]) else None
    n_h = dof.hectares_source.isin(CHANGED)
    print(f"DOF corrections: hectares {int(n_h.sum())} rows ({dof[n_h].hectares_source.value_counts().to_dict()}), "
          f"beneficiaries {int(dof.beneficiaries_source.isin(CHANGED).sum())}, signing {int(dof.signing_source.isin(CHANGED).sum())}, "
          f"not land grants in print {int((dof.land_grant_printed == 0).sum())}")
    return dof


def flag_reprints(L: pd.DataFrame) -> None:
    """A resolution the DOF printed more than once is one grant (El Porvenir, Coah., Reg. 19115, signed 13 Aug 1981, was
    printed on 7, 9 and 21 Oct 1981; some reprints are a scanned note and a note with text). DOF land-grant rows of the
    same state and village (core poblado / NCPE name), the same surface (within 0.01 ha) and the same signing date -- or
    one signing date missing and publications at most 120 days apart -- are one resolution: the first publication counts,
    later ones get duplicate_of = its action_id and is_land_grant = 0 (in place). A re-resolution (the same village and
    surface signed again years later, e.g. Zacatecas NCPEs of 1979 re-granted in 1989 after an amparo) has a different
    signing date and is kept."""
    L["duplicate_of"] = None
    G = L[(L.source == "dof") & (L.is_land_grant == 1) & L.hectares_total.notna()].copy()
    G["name"] = [(name_variants(p if isinstance(p, str) else n) or [""])[0] for p, n in zip(G.poblado, G.ncpe_name)]
    G = G[G["name"] != ""].sort_values(["dof_date", "action_id"])
    for _, g in G.groupby(["state_code", "name"]):
        if len(g) < 2:
            continue
        kept = []
        for r in g.itertuples():
            first = None
            for k in kept:
                same_sd = pd.notna(r.signing_date) and pd.notna(k.signing_date) and r.signing_date == k.signing_date
                near = ((pd.isna(r.signing_date) or pd.isna(k.signing_date))
                        and 0 <= (r.dof_date - k.dof_date).days <= 120)
                if abs(r.hectares_total - k.hectares_total) <= 0.01 and (same_sd or near):
                    first = k
                    break
            if first is None:
                kept.append(r)
            else:
                L.at[r.Index, "duplicate_of"] = first.action_id
    dup = L["duplicate_of"].notna()
    L.loc[dup, "is_land_grant"] = 0.0
    print(f"reprints: {int(dup.sum())} DOF land-grant rows are later publications of a resolution already counted "
          f"({L.loc[dup, 'hectares_total'].sum():,.1f} ha left out)")


def recompute_stage_lags(L: pd.DataFrame, rows: pd.Series) -> None:
    """03's add_stage_lags on the rows whose signing date or signer changed (in place): lags to the signature, the
    stage-order flag and whether the file predates the signer's term."""
    if not rows.any():
        return
    d = L.loc[rows]
    dt_ = {c: pd.to_datetime(d[c], errors="coerce") for c in ("petition_date", "petition_published_date",
                                                              "cam_dictamen_date", "mandamiento_date", "cca_approval_date",
                                                              "signing_date", "dof_date")}
    sig, dof_ = dt_["signing_date"], dt_["dof_date"]
    L.loc[rows, "lag_mandamiento_to_signing_days"] = (sig - dt_["mandamiento_date"]).dt.days
    L.loc[rows, "lag_petition_to_signing_days"] = (sig - dt_["petition_date"]).dt.days
    L.loc[rows, "lag_signing_to_publication_days"] = (dof_ - sig).dt.days
    order = [dt_["petition_date"], dt_["cam_dictamen_date"], dt_["mandamiento_date"], dt_["cca_approval_date"], sig, dof_]
    bad = pd.Series(False, index=d.index)
    for a in range(len(order)):
        for b in range(a + 1, len(order)):
            bad |= (order[a] > order[b]).fillna(False)
    L.loc[rows, "stage_order_flag"] = bad.astype(int)
    start = {n: a for n, a, _ in PRES_TABLE}
    # as in 03: only a signer read in the text (name or signing date) dates the signer's term
    ts = pd.to_datetime(d["president_signing"].where(d["president_source"].astype(str).str.startswith("text")).map(start))
    inh = pd.Series(np.nan, index=d.index)
    has_p = dt_["petition_date"].notna() & ts.notna()
    inh[has_p] = (dt_["petition_date"][has_p] < ts[has_p]).astype(int)
    bound = dt_["petition_date"].isna() & dt_["petition_published_date"].notna() & ts.notna() & (dt_["petition_published_date"] < ts)
    inh[bound] = 1
    L.loc[rows, "petition_predates_signer_term"] = inh
    L.loc[rows, "petition_predates_signer_term_basis"] = np.where(has_p, "petition_date", np.where(bound, "published_bound", None))


def main():
    print("loading Sanderson, DOF tables, nucleo names ...")
    san = load_sanderson()
    idx = pd.read_csv(DOF_AGRARIAN_INDEX_CSV, dtype={"state_code": str})
    notes = pd.read_csv(DOF_AGRARIAN_NOTES_CSV, dtype={"state_code": str}, low_memory=False)
    notes["dof_date"] = pd.to_datetime(notes["dof_date"])
    notes["signing_date"] = pd.to_datetime(notes["signing_date"], errors="coerce")
    nix = NucleoIndex()
    lags = lag_distribution(notes)
    print(f"signing->DOF lag (land grants 1973-92, n={len(lags)}): median {np.median(lags):.0f} d, "
          f"p90 {np.quantile(lags, .9):.0f} d, p95 {np.quantile(lags, .95):.0f} d")

    # ---- link DOF titles to Sanderson events (1916-1976)
    ev = event_table(san)
    links = link_dof_to_sanderson(ev, idx, nix, notes.set_index("codNota")["hectares_total"].to_dict())
    print(f"DOF titles linked to Sanderson events: {len(links):,} of {ev.shape[0]:,} events")
    print(links.dof_link_method.value_counts().to_string())
    links = links.drop_duplicates("sanderson_event").drop_duplicates("codNota")
    ix = idx.set_index("codNota")
    nt = notes.set_index("codNota")
    san = san.merge(links, on="sanderson_event", how="left")
    san["codNota"] = san["codNota"].astype("Int64")
    for c_out, c_in in (("poblado", "poblado"), ("poblado_alias", "poblado_alias"), ("ncpe_name", "ncpe_name"),
                        ("municipality_dof", "municipality"), ("dof_title", "title"), ("dof_issuing_body", "issuing_body")):
        san[c_out] = san["codNota"].map(ix[c_in]) if c_in in ix else None
    for c in ("signing_date", "president_signing", "president_source", "signer_body", "hectares_total", "beneficiaries",
              "has_fulltext", *STAGE_FIELDS):
        san[("dof_" + c) if c in ("hectares_total", "beneficiaries") else c] = san["codNota"].map(nt[c]) if c in nt else None
    san["dof_codNota"] = san.pop("codNota").astype("Int64")

    # ---- DOF rows: from the day after Sanderson's last DOF date (3 Nov 1976 -- Sanderson misses the end-of-term
    # burst of November 1976) to 31 Dec 1992
    san_end = san["dof_date"].max()
    print(f"Sanderson ends {san_end.date()}; DOF rows start the next day")
    dof = notes[(notes.dof_date > san_end) & (notes.in_ledger_scope == 1)].copy()
    dof["action_id"] = "DOF" + dof["codNota"].astype(str)
    dof["source"] = "dof"
    dof["action_group"] = dof["action_type"].map(ACTION_GROUP)
    dof["dof_codNota"] = dof["codNota"].astype("Int64")
    dof["dof_title"] = dof["title"]
    dof["dof_issuing_body"] = dof["issuing_body"]
    dof["municipality_dof"] = dof["municipality"]
    dof["action_detail"] = dof["doc_type"] + ": " + dof["action_type"]
    res = [nix.resolve_municipality(s, m) for s, m in zip(dof.state_code, dof.municipality)]
    dof["mun_code"] = [r[0] for r in res]
    dof["mun_match_score"] = [r[1] for r in res]
    dof = apply_dof_corrections(dof)
    san["hectares_source"] = np.where(san["hectares_total"].notna(), "sanderson", None)
    san["beneficiaries_source"] = np.where(san["beneficiaries"].notna(), "sanderson", None)
    san["signing_source"] = np.where(san["signing_date"].notna() | san["president_signing"].notna(), "dof_text_03", None)

    cols_common = ["action_id", "source", "dof_date", "dof_year", "signing_date", "president_signing", "president_source",
                   "signer_body",
                   "state_code", "mun_code", "municipality_dof", "poblado", "poblado_alias", "ncpe_name",
                   "sanderson_village", "sanderson_event", "sanderson_tipotramite", "action_type", "action_detail",
                   "action_group", "grant", "beneficiaries", "beneficiaries_rights_reserved", "hectares_total",
                   "ha_riego", "ha_temporal", "ha_agostadero", "ha_monte", "ha_desertico", "ha_indefinido",
                   "water_volume_m3", "expropriation_beneficiary", "indemnity_pesos", "dof_codNota", "dof_title",
                   "dof_issuing_body", "dof_link_method", "dof_link_score", "has_fulltext", "title_body_mismatch",
                   "dof_hectares_total", "dof_beneficiaries", "mun_match_score", *STAGE_FIELDS, *AUDIT_COLS,
                   "_president_03", "_president_source_03"]
    for c in cols_common:
        for df_ in (san, dof):
            if c not in df_:
                df_[c] = np.nan
    ledger = pd.concat([san[cols_common], dof[cols_common]], ignore_index=True)
    ledger["dof_date"] = pd.to_datetime(ledger["dof_date"])
    ledger["signing_date"] = pd.to_datetime(ledger["signing_date"], errors="coerce")
    ledger["dof_year"] = ledger["dof_year"].astype("Int64")
    ledger["state_name"] = ledger["state_code"].map(STATE_NAMES)
    ledger["grant"] = pd.to_numeric(ledger["grant"], errors="coerce").astype("Int64")
    ledger["is_land_grant_action"] = ledger["action_type"].isin(LAND_GRANT_ACTIONS).astype(int)
    # DOF land-grant resolutions without a readable text: 1975-92 resolutions with text are grants in >99.9%
    # of cases (denials were not published in this period), so they count as grants, flagged.
    # Notes the print shows are another act (land_grant_printed == 0) are neither imputed nor counted.
    not_printed_grant = ledger["land_grant_printed"] == 0
    imp = ((ledger["source"] == "dof") & (ledger["is_land_grant_action"] == 1) & ledger["grant"].isna()
           & ledger["action_detail"].astype(str).str.startswith("resolucion") & ~not_printed_grant)
    ledger["grant_imputed"] = imp.astype(int)
    ledger.loc[imp, "grant"] = 1
    ledger["is_land_grant"] = np.where(ledger["is_land_grant_action"] == 1, ledger["grant"].astype("float"), 0.0)
    ledger.loc[not_printed_grant, "is_land_grant"] = 0.0
    ledger = add_president_columns(ledger, lags)
    # the president the ledger gave each DOF row before the corrections (03's signer, else the DOF-date president)
    dofr = ledger["source"] == "dof"
    nonpres03 = ledger["_president_source_03"].astype(str).str.startswith("not_presidential")
    ledger["president_signing_prev"] = None
    ledger.loc[dofr, "president_signing_prev"] = ledger.loc[dofr, "_president_03"].where(
        ledger.loc[dofr, "_president_03"].notna(), ledger.loc[dofr, "president_in_office_at_dof"].where(~nonpres03[dofr]))
    recompute_stage_lags(ledger, dofr & ledger["signing_source"].isin(CHANGED))
    ledger = ledger.drop(columns=["_president_03", "_president_source_03"])
    flag_reprints(ledger)
    ledger["ehm_term"] = ledger["president_signing"].map(EHM_TERM_OF)
    ledger["poblado_any"] = ledger["poblado"].fillna(ledger["ncpe_name"])
    ledger["municipality_name"] = ledger["mun_code"].map(nix.mun_label).fillna(ledger["municipality_dof"])

    # ---- crosswalk to nucleos
    print("crosswalk to nucleos ...")
    cw = crosswalk(ledger, nix)
    acc = cw[cw.accepted == 1].set_index("action_id")
    ledger["nucleo_key"] = ledger["action_id"].map(acc["nucleo_key"])
    ledger["ran_claveunica"] = ledger["action_id"].map(acc["ran_claveunica"])
    ledger["nucleo_name"] = ledger["action_id"].map(acc["nucleo_name"])
    ledger["nucleo_match_score"] = ledger["action_id"].map(acc["score"])
    ledger["nucleo_match_method"] = ledger["action_id"].map(acc["method"])
    # municipality code: Sanderson's INEGI code; for DOF rows the title's municipality resolved to an INEGI code,
    # else the municipality of the matched nucleo
    ledger["mun_source"] = np.where(ledger["source"] == "sanderson", "sanderson",
                                    np.where(ledger["mun_code"].notna(), "dof_title", None))
    fill = ledger["mun_code"].isna() & ledger["action_id"].isin(acc.index)
    ledger.loc[fill, "mun_code"] = ledger.loc[fill, "action_id"].map(acc["nucleo_mun_code"])
    ledger.loc[fill, "mun_source"] = "nucleo_match"
    ledger["municipality_name"] = ledger["mun_code"].map(nix.mun_label).fillna(ledger["municipality_dof"])

    order = ["action_id", "source", "dof_date", "dof_year", "signing_date", "president_signing", "president_source",
             "signer_body",
             "president_in_office_at_dof", "days_since_handover", "handover_window", "p_signed_by_predecessor", "ehm_term",
             "state_code", "state_name", "mun_code", "mun_source", "municipality_name", "municipality_dof", "mun_match_score",
             "poblado", "poblado_alias", "ncpe_name", "sanderson_village", "sanderson_event", "sanderson_tipotramite",
             "action_type", "action_group", "action_detail", "is_land_grant_action", "grant", "grant_imputed", "is_land_grant",
             "beneficiaries", "beneficiaries_rights_reserved", "hectares_total", "ha_riego", "ha_temporal",
             "ha_agostadero", "ha_monte", "ha_desertico", "ha_indefinido", "water_volume_m3",
             "expropriation_beneficiary", "indemnity_pesos", "dof_codNota", "dof_title", "dof_issuing_body",
             "dof_link_method", "dof_link_score", "has_fulltext", "title_body_mismatch", "dof_hectares_total",
             "dof_beneficiaries", *AUDIT_COLS, "duplicate_of", *STAGE_FIELDS, "nucleo_key", "ran_claveunica", "nucleo_name",
             "nucleo_match_score", "nucleo_match_method"]
    ledger = ledger[order].sort_values(["dof_date", "action_id"], na_position="last")
    ledger["dof_date"] = ledger["dof_date"].dt.date
    ledger["signing_date"] = ledger["signing_date"].dt.date
    ledger["signing_date_prev"] = pd.to_datetime(ledger["signing_date_prev"], errors="coerce").dt.date
    ledger.to_csv(AGRARIAN_LEDGER_CSV, index=False)
    cw.to_csv(EJIDO_ACTION_CROSSWALK_CSV, index=False)
    print(f"ledger: {len(ledger):,} rows -> {AGRARIAN_LEDGER_CSV.name}; crosswalk {len(cw):,} rows "
          f"({int(cw.accepted.sum()):,} accepted) -> {EJIDO_ACTION_CROSSWALK_CSV.name}")

    # ---- validation
    ehm = load_ehm()
    ehm.to_csv(EHM_LONG_CSV, index=False)
    val = build_validation(ledger, idx, notes[notes.dof_date <= san_end], san, links, ehm, cw)
    val.to_csv(LAND_REFORM_VALIDATION_CSV, index=False)
    print(f"validation: {len(val):,} rows -> {LAND_REFORM_VALIDATION_CSV.name}")


def vrow(check, period, state, group, measure, a, src_a, b, src_b, note=""):
    ratio = (a / b) if (b not in (0, None) and not pd.isna(b) and not pd.isna(a)) else np.nan
    return {"check": check, "period": period, "state_code": state, "state_name": STATE_NAMES.get(state, "national" if state == "00" else None),
            "action_group": group, "measure": measure, "value_a": a, "source_a": src_a, "value_b": b,
            "source_b": src_b, "ratio_a_b": ratio, "note": note}


def build_validation(ledger, idx, notes, san, links, ehm, cw) -> pd.DataFrame:
    rows = []
    L = ledger.copy()
    L["dof_date"] = pd.to_datetime(L["dof_date"])
    # 1. Sanderson events vs DOF index titles, by year x group (1916-1976, years with an index)
    idx_years = set(idx.dof_year.unique())
    ev = event_table(san.rename(columns={}))
    ev["year"] = ev["dof_date"].dt.year
    di = idx[(idx.dof_year <= 1976) & idx.doc_type.isin(LINK_DOC_TYPES)].copy()
    di["group"] = di["action_type"].map(ACTION_GROUP)
    for (y, g), n in ev[ev.year.isin(idx_years)].groupby(["year", "group"]).size().items():
        nd = int(((di.dof_year == y) & (di.group == g)).sum())
        rows.append(vrow("sanderson_events_vs_dof_index_titles", str(int(y)), "00", g, "count", float(n), "sanderson_events",
                         float(nd), "dof_index_titles"))
    # link rate by year
    lk = ev.merge(links, on="sanderson_event", how="left")
    for y, g in lk[lk.year.isin(idx_years)].groupby("year"):
        rows.append(vrow("sanderson_events_linked_to_dof_title", str(int(y)), "00", "all", "share",
                         float(g.codNota.notna().mean()), "linked_events", float(len(g)), "events"))
    # link quality: links made without names -- is the DOF poblado found in the Sanderson municipality?
    lk2 = links.merge(ev[["sanderson_event", "year"]], on="sanderson_event", how="left")
    lk2["decade"] = (lk2["year"] // 10 * 10).astype("Int64").astype(str) + "s"
    for (dec, mth), g in lk2.groupby(["decade", "dof_link_method"]):
        if mth.startswith("name_in_municipality"):
            continue
        rows.append(vrow("link_name_found_in_sanderson_municipality", dec, "00", mth, "share_score_ge_85",
                         float((g.dof_link_score >= 85).sum()), "links_with_name_in_municipality", float(len(g)), "links"))
    # 2. Sanderson vs DOF full text, 1973-76 land grants by year x state (full texts exist from 1973)
    OVER = [1973, 1974, 1975, 1976]
    s7576 = L[(L.source == "sanderson") & L.dof_year.isin(OVER) & (L.is_land_grant == 1)]
    n7576 = notes[notes.dof_year.isin(OVER) & (notes.in_ledger_scope == 1) & notes.action_type.isin(LAND_GRANT_ACTIONS)]
    n7576g = n7576[n7576.grant == 1]
    for y in OVER:
        for st in sorted(set(s7576.state_code.dropna()) | set(n7576.state_code.dropna())) + ["00"]:
            a = s7576[(s7576.dof_year == y) & ((s7576.state_code == st) | (st == "00"))]
            b = n7576g[(n7576g.dof_year == y) & ((n7576g.state_code == st) | (st == "00"))]
            bt = n7576[(n7576.dof_year == y) & ((n7576.state_code == st) | (st == "00"))]
            rows.append(vrow("sanderson_vs_dof_fulltext_land_grants", str(y), st, "land_grant", "count", float(a.sanderson_event.nunique()),
                             "sanderson_events", float(len(bt)), "dof_notes_in_scope"))
            rows.append(vrow("sanderson_vs_dof_fulltext_land_grants", str(y), st, "land_grant", "hectares", float(a.hectares_total.sum()),
                             "sanderson", float(b.hectares_total.sum()), "dof_fulltext_parsed"))
            rows.append(vrow("sanderson_vs_dof_fulltext_land_grants", str(y), st, "land_grant", "beneficiaries", float(a.beneficiaries.sum()),
                             "sanderson", float(b.beneficiaries.sum()), "dof_fulltext_parsed"))
    # row level: linked Sanderson grant events vs the DOF note's parsed hectares
    pair = L[(L.source == "sanderson") & L.dof_codNota.notna() & L.dof_year.isin(OVER) & (L.is_land_grant == 1)]
    pair = pair.groupby("sanderson_event").agg(ha_s=("hectares_total", "sum"), ha_d=("dof_hectares_total", "first"),
                                               b_s=("beneficiaries", "max"), b_d=("dof_beneficiaries", "first"),
                                               method=("dof_link_method", "first")).dropna(subset=["ha_d"])
    if len(pair):
        agree = (abs(pair.ha_s - pair.ha_d) <= 0.01 * pair[["ha_s", "ha_d"]].max(axis=1) + 0.5)
        rows.append(vrow("row_level_sanderson_vs_dof_fulltext_1973_76", "1973-1976", "00", "land_grant", "share_hectares_within_1pct",
                         float(agree.mean()), "linked_pairs", float(len(pair)), "pairs"))
        bagree = (pair.b_s == pair.b_d)
        rows.append(vrow("row_level_sanderson_vs_dof_fulltext_1973_76", "1973-1976", "00", "land_grant", "share_beneficiaries_equal",
                         float(bagree.mean()), "linked_pairs", float(pair.b_d.notna().sum()), "pairs"))
        for mth, g in pair.groupby("method"):
            ag = (abs(g.ha_s - g.ha_d) <= 0.01 * g[["ha_s", "ha_d"]].max(axis=1) + 0.5)
            rows.append(vrow("row_level_sanderson_vs_dof_fulltext_1973_76", "1973-1976", "00", mth, "share_hectares_within_1pct",
                             float(ag.mean()), "linked_pairs", float(len(g)), "pairs"))
    # 3./4. ledger vs INEGI EHM 2014 by state x presidential period (land grants)
    G = L[(L.is_land_grant == 1)].copy()
    G["term_signing"] = G["president_signing"].map(EHM_TERM_OF)
    G["term_dof"] = G["president_in_office_at_dof"].map(EHM_TERM_OF)
    for measure, col in (("hectares", "hectares_total"), ("beneficiaries", "beneficiaries")):
        e = ehm[ehm.measure == measure]
        for term in EHM_TERMS[2:12]:
            for basis in ("term_signing", "term_dof"):
                g = G[G[basis] == term]
                if term == "1989-1992":   # EHM data stop on 21 Feb 1992
                    d_ = g["signing_date"].fillna(g["dof_date"])
                    g = g[pd.to_datetime(d_) <= pd.Timestamp("1992-02-21")]
                src = "ledger_by_" + basis
                for st in [f"{i:02d}" for i in range(1, 33)] + ["00"]:
                    a = g[col].sum() if st == "00" else g.loc[g.state_code == st, col].sum()
                    b = e[(e.state_code == st) & (e.ehm_term == term)]["value"]
                    b = float(b.iloc[0]) if len(b) else np.nan
                    rows.append(vrow(f"ledger_vs_inegi_ehm2014_{measure}", term, st, "land_grant", measure, float(a), src, b,
                                     "EHM2014_table_" + ("9.50" if measure == "hectares" else "9.51"),
                                     "EHM 1989-1992 runs to 21 Feb 1992; ledger rows restricted to signing (else DOF) date <= 21 Feb 1992" if term == "1989-1992" else ""))
    # national resolutions (Sanderson events / DOF rows) and hectares by land class vs EHM table 9.49
    e49 = ehm[ehm.table == "9.49"]
    for term in EHM_TERMS[2:12]:
        g = G[G["term_signing"] == term]
        if term == "1989-1992":
            g = g[pd.to_datetime(g["signing_date"].fillna(g["dof_date"])) <= pd.Timestamp("1992-02-21")]
        ev_n = g["sanderson_event"].nunique() + int((g.source == "dof").sum())
        b = e49[(e49.measure == "resolutions") & (e49.ehm_term == term)]["value"]
        rows.append(vrow("ledger_vs_inegi_ehm2014_resolutions", term, "00", "land_grant", "count", float(ev_n),
                         "ledger_by_term_signing", float(b.iloc[0]) if len(b) else np.nan, "EHM2014_table_9.49"))
        for c in ("ha_riego", "ha_temporal", "ha_agostadero", "ha_monte", "ha_desertico", "ha_indefinido"):
            b = e49[(e49.measure == c) & (e49.ehm_term == term)]["value"]
            rows.append(vrow("ledger_vs_inegi_ehm2014_land_class", term, "00", "land_grant", c,
                             float(pd.to_numeric(g[c], errors="coerce").sum()), "ledger_by_term_signing",
                             float(b.iloc[0]) if len(b) else np.nan, "EHM2014_table_9.49"))
    # 5. parse yields by year (DOF notes in scope with full text)
    sc = pd.read_csv(DOF_AGRARIAN_NOTES_CSV, dtype={"state_code": str}, low_memory=False)
    sc = sc[(sc.in_ledger_scope == 1)]
    for y, g in sc.groupby("dof_year"):
        ft = g[g.has_fulltext == 1]
        rows.append(vrow("dof_fulltext_coverage", str(int(y)), "00", "in_scope", "share_with_fulltext", float(len(ft)), "with_fulltext",
                         float(len(g)), "in_scope_notes"))
        for c in ("signing_date", "president_signing", "hectares_total", "beneficiaries", "grant"):
            gg = ft if c != "hectares_total" else ft[ft.action_type.isin(LAND_GRANT_ACTIONS | {"expropiacion"})]
            rows.append(vrow("dof_parse_yield", str(int(y)), "00", "in_scope", f"share_{c}", float(gg[c].notna().sum()),
                             "parsed", float(len(gg)), "with_fulltext"))
    # 6. crosswalk match rates by period and state
    L["period"] = pd.cut(L["dof_year"].astype(float), [1900, 1934, 1952, 1976, 1992],
                         labels=["1916-1934", "1935-1952", "1953-1976", "1977-1992"]).astype(str)
    base = L[L.is_land_grant_action == 1]
    for per, g in base.groupby("period"):
        for st in sorted(g.state_code.dropna().unique()) + ["00"]:
            gg = g if st == "00" else g[g.state_code == st]
            named = gg.poblado.notna() | gg.ncpe_name.notna()
            rows.append(vrow("crosswalk_land_grant_actions", per, st, "land_grant", "share_named", float(named.sum()), "with_dof_name",
                             float(len(gg)), "actions"))
            rows.append(vrow("crosswalk_land_grant_actions", per, st, "land_grant", "share_matched_of_all", float(gg.nucleo_key.notna().sum()),
                             "matched_to_polygon_nucleo", float(len(gg)), "actions"))
            rows.append(vrow("crosswalk_land_grant_actions", per, st, "land_grant", "share_matched_of_named", float(gg.nucleo_key.notna().sum()),
                             "matched_to_polygon_nucleo", float(named.sum()), "named_actions"))
    # 7. how good is "president in office on the DOF date" as a proxy for the signer? (1975-92 texts)
    nn = pd.read_csv(DOF_AGRARIAN_NOTES_CSV, dtype={"state_code": str}, low_memory=False)
    nn = nn[(nn.in_ledger_scope == 1) & nn.president_signing_text.notna()].copy()
    nn["dof_date"] = pd.to_datetime(nn["dof_date"])
    starts = [president_on(x)[1] for x in nn["dof_date"]]
    nn["dsh"] = (nn["dof_date"] - pd.to_datetime(pd.Series(starts, index=nn.index))).dt.days
    nn["agree"] = nn["president_signing_text"] == nn["president_in_office_at_dof"]
    bins = [-1, 30, 60, 90, 180, 365, 100000]
    labels = ["0-30", "31-60", "61-90", "91-180", "181-365", ">365"]
    nn["bin"] = pd.cut(nn["dsh"], bins, labels=labels).astype(str)
    for b, g in nn.groupby("bin"):
        rows.append(vrow("president_inferred_from_dof_date_vs_text", "1975-1992", "00", f"days_since_handover_{b}",
                         "share_agree", float(g.agree.sum()), "agree", float(len(g)), "notes_with_signer_in_text"))
    rows.append(vrow("president_inferred_from_dof_date_vs_text", "1975-1992", "00", "all", "share_agree",
                     float(nn.agree.sum()), "agree", float(len(nn)), "notes_with_signer_in_text"))
    # 8. matched nucleos: land-grant hectares in the ledger vs the PROCEDE registered surface
    a = pd.read_csv(EJIDOS_ATTRIBUTES_CSV, dtype={"nucleo_key": str})
    surf = a.set_index("nucleo_key")["surface_registered_ha"]
    G2 = ledger[(ledger.is_land_grant == 1) & ledger.nucleo_key.notna()]
    for src, g in [("all", G2), ("sanderson", G2[G2.source == "sanderson"]), ("dof", G2[G2.source == "dof"])]:
        tot = g.groupby("nucleo_key")["hectares_total"].sum()
        has_dot = g[g.action_type.isin(["dotacion", "ncpe", "bienes_comunales", "restitucion"])].nucleo_key.unique()
        tot = tot[tot.index.isin(has_dot)]
        r_ = (tot / surf.reindex(tot.index)).replace([np.inf, -np.inf], np.nan).dropna()
        if len(r_):
            rows.append(vrow("matched_nucleo_granted_vs_registered_surface", "all", "00", src, "median_ratio",
                             float(r_.median()), "granted_ha/registered_ha", float(len(r_)), "nucleos_with_original_grant"))
            rows.append(vrow("matched_nucleo_granted_vs_registered_surface", "all", "00", src, "share_ratio_0.5_to_1.5",
                             float(((r_ >= 0.5) & (r_ <= 1.5)).mean()), "share", float(len(r_)), "nucleos_with_original_grant"))
    rows += source_validation(L)
    rows += stage_validation()
    out = pd.DataFrame(rows)
    return out


def source_validation(L: pd.DataFrame) -> list[dict]:
    """Where the values of the land grants come from, by INEGI term of the signer; DOF land grants with and without
    hectares by year; and identical amounts booked to two land grants of one DOF date (a double count, as when 03 read
    another village's grant from an appended note: Agiabampo's 15,548.5 ha on Tepetzintla)."""
    rows = []
    G = L[L.is_land_grant == 1].copy()
    G["term"] = G["president_signing"].map(EHM_TERM_OF).fillna("unattributed")
    for field, val in (("hectares_source", "hectares_total"), ("beneficiaries_source", "beneficiaries"), ("signing_source", None)):
        for term, g in G[G.source == "dof"].groupby("term"):
            for src, gg in g.groupby(g[field].fillna("none")):
                rows.append(vrow(f"ledger_value_source_{field.replace('_source', '')}", term, "00", "land_grant", f"share_rows_{src}",
                                 float(len(gg)), "dof_land_grant_rows", float(len(g)), "dof_land_grant_rows_in_term"))
                if val:
                    rows.append(vrow(f"ledger_value_source_{field.replace('_source', '')}", term, "00", "land_grant", f"share_{val}_{src}",
                                     float(gg[val].sum()), val, float(g[val].sum()), f"{val}_in_term"))
    D = L[(L.source == "dof") & (L.is_land_grant_action == 1)]
    for y, g in D.groupby("dof_year"):
        lg = g[g.is_land_grant == 1]
        rows.append(vrow("dof_land_grants_with_hectares", str(int(y)), "00", "land_grant", "share_with_hectares",
                         float(lg.hectares_total.notna().sum()), "with_hectares", float(len(lg)), "land_grant_rows"))
        rows.append(vrow("dof_land_grants_with_hectares", str(int(y)), "00", "land_grant", "share_without_text_recovered_from_scan",
                         float(((lg.has_fulltext == 0) & (lg.hectares_source == "dof_scan")).sum()), "recovered_from_scan",
                         float((lg.has_fulltext == 0).sum()), "land_grant_rows_without_text"))
        rows.append(vrow("dof_land_grants_with_hectares", str(int(y)), "00", "title_land_grant", "n_not_land_grant_in_print",
                         float((g.land_grant_printed == 0).sum()), "land_grant_printed_0", float(len(g)), "title_land_grant_rows"))
    dd = L[(L.source == "dof") & (L.is_land_grant == 1) & (L.hectares_total >= 1)].copy()
    dd["ha_key"] = dd["hectares_total"].round(4)
    dup = dd[dd.duplicated(["dof_date", "ha_key"], keep=False)]
    for (d, h), g in dup.groupby(["dof_date", "ha_key"]):
        rows.append(vrow("duplicate_amount_same_dof_date", str(pd.Timestamp(d).date()), "00", "land_grant", "hectares", float(h),
                         "codNotas " + " ".join(str(int(c)) for c in g.dof_codNota), float(len(g)), "rows",
                         note="villages: " + "; ".join(str(x) for x in g.poblado.fillna(g.ncpe_name))))
    rows.append(vrow("duplicate_amount_same_dof_date", "1976-1992", "00", "land_grant", "n_groups", float(dup.groupby(["dof_date", "ha_key"]).ngroups),
                     "groups_of_rows_with_the_same_hectares_on_one_dof_date", float(len(dup)), "rows"))
    # reprints (flag_reprints): later publications of one resolution, left out of the land-grant counts
    R = L[L.duplicate_of.notna()]
    first = L.set_index("action_id")
    for r in R.itertuples():
        rows.append(vrow("reprint_left_out", str(pd.Timestamp(r.dof_date).date()), r.state_code, "land_grant", "hectares",
                         float(r.hectares_total), f"{r.action_id} (reprint)", float(first.at[r.duplicate_of, "hectares_total"]),
                         f"{r.duplicate_of} (first publication, {pd.Timestamp(first.at[r.duplicate_of, 'dof_date']).date()})",
                         note=f"{r.poblado if isinstance(r.poblado, str) else r.ncpe_name}; signed {r.signing_date}"))
    for term, g in R.assign(term=R.president_signing.map(EHM_TERM_OF)).groupby("term"):
        rows.append(vrow("reprint_left_out", term, "00", "land_grant", "n_rows_hectares", float(len(g)), "reprint_rows",
                         float(g.hectares_total.sum()), "hectares_left_out"))
    # re-resolutions: same state, village and surface signed again on another date (kept; counted in both terms)
    K = L[(L.source == "dof") & (L.is_land_grant == 1) & L.hectares_total.notna()].copy()
    K["name"] = [(name_variants(p if isinstance(p, str) else n) or [""])[0] for p, n in zip(K.poblado, K.ncpe_name)]
    K = K[K.name != ""]
    K["ha_key"] = K.hectares_total.round(2)
    rr = K[K.duplicated(["state_code", "name", "ha_key"], keep=False)].sort_values("dof_date")
    for (st, nm, h), g in rr.groupby(["state_code", "name", "ha_key"]):
        rows.append(vrow("same_grant_signed_again", " ".join(str(pd.Timestamp(d).date()) for d in g.dof_date), st, "land_grant",
                         "hectares", float(h), " ".join(g.action_id), float(len(g)), "rows",
                         note=f"{nm}; signed " + ", ".join(str(x) for x in g.signing_date) + "; " + ", ".join(g.president_signing.astype(str))))
    return rows


def _q(x: pd.Series) -> dict:
    x = pd.to_numeric(x, errors="coerce").dropna()
    if not len(x):
        return {}
    return {"n": len(x), "mean": x.mean(), "p10": x.quantile(.1), "p25": x.quantile(.25), "median": x.median(),
            "p75": x.quantile(.75), "p90": x.quantile(.9)}


def stage_validation() -> list[dict]:
    """File-history (stage) checks on the DOF land-grant resolutions with text, 1973-92: yield per field and
    year, lag distributions by signer, the share of files filed before the signer's term, and the hand checks."""
    rows = []
    n = pd.read_csv(DOF_AGRARIAN_NOTES_CSV, dtype={"state_code": str}, low_memory=False)
    lg = n[(n.in_ledger_scope == 1) & n.action_type.isin(LAND_GRANT_ACTIONS) & n.doc_type.isin(["resolucion", "sentencia"])
           & (n.has_fulltext == 1)].copy()
    gov = lg.action_type.isin(["dotacion", "ampliacion", "restitucion"])   # actions with a governor instance
    for y, g in lg.groupby("dof_year"):
        gg = g[g.action_type.isin(["dotacion", "ampliacion", "restitucion"])]
        for f, base in (("petition_date", g), ("cca_approval_date", g), ("governor_name", g), ("cam_dictamen_date", gg),
                        ("mandamiento_date", gg), ("mandamiento_outcome", gg)):
            rows.append(vrow("stage_field_yield", str(int(y)), "00", "land_grant" if base is g else "governor_instance",
                             f"share_{f}", float(base[f].notna().sum()), "parsed", float(len(base)), "resolutions_with_text"))
    for f, base in (("petition_date", lg), ("cca_approval_date", lg), ("governor_name", lg), ("cam_dictamen_date", lg[gov]),
                    ("mandamiento_date", lg[gov]), ("mandamiento_outcome", lg[gov])):
        rows.append(vrow("stage_field_yield", "1973-1992", "00", "all", f"share_{f}", float(base[f].notna().sum()),
                         "parsed", float(len(base)), "resolutions_with_text"))
    for o, k in lg[gov]["mandamiento_outcome"].value_counts().items():
        rows.append(vrow("stage_mandamiento_outcome", "1973-1992", "00", "governor_instance", f"share_{o}", float(k),
                         "resolutions", float(gov.sum()), "governor_instance_resolutions_with_text"))
    ok = lg[(lg.stage_order_flag == 0) & (lg.signer_body == "president")]
    for lag in ("lag_petition_to_mandamiento_days", "lag_mandamiento_to_signing_days", "lag_signing_to_publication_days",
                "lag_petition_to_signing_days"):
        groups = [("all", ok)] + [(p, g) for p, g in ok.groupby("president_signing")]
        for who, g in groups:
            for stat, v in _q(g[lag]).items():
                rows.append(vrow("stage_lag_days", "1973-1992", "00", who, f"{lag}_{stat}", float(v), "days", np.nan, ""))
    inh = lg[lg.petition_predates_signer_term.notna()]
    for who, g in [("all", inh)] + [(p, g) for p, g in inh.groupby("president_signing")]:
        rows.append(vrow("petition_predates_signer_term", "1973-1992", "00", who, "share_inherited",
                         float(g.petition_predates_signer_term.astype(float).sum()), "files_filed_before_signer_took_office",
                         float(len(g)), "resolutions_with_petition_date_or_bound"))
    if STAGE_HANDCHECK_CSV.exists():
        h = pd.read_csv(STAGE_HANDCHECK_CSV)
        for (smp, f), g in h.groupby(["sample", "field"]):
            ext = g[g.extracted.notna()]
            pres = g[g.truth.notna()]
            rows.append(vrow("stage_handcheck", smp, "00", f, "precision", float((ext.extracted == ext.truth).sum()),
                             "correct", float(len(ext)), "extracted"))
            rows.append(vrow("stage_handcheck", smp, "00", f, "recall", float((pres.extracted == pres.truth).sum()),
                             "found", float(len(pres)), "present"))
    return rows


if __name__ == "__main__":
    main()
