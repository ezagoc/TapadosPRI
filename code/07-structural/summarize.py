"""Best start, fit, preliminary sandwich standard errors, J and the AGS sensitivity (MODEL_SPEC.md section 8; preliminary
weighting of section 16.7). Usage: python code/07-structural/summarize.py --rule all"""
import argparse
import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import OUTPUT_DIR  # noqa: E402
import chairs_model as cm  # noqa: E402
import moments as mo  # noqa: E402
import objective as ob  # noqa: E402
import estimate_ii as ei  # noqa: E402
import weights as wt  # noqa: E402

ap = argparse.ArgumentParser(); ap.add_argument("--rule", default="all"); args = ap.parse_args()
out = OUTPUT_DIR / "structural" / args.rule
st = pd.concat([pd.read_csv(f) for f in glob.glob(str(out / "starts_[0-9]*.csv"))]).sort_values("value").reset_index(drop=True)
st.to_csv(out / "starts_all.csv", index=False)
best = st.iloc[0]; theta = best[[f"x_{p}" for p in cm.PARAMS]].to_numpy(float)
near = st[st.value <= best.value * 1.01]
print(f"{len(st)} starts; best criterion {best.value:.4f}; {len(near)} within 1% of it")
print("spread of the parameters across starts within 1%:")
print(near[[f"x_{p}" for p in cm.PARAMS]].agg(["min", "max"]).T.round(3).to_string())

cy, des, target, W, var, fam, idef = ei.setup(args.rule)
O = ob.Objective(cy, des, target, W, idef)
m, G = O.jacobian(theta)
names = mo.moment_names()
Wd = np.diag(W); Om = np.diag(var)
at_bound = np.array([np.isclose(theta[j], lo) or np.isclose(theta[j], hi) for j, (lo, hi) in enumerate(ei.BOUNDS)])
free = ~at_bound
Gf = G[:, free]
B = np.linalg.inv(Gf.T @ Wd @ Gf)
V = B @ Gf.T @ Wd @ Om @ Wd @ Gf @ B
se = np.full(len(theta), np.nan); se[free] = np.sqrt(np.diag(V))
AGS = np.full((len(theta), len(m)), np.nan); AGS[free] = -B @ Gf.T @ Wd
par = pd.DataFrame({"parameter": cm.PARAMS, "estimate": theta, "se_prelim": se, "at_bound": at_bound})
fit = pd.DataFrame({"moment": names, "family": [wt.family_of(n) for n in names], "data": target, "model": m,
                    "se_data": np.sqrt(var), "t_gap": (m - target) / np.sqrt(var)})
J = float((m - target) @ Wd @ (m - target))
sv = np.linalg.svd(Gf * np.sqrt(W)[:, None], compute_uv=False)
par.to_csv(out / "parameters.csv", index=False); fit.to_csv(out / "fit.csv", index=False)
pd.DataFrame(AGS.T, index=names, columns=cm.PARAMS).to_csv(out / "ags_sensitivity.csv")
print("\nParameters (preliminary standard errors: diagonal Omega, no joint bootstrap yet):")
print(par.round(3).to_string(index=False))
print(f"\nCriterion {J:.3f}; condition number of the weighted Jacobian {sv[0] / sv[-1]:.1f}")
print("\nFit (t_gap = (model - data) / se of the data moment):")
print(fit.round(3).to_string(index=False))
