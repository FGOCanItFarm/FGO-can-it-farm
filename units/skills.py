class Skills:
    def __init__(self, skills_data, append_5, mystic_code=None):
        self.skills = self.parse_skills(skills_data)
        self.cooldowns = {1: 0, 2: 0, 3: 0}
        self.max_cooldowns = self.initialize_max_cooldowns()
        self.cooldown_reduction_applied = {1: False, 2: False, 3: False}
        self.mystic_code = mystic_code
        self.melusine_skill = False
        self.append_5 = append_5

    @staticmethod
    def _safe_sval(svals_raw, default=None):
        """Return the max-level (index 9) sval dict from a raw svals list.
        Falls back to last entry when fewer than 10 entries exist.
        Returns default ({}) for non-list or empty input."""
        if default is None:
            default = {}
        if not isinstance(svals_raw, list) or not svals_raw:
            return default
        entry = svals_raw[9] if len(svals_raw) > 9 else svals_raw[-1]
        return entry if isinstance(entry, dict) else default

    def parse_skills(self, skills_data):
        skills = {1: [], 2: [], 3: []}
        for skill in skills_data:
            cooldown_list = skill.get('coolDown', [])
            if isinstance(cooldown_list, list) and cooldown_list:
                cooldown = cooldown_list[9] if len(cooldown_list) > 9 else cooldown_list[-1]
            else:
                cooldown = 0
            parsed_skill = {
                'id': skill.get('id'),
                'name': skill.get('name'),
                'cooldown': cooldown,
                'functions': []
            }
            for function in skill.get('functions', []):
                sval = self._safe_sval(function.get('svals'))
                parsed_function = {
                    'funcType': function.get('funcType'),
                    'funcTargetType': function.get('funcTargetType'),
                    'functvals': function.get('functvals'),
                    'fieldReq': function.get('funcquestTvals', []),
                    'condTarget': function.get('functvals', []),
                    'svals': sval,
                    'buffs': []
                }
                for buff in function.get('buffs', []):
                    buff_sval = self._safe_sval(buff.get('svals'))
                    parsed_buff = {
                        'name': buff.get('name'),
                        'tvals': buff.get('tvals', []),
                        'svals': buff_sval if buff_sval else None,
                        'value': buff_sval.get('Value', 0) if buff_sval else 0
                    }
                    parsed_function['buffs'].append(parsed_buff)
                parsed_skill['functions'].append(parsed_function)
            skills[int(skill['num'])].append(parsed_skill)
        return skills

    def initialize_max_cooldowns(self):
        max_cooldowns = {}
        for i in range(1, len(self.skills) + 1):
            max_cooldowns[i] = self.skills[i][-1]['cooldown']
        return max_cooldowns

    def get_skill_by_num(self, num):
        if 1 <= num < len(self.skills) + 1:
            if self.melusine_skill == False and self.skills[num][0]['id'] == 888550:
                self.melusine_skill = True
                return self.skills[num][0]
            else:
                return self.skills[num][-1]
        else:
            raise IndexError(f"Skill number {num} is out of range")

    def __iter__(self):
        return iter(self.skills)

    def get_skill_names(self):
        return [skill['name'] for skill in self.skills]

    def get_skill_cooldowns(self):
        return self.cooldowns

    def decrement_cooldowns(self, turns: int):
        for skill_num in self.cooldowns:
            if self.cooldowns[skill_num] > 0:
                self.cooldowns[skill_num] = max(0, self.cooldowns[skill_num] - turns)

    def skill_available(self, skill_num):
        return self.cooldowns[skill_num] == 0

    def set_skill_cooldown(self, skill_num):
        if not self.cooldown_reduction_applied[skill_num] and self.append_5:
            self.cooldowns[skill_num] = self.max_cooldowns[skill_num] - 1
            self.cooldown_reduction_applied[skill_num] = True
        else:
            self.cooldowns[skill_num] = self.max_cooldowns[skill_num]

    def __repr__(self):
        return f"Skills(skills={self.skills}, cooldowns={self.cooldowns}, max_cooldowns={self.max_cooldowns}, cooldown_reduction_applied={self.cooldown_reduction_applied})"
