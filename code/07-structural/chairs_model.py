"""Chairs and Clocks: data, forward-equation simulator and moments (MODEL_SPEC.md v4, research/structural_2026-10-19/).

Block A of the model. Each succession cycle e is simulated for t = e-1..e+8 (tau = 0..9) from the observed state of e-2.
State of a politician: s = 0..8 holds rung s+1; s = 9..17 holds no post, last held rung s-8. Ability on Gauss-Hermite
nodes, a | R_{e-2} ~ N(gamma_R R_{e-2}/9, sigma_a^2). Seats clear each year through capacity prices (Lemma 1, Newton).
Pull uses ties frozen at e-2; observed chairs (presidents, ex-presidents, contenders, politicians outside the pool) enter
at t, simulated pool members at t-1 through their probability of a top chair (mean field).
"""
from dataclasses import dataclass
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import jax
import jax.numpy as jnp

jax.config.update("jax_enable_x64", True)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DATA_DIR  # noqa: E402

STRUCT = DATA_DIR / "structural"
ELECTIONS = list(range(1940, 1989, 6))
NS, NR, NT, NODES = 18, 10, 10, 15          # states, rung choices 0..9, years e-1..e+8, ability nodes
PARAMS = ["omega_P", "omega_X", "lambda_A", "b0", "b1", "theta_s", "theta_sH", "theta_9H", "theta_m", "theta_a",
          "sigma_a", "gamma_R"]

# ---------------------------------------------------------------- state algebra
R_OF_S = np.r_[np.arange(1, 10), np.zeros(9, int)]            # current rung
ELL_OF_S = np.r_[np.arange(1, 10), np.arange(1, 10)]          # current or last held rung
NEXT = np.zeros((NS, NR), int)
for s in range(NS):
    for r in range(NR):
        NEXT[s, r] = r - 1 if r >= 1 else 9 + ELL_OF_S[s] - 1
NEXT_1H = np.zeros((NS, NR, NS)); NEXT_1H[np.arange(NS)[:, None], np.arange(NR)[None, :], NEXT] = 1.0
R_CH = np.arange(NR)
STAY = ((R_CH[None, :] == R_OF_S[:, None]) & (R_OF_S[:, None] >= 1)).astype(float)
DIST = np.where((R_CH[None, :] >= 1) & (R_CH[None, :] != R_OF_S[:, None]), np.abs(R_CH[None, :] - ELL_OF_S[:, None]), 0).astype(float)
# transition categories (from current rung R(s), 0 when out, to chosen rung r)
I_STAY = (R_CH[None, :] == R_OF_S[:, None]).astype(float)
I_UP = (R_CH[None, :] > R_OF_S[:, None]).astype(float)
I_DOWN = ((R_CH[None, :] >= 1) & (R_CH[None, :] < R_OF_S[:, None])).astype(float)
I_LEAVE = ((R_CH[None, :] == 0) & (R_OF_S[:, None] >= 1)).astype(float)
ABSMOVE = (np.abs(R_CH[None, :] - R_OF_S[:, None]) * (R_CH[None, :] != R_OF_S[:, None])).astype(float)
I_MOVE = (R_CH[None, :] != R_OF_S[:, None]).astype(float)
TOP = (R_OF_S >= 8).astype(float)
GH_X, GH_W = np.polynomial.hermite_e.hermegauss(NODES); GH_W = GH_W / GH_W.sum()


def state_index(R, L):
    R = np.asarray(R); L = np.asarray(L)
    return np.where(R >= 1, R - 1, 9 + L - 1)


@dataclass
class Cycle:
    e: int
    pid: np.ndarray            # (n,)
    s0: np.ndarray             # (n,) state at e-2
    R0: np.ndarray             # (n,) rung at e-2
    age_e: np.ndarray          # (n,)
    death: np.ndarray          # (n,) death year or 9999
    fixed_from: np.ndarray     # (n,) first observed (not simulated) year or 9999
    C_in: np.ndarray           # (n, n) tie weights among pool members
    nP: np.ndarray             # (n, NT) tie weight to observed holders by chair category
    nX: np.ndarray
    nXT: np.ndarray
    nT: np.ndarray
    Lsum: np.ndarray           # (n,) tie weight to the cycle's losing contenders
    C_out: np.ndarray          # (n, J) tie weights to observed holders (for counterfactual chair rules)
    out_ids: np.ndarray        # (J,) their person ids
    out_cat: np.ndarray        # (J, NT) observed chair category: 0 R, 1 P, 2 X, 3 XT, 4 T
    out_rung: np.ndarray       # (J, NT) observed rung
    M: np.ndarray              # (NT, 9) seats by rung 1..9
    Yobs: np.ndarray           # (n, 17) observed rung, k = -8..8
    pool: pd.DataFrame


