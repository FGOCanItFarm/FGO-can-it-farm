import requests
import json
import os
import time
import logging
from datetime import datetime, timezone
from pymongo import MongoClient
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(filename='script.log', level=logging.INFO, format='%(asctime)s:%(levelname)s:%(message)s')

# Load environment variables from .env file
load_dotenv()

# Adjust logging level for pymongo to suppress debug messages
logging.getLogger('pymongo').setLevel(logging.WARNING)

# MongoDB connection
mongo_uri = os.getenv('MONGO_URI')
if not mongo_uri:
    raise ValueError("No MONGO_URI environment variable set")

client = MongoClient(mongo_uri)
db = client['FGOCanItFarmDatabase']
servants_collection = db['servants']
quests_collection = db['quests']
mysticcode_collection = db['mysticcodes']
metadata_collection = db['metadata']


def fetch_with_backoff(url, retries=3):
    """Fetch a URL with exponential backoff. Returns parsed JSON or None on failure."""
    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                try:
                    return response.json()
                except json.JSONDecodeError as e:
                    logging.error(f"JSONDecodeError for {url}: {e}")
                    return None
            else:
                logging.error(f"HTTP {response.status_code} for {url}")
        except requests.RequestException as e:
            logging.error(f"RequestException for {url}: {e}")
        if attempt < retries - 1:
            time.sleep(2 ** attempt)  # 1s, 2s, 4s
    return None


def update_jp_hash():
    """Fetch AA /info and store the JP game hash in metadata."""
    data = fetch_with_backoff('https://api.atlasacademy.io/info')
    if data is None:
        logging.error("Failed to fetch AA /info")
        return None
    jp_hash = data.get('JP', {}).get('hash', '')
    metadata_collection.update_one(
        {'_id': 'aa_version'},
        {'$set': {'jp_hash': jp_hash, 'updated_at': datetime.now(timezone.utc)}},
        upsert=True
    )
    logging.info(f"Stored JP hash: {jp_hash}")
    return jp_hash


def retrieve_servants(progress_callback=None):
    """Auto-discover servants from basic_servant.json and update only changed ones."""
    basic_data = fetch_with_backoff('https://api.atlasacademy.io/export/JP/basic_servant.json')
    if basic_data is None:
        logging.error("Failed to fetch basic_servant.json")
        return 0, 0

    servants_checked = 0
    servants_updated = 0

    for entry in basic_data:
        collection_no = entry.get('collectionNo')
        aa_hash = entry.get('hash', '')
        if not collection_no:
            continue

        servants_checked += 1

        # Compare hash against stored document
        existing = servants_collection.find_one({'collectionNo': collection_no}, {'_aa_data_hash': 1})
        if existing and existing.get('_aa_data_hash') == aa_hash:
            logging.info(f"Servant {collection_no} unchanged (hash match), skipping")
            continue

        # Fetch full nice data
        url = f'https://api.atlasacademy.io/nice/JP/servant/{collection_no}?lore=true&expand=true&lang=en'
        servant_data = fetch_with_backoff(url)
        if servant_data is None:
            logging.error(f"Failed to fetch servant {collection_no}")
            time.sleep(0.5)
            continue

        servant_data['_aa_data_hash'] = aa_hash
        servants_collection.update_one(
            {'collectionNo': collection_no},
            {'$set': servant_data},
            upsert=True
        )
        servants_updated += 1
        logging.info(f"Upserted servant {collection_no}")

        if progress_callback:
            progress_callback('servant', collection_no)

        time.sleep(0.5)

    return servants_checked, servants_updated


def get_quest_ids_from_war(war_id):
    """Fetch a war and return qualifying quest IDs."""
    url = f'https://api.atlasacademy.io/nice/JP/war/{war_id}?lang=en'
    data = fetch_with_backoff(url)
    if data is None:
        return []
    quest_ids = []
    for spot in data.get('spots', []):
        for quest in spot.get('quests', []):
            recommend_lv = quest.get('recommendLv', '')
            consume = quest.get('consume', 0)
            after_clear = quest.get('afterClear', '')
            if recommend_lv in ['90', '90+', '90++', '90★', '90★★'] and consume == 40 and after_clear == 'repeatLast':
                quest_ids.append(quest.get('id'))
    return quest_ids


