"""Stochastic simulator with exact capacities and realized chairs (MODEL_SPEC.md section 8: the check on the mean field and
the data of the recovery experiment). Each year, Gumbel shocks are drawn and seats are assigned by maximizing total utility
subject to the observed number of seats at each rung (a transportation problem solved as an assignment over expanded seats);
in the large-market limit its choice probabilities are the capacity-constrained logit of the forward equation."""
import numpy as np
from scipy.optimize import linear_sum_assignment

import chairs_model as cm


def simulate_paths(theta, c: cm.Cycle, rng):
    p = cm.unpack(np.asarray(theta, float))
    n = len(c.pid)
    a = p["gamma_R"] * c.R0 / 9.0 + p["sigma_a"] * rng.standard_normal(n)
    b = np.r_[0.0, p["b0"] + p["b1"] * np.arange(1, 10)]
    Y = c.Yobs.copy()
    R_prev = c.R0.copy(); L_prev = cm.ELL_OF_S[c.s0].copy()
    years = c.e - 1 + np.arange(cm.NT)
    sim_all = (years[None, :] < c.fixed_from[:, None]) & (years[None, :] <= c.death[:, None])
    top_prev = (R_prev >= 8).astype(float)
    for tau in range(cm.NT):
        t = c.e - 1 + tau
        sim = sim_all[:, tau]
        pull = (p["omega_P"] * c.nP[:, tau] + p["omega_X"] * c.nX[:, tau] + max(p["omega_X"], 1.0) * c.nXT[:, tau]
                + c.nT[:, tau] + c.C_in @ (top_prev * sim))
        pen = p["lambda_A"] * c.Lsum * (1.0 if 2 <= tau <= 5 else 0.0)
        hand = 1.0 if tau in (2, 8) else 0.0
        r = np.arange(cm.NR)
        th_s = p["theta_s"] - hand * (p["theta_sH"] * r / 9.0 + p["theta_9H"] * (r == 9))
        ell = np.where(R_prev >= 1, R_prev, L_prev)
        stay = (r[None, :] == R_prev[:, None]) & (R_prev[:, None] >= 1)
        dist = np.where((r[None, :] >= 1) & (r[None, :] != R_prev[:, None]), np.abs(r[None, :] - ell[:, None]), 0)
        age_t = c.age_e + (t - c.e)
        U = (th_s[None, :] * stay - p["theta_m"] * dist + (r[None, :] == 0) * (p["theta_a"] * (age_t - 50) / 10)[:, None]
             + (r[None, :] / 10.0) * a[:, None] + b[None, :] * (pull - pen)[:, None])
        idx = np.where(sim)[0]
        M = c.M[tau].astype(int)
        slots = np.r_[np.repeat(np.arange(1, 10), M), np.zeros(len(idx) - M.sum(), int)]
        assert len(idx) >= M.sum(), "more seats than simulated politicians"
        eps = rng.gumbel(size=(len(idx), cm.NR))
        V = U[idx] + eps
        rows, cols = linear_sum_assignment(-V[:, slots])
        R_new = R_prev.copy()
        R_new[idx[rows]] = slots[cols]
        R_new[~sim] = c.Yobs[~sim, tau + 7]
        L_prev = np.where(R_new >= 1, R_new, ell)
        R_prev = R_new
        Y[:, tau + 7] = R_new
        top_prev = (R_new >= 8).astype(float)
    return Y


def simulated_results(theta, cycles, des, rng):
    """One simulated dataset in the observed-results format of moments.py."""
    import moments as mo
    out = []
    for c, d in zip(cycles, des):
        Yc = simulate_paths(theta, c, rng)
        cc = cm.Cycle(**{**c.__dict__, "Yobs": Yc})
        out.append(mo.observed_results(cc, d["main_idx"], d["iN"]))
    return out
