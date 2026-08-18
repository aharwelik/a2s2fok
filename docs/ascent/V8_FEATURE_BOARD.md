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
- Development-only, default-off model-stop evidence using `shouldStop`, stopping-path corroboration, live lead vetoes, source age, and trajectory validity. It does not classify the cause as a sign or light.
- Development-only, default-off driver-confirmed left lane-change evidence using a slower lead, adjacent-lane geometry, road edge, blind spot, source age, and lane confidence. It never operates a blinker, selects a lane, or labels the adjacent lane as a legal/same-direction passing lane.
- Stop-sign/light perception training and qualification path.
- Local speed-limit evidence.
- Chestnut/eGPU runtime with a preloaded native-model fallback for loading, USB, inference, or nonfinite-output failure.

The Developer settings screen exposes the two evidence toggles only on the 2023 Ascent development build. The Ascent status screen and restricted SSH `status` command show their state, current model mode, source freshness, trajectory verdict, curve target, lane trim, and per-drive totals.

## Runtime connectors that remain off

- Direct gas or brake control.
- Traffic-light or stop-sign braking.
- Green-light acceleration.
- Automatic pass, blinker, or lane selection.
- Dynamic EyeSight forwarding, automatic parking, or AI/VLA direct CAN.
