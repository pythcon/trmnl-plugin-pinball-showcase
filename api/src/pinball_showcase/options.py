"""Catalogue of filter values for the ``/api/v1/options`` endpoint.

``plugin/bin/sync-options`` builds the plugin's dropdowns from it, so keep each list in a
stable order (not by count) and ``value`` exactly what the filters accept."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .dataset import Dataset
from .presenter import DISPLAY_LABELS
from .selection import ERA_LABELS, FEATURES, MULTI_EDITION, Rotation, title_era, title_features


def filter_options(dataset: Dataset) -> dict[str, Any]:
    titles = dataset.showcase_titles
    eras = Counter(title_era(t) for t in titles)
    decades = Counter(t.year // 10 * 10 for t in titles if t.year)
    makers = Counter(t.manufacturer for t in titles if t.manufacturer)
    displays = Counter(t.representative.display for t in titles if t.representative.display)
    players = Counter(t.representative.players for t in titles if t.representative.players)
    features = Counter(f for t in titles for f in title_features(t))
    feature_labels = {**FEATURES, MULTI_EDITION: "Released in multiple editions"}

    return {
        "rotation": [r.value for r in Rotation],
        "era": [
            {"value": e.value, "label": ERA_LABELS[e], "titles": eras.get(e, 0)} for e in ERA_LABELS
        ],
        "decade": [{"value": d, "label": f"{d}s", "titles": n} for d, n in sorted(decades.items())],
        "manufacturer": [
            {"value": m.lower(), "label": m, "titles": makers[m]}
            for m in sorted(makers, key=str.casefold)
        ],
        "display": [
            {"value": d, "label": DISPLAY_LABELS.get(d, d), "titles": displays[d]}
            for d in [*DISPLAY_LABELS, *sorted(displays.keys() - DISPLAY_LABELS.keys())]
            if displays[d]
        ],
        "players": [
            {"value": p, "label": f"{p} player{'s' if p != 1 else ''}", "titles": n}
            for p, n in sorted(players.items())
        ],
        "feature": [
            {"value": f, "label": feature_labels[f], "titles": features.get(f, 0)}
            for f in feature_labels
        ],
        "total_titles": len(titles),
    }
