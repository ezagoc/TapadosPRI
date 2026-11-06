"""Indirect-inference objective with analytic gradients (MODEL_SPEC.md section 8)."""
import numpy as np
import jax
import jax.numpy as jnp

import chairs_model as cm
import moments as mo


class Objective:
    def __init__(self, cycles, des, target, W, intensive_def):
        self.des, self.target, self.W, self.idef = des, jnp.asarray(target), jnp.asarray(W), intensive_def
        # One compiled forward and one compiled forward-plus-pullback per cycle. The gradient pulls back one cycle at a
        # time, so only one cycle's intermediate arrays are alive at once (memory: 31 GB per process before, see README).
        self.fns, self.pullbacks = [], []
        for c, d in zip(cycles, des):
            A = cm.cycle_arrays(c, d["main_idx"], d["iN"]); e = A.pop("e")
            f = lambda th, A=A, e=e: cm.simulate_cycle(th, {**A, "e": e})
            self.fns.append(jax.jit(f))
            self.pullbacks.append(jax.jit(lambda th, ct, f=f: jax.vjp(f, th)[1](ct)[0]))
        self._mom = lambda res: mo.compute_moments(res, des, intensive_def)
        self._crit = lambda res: self._q(self._mom(res))

    def _q(self, m):
        d = m - self.target
        return d @ (self.W * d) if self.W.ndim == 1 else d @ self.W @ d

    def moments(self, theta):
        return np.asarray(self._mom([f(jnp.asarray(theta)) for f in self.fns]))

    def value_and_grad(self, theta):
        th = jnp.asarray(theta)
        res = [f(th) for f in self.fns]
        val, ct = jax.value_and_grad(self._crit)(res)
        g = np.zeros(th.shape[0])
        for pb, c in zip(self.pullbacks, ct):
            g += np.asarray(pb(th, c))
        return float(val), g

    def jacobian(self, theta):
        """Jacobian of the moments by forward-mode differentiation, one cycle at a time."""
        th = jnp.asarray(theta)
        res = [f(th) for f in self.fns]
        m, vjp_m = jax.vjp(self._mom, res)
        # d moments / d results (one row per moment), then chain with each cycle's forward-mode Jacobian of the results
        cts = [vjp_m(jnp.zeros_like(m).at[j].set(1.0))[0] for j in range(m.shape[0])]
        G = np.zeros((m.shape[0], th.shape[0]))
        for ci, f in enumerate(self.fns):
            Jc = jax.jacfwd(f)(th)
            for j in range(m.shape[0]):
                G[j] += np.asarray(sum(jnp.tensordot(cts[j][ci][k], Jc[k], axes=cts[j][ci][k].ndim) for k in Jc))
            del Jc
        return np.asarray(m), G
