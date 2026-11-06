"""Targeted moments of MODEL_SPEC.md section 8 (families 1-3 and 5-8; family 4 is not built yet), computed with the same
formulas from the model's forward distributions and from the observed data."""
import numpy as np
import pandas as pd
import jax.numpy as jnp

from chairs_model import STRUCT, ELECTIONS, NT

WINDOWS = [(1, 4), (5, 6), (7, 8)]
BANDS = ["low", "middle", "high"]
CATN = ["stay", "up", "down"]
AGEG = ["under45", "45to60", "over60"]


def moment_names():
    names = [f"D_k{k}" for k in range(1, 9)]
    names += [f"{g}_e{a}-{b}" for g in ["Pk", "Pl"] for a, b in WINDOWS]
    names += ["extensive", "intensive"]
    names += [f"trans_{bd}_{h}_{c}" for bd in BANDS for h in ["handover", "other"] for c in CATN]
    names += [f"jump_{bd}" for bd in BANDS] + [f"leave_{g}" for g in AGEG] + ["var_d1", "corr_d1_d2"]
    return names


def band_of(pre):
    return np.where(pre <= 4, 0, np.where(pre <= 7, 1, 2))


def load_design(cycles, rule="all"):
    aux = pd.read_csv(STRUCT / f"aux_{rule}.csv")
    X = pd.read_csv(STRUCT / f"aux_X_{rule}.csv")
    des = []
    for c in cycles:
        P = c.pool
        a = P[["pid"]].merge(aux[aux.election == c.e], on="pid", how="left").fillna(0)
        x = X[X.election == c.e]
        des.append(dict(a_D=jnp.asarray(a.a_D_es.values), a_Pk=jnp.asarray(a.a_Pk_es.values), a_Pl=jnp.asarray(a.a_Pl_es.values),
                        a_ext=jnp.asarray(a.a_ext.values), w=a.w_win.values, band=band_of(P.pre.values), age_e=P.age.values,
                        main_idx=P.reset_index().set_index("pid").loc[x.pid.values, "index"].values,
                        Xm=x.drop(columns=["election", "pid", "treated", "pre"]).values, treated=x.treated.values, pre=x.pre.values,
                        Y_m2=jnp.asarray(c.Yobs[:, 6], float), iN=np.where(a.w_win.values > 0)[0]))
    return des


def observed_results(c, im=None, iN=None):
    """The observed data in the simulator's output format (degenerate distributions); im, iN as in cycle_arrays."""
    Y = c.Yobs.astype(float)
    n = Y.shape[0]
    im = np.arange(n) if im is None else np.asarray(im); iN = np.arange(n) if iN is None else np.asarray(iN)
    Rprev, Rt = Y[:, 6:16], Y[:, 7:17]                       # t-1 and t for tau = 0..9
    cats = np.stack([Rt == Rprev, Rt > Rprev, (Rt >= 1) & (Rt < Rprev), (Rt == 0) & (Rprev >= 1),
                     np.abs(Rt - Rprev) * (Rt != Rprev), Rt != Rprev], -1).astype(float)
    post = Y[:, 9:13].max(1)
    d1 = Y[:, 12] - Y[:, 9]; R5, R8 = Y[:, 13], Y[:, 16]
    d1, R5, R8, post = d1[iN], R5[iN], R8[iN], post[im]
    return dict(EY=jnp.asarray(Rt), Ecat=jnp.asarray(cats), p_post=jnp.asarray((post > 0) * 1.0), E_post=jnp.asarray(post),
                E_d1=jnp.asarray(d1), E_d1sq=jnp.asarray(d1 ** 2), E_d1R8=jnp.asarray(d1 * R8), E_d1R5=jnp.asarray(d1 * R5),
                E_R8=jnp.asarray(R8), E_R5=jnp.asarray(R5), E_R8sq=jnp.asarray(R8 ** 2), E_R5sq=jnp.asarray(R5 ** 2),
                E_R8R5=jnp.asarray(R8 * R5))


