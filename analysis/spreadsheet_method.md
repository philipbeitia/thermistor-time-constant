# Finding τ in a spreadsheet (no Python needed)

Open one run's CSV in Excel / Google Sheets / LibreOffice. Columns A–C are `time_ms, raw_adc, temperature_C`.

## 1. The three numbers you need from the data

| name | how | cell |
|---|---|---|
| `T0` | average of `temperature_C` while the sensor is still in air (the flat start) | e.g. `=AVERAGE(C2:C60)` |
| `Tf` | average of the last 5 seconds (the flat end) | e.g. `=AVERAGE(C1500:C1750)` |
| `t0` | the `time_ms` of the last row before the reading starts climbing | read it off the sheet |

## 2. The 63 % rule

* target = `T0 + 0.632*(Tf − T0)`
* find the first row where `temperature_C ≥ target`; τ ≈ its `time_ms` − `t0`, in seconds.

## 3. The straight-line method (this is the maths from class)

The solution `T = Tf − (Tf − T0)·e^(−(t−t0)/τ)` rearranges to

    ln( (Tf − T) / (Tf − T0) ) = −(t − t0) / τ

so plotting the left side against time gives a **straight line through the origin with slope −1/τ**.

* column D: `=(A2-t0)/1000` → seconds since the plunge (only rows after `t0`)
* column E: `=LN((Tf-C2)/(Tf-T0))` → stop using rows once `Tf − C` is smaller than ~0.3 °C (that's just ADC noise)
* `=SLOPE(E_range, D_range)` → τ = `-1/slope`
* `=RSQ(E_range, D_range)` → how straight the line is. Below ~0.99 means the sensor isn't behaving like a simple first-order system (see Limitations in the README).
* Make a scatter plot of E vs D and add a trendline: if it bends, say so.

## 4. Three repeats → mean ± spread

* `=AVERAGE(τ1, τ2, τ3)`, `=STDEV.S(τ1, τ2, τ3)`, and quote the min–max too.
* Sleeve factor = `τ_sleeved_mean / τ_bare_mean`.
  Its uncertainty: `factor * SQRT( (SD_s/mean_s)^2 + (SD_b/mean_b)^2 )`.

The Python script `fit_tau.py` does exactly this, plus a proper least-squares fit of the curve, and writes `results.md` so the numbers can be pasted into the README.
