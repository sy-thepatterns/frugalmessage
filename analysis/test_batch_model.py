"""Small hand-checkable cases for the count-or-timeout model."""
import importlib.util
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location("analysis", Path(__file__).with_name("01_workload_characterization.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_timeout_excludes_later_event():
    count, waits = module.model_batches(np.array([0., 2., 10.]), 8, 5)
    assert count == 2
    np.testing.assert_allclose(waits, [5., 3., 5.])


def test_count_flush_and_single_event():
    count, waits = module.model_batches(np.array([0., 2., 10.]), 2, 5)
    assert count == 2
    np.testing.assert_allclose(waits, [2., 0., 5.])
    count, waits = module.model_batches(np.array([0., 2., 10.]), 1, 60)
    assert count == 3
    np.testing.assert_allclose(waits, [0., 0., 0.])

