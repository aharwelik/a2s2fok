# 2023 Subaru Ascent V8 Alpha Feature Board

Driver Monitoring is intentionally omitted from this user-facing feature board. The normal-road safety implementation remains unchanged.

## Preserved active behavior

- 2023 Ascent and Subaru D recognition.
- Bus-0 angle steering with the V6 planner, 170/300/100 driver thresholds, measured-angle resume, and final-settle protection.
- MADS authorization, heartbeat recovery, and the reverse/park/standstill/very-low-speed guard.
- Factory EyeSight lead following, stop/go, automatic emergency braking, and forward-collision warning.
- Driver-requested lane changes, road-edge veto, fresh blind-spot veto, boot-time ACC-cancel grace, and no-phantom-acceleration clamp.

## V8 shadow-only intelligence

- Unknown-space occupancy using current lead, blind-spot, road-edge, and source-age evidence.
- Adaptive curve envelope using predicted curvature and observed lateral-controller saturation.
- Lane-positioning research surface using current lane geometry and confidence.
- Whole-trajectory supervisor using model timestamps, acceleration, jerk, and derived curvature.
- Final-command shadow guard using the model's current action candidate.
- Stop-sign perception training path.
- Local speed-limit evidence.
- Chestnut/eGPU runtime with a preloaded native-model fallback for loading, USB, inference, or nonfinite-output failure.

The comma settings screen and restricted SSH `status` command show the current model mode, source freshness, trajectory verdict, curve target, lane trim, and per-drive evaluation/error totals.

## Runtime connectors that remain off

- Direct gas or brake control.
- Traffic-light or stop-sign braking.
- Green-light acceleration.
- Automatic pass, blinker, or lane selection.
- Dynamic EyeSight forwarding, automatic parking, or AI/VLA direct CAN.
