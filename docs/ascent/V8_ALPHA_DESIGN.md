# 2023 Subaru Ascent V8 Alpha

V8 uses synchronized Sunnypilot `0b1ed0d047aca5bed45f20323823c5d5e9cb6bc1` and OpenDBC `abab7a16903a0da7be42128af124f27c977e2617` as its modern base. Proven Ascent behavior is semantically ported from V7 root `549c460212c9bc948405c60de2802bc6265552e8` and OpenDBC `f96bf1ee6fc5891431938c4f175909b2e3198e4f`.

Stock EyeSight retains all longitudinal authority, automatic emergency braking, and forward-collision warning. V8 adds no production gas, brake, traffic-control, automatic-pass, automatic-blinker, or automatic-lane-selection connector. All new intelligence defaults to fail-closed shadow or evidence-only behavior.

The device maintenance channel is a restricted key-only SSH endpoint. It supports status, parked log bundles, signed parked updates, and parked rollback without embedding a private credential or permitting arbitrary on-road shell execution.
