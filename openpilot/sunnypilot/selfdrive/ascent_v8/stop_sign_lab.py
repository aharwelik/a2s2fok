from dataclasses import dataclass


@dataclass(frozen=True)
class StopSignLabPolicy:
  training_language_distillation: bool = True
  runtime_vlm_required: bool = False
  runtime_detector_connected: bool = False
  physical_braking_connected: bool = False
  minimum_validation_routes: int = 25

  def fail_closed(self) -> bool:
    return (self.training_language_distillation and not self.runtime_vlm_required and
            not self.runtime_detector_connected and not self.physical_braking_connected and
            self.minimum_validation_routes > 0)
