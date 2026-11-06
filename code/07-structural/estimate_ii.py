"""Indirect inference, Block A, design-only moments (MODEL_SPEC.md sections 8 and 16).

Usage: python code/07-structural/estimate_ii.py --rule all --starts 0-4 --maxiter 300
Writes OUTPUT_DIR/structural/<rule>/starts_<a>-<b>.csv (one row per start). summarize.py picks the best.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import qmc

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import OUTPUT_DIR  # noqa: E402
import chairs_model as cm  # noqa: E402
import moments as mo  # noqa: E402
import objective as ob  # noqa: E402
import weights as wt  # noqa: E402

BOUNDS = [(0, 10), (0, 10), (-3, 5), (0, 5), (0, 1), (-2, 8), (0, 6), (0, 6), (0, 3), (-3, 3), (0.01, 5), (-5, 10)]
HAND = np.array([1.6, 0.5, 0.0, 0.3, 0.05, 2.0, 1.0, 1.0, 0.3, 0.3, 1.0, 2.0])


def setup(rule):
    cy = cm.load_cycles(); des = mo.load_design(cy, rule)
    obs = [mo.observed_results(c, d["main_idx"], d["iN"]) for c, d in zip(cy, des)]
    ps = [r["p_post"] for r in obs]; ms = [r["E_post"] for r in obs]
    _, kc, ek = mo.intensive_plugin(ps, ms, des)
    target = np.asarray(mo.compute_moments(obs, des, (kc, ek)))
    W, var, fam = wt.build_W(cy, des, (kc, ek), rule, B=500)
    return cy, des, target, W, var, fam, (kc, ek)


def starts(n, seed=19102026):
    lo = np.array([b[0] for b in BOUNDS]); hi = np.array([b[1] for b in BOUNDS])
    sob = qmc.Sobol(d=len(BOUNDS), seed=seed).random(32)[: n - 1]
    return np.vstack([HAND, lo + sob * (hi - lo)])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rule", default="all"); ap.add_argument("--starts", default="0-0"); ap.add_argument("--maxiter", type=int, default=300)
    args = ap.parse_args()
    a, b = map(int, args.starts.split("-"))
    out = OUTPUT_DIR / "structural" / args.rule; out.mkdir(parents=True, exist_ok=True)
    cy, des, target, W, var, fam, idef = setup(args.rule)
    np.save(out / "W_diag.npy", W); np.save(out / "var_diag.npy", var); np.save(out / "target.npy", target)
    O = ob.Objective(cy, des, target, W, idef)
    S = starts(20)
    rows = []
    for k in range(a, b + 1):
        t0 = time.time(); hist = []
        def fg(x):
            v, g = O.value_and_grad(x); hist.append(v); return v, g
        r = minimize(fg, S[k], jac=True, method="L-BFGS-B", bounds=BOUNDS, options=dict(maxiter=args.maxiter, maxfun=2 * args.maxiter))
        rows.append(dict(start=k, value=r.fun, success=r.success, message=str(r.message), nit=r.nit, nfev=r.nfev,
                         minutes=(time.time() - t0) / 60, **{f"x_{p}": v for p, v in zip(cm.PARAMS, r.x)},
                         **{f"s_{p}": v for p, v in zip(cm.PARAMS, S[k])}))
        pd.DataFrame(rows).to_csv(out / f"starts_{a}-{b}.csv", index=False)
        print(f"start {k}: value {r.fun:.4f} after {r.nit} iterations, {rows[-1]['minutes']:.1f} min; {r.message}", flush=True)
