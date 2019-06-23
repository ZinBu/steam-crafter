import logging
import random
import re
from datetime import datetime
from time import sleep

import requests
from bs4 import BeautifulSoup
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta as t_delta
from urllib3.exceptions import ProtocolError

import settings
from cargo.utils import RequestsUtils, Commonly
from logic.storage import Storage, StatsStorage

# Настройки логгеров
error_logger = logging.getLogger("error_logger")
info_logger = logging.getLogger("info_logger")
sell_logger = logging.getLogger("sell_logger")

formatter = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')

st = logging.StreamHandler()
st.setFormatter(formatter)

er = logging.FileHandler("errors_log.txt")
er.setFormatter(formatter)

sl = logging.FileHandler("successful_sells.txt")
sl.setFormatter(logging.Formatter('%(asctime)s: %(message)s'))

info_logger.addHandler(st)
info_logger.setLevel(logging.INFO)

sell_logger.addHandler(sl)
sell_logger.setLevel(logging.INFO)

error_logger.addHandler(er)
# TODO
#  + автоматическая покупка мешков с самоцветами и их распоковка


class SteamUser:
    # Минимально допустимая маржа с продажи набора на мешок самоцветов
    MINIMAL_MARGIN = settings.MIN_MARGIN
    GOOD_B = 'GOOD_BUNDLE'
    BAD_B = 'BAD_BUNDLE'
    # Время актуальности данных о не рентабельных наборах (в часах).
    # Т.е. при актуализации эти бандлы будут просто пропущены, если не истекло
    # указанное время.
    BAD_B_ACTUAL_HOURS = 48
    SLEEP_TIME_MINUTES = 45
    # Максимальная цена крафта набора, которая учитывается при поиске
    # рентабельных наборов
    MAX_GEMS_PRICE = 700

    def __init__(self, cookies: str):
        # Подсунем сгенерированный хедер
        self.headers = RequestsUtils.get_random_header()
        # Конвертируем строку куков в словарь
        self.cookies = RequestsUtils.get_cookies_dict(cookies)
        # Загрузим страницу с карточками и сделаем инстанс BeautifulSoup
        self.bundle_page_soup = self.load_bundles_page()
        # Получим данные о доступных наборах для крафта и имя пользователя
        self._update_available_bundles(init=True)
        self._update_gems_amount()

    @classmethod
    def make_money(cls, cookie_string):
        """Стартует процесс создания и продажи карточек"""
        # Создадим папку под БД, если ее нет
        Storage.create_folder_path()
        # Отобразим настрйоки и статистику
        cls._show_setting()
        cls._pretty_info(
            'Очистка хранилища с рентабельными играми. '
            'Ведь какие-то таковыми могут уже и не быть'
        )
        Storage.clear(cls.GOOD_B)
        while True:
            try:
                # Стартуем всю логику софта
                cls._engage_process(cookie_string)
            except Exception as error:
                error_logger.error(Commonly.exception_detail_info(str(error)))
                # Штрафной сон
                sleep(60 * 5)

    @classmethod
    def _engage_process(cls, cookie_string):
        steam = cls(cookie_string)
        # Сначала нужно обновить ренатбельные наборы
        cls._pretty_info('Актуализируем рентабельность наборов...')
        steam.get_all_bundles_profitability()
        # Далее скрафтим доступные и рентабельные наборы
        cls._pretty_info('Скрафтим доступные и рентабельные наборы...')
        steam.create_card_available_bundles()
        # Далее, продадим созданные наборы и прочие,
        # которые можно продать по минималке
        cls._pretty_info('Продадим наборы...')
        steam.sell_exists_bundles()
        cls._pretty_info('Очистка хранилища с рентабельными играми.')
        Storage.clear(cls.GOOD_B)
        # Дальше уйдем в сон Одина
        cls._pretty_info('Поспим...')
        sleep(60 * cls.SLEEP_TIME_MINUTES)

    @classmethod
    def _show_setting(cls):
        info_logger.info('Блок статистики за все время ' + '+' * 30)
        StatsStorage.show_stats(info_logger.info)
        cls._pretty_info('+' * 40)
        info_logger.info('Блок настроек ' + '+' * 30)
        info_logger.info(
            f'Поиск наборов с минимальным доходом: '
            f'{cls.MINIMAL_MARGIN / 100} руб.'
        )
        cls._pretty_info('+' * 40)

    def create_card_bundle(self, appid, series=1, tradability_preference=2):
        """Создание набора карточек"""
        url = 'https://steamcommunity.com/tradingcards/ajaxcreatebooster'
        data = dict(
            sessionid=self.cookies['sessionid'],
            appid=appid,
            series=series,
            tradability_preference=tradability_preference
        )
        response = self._post(url=url, data=data)
        status_code = response.status_code
        purchase_result = response.json()['purchase_result']
        if status_code == 200 and purchase_result['success'] == 1:
            return True
        return False

    def get_dust_amount(self):
        """Получение количества самоцветов в интвентаре"""
        query = 'span', {'class': 'goovalue'}
        dust = self.bundle_page_soup.find(*query).contents[0].replace(',', '')
        return int(dust)

    def load_bundles_page(self):
        """Загрузка страницы с наборами карточек"""
        url = 'https://steamcommunity.com//tradingcards/boostercreator/'
        return BeautifulSoup(self._get(url).content, 'html.parser')

    def get_craft_bundles(self):
        """Получение списка доступных для крафта наборов дешевле 700 пыли"""
        # Получение тела скрипта, в котором сокрыты все данные
        # о доступных для создания наборах
        script = next(
            x for x in self.bundle_page_soup.find_all('script')
            if x.contents and 'CBoosterCreatorPage.Init' in x.contents[0]
        )
        # Достанем строку, в которой содержаться данные о набрах
        bundles_string = next(
            x for x in script.string.split('\r\n\t\t\t')
            if 'appid' in x and 'name' in x
        )
        # Преобразуем ее в список
        bundles = eval(
            bundles_string.replace('true', 'True').replace('false', 'False')
        )
        return {
            x['name']: x
            for x in bundles[0]
            if int(x['price']) < self.MAX_GEMS_PRICE
        }

    def create_card_available_bundles(self):
        """Создание рентабельных наборов карточек"""
        # Обновим данные о доступности наборов
        self._update_available_bundles()
        # Возьмем минимальную цену мешочка
        pouch_price, _ = self.get_gem_pouch_price()
        good_bundles = Storage.open().get(self.GOOD_B, {})
        # Сортировка от самого выгодного
        games = sorted(
            ((k, v) for k, v in good_bundles.items()),
            key=lambda x: x[1]['margin'],
            reverse=True
        )
        for game, g_data in games:
            bundle_info = self.available_bundles.get(game)
            # Проверка доступности набора для крафта
            if not bundle_info or bundle_info.get('unavailable'):
                info_logger.info(f"{game} не доступно для крафта еще!")
                continue
            # Проверка на наличие достаточного кол-ва самоцветов дял крафта
            if int(bundle_info['price']) > self.gems_amount:
                info_logger.info(
                    f'Недостаточно гемов для крафта {game}. '
                    f'Стоимость {bundle_info["price"]}. '
                    f'Всего гемов: {self.gems_amount}'
                )
                continue
            # Проверим рентабельность покупки на данный момент
            if not self.get_bundle_profitability(bundle_info, pouch_price):
                continue
            # Если набор карточек готов к созданию - сделаем это!!!
            is_success = self.create_card_bundle(
                appid=bundle_info['appid'],
                series=bundle_info['series']
            )
            # Обновим данные
            self._update_gems_amount()
            info_logger.info(
                f"{game} "
                f"{'крафт удался' if is_success else 'крафт провалился'}. "
                f"Навар {g_data['profit']} руб. на 1000 гемов."
            )
            if is_success:
                sell_logger.info(
                    f"{game} крафт удался. "
                    f"Навар {g_data['profit']} руб. на 1000 гемов."
                )
                # Обновим статистику
                StatsStorage.inc_crafted_bundles()
                StatsStorage.inc_gems_spent(int(bundle_info["price"]))

    def get_all_bundles_profitability(self):
        """Получение только рентабельных наборов"""
        # Возьмем минимальную цену мешочка
        _, pouch_price = self.get_gem_pouch_price()
        # Подгрузим нерентабельные наборы
        bad_bundles = Storage.open().get(self.BAD_B, {})
        bundles_count = len(self.available_bundles)
        info_logger.info(f"Наборов предстоит проверить: {bundles_count}")

        for num, bundle in enumerate(self.available_bundles.values(), start=1):
            # Если не известно время последнего получения
            # данных о рентабельности
            last_updated = bad_bundles.get(bundle['name'], {}).get('updated')
            info_logger.info(f"Проверяется: {num}/{bundles_count}")
            if last_updated:
                # Время последнего обновления набора и текущее время
                last_updated, dtn = parse(last_updated), datetime.now()
                # Если время обновления не устарело, то пропустим
                if dtn < last_updated + t_delta(hours=self.BAD_B_ACTUAL_HOURS):
                    continue
            self.get_bundle_profitability(bundle, pouch_price)

    def get_bundle_profitability(self, bundle, pouch_price, retry=True):
        """Получение рентабельности набора"""
        try:
            sell_price, buy_price = self.get_bundle_price_range(bundle['name'])
            # Поспим чуток от микробана подальше
            sleep(random.randint(1, 4))
            # Если нет ценника продажи, значит набор никто не продает, а это
            # значит, что его продавать нельзя
            # (способ не надежный, но пока что есть то есть)
            if not sell_price:
                # Прихроним информацию о нерентабельном наборе
                self._write_bundle_info(bundle, -1000, self.BAD_B)
                return
        except Exception:
            # Если возникла ошибка, запустим еще раз спустя время
            # с флагом, которой не запустит в случае ошибки повторно
            # во избежании рекурсии
            if retry:
                sleep(1.5)
                info_logger.info(f"{bundle}: перезапуск запроса!!!!!!!")
                self.get_bundle_profitability(bundle, pouch_price, retry=False)
            return
        # Если нет лотов на покупку, то сразу пропускаем
        if not buy_price:
            return
        # Наборов карточек получится с одного мешочка
        bundles_count = 1000 / int(bundle['price'])
        # С реализации одного мешка пыли этим набором получится
        income_per_pouch = round(bundles_count * buy_price)
        # Маржа набора
        margin = income_per_pouch - pouch_price
        # Если она положительная и больше минимальной маржи - добавим игру
        if margin and margin > self.MINIMAL_MARGIN:
            info_logger.info(
                f"ОТЛИЧНЫЙ НАБОР: {bundle['name']} ({margin / 100} руб.)"
            )
            # Хороший набор добавим в хранилище
            self._write_bundle_info(bundle, margin, self.GOOD_B)
            return {bundle['name']: (margin / 100)}
        # Прихроним информацию о нерентабельном наборе
        self._write_bundle_info(bundle, margin, self.BAD_B)

    def get_gem_pouch_price(self):
        """Цена мешка самоцветов (1000 гемов)"""
        url = 'https://steamcommunity.com/market/itemordershistogram'
        params = dict(
            country='RU',
            language='russian',
            currency=5,
            item_nameid=26463978,
            two_factor=0
        )
        response = self._get(url, params).json()
        return self._get_prices(response)

    def get_bundle_price_range(self, name):
        """
        Получение минимальной цены продажи набора
        :return (цена по котрой продают, цена по которой покупают)
        """
        url = 'https://steamcommunity.com/market/search'
        params = dict(q=f'{name} Booster Pack')
        soup = BeautifulSoup(self._get(url, params).content, 'html.parser')
        # Найдем среди списка карточек нужную
        search_class = (
            "market_listing_row "
            "market_recent_listing_row "
            "market_listing_searchresult"
        )
        items = soup.find_all('div', {"class": search_class})
        if not items:
            return None, None
        item = (
            next(x.attrs for x in items if name in x.attrs['data-hash-name'])
        )
        # Сформируем URL для поиска минимальной цены
        base_url = 'https://steamcommunity.com/market/listings'
        url = f"{base_url}/{item['data-appid']}/{item['data-hash-name']}"
        soup = BeautifulSoup(self._get(url).content, 'html.parser')
        script = next(
            x.contents[0] for x in soup.find_all('script') if
            x.contents and 'Market_LoadOrderSpread' in x.contents[0]
        )
        wanted_row = next(
            x for x in script.string.split('\r\n\t\t')
            if 'Market_LoadOrderSpread' in x
        )
        item_id = (
            wanted_row.lstrip('Market_LoadOrderSpread(').split(')')[0].strip()
        )
        # Запрорс для получения ценника
        url = 'https://steamcommunity.com/market/itemordershistogram'
        params = dict(
            country='RU',
            language='russian',
            currency=5,
            item_nameid=item_id,
            two_factor=0
        )
        response = self._get(url, params).json()
        return self._get_prices(response)

    def sell_exists_bundles(self):
        """Продажа всех имеющитхся бандлов в инвенторе"""
        # Необохдимо предотвратить продажу наборов,
        # которые остутсвуют в списке рентабельных
        good_bundles = Storage.open().get(self.GOOD_B)
        if not good_bundles:
            info_logger.info('Необнаружено рентабельлных наборов для продажи')
            return

        cards_bundles = self.get_inventory_cards()
        for bundle in cards_bundles:
            pure_name = bundle['name'].replace('Booster Pack', '').strip()
            if pure_name not in good_bundles:
                info_logger.info(
                    f'Набор {bundle["name"]} отсутсвует в рентабельных. '
                    f'Пропускаем!'
                )
                continue
            # Уточним цену на момент продажи
            _, price = self.get_bundle_price_range(
                bundle['name'].strip('Booster Pack')
            )
            response = self._sell_bundle_card(bundle, price)
            if response['success']:
                msg = (
                    f'Набор {bundle["name"]} выставлен за {price / 100} руб.!'
                )
                sell_logger.info(msg)
                # Обновление статистики
                # Заработано
                earned = round(
                    good_bundles[pure_name]['margin']
                    / (1000 / int(good_bundles[pure_name]['gems_price']))
                )
                StatsStorage.inc_money_earned(earned)
                StatsStorage.inc_sold_bundles()
            else:
                msg = f'Ошибка выставления набора {bundle["name"]}. {response}'
                error_logger.error(msg)

            info_logger.info(msg)

    def get_inventory_cards(self):
        """Получение идентификаторов наборов карт из инвенторя"""
        app_id, steam_id = self._get_inventory_identifiers()
        url = (
            f'https://steamcommunity.com/inventory/'
            f'{steam_id}/{app_id}/6'
        )
        response = self._get(url).json()
        assets = {
            (x['classid'], x['instanceid']): x for x in response['assets']
        }
        cards = [
            # Объеденим инфомацию о наборе в ассетами
            {**x, **assets[(x['classid'], x['instanceid'])]}
            for x in response['descriptions']
            # Интересуют только наборы, которые можно продать
            if x['type'] == 'Booster Pack' and x['marketable']
        ]
        return cards

    def _sell_bundle_card(self, bundle, price):
        """Выставление на продажу набора карт"""
        url = 'https://steamcommunity.com/market/sellitem/'
        data = dict(
            sessionid=self.cookies['sessionid'],
            appid=bundle['appid'],
            contextid=bundle['contextid'],
            assetid=bundle['assetid'],
            amount=1,
            # Цену необходимо указать ту, которая будет получена
            # с учетем комиссии стима (13 %)
            price=round(price - price * .13)
        )
        response = self._post(url=url, data=data, referer=True).json()
        return response

    def _get_inventory_identifiers(self):
        """Получение инвенаря Steam"""
        url = f'https://steamcommunity.com/id/{self.username}/inventory/'
        soup = BeautifulSoup(self._get(url).content, 'html.parser')
        items = soup.find('select', {'id': 'responsive_inventory_select'})
        steam_identifiers = next(
            x.attrs
            for x in items.contents
            if hasattr(x, 'contents') and 'Steam' in x.contents[0]
        )
        app_id = steam_identifiers['data-appid']
        script = next(
            x.contents[0]
            for x in soup.find_all('script')
            if x.contents and 'UserYou.SetSteamId' in x.contents[0]
        )
        wanted_row = next(
            x for x in script.string.split(';')
            if 'UserYou.SetSteamId' in x
        )
        steam_id = re.search(r'\d+', wanted_row).group()
        return app_id, steam_id

    def _get(self, url, params=None):
        """Базовый метод для GET-запросов"""
        sleep(random.randint(1, 2))
        try:
            return requests.get(
                url=url,
                params=params,
                cookies=self.cookies,
                headers=self.headers
            )
        except ProtocolError as error:
            error_logger.error(f'{error}. Data: {params}')
            sleep(6)
            return requests.get(
                url=url,
                params=params,
                cookies=self.cookies,
                headers=self.headers
            )

    def _post(self, url, data=None, referer=False):
        """Базовый метод для POST-запросов"""
        # Необходимо изменить хэдер для этого запроса
        sleep(random.randint(1, 3))
        headers = dict(**self.headers)
        content_type = 'application/x-www-form-urlencoded; charset=UTF-8'
        headers['Content-Type'] = content_type
        # Если есть заголовок refer
        if referer:
            r_url = f'https://steamcommunity.com/id/{self.username}/inventory/'
            headers['Referer'] = r_url
        try:
            return requests.post(
                url=url,
                data=data,
                headers=headers,
                cookies=self.cookies
            )
        except ProtocolError as error:
            error_logger.error(f'{error}. Data: {data}')
            sleep(6)
            return requests.post(
                url=url,
                data=data,
                headers=headers,
                cookies=self.cookies
            )

    def _update_available_bundles(self, init=False):
        """Обновление данных о доступных наборах для крафта"""
        try:
            self.available_bundles = self.get_craft_bundles()
        except StopIteration:
            error_logger.error(
                'ОШИБКА: кажется сессия устарела! Нужна новая Кука!'
            )

        # Получим имя пользователя
        if init:
            query = 'a', {'class': 'menuitem supernav username'}
            anchor = self.bundle_page_soup.find(*query)
            url_elements = anchor.attrs['href'].split('/')
            for num, elem in enumerate(url_elements):
                if elem == 'id':
                    self.username = url_elements[num + 1]
                    break

    def _update_gems_amount(self):
        """Обновление данных о колчестве имеющихся гемов"""
        self.bundle_page_soup = self.load_bundles_page()
        self.gems_amount = self.get_dust_amount()
        info_logger.info(f'Самоцветов доступно: {self.gems_amount}')

    @staticmethod
    def _get_prices(obj):
        """Получим цену покупки и продажи из результата"""
        sell_price = obj['lowest_sell_order']
        buy_price = obj['highest_buy_order']
        return (
            int(sell_price) if sell_price else None,
            int(buy_price) if buy_price else None
        )

    @staticmethod
    def _write_bundle_info(bundle, margin, primary_key):
        """Запись информации о наборе в БД"""
        Storage.write(
            primary_key=primary_key,
            data={
                bundle['name']: dict(
                    profit=(margin / 100),
                    margin=margin,
                    gems_price=bundle['price'],
                    updated=datetime.now().isoformat()
                )
            }
        )

    @staticmethod
    def _pretty_info(msg):
        info_logger.info(msg)
        info_logger.info('')
