"""The losing contender himself: destinations in e+1..e+6, pre/post rungs, repeat contenders, presidents after office,
and the back-of-the-envelope president-vs-loser comparison. Reads only the bundle; writes one CSV to output/main_direct_tie."""
import csv, math, os, re, collections, statistics as st
# Paths from the environment (the staging bundle sets them): data under TAPADOSPRI_DATA_DIR, outputs under TAPADOS_MAIN_OUTPUT_DIR.
# Run: python3 slides/analysis/loser_careers.py   (reads position_tiers.csv, corcholatas_matched.csv,
# official_pay_real.csv, structural/death_years.csv and aspirants.csv (aspirants_table.R, in the output folder); writes loser_careers.csv, tables/loser_careers.tex,
# tables/loser_macros.tex). Written 4 November 2026 for the deck's slide on the losing contenders themselves.
DB = os.environ.get('TAPADOSPRI_DB_ROOT', os.path.expanduser('~/Dropbox/TapadosPRI'))
DATA = os.environ.get('TAPADOSPRI_DATA_DIR', DB + '/data')
OUT = os.environ.get('TAPADOS_MAIN_OUTPUT_DIR', DB + '/output/main_direct_tie')
DATA_END = 2009  # last year covered by Camp 1935-2009

cm = list(csv.DictReader(open(DATA + '/candidates/corcholatas_matched.csv')))
for r in cm:
    r['e'] = int(r['election_year']); r['pid'] = int(r['person_id']) if r['person_id'] else None; r['main'] = r['in_main_slate'] == '1'
winners = {r['e']: r['pid'] for r in cm if r['role'] == 'winner'}
losers = [r for r in cm if r['main'] and r['e'] <= 1988 and r['role'] in ('runner_up', 'loser')]
assert len(losers) == 47, len(losers)

pt_all = list(csv.DictReader(open(DATA + '/rank/position_tiers.csv')))
PEOPLE = {r['pid'] for r in losers} | {winners[e] for e in winners if e <= 1988}
# Hand corrections, applied to the 56 contenders only: cabinet-level titles the 2026-10-26 classification ranks as a
# department head (3) or leaves unranked. Each is a federal cabinet-rank office in the year written.
OVERRIDES = [  # (regex on role_text, rung, rule)
    (r"^head, (department of the )?federal district( department)?$", 9, 'df_regent'),
    (r"^head, department of fisheries$", 9, 'autonomous_dept_head'),           # Departamento de Pesca, cabinet rank; Secretaria de Pesca from Dec 1982
    (r"^secretary, department of agrarian affairs and colonization$", 9, 'autonomous_dept_head'),  # head of DAAC 1970-75
    (r"^secretary of (public health|trade|programming and budgeting|communication and transportation)$", 9, 'cabinet_secretary'),
    (r"^president$", 11, 'president'),
    (r"^president, national securities commission$", 6, 'director_general'),   # federal agency head, DG level (unranked)
    (r"^president, federal board of conciliation and arbitration$", 6, 'director_general'),
    (r"^president, agrarian court$", 7, 'supreme_court_justice'),               # federal tribunal president (unranked)
]
pt = []; applied = []
for r in pt_all:
    if not r['year_start']:
        continue
    y0 = int(float(r['year_start'])); y1 = int(float(r['year_end'])) if r['year_end'] else y0; y1 = max(y0, y1)
    rung = math.floor(float(r['hybrid_rank']) + 1e-9) if r['hybrid_rank'] else 0
    rule = r['rule']; pid = int(r['person_id'])
    if pid in PEOPLE:
        for rx, rg, ru in OVERRIDES:
            if re.search(rx, r['role_text'].strip().lower()) and rung < rg:
                applied.append(f"{r['person_name'][:28]:28s} {r['role_text'][:55]:55s} {y0}-{y1}: {rule} {r['hybrid_rank']} -> {ru} {rg}")
                rung, rule = rg, ru
    pt.append(dict(pid=pid, y0=y0, y1=y1, rung=rung, rule=rule, role=r['role_text'], ds=r['dataset']))
