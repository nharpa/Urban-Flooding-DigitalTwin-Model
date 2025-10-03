import math
import pytest

from digital_twin.spatial.spatial_utils import calculate_pipe_grade


def test_calculate_pipe_grade_basic():
    # Upstream higher than downstream -> positive slope
    grade = calculate_pipe_grade(10.0, 9.5, 50.0)
    assert pytest.approx(grade, rel=1e-3) == (10.0 - 9.5) / 50.0 * 100


def test_calculate_pipe_grade_negative_becomes_nominal():
    # Downstream higher (reverse) -> coerced to nominal 0.1
    grade = calculate_pipe_grade(9.0, 9.5, 40.0)
    assert grade == 0.1


def test_calculate_pipe_grade_zero_slope_nominal():
    grade = calculate_pipe_grade(9.0, 9.0, 25.0)
    assert grade == 0.1


def test_calculate_pipe_grade_invalid_length():
    assert calculate_pipe_grade(10.0, 9.0, 0) is None
    assert calculate_pipe_grade(10.0, 9.0, 0.001) is None


def test_calculate_pipe_grade_large_cap():
    # Unrealistic large slope should be capped at 50%
    grade = calculate_pipe_grade(15.0, 10.0, 5.0)  # (5/5)*100 = 100%
    assert grade == 50.0


def test_calculate_pipe_grade_missing_inputs():
    assert calculate_pipe_grade(None, 9.0, 30.0) is None
    assert calculate_pipe_grade(10.0, None, 30.0) is None
    assert calculate_pipe_grade(10.0, 9.0, None) is None
