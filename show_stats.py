"""Скрипт служит дял отображения статистики"""
from logic.storage import StatsStorage


print('Блок статистики за все время:')
try:
    StatsStorage.show_stats()
except FileNotFoundError:
    print('Бот ниразу не запускался!!')

input()
