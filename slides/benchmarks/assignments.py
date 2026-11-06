"""Four one-term conditional benchmarks; each succession starts from observed careers."""
import os
from pathlib import Path
import numpy as np
import pandas as pd
# Data and results live under TAPADOS_BENCH_DIR (default TapadosPRI/output/slides/benchmarks), as in prepare.R.
HERE = Path(os.environ.get("TAPADOS_BENCH_DIR", Path(os.environ.get("TAPADOSPRI_DB_ROOT", Path.home() / "Dropbox" / "TapadosPRI")) / "output" / "slides" / "benchmarks"))
OUT = HERE / "data" / "calendar"
BASE = HERE / "data" / "design"
DATA = HERE / "data"
KS = np.arange(-7, 7)
ELECTIONS = np.arange(1940, 1989, 6)
CONTRASTS = ("DP", "DN", "PN")
SCOPES = ("all_observed", "federal_only", "top_only")
RULES = ("purge", "promotions_only", "sharing", "career")

def quota(n, shares, remaining, offset, permutation):
    """Capped proportional quotas; floor/ceiling systematic rounding.

    Shares are pre-designation camp population shares. Every rung's quotas sum
    to its observed capacity. No camp receives more seats than available people.
    The final specification fixes offsets at 0.5 and camp order alphabetically.
    """
    target = np.zeros(len(shares))
    free = remaining > 0
    left = float(n)
    while left > 1e-9:
        assert free.any()
        proposed = left * shares[free] / shares[free].sum()
        hit = proposed > remaining[free] + 1e-10
        if not hit.any():
            target[free] = proposed
            break
        capped = np.flatnonzero(free)[hit]
        target[capped] = remaining[capped]
        left -= remaining[capped].sum()
        free[capped] = False
    base = np.floor(target + 1e-10).astype(int)
    frac = np.maximum(target - base, 0)
    cum = np.cumsum(frac[permutation])
    increments = np.diff(np.floor(np.r_[0, cum] + offset)).astype(int)
    base[permutation] += increments
    assert base.sum() == n and (base <= remaining).all() and (base >= 0).all()
    return base

def allocate(rule, slots, cohort, priority, rng_offsets, permutation, alive, reserved, camp_shares=None):
    """Return one annual highest rank per person, respecting observed capacities."""
    n = len(cohort)
    y = np.zeros(n, dtype=np.int8)
    # Never reassign the presidency, including next December's president at e+6.
    y[slots == 11] = 11
    seats = np.sort(slots[(slots > 0) & (slots < 11)])[::-1]
    eligible = alive & ~reserved
    if rule == "purge":
        eligible &= cohort["group"].to_numpy() != "P"
    if eligible.sum() < len(seats):
        raise ValueError("Not enough available politicians: a closed-pool benchmark is infeasible.")
    if rule in ("purge", "career"):
        order = priority[eligible[priority]]
        if rule == "purge":
            # All winner followers first, then the unaligned. Within each block,
            # the SAME predetermined experience/credential order as other rules.
            is_d = cohort["group"].to_numpy()[order] == "D"
            order = np.r_[order[is_d], order[~is_d]]
        y[order[:len(seats)]] = seats
    else:
        camps = cohort["camp_code"].to_numpy()
        ng = camps.max() + 1
        shares = np.bincount(camps, minlength=ng) / n if camp_shares is None else camp_shares
        queues = [priority[(camps[priority] == g) & eligible[priority]] for g in range(ng)]
        remaining = np.array([len(q) for q in queues])
        cursor = np.zeros(ng, dtype=int)
        for r in range(10, 0, -1):
            nr = int(np.count_nonzero(slots == r))
            if not nr:
                continue
            q = quota(nr, shares, remaining, rng_offsets[r], permutation)
            for g in range(ng):
                y[queues[g][cursor[g]:cursor[g] + q[g]]] = r
            cursor += q
            remaining -= q
    assert np.array_equal(np.bincount(y, minlength=12), np.bincount(slots, minlength=12))
    assert (y[~alive] == 0).all()
    if rule == "purge":
        assert (y[cohort["group"].to_numpy() == "P"] == 0).all()
        # No neutral can outrank an available winner follower.
        dw = y[(cohort["group"].to_numpy() == "D") & alive & ~reserved]
        nn = y[(cohort["group"].to_numpy() == "N") & ~reserved]
        assert dw.min() >= nn.max()
    return y

def inputs():
    people = pd.read_csv(OUT / "people.csv")
    members = pd.read_csv(OUT / "memberships.csv")
    tables = {}
    for kind in ("all", "fed", "other", "top", "below_top"):
        tab = pd.read_csv(OUT / f"calendar_{kind}.csv")
        assert tab.pid.equals(people.pid)
        tables[kind] = tab.iloc[:, 1:].to_numpy(dtype=np.int8)
    years = np.array(tab.columns[1:], dtype=int)
    pool = pd.read_csv(BASE / "pool.csv")
    weights = pd.read_csv(BASE / "weights.csv")
    assert pool[["election", "pid"]].equals(weights[["election", "pid"]])
    person = pd.Index(people.pid).get_indexer(pool.pid)
    assert (person >= 0).all()
    assert np.array_equal(np.maximum(tables["fed"], tables["other"]), tables["all"])
    assert np.array_equal(np.maximum(tables["top"], tables["below_top"]), tables["all"])
    return people, members, tables, years, pool, person, weights