print('hand corrections applied:'); print('\n'.join('  ' + a for a in applied))
byp = collections.defaultdict(list)
for r in pt:
    byp[r['pid']].append(r)
death = {}
for r in csv.DictReader(open(DATA + '/structural/death_years.csv')):
    try:
        death[int(r['person_id'])] = int(float(r['death_year']))
    except ValueError:
        pass

FED_TOP = {'cabinet_secretary', 'attorney_general_federal', 'df_regent', 'autonomous_dept_head', 'big_parastatal_head',
           'presidential_chief_of_staff', 'president_private_secretary', 'parastatal_head'}
abroad_rx = re.compile(r"ambassador|embassy|minister to |plenipotentiary|representative to|united nations|president, iadb|inter-american development bank|\bconsul\b|consul general|\boas\b|unesco|\bfao\b")
ex_officio_rx = re.compile(r"^governor, (imf|world bank|iadb)")

def cat(rec):
    rule, role = rec['rule'], rec['role'].lower()
    if ex_officio_rx.search(role):
        return 'other federal'
    if rule in FED_TOP and rec['rung'] >= 8:
        return 'cabinet-level'
    if rule.startswith('governor'):
        return 'governor'
    if rule.startswith('ambassador') or rule == 'consul_general' or abroad_rx.search(role):
        return 'abroad'
    if rule.startswith('pri_') or rule.startswith('party_') or rule == 'opposition_party_leader':
        return 'party'
    if rule in ('senator', 'federal_deputy', 'chamber_leader', 'local_deputy'):
        return 'congress'
    if rule == 'supreme_court_justice':
        return 'supreme court'
    if rule in ('national_confederation_leader', 'national_union_leader', 'state_labor_leader', 'union_officer'):
        return 'labor'
    return 'other federal'
PRIORITY = ['cabinet-level', 'governor', 'abroad', 'party', 'congress', 'supreme court', 'labor', 'other federal']

# pay per design rung, 2025 pesos a month (official_pay_real.csv; file rung 1 = president -> design 11, else 11 - rung)
pay = list(csv.DictReader(open(DATA + '/rank/official_pay_real.csv')))
p27, p99 = {}, {}
for r in pay:
    d = 11 if r['rung'] == '1' else 11 - int(r['rung'])
    if r['pay_1927_monthly_2025_pesos']:
        p27.setdefault(d, []).append(float(r['pay_1927_monthly_2025_pesos']))
    if r['pay_1999_monthly_mid_2025_pesos']:
        p99.setdefault(d, []).append(float(r['pay_1999_monthly_mid_2025_pesos']))
gm = lambda v: math.exp(sum(map(math.log, v)) / len(v))
p27 = {k: gm(v) for k, v in p27.items()}; p99 = {k: gm(v) for k, v in p99.items()}
def fill(p):
    p = dict(p)
    p[8] = gm([p[7], p[9]])
    priced = sorted(k for k in p if k <= 9)
    for a, b in zip(priced, priced[1:]):
        for k in range(a + 1, b):
            p[k] = p[a] * (p[b] / p[a]) ** ((k - a) / (b - a))
    step = (p[9] / p[3]) ** (1 / 6)
    p[2] = p[3] / step; p[1] = p[2] / step
    return p
p27 = fill(p27); p99 = fill(p99)
print('pay per design rung, 2025 pesos/month (1927 scale | 1999 scale):')
for k in sorted(p27, reverse=True):
    print(f'  rung {k:2d}: {p27[k]/1000:7.0f}k | {p99.get(k, float("nan"))/1000:7.0f}k')

def annual_rank(pid, y_from, y_to):
    """max rung held in each year of [y_from, y_to]; years without a ranked post are absent."""
    out = {}
    for r in byp.get(pid, []):
        if r['rung'] < 1:
            continue
        for y in range(max(r['y0'], y_from), min(r['y1'], y_to) + 1):
            out[y] = max(out.get(y, 0), r['rung'])
    return out

