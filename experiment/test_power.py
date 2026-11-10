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
