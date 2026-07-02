#!/usr/bin/env python3
"""
analyze_spinodal.py
===================
Analysis of an AutoMOOSE Fe--Cr spinodal-decomposition (Cahn--Hilliard) run.

Reads the MOOSE Exodus output directly (Exodus is netCDF under the hood) and
produces the validation figure used in the manuscript, plus the Skeptic
invariant scalars (S1 mass conservation, S2 free-energy dissipation, S3
phase separation / coarsening).

Outputs
-------
  fig_fecr_spinodal.png   2-row figure:
                            row 1: composition field c(x,y) snapshots over time
                            row 2: m(t) mass drift, F(t) free energy,
                                   c_max/c_min(t) tie-line separation
  fig_fecr_coarsening.png  (optional) characteristic length L(t) ~ t^(1/3)
  spinodal_invariants.json  the S1--S3 scalar summary (the numbers cited in the paper)

Usage
-----
  python analyze_spinodal.py path/to/run.e
  python analyze_spinodal.py path/to/run.e --csv path/to/run.csv --coarsening
  python analyze_spinodal.py path/to/run.e --var c --outdir figures/

Requirements
------------
  numpy, matplotlib            (required)
  netCDF4  (preferred)  OR  meshio   (Exodus reader; one of the two)
  scipy                        (optional; only for the structure-factor L(t))

Notes
-----
- The Cahn--Hilliard order parameter is the conserved composition c (Cr mole
  fraction). The script auto-detects the nodal variable named 'c' (override
  with --var).
- The free energy is read from a CSV postprocessor column if available
  (--csv), since 'total_free_energy' is typically a postprocessor, not a nodal
  field. If no CSV is given the script integrates f_loc from the field using
  the CALPHAD expression below (approximate; the postprocessor value is
  preferred for the paper).
- Equilibrium tie-line targets for Fe--Cr at 500 C: 23.6 / 82.3 mol% Cr.
"""

import argparse
import json
import os
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# ----------------------------------------------------------------------
# CALPHAD Fe--Cr local free energy (matches the MOOSE [Materials] block)
# f_loc = eV_J * d * ( A c + B(1-c) + C c ln c + D(1-c)ln(1-c)
#                      + E c(1-c) + F c(1-c)(2c-1) + G c(1-c)(2c-1)^2 )
# ----------------------------------------------------------------------
CALPHAD = dict(
    A=-2.446831e4, B=-2.827533e4, C=4.167994e3, D=7.052907e3,
    E=1.208993e4, F=2.568625e3, G=-2.354293e3,
    eV_J=6.24150934e18, d=1e-27,
)
C_EQ_HI, C_EQ_LO = 0.823, 0.236   # Cr-rich / Fe-rich equilibrium (mol fraction)
S1_TOL = 1e-5                      # Skeptic S1 mass-conservation tolerance


def f_loc(c):
    """CALPHAD local free-energy density (per the MOOSE materials block)."""
    p = CALPHAD
    c = np.clip(c, 1e-12, 1 - 1e-12)   # guard the logs
    bulk = (p["A"] * c + p["B"] * (1 - c)
            + p["C"] * c * np.log(c) + p["D"] * (1 - c) * np.log(1 - c)
            + p["E"] * c * (1 - c)
            + p["F"] * c * (1 - c) * (2 * c - 1)
            + p["G"] * c * (1 - c) * (2 * c - 1) ** 2)
    return p["eV_J"] * p["d"] * bulk


