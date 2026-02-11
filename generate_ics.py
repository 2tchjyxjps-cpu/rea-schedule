import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from ics import Calendar, Event
import pytz

# ================= НАСТРОЙКИ =================

SKEY = "15.24д-мен01/24б"
BASE_PAGE = f"https://rasp.rea.ru/?q={SKEY}"
SCHEDULE_URL = "https://rasp.rea.ru/ScheduleCard"
TZ = pytz.timezone("Europe/Moscow")
WEEKS_AHEAD = 12

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Accept": "text/html, */*",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": BASE_PAGE,
}

# ================= ЗАГРУЗКА НЕДЕЛИ =================

def fetch_week(session, week_num=None):
    payload = {"skey": SKEY}
    if week_num is not None:
        payload["weekNum"] = str(week_num)

    r = session.post(SCHEDULE_URL, data=payload, timeout=30)
    if r.status_code != 200:
        raise RuntimeError("ScheduleCard вернул не 200")

    html = r.text
    if "view-week" not in html:
        raise RuntimeError("В ответе нет таблицы расписания")

    m = re.search(r'id="weekNum"\s+value="(\d+)"', html)
    if not m:
        raise RuntimeError("Не найден weekNum")

    return html, int(m.group(1))

# ================= ПАРСИНГ =================

def parse_week(html):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.view-week")
    if not table:
        return []

    # даты
    headers = table.select("thead th")[1:]
    dates = []
    for th in headers:
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

            uid = a.get("data-elementid", subject) + start_dt.isoformat()

            events.append({
                "name": subject,
                "type": lesson_type,
                "location": location,
                "start": start_dt,
                "end": end_dt,
                "uid": uid,
            })

    return events

# ================= ICS =================

def build_ics(events):
    cal = Calendar()
    for e in events:
        ev = Event()
        ev.name = e["name"]
        ev.begin = e["start"]
        ev.end = e["end"]
        ev.uid = e["uid"]
        if e["type"]:
            ev.description = e["type"]
        if e["location"]:
            ev.location = e["location"]
        cal.events.add(ev)
    return cal

# ================= MAIN =================

def main():
    session = requests.Session()
    session.headers.update(HEADERS)

    # первый заход — как браузер
    session.get(BASE_PAGE, timeout=30)

    html, current_week = fetch_week(session)

    all_events = []
    for w in range(current_week, current_week + WEEKS_AHEAD):
        html, _ = fetch_week(session, w)
        all_events.extend(parse_week(html))

    cal = build_ics(all_events)

    with open("schedule.ics", "w", encoding="utf-8") as f:
        f.writelines(cal)

    print(f"OK: {len(all_events)} событий")

if __name__ == "__main__":
    main()
