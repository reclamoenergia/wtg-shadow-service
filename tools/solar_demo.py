from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is importable when running as: python tools/solar_demo.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model.solar import build_times_for_year, filter_daylight, solar_position


def main() -> None:
    config = {
        "lat": 45.4642,
        "lon": 9.1900,
        "tz": "Europe/Rome",
        "year": 2025,
        "step": 60,
    }

    times = build_times_for_year(
        year=config["year"],
        timezone=config["tz"],
        step_minutes=config["step"],
    )

    positions = solar_position(
        times=times,
        latitude_deg=config["lat"],
        longitude_deg=config["lon"],
    )

    daylight = filter_daylight(positions, min_elevation_deg=0.0)

    print(f"Righe totali: {len(positions)}")
    print(f"Righe diurne: {len(daylight)}")

    print("\nPrime 5 righe (timestamp, elevazione, azimut):")
    preview = positions[["apparent_elevation", "azimuth"]].head(5)
    for ts, row in preview.iterrows():
        print(f"{ts} | {row['apparent_elevation']:.3f} | {row['azimuth']:.3f}")


if __name__ == "__main__":
    main()