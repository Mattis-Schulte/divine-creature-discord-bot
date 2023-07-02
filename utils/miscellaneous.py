import calendar
import time


def capitalize_first_letter(string: str) -> str:
    """
    Capitalize the first letter of a string.

    :param string: The string to capitalize the first letter of.

    :return: The string with the first letter capitalized.
    """
    return string[:1].upper() + string[1:]


def calc_refresh_time() -> int:
    """
    Calculate the time when the user's quota is refilled.

    :return: The time when the user's quota is refilled.
    """
    tomorrow = int(calendar.timegm(time.gmtime())) + 86400
    return tomorrow - (tomorrow % 86400)


def time_until_refresh(refresh_time: int = calc_refresh_time()) -> tuple[int, int]:
    """
    Calculate the time until the user's quota is refilled.

    :param refresh_time: The time when the user's quota is refilled.

    :return: The time until the user's quota is refilled.
    """
    time_until = refresh_time - int(calendar.timegm(time.gmtime()))
    hours = time_until // 3600
    minutes = (time_until % 3600) // 60

    return hours, minutes
    

def beautified_date() -> str:
    """
    Return the current date in a written format.

    Example: "Monday, January 1st 2021"

    :return: The current date in a written format.
    """
    DAY_SUFFIXES = {"1": "st", "2": "nd", "3": "rd"}
    weekday = time.strftime("%A", time.gmtime())
    month = time.strftime("%B", time.gmtime())
    day = time.strftime("%d", time.gmtime()).lstrip("0")
    year = time.strftime("%Y", time.gmtime())

    return f"{weekday}, {month} {day + ('th' if len(day) > 1 and day[0] == '1' else DAY_SUFFIXES.get(day[-1], 'th'))} {year}"
