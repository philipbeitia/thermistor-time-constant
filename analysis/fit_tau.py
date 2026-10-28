#!/usr/bin/env python3
"""
fit_tau.py — find the time constant τ of a temperature sensor from a step-response log.

    python analysis/fit_tau.py data/*.csv          # fit every run, write results + plots
    python analysis/fit_tau.py --selftest          # check the method on made-up data with a known τ

Input  : CSVs from the Arduino sketch, columns  time_ms, raw_adc, temperature_C
         named  <condition>_run<N>.csv   e.g. bare_run1.csv, sleeved_run2.csv
Output : analysis/results.csv  (one row per run)
         analysis/results.md   (summary table, paste into README)
         analysis/fig_T_vs_t.png        temperature vs time with fitted curves
         analysis/fig_log_check.png     the straight-line check  ln(gap/gap0) vs t

Model (Newton's law of heating, same form as the falling-body equation dv/dt = A − B·v):

        dT/dt = (T_true − T)/τ     →     T(t) = T_true − (T_true − T0)·exp(−(t − t0)/τ)

τ is found three ways per run:
  1. 63 % rule   — time after the plunge for the reading to cover 63.2 % of the gap (pure data, no fitting)
  2. curve fit   — least squares on the exponential (free: T_inf, T0, τ, t0)
  3. straight line — fit a line to  y = ln((T_inf − T)/(T_inf − T0))  vs  t ; slope = −1/τ.
                     If the points are not on a straight line, the sensor is not a simple first-order system.
Uncertainty across repeats = mean ± standard deviation (n−1) of the 3 runs, plus the min–max range.
"""
import argparse
import glob
import os
import re
import sys
import tempfile

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))


# ----------------------------------------------------------------------------- model
def step_model(t, T_inf, T0, tau, t0):
    """First-order step response. Flat at T0 before t0, exponential after."""
    out = np.full_like(t, T0, dtype=float)
    after = t >= t0
    out[after] = T_inf - (T_inf - T0) * np.exp(-(t[after] - t0) / tau)
    return out


