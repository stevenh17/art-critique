import json

import numpy as np
import pytest

from artcrit.critic import CritiqueRun
from artcrit.critique_schema import parse_critique
from artcrit.outcomes import OutcomeRow
from artcrit.store.images import ImageStore
from artcrit.store.sessions import SessionStore

CRIT = json.dumps({"issues": [
    {"category": "proportion", "title": "Jaw too long", "instruction": "Shorten the chin.", "drawing_cells": ["C7"], "photo_cells": ["C6"]},
    {"category": "values", "title": "Shadow light", "instruction": "Darken it.", "drawing_cells": ["B3"], "photo_cells": ["B3"]}]})
C = ((0, 0), (1, 0), (1, 1), (0, 1))


class World:
    def __init__(self, tmp_path):
        self.store = SessionStore(tmp_path / "s.db")
        self.images = ImageStore(tmp_path / "img")
        self.tmp = tmp_path

    def img(self, value, shape=(300, 200, 3)):
        return np.full(shape, value, np.uint8)

    def drawing(self, publish=True, url="https://unsplash.com/p", license="Unsplash", crit=CRIT, versions=1, done=True):
        photo = self.images.save(self.img(120, (400, 600, 3)), "photo")
        d = self.store.add_drawing(photo, (0.1, 0.1, 0.9, 0.9), url, license, publish)
        parent, sids = None, []
        for v in range(1, versions + 1):
            s = self.store.add_submission(d, v, parent, f"original/o{v}.png", self.images.save(self.img(200 + v), "drawing"), C)
            self.store.add_critique(s, CritiqueRun(parse_critique(crit), [{"tool": "zoom", "input": {}}], "claude-x", "sha123"))
            self.store.add_status(s, "done" if done else "failed", "" if done else "secret detail")
            parent = s
            sids.append(s)
        return d, sids


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


def outcome(store, issue_id, sid, final="fixed", source="geometry:outline"):
    store.add_outcome(OutcomeRow(issue_id, sid, "partly", "private reason", "{}", final, source, True))
