import pprint
from scripts.connectDB import get_cursor


class MysticCode:
    def __init__(self, mc_id):
        self.mc_id = mc_id
        self.data = self.load_mystic_code(mc_id)
        self.name = self.data.get('name', '')
        self.short_name = self.data.get('shortName', '')
        self.detail = self.data.get('detail', '')
        self.max_lv = self.data.get('maxLv', 10)
        self.skills = self.parse_skills(self.data.get('skills', []))
        self.cooldowns = {i: 0 for i in range(3)}

    def load_mystic_code(self, mc_id):
        with get_cursor() as cur:
            cur.execute('SELECT data FROM public.mystic_codes WHERE id = %s', (mc_id,))
            row = cur.fetchone()
        if not row:
            raise ValueError(f'Mystic Code with id {mc_id} not found in the database.')
        return row['data']

    def parse_skills(self, skills_data):
        skills = []
        for skill in skills_data:
            parsed_skill = {
                'id':       skill.get('id'),
                'num':      skill.get('num'),
                'name':     skill.get('name'),
                'detail':   skill.get('detail'),
                'cooldown': skill.get('coolDown', [0])[-1],
                'functions': [],
                'icon':     skill.get('icon', ''),
            }
            for func in skill.get('functions', []):
                svals = func.get('svals', [])
                if isinstance(svals, list) and svals:
                    svals = svals[-1]
                elif not isinstance(svals, dict):
                    svals = {}
                parsed_func = dict(func)
                parsed_func['svals'] = svals
                parsed_skill['functions'].append(parsed_func)
            skills.append(parsed_skill)
        return skills

    def get_skill_by_num(self, num):
        return self.skills[num]

    def set_cooldown(self, skill_num):
        skill = self.get_skill_by_num(skill_num)
        self.cooldowns[skill_num] = skill['cooldown']

    def decrement_cooldowns(self):
        for k in self.cooldowns:
            if self.cooldowns[k] > 0:
                self.cooldowns[k] -= 1

    def __repr__(self):
        lines = [
            f"MysticCode(name='{self.name}', short_name='{self.short_name}', max_lv={self.max_lv})",
            f'Detail: {self.detail}',
            'Skills (full data):',
        ]
        pp = pprint.PrettyPrinter(indent=2, width=120, compact=False)
        for idx, skill in enumerate(self.skills):
            lines.append(f'Skill {idx + 1}:')
            lines.append(pp.pformat(skill))
        return '\n'.join(lines)
