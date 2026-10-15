"""
Re-read the Diario Oficial texts of the DOF land-grant resolutions of the ledger (Nov 1976 - 1992) with rules that fix
the ways 03_parse_dof_agrarian.py misreads them, and write the corrections that 04_build_agrarian_ledger.py applies.

Population: the DOF land-grant notes of the ledger that have a SIDOF full text, read from 03's notes table (not from the
ledger, which 04 builds from this script's output): published after Sanderson's last date, in the ledger's scope, granted
or an undecided resolucion (dof_agrarian_utils.dof_ledger_land_grant_notes; 5,975 notes). Two parts:
  - the 197 notes whose hectares 03 did not find ("targets"): full recovery (rules, words, hand readings on the text or on
    the scanned page, LLM step when credit exists), reason_missed, not-a-land-grant verdicts;
  - the 5,778 notes 03 parsed with hectares ("spillover"): the same rules on the note's own resolutive points; where they
    read a different total, 03 misread it (hand check below), and where the text holds several notes 03's beneficiaries
    and signing date come from the appended note.

Inputs
  config.DOF_AGRARIAN_NOTES_CSV    03's notes table (the population, 03's values and title fields)
  config.SANDERSON_DTA             only for Sanderson's last date (the ledger's DOF rows start the next day)
  config.DOF_SIDOF_FULLTEXT_DIR    SIDOF full texts (sidof_fulltext_<year>.jsonl.gz); provenance = file + line number
  <WEB_DISCOVERY_DIR>/dof_scanned_editions/   scanned DOF editions (OCR text, one JSON line per PDF page) for notes
                                   whose SIDOF text is truncated, scrambled or contradicts its title (--fetch-scans)

Outputs (config.LAND_REFORM_DIR)
  dof_reparsed_texts_1976_1992.csv   one row per target note: reason_missed (why 03 found no hectares), hectares,
                                     hectares in words, land classes, beneficiaries, grant, signing date, signer,
                                     method (rules / rules_words / llm / hand), confidence, text source and provenance, note
                                     (ledger_* columns = 03's values as the ledger carried them before the corrections)
  dof_text_corrections_1976_1992.csv one row per note of the population: the hectares, land classes, beneficiaries,
                                     signing date, signer and president that 04 writes into the ledger, the source of
                                     each (dof_text_03 = 03 unchanged, dof_text_reparse = these rules or a hand reading on
                                     the text, dof_scan = read on the scanned page), 03's value (*_03), this script's
                                     reading (*_reparse), the 03 failure mechanism, land_grant_printed / reason
                                     (build_corrections states the rules)
  dof_reparsed_texts_validation.csv  (a) hand check of 30 random recovered notes (truth typed by hand, read back on
                                     every run, never overwritten); (b) "spillover": 03's hectares vs these rules on every
                                     land-grant note that HAS hectares, by failure mechanism, with a hand-checked sample
  dof_reparse_llm_cache/             every LLM answer (JSON), so re-runs are free and auditable (created on the first answer)

Why 03 missed (reason_missed; the first failing step of 03's pipeline, found by replaying 03's own functions with one
fix at a time):
  multi_document_text        SIDOF stored the note's resolution followed by the next DOF note(s); 03 reads the LAST
                             "resuelve" before the LAST signature, i.e. the appended note (a privacion de derechos, an
                             inafectabilidad acuerdo, ...), which grants no land
  operative_mislocated       a later "resuelve" inside the resolutive points ("ni resuelve los conflictos de limites"),
                             or no "resuelve" at all, moved 03's operative section past the grant
  verb_variant               the grant verb is not in 03's list: "se reconocen y titula", "se conoce y titula", "es
                             procedente el reconocimiento ... una superficie", "sedota", "se nota", "se data", "se dot",
                             "dotandose", "se dotar", "deberan otorgarse", "se toman ... para la creacion", "se decreta la
                             afectacion", typos such as "se reconcoe", "se renonoce", "se conceda"
  amount_format:<subtype>    the amount is printed in a form 03's regexes skip: missing / doubled / stray hyphens, a
                             space or dot for a hyphen, hyphen as thousands separator, a decimetre group, 3-digit
                             groups, two groups only, OCR letters inside digits (o, l, i, s), no unit or "mas." / "hass."
  text_garbled_or_truncated  the SIDOF text lacks the resolutive points (cut, or pages of another note spliced in)
  not_a_land_grant:<type>    the body is not a land grant (rights resolution, inafectabilidad, division, colonia,
                             initiation notice); the ledger counts it as a land grant from its title
Rules (this script)
  document     the text is split at each closing block ("Dada en ... <date> ... Rubrica"); the note's own document is
               the first one. Its resolutive section starts at the first "resuelve" followed by "primero/unico".
  grant        the first resolutive point with a grant anchor (03's verbs plus the variants above, "se-concede" and typos
               such as "se concedo", "se corcede", "concedase", "que concede al poblado") followed by an
               amount. Every reading of the printed digits is generated (standard ha-a-ca groups, thousands groups, all
               hyphen-less splits, OCR letters o/l/i/s -> 0/1/1/5, another OCR letter for the last hyphen as in
               "10,470-32j51"; a comma is never read as the hectare/area separator when hyphens follow, so "20,90-77-40"
               has no structured reading) and compared with the amount written in words
               (hectareas, areas, centiareas, decimetros cuadrados). Accepted by rules when a reading agrees with the
               words within 1.5 m2 (or at the printed precision of the words), or when there are no words and the
               digits have one standard reading (method rules); words without usable digits -> rules_words. Digit/word
               conflicts, affectation-type anchors ("se decreta la afectacion de ..."; the grant may be a part) and
               unparsed grants go to the LLM: two independent reads of the resolutive points (llm_tables.READERS), a
               third (TIEBREAK) when they disagree; method llm.
  classes      03's classify_window on the words after the total and after each component amount (03's logic).
  beneficiaries 03's BENEF_RE on the resolutive section (after 03's fix_digits, "2o4 capacitados"), else 03's census
               count; signing date / signer: 03's parse_signing on the note's own document (not on an appended note).
Scanned editions (only with --fetch-scans): note record https://sidof.segob.gob.mx/dof/sidof/notas/nota/<codNota> gives
  codDiario; https://sidof.segob.gob.mx/dof/sidof/documentos/pdf/<codDiario> is the whole edition with an OCR layer. The
  PDF goes to a local folder outside Dropbox (--scan-tmp), its pages are written with `pdftotext -layout` to
  dof_scanned_editions/<date>_<codEdicion>_<codDiario>.jsonl.gz (one JSON line per page) with a MANIFEST.csv row, the
  pages that hold the note are rendered to PNG for reading, and the PDF is deleted. An edition already stored is
  reused. >= 1 s between requests.

Run
  python -I code/06-land/06_reparse_dof_texts.py                 # parse; LLM only for notes not yet cached
  python -I code/06-land/06_reparse_dof_texts.py --offline       # cached LLM answers only, no network
  python -I code/06-land/06_reparse_dof_texts.py --fetch-scans   # also download / reuse scanned editions
  Order: 03 -> 06 (--offline) -> 04. 05 (scanned editions) is independent of 06; 04 reads both.
  LLM_BUDGET_USD caps the cumulative LLM ledger (llm_tables); --max-new-usd caps this run's new spend (default 4.5).
"""
from __future__ import annotations

import argparse
import base64
import csv
import datetime as dt
import fcntl
import gzip
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
from rapidfuzz import fuzz

HERE = Path(__file__).resolve().parent
CODE_DIR = HERE.parents[0]
sys.path.insert(0, str(CODE_DIR))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(CODE_DIR / "05-investment"))
from config import (  # noqa: E402
    DOF_AGRARIAN_NOTES_CSV, DOF_REPARSED_TEXTS_CSV, DOF_REPARSED_VALIDATION_CSV, DOF_SIDOF_FULLTEXT_DIR,
    DOF_TEXT_CORRECTIONS_CSV, LAND_REFORM_DIR, SANDERSON_DTA, WEB_DISCOVERY_DIR, openai_api_key,
)
from dof_agrarian_utils import (  # noqa: E402
    dof_ledger_land_grant_notes, fulltext_files, html_to_text, norm, sanderson_last_dof_date,
)


