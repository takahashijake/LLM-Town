"""Opt-in V9 continuation of the existing Python activity arbitration stream."""
import math
import random


def restore_project_random_state(data: dict) -> None:
    """Validate with an isolated generator before changing the runtime stream."""
    if (type(data) is not dict or set(data) != {'version', 'state'}
            or type(data['version']) is not int or data['version'] != 1):
        raise ValueError('invalid V9 random state')
    state = data['state']
    if (type(state) is not list or len(state) != 3 or type(state[0]) is not int or state[0] != 3
            or type(state[1]) is not list or len(state[1]) != 625
            or any(type(n) is not int or not 0 <= n <= 2**32 - 1 for n in state[1][:-1])
            or type(state[1][-1]) is not int or not 0 <= state[1][-1] <= 624
            or (state[2] is not None and (type(state[2]) is not float or not math.isfinite(state[2])))):
        raise ValueError('invalid V9 activity arbitration state')
    restored = (state[0], tuple(state[1]), state[2])
    probe = random.Random()
    probe.setstate(restored)
    random.setstate(restored)
