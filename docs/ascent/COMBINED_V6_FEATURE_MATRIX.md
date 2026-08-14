# Ascent combined V6 feature matrix

| Feature | Classification |
| --- | --- |
| Angle lane centering | LIVE_ACTIVE |
| Driver-blinker lane change | LIVE_ACTIVE |
| Automatic blinker activation | UNAVAILABLE |
| Map display | LIVE_ACTIVE |
| Speed-limit information/warning | LIVE_ACTIVE |
| Map-controlled Ascent braking | UNAVAILABLE |
| Model stop detection | LIVE_SHADOW |
| Virtual stop obstacle | LIVE_SHADOW / SIMULATION_ONLY actuation |
| Stop-sign/red-light live braking | UNAVAILABLE |
| Overtake recommendation | LIVE_SHADOW |
| Autonomous passing decision | SIMULATION_ONLY |
| Openpilot longitudinal | UNAVAILABLE |
| Stock EyeSight longitudinal | LIVE_ACTIVE |
| EyeSight disable | UNAVAILABLE |
| Factory AEB/FCW | PRESERVED |

Live-shadow stop and overtake packages do not publish live brake, throttle,
cruise-button, blinker, or vehicle-control requests.

