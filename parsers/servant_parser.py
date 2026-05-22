from dataclasses import dataclass
from typing import Optional


@dataclass
class ServantVersionSpec:
    """Specifies which skill/NP upgrade and ascension level to use when
    resolving a servant's data from a raw Atlas Academy document.

    Upgrade index semantics (applies to skill1/2/3_upgrade and np_upgrade):
      -1  take the last entry  (latest, fully-strengthened)  [default]
       0  take the first entry (base, pre-buff)
       n  take the n-th entry  (0-based), clamped to list length
    """
    ascension: int = 4
    skill1_upgrade: int = -1
    skill2_upgrade: int = -1
    skill3_upgrade: int = -1
    np_upgrade: int = -1


# ---------------------------------------------------------------------------
# svals normalisation
# ---------------------------------------------------------------------------

def _pad_svals(svals_raw, length: int = 10):
    """Return svals_raw padded to exactly `length` entries.

    If svals_raw is not a list or is empty it is returned unchanged so that
    callers which store non-list values (dicts, None, …) are not broken.
    """
    if not isinstance(svals_raw, list) or not svals_raw:
        return svals_raw
    if len(svals_raw) >= length:
        return list(svals_raw[:length])
    padded = list(svals_raw)
    while len(padded) < length:
        padded.append(padded[-1])
    return padded


def _normalize_function_svals(func: dict) -> dict:
    """Return a copy of func with all svals/svals{n} and buff.svals padded."""
    func = dict(func)
    for key in list(func.keys()):
        if key == 'svals' or (key.startswith('svals') and key[5:].isdigit()):
            func[key] = _pad_svals(func[key])
    if 'buffs' in func and isinstance(func['buffs'], list):
        normalized_buffs = []
        for buff in func['buffs']:
            buff = dict(buff)
            if 'svals' in buff:
                buff['svals'] = _pad_svals(buff['svals'])
            normalized_buffs.append(buff)
        func['buffs'] = normalized_buffs
    return func


# ---------------------------------------------------------------------------
# per-section resolvers
# ---------------------------------------------------------------------------

def _resolve_skills(skills_data: list, spec: ServantVersionSpec) -> list:
    """Select one skill entry per slot (num 1/2/3) according to the spec.

    Atlas Academy stores every upgrade variant of a skill in the flat skills
    list, each carrying a `num` field (1/2/3) that identifies the slot.
    The entries are ordered from oldest to newest so index -1 is always the
    latest version.  The caller can pin an older version via the upgrade index.

    Returns a list with one normalised entry per slot in ascending num order.
    """
    by_num: dict = {}
    for skill in skills_data:
        num = skill.get('num')
        if num is None:
            continue
        by_num.setdefault(int(num), []).append(skill)

    upgrade_map = {
        1: spec.skill1_upgrade,
        2: spec.skill2_upgrade,
        3: spec.skill3_upgrade,
    }

    result = []
    for num in sorted(by_num.keys()):
        entries = by_num[num]
        idx = upgrade_map.get(num, -1)
        if idx == -1 or idx >= len(entries):
            chosen = entries[-1]
        elif idx <= 0:
            chosen = entries[0]
        else:
            chosen = entries[min(idx, len(entries) - 1)]

        chosen = dict(chosen)
        if 'coolDown' in chosen:
            chosen['coolDown'] = _pad_svals(chosen['coolDown'])
        if 'functions' in chosen and isinstance(chosen['functions'], list):
            chosen['functions'] = [_normalize_function_svals(f) for f in chosen['functions']]
        result.append(chosen)

    return result


def _resolve_np(nps_data: list, spec: ServantVersionSpec) -> list:
    """Select one NP entry from the noblePhantasms list according to the spec.

    Returns a single-element list so the result is a valid drop-in for
    raw_data['noblePhantasms'] fed into NP.__init__.
    """
    if not nps_data:
        return []
    sorted_nps = sorted(nps_data, key=lambda np: np.get('id', 0))
    idx = spec.np_upgrade
    if idx == -1 or idx >= len(sorted_nps):
        chosen = sorted_nps[-1]
    elif idx <= 0:
        chosen = sorted_nps[0]
    else:
        chosen = sorted_nps[min(idx, len(sorted_nps) - 1)]

    chosen = dict(chosen)
    if 'functions' in chosen and isinstance(chosen['functions'], list):
        chosen['functions'] = [_normalize_function_svals(f) for f in chosen['functions']]
    return [chosen]


def _resolve_passives(raw_data: dict, ascension: int) -> list:
    """Return the effective classPassive list for the given ascension level.

    Atlas Academy stores passive overrides in
      ascensionAdd.overwriteClassPassive
    which can be either:
      - a dict keyed directly by ascension number string (flat format)
      - a nested dict with an 'ascension' sub-key (standard nice format)

    The highest threshold key whose value is <= ascension wins; if no key
    applies the base classPassive list is returned unchanged.
    """
    base_passives = list(raw_data.get('classPassive', []))
    container = raw_data.get('ascensionAdd', {}).get('overwriteClassPassive', {})
    if not container:
        return base_passives

    # Handle both nested {"ascension": {"1": [...]}} and flat {"1": [...]} forms
    if 'ascension' in container and isinstance(container['ascension'], dict):
        overwrite_map = container['ascension']
    else:
        overwrite_map = container

    applicable = [
        (int(k), v)
        for k, v in overwrite_map.items()
        if str(k).isdigit() and int(k) <= ascension
    ]
    if not applicable:
        return base_passives

    applicable.sort(key=lambda t: t[0])
    _, overwrite_passives = applicable[-1]
    return list(overwrite_passives)


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------

def parse_servant_data(
    raw_data: dict,
    spec: Optional[ServantVersionSpec] = None,
) -> dict:
    """Resolve skill/NP versions and normalise svals in a raw AA servant doc.

    Returns a shallow-patched copy of raw_data with:
      - 'skills'          one entry per slot, selected by spec upgrade index
      - 'noblePhantasms'  one entry, selected by spec np_upgrade index
      - 'classPassive'    merged with ascensionAdd overrides for spec.ascension
      - all svals lists padded to exactly 10 entries

    The returned dict is a drop-in for Servant.__init__'s self.data, so
    downstream Skills / NP / Buffs constructors receive clean, index-safe data
    without needing their own length-guard boilerplate.
    """
    if spec is None:
        spec = ServantVersionSpec()

    result = dict(raw_data)
    result['skills'] = _resolve_skills(raw_data.get('skills', []), spec)
    result['noblePhantasms'] = _resolve_np(raw_data.get('noblePhantasms', []), spec)
    result['classPassive'] = _resolve_passives(raw_data, spec.ascension)
    return result
