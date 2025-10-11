from ..utils.paths import PATHS


def test_paths_experiments_exists():
    p = PATHS.experiments
    assert p.name == "experiments"