def _load_03():
    spec = importlib.util.spec_from_file_location("parse_dof_03", HERE / "03_parse_dof_agrarian.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P03 = _load_03()

OUT_CSV = DOF_REPARSED_TEXTS_CSV
VALID_CSV = DOF_REPARSED_VALIDATION_CSV
CORR_CSV = DOF_TEXT_CORRECTIONS_CSV
LLM_CACHE = LAND_REFORM_DIR / "dof_reparse_llm_cache"
SCAN_DIR = WEB_DISCOVERY_DIR / "dof_scanned_editions"
SCAN_MANIFEST = SCAN_DIR / "MANIFEST.csv"
NOTE_RECORDS = SCAN_DIR / "note_records.jsonl"        # SIDOF note records (codDiario, page, section), no HTML
SIDOF = "https://sidof.segob.gob.mx/dof/sidof"
UA = "Mozilla/5.0 (academic research; TapadosPRI land-reform project)"
SEED = 20261014
CLASSES = P03.CLASSES                                 # riego, temporal, agostadero, monte, desertico, indefinido

# Hand-located PDF pages (1-based) of notes whose scan the OCR search could not place unambiguously; each entry
# was checked on the page image (see README "Re-parsed texts").
SCAN_PAGE_OVERRIDES: dict[int, list[int]] = {}

# Hand readings, used where the rules cannot accept a value and the LLM is unavailable (on 2026-10-14 the project
# OpenAI key had no credit, as for the 1986/2004 agency tables in 05-investment). Each entry was read in the printed
# text (SIDOF full text, or the scanned page image for source "scan") and states the evidence. Digit/word conflicts are
# settled by the other places where the resolution repeats the surface (considerandos, the governor's mandamiento,
# component sums). Values: hectares (total granted to the poblado), optional land classes and beneficiaries.
HAND_READINGS: dict[int, dict] = {
    4849916: dict(hectares=2877.3359, source="sidof_text", evidence="digits 2,887-33-59 vs words 'dos mil ochocientas setenta y "
                  "siete hectareas, treinta y tres areas y cincuenta y nueve centiareas'; the considerandos give 2,877-33-59 three times"),
    4652783: dict(hectares=2951.20, source="sidof_text", evidence="digits 2,951-20-00 vs words '... cincuenta y una hectareas veinte "
                  "centiareas'; the considerandos give 2,951-20-00 twice (the words slip areas -> centiareas)"),
    4655573: dict(hectares=46.424015, source="sidof_text", evidence="digits '42-40.15' lost the hectare group; words 'cuarenta y "
                  "seis hectareas, cuarenta y dos areas, cuarenta centiareas, quince decimetros'; considerandos 46-42-40.15 twice"),
    4729040: dict(hectares=1378.20, source="sidof_text", evidence="digits 1,378-20-00 vs words 'un mil trescientos ochenta y siete "
                  "hectareas'; the considerandos give 1,378-20-00"),
    4669849: dict(hectares=2289.66448, source="sidof_text", evidence="digits '2,289-6644.8' vs words '... setenta y seis areas, "
                  "cuarenta y cuatro centiareas, ocho decimetros'; the resultandos and considerandos give 2,289-66-44.8 four times"),
    4802781: dict(hectares=64.547934, source="sidof_text", evidence="digits 64-54-79.34 vs words 'setenta y cuatro hectareas ...'; "
                  "the considerandos give 64-54-79.34 twice"),
    4806895: dict(hectares=1553.478570, source="sidof_text", evidence="digits '1,553-487-85.70' vs words 'mil quinientas cincuenta "
                  "y tres hectareas, cuarenta y siete areas, ochenta y cinco centiareas, setenta decimetros'; considerandos 1,553-47-85.70 thrice"),
    4912226: dict(hectares=690.0, source="sidof_text", evidence="digits 69-00-00 vs words 'seiscientas noventa hectareas'; the "
                  "considerandos give 690-00-00 twice"),
    4837823: dict(hectares=350.846529, source="sidof_text", evidence="digits '350-8445.29' vs words '... ochenta y cuatro areas "
                  "sesenta y cinco centiareas veintinueve decimetros'; considerandos 350-84-65.29 twice"),
    4704843: dict(hectares=3917.6859, source="sidof_text", evidence="digits '3,91748-59' vs words 'tres mil novecientas diecisiete "
                  "hectareas, sesenta y ocho areas, cincuenta y nueve centiareas'; mandamiento and considerandos give 3,917-68-59 thrice"),
    4850405: dict(hectares=135.0, classes={"temporal": 135.0}, source="sidof_text", evidence="'se decreta la afectacion de 135-00-00 "
                  "has. (ciento treinta y cinco hectareas), de las cuales 129-00-00 has. ... de temporal y 6-00-00 has. de humedad' = the "
                  "complement of the ampliacion granted to Troncones (humedad counts as temporal, as in 03)"),
    4755264: dict(hectares=274.46, classes={"temporal": 274.46}, source="sidof_text", evidence="of 550-47-06 has. affected, "
                  "'274-46-00 has. (doscientas sesenta y cuatro hectareas, cuarenta y seis areas), son de temporal, que se destinan para "
                  "la dotacion definitiva' of El Botho; the six fractions listed sum to 274.46 and the remainder reserved for Capula is "
                  "276-01-06 (550.4706 - 274.46), so the words are the slip"),
    4620261: dict(hectares=9100.0, classes={"agostadero": 9100.0}, source="sidof_text", evidence="of 18,200-00-00 has. of agostadero "
                  "arido affected, 9,100-00-00 go to the NCPE 'La Gallina' and 'las restantes 9,100-00-00 has. (nueve mil cien "
                  "hectareas) ... se concede para la creacion del nuevo centro de poblacion ejidal ... Ignacio Camargo'"),
    # ---- read on the scanned page images (SIDOF text truncated, scrambled, or of another note)
    4855497: dict(hectares=225.0, classes={"riego": 225.0}, beneficiaries=43, source="scan", pdf_pages=[155],
                  evidence="SEGUNDO '225-00-00 Has., (DOSCIENTAS VEINTICINCO HECTAREAS) de riego'; SEXTO '43 capacitados' (SIDOF "
                  "dropped the SEGUNDO point)"),
    4855499: dict(hectares=595.0, classes={"riego": 595.0}, beneficiaries=117, source="scan", pdf_pages=[157],
                  evidence="SEGUNDO '595-00-00 Has. (QUINIENTOS NOVENTA Y CINCO HECTAREAS) de riego'; SEXTO '117 capacitados'"),
    4855495: dict(hectares=100.0, classes={"riego": 100.0}, beneficiaries=18, source="scan", pdf_pages=[152, 153],
                  confidence="medium", evidence="the printed resolution also lacks its SEGUNDO (grant) point; CONSIDERANDO SEGUNDO: "
                  "'se dispone de una superficie de 100-00-00 Has. de riego'; 18 capacitados"),
    4830133: dict(hectares=900.0, classes={"agostadero": 900.0}, beneficiaries=65, signing_date="1979-07-23",
                  signer="Jose Lopez Portillo", source="scan", pdf_pages=[52],
                  evidence="SEGUNDO '900-00-00 Has. (NOVECIENTAS HECTAREAS), de terrenos de agostadero de mala calidad'; TERCERO "
                  "'65 capacitados'; signature in the SIDOF closing, whose publication clause names La Parrilla"),
    4850766: dict(hectares=3239.20, beneficiaries=200, signing_date="1980-03-05", signer="Jose Lopez Portillo", source="scan",
                  pdf_pages=[24, 25, 26], evidence="PRIMERO '3,239-20-00 Has. (TRES MIL DOSCIENTAS TREINTA Y NUEVE HECTAREAS, "
                  "VEINTE AREAS, CERO CENTIAREAS), de terrenos en general'; census 200 comuneros; dada 5 Mar 1980"),
    4609879: dict(hectares=5016.140610, classes={"monte": 5016.140610}, beneficiaries=26, signing_date="1980-11-21",
                  signer="Jose Lopez Portillo", source="scan", pdf_pages=[51, 52],
                  evidence="TERCERO '5016-14-06.10 Has., (Cinco mil dieciseis hectareas, catorce areas, seis centiareas, diez "
                  "decimetros cuadrados) de terreno de monte alto con bosque maderable'; CUARTO '26 capacitados'"),
    4650253: dict(hectares=195.733491, classes={"temporal": 195.733491}, beneficiaries=30, signing_date="1981-03-17",
                  signer="Jose Lopez Portillo", source="scan", pdf_pages=[40, 41],
                  evidence="PRIMERO '195-73-34.91 Has. (CIENTO NOVENTA Y CINCO HECTAREAS, SETENTA Y TRES AREAS, TREINTA Y CUATRO "
                  "CENTIAREAS, NOVENTA Y UNO DECIMETROS CUADRADOS), de temporal'; 30 comuneros in the census"),
    4677758: dict(hectares=570.0, classes={"agostadero": 570.0}, beneficiaries=30, signing_date="1981-06-01",
                  signer="Jose Lopez Portillo", source="scan", pdf_pages=[25, 26, 27],
                  evidence="TERCERO '570-00-00 Has. (QUINIENTAS SETENTA HECTAREAS), de agostadero cerril con 30% laborable'; CUARTO "
                  "'30 capacitados' (the SIDOF text read the governor's mandamiento quoted in the resultandos, 4,951 ha)"),
    4684234: dict(hectares=690.0, classes={"agostadero": 690.0}, beneficiaries=91, signing_date="1981-06-10",
                  signer="Jose Lopez Portillo", source="scan", pdf_pages=[23, 28, 30],
                  evidence="pages printed out of order (28, 23, 30); TERCERO '690-00-00 Has., (SEISCIENTAS NOVENTA HECTAREAS), de "
                  "agostadero de buena calidad'; CUARTO '91 capacitados'; dada 10 Jun 1981"),
    4687425: dict(hectares=1300.0, classes={"temporal": 1300.0}, beneficiaries=46, source="scan", pdf_pages=[48, 49],
                  confidence="medium", evidence="the DOF printed only the PRIMERO point (the next note follows); CONSIDERANDO "
                  "SEGUNDO 'se afecta la superficie de 1,300-00-00 Has. de humedad con un 70% laborable ... para los usos "
                  "colectivos de los 46 campesinos capacitados'; signing date not printed"),
    4699446: dict(hectares=92.3351, classes={"agostadero": 92.3351}, beneficiaries=34, signing_date="1981-09-20",
                  signer="Jose Lopez Portillo", source="scan", pdf_pages=[68, 69, 70],
                  evidence="TERCERO '92-33-51 Has., (NOVENTA Y DOS HECTAREAS, TREINTA Y TRES AREAS, CINCUENTA Y UNA CENTIAREAS), de "
                  "agostadero cerril'; CUARTO '34 capacitados'"),
    4754701: dict(hectares=325.6594, classes={"agostadero": 325.6594}, beneficiaries=67, signing_date="1985-07-30",
                  signer="Miguel de la Madrid Hurtado", source="scan", pdf_pages=[92],
                  evidence="TERCERO '325-65-94 Has. (trescientas veinticinco hectareas, sesenta y cinco areas, noventa y cuatro "
                  "centiareas) de agostadero'; CUARTO '67 capacitados'"),
    4755277: dict(hectares=283.0101, classes={"agostadero": 283.0101}, beneficiaries=28, signing_date="1985-07-30",
                  signer="Miguel de la Madrid Hurtado", source="scan", pdf_pages=[78, 79, 80],
                  evidence="TERCERO '283-01-01 Has. (doscientas ochenta y tres hectareas, una area, una centiarea) de agostadero de "
                  "buena calidad'; CUARTO '28 capacitados'"),
    4774713: dict(hectares=78.62, classes={"temporal": 78.62}, beneficiaries=165, signing_date="1985-10-02",
                  signer="Miguel de la Madrid Hurtado", source="scan", pdf_pages=[29, 30, 83, 85, 86],
                  evidence="TERCERO '78-62-00 Has., (setenta y ocho hectareas, sesenta y dos areas), de diversas calidades': 34-62-00 "
                  "de humedad + 16-00-00 and 28-00-00 de temporal (humedad counts as temporal, as in 03); CUARTO '165 capacitados'"),
    4799816: dict(hectares=4215.4998, classes={"agostadero": 4215.4998}, beneficiaries=53, signing_date="1986-06-20",
                  signer="Miguel de la Madrid Hurtado", source="scan", pdf_pages=[114, 115],
                  evidence="TERCERO '4,215-49-98 Has., (cuatro mil doscientas quince hectareas, cuarenta y nueve areas, noventa y "
                  "ocho centiareas), de agostadero en terrenos aridos'; CUARTO '53 capacitados'"),
    4803667: dict(hectares=725.0, classes={"temporal": 725.0}, beneficiaries=101, signing_date="1986-07-03",
                  signer="Miguel de la Madrid Hurtado", source="scan", pdf_pages=[34, 63, 64],
                  evidence="continued from p. 34 to p. 63; TERCERO '725-00-00 Has. (setecientas veinticinco hectareas) de temporal'; "
                  "for the 101 capacitados of the 1967 dotacion (complementary grant, no new census)"),
    4729703: dict(hectares=260.6558, classes={"riego": 260.6558}, beneficiaries=40, signing_date="1988-03-30",
                  signer="Miguel de la Madrid Hurtado", source="scan", pdf_pages=[224, 225, 226],
                  evidence="SEGUNDO '260-65-58 Has. (doscientas sesenta hectareas, sesenta y cinco areas, cincuenta y ocho "
                  "centiareas) de riego'; QUINTO '40 capacitados'; signature in the SIDOF closing, which names El Horizonte"),
    # ---- not land grants: the printed note itself is another act (heading and body disagree in print, or SIDOF's title)
    4641805: dict(is_land_grant=False, body_type="rights_resolution", source="scan", pdf_pages=[43],
                  evidence="printed heading 'Resolucion sobre privacion de derechos agrarios y nuevas adjudicaciones ... Agua Linda "
                  "(Reg. 17276)'; SIDOF's index title ('Segunda Ampliacion de Ejido') is wrong"),
    4686054: dict(is_land_grant=False, body_type="rights_resolution", source="scan", pdf_pages=[14],
                  evidence="printed heading 'dotacion de tierras ... El Ocotal (Reg. 18940)' over a privacion de derechos (VISTO and "
                  "resolutive points)"),
    4686264: dict(is_land_grant=False, body_type="rights_resolution", source="scan", pdf_pages=[24],
                  evidence="printed heading 'dotacion de tierras ... El Triunfo (Reg. 19002)' over a privacion de derechos"),
    4686431: dict(is_land_grant=False, body_type="rights_resolution", source="scan", pdf_pages=[7],
                  evidence="reprint (17 Sep 1981) of 4686264: same Reg. 19002, same heading, same privacion de derechos"),
    4711441: dict(is_land_grant=False, body_type="division", source="scan", pdf_pages=[176],
                  evidence="printed heading 'segunda ampliacion de ejido ... San Miguel El Alto y su anexo' over a VISTO for the "
                  "'division de ejido'"),
    4733844: dict(is_land_grant=False, body_type="division", source="scan", pdf_pages=[34],
                  evidence="printed heading 'dotacion de ejido ... Zipiajo y su anexo (Reg. 5333)' over a VISTO for the 'division de "
                  "ejido'"),
    4812750: dict(is_land_grant=False, body_type="initiation_notice", source="scan", pdf_pages=[34],
                  evidence="printed heading 'reconocimiento y titulacion de bienes comunales ... San Miguel Mixtepec' over 'ASUNTO: Se "
                  "inicia de oficio expediente' (an initiation notice)"),
    4698006: dict(is_land_grant=False, body_type="rights_resolution", source="scan", pdf_pages=[8],
                  evidence="print matches SIDOF: 1991 re-resolution of the 1965 ampliacion (282 ha) after an amparo; re-allocates 22 "
                  "units, grants no new surface"),
    # ---- grants whose resolutive points were never printed (not recoverable from the DOF)
    4862778: dict(hectares=None, source="scan", pdf_pages=[88, 89], evidence="the printed DOF itself splices Cuevecillas' "
                  "considerandos with the resolutive points of San Antonio Ocotlan's privacion de derechos; no grant printed"),
    4695746: dict(hectares=None, source="scan", pdf_pages=[47, 48], evidence="the printed note breaks off in the census list "
                  "('4.-Francisco Lorenzo') and the next note starts; no resolutive points printed in this edition"),
    4640010: dict(hectares=None, source="scan", pdf_pages=[9, 10], reason="text_garbled_or_truncated",
                  reason_detail="printed_edition_spliced_with_another_act", evidence="the printed NCPE 'Aquiles Serdan' (Reg. 16684) "
                  "runs straight into a colonia desincorporation acuerdo (lot 5, Colonia Agricola Rio Mayo); its own resolutive "
                  "points were not printed"),
    4855571: dict(hectares=None, source="scan", pdf_pages=[], evidence="quinta seccion, p. 36: the scanned edition (312 pages) "
                  "repeats the cuarta seccion and lacks the quinta; SIDOF marks '*****falta texto*****'"),
    # ---- notes that 03 parsed WITH hectares where both 03 and the rules misread the grant (used by the corrections table).
    # Three are multi-document texts (03 read the appended note) whose own grant has digits and words in conflict; one
    # prints a malformed amount in the resolutive point.
    4836404: dict(hectares=2490.7740, source="sidof_text", confidence="medium", evidence="resolutive point '20,90-77-40 has. de "
                  "diversas calidades' (no words; 03 read 90-77-40, the rules have no reading); the considerando gives the NCPE "
                  "'una superficie total de 2,490-77.40 has. de diversas calidades', taken from 4,943-81-00 has. available"),
    4751725: dict(hectares=520.0, classes={"riego": 520.0}, beneficiaries=50, source="sidof_text", evidence="digits '20-00-00 has., "
                  "(quinientas veinte hectareas) de riego' lost the leading 5; the considerandos and the SEXTO point give 520-00-00 "
                  "has. six times; 03 read the appended note (5.06 ha)"),
    4799847: dict(hectares=4895.67, beneficiaries=184, source="sidof_text", evidence="digits 4,895-67-00 vs words '... noventa y "
                  "cinco hectareas, setenta y siete areas'; the considerandos give 4,895-67-00 twice and 4,895-67 once, so the words "
                  "are the slip; 03 read the appended note (4,223.76 ha)"),
    4764050: dict(hectares=867.7107, classes={"riego": 760.0, "temporal": 107.7107}, beneficiaries=78, source="sidof_text",
                  evidence="digits 867-71-07 vs words 'ochocientas setenta y siete hectareas, setenta y un areas, siete "
                  "centiareas'; the components 760-00-00 has. de riego + 107-71-07 has. de temporal sum to 867-71-07, so the words "
                  "are the slip; 03 read an appended note (389.59 ha)"),
    4675780: dict(signing_date="1987-08-05", signer="Miguel de la Madrid Hurtado", source="sidof_text", evidence="own closing "
                  "'a los cinco dia del mes de agosto de mil novecientos ochenta ochenta y siete.- ... miguel de la madrid h.' (the "
                  "doubled 'ochenta' defeats the date rule); the text runs on into San Isidro's resolution (97-63-99.05 has.), which "
                  "03 read as this note's grant"),
}

# ------------------------------------------------------------------------------------------------ text loading
def load_population() -> pd.DataFrame:
    """The DOF land-grant notes of the ledger that have a full text, as 03 parsed them (dof_ledger_land_grant_notes:
    published after Sanderson's last date, in scope, granted or an undecided resolucion). Read from 03's notes table, not
    from the ledger, because 04 applies this script's corrections to the ledger. Ledger-named columns: dof_title, and
    president_ledger = the president the ledger gives the note from 03's parse (the signer in the text, else, unless a
    tribunal / CAM / SRA signed, the president in office on the DOF date)."""
    n = pd.read_csv(DOF_AGRARIAN_NOTES_CSV, low_memory=False, dtype={"state_code": str})
    pop = dof_ledger_land_grant_notes(n, sanderson_last_dof_date(SANDERSON_DTA))
    pop = pop[pop.has_fulltext == 1].copy()
    pop["dof_title"] = pop["title"]
    nonpres = pop["president_source"].astype(str).str.startswith("not_presidential")
    pop["president_ledger"] = pop["president_signing"].where(pop["president_signing"].notna(),
                                                             pop["president_in_office_at_dof"].where(~nonpres))
    return pop.sort_values(["dof_date", "codNota"]).reset_index(drop=True)


def load_texts(cods: set[int], years: set[int]) -> dict[int, dict]:
    """codNota -> {'text', 'file', 'line', 'record'}: the SIDOF full text with its provenance (file, 1-based line)."""
    out = {}
    for fn in fulltext_files(DOF_SIDOF_FULLTEXT_DIR):
        m = re.search(r"(\d{4})", fn.name)
        if years and m and int(m.group(1)) not in years:
            continue
        opener = gzip.open if fn.suffix == ".gz" else open
        with opener(fn, "rt", encoding="utf-8") as fh:
            for i, line in enumerate(fh, start=1):
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                c = rec.get("codNota")
                if c is None or int(c) not in cods:
                    continue
                meta = {k: v for k, v in rec.items() if k != "html"}
                out[int(c)] = {"text": html_to_text(rec.get("html") or ""), "file": fn.name, "line": i, "record": meta}
    return out


# ------------------------------------------------------------------------------------------- document structure
RUBRICA_RE = re.compile(r"r\s?u\s?b\s?r\s?i\s?c\s?a\b\.?")
HEADING_RE = re.compile(r"\b(?:resolucion|resoluciones|decreto|acuerdo|aviso|sentencia|solicitud|edicto)\s+"
                        r"(?:sobre|que|por|relativ|en\s+unica|del|de|mediante|dictada)\b")
CLOSING_RE = re.compile(r"sufragio\s+efectivo[\s\.,]*no\s*\.?\s+reeleccion")
# the signing formula of a presidential resolution ("Dada en el Palacio del Poder Ejecutivo ..."); a bare "dado en" also
# occurs in the resultandos ("se habia dado en posesion"), so the place is required
SIGN_PLACE_RE = re.compile(r"\bpalacio\s+del\s+poder\s+ejecutivo\b|\bdad[oa]s?\s+en\s+(?:el\s+)?pal[a-z]{2,5}\b|\bdad[oa]s?\s+en\s+(?:la\s+)?(?:residencia|ciudad\s+de\s+mexico|mexico|los\s+pinos)\b")
END_RESOLUTION_RE = re.compile(r"notifiquese\s*,?\s*y\s+ejecutese|notifiquese\s+y\s+cumplase|publiquese\s+y\s+cumplase|\bejecutese\s*\.")


def closing_blocks(t: str) -> list[tuple[int, int]]:
    """(start, end) of each closing block: 'Dada en ... <date> ... Rubrica' or 'Sufragio efectivo. No reeleccion ... Rubrica'."""
    blocks = []
    for m in list(SIGN_PLACE_RE.finditer(t)) + list(CLOSING_RE.finditer(t)):
        win = t[m.start(): m.start() + 650]
        dm = P03.DATE_RE.search(win) or re.search(r"\b\d{1,2}\s+de\s+[a-z]+\s+de\s+\d{4}", win)
        if not dm:
            continue
        e = m.start() + dm.end()
        tail = t[e: e + 520]
        nh = HEADING_RE.search(tail)
        lim = nh.start() if nh else len(tail)
        rubs = [r.end() for r in RUBRICA_RE.finditer(tail) if r.end() <= lim]
        blocks.append((m.start(), e + (rubs[-1] if rubs else min(lim, 260))))
    blocks.sort()
    merged = []
    for a, b in blocks:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return merged


# SIDOF's header of the next note when it stored several notes in one text: "[cccxliv] 08-18-87 resolucion sobre ..."
NOTE_HEADER_RE = re.compile(r"\[\s*[a-z0-9]{1,12}\s*\]\s*\d{2}-\d{2}-\d{2,4}\s+(?:resolucion|resoluciones|decreto|acuerdo|"
                            r"solicitud|aviso|edicto|sentencia|fe de erratas|iniciacion|notificacion)")


def documents(t: str) -> list[dict]:
    """Split a SIDOF text into documents at each closing block. The last piece without a closing block is kept as an
    unsigned fragment (a truncated note, or the head of the next note) when it is longer than 300 characters. A SIDOF
    note header ("[cccxliv] 08-18-87 resolucion sobre ...") met before the next closing block also ends a document (its
    closing was not recognised; e.g. 4675780 runs into San Isidro's resolution)."""
    docs, start = [], 0
    heads = [m.start() for m in NOTE_HEADER_RE.finditer(t)]
    for a, b in closing_blocks(t):
        if a < start:
            continue
        for h in heads:
            if start + 300 < h < a:
                docs.append({"start": start, "end": h, "sign_start": h, "signed": False})
                start = h
        docs.append({"start": start, "end": b, "sign_start": a, "signed": True})
        start = b
    if len(t) - start > 300 or not docs:
        docs.append({"start": start, "end": len(t), "sign_start": len(t), "signed": False})
    return docs


RES_START_RE = re.compile(
    r"(?:\bse\s+)?\br\s?e\s?s\s?u\s?e\s?l\s?v\s?e\s*[:;,\.]?\s*(?=[\.\-\s]*(?:articulo\s+)?(?:primero|unico|1o\b|i\s*\.))"
    r"|\bsiguiente\s+(?:decreto|acuerdo|resolucion)\s*:?\s*(?=[\.\-\s]*(?:articulo\s+)?(?:primero|unico))"
    r"|\bhe\s+tenido\s+a\s+bien\s+(?:dictar|expedir)\b[^.]{0,80}?(?=(?:articulo\s+)?(?:primero|unico))")
POINT_RE = re.compile(r"\b(primero|segundo|tercero|cuarto|quinto|sexto|septimo|octavo|noveno|decimo|unico)\s*\.?\s*-")


def resolutive_candidates(t: str, doc: dict) -> list[tuple[int, str]]:
    """Every 'se resuelve: primero' (or 'siguiente decreto/acuerdo: primero') in a document. Rulings quoted in the
    resultandos (an earlier procedure, the Cuerpo Consultivo's acuerdo) also match; parse_note keeps the last one whose
    points hold a grant."""
    return [(m.end(), "resuelve_primero") for m in RES_START_RE.finditer(t, doc["start"], doc["sign_start"])]


def resolutive_section(t: str, doc: dict) -> tuple[int | None, str]:
    """Start of the resolutive points of a document when no 'resuelve ... primero' exists, and how it was found."""
    a, e = doc["start"], doc["sign_start"]
    m = RES_START_RE.search(t, a, e)
    if m:
        return m.end(), "resuelve_primero"
    m = re.compile(r"\b(?:se\s+)?r\s?e\s?s\s?u\s?e\s?l\s?v\s?e\s*:").search(t, a, e)
    if m:
        return m.end(), "resuelve_without_primero"          # the first point is missing (garbled)
    for p in RES_FIRST_POINT_RE.finditer(t, a, e):
        # not a ruling quoted in the resultandos (e.g. the governor's mandamiento): no resultando/considerando heading
        # may follow it
        if p.start() > a + (e - a) * 0.5 and not re.compile(r"\bresulta(?:n)?do\s+\w+\s*\.?-|\bconsiderando\s+\w+\s*\.?-").search(t, p.end(), e):
            return p.start(), "first_point_without_resuelve"
    return None, "none"


RES_FIRST_POINT_RE = re.compile(r"\bprimero\s*\.?\s*-\s*(?=(?:es\s+procedente|se\s+(?:concede|dota|reconoce|confirma|modifica|revoca|"
                                r"decreta|declara|deja)|para\s+la\s+creacion|por\s+ejecutoria|en\s+cumplimiento))")


def points(section: str) -> list[tuple[int, int, str]]:
    """(start, end, ordinal) of each resolutive point in a section."""
    ms = list(POINT_RE.finditer(section))
    if not ms:
        return [(0, len(section), "")]
    out = []
    if ms[0].start() > 0:
        out.append((0, ms[0].start(), ""))
    for i, m in enumerate(ms):
        out.append((m.start(), ms[i + 1].start() if i + 1 < len(ms) else len(section), m.group(1)))
    return out


# ------------------------------------------------------------------------------------------------ body type
NONGRANT_RULES = [
    ("rights_resolution", re.compile(r"privacion\s+de\s+(?:los\s+)?derechos\s+agrarios|se\s+reconocen\s+derechos\s+agrarios|"
                                     r"reconocimiento\s+de\s+derechos\s+agrarios|se\s+adjudican\s+(?:las\s+|\d+\s+)?unidades|"
                                     r"\bse\s+acomoda\b|se\s+priva\s+a(?:l)?\b")),
    ("inafectabilidad", re.compile(r"se\s+declaran?\s+inafectables?")),
    ("division", re.compile(r"accion\s+de\s+division|division\s+del?\s+ejido")),
    ("colonia", re.compile(r"desincorpora|regimen\s+juridico\s+de\s+colonizacion|como\s+colono")),
    ("initiation_notice", re.compile(r"se\s+inicia\s+de\s+oficio\s+el\s+expediente|iniciacion\s+del\s+expediente|"
                                     r"instauracion\s+del\s+expediente|se\s+tiene\s+por\s+iniciado")),
]


def nongrant_type(section: str) -> str | None:
    head = section[:1500]
    hits = [(m.start(), name) for name, rx in NONGRANT_RULES for m in [rx.search(head)] if m]
    return min(hits)[1] if hits else None


# ------------------------------------------------------------------------------------------------ grant anchors
ANCHOR_RE = re.compile(
    r"\bse[\s\-]+(?:le\s+|les\s+)?(?:conceden?|conceda|concedio|concedo|concece|corcede|otorgan?|dotan?|dot|nota|data|dotar|"
    r"amplia|restituyen?|reconocen?(?!\s+(?:derechos|como|que|los\s+derechos))|reconocer|reconcoe|renonoce|reconose|conoce|"
    r"titulan?|crea)\b"
    r"|\bse\s+confirman?\s+y\s+titula"
    r"|\bconcede\s+al\s+(?:poblado|nucleo|nuevo)\b|\bconcedase\b|\bse\s+procede\s+al\s+poblado\b"
    r"|\bsedota\b|\bdotandose\b|(?<!se\s)\bdota\s+a\s+(?:los|las)\b|\bes\s+de\s+dotarse\b|\bdeberan\s+otorgarse\b"
    r"|\bse\s+toman\b"
    r"|\bes\s+procedentes?\s+(?:el\s+)?(?:reconocimiento|reconocer)\b|\bes\s+procedente\s+la\s+accion\b"
    r"|(?P<affect>\bse\s+decreta\s+la\s+afectacion\b|\bse\s+afecta\b)")
# 03's own verb list (to tell a verb variant from an amount-format miss)
P03_VERB = P03.CONCESSION_RE

# ------------------------------------------------------------------------------------------------ amounts
NUMW = dict(P03.NUM_WORDS)
NUMW.update({"trelnta": 30, "neuve": 9, "diecisies": 16, "oeho": 8, "veintiuno": 21, "dieciseis": 16, "diesiseis": 16,
             "diesiocho": 18, "dieciocho": 18, "diesisiete": 17, "diesinueve": 19, "veintiseis": 26, "cuatrocientos": 400,
             "ochocienta": 800, "quinienta": 500, "seiscienta": 600, "doscienta": 200, "trescienta": 300,
             "cuatrocienta": 400, "setecienta": 700, "novecienta": 900, "cientos": 100, "cientas": 100, "cento": 100})
SKIP_W = {"y", "e", "de", "del", "con"}
OCR_TR = str.maketrans("olis", "0115")
UNIT_RE = re.compile(r"\s*\)?\s*,?\s*(?:(?P<std>has?\b\.?|hs\b\.?|hect[a-z]*|hras?\b\.?)|(?P<var>hass\b\.?|mas\b\.?|w\s+has\b\.?|ha\s+s\b\.?))")
WORDS_GAP_RE = re.compile(r"^[\s\.,;:\(\)\-'\"]*(?:(?:has?s?|hs|mas|w\s+has)\b\.?)?[\s\.,;:\(\)\-'\"]*")


HECT_RX = re.compile(r"\bh[a-z]{2,4}areas?\b|\bhectar[a-z]{0,3}\b")


def words_value(run: str) -> int | None:
    run = re.sub(r"\b(dos|tres|cuatro|seis|ocho)\s+cient", r"\1cient", run)
    total, cur, ok = 0, 0, False
    for w in re.findall(r"[a-z]+", run):
        if w in SKIP_W:
            continue
        if w not in NUMW:
            return None
        v = NUMW[w]
        if v == 1000:
            total += (cur or 1) * 1000
            cur = 0
        elif v == 100 and w in ("cientos", "cientas", "cento") and cur and cur < 10:
            cur = cur * 100
        else:
            cur += v
        ok = True
    return total + cur if ok else None


def parse_words(s: str) -> dict | None:
    """The amount written in words at the start of s ('(cuatrocientas ochenta y seis hectareas, ochenta areas,
    treinta centiareas, diez decimetros cuadrados)'): {'ha','a','ca','dm','value','parts','text'}."""
    gap = WORDS_GAP_RE.match(s)
    i = gap.end() if gap else 0
    hm = HECT_RX.search(s, i, i + 220)
    if not hm:
        return None
    run = s[i:hm.start()].strip(" ,")
    if not run or re.search(r"[^a-z\s,]", run):
        return None
    ha = words_value(run)
    if ha is None:
        return None
    out = {"ha": ha, "a": None, "ca": None, "dm": None}
    j = hm.end()
    for key, rx in (("a", r"[\s,;y]*(?P<w>(?:[a-z]+[\s,]*){1,5}?)areas?\b"),
                    ("ca", r"[\s,;y]*(?P<w>(?:[a-z]+[\s,]*){1,5}?)centi[a-z]*areas?\b"),
                    ("dm", r"[\s,;y]*(?P<w>(?:[a-z]+[\s,]*){1,5}?)deci?[a-z]*metros?\s+cuadrados?\b")):
        m = re.compile(rx).match(s, j)
        if not m:
            continue
        if key == "a" and re.search(r"centi|hect", m.group("w")):
            continue
        v = words_value(m.group("w"))
        if v is None or v >= 100:
            continue
        out[key] = v
        j = m.end()
    out["parts"] = sum(out[k] is not None for k in ("a", "ca", "dm"))
    out["value"] = ha + (out["a"] or 0) / 100 + (out["ca"] or 0) / 1e4 + (out["dm"] or 0) / 1e6
    out["text"] = s[i:j].strip(" ,()")
    out["end"] = j
    return out


def scan_digit_token(s: str, i: int) -> int:
    """End of the printed amount starting at s[i] (a digit): digits, separators, single spaces between groups, OCR
    letters o/l/i/s inside a group, and an OCR letter printed for the hyphen before the last two digits
    ("10,470-32j51 has.")."""
    j, n = i, len(s)
    while j < n:
        c = s[j]
        if c.isdigit() or c in ".,-'":
            j += 1
        elif c == " " and j + 1 < n and (s[j + 1].isdigit() or s[j + 1] == "-") and (s[j - 1].isdigit() or s[j - 1] in "-.,"):
            j += 1
        elif c == " " and j + 2 < n and s[j + 1] == "," and s[j + 2].isdigit() and s[j - 1].isdigit():
            j += 1                                          # "1 ,980-00-00"
        elif c in "olis" and (s[j - 1].isdigit() or s[j - 1] in "-.,"):
            k = j
            while k < n and s[k] in "olis":
                k += 1
            if k - j > 2 or (k < n and s[k].isalpha()):
                break
            j = k
        elif (c.isalpha() and re.search(r"-\s?\d{1,2}$", s[max(i, j - 4):j])
              and re.match(r"\d{2}(?!\d)", s[j + 1:j + 4])):
            j += 1                                          # "10,470-32j51": the letter is the hyphen of the centiareas
        else:
            break
    return j


def digit_readings(tok: str) -> dict[str, tuple[float, int]]:
    """Every plausible reading of a printed amount -> (hectares, precision), precision = number of sub-hectare groups
    (1 areas, 2 centiareas, 3 square decimetres). Readings: ha-a-ca(-dm) groups with thousands groups of 3 digits
    (separator ',', '.' or a stray '-'), and the hyphen-less splits of all its digits. A comma before the areas group is
    accepted only when no hyphen follows ("7,619,20,00" is ha-a-ca; "20,90-77-40" is a malformed thousands group, whose
    only readings are the hyphen-less splits)."""
    t = tok.translate(OCR_TR).replace("'", "")
    groups = re.findall(r"\d+", t)
    seps = re.findall(r"\D+", re.sub(r"^\D+|\D+$", "", t))           # separators between consecutive groups
    out: dict[str, tuple[float, int]] = {}
    if not groups:
        return out
    for k in range(1, len(groups) + 1):
        head, frac = groups[:k], groups[k:]
        if any(len(g) != 3 for g in head[1:]) or len(frac) > 3:
            continue
        if frac and k - 1 < len(seps) and "," in seps[k - 1] and any("-" in x for x in seps[k:]):
            continue
        v, scale, ok = float(int("".join(head))), 100.0, True
        for g in frac:
            if len(g) > 2:
                if set(g[2:]) <= {"0"}:
                    g = g[:2]                       # '-000' printed for '-00'
                else:
                    ok = False
                    break
            v += int(g) / scale
            scale *= 100
        if ok:
            out[f"groups{k}"] = (v, len(frac))
    d = "".join(groups)
    if len(d) >= 3:
        out["concat_a"] = (int(d[:-2]) + int(d[-2:]) / 100, 1)
    if len(d) >= 5:
        out["concat_a_ca"] = (int(d[:-4]) + int(d[-4:-2]) / 100 + int(d[-2:]) / 1e4, 2)
    if len(d) >= 7:
        out["concat_a_ca_dm"] = (int(d[:-6]) + int(d[-6:-4]) / 100 + int(d[-4:-2]) / 1e4 + int(d[-2:]) / 1e6, 3)
    out["integer"] = (float(int(d)), 0)
    return out


STANDARD_TOKEN = re.compile(r"\d{1,3}(?:,\d{3})*-\d{2}-\d{2}(?:\.\d{1,2})?|\d{1,3}(?:,\d{3})*(?:\.\d+)?")


def _trunc(v: float, p: int) -> int:
    return int(round(v * 100 ** p, 4) + 1e-6) if p < 3 else int(round(v * 1e6))


def agree(reading: tuple[float, int], w: dict | None) -> bool:
    """A digit reading agrees with the words at the coarser of the two printed precisions (square decimetres are
    compared with a 1.5 m2 tolerance)."""
    if w is None:
        return False
    v, pd_ = reading
    p = min(pd_, w["parts"])
    if p >= 3 or (p == 2 and pd_ >= 3 and w["parts"] >= 3):
        return abs(v - w["value"]) <= 0.00015
    return _trunc(v, p) == _trunc(w["value"], p)


def first_amount(s: str, pos: int, end: int) -> dict | None:
    """First printed amount in s[pos:end]: a digit token followed by a unit and/or the amount in words, else words
    alone. Numbers without unit or words (articles, dates, percentages, lot numbers) are skipped."""
    for m in re.compile(r"(?<![\w\-\.,/])\d").finditer(s, pos, end):
        j = scan_digit_token(s, m.start())
        tok = s[m.start():j].rstrip(" .,-'")
        if not re.search(r"\d", tok):
            continue
        after = s[m.start() + len(tok): m.start() + len(tok) + 260]
        unit = UNIT_RE.match(after)
        if re.match(r"\s*(?:%|por ciento|metros|kilometros|anos|dias|campesinos|capacitados)", after):
            continue
        w = parse_words(after)
        if unit or w:
            return {"pos": m.start(), "token": tok, "unit": (unit.group("std") or unit.group("var")).strip() if unit else None,
                    "unit_variant": bool(unit and unit.group("var")), "words": w,
                    "end": m.start() + len(tok) + (w["end"] if w else (unit.end() if unit else 0))}
    hm = HECT_RX.search(s, pos, end)
    if hm:
        back = s[max(pos, hm.start() - 160):hm.start()]
        run = P03.NUMWORD_RUN_RE.search(back.rstrip(" ,("))
        if run:
            st = hm.start() - len(back) + run.start()
            w = parse_words(s[st:st + 300])
            if w:
                return {"pos": st, "token": None, "unit": None, "unit_variant": False, "words": w, "end": st + w["end"]}
    return None


def resolve_amount(am: dict) -> dict:
    """Value of an amount from digits and words: agreement, a single reading, or a conflict for the LLM."""
    w, tok = am["words"], am["token"]
    rd = digit_readings(tok) if tok else {}
    res = {"hectares": None, "hectares_words": w["value"] if w else None, "words_text": w["text"] if w else None,
           "digits": tok, "reading": None, "status": None}
    if rd and w:
        ok = [(k, r) for k, r in rd.items() if agree(r, w)]
        if ok:
            # prefer a structured reading, then the reading with the finest precision
            k, (v, prec) = sorted(ok, key=lambda x: (not x[0].startswith("groups"), -x[1][1]))[0]
            if w["parts"] > prec:
                v = w["value"]                      # the words carry finer parts than the digits
            res.update(hectares=round(v, 6), reading=k, status="digits_words_agree")
        else:
            res.update(status="digits_words_disagree")
        return res
    if rd and not w:
        structured = {k: r for k, r in rd.items() if k.startswith("groups") and r[1] >= 1}
        clean = not re.search(r"[olis]", tok)
        if STANDARD_TOKEN.fullmatch(tok) and clean:
            k = 1 + tok.split("-")[0].count(",")         # thousands groups of the integer part
            v = rd[f"groups{k}"][0] if "-" in tok else float(tok.replace(",", ""))
            res.update(hectares=round(v, 6), reading="standard", status="digits_only_standard")
        elif clean and len(structured) == 1 and len(re.findall(r"\d+", tok)) >= 3:
            k, (v, _) = next(iter(structured.items()))
            res.update(hectares=round(v, 6), reading=k, status="digits_only_single_reading")
        else:
            res.update(status="digits_only_ambiguous")
        return res
    if w and not rd:
        res.update(hectares=round(w["value"], 6), reading="words", status="words_only")
    return res


def find_grant(section: str) -> dict | None:
    """The grant in a resolutive section: the first point with a concession anchor followed by an amount; an
    affectation anchor ("se decreta la afectacion de ...") only when no concession anchor has an amount."""
    found = []
    for a, b, ordinal in points(section):
        for m in ANCHOR_RE.finditer(section, a, b):
            am = first_amount(section, m.end(), min(b, m.end() + 900))
            if am:
                found.append({"point_start": a, "point_end": b, "ordinal": ordinal, "anchor": m.group(0),
                              "anchor_pos": m.start(), "affectation": bool(m.group("affect")), "amount": am})
                break
    conc = [g for g in found if not g["affectation"]]
    return conc[0] if conc else (found[0] if found else None)


def land_classes(section: str, g: dict, total: float) -> dict:
    """03's land-class logic on the grant point: component amounts after the total, else the words after it."""
    seg = section[g["amount"]["end"]: g["point_end"]]
    am = P03.amounts_in(P03.fix_digits(seg))
    cls = {c: 0.0 for c in CLASSES}
    comps = []
    for i, (a, b, v) in enumerate(am):
        nxt = am[i + 1][0] if i + 1 < len(am) else min(len(seg), b + 160)
        cl = P03.classify_window(seg[b:min(nxt, b + 160)])
        if cl:
            comps.append((cl[0], v))
    if comps and sum(v for _, v in comps) <= total * 1.001 + 0.01:
        for c, v in comps:
            cls[c] += v
    else:
        first_end = g["amount"]["end"]
        nxt = am[0][0] if am else min(len(seg), 200)
        cl = P03.classify_window(section[first_end: first_end + min(nxt, 200)])
        if cl:
            cls[cl[0]] += total
    rem = total - sum(cls.values())
    if rem > 0.01:
        cls["indefinido"] += rem
    return {f"ha_{c}": round(cls[c], 4) for c in CLASSES}


# ------------------------------------------------------------------------------------- 03 replays (diagnosis)
def p03_hectares(op_text: str) -> float | None:
    """03's hectare rule on an operative text: first concession verb, segment to the next item, first amount."""
    op = P03.fix_digits(op_text)
    conc = P03.CONCESSION_RE.search(op)
    if not conc:
        return None
    seg_end = P03.NEXT_ITEM_RE.search(op, conc.end())
    seg = op[conc.start(): (seg_end.start() if seg_end else min(len(op), conc.start() + 3000))]
    if not P03.amounts_in(seg):
        seg = op[conc.start(): conc.start() + 3000]
    am = P03.amounts_in(seg)
    return am[0][2] if am else None


def p03_operative_start(t: str) -> int:
    sig = list(P03.SIGN_RE.finditer(t))
    end = sig[-1].start() if sig else len(t)
    opers = list(P03.OPER_RE.finditer(t, 0, end))
    if opers:
        return opers[-1].end()
    firsts = [m for m in re.finditer(r"\bprimero\s*\.?\s*-", t[:end]) if m.start() > end * 0.4]
    return firsts[0].start() if firsts else int(end * 0.6)


def format_subtype(am: dict) -> str:
    tok = am["token"]
    if tok is None:
        return "words_only"
    if re.search(r"[olis]", tok):
        return "ocr_letter_in_digits"
    if am["unit"] is None:
        return "no_unit"
    if am["unit_variant"]:
        return "unit_variant"
    if " " in tok:
        return "space_for_hyphen"
    if re.search(r"--|-$|-\s*-", tok):
        return "stray_or_double_hyphen"
    if re.fullmatch(r"\d{1,3}(?:[,\.]\d{3})*-\d{2}", tok):
        return "two_groups_only"
    if re.search(r"-\d{3}(?:-|$)", tok) and not re.match(r"\d{1,2}-\d{3}-\d{2}-\d{2}", tok):
        return "three_digit_group"
    if re.match(r"\d{1,2}-\d{3}-", tok):
        return "hyphen_as_thousands"
    if len(re.findall(r"\d+", tok.split("-", 1)[-1])) >= 3 or re.search(r"-\d{2}-\d{2}[-\.]\d{2}", tok):
        return "decimetre_group"
    if re.search(r"\d\.\d{2}-", tok) or re.search(r"-\d{2}\.\d{2}$", tok):
        return "dot_for_hyphen"
    if re.search(r"\d{4,}-\d{2}$|-\d{4}", tok) or re.fullmatch(r"\d{5,}", tok):
        return "missing_hyphen"
    return "other_format"


# ------------------------------------------------------------------------------------------------ LLM
LLM_PROMPT = """You read one Mexican presidential agrarian resolution published in the Diario Oficial de la Federacion.
The text below (accents removed, lower case; typing or OCR errors are possible) is its heading and its resolutive points
("se resuelve: primero.- ..."), followed by any sentences elsewhere in the same resolution that repeat the surface.
Poblado named in the title: {poblado}.

Return a JSON object with these keys:
  "is_land_grant": true if the resolution grants, extends, restores or recognises land (dotacion, ampliacion, restitucion,
                   nuevo centro de poblacion ejidal, reconocimiento y titulacion de bienes comunales) to that poblado;
                   false if it is another act (privacion / reconocimiento de derechos agrarios, inafectabilidad, division
                   de ejido, ...)
  "grant": 1 if land is granted, 0 if the request is denied, null if not applicable
  "hectares_digits": the total surface granted to that poblado exactly as printed in digits (string), or null
  "hectares_words": the same surface exactly as written in words (string), or null
  "hectares": the total surface granted to that poblado in hectares as a decimal number (hectareas + areas/100 +
              centiareas/10000); when an affected property is split among several poblados, only this poblado's part;
              when digits and words conflict, use the reading supported by the rest of the text and say why
  "beneficiaries": number of beneficiaries (capacitados, campesinos, comuneros) named in the resolutive points, or null
  "explanation": one short sentence

TEXT:
{text}
"""

VISION_PROMPT = """These are scanned pages of the Mexican Diario Oficial de la Federacion of {date}. One of the notes on
them is the presidential resolution titled: "{title}". Find THAT resolution (several notes share a page; columns read
top to bottom, left to right) and read its resolutive points ("se resuelve: primero.- ...") and its closing signature.

Return a JSON object with these keys:
  "found": true if the resolution's resolutive points are visible on these pages, else false
  "is_land_grant": true if it grants, extends, restores or recognises land to the poblado; false for another act
  "grant": 1 if land is granted, 0 if denied, null if not applicable
  "hectares_digits": the total surface granted to the poblado exactly as printed in digits (string), or null
  "hectares_words": the same surface exactly as written in words (string), or null
  "hectares": that surface in hectares as a decimal number (hectareas + areas/100 + centiareas/10000)
  "beneficiaries": number of beneficiaries (capacitados) named in the resolutive points, or null
  "signing_date": date in the closing "Dada en el Palacio del Poder Ejecutivo ... a los ... dias del mes de ... de ..."
                  as YYYY-MM-DD, or null
  "signer": the President who signs, or null
  "explanation": one short sentence
"""


class LLM:
    """Cached two-reader protocol with llm_tables' budget guard and ledger, plus a cap on this run's new spend."""

    def __init__(self, offline: bool, max_new_usd: float):
        import llm_tables
        self.lt = llm_tables
        self.offline = offline
        self.max_new = max_new_usd
        self.start_spent = llm_tables.spent_usd()
        self.client = None
        self.unavailable: str | None = None

    def new_spend(self) -> float:
        return self.lt.spent_usd() - self.start_spent

    def _client(self):
        if self.client is None:
            from openai import OpenAI
            self.client = OpenAI(api_key=openai_api_key())
        return self.client

    def ask(self, model: str, tag: str, prompt: str, images: list[bytes] | None = None) -> dict | None:
        cache = LLM_CACHE / f"{tag}_{model}.json"
        if cache.exists():
            return json.loads(cache.read_text())
        if self.offline:
            return None
        if self.unavailable:
            return None
        if self.new_spend() >= self.max_new:
            print(f"  [llm] run cap reached (${self.new_spend():.2f} new); skipping {tag}")
            return None
        try:
            self.lt.check_budget()
        except self.lt.BudgetExceeded as e:
            self.unavailable = str(e)
            print(f"  [llm] {e}")
            return None
        content = [{"type": "text", "text": prompt}]
        for png in images or []:
            content.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode(),
                                                               "detail": "high"}})
        kw = dict(model=model, response_format={"type": "json_object"}, messages=[{"role": "user", "content": content}])
        try:
            try:
                r = self._client().chat.completions.create(reasoning_effort="low", **kw)
            except Exception as e:                               # model without the parameter
                if "reasoning" not in str(e).lower():
                    raise
                r = self._client().chat.completions.create(**kw)
        except Exception as e:                                   # no credit, quota, network: stop asking, keep going
            self.unavailable = f"{type(e).__name__}: {str(e)[:160]}"
            print(f"  [llm] unavailable ({self.unavailable}); remaining notes fall back to hand readings")
            return None
        self.lt._log_usage(model, r.usage, tag)
        ans = json.loads(r.choices[0].message.content)
        ans["_model"], ans["_tag"] = model, tag
        LLM_CACHE.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(ans, ensure_ascii=False, indent=1))
        return ans

    def two_reads(self, tag: str, prompt: str, images=None) -> tuple[dict | None, str, list[dict]]:
        """(decision, confidence, answers): READERS[0] and READERS[1]; TIEBREAK when they disagree."""
        a = [self.ask(m, tag, prompt, images) for m in self.lt.READERS]
        a = [x for x in a if x]
        if len(a) < 2:
            return None, "not_read", a

        def key(x):
            h = x.get("hectares")
            try:
                h = round(float(h), 4) if h is not None else None
            except (TypeError, ValueError):
                h = None
            return (h, bool(x.get("is_land_grant")))
        if key(a[0]) == key(a[1]):
            return a[0], "two_reads_agree", a
        c = self.ask(self.lt.TIEBREAK, tag, prompt, images)
        if c:
            a.append(c)
            for x in a[:2]:
                if key(x) == key(c):
                    return x, "tiebreak_majority", a
        return None, "readers_disagree", a