def single_term_path(rule, scope, election, people, context, tables, years):
    # Each experiment gets a fresh copy of its OBSERVED history.
    ix = election + KS - years[0]
    path = tables["all"][:, ix].copy()
    slot_key = {"all_observed": "all", "federal_only": "fed", "top_only": "top"}[scope]
    residual = {"federal_only": "other", "top_only": "below_top"}.get(scope)
    c = context.copy()
    winner = c.winner_tie.to_numpy(bool) | (people.pid.to_numpy() == c.winner.iloc[0])
    loser = c.loser_tie.to_numpy(bool) & ~winner
    c["group"] = np.where(winner, "D", np.where(loser, "P", "N"))
    c["camp_code"] = pd.factorize(c.camp, sort=True)[0]
    camps = c.camp_code.to_numpy()
    hist = tables["all"][:, (years >= election-5) & (years <= election-2)]
    prior = hist.max(axis=1)
    experience = (hist > 0).sum(axis=1)
    tie = people.pid.to_numpy()
    priority = np.lexsort((tie, -c.credential.to_numpy(), -experience, -prior))
    offsets = np.full(12, .5)
    permutation = np.arange(camps.max()+1)
    audits = []
    for k in range(1, 7):
        year = election + k
        j = int(year - years[0])
        base = tables[slot_key][:, j]
        available = ((people.birth_year.to_numpy() <= year-25) &
                     (people.entry_year.to_numpy() <= year) &
                     (people.death_year.fillna(9999).to_numpy() >= year))
        reserved = tables["all"][:, j] == 11
        if rule == "promotions_only":
            # This is a within-term perturbation of observed annual careers,
            # not a recursive law for careers in later presidencies.
            y = base.copy()
            movable = available & ~loser & ~reserved & (base > 0)
            def order(indices):
                return indices[np.lexsort((tie[indices], -c.credential.to_numpy()[indices],
                    -experience[indices], -prior[indices], -base[indices]))]
            dw = order(np.flatnonzero(movable & winner))
            nn = order(np.flatnonzero(movable & ~winner))
            slots = np.sort(base[movable])[::-1]
            y[dw] = slots[:len(dw)]
            y[nn] = slots[len(dw):]
            assert np.array_equal(y[loser], base[loser])
            assert np.array_equal(y > 0, base > 0)
            assert (y[winner] >= base[winner]).all()
            assert (y[~winner] <= base[~winner]).all()
        else:
            shares = np.bincount(camps[available & ~reserved], minlength=camps.max()+1)
            shares = shares / shares.sum()
            allocator_c = c
            if (reserved & loser).any():
                allocator_c = c.copy()
                allocator_c.loc[reserved, "group"] = "D"
            y = allocate(rule, base, allocator_c, priority, offsets, permutation,
                         available, reserved, camp_shares=shares)
            if rule == "purge":
                assert (y[loser & ~reserved] == 0).all()
        assert np.array_equal(np.bincount(y, minlength=12), np.bincount(base, minlength=12))
        if residual:
            y = np.maximum(y, tables[residual][:, j])
        if rule == "promotions_only":
            assert np.array_equal(y[loser], tables["all"][loser, j])
            assert np.array_equal(y > 0, tables["all"][:, j] > 0)
        path[:, np.flatnonzero(KS == k)[0]] = y
        audits.append(dict(scope=scope, rule=rule, election=int(election), year=year,
            rank_counts_preserved=True,
            losers_changed=int((y[loser] != tables["all"][loser, j]).sum()),
            winner_hires=int(((y > 0) & (tables["all"][:, j] == 0) & winner).sum()),
            unaligned_exits=int(((y == 0) & (tables["all"][:, j] > 0) & ~winner & ~loser).sum())))
    assert np.array_equal(path[:, KS <= 0], tables["all"][:, ix[KS <= 0]])
    return path, audits


def main():
    people, members, tables, years, pool, person, weights = inputs()
    events, paths, audits = [], [], []
    for scope in SCOPES:
        for rule in RULES:
            outcome = np.zeros((len(pool), len(KS)))
            for election in ELECTIONS:
                c = members.query("election == @election").reset_index(drop=True)
                assert c.pid.equals(people.pid)
                path, audit = single_term_path(rule, scope, election, people, c, tables, years)
                row = pool.election.to_numpy() == election
                outcome[row] = path[person[row]]
                paths.append(pd.DataFrame(dict(scope=scope, rule=rule, election=int(election),
                    pid=np.repeat(people.pid, len(KS)), k=np.tile(KS, len(people)), rank=path.ravel())))
                audits.extend(audit)
            change = outcome - outcome[:, np.flatnonzero(KS == -2)[0]][:, None]
            for contrast in CONTRASTS:
                values = weights[f"{contrast}_event"].to_numpy() @ change
                for j, k in enumerate(KS):
                    events.append(dict(scope=scope, rule=rule, contrast=contrast,
                        k=int(k), n_successions=9, estimate=values[j]))
    pd.DataFrame(events).to_csv(DATA / "assignment_estimates.csv", index=False)
    pd.concat(paths, ignore_index=True).to_csv(DATA / "paths.csv.gz", index=False)
    pd.DataFrame(audits).to_csv(DATA / "allocation_checks.csv", index=False)
    print(pd.DataFrame(events).query("scope == 'all_observed' and 1 <= k <= 4")
          .groupby(["rule", "contrast"]).estimate.mean().round(3).to_string())


if __name__ == "__main__":
    main()