def load_cycles():
    pool = pd.read_csv(STRUCT / "pool.csv")
    ties = pd.read_csv(STRUCT / "ties.csv")
    chairs = pd.read_csv(STRUCT / "chairs.csv")
    caps = pd.read_csv(STRUCT / "capacities.csv")
    losers = pd.read_csv(STRUCT / "losers.csv")
    rcols = [f"R_{'m' if k < 0 else 'p'}{abs(k)}" for k in range(-8, 9)]
    out = []
    for e in ELECTIONS:
        P = pool[pool.election == e].reset_index(drop=True)
        n = len(P); idx = pd.Series(np.arange(n), index=P.pid.values)
        Y = P[rcols].to_numpy(int)
        pre_rungs = Y[:, :7]                                   # k = -8..-2
        last = np.array([row[row > 0][-1] if (row > 0).any() else 0 for row in pre_rungs])
        R0 = Y[:, 6]
        assert (last >= 1).all(), "every pool member held a post by e-2"
        T_ = ties[ties.election == e]
        inside = T_.j.isin(idx.index)
        C = np.zeros((n, n))
        ti = T_[inside]
        C[idx[ti.i].values, idx[ti.j].values] = ti.c.values
        np.fill_diagonal(C, 0.0)
        ch_e = chairs[chairs.election == e]
        J = np.unique(ch_e.j.values); jdx = pd.Series(np.arange(len(J)), index=J)
        code = {"P": 1, "X": 2, "XT": 3, "T": 4}
        out_cat = np.zeros((len(J), NT), int)
        out_cat[jdx[ch_e.j].values, (ch_e.t - (e - 1)).values] = ch_e.cat.map(code).values
        C_out = np.zeros((n, len(J)))
        to = T_[T_.j.isin(J)]
        C_out[idx[to.i].values, jdx[to.j].values] = to.c.values
        cats = {k: C_out @ (out_cat == v) for k, v in code.items()}
        rcols_t = [f"R_{'m' if k < 0 else 'p'}{abs(k)}" for k in range(-1, 9)]
        out_rung = np.zeros((len(J), NT), int)
        lz = losers[losers.election == e].pid
        Ls = T_[T_.j.isin(lz)].groupby("i").c.sum()
        Lsum = np.zeros(n); Lsum[idx[Ls.index].values] = Ls.values
        M = caps[caps.election == e].pivot(index="t", columns="r", values="M").loc[e - 1:e + 8, 1:9].to_numpy(float)
        out.append(Cycle(e=e, pid=P.pid.to_numpy(), s0=state_index(R0, last), R0=R0, age_e=P.age.to_numpy(float),
                         death=P.death_year.fillna(9999).to_numpy(int), fixed_from=P.obs_from.fillna(9999).to_numpy(int),
                         C_in=C, nP=cats["P"], nX=cats["X"], nXT=cats["XT"], nT=cats["T"], Lsum=Lsum, M=M, Yobs=Y, pool=P,
                         C_out=C_out, out_ids=J, out_cat=out_cat, out_rung=out_rung))
    return out


def unpack(theta):
    return dict(zip(PARAMS, theta))


def _demand(U, wts, p, avail):
    V = jnp.where(avail[None, :], U, -jnp.inf) - jnp.r_[0.0, p][None, :]
    P = jax.nn.softmax(V, axis=1)
    return P, (wts[:, None] * P).sum(0)[1:]


def _hessian(P, wts, avail):
    Pr = P[:, 1:]
    H = jnp.diag((wts[:, None] * Pr).sum(0)) - jnp.einsum("m,mr,mq->rq", wts, Pr, Pr)
    return jnp.where(avail[1:, None] & avail[None, 1:], H, jnp.eye(9))


def solve_prices(U, wts, M, avail, iters=30):
    """Capacity prices for rungs 1..9 (Lemma 1): Newton on the strictly convex dual, run without gradients; derivatives
    come from one differentiable Newton step at the solution, which equals the implicit-function derivative
    dp/dtheta = H^{-1} dD/dtheta because the clearing residual is zero there."""
    big = 50.0
    Mx = jnp.where(avail[1:], M, 1.0)
    Us, ws = jax.lax.stop_gradient(U), jax.lax.stop_gradient(wts)
    _, D0 = _demand(Us, ws, jnp.zeros(9), avail)
    p0 = jnp.where(avail[1:], jnp.log(jnp.maximum(D0, 1e-12) / Mx), big)
    def step(_, p):
        P, D = _demand(Us, ws, p, avail)
        dp = jnp.linalg.solve(_hessian(P, ws, avail), -(jnp.where(avail[1:], Mx - D, 0.0)))
        return jnp.where(avail[1:], p + jnp.clip(dp, -5, 5), big)
    p_star = jax.lax.stop_gradient(jax.lax.fori_loop(0, iters, step, p0))
    P_star, D_star = _demand(U, wts, p_star, avail)
    H = jax.lax.stop_gradient(_hessian(P_star, ws, avail))
    p = p_star - jnp.linalg.solve(H, jnp.where(avail[1:], Mx - D_star, 0.0))
    P, D = _demand(U, wts, p, avail)
    return p, P, D