def upsert_quest(data):
    quest_id = data.get('id')
    stages = data.get('stages', [])
    if quest_id and stages and 'enemies' in stages[0] and len(stages[0]['enemies']) > 0:
        quests_collection.update_one({'id': quest_id}, {'$set': data}, upsert=True)
        logging.info(f"Upserted quest {quest_id}")
        return True
    else:
        logging.error(f"Quest data missing 'id' or stages[0].enemies is empty for quest ID: {quest_id}")
        return False


def retrieve_quests(progress_callback=None):
    """Auto-discover wars from basic_war.json and upsert all matching quests."""
    basic_wars = fetch_with_backoff('https://api.atlasacademy.io/export/JP/basic_war.json')
    if basic_wars is None:
        logging.error("Failed to fetch basic_war.json")
        return 0

    # Keep wars that are eventQuest or permanent
    valid_wars = [
        w for w in basic_wars
        if w.get('type') in ('eventQuest', 'permanent')
    ]
    logging.info(f"Found {len(valid_wars)} valid wars out of {len(basic_wars)}")

    all_quest_ids = []
    for war in valid_wars:
        war_id = war.get('id')
        if war_id is None:
            continue
        quest_ids = get_quest_ids_from_war(war_id)
        all_quest_ids.extend(quest_ids)
        time.sleep(0.3)

    quests_updated = 0
    for quest_id in all_quest_ids:
        url = f'https://api.atlasacademy.io/nice/JP/quest/{quest_id}/1?lang=en'
        data = fetch_with_backoff(url)
        if data is None:
            logging.error(f"Failed to fetch quest {quest_id}")
            time.sleep(0.3)
            continue
        if upsert_quest(data):
            quests_updated += 1
            if progress_callback:
                progress_callback('quest', quest_id)
        time.sleep(0.3)

    return quests_updated


def retrieve_mystic_codes(progress_callback=None):
    """Auto-discover mystic codes from basic_mystic_code.json and update only changed ones."""
    basic_data = fetch_with_backoff('https://api.atlasacademy.io/export/JP/basic_mystic_code.json')
    if basic_data is None:
        logging.error("Failed to fetch basic_mystic_code.json")
        return 0

    mc_updated = 0
    for entry in basic_data:
        mc_id = entry.get('id')
        aa_hash = entry.get('hash', '')
        if mc_id is None:
            continue

        existing = mysticcode_collection.find_one({'id': mc_id}, {'_aa_data_hash': 1})
        if existing and existing.get('_aa_data_hash') == aa_hash:
            logging.info(f"Mystic code {mc_id} unchanged (hash match), skipping")
            continue

        url = f'https://api.atlasacademy.io/nice/JP/MC/{mc_id}?lang=en'
        mc_data = fetch_with_backoff(url)
        if mc_data is None:
            logging.error(f"Failed to fetch mystic code {mc_id}")
            time.sleep(0.3)
            continue

        mc_data['_aa_data_hash'] = aa_hash
        mysticcode_collection.update_one(
            {'id': mc_id},
            {'$set': mc_data},
            upsert=True
        )
        mc_updated += 1
        logging.info(f"Upserted mystic code {mc_id}")

        if progress_callback:
            progress_callback('mystic_code', mc_id)

        time.sleep(0.3)

    return mc_updated


def run_update(progress_callback=None):
    """Run the full update flow and return a summary dict."""
    start_time = time.monotonic()

    new_jp_hash = update_jp_hash() or ''

    servants_checked, servants_updated = retrieve_servants(progress_callback=progress_callback)
    quests_updated = retrieve_quests(progress_callback=progress_callback)
    mc_updated = retrieve_mystic_codes(progress_callback=progress_callback)

    duration = time.monotonic() - start_time

    summary = {
        'servants_checked': servants_checked,
        'servants_updated': servants_updated,
        'quests_updated': quests_updated,
        'mystic_codes_updated': mc_updated,
        'new_jp_hash': new_jp_hash,
        'duration_seconds': round(duration, 2),
    }
    logging.info(f"Update complete: {summary}")
    return summary


if __name__ == '__main__':
    result = run_update()
    print(json.dumps(result, indent=2))
