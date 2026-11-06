"""Preliminary diagonal weighting matrix (MODEL_SPEC.md section 16, implementation note 7).

Variances: families 1 and 3 from the design's own intervals (Ferman-Pinto for the designee's followers, as published);
family 2 window averages from the mean of the yearly standard errors in the window (an upper bound when the years are
positively correlated); families 5-8 from a pairs bootstrap of unaligned politicians clustered across successions, with
the entropy-balancing weights held fixed. W_jj = 1 / (var_j * K_f), K_f the number of moments in family f, so that each
family carries equal expected weight. The joint bootstrap (joint_draws.R) replaces this for the final inference.
"""
import numpy as np
import pandas as pd
import jax.numpy as jnp

import chairs_model as cm
import moments as mo

FAMILIES = {"D_k": 1, "Pk_": 2, "Pl_": 2, "extensive": 3, "intensive": 3, "trans_": 5, "jump_": 6, "leave_": 7, "var_d1": 8, "corr_d1_d2": 8}


def family_of(name):
    return next(f for k, f in FAMILIES.items() if name.startswith(k))


def design_variances(rule, names):
    t = pd.read_csv(cm.STRUCT / f"targets_{rule}.csv")
    v = {}
    for k in range(1, 9):
        v[f"D_k{k}"] = t[(t.family == "D_es") & (t.k == k)].se.iloc[0] ** 2
    for g, fam in [("Pk", "Pk_es"), ("Pl", "Pl_es")]:
        for a, b in mo.WINDOWS:
            v[f"{g}_e{a}-{b}"] = t[(t.family == fam) & t.k.between(a, b)].se.mean() ** 2
    for m in ["extensive", "intensive"]:
        v[m] = t[t.family == m].se.iloc[0] ** 2
    return v


def bootstrap_unaligned(cycles, des, idef, B=500, seed=19102026):
    """Pairs bootstrap of families 5-8 over unaligned politicians (clustered across successions)."""
    names = mo.moment_names()
    obs = [mo.observed_results(c, d["main_idx"], d["iN"]) for c, d in zip(cycles, des)]
    full = np.asarray(mo.compute_moments(obs, des, idef))
    pids = np.unique(np.concatenate([c.pid[d["w"] > 0] for c, d in zip(cycles, des)]))
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(B):
        mult = pd.Series(rng.multinomial(len(pids), np.full(len(pids), 1 / len(pids))), index=pids)
        des_b = []
        for c, d in zip(cycles, des):
            m_ = pd.Series(c.pid).map(mult).fillna(0).values
            des_b.append({**d, "w": d["w"] * m_})
        draws.append(np.asarray(mo.compute_moments(obs, des_b, idef)))
    draws = np.array(draws)
    fam = np.array([family_of(n) for n in names])
    return {n: draws[:, j].var() for j, n in enumerate(names) if fam[j] >= 5}, full


def build_W(cycles, des, idef, rule, B=500):
    names = mo.moment_names()
    var = design_variances(rule, names)
    vb, _ = bootstrap_unaligned(cycles, des, idef, B)
    var.update(vb)
    v = np.array([var[n] for n in names])
    fam = np.array([family_of(n) for n in names])
    K = pd.Series(fam).map(pd.Series(fam).value_counts()).values
    return 1.0 / (v * K), v, fam
