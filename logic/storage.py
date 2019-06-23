import os
import shelve


class Storage:
    """Класс работы с хранилищем"""

    BASE_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    FOLDER_PATH = os.path.join(BASE_PATH, 'db')
    STORAGE_PATH = os.path.join(FOLDER_PATH, 'storage')

    @classmethod
    def create_folder_path(cls):
        if not os.path.exists(cls.FOLDER_PATH):
            os.mkdir(cls.FOLDER_PATH)

    @classmethod
    def open(cls):
        with shelve.open(cls.STORAGE_PATH) as db:
            return dict(db.items())

    @classmethod
    def write(cls, data: dict, primary_key: str):
        with shelve.open(cls.STORAGE_PATH) as db:
            sector = db.setdefault(primary_key, {})
            sector.update(data)
            db[primary_key] = sector

    @classmethod
    def clear(cls, primary_key: str):
        with shelve.open(cls.STORAGE_PATH) as db:
            db[primary_key] = {}

    @classmethod
    def clear_all(cls):
        with shelve.open(cls.STORAGE_PATH) as db:
            db.clear()


class StatsStorage(Storage):
    """Класс работы с хранилищем статистики"""

    STORAGE_PATH = os.path.join(Storage.FOLDER_PATH, 'statistics')

    KEYS_MAP = dict(
        earned='Заработано денег',
        crafted='Наборов создано',
        sold_bundles='Наборов продано',
        gems_spend='Самоцветов потрачено',
    )

    @classmethod
    def inc_money_earned(cls, amount):
        cls._inc_and_write('earned', amount)

    @classmethod
    def inc_crafted_bundles(cls):
        cls._inc_and_write('crafted')

    @classmethod
    def inc_sold_bundles(cls):
        cls._inc_and_write('sold_bundles')

    @classmethod
    def inc_gems_spent(cls, amount):
        cls._inc_and_write('gems_spend', amount)

    @classmethod
    def show_stats(cls, logger=None):
        logger = logger or print
        storage = StatsStorage.open()
        map_data = [
            (v, storage.get(k, {}).get("value", 0))
            for k, v in StatsStorage.KEYS_MAP.items()
        ]
        for name, value in map_data:
            if name == cls.KEYS_MAP['earned']:
                value = f'{value / 100} руб.'
            logger(f'{name}: {value}')

    @classmethod
    def _inc_and_write(cls, primary_key: str, amount: int = None):
        sell_count = cls.open().get(primary_key, {}).get('value', 0)
        cls.write(dict(value=sell_count + (amount or 1)), primary_key)

