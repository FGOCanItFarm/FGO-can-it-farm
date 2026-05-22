from units.Enemy import Enemy
from scripts.connectDB import get_cursor


class Quest:
    def __init__(self, quest_id):
        self.quest_id = quest_id
        self.fields = []
        self.waves = {}
        self.total_waves = 0
        self.current_wave_index = 1
        self.retrieve_quest()

    def retrieve_quest(self):
        with get_cursor() as cur:
            cur.execute('SELECT data FROM public.quests WHERE id = %s', (self.quest_id,))
            row = cur.fetchone()
        if row:
            self.process_quest(row['data'])

    def process_quest(self, document):
        waves = document['stages']
        for field in document['individuality']:
            self.fields.append(field['id'])
        for i, wave in enumerate(waves):
            wave_data = []
            for enemy in wave['enemies']:
                enemydata = [
                    enemy['name'],
                    enemy['hp'],
                    enemy['deathRate'],
                    enemy['svt']['className'],
                    [trait['id'] for trait in enemy['svt']['traits']],
                    enemy['svt']['attribute'],
                    enemy.get('state'),
                ]
                wave_data.append(Enemy(enemydata))
            self.waves[i + 1] = wave_data
        self.total_waves = len(self.waves)

    def get_wave(self, wave_no=0):
        if wave_no == 0:
            return self.waves
        return self.waves.get(wave_no, [])
