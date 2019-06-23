import settings
from logic.user import SteamUser


if __name__ == '__main__':
    SteamUser.make_money(settings.COOKIES)
