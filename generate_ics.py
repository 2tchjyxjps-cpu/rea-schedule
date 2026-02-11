import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from ics import Calendar, Event
import pytz
from urllib.parse import quote

# ===== НАСТРОЙКИ =====

GROUP_RAW = "15.24д-мен01/24б"
GROUP = quote(GROUP_RAW)
URL = f"https://rasp.rea.ru/?q={GROUP}"

TZ = pytz.timezone("Europe/Moscow")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

# ===== ЗАГРУЗКА СТРАНИЦЫ =====

def fetch_page():
    r = requests.get(URL, headers=HEADERS, timeout=30)
    if r.status_code != 200:
        raise RuntimeError("Не удалось загрузить страницу расписания")
    return r.text

# ===== ПАРСИНГ =====

def parse_schedule(html):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.view-week")
    if not table:
        raise RuntimeError("Таблица расписания не найдена")

    # даты
    ths = table.select("thead th")[1:]
    dates = []
    for th in ths:
        m = re.search(r"\d{2}\.\d{2}\.\d{4}", th.text)
        dates.append(datetime.strptime(m.group(), "%d.%m.%Y").date())

    events = []

    for row in table.select("tr.slot"):
        cells = row.select("td")
        if len(cells) < 2:
            continue

        times = re.findall(r"\d{2}:\d{2}", cells[0].text)
        if len(times) != 2:
            continue

        start_s, end_s = times

        for i, cell in enumerate(cells[1:]):
            a = cell.select_one("a.task")
            if not a:
                continue

            lines = [l.strip() for l in a.text.split("\n") if l.strip()]
            subject = lines[0]

            lesson_type = a.select_one("i")
            lesson_type = lesson_type.text.strip() if lesson_type else ""

            location = " ".join(lines[1:]).replace(lesson_type, "").strip()

            start_dt = TZ.localize(datetime.combine(dates[i], datetime.strptime(start_s, "%H:%M").time()))
            end_dt = TZ.localize(datetime.combine(dates[i], datetime.strptime(end_s, "%H:%M").time()))

            uid = f"{subject}-{start_dt.isoformat()}"

            ev = Event()
            ev.name = subject
            ev.begin = start_dt
            ev.end = end_dt
            ev.uid = uid
            if lesson_type:
                ev.description = lesson_type
            if location:
                ev.location = location

            events.append(ev)

    return events

# ===== MAIN =====

def main():
    html = fetch_page()
    events = parse_schedule(html)

    cal = Calendar()
    for e in events:
        cal.events.add(e)

    with open("schedule.ics", "w", encoding="utf-8") as f:
        f.writelines(cal)

    print(f"OK: {len(events)} событий")

if __name__ == "__main__":
    main()