# ----------------------------------------------------------------------------- one run
def analyse_run(t, T, baseline_s=1.5, tail_frac=0.10):
    """
    t in seconds, T in °C. Returns a dict of numbers for this run.
    baseline_s : how many seconds at the start are 'sensor sitting in air'
    tail_frac  : last fraction of the run used to estimate the final temperature
    """
    t = np.asarray(t, float)
    T = np.asarray(T, float)
    ok = np.isfinite(T)
    t, T = t[ok], T[ok]
    dt = float(np.median(np.diff(t)))

    # --- 0. if the sensor was lifted out before logging stopped, the end cools in air: cut at the peak
    k = max(int(round(0.5 / dt)), 3)                       # ~0.5 s moving average
    Ts = np.convolve(T, np.ones(k) / k, mode="valid")       # 'valid' = no zero-padding at the edges
    i_peak = int(np.argmax(Ts)) + k // 2                     # index back in the unsmoothed array
    trimmed_s = 0.0
    if Ts[-1] < Ts.max() - 0.5 and i_peak < len(T) - k:
        trimmed_s = float(t[-1] - t[i_peak])
        t, T = t[:i_peak + 1], T[:i_peak + 1]

    # --- 1. baseline (T0) and noise level from the first baseline_s seconds
    base = T[t <= t[0] + baseline_s]
    if len(base) < 10:
        base = T[:10]
    T0_data = float(np.median(base))
    sigma = float(np.std(base, ddof=1)) if len(base) > 1 else 0.05
    sigma = max(sigma, 0.02)

    # --- 2. detect the plunge: first sample clearly above the baseline
    thresh = T0_data + max(6 * sigma, 0.4)
    idx = np.argmax(T > thresh)
    if not (T > thresh).any():
        raise ValueError("no temperature step found — did the sensor go into the water?")
    i_plunge = max(idx - 1, 0)          # last sample still at baseline
    t0_data = float(t[i_plunge])

    # --- 3. final temperature from the tail of the run
    n_tail = max(int(len(T) * tail_frac), 10)
    tail = T[-n_tail:]
    T_inf_data = float(np.mean(tail))
    tail_slope = float(np.polyfit(t[-n_tail:], tail, 1)[0])   # °C/s; should be ~0 if settled

    gap0 = T_inf_data - T0_data

    # --- 4. the 63 % rule
    target = T0_data + (1 - np.exp(-1)) * gap0
    j = idx + int(np.argmax(T[idx:] >= target))
    # linear interpolation between sample j-1 and j for the crossing time
    if j > 0 and T[j] != T[j - 1]:
        t_cross = t[j - 1] + (target - T[j - 1]) * (t[j] - t[j - 1]) / (T[j] - T[j - 1])
    else:
        t_cross = t[j]
    tau_63 = float(t_cross - t0_data)

    # --- 5. least-squares fit of the exponential (free T_inf, T0, tau, t0)
    sel = t >= t0_data - 1.0                      # keep 1 s of baseline so T0 and t0 are pinned
    p0 = [T_inf_data, T0_data, max(tau_63, dt), t0_data]
    popt, pcov = curve_fit(step_model, t[sel], T[sel], p0=p0, maxfev=20000)
    perr = np.sqrt(np.diag(pcov))
    T_inf_fit, T0_fit, tau_fit, t0_fit = (float(v) for v in popt)
    resid = T[sel] - step_model(t[sel], *popt)
    rmse = float(np.sqrt(np.mean(resid ** 2)))

    # --- 6. the straight-line check:  ln(gap/gap0) = -(t - t0)/tau
    after = (t > t0_data) & (T_inf_data - T > max(5 * sigma, 0.3))   # stop before the noise floor
    y = np.log((T_inf_data - T[after]) / gap0)
    x = t[after] - t0_data
    if len(x) >= 5:
        slope, intercept = np.polyfit(x, y, 1)
        yhat = slope * x + intercept
        r2 = float(1 - np.sum((y - yhat) ** 2) / np.sum((y - y.mean()) ** 2))
        tau_lin = float(-1 / slope)
    else:
        slope = intercept = np.nan
        r2, tau_lin = np.nan, np.nan

    return dict(
        sample_period_s=dt,
        n_samples=len(T),
        trimmed_end_s=trimmed_s,
        T0_C=T0_data,
        T_inf_C=T_inf_data,
        T_inf_fit_C=T_inf_fit,
        tail_slope_C_per_s=tail_slope,
        noise_sd_C=sigma,
        t0_s=t0_data,
        t0_fit_s=t0_fit,
        tau_63_s=tau_63,
        tau_fit_s=tau_fit,
        tau_fit_se_s=float(perr[2]),
        fit_rmse_C=rmse,
        tau_line_s=tau_lin,
        line_R2=r2,
        _fit=(popt, t[sel], T[sel]),
        _line=(x, y, slope, intercept),
    )


# ----------------------------------------------------------------------------- many runs
def parse_name(path):
    m = re.match(r"([A-Za-z]+)_run(\d+)", os.path.basename(path))
    if not m:
        raise ValueError(f"{path}: name it <condition>_run<N>.csv, e.g. bare_run1.csv")
    return m.group(1).lower(), int(m.group(2))


def summarise(df):
    """Per-condition mean ± SD, plus the sleeved/bare ratio with its uncertainty."""
    rows = []
    for cond, g in df.groupby("condition"):
        for col in ("tau_fit_s", "tau_63_s", "tau_line_s"):
            v = g[col].dropna().values
            rows.append(dict(condition=cond, method=col.replace("_s", ""), n=len(v),
                             mean=v.mean(), sd=v.std(ddof=1) if len(v) > 1 else np.nan,
                             se=v.std(ddof=1) / np.sqrt(len(v)) if len(v) > 1 else np.nan,
                             min=v.min(), max=v.max()))
    summ = pd.DataFrame(rows)

    ratio_txt = ""
    conds = set(df.condition)
    if {"bare", "sleeved"} <= conds:
        b = summ[(summ.condition == "bare") & (summ.method == "tau_fit")].iloc[0]
        s = summ[(summ.condition == "sleeved") & (summ.method == "tau_fit")].iloc[0]
        ratio = s["mean"] / b["mean"]
        # relative uncertainties add in quadrature (SDs, so this is a spread, not a standard error)
        rel = np.sqrt((s["sd"] / s["mean"]) ** 2 + (b["sd"] / b["mean"]) ** 2)
        ratio_txt = (f"\nThe sleeve made the sensor **{ratio:.1f} ± {ratio * rel:.1f}×** slower "
                     f"(τ_sleeved / τ_bare, from the curve fits; ± from the run-to-run spread).\n")
    return summ, ratio_txt


