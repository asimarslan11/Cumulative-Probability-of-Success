"""
registry.py

Resolves a drug / vaccine **name** into the engine's `Asset` inputs.

This module exists because of a hard limitation worth stating plainly: the project's two
sources (BIO/QLS 2021, Wong 2019) are **aggregate statistics and contain no per-drug rows
whatsoever**. Nothing in the published data can tell you what phase Drug X is in, what its
modality is, or whether it has breakthrough designation. So a name on its own is not enough
to compute a probability of success -- it has to be resolved against attributes that a human
asserted.

`data/drug_registry.json` holds those assertions, each carrying `_source` and `_as_of`. The
split matters for how much you trust the output:

    * the engine's *statistics* trace to published figures (that invariant is intact);
    * a named program's *attributes* are declared inputs, and a wrong `current_phase`
      moves the answer more than any modelling choice in the engine.

Unknown names fail loudly rather than falling back to an industry average, because a generic
7.9% presented under a drug's name reads as a drug-specific finding when it is nothing of the
sort.
"""

from pos_engine import load_data

REGISTRY_FILE = "drug_registry.json"

# Keys in a registry entry that are provenance, not Asset fields.
_PROVENANCE_KEYS = ("_source", "_as_of")


class UnknownAssetError(KeyError):
    """Raised when a name has no registry entry and no attributes were supplied."""

    def __str__(self):
        # KeyError's repr quotes the message; give the plain text.
        return self.args[0] if self.args else ""


def load_registry(registry_file=REGISTRY_FILE):
    """Load the raw registry document (``_meta`` + ``assets``)."""
    return load_data(registry_file)


def known_names(registry_file=REGISTRY_FILE):
    """Every name the registry can resolve, in sorted order."""
    return sorted(load_registry(registry_file)["assets"])


def resolve(name, overrides=None, registry_file=REGISTRY_FILE):
    """Resolve ``name`` into ``(asset_kwargs, provenance)``.

    Matching is case-insensitive and whitespace-tolerant. ``overrides`` (a dict of Asset
    fields) is merged on top of the registry entry, so a caller can correct a stale phase
    or assess a program that isn't registered at all.

    Raises :class:`UnknownAssetError` when the name is unregistered *and* the overrides
    don't at least supply ``current_phase`` -- without it there is no asset to score.
    """
    overrides = {k: v for k, v in (overrides or {}).items() if v is not None}
    registry = load_registry(registry_file)
    assets = registry["assets"]

    key = _match(name, assets)
    if key is None:
        if "current_phase" not in overrides:
            raise UnknownAssetError(
                f"{name!r} is not in the registry, and no attributes were supplied.\n"
                f"The sources contain no per-drug data, so a name alone cannot be scored.\n"
                f"Either add an entry to data/{registry_file}, or pass the attributes "
                f"directly (at minimum --phase).\n"
                f"Known names: {', '.join(sorted(assets)) or '(none)'}"
            )
        # Ad-hoc, caller-supplied asset. Provenance says exactly that.
        return dict(overrides), {
            "_source": "supplied by the caller at run time (not from the registry)",
            "_as_of": None,
            "registered": False,
            "resolved_name": name,
        }

    entry = assets[key]
    asset_kwargs = {k: v for k, v in entry.items() if k not in _PROVENANCE_KEYS}
    provenance = {
        "_source": entry.get("_source"),
        "_as_of": entry.get("_as_of"),
        "registered": True,
        "resolved_name": key,
    }
    if overrides:
        asset_kwargs.update(overrides)
        provenance["overridden_fields"] = sorted(overrides)
    return asset_kwargs, provenance


def _match(name, assets):
    """Case-insensitive / whitespace-tolerant lookup; returns the real key or None."""
    def norm(s):
        return " ".join(str(s).strip().split()).lower()

    target = norm(name)
    for key in assets:
        if norm(key) == target:
            return key
    return None


__all__ = ["resolve", "load_registry", "known_names", "UnknownAssetError", "REGISTRY_FILE"]
