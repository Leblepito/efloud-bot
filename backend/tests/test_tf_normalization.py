import pytest
from data.timeframes import tf_to_minutes


@pytest.mark.parametrize("tf,expected", [
    ("1m", 1), ("15m", 15), ("1h", 60), ("4h", 240), ("1d", 1440), ("1w", 10080),
])
def test_tf_to_minutes_known(tf, expected):
    assert tf_to_minutes(tf) == expected


@pytest.mark.parametrize("bad", ["", "15", "15x", "abc", None])
def test_tf_to_minutes_bad_raises(bad):
    with pytest.raises((ValueError, TypeError)):
        tf_to_minutes(bad)
