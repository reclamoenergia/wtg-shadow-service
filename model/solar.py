from __future__ import annotations

import pandas as pd
from pvlib.solarposition import get_solarposition


def build_times_for_year(year: int, timezone: str, step_minutes: int) -> pd.DatetimeIndex:
    """Build a timezone-aware timeline for the full year with DST handled by pandas."""
    if step_minutes <= 0:
        raise ValueError("step_minutes must be > 0")

    start = pd.Timestamp(year=year, month=1, day=1, tz=timezone)
    end = pd.Timestamp(year=year + 1, month=1, day=1, tz=timezone)

    return pd.date_range(
        start=start,
        end=end,
        freq=f"{step_minutes}min",
        inclusive="left",
    )


def solar_position(
    times: pd.DatetimeIndex,
    latitude_deg: float,
    longitude_deg: float,
) -> pd.DataFrame:
    """Return solar apparent elevation and azimuth (degrees) for each timestamp."""
    position = get_solarposition(
        time=times,
        latitude=latitude_deg,
        longitude=longitude_deg,
    )

    return position[["apparent_elevation", "azimuth"]].copy()


def filter_daylight(df: pd.DataFrame, min_elevation_deg: float) -> pd.DataFrame:
    """Filter rows where apparent elevation is above the provided minimum."""
    if "apparent_elevation" not in df.columns:
        raise KeyError("df must contain 'apparent_elevation' column")

    return df[df["apparent_elevation"] > min_elevation_deg].copy()