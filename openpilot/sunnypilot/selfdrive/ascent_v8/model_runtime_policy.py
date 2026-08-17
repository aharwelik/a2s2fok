from dataclasses import dataclass


@dataclass(frozen=True)
class BigModelPolicy:
  native_first: bool = True
  big_model_default: bool = False
  load_watchdog_ms: int = 30000
  run_watchdog_ms: int = 3000
  overall_load_timeout_s: int = 60
  stable_power_reference_mv: int = 13000
  stable_power_reference_s: float = 3.0
  disengaged_only_swap: bool = True
  preload_small_model: bool = True
  warmup_required: bool = True
  cleanup_thread_cache: bool = True
  no_board_bench_supported: bool = True
  background_load: bool = True
  recurrent_state_reset: bool = True
  fallback_on_exception: bool = True
  fallback_on_nonfinite: bool = True
  fallback_on_usb_loss: bool = True

  def safe_defaults(self) -> bool:
    return (self.native_first and not self.big_model_default and self.load_watchdog_ms > self.run_watchdog_ms and
            self.disengaged_only_swap and self.preload_small_model and self.warmup_required and self.cleanup_thread_cache and
            self.no_board_bench_supported and self.background_load and self.recurrent_state_reset and
            self.fallback_on_exception and self.fallback_on_nonfinite and self.fallback_on_usb_loss)
