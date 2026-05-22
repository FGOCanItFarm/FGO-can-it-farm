import logging

# Configure logging
logging.basicConfig(filename='./outputs/output.log', level=logging.INFO,
                    format='%(asctime)s:%(levelname)s:%(message)s')

magic_bullet_buff = {'buff': 'Magic Bullet', 'functvals': [], 'value': 9999, 'tvals': [], 'turns': -1}

class Buffs:
    def __init__(self, servant=None, enemy=None):
        if servant:
            self.servant = servant
            self.buffs = []
        if enemy:
            self.enemy = enemy
            self.buffs = []

    def process_end_turn_skills(self):
        add_magic_bullets = False
        logging.info(f"PROCESSING END TURN SKILLS")
        for i, buff in enumerate(self.buffs):
            if buff['buff'] == 'NP Gain Each Turn':
                self.servant.set_npgauge(buff['value'])
            if buff['buff'] == 'Delayed Effect (Death)':
                self.servant.kill = True
            if self.servant.name == 'Super Aoko':
                add_magic_bullets = True

        if add_magic_bullets == True:
            self.add_buff(magic_bullet_buff)
            self.add_buff(magic_bullet_buff)

    def process_enemy_buffs(self):
        # Reset modifiers
        self.enemy.defense = 0
        self.enemy.b_resdown = 0
        self.enemy.a_resdown = 0
        self.enemy.q_resdown = 0
        self.enemy.roman = self.enemy.traits.count(2004)
        for buff in self.buffs:
            if buff['buff'] == 'DEF Down':
                self.enemy.defense -= buff['value'] / 1000
            elif buff['buff'] == 'Buster Card Resist Down':
                self.enemy.b_resdown -= buff['value'] / 1000
            elif buff['buff'] == 'Arts Card Resist Down':
                self.enemy.a_resdown -= buff['value'] / 1000
            elif buff['buff'] == 'Quick Card Resist Down':
                self.enemy.q_resdown -= buff['value'] / 1000
            elif buff['buff'] == 'Apply Trait (Rome)':
                self.enemy.traits.append(2004)

    def process_servant_buffs(self):
        # Reset modifiers
        self.servant.atk_mod = self.servant.user_atk_mod
        self.servant.b_up = self.servant.user_b_up
        self.servant.a_up = self.servant.user_a_up
        self.servant.q_up = self.servant.user_q_up
        self.servant.power_mod = {}
        self.servant.np_damage_mod = self.servant.user_np_damage_mod
        self.servant.oc_level = 1
        self.servant.np_gain_mod = 1
        self.servant.buster_card_damage_up = self.servant.user_buster_damage_up
        self.servant.arts_card_damage_up = self.servant.user_arts_damage_up
        self.servant.quick_card_damage_up = self.servant.user_quick_damage_up

        boost_np_strength_up_active = False

        for buff in self.buffs:
            required_field = buff.get('script', {}).get('INDIVIDUALITIE', {}).get('id')
            if required_field is None:
                required_field = buff.get('originalScript', {}).get('INDIVIDUALITIE')
            if required_field is None or (required_field in self.servant.fields):
                if buff['buff'] == 'NP Strength Up' or buff['buff'] == 'upNpdamage':
                    self.servant.np_damage_mod += buff['value'] / 1000
                elif buff['buff'] == 'Boost NP Strength Up':
                    boost_np_strength_up_active = True

        if boost_np_strength_up_active:
            self.servant.np_damage_mod *= 2

        for buff in self.buffs:
            required_field = buff.get('script', {}).get('INDIVIDUALITIE', {}).get('id')
            if required_field is None:
                required_field = buff.get('originalScript', {}).get('INDIVIDUALITIE')
            if required_field is None or (required_field in self.servant.fields):
                if buff['buff'] == 'ATK Up':
                    self.servant.atk_mod += buff['value'] / 1000
                elif buff['buff'] == 'Buster Up':
                    self.servant.b_up += buff['value'] / 1000
                elif buff['buff'] == 'Arts Up':
                    self.servant.a_up += buff['value'] / 1000
                elif buff['buff'] == 'Quick Up':
                    self.servant.q_up += buff['value'] / 1000
                elif buff['buff'] == 'Power Up':
                    self.servant.power_mod += buff['value'] / 1000
                elif buff['buff'] in ['NP Overcharge Level Up', 'Overcharge Lv. Up']:
                    self.servant.oc_level = min(self.servant.oc_level + buff['value'], 5)
                elif "STR Up" in buff["buff"] or "Strength Up" in buff["buff"]:
                    for tval in buff['tvals']:
                        if tval not in self.servant.power_mod:
                            self.servant.power_mod[tval] = 0
                        self.servant.power_mod[tval] += buff.get("value", 0)
                elif 'Triggers Each Turn (Increase NP)' in buff['buff'] or 'Triggers Each Turn (NP Absorb)' in buff['buff']:
                    self.servant.np_gauge += buff['value']
                elif buff['buff'] == 'NP Gain Up':
                    self.servant.np_gain_mod += buff['value'] / 1000
                elif buff['buff'] == 'Buster Card Damage Up':
                    self.servant.buster_card_damage_up += buff['value'] / 1000
                elif buff['buff'] == 'Arts Card Damage Up':
                    self.servant.arts_card_damage_up += buff['value'] / 1000
                elif buff['buff'] == 'Quick Card Damage Up':
                    self.servant.quick_card_damage_up += buff['value'] / 1000

    def parse_passive(self, passives_data):
        passives = []
        for passive in passives_data:
            parsed_passive = {
                'id': passive.get('id'),
                'name': passive.get('name'),
                'functions': self.parse_passive_functions(passive.get('functions', []))
            }
            passives.append(parsed_passive)
        return passives

    def parse_passive_functions(self, functions_data):
        functions = []
        for func in functions_data:
            svals_raw = func.get('svals')
            if isinstance(svals_raw, list) and svals_raw and isinstance(svals_raw[0], dict):
                sval = svals_raw[0]
            else:
                sval = {}
            parsed_function = {
                'funcType': func.get('funcType'),
                'funcTargetType': func.get('funcTargetType'),
                'functvals': func.get('functvals', []),
                'svals': sval,
                'buffs': func.get('buffs', [])
            }
            functions.append(parsed_function)
        return functions

    def add_buff(self, buff: dict):
        self.buffs.append(buff)

    def remove_buff(self, buff: dict):
        for i, b in enumerate(self.buffs):
            if buff == b:
                self.buffs.pop(i)

    def decrement_buffs(self):
        for buff in self.buffs[:]:
            if buff['turns'] > 0:
                buff['turns'] -= 1
            if buff['turns'] == 0:
                self.buffs.remove(buff)

    def clear_buff(self, str):
        self.buffs = [i for i in self.buffs if i['buff'] != str]

    def grouped_str(self):
        from collections import defaultdict
        grouped = defaultdict(list)
        for buff in self.buffs:
            name = buff.get('buff', 'Unknown')
            value = buff.get('value', 0)
            turns = buff.get('turns', -1)
            grouped[name].append((value, turns))
        lines = []
        for name, vals in grouped.items():
            val_str = ', '.join([f"value={v/1000 if v else v}, turns={t}" for v, t in vals])
            lines.append(f"{name}: [{val_str}]")
        return "\n".join(lines) if lines else "No active buffs"

    def __repr__(self):
        return self.grouped_str()