# ----------------------------------------------------------------------
# Exodus reading (netCDF4 preferred, meshio fallback)
# ----------------------------------------------------------------------
def read_exodus_netcdf(path, varname="c"):
    """Return (times, coords(x,y), C[ntime, nnode]) using netCDF4."""
    from netCDF4 import Dataset
    ds = Dataset(path, "r")

    # node coordinates
    if "coordx" in ds.variables:
        x = np.array(ds.variables["coordx"][:])
        y = np.array(ds.variables["coordy"][:])
    else:  # older exodus: 'coord' is (ndim, nnode)
        coord = np.array(ds.variables["coord"][:])
        x, y = coord[0], coord[1]

    times = np.array(ds.variables["time_whole"][:])

    # nodal variable names live in 'name_nod_var'
    names = []
    if "name_nod_var" in ds.variables:
        raw = ds.variables["name_nod_var"][:]
        for row in raw:
            s = "".join(c.decode("utf-8") if isinstance(c, bytes) else str(c)
                        for c in row).strip("\x00").strip()
            names.append(s)
    if varname not in names:
        ds.close()
        raise ValueError(f"variable '{varname}' not in nodal vars {names}; "
                         f"pass --var <name>")
    idx = names.index(varname) + 1   # exodus is 1-indexed: vals_nod_var{idx}
    key = f"vals_nod_var{idx}"
    C = np.array(ds.variables[key][:])   # shape (ntime, nnode)
    ds.close()
    return times, (x, y), C


def read_exodus_meshio(path, varname="c"):
    """Fallback reader using meshio (reads point_data per step)."""
    import meshio
    with meshio.xdmf.TimeSeriesReader(path) if path.endswith(".xdmf") \
            else _meshio_exodus(path) as reader:
        pass
    # meshio's exodus reader returns a single mesh with all steps as point_data
    m = meshio.read(path)
    x = m.points[:, 0]
    y = m.points[:, 1]
    # collect c at each step: meshio stores keys like 'c' with shape (nnode, nstep)
    if varname not in m.point_data:
        raise ValueError(f"variable '{varname}' not in {list(m.point_data)}")
    arr = np.asarray(m.point_data[varname])
    if arr.ndim == 1:
        arr = arr[None, :]
    else:
        arr = arr.T                      # -> (nstep, nnode)
    times = np.arange(arr.shape[0], dtype=float)  # meshio may not expose times
    return times, (x, y), arr


def _meshio_exodus(path):
    raise RuntimeError("use meshio.read")


def load_field(path, varname="c"):
    try:
        return read_exodus_netcdf(path, varname)
    except ImportError:
        print("[info] netCDF4 not available; trying meshio ...", file=sys.stderr)
        return read_exodus_meshio(path, varname)


# ----------------------------------------------------------------------
# Gridding (scattered nodes -> regular grid for imaging & FFT)
# ----------------------------------------------------------------------
def to_grid(x, y, c, n=None):
    """Interpolate nodal values onto a regular grid. Returns (X, Y, Cg)."""
    xs = np.unique(np.round(x, 9))
    ys = np.unique(np.round(y, 9))
    if n is None:
        n = (len(ys), len(xs))
    # if the mesh is already a structured grid this is exact
    if len(xs) * len(ys) == len(x):
        order = np.lexsort((x, y))
        Cg = c[order].reshape(len(ys), len(xs))
        X, Y = np.meshgrid(xs, ys)
        return X, Y, Cg
    # otherwise interpolate
    from scipy.interpolate import griddata
    gx = np.linspace(x.min(), x.max(), n[1])
    gy = np.linspace(y.min(), y.max(), n[0])
    X, Y = np.meshgrid(gx, gy)
    Cg = griddata((x, y), c, (X, Y), method="linear")
    return X, Y, Cg


# ----------------------------------------------------------------------
# Characteristic length from the radially-averaged structure factor
# L(t) = 2*pi / <k>,  <k> = sum k S(k) / sum S(k)
# ----------------------------------------------------------------------
def characteristic_length(Cg, Lx, Ly):
    c = Cg - np.nanmean(Cg)
    c = np.nan_to_num(c)
    F = np.fft.fftn(c)
    S = np.abs(F) ** 2
    ny, nx = c.shape
    kx = np.fft.fftfreq(nx, d=Lx / nx) * 2 * np.pi
    ky = np.fft.fftfreq(ny, d=Ly / ny) * 2 * np.pi
    KX, KY = np.meshgrid(kx, ky)
    K = np.sqrt(KX ** 2 + KY ** 2)
    mask = K > 0
    k1 = np.sum(K[mask] * S[mask]) / np.sum(S[mask])
    return 2 * np.pi / k1 if k1 > 0 else np.nan


