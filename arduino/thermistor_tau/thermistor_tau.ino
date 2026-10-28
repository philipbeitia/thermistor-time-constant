/*
  thermistor_tau.ino  —  log an NTC thermistor's temperature at a fixed rate as CSV over USB serial.

  Author : Abdon Philip Beitia Tsang
  Date   : 26 October 2026
  Board  : Arduino Uno / Nano (ATmega328P, 10-bit ADC, 5 V)   <-- change ADC_MAX if your board differs

  Circuit (voltage divider, thermistor to ground):

        5V ──[ R_FIXED ]──┬──[ NTC ]── GND
                          │
                          A0

  Because both halves of the divider see the same 5 V, the supply voltage cancels out:
        ADC / ADC_MAX = R_ntc / (R_FIXED + R_ntc)
    →   R_ntc = R_FIXED * ADC / (ADC_MAX - ADC)

  Then the Beta equation turns resistance into temperature (kelvin):
        1/T = 1/T0 + (1/BETA) * ln(R_ntc / R0)        T0 = 298.15 K (25 °C), R0 = R at 25 °C

  Output (one line per sample, 115200 baud):
        time_ms,raw_adc,temperature_C
*/

// ---------- things to set for YOUR parts ----------
const int   PIN_NTC     = A0;
const float R_FIXED_OHM = 10000.0;   // measure your fixed resistor with a multimeter and type the real value
const float R0_OHM      = 10000.0;   // thermistor resistance at 25 °C (datasheet)
const float BETA_K      = 3950.0;    // Beta value from the datasheet (3435 and 3950 are the common ones)
const float ADC_MAX     = 1023.0;    // 10-bit ADC. A 12-bit board would be 4095.0
// ---------- sampling ----------
const unsigned long PERIOD_MS = 50;  // 50 ms = 20 Hz — the rate used for all the runs in data/
const int   N_AVERAGE   = 8;         // ADC reads averaged per sample — cuts noise, costs < 1 ms
// ---------------------------------------------------

const float T0_K = 298.15;           // 25 °C in kelvin
unsigned long nextSample = 0;

void setup() {
  Serial.begin(115200);
  analogRead(PIN_NTC);               // first read after power-up is junk; throw it away
  Serial.println(F("time_ms,raw_adc,temperature_C"));
  nextSample = millis();
}

void loop() {
  unsigned long now = millis();
  if ((long)(now - nextSample) < 0) return;   // not time yet (wrap-safe comparison)
  nextSample += PERIOD_MS;                    // fixed timetable, so the rate never drifts

  // --- read the ADC N times and average ---
  long sum = 0;
  for (int i = 0; i < N_AVERAGE; i++) sum += analogRead(PIN_NTC);
  float adc = (float)sum / N_AVERAGE;          // 0 … ADC_MAX, fractional thanks to averaging

  // --- ADC → resistance → temperature ---
  float tempC;
  if (adc <= 0.5 || adc >= ADC_MAX - 0.5) {
    tempC = NAN;                               // open or shorted thermistor: don't divide by zero
  } else {
    float r_ntc = R_FIXED_OHM * adc / (ADC_MAX - adc);
    float invT  = 1.0 / T0_K + log(r_ntc / R0_OHM) / BETA_K;
    tempC = 1.0 / invT - 273.15;
  }

  // --- one CSV line ---
  Serial.print(now);     Serial.print(',');
  Serial.print(adc, 2);  Serial.print(',');
  Serial.println(tempC, 2);
}