def intensive_plugin(ps, ms, des, keep_cols=None, es_keep=None):
    """Plug-in of build_design(keep = post > 0) with the section-4 covariates: p = P(post > 0), m = E[post]."""
    X = np.vstack([d["Xm"] for d in des]); tr = np.concatenate([d["treated"] for d in des])
    el = np.concatenate([np.full(len(d["treated"]), i) for i, d in enumerate(des)]); pre = np.concatenate([d["pre"] for d in des])
    p = jnp.concatenate(ps); m = jnp.concatenate(ms)
    y_mass = m - pre * p                                      # E[(post - pre) 1(post > 0)]
    ctrl = tr == 0
    if es_keep is None:
        es_keep = [i for i in range(len(des)) if (np.asarray(p)[(el == i) & tr == 1].sum() > 0) and (np.asarray(p)[(el == i) & ctrl].sum() > 0)]
    sel = np.isin(el, es_keep)
    if keep_cols is None:
        keep_cols = np.abs(X[ctrl & sel] * np.asarray(p)[ctrl & sel][:, None]).sum(0) > 0
    Xk = jnp.asarray(X[:, keep_cols])
    n0 = jnp.stack([p[(el == i) & ctrl].sum() for i in range(len(des))])
    w0 = jnp.where(jnp.asarray(ctrl & sel), 1.0 / n0[el], 0.0)
    M = jnp.linalg.inv((Xk * (w0 * p)[:, None]).T @ Xk)
    om = 1.0 / len(es_keep)
    bvec = sum(om * (Xk * (p * (el == i) * (tr == 1))[:, None]).sum(0) / p[(el == i) & (tr == 1)].sum() for i in es_keep)
    beta = M @ (Xk.T @ (w0 * y_mass))
    est = sum(om * y_mass[(el == i) & (tr == 1)].sum() / p[(el == i) & (tr == 1)].sum() for i in es_keep) - bvec @ beta
    return est, keep_cols, es_keep


def compute_moments(results, des, intensive_def=None):
    """results, des: lists over cycles. Returns the moment vector (jnp) in moment_names() order."""
    v = []
    for k in range(1, 9):
        v.append(sum((d["a_D"] * (r["EY"][:, k + 1] - d["Y_m2"])).sum() for r, d in zip(results, des)))
    for g in ["a_Pk", "a_Pl"]:
        for a_, b_ in WINDOWS:
            v.append(sum(sum((d[g] * (r["EY"][:, k + 1] - d["Y_m2"])).sum() for r, d in zip(results, des)) for k in range(a_, b_ + 1)) / (b_ - a_ + 1))
    v.append(sum((d["a_ext"][d["main_idx"]] * (r["p_post"] - 1.0)).sum() for r, d in zip(results, des)))
    ps = [r["p_post"] for r in results]; ms = [r["E_post"] for r in results]
    kc, ek = (None, None) if intensive_def is None else intensive_def
    v.append(intensive_plugin(ps, ms, des, kc, ek)[0])
    w = np.concatenate([d["w"] for d in des]); band = np.concatenate([d["band"] for d in des])
    Ec = jnp.concatenate([r["Ecat"] for r in results])                       # (N, NT, 6)
    hand = np.zeros(NT, bool); hand[[2, 8]] = True
    for bi in range(3):
        wb = jnp.asarray(w * (band == bi))
        for h in [hand, ~hand]:
            for ci in range(3):
                v.append((wb[:, None] * Ec[:, h, ci]).sum() / (wb.sum() * h.sum()))
    for bi in range(3):
        wb = jnp.asarray(w * (band == bi))
        v.append((wb[:, None] * Ec[:, :, 4]).sum() / (wb[:, None] * Ec[:, :, 5]).sum())
    age = np.concatenate([d["age_e"] for d in des])[:, None] + (np.arange(NT) - 1)[None, :]
    for lo, hi in [(0, 45), (45, 60), (60, 200)]:
        wa = jnp.asarray(w[:, None] * ((age >= lo) & (age < hi)))
        v.append((wa * Ec[:, :, 3]).sum() / wa.sum())
    wj = jnp.asarray(np.concatenate([d["w"][d["iN"]] for d in des])); W = wj.sum()
    g = lambda key: jnp.concatenate([r[key] for r in results])
    m1 = (wj * g("E_d1")).sum() / W; m2 = (wj * (g("E_R8") - g("E_R5"))).sum() / W
    v1 = (wj * g("E_d1sq")).sum() / W - m1 ** 2
    v2 = (wj * (g("E_R8sq") - 2 * g("E_R8R5") + g("E_R5sq"))).sum() / W - m2 ** 2
    cov = (wj * (g("E_d1R8") - g("E_d1R5"))).sum() / W - m1 * m2
    v += [v1, cov / jnp.sqrt(v1 * v2)]
    return jnp.stack([jnp.asarray(x, float) for x in v])
