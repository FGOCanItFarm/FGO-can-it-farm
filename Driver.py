from managers.turn_manager import TurnManager
from managers.skill_manager import SkillManager
from managers.game_manager import GameManager
from managers.np_manager import npManager
from managers.Quest import Quest
from units.Servant import Servant
from units.Enemy import Enemy
import logging
import re

logging.basicConfig(filename='./outputs/output.log', level=logging.INFO,
                    format='%(asctime)s:%(levelname)s:%(message)s')

class Driver:
    def __init__(self, servant_init_dicts, quest_id, mc_id=260, damage_multiplier=1.0):
        self.servant_init_dicts = servant_init_dicts
        self.quest_id = quest_id
        self.mc_id = mc_id
        self.damage_multiplier = damage_multiplier
        self.turn_manager = None
        self.skill_manager = None
        self.np_manager = None
        self.game_manager = GameManager(
            self.servant_init_dicts,
            quest_id=self.quest_id,
            mc_id=self.mc_id,
            damage_multiplier=self.damage_multiplier
        )
        self.all_tokens = []

    def reset_state(self):
        self.game_manager = GameManager(
            self.servant_init_dicts,
            self.quest_id,
            self.mc_id,
            damage_multiplier=self.damage_multiplier
        )
        self.turn_manager = TurnManager(game_manager=self.game_manager)
        self.skill_manager = SkillManager(turn_manager=self.turn_manager)
        self.np_manager = npManager(skill_manager=self.skill_manager)

    def decrement_cooldowns(self):
        for servant in self.game_manager.servants:
            for i in range(len(servant.skills.cooldowns)):
                if servant.skills.cooldowns[i] > 0:
                    servant.skills.cooldowns[i] -= 1

    def execute_token(self, token):
        token_actions = {}

        skill_letters = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i']
        for idx, letter in enumerate(skill_letters):
            servant_idx = idx // 3
            skill_idx = idx % 3
            token_actions[letter] = lambda s=servant_idx, sk=skill_idx: self.skill_manager.use_skill(self.game_manager.servants[s], sk)
            for t in range(3):
                token_actions[f"{letter}{t+1}"] = lambda s=servant_idx, sk=skill_idx, tgt=t: self.skill_manager.use_skill(self.game_manager.servants[s], sk, self.game_manager.servants[tgt])

        for idx, letter in enumerate(['j', 'k', 'l']):
            token_actions[letter] = lambda i=idx: self.skill_manager.use_mystic_code_skill(i)
            for t in range(3):
                token_actions[f"{letter}{t+1}"] = lambda i=idx, tgt=t: self.skill_manager.use_mystic_code_skill(i, self.game_manager.servants[tgt])

        for i in range(1, 4):
            for j in range(1, 4):
                token_actions[f"x{i}{j}"] = lambda a=i, b=j: self.skill_manager.swap_servants(a, b)
        token_actions['x'] = lambda: self.skill_manager.swap_servants()

        for idx, np_token in enumerate(['4', '5', '6']):
            token_actions[np_token] = lambda i=idx: self.np_manager.use_np(self.game_manager.servants[i])

        token_actions['#'] = lambda: self.turn_manager.end_turn()

        match = re.match(r"([a-i])\[Ch(\d+)([A-C])\]", token)
        if match:
            skill_map = {l: (i // 3, i % 3) for i, l in enumerate(skill_letters)}
            s_letter, choice_num, choice_letter = match.groups()
            servant_idx, skill_idx = skill_map[s_letter]
            choice_idx = ord(choice_letter) - ord('A')
            return self.skill_manager.use_skill(
                self.game_manager.servants[servant_idx],
                skill_idx,
                choice=(int(choice_num), choice_idx)
            )

        match = re.match(r"([a-i])\(\[Ch(\d+)([A-C])\](\d)\)", token)
        if match:
            skill_map = {l: (i // 3, i % 3) for i, l in enumerate(skill_letters)}
            s_letter, choice_num, choice_letter, target_idx = match.groups()
            servant_idx, skill_idx = skill_map[s_letter]
            choice_idx = ord(choice_letter) - ord('A')
            target_idx = int(target_idx) - 1
            return self.skill_manager.use_skill(
                self.game_manager.servants[servant_idx],
                skill_idx,
                self.game_manager.servants[target_idx],
                choice=(int(choice_num), choice_idx)
            )

        action = token_actions.get(token)
        if action:
            print(f"Executing TOKEN: {token}")
            logging.info(f"Executing TOKEN: {token}")
            retval = action()
            if retval is False:
                return False
        else:
            logging.info(f"Invalid token: {token}")
        return self.game_manager

    def copy(self):
        import copy
        return copy.deepcopy(self)

    def get_all_possible_actions(self):
        return ['#']

    def apply_action(self, action):
        return
