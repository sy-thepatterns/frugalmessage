import pandas as pd
import pytest

from experiment.integrate_power import integrate


def test_constant_watts_integrate_to_joules():
    samples = pd.DataFrame({'timestamp_utc': pd.to_datetime(
        ['2026-01-01T00:00:00Z', '2026-01-01T00:00:01Z',
         '2026-01-01T00:00:02Z'], utc=True), 'power_w': [10, 10, 10]})
    assert integrate(samples, pd.Timestamp('2026-01-01T00:00:00.5Z'),
                     pd.Timestamp('2026-01-01T00:00:01.5Z'), 2) == pytest.approx(10)
    with pytest.raises(ValueError, match='gap'):
        integrate(samples, pd.Timestamp('2026-01-01T00:00:00Z'),
                  pd.Timestamp('2026-01-01T00:00:02Z'), .5)


def test_short_run_cannot_bridge_long_sensor_gap():
    samples = pd.DataFrame({'timestamp_utc': pd.to_datetime(
        ['2026-01-01T00:00:00Z', '2026-01-01T00:01:00Z'], utc=True),
        'power_w': [10, 10]})
    with pytest.raises(ValueError, match='gap'):
        integrate(samples, pd.Timestamp('2026-01-01T00:00:20Z'),
                  pd.Timestamp('2026-01-01T00:00:21Z'), 5)


@pytest.mark.parametrize('watts', [[10, float('nan')], [10, float('inf')], [10, -1]])
def test_invalid_watts_rejected(watts):
    samples = pd.DataFrame({'timestamp_utc': pd.to_datetime(
        ['2026-01-01T00:00:00Z', '2026-01-01T00:00:01Z'], utc=True), 'power_w': watts})
    with pytest.raises(ValueError, match='finite'):
        integrate(samples, samples.timestamp_utc.iloc[0], samples.timestamp_utc.iloc[1], 5)
