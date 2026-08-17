from dataclasses import dataclass


@dataclass(frozen=True)
class SpeedLimitEvidence:
  way_id: int
  speed_mps: float
  source: str
  lat: float
  lon: float
  heading_deg: float
  timestamp_s: float
  confidence: float

  def valid(self) -> bool:
    return (self.way_id > 0 and self.speed_mps >= 1.0 and -90 <= self.lat <= 90 and -180 <= self.lon <= 180 and
            0 <= self.heading_deg < 360 and 0 <= self.confidence <= 1)


def same_way_for_revalidation(saved_way_id: int, returned_way_id: int) -> bool:
  return saved_way_id > 0 and saved_way_id == returned_way_id