def results_markdown(df, summ, ratio_txt):
    lines = ["| Run | T₀ (°C) | T_final (°C) | τ 63 % (s) | τ fit (s) | τ line (s) | line R² | fit RMSE (°C) |",
             "|---|---|---|---|---|---|---|---|"]
    for _, r in df.sort_values(["condition", "run"]).iterrows():
        lines.append(f"| {r.condition} {r.run} | {r.T0_C:.1f} | {r.T_inf_C:.1f} | {r.tau_63_s:.2f} | "
                     f"{r.tau_fit_s:.2f} | {r.tau_line_s:.2f} | {r.line_R2:.3f} | {r.fit_rmse_C:.2f} |")
    lines += ["", "| Condition | Method | n | mean τ (s) | SD (s) | min–max (s) |", "|---|---|---|---|---|---|"]
    for _, r in summ.iterrows():
        lines.append(f"| {r.condition} | {r.method} | {r.n} | {r['mean']:.2f} | {r.sd:.2f} | "
                     f"{r['min']:.2f}–{r['max']:.2f} |")
    return "\n".join(lines) + "\n" + ratio_txt


def make_plots(runs, outdir):
    colours = {"bare": "#1f77b4", "sleeved": "#d62728"}
    # --- figure 1: T vs t with fitted curves, time shifted so the plunge is at t = 0
    fig, ax = plt.subplots(figsize=(8, 5))
    for cond, run, res in runs:
        c = colours.get(cond, None)
        popt, tt, TT = res["_fit"]
        ax.plot(tt - res["t0_s"], TT, ".", ms=3, alpha=0.35, color=c,
                label=f"{cond} data" if run == 1 else None)
        tf = np.linspace(tt.min(), tt.max(), 600)
        ax.plot(tf - res["t0_s"], step_model(tf, *popt), "-", lw=1.6, color=c,
                label=f"{cond} fit  (τ = {res['tau_fit_s']:.2f} s, run {run})")
    ax.set_xlabel("time since plunge (s)")
    ax.set_ylabel("temperature (°C)")
    ax.set_title("Thermistor step response: room air → warm water")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, "fig_T_vs_t.png"), dpi=150)
    plt.close(fig)

    # --- figure 2: straight-line check
    fig, ax = plt.subplots(figsize=(8, 5))
    for cond, run, res in runs:
        x, y, slope, intercept = res["_line"]
        c = colours.get(cond, None)
        ax.plot(x, y, ".", ms=3, alpha=0.5, color=c, label=f"{cond} run {run}" )
        if np.isfinite(slope):
            ax.plot(x, slope * x + intercept, "-", lw=1, color=c, alpha=0.8)
    ax.set_xlabel("time since plunge (s)")
    ax.set_ylabel("ln( (T_final − T) / (T_final − T₀) )")
    ax.set_title("First-order check: a straight line means dT/dt ∝ (T_true − T) holds")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, "fig_log_check.png"), dpi=150)
    plt.close(fig)