rows = []; unranked_in_term = []
for L in losers:
    e, pid = L['e'], L['pid']
    recs = byp.get(pid, [])
    # the new president's term: posts started by e+5 and held in e+1..e+6 (a post starting in the handover year e+6 is the
    # next president's); unranked records count only when they are a posting abroad / international body
    in_window = [r for r in recs if r['y0'] <= e + 5 and r['y1'] >= e + 1]
    term = [r for r in in_window if r['rung'] >= 1 or (abroad_rx.search(r['role'].lower()) and not ex_officio_rx.search(r['role'].lower()))]
    unranked_in_term += [f"{e} {L['corcholata_name'][:22]:22s}: {r['role'][:70]} ({r['y0']}-{r['y1']}) [{r['ds']}]" for r in in_window if r['rung'] < 1]
    cats = {cat(r) for r in term}
    dest = next((c for c in PRIORITY if c in cats), 'none')
    pre = annual_rank(pid, e - 5, e - 2); post = {y: v for y, v in annual_rank(pid, e + 1, e + 6).items()}
    post = {}
    for r in term:
        if r['rung'] >= 1:
            for y in range(max(r['y0'], e + 1), min(r['y1'], e + 6) + 1):
                post[y] = max(post.get(y, 0), r['rung'])
    pre_max = max(pre.values(), default=0); post_max = max(post.values(), default=0)
    r_e2 = pre.get(e - 2, 0); r_p2 = post.get(e + 2, 0)
    later8 = [r for r in recs if r['rung'] >= 8 and r['y0'] >= e + 6]
    cab_again = [r for r in recs if r['rule'] in FED_TOP and r['rung'] >= 9 and r['y0'] > e]
    gov_after = [r for r in recs if r['rule'].startswith('governor') and r['y0'] > e]
    dy = death.get(pid); horizon_end = min(dy if dy else DATA_END, DATA_END)
    yrs = annual_rank(pid, e + 1, horizon_end)
    n_years = len(yrs); mean_rung = st.mean(yrs.values()) if yrs else 0.0
    pay27 = sum(12 * p27[v] for v in yrs.values()); pay99 = sum(12 * p99[v] for v in yrs.values())
    yrs6 = {y: v for y, v in yrs.items() if y <= e + 6}
    pay27_6 = sum(12 * p27[v] for v in yrs6.values())
    rows.append(dict(election=e, pid=pid, name=L['corcholata_name'], role=L['role'], destination=dest,
                     categories=';'.join(sorted(cats)), any_rung8_term=int(post_max >= 8), rung_e2=r_e2, pre_max=pre_max,
                     rung_e2_post=r_p2, post_max=post_max, kept_or_up=int(post_max >= pre_max and post_max > 0),
                     later_rung8_after_term=int(bool(later8)), later_rung8_posts='; '.join(f"{r['role']} ({r['y0']}-{r['y1']})" for r in later8),
                     cabinet_again='; '.join(f"{r['role']} ({r['y0']}-{r['y1']})" for r in cab_again),
                     governor_after='; '.join(f"{r['role']} ({r['y0']}-{r['y1']})" for r in gov_after),
                     death_year=dy if dy else '', horizon_years=horizon_end - e, years_in_office_after=n_years,
                     years_in_office_e1_e6=len(yrs6), mean_rung_after=round(mean_rung, 2),
                     pay_after_1927scale_mn=round(pay27 / 1e6, 1), pay_after_1999scale_mn=round(pay99 / 1e6, 1),
                     pay_e1_e6_1927scale_mn=round(pay27_6 / 1e6, 1),
                     posts_term='; '.join(f"{r['role']} [{r['rule']} r{r['rung']}] ({r['y0']}-{r['y1']})" for r in sorted(term, key=lambda r: -r['rung']))))
