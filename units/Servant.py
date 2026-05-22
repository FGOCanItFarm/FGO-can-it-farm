from data import base_multipliers
from .stats import Stats
from .skills import Skills
from .buffs import Buffs
from .np import NP
from scripts.connectDB import db

import logging

# Configure logging
logging.basicConfig(filename='./outputs/output.log', level=logging.INFO,
                    format='%(asctime)s:%(levelname)s:%(message)s')

class Servant:
    special_servants = [312, 394, 391, 413, 385, 350, 306, 305]

    def __init__(self, collectionNo, np=1, initialCharge=0, attack=0, atkUp=0, artsUp=0, quickUp=0, busterUp=0, npUp=0, damageUp=0, busterDamageUp=0, quickDamageUp=0, artsDamageUp=0, append_5=False, version_spec=None):
        self.id = collectionNo
        raw_data = select_character(collectionNo)
        if raw_data is None:
            raise ValueError(f"Servant data for collectionNo {collectionNo} not found.")

        if version_spec is not None:
            from parsers.servant_parser import parse_servant_data
            self.data = parse_servant_data(raw_data, version_spec)
        else:
            self.data = raw_data

        self.name = self.data.get('name')
        self.class_name = self.data.get('className')
        self.class_id = self.data.get('classId')
        self.gender = self.data.get('gender')
        self.attribute = self.data.get('attribute')
        self.traits = [trait['id'] for trait in self.data.get('traits', [])]
        self.cards = self.data.get('cards', [])
        self.atk_growth = self.data.get('atkGrowth', [])
        self.skills = Skills(self.data.get('skills', []), append_5=append_5)
        self.np_level = np
        self.oc_level = 1
        self.nps = NP(self.data.get('noblePhantasms', []))
        self.rarity = self.data.get('rarity')
        self.np_gauge = initialCharge
        self.np_gain_mod = 1
        self.buffs = Buffs(self)
        self.stats = Stats(self)
        self.ce_attack = attack # TODO unused
        self.atk_mod = atkUp
        self.b_up = busterUp
        self.a_up = artsUp
        self.q_up = quickUp
        self.power_mod = {damageUp}
        self.np_damage_mod = 0
        self.card_type = self.nps.nps[0]['card'] #if self.nps.nps else None
        self.class_base_multiplier = 1 if self.id == 426 else base_multipliers[self.class_name]

        self.passives = self.buffs.parse_passive(self.data.get('classPassive', []))
        self.apply_passive_buffs()
        self.kill = False

        # Store user-inputted buffs separately
        self.user_atk_mod = atkUp
        self.user_b_up = busterUp
        self.user_a_up = artsUp
        self.user_q_up = quickUp
        self.user_np_damage_mod = npUp
        self.user_buster_damage_up = busterDamageUp
        self.user_quick_damage_up = quickDamageUp
        self.user_arts_damage_up = artsDamageUp

    def __repr__(self):
        return (
            f"Servant(name={self.name}, class_id={self.class_name}, attribute={self.attribute})\n"
            f"Buffs:\n{self.buffs.grouped_str()}"
        )
    

    def set_npgauge(self, value):
        
        if value == 0:
            logging.info(f"Setting NP GAUGE to 0 for {self.name}")
            self.np_gauge = 0
        else:
            logging.info(f"INCREASING NP GAUGE OF {self.name} TO {self.np_gauge + value}")
            self.np_gauge += value

    def get_npgauge(self):
        return self.np_gauge

    def apply_bonus_buffs(self):
        # Only apply if the value is nonzero
        if self.user_atk_mod:
            self.apply_buff({'buff_name': 'ATK Up', 'value': self.user_atk_mod, 'turns': -1, 'functvals': [], 'tvals': []})
        if self.user_b_up:
            self.apply_buff({'buff_name': 'Buster Up', 'value': self.user_b_up, 'turns': -1, 'functvals': [], 'tvals': []})
        if self.user_a_up:
            self.apply_buff({'buff_name': 'Arts Up', 'value': self.user_a_up, 'turns': -1, 'functvals': [], 'tvals': []})
        if self.user_q_up:
            self.apply_buff({'buff_name': 'Quick Up', 'value': self.user_q_up, 'turns': -1, 'functvals': [], 'tvals': []})
        if self.user_np_damage_mod:
            self.apply_buff({'buff_name': 'NP Strength Up', 'value': self.user_np_damage_mod, 'turns': -1, 'functvals': [], 'tvals': []})
        if self.user_buster_damage_up:
            self.apply_buff({'buff_name': 'Buster Card Damage Up', 'value': self.user_buster_damage_up, 'turns': -1, 'functvals': [], 'tvals': []})
        if self.user_quick_damage_up:
            self.apply_buff({'buff_name': 'Quick Card Damage Up', 'value': self.user_quick_damage_up, 'turns': -1, 'functvals': [], 'tvals': []})
        if self.user_arts_damage_up:
            self.apply_buff({'buff_name': 'Arts Card Damage Up', 'value': self.user_arts_damage_up, 'turns': -1, 'functvals': [], 'tvals': []})
          

    def apply_passive_buffs(self):
        for passive in self.passives:
            for func in passive['functions']:
                for buff in func['buffs']:
                    state = {
                        'buff_name': buff.get('name', 'Unknown'),
                        'value': func['svals'].get('Value', 0),
                        'turns': -1,  # Infinite duration
                        'functvals': func.get('functvals', [])
                    }
                    self.apply_buff(state)

    def apply_buff(self, state):
        buff = state['buff_name']
        value = state['value']
        functvals = state['functvals']
        tvals = [tval['id'] for tval in state.get('tvals', [])]
        turns = state['turns']

        self.buffs.add_buff({'buff': buff, 'functvals': functvals, 'value': value, 'tvals': tvals, 'turns': turns})

    def apply_ce_effects(self, ce_effects):
        for effect in ce_effects:
            state = {
                'buff_name': effect.get('name', 'Unknown'),
                'value': effect.get('value', 0),
                'turns': -1,  # Infinite duration
                'functvals': effect.get('functvals', [])
            }
            self.apply_buff(state)

    def __getstate__(self):
        state = self.__dict__.copy()
        # Remove database connection if present
        if 'data' in state and hasattr(state['data'], 'collection'):  # crude check for pymongo object
            state['data'] = None
        return state

def select_character(character_id):
    servant = db.servants.find_one({'collectionNo': character_id})
    return servant  # Ensure character_id is an integer
