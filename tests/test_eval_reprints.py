"""Hand-checkable ranking examples for the reprint evaluator."""

import importlib.util
from pathlib import Path


path = Path(__file__).resolve().parent.parent / "scripts/evaluation/eval_reprints.py"
spec = importlib.util.spec_from_file_location("eval_reprints", path)
evaluator = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(evaluator)


def test_recall_counts_all_other_family_members():
    class Vectors:
        def __contains__(self, member):
            return True

        def most_similar(self, member, topn):
            return [(other, 1.0) for other in "ABCD" if other != member][:topn]

    result = evaluator.evaluate(Vectors(), [{"members": list("ABCD")}])
    # Every query finds one of three relevant members at rank 1.
    assert result["recall"][1] == 1 / 3