# ---------------------------------------------------------------- forward equation for one cycle
def cycle_arrays(c: Cycle, idx_main=None, idx_N=None):
    """Static arrays of a cycle for the simulator. idx_main: rows that need the window maximum (the main design's
    followers); idx_N: rows that need the persistence moments (unaligned politicians with a balancing weight)."""
    n = len(c.pid)
    idx_main = np.arange(n) if idx_main is None else np.asarray(idx_main)
    idx_N = np.arange(n) if idx_N is None else np.asarray(idx_N)
    taus = np.arange(NT); years = c.e - 1 + taus
    sim = (years[None, :] < c.fixed_from[:, None]) & (years[None, :] <= c.death[:, None])
    r_obs = c.Yobs[:, 7:17]                                    # k = -1..8 -> tau 0..9
    return dict(s0=jnp.asarray(c.s0), R0=jnp.asarray(c.R0, float), age=jnp.asarray(c.age_e), sim=jnp.asarray(sim),
                r_obs=jnp.asarray(r_obs), C=jnp.asarray(c.C_in), nP=jnp.asarray(c.nP), nX=jnp.asarray(c.nX),
                nXT=jnp.asarray(c.nXT), nT=jnp.asarray(c.nT), Lsum=jnp.asarray(c.Lsum), M=jnp.asarray(c.M), e=c.e,
                im=jnp.asarray(idx_main), iN=jnp.asarray(idx_N),
                hand=jnp.asarray(np.isin(np.arange(NT), [2, 8]), float), pen=jnp.asarray((np.arange(NT) >= 2) & (np.arange(NT) <= 5), float))


N1H = jnp.asarray(NEXT_1H)
R_S = jnp.asarray(R_OF_S, float)
CATS = jnp.asarray(np.stack([I_STAY, I_UP, I_DOWN, I_LEAVE, ABSMOVE, I_MOVE], -1))   # (NS, NR, 6)
MAX1H = jnp.asarray((np.maximum(np.arange(NR)[:, None], np.arange(NR)[None, :])[..., None] == np.arange(NR)[None, None, :]).astype(float))
D1H = jnp.asarray(((R_OF_S[:, None] - np.arange(NR)[None, :] + 9)[..., None] == np.arange(19)[None, None, :]).astype(float))  # (s4, r1) -> d1+9
GW = jnp.asarray(GH_W)


