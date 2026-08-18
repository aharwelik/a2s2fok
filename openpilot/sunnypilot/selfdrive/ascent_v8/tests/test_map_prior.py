from math import isclose

from tools.ascent_v8_map_prior import evaluate_labels, haversine_m


def test_haversine_distance_for_small_longitude_change():
  assert isclose(haversine_m(0.0, 0.0, 0.0, 0.001), 111.195, rel_tol=0.001)


def test_map_prior_matches_signal_but_keeps_missing_stop_unmatched():
  points = [
    {"mono_ns": 100, "lat": 27.0, "lon": -82.0, "accuracy_m": 1.0},
    {"mono_ns": 200, "lat": 27.001, "lon": -82.001, "accuracy_m": 1.0},
  ]
  nodes = [
    {"id": 1, "lat": 27.0001, "lon": -82.0, "tags": {"highway": "traffic_signals"}},
    {"id": 2, "lat": 27.1, "lon": -82.1, "tags": {"highway": "stop"}},
  ]
  labels = [
    {"segment": 1, "approx_mono_ns": 100, "control_type": "traffic_signal", "state": "red"},
    {"segment": 2, "approx_mono_ns": 200, "control_type": "stop_sign", "state": "stop_required"},
  ]

  result = evaluate_labels(labels, points, nodes, match_distance_m=50.0)

  assert result[0]["map_match"] is True
  assert result[0]["nearest_osm_id"] == 1
  assert result[1]["map_match"] is False
  assert result[1]["nearest_osm_id"] == 2