# ------------------------------------------------------------------------------------------------ scans
def http_get(url: str, timeout: int = 300) -> tuple[int, str, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()


_last_request = [0.0]


def polite_get(url: str, timeout: int = 300):
    wait = 1.2 - (time.monotonic() - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    try:
        return http_get(url, timeout)
    finally:
        _last_request[0] = time.monotonic()


def note_record(cod: int, fetch: bool) -> dict | None:
    """SIDOF note record (codDiario, page, section, edition), cached without the HTML in note_records.jsonl."""
    if NOTE_RECORDS.exists():
        with open(NOTE_RECORDS) as fh:
            for line in fh:
                r = json.loads(line)
                if r.get("codNota") == cod:
                    return r
    if not fetch:
        return None
    status, _, body = polite_get(f"{SIDOF}/notas/nota/{cod}", 90)
    n = json.loads(body).get("Nota") or {}
    rec = {k: n.get(k) for k in ("codNota", "codDiario", "fecha", "pagina", "paginaHasta", "codSeccion", "codEdicion",
                                 "titulo", "existePdf", "existeImagen", "existeDoc")}
    rec["fetched_utc"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    SCAN_DIR.mkdir(parents=True, exist_ok=True)
    with open(NOTE_RECORDS, "a") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


SECTION_RX = re.compile(r"(PRIMERA|SEGUNDA|TERCERA|CUARTA|QUINTA|SEXTA|S[EÉ]PTIMA|OCTAVA|NOVENA|D[EÉ]CIMA)\s+SECCI[OÓ]N", re.I)


def edition_path(rec: dict) -> Path:
    d = dt.datetime.strptime(rec["fecha"], "%d-%m-%Y").date().isoformat()
    return SCAN_DIR / f"{d}_{rec['codEdicion']}_{rec['codDiario']}.jsonl.gz"


def ensure_edition(rec: dict, tmp: Path, fetch: bool) -> Path | None:
    """Stored OCR pages of the note's edition (reused if this or another agent already stored it); otherwise, with
    fetch on, download the PDF to `tmp` (outside Dropbox), write one JSON line per page with `pdftotext -layout`, and
    keep the provenance in a pending row that finalize_manifest() appends to MANIFEST.csv once the note pages are
    verified. The PDF is deleted after its pages are rendered (unless --keep-pdf)."""
    out = edition_path(rec)
    if out.exists() or not fetch:
        return out if out.exists() else None
    tmp.mkdir(parents=True, exist_ok=True)
    pdf = tmp / f"{rec['codDiario']}.pdf"
    url = f"{SIDOF}/documentos/pdf/{rec['codDiario']}"
    status, ctype, body = polite_get(url, 600)
    pdf.write_bytes(body)
    info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    n_pages = int(re.search(r"Pages:\s+(\d+)", info).group(1))
    producer = (re.search(r"Producer:\s+(.*)", info) or [None, ""])[1].strip()
    ver = re.search(r"pdftotext version (\S+)", subprocess.run(["pdftotext", "-v"], capture_output=True, text=True).stderr)
    txt = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", str(pdf), "-"], capture_output=True).stdout.decode("utf-8", "replace")
    pages = txt.split("\f")[:n_pages]
    d = dt.datetime.strptime(rec["fecha"], "%d-%m-%Y").date().isoformat()
    SCAN_DIR.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8") as fh:
        for i, pg in enumerate(pages, start=1):
            sm = SECTION_RX.search("\n".join(pg.splitlines()[:12]))
            fh.write(json.dumps({"codDiario": rec["codDiario"], "date": d, "codEdicion": rec["codEdicion"], "pdf_page": i,
                                 "section_header_detected": sm.group(0) if sm else None, "text": pg},
                                ensure_ascii=False) + "\n")
    row = {"source_url": url, "codDiario": rec["codDiario"], "date": d, "codEdicion": rec["codEdicion"],
           "http_status": status, "content_type": ctype, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
           "n_pages": n_pages, "pdf_producer": producer,
           "downloaded_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "extracted_with": f"pdftotext {ver.group(1) if ver else ''} (poppler) -layout -enc UTF-8, one line per page",
           "edition_text_file": out.name, "codNotas_pdf_pages": ""}
    with open(tmp / "pending_manifest.jsonl", "a") as fh:
        fh.write(json.dumps(row) + "\n")
    return out


MANIFEST_COLS = ["source_url", "codDiario", "date", "codEdicion", "http_status", "content_type", "bytes", "sha256",
                 "n_pages", "pdf_producer", "downloaded_at", "extracted_with", "edition_text_file", "codNotas_pdf_pages"]


def finalize_manifest(tmp: Path, pages_by_edition: dict[int, str]):
    """Append this run's downloaded editions to MANIFEST.csv (append only, under an exclusive lock: another agent
    writes to the same file), with the verified 'codNota:first-last' pages of the notes read from each edition."""
    pend = tmp / "pending_manifest.jsonl"
    if not pend.exists():
        return
    rows = [json.loads(x) for x in pend.read_text().splitlines() if x.strip()]
    SCAN_DIR.mkdir(parents=True, exist_ok=True)
    with open(SCAN_MANIFEST, "a+", newline="") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        head = fh.readline()
        cols = next(csv.reader([head])) if head.strip() else MANIFEST_COLS
        fh.seek(0, os.SEEK_END)
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        if not head.strip():
            w.writeheader()
        fh.seek(0)
        have = {x.get("codDiario") for x in csv.DictReader(fh)}
        fh.seek(0, os.SEEK_END)
        skipped = []
        for r in rows:
            if str(r["codDiario"]) in have:          # the other agent fetched the same edition: keep one row per edition
                skipped.append(r["codDiario"])
                continue
            r["codNotas_pdf_pages"] = pages_by_edition.get(int(r["codDiario"]), "")
            w.writerow({c: r.get(c, "") for c in cols})
        if skipped:
            print(f"manifest: {len(skipped)} editions already listed by another run (kept their row): {skipped}")
        fh.flush()
        fcntl.flock(fh, fcntl.LOCK_UN)
    pend.unlink()
    print(f"manifest: {len(rows) - len(skipped)} editions appended to {SCAN_MANIFEST.name}")


def load_pages(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


TOC_LINE_RE = re.compile(r"\.{5,}|(?:\.\s){5,}")
RESUELVE_OCR_RE = re.compile(r"r\W?e\W?s\W?u\W?e\W?l\W?v\W?e\s*[:;\.]|se\s+resuelve")


def locate_note_pages(pages: list[dict], cod: int, keys: list[str], printed_page: int | None) -> list[int]:
    """PDF pages (1-based) likely to hold the note's resolutive points. Start page: best fuzzy match of the title's
    place name in the OCR text (noise tolerated), +15 when the page header shows the printed page number; table-of-
    contents pages (dot leaders) are skipped. Then the first page from there with 'se resuelve', and the page after it
    (the points and the signature often run over). Hand-checked overrides in SCAN_PAGE_OVERRIDES win."""
    if cod in SCAN_PAGE_OVERRIDES:
        return SCAN_PAGE_OVERRIDES[cod]
    keys = [k for k in keys if k and len(k) >= 5]
    if not keys:
        return []
    texts = [norm(p["text"]) for p in pages]
    scores = []
    for p, t in zip(pages, texts):
        if sum(bool(TOC_LINE_RE.search(x)) for x in p["text"].splitlines()) >= 6:
            scores.append(-1)
            continue
        s = max(fuzz.partial_ratio(k, t) for k in keys)
        head = norm(" ".join(p["text"].strip().splitlines()[:3]))
        if printed_page and re.search(rf"(?<![\d,.]){printed_page}(?![\d,.])", head):
            s += 15
        scores.append(s)
    start = int(np.argmax(scores))
    res = next((j for j in range(start, min(start + 12, len(texts))) if RESUELVE_OCR_RE.search(texts[j])), start)
    out = sorted({start + 1, res + 1, min(res + 2, len(texts))})
    return out


def render_pages(pdf: Path, pages: list[int], dpi: int = 150) -> list[bytes]:
    import pymupdf
    doc = pymupdf.open(pdf)
    out = []
    for p in pages:
        pix = doc[p - 1].get_pixmap(dpi=dpi)
        out.append(pix.tobytes("png"))
    return out


# ------------------------------------------------------------------------------------------------ main parse
def own_resolution_end(t: str, own: dict, rs: int | None) -> tuple[int, bool]:
    """End of the note's own resolutive points: its 'notifiquese y ejecutese' (texts can run on into the next note
    without a closing block), else the document's closing block."""
    if rs is None:
        return own["sign_start"], False
    m = END_RESOLUTION_RE.search(t, rs, own["sign_start"] if own["signed"] else len(t))
    return (m.end(), True) if m else (own["sign_start"], False)


def signing_of(t: str, sec_end: int, own: dict) -> dict:
    """03's parse_signing on the closing right after the note's own resolutive points (never on an appended note)."""
    win = t[max(0, sec_end - 200): sec_end + 750]
    if not (SIGN_PLACE_RE.search(win) or P03.SIGN_RE.search(win[200:]) or "palacio del poder ejecutivo" in win
            or re.search(r"magistrad|tribunal\s+(?:superior|unitario)", win)):
        return {"signing_date": None, "president_signing_text": None, "signer_body": None, "signing_found": 0}
    s = P03.parse_signing(win)
    if s["signing_date"] is None:                 # typos 03's DATE_RE rejects: "d los", no "a", "mi;", "del mes mayo"
        m = SIGN_DATE_FALLBACK.search(win)
        if m:
            day = P03.words_to_int(m.group("day"))
            yr = P03.words_to_int(re.sub(r"\bmil?\W?(?=\s)", "mil", m.group("year")).replace(".", ""))
            try:
                if day and yr and 1900 < yr < 2001:
                    s["signing_date"] = dt.date(yr, P03.MONTHS[m.group("month")], day)
                    s["signing_fallback"] = 1
            except ValueError:
                pass
            if s.get("president_signing_text") is None:
                pm = P03.PRES_RE.search(win[m.end(): m.end() + 400])
                if pm:
                    s["president_signing_text"] = P03.PRES_CANON.get(P03.PRES_KEY.get(pm.group(1), pm.group(1)))
                    s["signer_body"] = "president"
    s["signing_found"] = int(s["signing_date"] is not None)
    return s


SIGN_DATE_FALLBACK = re.compile(
    r"(?P<day>\d{1,2}|[a-z]+(?:\s+y\s+[a-z]+)?)\s+(?:\(\d+\)\s+)?dias?\s+(?:dias\s+)?del?\s+mes\s+(?:de\s+)?"
    r"(?P<month>enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+"
    r"(?:de|del)\s+(?P<year>mil?\W?\s+novecientos(?:\s+[a-z]+){0,4}|\d{4})")


def diagnose(t: str, sec: str, rs: int, sec_end: int, g: dict) -> list[str]:
    """Why 03 found no hectares, by checking each step of 03's pipeline against the grant found here: its operative
    section (last 'resuelve' before the last signature of the whole text), its concession-verb segment, and its amount
    regexes on the printed amount."""
    problems = []
    gpos = rs + g["amount"]["pos"]
    op03 = p03_operative_start(t)
    if op03 > sec_end:
        problems.append("multi_document_text")
    elif op03 > gpos:
        problems.append("operative_mislocated")
    apos = g["amount"]["pos"]
    conc = P03.CONCESSION_RE.search(sec)
    verb_ok = False
    if conc and conc.start() <= apos:
        nxt = P03.NEXT_ITEM_RE.search(sec, conc.end())
        seg_end = nxt.start() if nxt else min(len(sec), conc.start() + 3000)
        if seg_end <= apos and not P03.amounts_in(P03.fix_digits(sec[conc.start():seg_end])):
            seg_end = conc.start() + 3000               # 03 widens the segment when it holds no amount
        verb_ok = seg_end > apos
    am = g["amount"]
    target = [v for v, _ in digit_readings(am["token"]).values()] if am["token"] else []
    if am["words"]:
        target.append(am["words"]["value"])
    got = P03.amounts_in(P03.fix_digits(sec[apos: am["end"] + 3]))
    fmt_ok = bool(got) and got[0][0] <= 2 and any(abs(got[0][2] - v) <= 0.01 * max(v, 1) for v in target)
    if not verb_ok:
        problems.append("verb_variant")
    if not fmt_ok:
        problems.append(f"amount_format:{format_subtype(am)}")
    return problems or ["other"]


def parse_note(cod: int, src: dict, row: pd.Series) -> dict:
    t = norm(src["text"])
    docs = documents(t)
    own = docs[0]
    cands = resolutive_candidates(t, own)
    if cands:
        pick = None
        for rs_c, how_c in reversed(cands):
            end_c, has_c = own_resolution_end(t, own, rs_c)
            g_c = find_grant(t[rs_c:end_c])
            if g_c is not None:
                pick = (rs_c, how_c, end_c, has_c, g_c)
                break
        if pick is None:
            rs_c, how_c = cands[-1]
            end_c, has_c = own_resolution_end(t, own, rs_c)
            pick = (rs_c, how_c, end_c, has_c, None)
        rs, rs_how, sec_end, has_end, g = pick
        if len(cands) > 1:
            rs_how += f"_{cands.index((rs, rs_how)) + 1}of{len(cands)}"
    else:
        rs, rs_how = resolutive_section(t, own)
        sec_end, has_end = own_resolution_end(t, own, rs)
        g = find_grant(t[rs:sec_end]) if rs is not None else None
    sec = t[rs:sec_end] if rs is not None else ""
    ng = nongrant_type(sec) if sec else None
    if not sec:
        doc = t[own["start"]: own["end"]]
        ng = ("initiation_notice" if re.search(r"iniciacion|instauracion", doc[:300])
              or re.search(r"(?:por\s+medio\s+del\s+presente\s+)?se\s+inicia\s+de\s+oficio\s+el\s+expediente", doc) else None)
    poblado = row.get("ncpe_name") if isinstance(row.get("ncpe_name"), str) else row.get("poblado")
    village_ok = None
    if isinstance(poblado, str) and len(poblado) >= 4 and sec:
        village_ok = fuzz.partial_ratio(norm(poblado), sec) >= 85
    out = {"codNota": cod, "n_documents_in_text": sum(d["signed"] for d in docs), "own_document_signed": int(own["signed"]),
           "resolutive_found": rs_how, "poblado_in_resolutive": village_ok}
    garbled = []
    if rs is None:
        garbled.append("no_resolutive_points")
    elif rs_how == "resuelve_without_primero":
        garbled.append("first_resolutive_point_missing")
    if sec and not has_end and not own["signed"]:
        garbled.append("text_cut_before_signature")
    if village_ok is False and g is None:
        garbled.append("resolutive_points_of_another_village")
    if g is None and ng is None and sec and re.search(r"la anterior superficie|superficie concedida|tierras concedidas", sec):
        garbled.append("grant_point_missing")
    out["body_type"] = "land_grant" if g is not None else (ng or "unknown")
    if g is None and ng:
        reason, detail = f"not_a_land_grant:{ng}", (["multi_document_text"] if len(docs) > 1 else [])
    elif g is None:
        reason, detail = "text_garbled_or_truncated", garbled or ["no_grant_found"]
    else:
        probs = diagnose(t, sec, rs, sec_end, g)
        reason, detail = probs[0], probs[1:]
    out["reason_missed"], out["reason_detail"] = reason, (";".join(detail) if detail else None)
    out.update({"hectares": None, "hectares_digits": None, "hectares_words": None, "hectares_words_text": None,
                "digit_reading": None, "amount_status": None, "grant_anchor": None, **{f"ha_{c}": None for c in CLASSES}})
    if g is not None:
        r = resolve_amount(g["amount"])
        out.update(hectares_digits=r["digits"], hectares_words=r["hectares_words"], hectares_words_text=r["words_text"],
                   digit_reading=r["reading"], amount_status=r["status"], grant_anchor=g["anchor"])
        if g["affectation"]:
            out["amount_status"] = (r["status"] or "") + "+affectation_anchor"
        elif r["hectares"] is not None:
            out["hectares"] = r["hectares"]
            out.update(land_classes(sec, g, r["hectares"]))
    # beneficiaries: 03's rules on the note's own resolutive points, else its census count
    bm = P03.BENEF_RE.search(P03.fix_digits(sec)) if sec else None
    if bm:
        out["beneficiaries"], out["beneficiaries_source"] = int(bm.group("n").replace(",", "")), "operative"
    else:
        cm = list(P03.CENSUS_RE.finditer(t[own["start"]: (rs or own["sign_start"])]))
        out["beneficiaries"], out["beneficiaries_source"] = ((int(cm[-1].group("n").replace(",", "")), "census") if cm else (None, None))
    deny = P03.DENIAL_RE.search(sec) if sec else None
    out["grant"] = 1 if g is not None else (0 if (deny and out["body_type"] == "unknown" and sec) else None)
    s = signing_of(t, sec_end, own) if sec else {"signing_date": None, "president_signing_text": None, "signer_body": None}
    out["signing_date"] = s["signing_date"]
    out["signer_body"] = s.get("signer_body")
    pres = s.get("president_signing_text")
    if out["signer_body"] == "president" and pres is None:
        pres = P03.president_on(s["signing_date"])
    out["signer"] = pres if out["signer_body"] == "president" else None
    out["_section"], out["_grant"], out["_heading"], out["_rs"] = sec, g, t[:400], rs
    return out


def corroboration(t: str, g: dict, r_digits: str | None, r_words: float | None) -> str:
    """Sentences elsewhere in the text that repeat the surface (either reading), for the LLM."""
    keys = set()
    if r_words:
        keys.add(str(int(r_words)))
    for v, _ in digit_readings(r_digits).values() if r_digits else []:
        keys.add(str(int(v)))
    out = []
    for k in keys:
        if len(k) < 2:
            continue
        kk = f"{int(k):,}" if len(k) > 3 else k
        for m in re.finditer(rf"(?<![\d,]){re.escape(kk)}\s?-\s?\d\d", t):
            out.append(t[max(0, m.start() - 160): m.end() + 120])
    return "\n...\n".join(out[:4])


def build(args, pop: pd.DataFrame) -> pd.DataFrame:
    tgt = pop[pop.hectares_total.isna()].copy()
    print(f"targets: {len(tgt)} land-grant DOF rows with text and no hectares")
    texts = load_texts(set(tgt.codNota), set(tgt.dof_year.astype(int)))
    llm = LLM(args.offline, args.max_new_usd)
    rows = []
    for _, row in tgt.iterrows():
        cod = int(row.codNota)
        src = texts[cod]
        r = parse_note(cod, src, row)
        r.update({"dof_date": row.dof_date, "dof_year": int(row.dof_year), "action_type_title": row.action_type,
                  "state_name": row.state_name, "poblado": row.poblado, "ncpe_name": row.ncpe_name,
                  "ledger_beneficiaries": row.beneficiaries, "ledger_signing_date": row.signing_date,
                  "ledger_president": row.president_ledger, "text_source": "sidof_fulltext",
                  "source_file": f"{DOF_SIDOF_FULLTEXT_DIR.name}/{src['file']}", "source_line": src["line"],
                  "method": None, "confidence": None, "note": None, "dof_title": row.dof_title})
        g = r["_grant"]
        if r["hectares"] is not None:
            st = r["amount_status"]
            r["method"] = "rules_words" if st == "words_only" else "rules"
            r["confidence"] = {"digits_words_agree": "high"}.get(st, "medium")
        needs_llm = r["body_type"] == "land_grant" and r["hectares"] is None
        if needs_llm:
            t = norm(src["text"])
            sec = r["_section"]
            ctx = corroboration(t[: r["_rs"]], g, r["hectares_digits"], r["hectares_words"]) if g else ""
            prompt = LLM_PROMPT.format(poblado=r["ncpe_name"] if isinstance(r["ncpe_name"], str) else r["poblado"],
                                       text=r["_heading"][:300] + "\n\n" + sec[:6000] + ("\n\nOTHER SENTENCES:\n" + ctx if ctx else ""))
            dec, conf, answers = llm.two_reads(f"text_{cod}", prompt)
            r["llm_reads"] = json.dumps([{k: a.get(k) for k in ("_model", "hectares", "hectares_digits", "hectares_words",
                                                                "beneficiaries", "is_land_grant", "explanation")} for a in answers],
                                        ensure_ascii=False)
            if dec is not None and dec.get("hectares") is not None and dec.get("is_land_grant"):
                r["hectares"] = round(float(dec["hectares"]), 6)
                r["method"] = "llm"
                agrees = any(abs(r["hectares"] - v) < 0.00015 for v in ([r["hectares_words"]] if r["hectares_words"] else []) +
                             [v for v, _ in (digit_readings(r["hectares_digits"]).values() if r["hectares_digits"] else [])])
                r["confidence"] = ("high" if conf == "two_reads_agree" and agrees else
                                   "medium" if conf in ("two_reads_agree", "tiebreak_majority") else "low")
                r["note"] = f"LLM {conf}: {dec.get('explanation')}"
                if g is not None:
                    r.update(land_classes(sec, {**g, "amount": {**g["amount"]}}, r["hectares"]))
            elif dec is not None and dec.get("is_land_grant") is False:
                r["note"] = f"LLM {conf}: not a land grant ({dec.get('explanation')})"
            else:
                r["note"] = f"LLM {conf}"
        rows.append(r)
    df = pd.DataFrame(rows)
    # non-grants whose own DOF title names the act: 03's title rules took the action from a keyword such as "unidades de
    # dotacion" (acomodo, reconocimiento de derechos), "nuevo centro de poblacion" (division of an NCPE ejido) or
    # "reconocimiento y titulacion" (initiation of that procedure)
    named = df.reason_missed.str.startswith("not_a_land_grant") & df.dof_title.map(norm).str.contains(
        r"derechos|acomodo|division|iniciacion|instauracion")
    df.loc[named, "note"] = ("the DOF title itself names this act; 03 took the land-grant action from a keyword in the title "
                             "(e.g. 'unidades de dotacion', 'nuevo centro de poblacion', 'reconocimiento y titulacion')")
    return df, tgt, texts, llm


def apply_hand(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """Hand readings (HAND_READINGS) for notes still without a value: method 'hand'."""
    for cod, h in HAND_READINGS.items():
        if h["source"] != source or cod not in set(df.codNota):
            continue
        i = df.index[df.codNota == cod][0]
        if pd.notna(df.at[i, "hectares"]) and df.at[i, "method"] in ("rules", "rules_words", "llm"):
            continue
        if h.get("reason"):
            df.at[i, "reason_missed"], df.at[i, "reason_detail"] = h["reason"], h.get("reason_detail")
        if h.get("is_land_grant", True) and h.get("hectares") is None:
            df.at[i, "body_type"] = "land_grant_not_printed"
            df.at[i, "grant"] = 1
            prev = df.at[i, "note"] if isinstance(df.at[i, "note"], str) else ""
            df.at[i, "note"] = (prev + " | " if prev else "") + f"not recoverable ({source}): {h['evidence']}"
            df.at[i, "text_source"] = "scanned_edition" if source == "scan" else df.at[i, "text_source"]
            if h.get("pdf_pages"):
                df.at[i, "scan_pdf_pages"] = "+".join(map(str, h["pdf_pages"]))
            continue
        if h.get("is_land_grant", True):
            df.at[i, "hectares"] = h["hectares"]
            for c in CLASSES:
                df.at[i, f"ha_{c}"] = 0.0
            cl = h.get("classes") or {}
            for c, v in cl.items():
                df.at[i, f"ha_{c}"] = v
            rem = h["hectares"] - sum(cl.values())
            if rem > 0.01:
                df.at[i, "ha_indefinido"] = round(rem, 6)
            df.at[i, "grant"] = 1
            df.at[i, "body_type"] = "land_grant"
        else:
            df.at[i, "grant"] = None
            df.at[i, "body_type"] = h.get("body_type", "not_land_grant")
        for k in ("beneficiaries", "signing_date", "signer", "hectares_digits", "hectares_words_text"):
            if k in h:
                df.at[i, k] = h[k]
        if "beneficiaries" in h:
            df.at[i, "beneficiaries_source"] = f"hand_{source}"
        df.at[i, "method"] = "hand"
        df.at[i, "confidence"] = h.get("confidence", "high")
        prev = df.at[i, "note"] if isinstance(df.at[i, "note"], str) else ""
        df.at[i, "note"] = (prev + " | " if prev else "") + f"hand reading ({source}): {h['evidence']}"
        if source == "scan":
            df.at[i, "text_source"] = "scanned_edition"
            if h.get("pdf_pages"):
                df.at[i, "scan_pdf_pages"] = "+".join(map(str, h["pdf_pages"]))
    return df


def apply_scans(df: pd.DataFrame, tgt: pd.DataFrame, llm: LLM, args) -> pd.DataFrame:
    """Notes whose SIDOF text cannot give the grant (garbled or truncated text, a body that contradicts its title, or
    a grant the text could not settle): locate the note in the scanned edition (OCR search), render its pages, and read
    them (vision LLM, two reads + tie-break; else the hand readings in HAND_READINGS with source 'scan')."""
    title_names_body = df.dof_title.map(norm).str.contains(r"derechos|acomodo|division|iniciacion|instauracion|inafectab|"
                                                            r"colonia agricola|colonizacion")
    need = df[(df.reason_missed == "text_garbled_or_truncated")
              | (df.reason_missed.str.startswith("not_a_land_grant") & ~title_names_body)
              | ((df.body_type == "land_grant") & df.hectares.isna())]
    tmp = Path(args.scan_tmp)
    tl = tgt.set_index("codNota")
    recs, by_ed = {}, {}
    for cod in need.codNota:
        rec = note_record(int(cod), args.fetch_scans and not args.offline)
        if rec is None or rec.get("existePdf") != "S":
            continue
        recs[int(cod)] = rec
        by_ed.setdefault(int(rec["codDiario"]), []).append(int(cod))
    print(f"scans: {len(need)} notes need the scanned edition; {len(recs)} with a note record, {len(by_ed)} editions")
    pages_by_edition: dict[int, str] = {}
    for cd, cods in sorted(by_ed.items()):
        path = ensure_edition(recs[cods[0]], tmp, args.fetch_scans and not args.offline)
        if path is None:
            continue
        pages = load_pages(path)
        pdf = tmp / f"{cd}.pdf"
        if not pdf.exists() and args.render_reused and not args.offline:
            # edition stored earlier (OCR reused, no new manifest row): the PDF is fetched again only to look at pages
            status, ctype, body = polite_get(f"{SIDOF}/documentos/pdf/{cd}", 600)
            if status == 200 and body[:4] == b"%PDF":
                pdf.write_bytes(body)
        recovered = []
        for cod in cods:
            rec, row = recs[cod], tl.loc[cod]
            i = df.index[df.codNota == cod][0]
            keys = [norm(x) for x in (row.ncpe_name, row.poblado) if isinstance(x, str) and len(x) >= 5]
            tm = re.search(r"denominar[ai]\s+(.{8,45}?)(?:,|\(|$)|denominad[oa]\s+(.{8,45}?)(?:,|\(|$)", norm(str(row.dof_title)))
            if tm:
                keys.append((tm.group(1) or tm.group(2)).strip())
            pp = HAND_READINGS.get(cod, {}).get("pdf_pages") or locate_note_pages(pages, cod, keys, rec.get("pagina"))
            df.at[i, "scan_edition_file"] = f"{SCAN_DIR.name}/{path.name}"
            df.at[i, "scan_pdf_pages"] = "+".join(map(str, pp))
            imgs = []
            if pdf.exists():
                (tmp / "pages").mkdir(parents=True, exist_ok=True)
                for p in pp:
                    f = tmp / "pages" / f"{cod}_{cd}_p{p}.png"
                    if not f.exists():
                        f.write_bytes(render_pages(pdf, [p])[0])
                    imgs.append(f.read_bytes())
            if HAND_READINGS.get(cod, {}).get("source") == "scan":
                hp = HAND_READINGS[cod].get("pdf_pages")
                if hp:                                    # pages read by hand ([] = the note is not in the scan)
                    recovered.append(f"{cod}:{min(hp)}-{max(hp)}" if len(hp) > 1 else f"{cod}:{hp[0]}")
                continue
            if not imgs or llm.unavailable or args.offline:
                continue
            title = rec.get("titulo") or row.dof_title
            prompt = VISION_PROMPT.format(date=rec.get("fecha"), title=re.sub(r"\s+", " ", str(title)).strip())
            dec, conf, answers = llm.two_reads(f"scan_{cod}", prompt, imgs)
            df.at[i, "scan_llm_reads"] = json.dumps([{k: a.get(k) for k in ("_model", "found", "hectares", "hectares_digits",
                                                                              "hectares_words", "beneficiaries", "signing_date",
                                                                              "is_land_grant", "explanation")} for a in answers],
                                                    ensure_ascii=False)
            if dec is None or not dec.get("found"):
                continue
            recovered.append(f"{cod}:{min(pp)}-{max(pp)}")
            df.at[i, "text_source"] = "scanned_edition"
            if dec.get("is_land_grant") and dec.get("hectares") is not None:
                df.at[i, "hectares"] = round(float(dec["hectares"]), 6)
                df.at[i, "hectares_digits"] = dec.get("hectares_digits")
                df.at[i, "hectares_words_text"] = dec.get("hectares_words")
                df.at[i, "method"], df.at[i, "confidence"] = "llm", ("high" if conf == "two_reads_agree" else "medium")
                df.at[i, "grant"], df.at[i, "body_type"] = 1, "land_grant"
                for c in CLASSES:
                    df.at[i, f"ha_{c}"] = 0.0
                df.at[i, "ha_indefinido"] = df.at[i, "hectares"]
                if dec.get("beneficiaries") is not None:
                    df.at[i, "beneficiaries"], df.at[i, "beneficiaries_source"] = int(dec["beneficiaries"]), "scan_operative"
                if dec.get("signing_date") and pd.isna(df.at[i, "signing_date"]):
                    try:
                        df.at[i, "signing_date"] = dt.date.fromisoformat(dec["signing_date"])
                        df.at[i, "signer"] = dec.get("signer")
                    except ValueError:
                        pass
                df.at[i, "note"] = f"scan LLM {conf}: {dec.get('explanation')}"
            elif dec.get("is_land_grant") is False:
                df.at[i, "body_type"], df.at[i, "grant"] = "not_land_grant_scan", None
                df.at[i, "note"] = f"scan LLM {conf}: not a land grant ({dec.get('explanation')})"
        if recovered:
            pages_by_edition[cd] = ";".join(recovered)
        if pdf.exists() and not args.keep_pdf:
            pdf.unlink()                                  # keep only the OCR pages and the manifest row
    if args.finalize_manifest:
        finalize_manifest(tmp, pages_by_edition)
    return df


# ------------------------------------------------------------------------------------------------ validation
VALID_COLS = ["check", "sample", "codNota", "dof_year", "field", "truth", "extracted", "correct", "mechanism", "ha_03",
              "method", "text_source", "note"]


def _old_truth() -> dict:
    """Hand-typed truth already in the validation file: (check, codNota, field) -> (truth, note)."""
    if not VALID_CSV.exists():
        return {}
    v = pd.read_csv(VALID_CSV, dtype=str)
    v = v[v.truth.notna() & (v.truth != "")]

    def hand_note(x):
        # the stored note minus the "03 correct/wrong" verdicts that spillover_rows prepends on every run
        x = re.sub(r"^(?:03 (?:correct|wrong)(?:; |$))+", "", x) if isinstance(x, str) else ""
        return x or None
    return {(r.check, int(r.codNota), r.field): (r.truth, hand_note(r.note)) for r in v.itertuples()}


def _same(field: str, truth, ext) -> bool | None:
    if truth is None or (isinstance(truth, float) and np.isnan(truth)) or truth == "":
        return None
    if str(truth).strip().lower() in ("none", "nan", "null"):
        return ext is None or (isinstance(ext, float) and np.isnan(ext)) or str(ext) in ("", "nan", "None", "NaT")
    if field in ("hectares", "beneficiaries", "ha_03"):
        try:
            return abs(float(truth) - float(ext)) <= 0.0002 + 1e-6 * abs(float(truth))
        except (TypeError, ValueError):
            return False
    return str(truth)[:10] == str(ext)[:10]


def handcheck_rows(out: pd.DataFrame, old: dict) -> list[dict]:
    """30 random recovered notes (fixed seed): hectares, beneficiaries and signing date, truth read by hand. Once truth is
    stored, the sample is frozen to those notes (a change in the rules must not redraw it and orphan the readings)."""
    frozen = list(dict.fromkeys(c for (chk, c, _f) in old if chk == "handcheck"))
    if frozen:
        smp = out.set_index("codNota").loc[[c for c in frozen if c in set(out.codNota)]].reset_index()
    else:
        rec = out[out.hectares.notna()].sort_values("codNota")
        smp = rec.sample(n=min(30, len(rec)), random_state=SEED)
    rows = []
    for r in smp.itertuples():
        for f in ("hectares", "beneficiaries", "signing_date"):
            ext = getattr(r, f)
            tr, nt = old.get(("handcheck", int(r.codNota), f), (None, None))
            rows.append({"check": "handcheck", "sample": "random30_recovered", "codNota": int(r.codNota), "dof_year": r.dof_year,
                         "field": f, "truth": tr, "extracted": ext, "correct": _same(f, tr, ext), "mechanism": r.reason_missed,
                         "ha_03": None, "method": r.method, "text_source": r.text_source, "note": nt})
    return rows


def spillover(args, pop: pd.DataFrame) -> pd.DataFrame:
    """03's hectares vs these rules on every DOF land-grant row that HAS hectares and a text: where they differ, which
    of the mechanisms behind the 197 misses is present (03 read an appended note / a later point / skipped a verb
    variant / skipped a malformed amount)."""
    pop = pop[pop.hectares_total.notna()].copy()
    texts = load_texts(set(pop.codNota), set(pop.dof_year.astype(int)))
    res = []
    for _, row in pop.iterrows():
        cod = int(row.codNota)
        if cod not in texts:
            continue
        t = norm(texts[cod]["text"])
        try:
            r = parse_note(cod, texts[cod], row)
        except Exception as e:                          # never let one odd text stop the check
            res.append({"codNota": cod, "dof_year": int(row.dof_year), "ha_03": row.hectares_total, "ha_06": None,
                        "mechanism": f"error:{type(e).__name__}"})
            continue
        g = r["_grant"]
        mech = []
        if r["_rs"] is not None:
            sec_end = r["_rs"] + len(r["_section"])
            op03 = p03_operative_start(t)
            if op03 > sec_end:
                mech.append("multi_document_text")
            elif g is not None and op03 > r["_rs"] + g["amount"]["pos"]:
                mech.append("operative_mislocated")
            if g is not None:
                sec = r["_section"]
                conc = P03.CONCESSION_RE.search(sec)
                if not conc or conc.start() > g["anchor_pos"] + 2:
                    mech.append("verb_variant")
                am = g["amount"]
                got = P03.amounts_in(P03.fix_digits(sec[am["pos"]: am["end"] + 3]))
                if r["hectares"] is not None and not (got and got[0][0] <= 2 and abs(got[0][2] - r["hectares"]) <= 0.01 * r["hectares"]):
                    mech.append("amount_format")
        res.append({"codNota": cod, "dof_year": int(row.dof_year), "ha_03": float(row.hectares_total), "ha_06": r["hectares"],
                    "status_06": r["amount_status"], "body_type": r["body_type"], "mechanism": ";".join(mech) or None,
                    "ben_03": row.beneficiaries, "ben_06": r["beneficiaries"], "sd_03": row.signing_date,
                    "sd_06": str(r["signing_date"]) if r["signing_date"] else None,
                    "signer_06": r["signer"], "signer_body_06": r["signer_body"], "village_in_section": r["poblado_in_resolutive"],
                    "n_documents_in_text": r["n_documents_in_text"], "hectares_digits": r["hectares_digits"],
                    "hectares_words_text": r["hectares_words_text"], **{f"ha06_{c}": r.get(f"ha_{c}") for c in CLASSES}})
    S = pd.DataFrame(res)
    S["agree"] = (S.ha_06.notna() & ((S.ha_03 - S.ha_06).abs() <= 0.005 * S.ha_03.abs() + 0.01))
    S["differs"] = S.ha_06.notna() & ~S.agree
    return S


def spillover_rows(S: pd.DataFrame, old: dict) -> list[dict]:
    rows = []
    for mech, g in S.groupby(S.mechanism.fillna("none")):
        rows.append({"check": "spillover_summary", "sample": "all_land_grant_rows_with_hectares", "codNota": 0, "dof_year": None,
                     "field": "n_rows|n_parsed|n_differs", "truth": None,
                     "extracted": f"{len(g)}|{int(g.ha_06.notna().sum())}|{int(g.differs.sum())}", "correct": None,
                     "mechanism": mech, "ha_03": None, "method": None, "text_source": None, "note": None})
    # hand check: 25 random rows where the two parsers differ and a mechanism is present, + 10 that differ without one
    # (drawn on 2026-10-14; frozen to the notes whose truth is stored, so that later rule changes do not redraw it)
    frozen = list(dict.fromkeys(c for (chk, c, _f) in old if chk == "spillover_handcheck"))
    if frozen:
        smp = S.set_index("codNota").loc[[c for c in frozen if c in set(S.codNota)]].reset_index()
    else:
        d = S[S.differs].sort_values("codNota")
        smp = pd.concat([d[d.mechanism.notna()].sample(n=min(25, int(d.mechanism.notna().sum())), random_state=SEED),
                         d[d.mechanism.isna()].sample(n=min(10, int(d.mechanism.isna().sum())), random_state=SEED)])
    for r in smp.itertuples():
        tr, nt = old.get(("spillover_handcheck", int(r.codNota), "hectares"), (None, None))
        c03 = _same("hectares", tr, r.ha_03)
        rows.append({"check": "spillover_handcheck", "sample": "differs_with_mechanism" if isinstance(r.mechanism, str) else
                     "differs_no_mechanism", "codNota": int(r.codNota), "dof_year": r.dof_year, "field": "hectares",
                     "truth": tr, "extracted": r.ha_06, "correct": _same("hectares", tr, r.ha_06), "mechanism": r.mechanism,
                     "ha_03": r.ha_03, "method": "rules", "text_source": "sidof_fulltext",
                     "note": "; ".join(x for x in (None if c03 is None else f"03 {'correct' if c03 else 'wrong'}", nt) if x)})
    # estimate: rows whose 03 hectares are wrong by these mechanisms (the hand-checked share applied to the differences)
    hc = [x for x in rows if x["check"] == "spillover_handcheck" and x["truth"] is not None]
    wrong03 = sum(1 for x in hc if not _same("hectares", x["truth"], x["ha_03"]))
    right06 = sum(1 for x in hc if x["correct"])
    d = S[S.differs]
    est = [("n_rows_with_hectares_and_text", len(S)), ("n_parsed_by_06", int(S.ha_06.notna().sum())),
           ("n_differ_from_03", len(d)), ("share_differ_from_03", round(len(d) / max(len(S), 1), 4)),
           ("handcheck_n", len(hc)), ("handcheck_03_wrong", wrong03), ("handcheck_06_correct", right06),
           ("estimated_rows_with_wrong_03_hectares", round(len(d) * wrong03 / max(len(hc), 1))),
           ("hectares_03_in_differing_rows", round(float(d.ha_03.sum()), 1)),
           ("hectares_06_in_differing_rows", round(float(d.ha_06.sum()), 1)),
           ("abs_hectare_difference_in_differing_rows", round(float((d.ha_06 - d.ha_03).abs().sum()), 1)),
           ("signing_date_differs_multi_document_rows", int(((S.sd_03.astype(str) != S.sd_06.astype(str)) & S.sd_06.notna()
                                                             & S.sd_03.notna() & S.mechanism.fillna("").str.contains("multi")).sum())),
           ("beneficiaries_differ_multi_document_rows", int(((S.ben_03 != S.ben_06) & S.ben_06.notna() & S.ben_03.notna()
                                                             & S.mechanism.fillna("").str.contains("multi")).sum()))]
    for k, v in est:
        rows.append({"check": "spillover_estimate", "sample": "all_land_grant_rows_with_hectares", "codNota": 0, "dof_year": None,
                     "field": k, "truth": None, "extracted": v, "correct": None, "mechanism": None, "ha_03": None,
                     "method": None, "text_source": None, "note": None})
    return rows


def build_validation(out: pd.DataFrame, args, S: pd.DataFrame):
    old = _old_truth()
    rows = handcheck_rows(out, old)
    rows += spillover_rows(S, old)
    V = pd.DataFrame(rows, columns=VALID_COLS)
    V.to_csv(VALID_CSV, index=False)
    hc = V[(V.check == "handcheck") & V.correct.notna()]
    print(f"-> {VALID_CSV.name}: hand check {int(hc.correct.astype(bool).sum())}/{len(hc)} fields correct")
    for f, g in hc.groupby("field"):
        print(f"   {f}: precision {g.correct.astype(bool).mean():.3f} ({int(g.correct.astype(bool).sum())}/{len(g)})")
    print("spillover (rows with hectares):", len(S), "parsed", int(S.ha_06.notna().sum()), "differ", int(S.differs.sum()))
    print(S[S.differs].mechanism.fillna("none").value_counts().to_string())
    return V, S


# ------------------------------------------------------------------------------------------- corrections table
LAND_GRANT_BODIES = {"land_grant", "land_grant_not_printed"}
CORR_COLS = ["codNota", "dof_date", "dof_year", "population", "mechanism", "n_documents_in_text",
             "hectares_03", "hectares_reparse", "reparse_amount_status", "hectares", "hectares_source", "hectares_method",
             "hectares_confidence", *[f"ha_{c}" for c in CLASSES],
             "beneficiaries_03", "beneficiaries_reparse", "beneficiaries", "beneficiaries_source",
             "signing_date_03", "signing_date_reparse", "signing_date", "signer", "signer_body", "president_signing",
             "president_source", "signing_source", "grant", "land_grant_printed", "not_land_grant_reason", "note"]


def _nn(v) -> bool:
    return v is not None and not (isinstance(v, float) and np.isnan(v)) and str(v) not in ("", "nan", "NaT", "None", "<NA>")


def _eq(a, b) -> bool:
    if not _nn(a) and not _nn(b):
        return True
    if not (_nn(a) and _nn(b)):
        return False
    try:
        return abs(float(a) - float(b)) <= 1e-6 * max(1.0, abs(float(a)))
    except (TypeError, ValueError):
        return str(a)[:10] == str(b)[:10]


def _president(signer, signer_body, signing_date) -> tuple:
    """(president_signing, president_source) of a note's own closing, by 03's rule: the name in the signature; else the
    president in office on the signing date when the President signed; no president when a tribunal, a Comision
    Agraria Mixta or the SRA signed; (None, None) when the closing says nothing (04 then infers from the DOF date)."""
    if _nn(signer):
        return signer, "text_name"
    if _nn(signer_body) and signer_body != "president":
        return None, f"not_presidential_{signer_body}"
    if _nn(signing_date) and signer_body == "president":
        return P03.president_on(pd.Timestamp(str(signing_date)[:10]).date()), "text_signing_date"
    return None, None


def build_corrections(out: pd.DataFrame, S: pd.DataFrame, pop: pd.DataFrame) -> pd.DataFrame:
    """The values 04 writes into the ledger for every DOF land-grant note with a full text (load_population), one row per
    note, with the source of each field and 03's value for audit (*_03). Sources: dof_text_03 (03's parse, unchanged),
    dof_text_reparse (these rules or a hand reading on the SIDOF text), dof_scan (read on the scanned edition's page).
      Notes 03 parsed without hectares (`out`, the 197 targets): this script's final reading. Beneficiaries and the
        signing date / signer come from the note's own document when read there; otherwise 03's are kept, unless the text
        holds another note (several signed documents, or a printed note spliced with another act), in which case 03's
        value belongs to that note and is dropped. Notes that are not land grants in print: land_grant_printed = 0.
      Notes 03 parsed with hectares (`S`): 03's total is replaced when these rules read a different total on the note's own
        resolutive points (hand check: in 30 differing rows read by hand 03 was wrong 30 times; these rules were right 29
        times before the OCR-hyphen fix of "10,470-32j51", 30 after it), or by a hand reading where both misread
        (HAND_READINGS, source sidof_text). In multi-document texts 03 read the appended note: beneficiaries, signing
        date and signer are replaced by the own note's (empty when the own note prints none), and the hectares dropped
        when the own grant cannot be read (no such note left after the hand readings).
    Land classes follow the hectares' source; president_signing / president_source follow the signing source."""
    P = pop.set_index("codNota")
    rows = []

    def base(cod, p_, population, mech, ndocs):
        cls = {f"ha_{c}": p_.get(f"ha_{c}") for c in CLASSES}
        return {"codNota": cod, "dof_date": p_.dof_date, "dof_year": int(p_.dof_year), "population": population,
                "mechanism": mech or None, "n_documents_in_text": ndocs,
                "hectares_03": p_.hectares_total, "hectares": p_.hectares_total,
                "hectares_source": "dof_text_03" if _nn(p_.hectares_total) else None,
                "hectares_method": "03" if _nn(p_.hectares_total) else None, "hectares_confidence": None, **cls,
                "beneficiaries_03": p_.beneficiaries, "beneficiaries": p_.beneficiaries,
                "beneficiaries_source": "dof_text_03" if _nn(p_.beneficiaries) else None,
                "signing_date_03": p_.signing_date, "signing_date": p_.signing_date,
                "signer": p_.president_signing_text if _nn(p_.get("president_signing_text")) else None,
                "signer_body": p_.signer_body if _nn(p_.get("signer_body")) else None,
                "president_signing": p_.president_signing if _nn(p_.president_signing) else None,
                "president_source": p_.president_source if _nn(p_.president_source) else None,
                "signing_source": "dof_text_03" if _nn(p_.signing_date) or _nn(p_.president_signing) else None,
                "grant": p_.grant if _nn(p_.grant) else None, "land_grant_printed": 1, "not_land_grant_reason": None,
                "note": None}

    def set_signing(r, sd, signer, body, source):
        r["signing_date"] = str(sd)[:10] if _nn(sd) else None
        r["signer"] = signer if _nn(signer) else None
        r["signer_body"] = body if _nn(body) else None
        r["president_signing"], r["president_source"] = _president(r["signer"], r["signer_body"], r["signing_date"])
        r["signing_source"] = source

    # ---- notes 03 parsed without hectares: this script's reading
    for a in out.to_dict("records"):
        cod = int(a["codNota"])
        p_ = P.loc[cod]
        reason = ";".join(str(a[k]) for k in ("reason_missed", "reason_detail") if _nn(a.get(k)))
        r = base(cod, p_, "no_03_hectares", reason, a.get("n_documents_in_text"))
        r["hectares_reparse"], r["reparse_amount_status"] = a.get("hectares"), a.get("amount_status")
        r["beneficiaries_reparse"], r["signing_date_reparse"] = a.get("beneficiaries"), a.get("signing_date")
        scan = a.get("text_source") == "scanned_edition"
        # the text holds another note: 03's values (and, for a printed note spliced with another act, the closing found
        # after the note's own text) belong to that note
        spliced = "spliced" in reason
        other_note = ("multi_document_text" in reason or (_nn(a.get("n_documents_in_text")) and a["n_documents_in_text"] > 1)
                      or spliced or (a.get("body_type") == "land_grant_not_printed" and "no_resolutive_points" in reason))
        if _nn(a.get("hectares")):
            r.update(hectares=a["hectares"], hectares_source="dof_scan" if scan else "dof_text_reparse",
                     hectares_method=a.get("method"), hectares_confidence=a.get("confidence"),
                     **{f"ha_{c}": a.get(f"ha_{c}") for c in CLASSES})
        r["grant"] = a.get("grant") if _nn(a.get("grant")) else None
        if a.get("body_type") not in LAND_GRANT_BODIES:
            r["land_grant_printed"] = 0
            r["not_land_grant_reason"] = f"{a.get('body_type')}: {a.get('note') or ''}".strip(" :")
        b = a.get("beneficiaries")
        if _nn(b) and not _eq(b, r["beneficiaries_03"]):
            r["beneficiaries"] = b
            r["beneficiaries_source"] = "dof_scan" if str(a.get("beneficiaries_source")).endswith("scan") else "dof_text_reparse"
        elif not _nn(b) and _nn(r["beneficiaries_03"]) and other_note:
            r["beneficiaries"], r["beneficiaries_source"] = None, "dof_text_reparse"
            r["note"] = "03's beneficiaries belong to another note in the text; the own note prints none"
        sd = a.get("signing_date") if not spliced else None
        if _nn(sd) and (not _eq(sd, r["signing_date_03"]) or not _nn(r["president_signing"])):
            set_signing(r, sd, a.get("signer"), a.get("signer_body"), "dof_scan" if scan else "dof_text_reparse")
        elif not _nn(sd) and (_nn(r["signing_date_03"]) or _nn(r["president_source"])) and other_note:
            set_signing(r, None, None, None, "dof_text_reparse")
            r["note"] = "; ".join(x for x in (r["note"], "03's signing date / signer belong to another act in the text") if x)
        rows.append(r)

    # ---- notes 03 parsed with hectares: replace what these rules (or a hand reading) show 03 misread
    for s_ in S.to_dict("records"):
        cod = int(s_["codNota"])
        p_ = P.loc[cod]
        mech = s_.get("mechanism") if isinstance(s_.get("mechanism"), str) else ""
        multi = "multi_document_text" in mech
        r = base(cod, p_, "has_03_hectares", mech, s_.get("n_documents_in_text"))
        r["hectares_reparse"], r["reparse_amount_status"] = s_.get("ha_06"), s_.get("status_06")
        r["beneficiaries_reparse"], r["signing_date_reparse"] = s_.get("ben_06"), s_.get("sd_06")
        h = HAND_READINGS.get(cod) if HAND_READINGS.get(cod, {}).get("source") == "sidof_text" else None
        vflag = s_.get("village_in_section")
        if multi and vflag is not None and not (isinstance(vflag, float) and np.isnan(vflag)) and not bool(vflag) and h is None:
            # the first document of the text names another village: SIDOF spliced another note's pages into this one
            # (4699456 carries 20 de Noviembre's resolutive points), so the "own" document is not the note's; 03 kept
            r["note"] = ("the first document in the text names another village (pages of another note spliced in); "
                         "03's reading of the last document kept")
            rows.append(r)
            continue
        if h is not None and h.get("hectares") is not None:
            cl = {c: 0.0 for c in CLASSES}
            cl.update(h.get("classes") or {})
            rem = h["hectares"] - sum(cl.values())
            if rem > 0.01:
                cl["indefinido"] += round(rem, 6)
            r.update(hectares=h["hectares"], hectares_source="dof_text_reparse", hectares_method="hand",
                     hectares_confidence=h.get("confidence", "high"), **{f"ha_{c}": cl[c] for c in CLASSES})
            r["note"] = f"hand reading: {h['evidence']}"
        elif bool(s_.get("differs")):
            st = s_.get("status_06")
            r.update(hectares=s_["ha_06"], hectares_source="dof_text_reparse",
                     hectares_method="rules_words" if st == "words_only" else "rules",
                     hectares_confidence="high" if st == "digits_words_agree" else "medium",
                     **{f"ha_{c}": s_.get(f"ha06_{c}") for c in CLASSES})
        elif multi and not _nn(s_.get("ha_06")):
            r.update(hectares=None, hectares_source="dof_text_reparse", hectares_method=None, hectares_confidence=None,
                     **{f"ha_{c}": None for c in CLASSES})
            r["note"] = "03's hectares belong to the appended note; the own grant could not be read"
        if h is not None and "beneficiaries" in h:
            if not _eq(h["beneficiaries"], r["beneficiaries_03"]):
                r["beneficiaries"], r["beneficiaries_source"] = h["beneficiaries"], "dof_text_reparse"
        elif multi and not _eq(s_.get("ben_06"), r["beneficiaries_03"]):
            r["beneficiaries"] = s_.get("ben_06") if _nn(s_.get("ben_06")) else None
            r["beneficiaries_source"] = "dof_text_reparse"
            if not _nn(s_.get("ben_06")):
                r["note"] = "; ".join(x for x in (r["note"], "03's beneficiaries belong to the appended note; the own note prints none") if x)
        if h is not None and "signing_date" in h:
            if not _eq(h["signing_date"], r["signing_date_03"]) or not _eq(h.get("signer"), r["president_signing"]):
                set_signing(r, h["signing_date"], h.get("signer"), "president", "dof_text_reparse")
            r["note"] = "; ".join(x for x in (r["note"], f"hand reading: {h['evidence']}") if x and x not in str(r["note"]))
        elif multi and not _eq(s_.get("sd_06"), r["signing_date_03"]):
            set_signing(r, s_.get("sd_06"), s_.get("signer_06"), s_.get("signer_body_06"), "dof_text_reparse")
        rows.append(r)
    C = pd.DataFrame(rows)
    for c in CORR_COLS:
        if c not in C:
            C[c] = None
    C = C[CORR_COLS].sort_values(["dof_date", "codNota"]).reset_index(drop=True)
    assert C.codNota.is_unique and len(C) == len(pop), (len(C), len(pop))
    return C


def corrections_summary(C: pd.DataFrame):
    ch_h = C.hectares_source.isin(["dof_text_reparse", "dof_scan"])
    ch_b = C.beneficiaries_source.isin(["dof_text_reparse", "dof_scan"])
    ch_s = C.signing_source.isin(["dof_text_reparse", "dof_scan"])
    print(f"-> {CORR_CSV.name}: {len(C)} notes; hectares from this script {int(ch_h.sum())} "
          f"({C[ch_h].population.value_counts().to_dict()}); beneficiaries {int(ch_b.sum())}; signing {int(ch_s.sum())}; "
          f"not land grants in print {int((C.land_grant_printed == 0).sum())}")
    w = C[ch_h & (C.population == "has_03_hectares")]
    print(f"   notes with 03 hectares replaced: {len(w)}; 03 {w.hectares_03.sum():,.1f} ha -> {w.hectares.sum():,.1f} ha")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="no LLM calls and no downloads (cached answers only)")
    ap.add_argument("--fetch-scans", action="store_true", help="download missing scanned editions")
    ap.add_argument("--scan-tmp", default=str(Path(tempfile.gettempdir()) / "dof_editions_06"),
                    help="local folder for edition PDFs and page images (outside Dropbox)")
    ap.add_argument("--max-new-usd", type=float, default=4.5, help="cap on this run's new LLM spend")
    ap.add_argument("--keep-pdf", action="store_true", help="keep downloaded edition PDFs in --scan-tmp (for reading pages)")
    ap.add_argument("--no-validation", action="store_true", help="skip the hand-check / spillover file")
    ap.add_argument("--render-reused", action="store_true", help="fetch the PDF of an edition stored earlier, to look at pages")
    ap.add_argument("--finalize-manifest", action="store_true", help="append this run's downloaded editions to MANIFEST.csv")
    ap.add_argument("--debug", action="store_true", help="also write the row-level spillover comparison (scratch)")
    args = ap.parse_args()
    pop = load_population()
    df, tgt, texts, llm = build(args, pop)
    df = apply_hand(df, "sidof_text")
    df = apply_scans(df, tgt, llm, args)
    df = apply_hand(df, "scan")
    keep = ["codNota", "dof_date", "dof_year", "action_type_title", "state_name", "poblado", "ncpe_name", "reason_missed",
            "reason_detail", "body_type", "hectares", "hectares_digits", "hectares_words", "hectares_words_text",
            "digit_reading", "amount_status", "grant_anchor", *[f"ha_{c}" for c in CLASSES], "beneficiaries",
            "beneficiaries_source", "grant", "signing_date", "signer", "signer_body", "president_signing",
            "method", "confidence", "text_source", "source_file", "source_line", "scan_edition_file", "scan_pdf_pages",
            "n_documents_in_text", "own_document_signed", "resolutive_found", "poblado_in_resolutive",
            "ledger_beneficiaries", "ledger_signing_date", "ledger_president", "llm_reads", "scan_llm_reads", "note", "dof_title"]
    sd = pd.to_datetime(df["signing_date"], errors="coerce")
    df["president_signing"] = [P03.president_on(d.date()) if pd.notna(d) else None for d in sd]
    df.loc[df.signer.notna(), "president_signing"] = df.loc[df.signer.notna(), "signer"]
    for c in keep:
        if c not in df:
            df[c] = None
    out = df[keep].sort_values(["dof_date", "codNota"])
    out.to_csv(OUT_CSV, index=False)
    print(f"-> {OUT_CSV.name}: {len(out)} rows; new LLM spend this run ${llm.new_spend():.2f}")
    print(out.reason_missed.str.split(":").str[0].value_counts().to_string())
    print(out.groupby("method", dropna=False).size().to_string())
    S = spillover(args, pop)
    if args.debug:
        S.to_csv(Path(args.scan_tmp) / "spillover_rows_06.csv", index=False)
    if not args.no_validation:
        build_validation(out, args, S)
    C = build_corrections(out, S, pop)
    C.to_csv(CORR_CSV, index=False)
    corrections_summary(C)


if __name__ == "__main__":
    main()
