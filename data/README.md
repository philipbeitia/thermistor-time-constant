# data/

Raw logs straight from the Arduino, never edited by hand (except that `bare_run3`, `sleeved_run1..3` were cut out of files that had two recordings appended — the cut is at a time jump, no samples inside a run were touched).

Columns: `time_ms, raw_adc, temperature_C`, one line every 50 ms. `time_ms` is the Arduino's clock since power-up, so it doesn't start at 0. A few files start with a couple of stale lines from the serial buffer and contain the odd corrupted line; `analysis/fit_tau.py` skips those.

All runs: 26–27 October 2026, room ~22–25 °C, probe plunged into a mug of stirred warm tap water. TP101 read just before each plunge.

| file | probe | TP101 water (°C) | notes |
|---|---|---|---|
| bare_run1.csv | bare | 48.0 | probe lifted out ~6 s before logging stopped |
| bare_run2.csv | bare | 43.0 | |
| bare_run3.csv | bare | 45.0 | water cooled ~0.5 °C during the run |
| bare_run4.csv | bare | 42.2 | |
| sleeved_run1.csv | plastic wrap, fresh, air trapped | 38.6 | |
| sleeved_run2.csv | same wrap, not re-fitted | 44.5 | water cooling ~0.4 °C/min at the end |
| sleeved_run3.csv | same wrap, not re-fitted — damp inside, less air | 40.3 | probe started at 28.5 °C (not fully cooled from run 2); water cooling ~0.5 °C/min at the end |
