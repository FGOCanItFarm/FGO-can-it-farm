from .Quest import Quest
from units.Servant import Servant
from .MysticCode import MysticCode
import copy
import logging

logging.basicConfig(filename='./outputs/output.log', level=logging.INFO,
                    format='%(asctime)s:%(levelname)s:%(message)s')

class GameManager:
    def __init__(self, servant_init_dicts, quest_id, mc_id, gm_copy=None, damage_multiplier=1.0):
        self.servant_init_dicts = servant_init_dicts
        self.quest_id = quest_id
        self.mc_id = mc_id
        self.damage_multiplier = damage_multiplier
        self.servants = [Servant(**params) for params in self.servant_init_dicts]
        self.mc = MysticCode(mc_id)
        self.fields = []
        self.quest = None
        self.wave = 1
        self.total_waves = 0
        self.enemies = []
        self.wave_stats = {}
        self.quest_cleared = False
        self.servants_at_wave_end = {}
        self.init_quest()
        if any(servant['collectionNo'] == 413 for servant in servant_init_dicts):
            self.saoko = Servant(collectionNo=4132)

    def reset_servants(self):
        self.servants = [Servant(**params) for params in self.servant_init_dicts]

    def add_field(self, state):
        name = state.get('field_name', 'Unknown')
        turns = state.get('turns', 0)
        self.fields.append([name, turns])

    def reset(self):
        self.reset_servants()
        self.fields = []

    def swap_servants(self, frontline_idx, backline_idx):
        self.servants[frontline_idx], self.servants[backline_idx] = self.servants[backline_idx], self.servants[frontline_idx]

    def transform_aoko(self, aoko_buffs, aoko_cooldowns, aoko_np_gauge=None):
        print("What? \nAoko is transforming!")
        servants_list = [servant.name for servant in self.servants]
        logging.info(f"servants are: {servants_list}")
        for i, servant in enumerate(self.servants):
            if servant.id == 413:
                transformed = Servant(collectionNo=4132)
                transformed.buffs.buffs = copy.deepcopy(aoko_buffs)
                transformed.skills.cooldowns = copy.deepcopy(aoko_cooldowns)
                if aoko_np_gauge is not None:
                    transformed.np_gauge = aoko_np_gauge
                self.servants[i] = transformed
                print(f"Contratulations! Your 'Aoko Aozaki' transformed into '{transformed.name}' ")
        servants_list = [servant.name for servant in self.servants]
        logging.info(f"servants are: {servants_list}")

    def _record_initial_wave_hp(self):
        wave = self.wave
        if wave not in self.wave_stats:
            self.wave_stats[wave] = {'hp_required': 0.0, 'damage_at_11': 0.0}
        self.wave_stats[wave]['hp_required'] = sum(
            getattr(enemy, 'max_hp', 0) for enemy in self.enemies
        )

    def record_np_damage(self, wave, damage):
        if wave not in self.wave_stats:
            self.wave_stats[wave] = {'hp_required': 0.0, 'damage_at_11': 0.0}
        self.wave_stats[wave]['damage_at_11'] += damage

    def capture_servants_at_wave_end(self, wave):
        self.servants_at_wave_end[str(wave)] = [
            {
                'slot': i,
                'collectionNo': getattr(s, 'id', None),
                'np_gauge': round(getattr(s, 'np_gauge', 0), 1)
            }
            for i, s in enumerate(self.servants[:3])
        ]

    def init_quest(self):
        self.quest = Quest(self.quest_id)
        self.total_waves = self.quest.total_waves
        self.enemies = self.quest.get_wave(self.wave)
        self._record_initial_wave_hp()

    def get_next_wave(self):
        self.wave += 1
        if self.wave > self.total_waves:
            logging.info("All waves completed.")
            return
        try:
            next_wave = self.quest.get_wave(self.wave)
            self.enemies = next_wave
            self._record_initial_wave_hp()
            print(f"Advancing to wave {self.wave}")
        except StopIteration:
            logging.info("No more waves available.")

    def get_enemies(self):
        return self.enemies

    def __getstate__(self):
        state = self.__dict__.copy()
        if 'mc' in state and hasattr(state['mc'], '__dict__'):
            mc_state = state['mc'].__dict__.copy()
            if 'db' in mc_state:
                mc_state['db'] = None
            state['mc'].__dict__ = mc_state
        if 'quest' in state and hasattr(state['quest'], '__dict__'):
            quest_state = state['quest'].__dict__.copy()
            if 'db' in quest_state:
                quest_state['db'] = None
            state['quest'].__dict__ = quest_state
        return state
