"""
baseline_lookup.py

Turns the canonical consolidated table (data/baseline_rates.json) into a single
baseline-selection function that follows a fallback hierarchy, from most specific to
most general:

    1. disease + phase   (BIO/QLS Fig 2)   e.g. "Hematology, Phase II to III"
    2. modality          (BIO/QLS Fig 10b) e.g. "CAR-T"
    3. novelty class     (BIO/QLS Fig 9)   e.g. "Biosimilar"   <- added in Day 1 refactor
    4. all-indications   (BIO/QLS Fig 1)   the overall industry average (last resort)

Why a hierarchy? The report doesn't have a number for every possible combination. If
we don't have a disease-specific rate, the next best thing is a modality-specific rate;
then a novelty-class rate; and if we have none of those, the overall industry average
rather than failing.

Design notes:
    - The engine reads ONLY baseline_rates.json (single source of truth).
    - The default fallback chain uses ONLY BIO/QLS (2021) rows, which are phase-by-phase
      across four transitions. Wong (2019) rows also live in the table but use a different
      method (path-by-path) and a merged Phase-3->Approval step, so they are kept for
      cross-validation (Day 4) and deliberately excluded from the live chain.
    - Modifier categories (biomarker, rare_chronic, oncology_subtype) are present in the
      table but are NOT part of this chain; Day 2 turns them into likelihood ratios.
"""

from pos_engine import PHASE_KEYS, load_data

# The tiers of the fallback hierarchy, most specific first. Each entry pairs the
# keyword argument name of get() with the category_type it selects from the table.
_FALLBACK_TIERS = [
    ("disease", "disease_area", "disease+phase"),
    ("modality", "modality", "modality"),
    ("novelty", "novelty_class", "novelty_class"),
]


class BaselineLookup:
    """Loads the canonical baseline table once, then answers questions like
    "What's the Phase II to III success rate for Hematology?" using the fallback
    hierarchy."""

    def __init__(self, table_file="baseline_rates.json", source="BIO/QLS 2021"):
        self.source = source
        table = load_data(table_file)
        # Index BIO/QLS rows by (category_type, category, phase_transition) for O(1) lookup.
        self._index = {}
        for row in table["rows"]:
            if row["source"] != source:
                continue
            key = (row["category_type"], row["category"], row["phase_transition"])
            self._index[key] = row

    def _fetch(self, category_type, category, phase):
        return self._index.get((category_type, category, phase))

    def get(self, phase, disease=None, modality=None, novelty=None):
        """Return the best available baseline for ``phase`` using the fallback
        hierarchy.

        Returns a dict: {rate, n, source, source_ref, source_level, source_key}.
        ``phase`` must be one of PHASE_KEYS.
        """
        if phase not in PHASE_KEYS:
            raise ValueError(f"Unknown phase {phase!r}. Must be one of {PHASE_KEYS}")

        supplied = {"disease": disease, "modality": modality, "novelty": novelty}

        # Tiers 1-3: disease+phase -> modality -> novelty class.
        for arg_name, category_type, source_level in _FALLBACK_TIERS:
            value = supplied[arg_name]
            if not value:
                continue
            row = self._fetch(category_type, value, phase)
            if row:
                return self._result(row, source_level)

        # Tier 4: overall industry average, always available.
        row = self._fetch("all_indications", "all_indications", phase)
        if row is None:  # pragma: no cover - the all-indications row always exists
            raise LookupError(f"No all-indications baseline for phase {phase!r}")
        return self._result(row, "all_indication")

    @staticmethod
    def _result(row, source_level):
        return {
            "rate": row["rate"],
            "n": row["n"],
            "source": row["source"],
            "source_ref": row["source_ref"],
            "source_level": source_level,
            "source_key": row["category"],
        }


if __name__ == "__main__":
    # Quick manual check when running this file directly.
    lookup = BaselineLookup()

    print("Hematology, Phase II to III:")
    print(lookup.get("phase2_to_3", disease="Hematology"))

    print("\nUnknown disease, but CAR-T modality, Phase I to II:")
    print(lookup.get("phase1_to_2", disease="MadeUpDisease", modality="CAR-T"))

    print("\nUnknown disease/modality, but Biosimilar novelty, Phase I to II:")
    print(lookup.get("phase1_to_2", novelty="Biosimilar"))

    print("\nUnknown everything (falls all the way back):")
    print(lookup.get("phase1_to_2"))
