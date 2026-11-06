"""Counterfactual succession rules within one cycle (MODEL_SPEC.md section 12). Network, pool, slates and calendar are held
as observed; each rule changes the chairs of observed holders, the seats, the handover reshuffle or the penalty, and the
model is re-solved (capacity prices included). Outputs average the nine cycles with equal weight.

Rules: baseline; maximato (the outgoing president carries omega_P in e+1..e+6); purges (no loser keeps a top chair after e,
his seat is added to the pool's capacities); reelection (the outgoing president keeps the presidency through e+6, every
other observed holder keeps his e-1 chair, no handover reshuffle at e+1, no penalty). The announced heir needs a pool
defined at e-6 and is not implemented yet.
"""
import numpy as np
import pandas as pd
import jax
import jax.numpy as jnp

import chairs_model as cm

CODE = {"R": 0, "P": 1, "X": 2, "XT": 3, "T": 4}


def roles(e):
    pres = pd.read_csv(cm.STRUCT / "presidents.csv")
    losers = pd.read_csv(cm.STRUCT / "losers.csv")
    L = losers[losers.election == e]
    return dict(outgoing=int(pres[pres.term_end == e].person_id.iloc[0]), designee=int(pres[pres.term_start == e].person_id.iloc[0]),
                losers=L.pid.to_numpy(), loser_rungs=L[[f"R_{'m' if k < 0 else 'p'}{abs(k)}" for k in range(-1, 9)]].to_numpy(),
                presidents=pres.person_id.to_numpy())


def scenario_arrays(c: cm.Cycle, d, rule):
    A = cm.cycle_arrays(c, d["main_idx"], d["iN"])
    if rule == "baseline":
        return A
    R = roles(c.e)
    cat = c.out_cat.copy(); M = c.M.copy()
    col = {j: k for k, j in enumerate(c.out_ids)}
    years = c.e - 1 + np.arange(cm.NT)
    if rule == "maximato":
        if R["outgoing"] in col:
            k = col[R["outgoing"]]; sel = (years >= c.e + 1) & (years <= c.e + 6) & np.isin(cat[k], [CODE["X"], CODE["XT"]])
            cat[k, sel] = CODE["P"]
    elif rule == "purges":
        for l, rung in zip(R["losers"], R["loser_rungs"]):
            if l in col:
                k = col[l]; cat[k, years >= c.e + 1] = np.where(cat[k, years >= c.e + 1] == CODE["T"], CODE["R"], cat[k, years >= c.e + 1])
            for tau in np.where(years >= c.e + 1)[0]:
                if rung[tau] in (8, 9):
                    M[tau, rung[tau] - 1] += 1
    elif rule == "reelection":
        for j, k in col.items():
            if j == R["outgoing"]:
                cat[k, years <= c.e + 6] = CODE["P"]
            elif j in R["presidents"] and j != R["designee"]:
                continue                                           # other ex-presidents and the next one: as observed
            else:
                cat[k, 1:] = cat[k, 0]                             # every other holder keeps his e-1 chair (no new cabinet)
        A["hand"] = A["hand"].at[2].set(0.0)                       # no handover at e+1
        A["pen"] = jnp.zeros(cm.NT)                                # no losers, no penalty
    else:
        raise ValueError(rule)
    for name, v in [("nP", "P"), ("nX", "X"), ("nXT", "XT"), ("nT", "T")]:
        A[name] = jnp.asarray(c.C_out @ (cat == CODE[v]))
    A["M"] = jnp.asarray(M)
    return A


def outcomes(theta, cycles, des, aux, rule):
    """Stakes, concentration, circulation, selection and the incumbent-camp gap under one rule."""
    out = {k: [] for k in ["stakes_term", "stakes_8", "conc_designee", "conc_incumbent", "circulation", "selection", "incumbent_gap"]}
    series = []
    for c, d in zip(cycles, des):
        A = scenario_arrays(c, d, rule); e = A.pop("e")
        r = jax.jit(lambda th, A=A, e=e: cm.simulate_cycle(th, {**A, "e": e}))(jnp.asarray(theta))
        EY = np.asarray(r["EY"]); q = np.asarray(r["q"]); qa = np.asarray(r["qa"])
        a = c.pool[["pid"]].merge(aux[aux.election == c.e], on="pid", how="left").fillna(0)
        aD, aP = a.a_D_es.values, a.a_P_es.values
        gap = [(aD - aP) @ (EY[:, k + 1] - c.Yobs[:, 6]) for k in range(1, 9)]
        series.append(dict(e=c.e, **{f"gap_k{k}": g for k, g in zip(range(1, 9), gap)}))
        out["stakes_term"].append(sum(gap[:6])); out["stakes_8"].append(sum(gap))
        R = roles(c.e)
        grp = c.pool.group.values
        tied_out = np.zeros(len(c.pid), bool)
        if R["outgoing"] in set(c.out_ids):
            tied_out = c.C_out[:, list(c.out_ids).index(R["outgoing"])] > 0
        inc = (grp == "N") & tied_out
        term = slice(2, 8)                                              # e+1..e+6
        out["conc_designee"].append((q[grp == "D"][:, term].sum(0) / q[:, term].sum(0)).mean())
        out["conc_incumbent"].append((q[inc][:, term].sum(0) / q[:, term].sum(0)).mean())
        camp = np.where(grp == "D", "D", np.where(grp == "P", "P" + c.pool.patron.fillna(0).astype(int).astype(str), np.where(inc, "X", "other")))
        top0 = (c.R0 >= 8).astype(float)
        sh0 = pd.Series(top0).groupby(camp).sum() / top0.sum(); sh4 = pd.Series(q[:, 5]).groupby(camp).sum() / q[:, 5].sum()
        out["circulation"].append(0.5 * (sh4 - sh0).abs().sum())
        out["selection"].append(qa[:, 5].sum() / q[:, 5].sum())
        w = a.w_win.values; ctrl = (grp == "N") & ~inc & (w > 0)
        sim_years = slice(0, 8)                                         # e-1..e+6
        d_inc = (EY[inc][:, sim_years] - c.Yobs[inc][:, [6]]).mean() if inc.any() else np.nan
        d_ctrl = ((EY[ctrl][:, sim_years] - c.Yobs[ctrl][:, [6]]).mean(1) * w[ctrl]).sum() / w[ctrl].sum()
        out["incumbent_gap"].append(d_inc - d_ctrl)
    summary = {k: float(np.nanmean(v)) if not k.startswith("stakes") else float(np.sum(v)) for k, v in out.items()}
    return summary, pd.DataFrame(series)
