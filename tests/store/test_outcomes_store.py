from artcrit.outcomes import OutcomeRow

from .test_sessions import RUN, _submission
from .test_sessions import store  # noqa: F401  (fixture)


def _row(issue_id, sid, final):
    return OutcomeRow(issue_id, sid, "fixed", "r", "{}", final, "judge", False)


def test_outcomes_latest_row_per_issue_wins(store):  # noqa: F811
    d, s1 = _submission(store)
    ids = store.add_critique(s1, RUN)
    s2 = store.add_submission(d, 2, s1, "o", "n", ((0, 0), (1, 0), (1, 1), (0, 1)))
    store.add_outcome(_row(ids[0], s2, "partly"))
    store.add_outcome(_row(ids[0], s2, "fixed"))
    store.add_outcome(_row(ids[1], s2, "not_fixed"))
    out = store.outcomes_for(s2)
    assert [(o.number, o.title, o.final_verdict) for o in out] == [(1, "Jaw too long", "fixed"), (2, "Shadow light", "not_fixed")]


def test_revision_metrics_roundtrip(store):  # noqa: F811
    d, s1 = _submission(store)
    assert store.revision_metrics(s1) is None
    store.add_revision_metrics(s1, 0.08, 0.05)
    assert store.revision_metrics(s1) == (0.08, 0.05)
