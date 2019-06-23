""" Сборник классов с общими методами для разных нужд """
import multiprocessing
import os
import pickle
import random
import sys
import threading
import traceback


class Commonly:
    """
    Часто используемые методы или методы без категории
    """

    @staticmethod
    def exception_detail_info(msg: str = None):
        """
        Возвращает более детальную информацию об ошибке в блоке,
        в который интегрирована эта функция
        :param msg: сообщение, которое необходимо добавить
        :return: детали об ошибке и строка в которой она произошла
        """
        error_info = sys.exc_info()
        if error_info[2]:
            tb = traceback.extract_tb(sys.exc_info()[2])[-1]
            detail_info = (
                f"line №{tb.lineno}: {tb.line}; func_name: {tb.name}"
            )
            return detail_info + '; msg: ' + msg if msg else ''
        return ''

    @staticmethod
    def process(func):
        """ Декоратор для запуска функций в процессе исполнения """

        def run(*args, **kwargs):
            target = multiprocessing.Process(
                target=func, args=args, kwargs=kwargs
            )
            target.start()
            return target

        return run

    @staticmethod
    def thread(func, daemon_state=True):
        """ Декоратор для запуска функций в потоке без контроля исполнения """

        def run(*args, **kwargs):
            target = threading.Thread(target=func, args=args, kwargs=kwargs)
            # если False, то работает после завершения главного процесса
            target.setDaemon(daemon_state)
            target.start()
            return target

        return run

    @staticmethod
    def executable_file_path(file_path: str):
        """
        Определение пути файла в зависимости от того как исполняется приложение
        :param file_path: str
        :return: str
        """
        if getattr(sys, 'frozen', False):
            exec_path = sys._MEIPASS
            file_path = os.path.join(exec_path, file_path)
        else:
            file_path = file_path
        return file_path


class RequestsUtils:
    """ Различные методы для работы с запросами """

    STANDARD_USER_AGENT_LIST = (
        'Mozilla/5.0 (Windows NT 6.1; rv:57.0) Gecko/20100101 Firefox/57.0',

        'Opera/9.64 (X11; Linux i686; U; pl) Presto/2.1.1',

        'Mozilla/5.0 (Windows NT 5.0; WOW64; rv:6.0) '
        'Gecko/20100101 Firefox/6.0',

        'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1; '
        'Acoo Browser; .NET CLR 2.0.50727; .NET CLR 1.1.4322)',

        'Midori/0.2.0 (X11; Linux i686; U; pt-br) WebKit/531.2+',

        'Opera/9.64 (X11; Linux x86_64; U; en-GB) Presto/2.1.1'
    )

    def __init__(self):
        self.STANDARD_USER_AGENT_LIST = self._load_user_agent_list()

    @property
    def new_user_agent(self):
        """
        Предпочтительный способ получения UA, так как нет лишних I/O
        :return:
        """
        return random.choice(self.STANDARD_USER_AGENT_LIST)

    @classmethod
    def get_cookies_dict(cls, cookies: str):
        new_cookies = dict(x.split('=') for x in cookies.split(';'))
        return {k.strip(): v for k, v in new_cookies.items()}

    @classmethod
    def _load_user_agent_list(cls, file_path=None, file_name=None):
        """
        Возвращает список User Agent, если есть файл 'ua_list.pickle'
        загружает из него, если нет возвращает несколько дефолтных вариантов
        :param file_name: имя файла с User Agents
        :param file_path: путь до 'ua_list.pickle'
        :return: list: список User Agents
        """
        if not file_name:
            file_name = 'ua_list.pickle'
        if not file_path:
            file_path = os.path.join(file_name)
        file = Commonly.executable_file_path(file_path)
        try:
            with open(file, 'rb') as f:
                user_agent_list = pickle.load(f)
        except FileNotFoundError:
            user_agent_list = cls.STANDARD_USER_AGENT_LIST
        return user_agent_list

    @classmethod
    def get_random_header(cls, ua_list: list = None):
        """
        Возвращает header со случайным user agent
        :param ua_list: list: список user agent
        :return: dict
        """
        return {
            'Content-Type': 'application/json; charset=UTF-8',
            'User-Agent': random.choice(
                ua_list if ua_list else cls._load_user_agent_list()
            )
        }