def load_log(path):
    """
    Read a log line by line. Tolerates: '#' comment lines, a missing header, a corrupted line
    (serial glitch), a partial first line, blank lines. Keeps only lines with 3 numeric fields.
    Returns (t_seconds, T_celsius, n_dropped).
    """
    t, T, dropped = [], [], 0
    with open(path, "r", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or line.lower().startswith("time_ms"):
                continue
            parts = line.split(",")
            try:
                if len(parts) != 3:
                    raise ValueError
                t_ms, _, temp = float(parts[0]), float(parts[1]), float(parts[2])
            except ValueError:
                dropped += 1
                continue
            t.append(t_ms / 1000.0)
            T.append(temp)
    t, T = np.asarray(t), np.asarray(T)
    # A file can hold more than one recording: stale lines from the serial buffer when the port opens
    # (time jumps backwards), or a second run appended to the first (time jumps forwards by a lot).
    # Split wherever time is not continuous and keep the LAST segment that is long enough to be a run.
    cuts = np.where((np.diff(t) <= 0) | (np.diff(t) > 1.0))[0] + 1
    segments = np.split(np.arange(len(t)), cuts)
    good = [s for s in segments if len(s) >= 100]
    if not good:
        raise ValueError(f"{path}: no run of 100+ samples found")
    if len(good) > 1:
        print(f"{os.path.basename(path)}: contains {len(good)} recordings — using the last one "
              f"(samples {good[-1][0]}–{good[-1][-1]}). Split the file if that is not what you meant.")
    keep = good[-1]
    dropped += len(t) - len(keep)
    t, T = t[keep], T[keep]
    # the Arduino's millis() keeps counting while nothing is logged; make time start at the first kept sample
    return t - t[0], T, dropped


def run_all(paths, outdir):
    os.makedirs(outdir, exist_ok=True)
    rows, runs = [], []
    for p in sorted(paths):
        cond, run = parse_name(p)
        t, T, dropped = load_log(p)
        if dropped:
            print(f"{os.path.basename(p)}: skipped {dropped} unreadable line(s)")
        res = analyse_run(t, T)
        runs.append((cond, run, res))
        rows.append(dict(file=os.path.basename(p), condition=cond, run=run,
                         **{k: v for k, v in res.items() if not k.startswith("_")}))
        print(f"{os.path.basename(p):22s}  τ63 = {res['tau_63_s']:.2f} s   τfit = {res['tau_fit_s']:.2f} ± "
              f"{res['tau_fit_se_s']:.2f} s   τline = {res['tau_line_s']:.2f} s (R² {res['line_R2']:.3f})   "
              f"T0 {res['T0_C']:.1f} → {res['T_inf_C']:.1f} °C   tail slope {res['tail_slope_C_per_s']:+.3f} °C/s")
        if res["trimmed_end_s"] > 0:
            print(f"    note: last {res['trimmed_end_s']:.1f} s cut off (sensor lifted out before logging stopped)")
        if abs(res["tail_slope_C_per_s"]) > 0.02:
            print("    ! the reading was still drifting at the end — log longer or the water was cooling")
        if res["sample_period_s"] > 0.2 * res["tau_fit_s"]:
            print("    ! fewer than 5 samples per τ — sample faster for this condition")

    df = pd.DataFrame(rows)
    summ, ratio_txt = summarise(df)
    df.to_csv(os.path.join(outdir, "results.csv"), index=False, float_format="%.4f")
    md = results_markdown(df, summ, ratio_txt)
    with open(os.path.join(outdir, "results.md"), "w") as f:
        f.write(md)
    make_plots(runs, outdir)
    print("\n" + md)
    print(f"written: {outdir}/results.csv, results.md, fig_T_vs_t.png, fig_log_check.png")
    return df, summ


# ----------------------------------------------------------------------------- self-test
def synth_run(path, tau, T0=22.0, T_inf=40.0, t_plunge=3.0, duration=None, fs=50, seed=0):
    """Fake a log with a known τ: ADC-style 0.1 °C steps and a bit of noise."""
    rng = np.random.default_rng(seed)
    duration = duration or (t_plunge + 8 * tau)
    t = np.arange(0, duration, 1 / fs)
    T = step_model(t, T_inf, T0, tau, t_plunge) + rng.normal(0, 0.03, len(t))
    T = np.round(T / 0.1) * 0.1                                   # quantise like a 10-bit ADC
    pd.DataFrame({"time_ms": (t * 1000).astype(int), "raw_adc": 0, "temperature_C": T}).to_csv(path, index=False)


def selftest():
    tmp = tempfile.mkdtemp(prefix="tau_selftest_")
    truth = {"bare": [2.0, 2.1, 1.9], "sleeved": [8.0, 8.4, 7.7]}
    for cond, taus in truth.items():
        for i, tau in enumerate(taus, 1):
            synth_run(os.path.join(tmp, f"{cond}_run{i}.csv"), tau, seed=i)
    print(f"self-test on synthetic data in {tmp}\ntrue τ: {truth}\n")
    df, summ = run_all(glob.glob(os.path.join(tmp, "*.csv")), os.path.join(tmp, "out"))
    worst = max(abs(r.tau_fit_s - truth[r.condition][r.run - 1]) / truth[r.condition][r.run - 1]
                for _, r in df.iterrows())
    print(f"\nlargest error of the curve fit vs the true τ: {100 * worst:.1f} %  "
          f"({'OK' if worst < 0.05 else 'CHECK THE METHOD'})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help="CSV logs, e.g. data/*.csv")
    ap.add_argument("--selftest", action="store_true", help="run on synthetic data with a known τ")
    ap.add_argument("--out", default=HERE, help="output folder (default: this analysis/ folder)")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    elif a.files:
        run_all(a.files, a.out)
    else:
        ap.print_help()
        sys.exit(1)