def _step(theta, A, carry, tau):
    """One year of the forward equation (rematerialized in the backward pass, see simulate_cycle)."""
    p = unpack(theta)
    pi, q_prev, Win, Bj, Dj, Gj, Ed1R5, ER5sq = carry
    n = pi.shape[0]
    a = p["gamma_R"] * A["R0"][:, None] / 9.0 + p["sigma_a"] * jnp.asarray(GH_X)[None, :]
    b = jnp.r_[0.0, p["b0"] + p["b1"] * jnp.arange(1, 10)]
    t = A["e"] - 1 + tau
    sim = A["sim"][:, tau]
    pull = (p["omega_P"] * A["nP"][:, tau] + p["omega_X"] * A["nX"][:, tau] + jnp.maximum(p["omega_X"], 1.0) * A["nXT"][:, tau]
            + A["nT"][:, tau] + A["C"] @ (q_prev * sim))
    pen = p["lambda_A"] * A["Lsum"] * A["pen"][tau]
    hand = A["hand"][tau]
    th_s = p["theta_s"] - hand * (p["theta_sH"] * jnp.arange(NR) / 9.0 + p["theta_9H"] * (jnp.arange(NR) == 9))
    base = th_s[None, :] * STAY - p["theta_m"] * DIST
    age_t = A["age"] + (t - A["e"])
    U = (base[None, None, :, :]
         + (jnp.arange(NR) == 0)[None, None, None, :] * (p["theta_a"] * (age_t - 50.0) / 10.0)[:, None, None, None]
         + (jnp.arange(NR) / 10.0)[None, None, None, :] * a[:, :, None, None]
         + b[None, None, None, :] * (pull - pen)[:, None, None, None])
    avail = jnp.r_[True, A["M"][tau] > 0]
    wts = (pi * GW[None, :, None] * sim[:, None, None]).reshape(-1)
    prices, Pflat, D = solve_prices(U.reshape(-1, NR), wts, A["M"][tau], avail)
    P = Pflat.reshape(n, NODES, NS, NR)
    obs1h = jax.nn.one_hot(A["r_obs"][:, tau], NR)
    P = jnp.where(sim[:, None, None, None], P, obs1h[:, None, None, :])
    flow = pi[..., None] * P
    Ecat = jnp.einsum("insr,srk,n->ik", flow, CATS, GW)
    new_state = lambda F: jnp.einsum("insr,srt->int", F, N1H)
    im, iN = A["im"], A["iN"]
    if tau == 2:
        Win = jnp.einsum("insr,srt->intr", flow[im], N1H)                     # running max starts at r
        Bj = jnp.einsum("insr,srt->intr", flow[iN], N1H)                      # r1 = R_{e+1}
    elif 3 <= tau <= 5:
        WP = jnp.einsum("insm,insr->insmr", Win, P[im])
        Win = jnp.einsum("intmr,mrz->intz", jnp.einsum("insmr,srt->intmr", WP, N1H), MAX1H)
        Bj = jnp.einsum("insmr,srt->intm", jnp.einsum("insm,insr->insmr", Bj, P[iN]), N1H)
    if tau == 5:
        Dj = jnp.einsum("insm,smd->insd", Bj, D1H)
    elif tau >= 6:
        Dj = jnp.einsum("insdr,srt->intd", jnp.einsum("insd,insr->insdr", Dj, P[iN]), N1H)
    if tau == 6:
        Gj = jnp.einsum("insr,srt->intr", flow[iN], N1H)
        Ed1R5 = jnp.einsum("insd,s,d,n->i", Dj, R_S, jnp.arange(19) - 9.0, GW)
        ER5sq = jnp.einsum("insr,srt,t,n->i", flow[iN], N1H, R_S ** 2, GW)
    elif tau >= 7:
        Gj = jnp.einsum("insmr,srt->intm", jnp.einsum("insm,insr->insmr", Gj, P[iN]), N1H)
    pi = new_state(flow)
    EY = jnp.einsum("ins,s,n->i", pi, R_S, GW)
    q_prev = jnp.einsum("ins,s,n->i", pi, jnp.asarray(TOP), GW)
    qa = jnp.einsum("ins,s,n,in->i", pi, jnp.asarray(TOP), GW, a)                     # ability mass in top chairs
    clear = D - jnp.where(avail[1:], A["M"][tau], 0.0)
    return (pi, q_prev, Win, Bj, Dj, Gj, Ed1R5, ER5sq), (EY, Ecat, prices, clear, q_prev, qa)


def simulate_cycle(theta, A):
    n = A["s0"].shape[0]; nm = A["im"].shape[0]; nN = A["iN"].shape[0]
    pi = jnp.zeros((n, NODES, NS)).at[jnp.arange(n), :, A["s0"]].set(1.0)
    z = lambda k, *sh: jnp.zeros((k, NODES) + sh)
    carry = (pi, (A["R0"] >= 8).astype(float), z(nm, NS, NR), z(nN, NS, NR), z(nN, NS, 19), z(nN, NS, NR), jnp.zeros(nN), jnp.zeros(nN))
    outs = []
    for tau in range(NT):
        step = jax.checkpoint(lambda th, c, tau=tau: _step(th, A, c, tau))
        carry, o = step(theta, carry)
        outs.append(o)
    pi, _, Win, _, Dj, Gj, Ed1R5, ER5sq = carry
    EY = jnp.stack([o[0] for o in outs], 1)
    win_m = jnp.einsum("insm,n->im", Win, GW)
    d1v = jnp.arange(19) - 9.0
    return dict(EY=EY, Ecat=jnp.stack([o[1] for o in outs], 1), prices=jnp.stack([o[2] for o in outs]),
                q=jnp.stack([o[4] for o in outs], 1), qa=jnp.stack([o[5] for o in outs], 1),
                clear=jnp.stack([o[3] for o in outs]), p_post=1.0 - win_m[:, 0], E_post=win_m @ jnp.arange(NR, dtype=float),
                E_d1=jnp.einsum("insd,d,n->i", Dj, d1v, GW), E_d1sq=jnp.einsum("insd,d,n->i", Dj, d1v ** 2, GW),
                E_d1R8=jnp.einsum("insd,s,d,n->i", Dj, R_S, d1v, GW), E_d1R5=Ed1R5, E_R8=EY[A["iN"], 9], E_R5=EY[A["iN"], 6],
                E_R8sq=jnp.einsum("ins,s,n->i", pi[A["iN"]], R_S ** 2, GW), E_R5sq=ER5sq,
                E_R8R5=jnp.einsum("insm,s,m,n->i", Gj, R_S, jnp.arange(NR, dtype=float), GW))