# ----------------------------------------------------------------------
# Main analysis
# ----------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("exodus", help="path to the MOOSE Exodus (.e) output")
    ap.add_argument("--var", default="c", help="nodal composition variable (default: c)")
    ap.add_argument("--csv", default=None,
                    help="optional CSV with postprocessor columns "
                         "(time,total_free_energy,...) for exact F(t)")
    ap.add_argument("--outdir", default="figures", help="output directory")
    ap.add_argument("--coarsening", action="store_true",
                    help="also compute L(t) ~ t^(1/3) structure-factor analysis")
    ap.add_argument("--nsnap", type=int, default=4,
                    help="number of composition snapshots in row 1")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    times, (x, y), C = load_field(args.exodus, args.var)
    ntime = C.shape[0]
    Lx, Ly = x.max() - x.min(), y.max() - y.min()
    print(f"[ok] read {ntime} steps, {C.shape[1]} nodes, domain {Lx:g} x {Ly:g}")

    # ---- invariant time series ----
    mass = C.mean(axis=1)                       # proportional to integral of c
    m0 = mass[0]
    drift = (mass - m0) / m0
    cmax = C.max(axis=1)
    cmin = C.min(axis=1)

    # free energy: prefer CSV postprocessor; else integrate f_loc from the field
    if args.csv and os.path.exists(args.csv):
        import csv
        t_csv, F_csv = [], []
        with open(args.csv) as fh:
            r = csv.DictReader(fh)
            fcol = next((k for k in r.fieldnames
                         if "free_energy" in k.lower() or k.lower() in ("f", "energy")), None)
            tcol = next((k for k in r.fieldnames if k.lower() in ("time", "t")), r.fieldnames[0])
            for row in r:
                t_csv.append(float(row[tcol]))
                if fcol:
                    F_csv.append(float(row[fcol]))
        F = np.interp(times, t_csv, F_csv) if F_csv else None
        f_source = f"CSV column ('{fcol}')" if F_csv else None
    else:
        F = np.array([f_loc(C[i]).mean() for i in range(ntime)])
        f_source = "integrated f_loc (CALPHAD)"
    print(f"[ok] free energy from {f_source}")

    # ---- Skeptic invariants (scalars) ----
    final_drift = float(drift[-1])
    dF_pct = float((F[-1] - F[0]) / abs(F[0]) * 100) if F is not None and F[0] != 0 else None
    # S2 monotonicity: count steps where F increases beyond round-off
    inc_steps = int(np.sum(np.diff(F) > 1e-12 * np.abs(F[:-1]))) if F is not None else None
    invariants = {
        "S1_relative_mass_drift": final_drift,
        "S1_tolerance": S1_TOL,
        "S1_pass": bool(abs(final_drift) <= S1_TOL),
        "S2_free_energy_decrease_percent": dF_pct,
        "S2_increasing_steps_within_tol": inc_steps,
        "S3_c_max_final": float(cmax[-1]),
        "S3_c_min_final": float(cmin[-1]),
        "S3_target_hi": C_EQ_HI,
        "S3_target_lo": C_EQ_LO,
        "n_timesteps": int(ntime),
    }
    with open(os.path.join(args.outdir, "spinodal_invariants.json"), "w") as fh:
        json.dump(invariants, fh, indent=2)
    print("[ok] invariants:", json.dumps(invariants, indent=2))

    # ---- FIGURE: 2 rows ----
    snap_idx = np.linspace(0, ntime - 1, args.nsnap).astype(int)
    fig = plt.figure(figsize=(13, 6.6))
    gs = fig.add_gridspec(2, max(args.nsnap, 3), height_ratios=[1.05, 1])
    fig.suptitle("AutoMOOSE Fe–Cr spinodal decomposition (500 °C)", fontsize=13, y=0.98)

    # row 1: composition snapshots
    for j, ti in enumerate(snap_idx):
        ax = fig.add_subplot(gs[0, j])
        _, _, Cg = to_grid(x, y, C[ti])
        im = ax.imshow(Cg, origin="lower", cmap="coolwarm", vmin=0.0, vmax=1.0,
                       extent=[0, Lx, 0, Ly])
        ax.set_title(f"t = {times[ti]:.3g}", fontsize=10)
        ax.set_xticks([]); ax.set_yticks([])
        if j == 0:
            ax.set_ylabel("composition $c$ (Cr)", fontsize=10)
    cax = fig.add_axes([0.92, 0.56, 0.013, 0.32])
    fig.colorbar(im, cax=cax, label="$c$ (Cr mole fraction)")

    # row 2: three invariant traces
    axm = fig.add_subplot(gs[1, 0])
    axm.plot(times, drift, color="#0072ce", lw=1.6)
    axm.axhline(S1_TOL, color="#b35c00", ls="--", lw=1.2, label=f"$S_1$ tol {S1_TOL:g}")
    axm.set_title("(a) $S_1$ mass drift", fontsize=11, loc="left")
    axm.set_xlabel("time (s)"); axm.set_ylabel(r"$(m-m_0)/m_0$")
    axm.legend(fontsize=8)

    axf = fig.add_subplot(gs[1, 1])
    if F is not None:
        axf.plot(times, F, color="#1a7f5a", lw=1.6)
    axf.set_title("(b) $S_2$ free energy", fontsize=11, loc="left")
    axf.set_xlabel("time (s)"); axf.set_ylabel("total free energy")

    axc = fig.add_subplot(gs[1, 2])
    axc.plot(times, cmax, color="#1a7f5a", lw=1.6, label="max (Cr-rich)")
    axc.plot(times, cmin, color="#004a86", lw=1.6, label="min (Fe-rich)")
    axc.axhline(C_EQ_HI, color="#999", ls=":", lw=1)
    axc.axhline(C_EQ_LO, color="#999", ls=":", lw=1)
    axc.set_title("(c) $S_3$ tie-line", fontsize=11, loc="left")
    axc.set_xlabel("time (s)"); axc.set_ylabel("Cr mole fraction")
    axc.set_ylim(0, 1); axc.legend(fontsize=8)

    fig.subplots_adjust(left=0.06, right=0.90, top=0.90, bottom=0.08, hspace=0.35, wspace=0.3)
    out = os.path.join(args.outdir, "fig_fecr_spinodal.png")
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"[ok] wrote {out}")

    # ---- optional: coarsening L(t) ~ t^(1/3) ----
    if args.coarsening:
        L = []
        for i in range(ntime):
            _, _, Cg = to_grid(x, y, C[i])
            L.append(characteristic_length(Cg, Lx, Ly))
        L = np.array(L)
        good = (times > 0) & np.isfinite(L) & (L > 0)
        fig2, ax2 = plt.subplots(figsize=(5.2, 4.2))
        ax2.loglog(times[good], L[good], "o", color="#0072ce", ms=5, label="L(t)")
        # reference t^(1/3)
        if good.sum() > 2:
            t_ref = times[good]
            L_ref = L[good][len(L[good]) // 2] * (t_ref / t_ref[len(t_ref) // 2]) ** (1 / 3)
            ax2.loglog(t_ref, L_ref, "k--", lw=1.2, label=r"$t^{1/3}$ (LSW)")
        ax2.set_xlabel("time (s)"); ax2.set_ylabel("characteristic length $L$")
        ax2.set_title("$S_3$ coarsening: $L(t)\\sim t^{1/3}$", fontsize=11)
        ax2.legend(fontsize=9)
        out2 = os.path.join(args.outdir, "fig_fecr_coarsening.png")
        fig2.savefig(out2, dpi=200, bbox_inches="tight")
        print(f"[ok] wrote {out2}")

    print("[done]")


if __name__ == "__main__":
    main()
