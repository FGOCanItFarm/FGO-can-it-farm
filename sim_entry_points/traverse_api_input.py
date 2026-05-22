import os
import logging
from dotenv import load_dotenv
from pymongo import MongoClient
from Driver import Driver

logging.basicConfig(filename='./outputs/traverse_api_input.log', level=logging.INFO,
                    format='%(asctime)s:%(levelname)s:%(message)s')

load_dotenv()

mongo_uri = os.getenv('MONGO_URI_READ')
if not mongo_uri:
    raise ValueError("No MONGO_URI_READ environment variable set")

client = MongoClient(mongo_uri)
db = client['FGOCanItFarmDatabase']

DAMAGE_MULTIPLIER = 1.1


def _compute_wave_stats(wave_stats):
    waves = {}
    for wave_num, data in wave_stats.items():
        damage_at_11 = data.get('damage_at_11', 0.0)
        hp_required = data.get('hp_required', 0.0)

        base = damage_at_11 / DAMAGE_MULTIPLIER if damage_at_11 > 0 else 0.0
        damage_at_10 = base
        damage_at_09 = base * 0.9

        if base > 0 and hp_required > 0:
            min_mult = hp_required / base
        elif hp_required == 0:
            min_mult = 0.0
        else:
            min_mult = 999.0

        clear_prob = max(0.0, min(1.0, (1.1 - min_mult) / 0.2))
        overkill_ratio_10 = damage_at_10 / hp_required if hp_required > 0 else 0.0

        if min_mult <= 0.9:
            outcome = 'guaranteed'
        elif min_mult >= 1.1:
            outcome = 'impossible'
        else:
            outcome = 'rng'

        waves[str(wave_num)] = {
            'hp_required': hp_required,
            'damage_at_09': damage_at_09,
            'damage_at_10': damage_at_10,
            'damage_at_11': damage_at_11,
            'overkill_ratio_10': overkill_ratio_10,
            'min_multiplier_needed': min_mult,
            'clear_probability': clear_prob,
            'outcome': outcome,
        }
    return waves


def traverse_api_input(servant_init_dicts, mc_id, quest_id, commands):
    try:
        servant_init_dicts = [s for s in servant_init_dicts if s.get('collectionNo')]
        driver = Driver(servant_init_dicts, quest_id, mc_id, damage_multiplier=DAMAGE_MULTIPLIER)
        driver.reset_state()

        failed_tokens = []
        first_failed_token = None
        first_failed_index = None

        for i, command in enumerate(commands):
            try:
                result = driver.execute_token(command)
                if result is False:
                    if first_failed_token is None:
                        first_failed_token = command
                        first_failed_index = i
                    failed_tokens.append(command)
                    logging.warning(f"Token '{command}' at index {i} returned False (skipping)")
            except Exception as e:
                if first_failed_token is None:
                    first_failed_token = command
                    first_failed_index = i
                failed_tokens.append(command)
                logging.error(f"Token '{command}' at index {i} raised: {e}")

        gm = driver.game_manager
        wave_stats = _compute_wave_stats(gm.wave_stats)

        overall_prob = 1.0
        for wave_data in wave_stats.values():
            overall_prob *= wave_data['clear_probability']

        logging.info("Commands executed successfully.")
        return {
            'success': True,
            'quest_cleared': gm.quest_cleared,
            'wave_reached': gm.wave,
            'total_waves': gm.total_waves,
            'stats': {
                'waves': wave_stats,
                'overall_clear_probability': overall_prob,
            },
            'servants_at_wave_end': gm.servants_at_wave_end,
            'failed_token_count': len(failed_tokens),
            'first_failed_token': first_failed_token,
            'first_failed_index': first_failed_index,
        }

    except Exception as e:
        logging.error(f"Simulation error: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'quest_cleared': False,
            'wave_reached': 0,
            'total_waves': 0,
            'stats': {'waves': {}, 'overall_clear_probability': 0.0},
            'servants_at_wave_end': {},
            'failed_token_count': 0,
            'first_failed_token': None,
            'first_failed_index': None,
        }