with open(OUT + '/loser_careers.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

print('\n== TASK 1: destination in e+1..e+6 (mutually exclusive, priority order)')
cnt = collections.Counter(r['destination'] for r in rows)
for c in PRIORITY + ['none']:
    if cnt[c]:
        print(f"  {c:15s} {cnt[c]:3d}  {100*cnt[c]/47:4.0f}%")
print('  any post at rung>=8 in e+1..e+6:', sum(r['any_rung8_term'] for r in rows), '/47')
print('  categories held at all (not exclusive):', collections.Counter(c for r in rows for c in r['categories'].split(';') if c))
print('  rung at e+2 >= 8 (aspirants.csv "kept a top chair"):', sum(r['rung_e2_post'] >= 8 for r in rows))
print('  highest rung e-5..e-2: mean %.2f, median %d; share >=9: %d/47' % (st.mean(r['pre_max'] for r in rows), st.median(r['pre_max'] for r in rows), sum(r['pre_max'] >= 9 for r in rows)))
print('  highest rung e+1..e+6: mean %.2f, median %d; share >=9: %d/47; ==0: %d/47' % (st.mean(r['post_max'] for r in rows), st.median(r['post_max'] for r in rows), sum(r['post_max'] >= 9 for r in rows), sum(r['post_max'] == 0 for r in rows)))
print('  post_max >= pre_max (kept or improved):', sum(r['kept_or_up'] for r in rows), '/47')
print('  distribution of post_max:', sorted(collections.Counter(r['post_max'] for r in rows).items()))
print('  returned to rung>=8 after the term (y0>=e+7):', sum(r['later_rung8_after_term'] for r in rows), '/47')
print('  rung>=8 at any time after e (term or later):', sum(1 for r in rows if r['any_rung8_term'] or r['later_rung8_after_term']), '/47')
print('\n  by election:')
for e in sorted({r['election'] for r in rows}):
    rr = [r for r in rows if r['election'] == e]
    print(f"  {e}: n={len(rr)} ", collections.Counter(r['destination'] for r in rr), 'rung8_term', sum(r['any_rung8_term'] for r in rr))
print('\n  per loser (for hand check):')
for r in rows:
    print(f"  {r['election']} {r['name'][:24]:24s} {r['role'][:9]:9s} pre{r['pre_max']:2d} post{r['post_max']:2d} {r['destination']:14s} later8={r['later_rung8_after_term']} yrs={r['years_in_office_after']:2d}/{r['horizon_years']:2d} | {r['posts_term'][:110]}")
print('\n  unranked records held in the term (hand check: anything missed?):')
print('\n'.join('  ' + u for u in unranked_in_term))
print('\n  later rung>=8 posts (after the term):')
for r in rows:
    if r['later_rung8_posts']:
        print(f"  {r['election']} {r['name'][:24]:24s}: {r['later_rung8_posts'][:150]}")
print('\n  cabinet-level federal post again (rung 9, started after e):')
for r in rows:
    if r['cabinet_again']:
        print(f"  {r['election']} {r['name'][:24]:24s}: {r['cabinet_again'][:150]}")
print('\n  governor after e:')
for r in rows:
    if r['governor_after']:
        print(f"  {r['election']} {r['name'][:24]:24s}: {r['governor_after'][:150]}")
# candidacies for governor after e, from the unranked text too
pp = list(csv.DictReader(open(DATA + '/parsed_positions.csv')))
print('\n  governor candidacies in the text after e:')
for L in losers:
    for r in pp:
        if r['person_id'] and int(r['person_id']) == L['pid'] and re.search(r'candidate for governor|precandidate for governor|governor-elect', r['role_text'].lower()):
            ys = r['year_start']
            if ys and float(ys) > L['e']:
                print(f"  {L['e']} {L['corcholata_name'][:24]:24s}: {r['role_text'][:80]} ({ys})")

print('\n== TASK 2: repeat contenders (all crosswalk rows)')
per = collections.defaultdict(list)
for r in cm:
    if r['pid']:
        per[r['pid']].append(r)
for pid, rr in per.items():
    if len(rr) > 1:
        print('  ', rr[0]['corcholata_name'], ' | '.join(f"{r['e']} {r['role']}{' [main]' if r['main'] else ''}" for r in sorted(rr, key=lambda r: r['e'])))

print('\n== TASK 3: presidents after office (ranked records with y1 >= e+7)')
for e in sorted(winners):
    if e > 1988:
        continue
    pid = winners[e]; name = next(r['corcholata_name'] for r in cm if r['pid'] == pid and r['e'] == e)
    after = [r for r in byp.get(pid, []) if r['y1'] >= e + 7]
    yrs = annual_rank(pid, e + 7, min(death.get(pid, DATA_END), DATA_END))
    print(f"  {e} {name[:26]:26s} died {death.get(pid, '?')}  years with a ranked post after e+6: {len(yrs)} (max rung {max(yrs.values(), default=0)})")
    for r in after:
        print(f"       {r['role'][:70]} [{r['rule']} r{r['rung']}] ({r['y0']}-{r['y1']})")
    inoff = [r for r in byp.get(pid, []) if r['rule'] == 'president']
    print('       president records:', [(r['y0'], r['y1']) for r in inoff])

print('\n== TASK 3: back of the envelope')
alive6 = [r for r in rows if not r['death_year'] or int(r['death_year']) > r['election'] + 6]
def summ(rs, lab):
    n = len(rs)
    print(f"  {lab}: n={n}; horizon (years to death or 2009) mean {st.mean(r['horizon_years'] for r in rs):.1f}; "
          f"years in ranked office after e: mean {st.mean(r['years_in_office_after'] for r in rs):.1f}, median {st.median(r['years_in_office_after'] for r in rs):.0f}, "
          f"zero: {sum(r['years_in_office_after']==0 for r in rs)}; in e+1..e+6: mean {st.mean(r['years_in_office_e1_e6'] for r in rs):.1f}; "
          f"mean rung when in office {st.mean(r['mean_rung_after'] for r in rs if r['years_in_office_after']>0):.2f}; "
          f"pay after e (1927 scale) mean {st.mean(r['pay_after_1927scale_mn'] for r in rs):.1f}m, median {st.median(r['pay_after_1927scale_mn'] for r in rs):.1f}m; "
          f"(1999 scale) mean {st.mean(r['pay_after_1999scale_mn'] for r in rs):.1f}m; pay e+1..e+6 (1927 scale) mean {st.mean(r['pay_e1_e6_1927scale_mn'] for r in rs):.1f}m")
summ(rows, 'all 47')
summ(alive6, 'alive through e+6')
summ([r for r in rows if r['destination'] != 'none'], 'with a post in the term')
summ([r for r in rows if r['any_rung8_term']], 'kept rung>=8 in the term')
pres6 = 6 * 12 * p27[11]
print(f"  president: 6 years at rung 11, official pay 1927 scale {p27[11]/1000:.0f}k/month -> {pres6/1e6:.1f}m over the term; "
      f"cabinet 1927 scale {p27[9]/1000:.0f}k/month -> 6 years {6*12*p27[9]/1e6:.1f}m; 1999 scale cabinet {p99[9]/1000:.0f}k -> {6*12*p99[9]/1e6:.1f}m")
print(f"  president/cabinet pay ratio 1927: {p27[11]/p27[9]:.2f}")
# years the loser would need at his mean rung to match the president's six years of pay
mr = st.mean(r['mean_rung_after'] for r in rows if r['years_in_office_after'] > 0)
print(f"  loser mean rung when in office {mr:.2f}; years at rung 9 to match the president's 6-year pay (1927 scale): {pres6/(12*p27[9]):.1f}; at rung 7: {pres6/(12*p27[7]):.1f}")
ages = {}
for r in csv.DictReader(open(OUT + '/aspirants.csv')):
    if r['slate'] == 'main':
        ages[(int(r['election']), int(r['pid']))] = int(r['age'])
print(f"  losers' age at e: mean {st.mean(ages[(r['election'], r['pid'])] for r in rows):.1f}")

# ------------------------------------------------------------------ table and macros for the deck
os.makedirs(OUT + '/tables', exist_ok=True)
n = len(rows)
dest = collections.Counter(r['destination'] for r in rows)
broke = {}
for r in csv.DictReader(open(OUT + '/aspirants.csv')):
    if r['slate'] == 'main':
        broke[(int(r['election']), int(r['pid']))] = int(r['broke'])
none_broke = sum(1 for r in rows if r['destination'] == 'none' and broke.get((r['election'], r['pid']), 0) == 1)
grp = {'cabinet': dest['cabinet-level'], 'abroad': dest['abroad'],
       'other': sum(dest[c] for c in ['governor', 'party', 'congress', 'supreme court', 'labor', 'other federal']), 'none': dest['none']}
assert sum(grp.values()) == n
pre8 = sum(r['pre_max'] >= 8 for r in rows); term8 = sum(r['any_rung8_term'] for r in rows)
ever8 = sum(1 for r in rows if r['any_rung8_term'] or r['later_rung8_after_term'])
years = [r['years_in_office_after'] for r in rows]
mean_rung = st.mean(r['mean_rung_after'] for r in rows if r['years_in_office_after'] > 0)
cab_again = sum(1 for r in rows if r['cabinet_again']); gov_after = sum(1 for r in rows if r['governor_after'])
pres_cab_after = 0
for e in sorted(winners):
    if e > 1988: continue
    pid = winners[e]; yrs_p = annual_rank(pid, e + 7, min(death.get(pid, DATA_END), DATA_END))
    pres_cab_after += int(max(yrs_p.values(), default=0) >= 9)
loser_pay = st.mean(r['pay_after_1927scale_mn'] for r in rows); loser_pay_med = st.median(r['pay_after_1927scale_mn'] for r in rows)
pres_pay = pres6 / 1e6; ratio = pres_pay / loser_pay
main_ids = collections.Counter(r['pid'] for r in losers)
repeat = sum(1 for pid, c in main_ids.items() if c > 1)
repeat_won = sum(1 for pid in main_ids if main_ids[pid] > 1 and pid in {winners[e] for e in winners})
pct = lambda k: f"{100 * k / n:.0f}\\%"
lines = ["% loser_careers.tex (loser_careers.py). The 47 losing contenders of the main slates 1940-1988 in the new president's term. Do not edit by hand.",
  "\\begin{tabular}{lcc}", "\\toprule",
  f"The {n} losing contenders in the new president's term & Contenders & Share \\\\", "\\midrule",
  f"Cabinet-level post in Mexico & {grp['cabinet']} & {pct(grp['cabinet'])} \\\\",
  f"Embassy or international body & {grp['abroad']} & {pct(grp['abroad'])} \\\\",
  f"Governor, Congress, courts or party & {grp['other']} & {pct(grp['other'])} \\\\",
  f"No recorded post & {grp['none']} & {pct(grp['none'])} \\\\",
  f"\\quad of whom had left the party & {none_broke} & \\\\", "\\midrule",
  f"Cabinet-level rank (8 or above) before the succession & {pre8} & {pct(pre8)} \\\\",
  f"Cabinet-level rank during the term & {term8} & {pct(term8)} \\\\",
  f"Cabinet-level rank at any time after the succession & {ever8} & {pct(ever8)} \\\\",
  "\\bottomrule", "\\end{tabular}"]
open(OUT + '/tables/loser_careers.tex', 'w').write('\n'.join(lines) + '\n')
mac = lambda k, v: f"\\newcommand{{\\{k}}}{{{v}}}"
macros = ["% loser_macros.tex (loser_careers.py). Do not edit by hand.",
  mac('LCn', n), mac('LCcabinet', grp['cabinet']), mac('LCabroad', grp['abroad']), mac('LCother', grp['other']), mac('LCnone', grp['none']), mac('LCnoneLeft', none_broke),
  mac('LCpreTop', pre8), mac('LCtermTop', term8), mac('LCeverTop', ever8),
  mac('LCyears', f"{st.mean(years):.0f}"), mac('LCyearsMedian', f"{st.median(years):.0f}"), mac('LCnever', sum(y == 0 for y in years)),
  mac('LCmeanRung', f"{mean_rung:.1f}"), mac('LCcabAgain', cab_again), mac('LCgovAfter', gov_after), mac('LCpresCabAfter', pres_cab_after),
  mac('LCpresPay', f"{pres_pay:.0f}"), mac('LCloserPay', f"{loser_pay:.0f}"), mac('LCloserPayMedian', f"{loser_pay_med:.0f}"), mac('LCratio', f"{ratio:.1f}"),
  mac('LCrepeat', repeat), mac('LCrepeatWon', repeat_won)]
open(OUT + '/tables/loser_macros.tex', 'w').write('\n'.join(macros) + '\n')
print('\n'.join(lines)); print('\n'.join(macros))
