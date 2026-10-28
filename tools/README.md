# tools/ — getting the numbers off the Arduino

The sketch prints one CSV line every 50 ms. The Arduino IDE's Serial Monitor shows them but can't save them, so one of these two does the saving. **Close the Arduino IDE first** — only one program can hold the serial port, and the IDE keeps it even when the Serial Monitor is closed.

## What I used: one PowerShell line (Windows)

Check the port name:

```
[System.IO.Ports.SerialPort]::GetPortNames()
```

If the IDE is still holding the port, free it:

```
Get-Process | Where-Object { $_.ProcessName -match 'arduino|serial-monitor|serial-discovery' } | Stop-Process -Force
```

Record (change `COM4` and the file name for each run):

```
$p = New-Object System.IO.Ports.SerialPort COM4,115200; $p.NewLine = "`r`n"; $p.Open(); try { while ($true) { $l = $p.ReadLine(); Add-Content -Path "$HOME\Downloads\bare_run1.csv" -Value $l -Encoding ascii; Write-Host $l } } finally { $p.Close() }
```

Lines scroll on screen and go into the file as they arrive. **Ctrl-C** stops it and closes the port.

Mac/Linux equivalent: `(stty -f /dev/cu.usbmodemXXXX 115200; cat /dev/cu.usbmodemXXXX) > bare_run1.csv`, Ctrl-C to stop.

## Alternative: serial_logger.html

Open `serial_logger.html` in Chrome or Edge (not Safari/Firefox) → Connect → pick the Arduino → Start run → Stop → Download CSV. Shows a live graph while recording. Uses the browser's Web Serial API; nothing to install.

## Quirks the analysis script copes with

* A few stale lines from the serial buffer arrive when the port opens (time jumps backwards) — dropped.
* The odd corrupted line (`206900,4?)?b??r??j`) — dropped.
* Two runs appended to one file by mistake (time jumps forwards by minutes) — the script uses the last recording and says so.
* The sensor lifted out before Ctrl-C (cooling tail) — the script cuts the run at the peak.
