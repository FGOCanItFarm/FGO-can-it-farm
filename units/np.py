class NP:
    def __init__(self, nps_data):
        self.nps = self.parse_noble_phantasms(nps_data)
        self.card = self.nps[-1]['card'] if self.nps else None

    def parse_noble_phantasms(self, nps_data):
        if not nps_data:
            return []
        sorted_nps = sorted(nps_data, key=lambda np: np.get('id', 0))
        for i, np in enumerate(sorted_nps):
            np['new_id'] = i + 1
        return sorted_nps

    def get_np_by_id(self, new_id=None):
        if new_id is None:
            return self.nps[-1]
        for np in self.nps:
            if np['new_id'] == new_id:
                return np
        raise ValueError(f"No NP found with new_id {new_id}")

    @staticmethod
    def _safe_sval_at_level(func, oc, np_level):
        """Get sval dict at np_level from the appropriate OC svals list.
        Falls back from svals{oc} to svals when the OC key is missing.
        Guards against lists shorter than np_level."""
        key = f'svals{oc}' if oc > 1 else 'svals'
        svals_list = func.get(key) or func.get('svals') or []
        if not isinstance(svals_list, list) or not svals_list:
            return {}
        idx = min(max(np_level - 1, 0), len(svals_list) - 1)
        entry = svals_list[idx]
        return entry if isinstance(entry, dict) else {}

    def get_np_values(self, np_level=1, overcharge_level=1, new_id=None):
        np = self.get_np_by_id(new_id)
        result = []
        for func in np['functions']:
            svals_key = f'svals{overcharge_level}' if overcharge_level > 1 else 'svals'
            svals_list = func.get(svals_key) or func.get('svals') or []
            if isinstance(svals_list, list) and svals_list:
                idx = min(max(np_level - 1, 0), len(svals_list) - 1)
                entry = svals_list[idx]
                func_values = entry if isinstance(entry, dict) else {}
            else:
                func_values = {}

            buffs = [
                {
                    'name': buff.get('name'),
                    'functvals': buff.get('functvals', ''),
                    'tvals': buff.get('tvals', []),
                    'svals': buff.get('svals', [None])[9] if len(buff.get('svals', [])) > 9 else None,
                    'value': buff.get('svals', [{}])[9].get('Value', 0) if len(buff.get('svals', [])) > 9 else 0,
                    'turns': buff.get('svals', [{}])[9].get('Turn', 0) if len(buff.get('svals', [])) > 9 else 0
                }
                for buff in func.get('buffs', [])
            ]

            result.append({
                'funcType': func['funcType'],
                'funcTargetType': func['funcTargetType'],
                'functvals': func.get('functvals', []),
                'fieldReq': func.get('fieldReq', []),
                'condTarget': func.get('condTarget', []),
                'svals': func_values,
                'buffs': buffs
            })

        return result

    def get_np_damage_values(self, oc=1, np_level=1, new_id=None):
        np = self.get_np_by_id(new_id)

        for func in np['functions']:
            if func['funcType'] in ['damageNp', 'damageNpPierce']:
                sval = self._safe_sval_at_level(func, oc, np_level)
                return sval.get('Value', 0) / 1000, None, None, None, None

            elif func['funcType'] in ['damageNpIndividual', 'damageNpStateIndividualFix']:
                sval = self._safe_sval_at_level(func, 1, np_level)
                np_damage = sval.get('Value', 0)
                np_correction_target = sval.get('Target', 0)
                np_correction = sval.get('Correction', 0)
                return np_damage / 1000, None, np_correction / 1000, None, np_correction_target

            elif func['funcType'] == 'damageNpIndividualSum':
                sval = self._safe_sval_at_level(func, 1, np_level)
                np_damage = sval.get('Value', 0)
                np_damage_correction_init = sval.get('Value2', 0)
                np_correction = sval.get('Correction', 0)
                np_correction_target = sval.get('Target', 0)
                np_correction_id = sval.get('TargetList', 0)
                return np_damage / 1000, np_damage_correction_init / 1000, np_correction / 1000, np_correction_id, np_correction_target

        return 0, None, None, None, None

    def get_npgain(self, card_type, new_id=None):
        np = self.get_np_by_id(new_id)
        np_gain = np.get('npGain', {}).get(card_type, [0])[0]
        return np_gain / 100

    def get_npdist(self, new_id=None):
        np = self.get_np_by_id(new_id)
        return np.get('npDistribution', [])
