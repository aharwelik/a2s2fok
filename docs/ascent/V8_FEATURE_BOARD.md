# 2023 Subaru Ascent V8 Alpha Feature Board

Driver Monitoring is intentionally omitted from this user-facing feature board. The normal-road safety implementation remains unchanged.

## Preserved active behavior

- 2023 Ascent and Subaru D recognition.
- Bus-0 angle steering with the V6 planner, 170/300/100 driver thresholds, measured-angle resume, and final-settle protection.
- MADS authorization, heartbeat recovery, and the reverse/park/standstill/very-low-speed guard.
- Factory EyeSight lead following, stop/go, automatic emergency braking, and forward-collision warning.
- Driver-requested lane changes, road-edge veto, fresh blind-spot veto, boot-time ACC-cancel grace, and no-phantom-acceleration clamp.

## V8 shadow-only intelligence

- Unknown-space occupancy.
- Adaptive curve envelope.
- Lane-positioning research surface.
- Whole-trajectory supervisor.
- Final-command shadow guard.
- Stop-sign perception training path.
- Local speed-limit evidence.
- Native-model-first Chestnut/eGPU policy.

## Runtime connectors that remain off

- Direct gas or brake control.
- Traffic-light or stop-sign braking.
- Green-light acceleration.
- Automatic pass, blinker, or lane selection.
- Dynamic EyeSight forwarding, automatic parking, or AI/VLA direct CAN.
