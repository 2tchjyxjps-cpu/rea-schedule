import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from ics import Calendar, Event
import pytz

SKEY = "15.24д-мен01/24б"
TZ = pytz.timezone("Europe/Moscow")

CANDIDATES = [
    ("POST", "https://rasp.rea.ru/ScheduleCard"),
    ("GET",  "https://rasp.rea.ru/ScheduleCard"),
    ("POST", "https://rasp.rea.ru/Home/ScheduleCard"),
    ("GET",  "https://rasp.rea.ru/Home/ScheduleCard"),
    ("POST", "https://rasp.rea.ru/Schedule/ScheduleCard"),
    ("GET",  "https://rasp.rea.ru/Schedule/ScheduleCard"),
]

BASE_URL = "https://rasp.rea.ru/?q=15.24д-мен01/24б"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": BASE_URL,
}

def fetch_week_html(week_num: int | None):
    """
    Пытается получить HTML-таблицу недели из ScheduleCard разными способами.
    Возвращает (html, resolved_week_num).
    """
    payload = {"skey": SKEY}
    if week_num is not None:
        payload["weekNum"] = str(week_num)

    last_err = None

    for method, url in CANDIDATES:
        try:
            if method == "POST":
                r = requests.post(url, data=payload, headers=HEADERS, timeout=30)
            else:
                r = requests.get(url, params=payload, headers=HEADERS, timeout=30)

            if r.status_code != 200:
                continue

            html = r.text
            # Быстрая проверка, что это похоже на нужный фрагмент
            if "view-week" not in html or 'id="weekNum"' not in html:
                continue

            # Вытащим weekNum из hidden input (как в твоём примере)
            m = re.search(r'id="weekNum"\s+value="(\d+)"', html)
            resolved = int(m.group(1)) if m else week_num
            return html, resolved

        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"Не смог получить ScheduleCard. Последняя ошибка: {last_err}")

def parse_week_table(html: str):
    soup = BeautifulSoup(html, "html.parser")

    table = soup.select_one("table.view-week")
    if not table:
        return []

    # Заголовки: соответствие колонка -> дата
    ths = table.select("thead th")
    # Первый th пустой, далее идут даты
    col_dates = []
    for th in ths[1:]:
        txt = th.get_text(" ", strip=True)
        # Ищем dd.mm.yyyy
        m = re.search(r"(\d{2}\.\d{2}\.\d{4})", txt)
        if not m:
            col_dates.append(None)
        else:
            col_dates.append(datetime.strptime(m.group(1), "%d.%m.%Y").date())

    events = []

    # Каждая строка slot — это “пара” со временем + ячейки по дням
    for tr in table.select("tr.slot"):
        tds = tr.select("td")
        if not tds:
            continue

        time_td = tds[0]
        time_lines = [x.strip() for x in time_td.get_text("\n", strip=True).split("\n") if x.strip()]
        # Пример: ["1 пара", "08:30", "10:00"]
        if len(time_lines) < 3:
            continue
        start_s, end_s = time_lines[1], time_lines[2]

        day_cells = tds[1:]

        for idx, cell in enumerate(day_cells):
            day_date = col_dates[idx] if idx < len(col_dates) else None
            if not day_date:
                continue

            a = cell.select_one("a.task")
            if not a:
                continue

            # Название предмета — первая строка
            full_lines = [x.strip() for x in a.get_text("\n", strip=True).split("\n") if x.strip()]
            if not full_lines:
                continue

            subject = full_lines[0]

            # Тип занятия в <i>
            i_tag = a.select_one("i")
            lesson_type = i_tag.get_text(" ", strip=True) if i_tag else ""

            # Локация — хвостовые строки после типа
            # (часто "3 корпус - 103, пл. Основная")
            location_parts = []
            for line in full_lines[1:]:
                # выкинем сам тип, если он совпал
                if lesson_type and lesson_type in line:
                    continue
                location_parts.append(line)
            location = " ".join(location_parts).strip()

            # elementid (если есть) — супер для стабильного UID
            element_id = a.get("data-elementid", "").strip()

            # Время
            start_dt = TZ.localize(datetime.combine(day_date, datetime.strptime(start_s, "%H:%M").time()))
            end_dt = TZ.localize(datetime.combine(day_date, datetime.strptime(end_s, "%H:%M").time()))

            events.append({
                "subject": subject,
                "type": lesson_type,
                "location": location,
                "start": start_dt,
                "end": end_dt,
                "uid": f"rea-{element_id or subject}-{day_date.isoformat()}-{start_s}",
            })

    return events

def build_ics(events):
    cal = Calendar()
    for e in events:
        ev = Event()
        ev.name = e["subject"]
        ev.begin = e["start"]
        ev.end = e["end"]
        ev.uid = e["uid"]
        desc = e["type"].strip()
        if desc:
            ev.description = desc
        if e["location"]:
            ev.location = e["location"]
        cal.events.add(ev)
    return cal

def main():
    # 1) Забираем “текущую” неделю: пробуем без weekNum, а сервер сам вернёт weekNum в hidden input
    html, current_week = fetch_week_html(week_num=None)

    # 2) Сколько недель выгружать вперёд (можешь поменять)
    WEEKS_AHEAD = 12

    all_events = []
    # включая текущую
    for w in range(current_week, current_week + WEEKS_AHEAD):
        week_html, _ = fetch_week_html(week_num=w)
        all_events.extend(parse_week_table(week_html))

    cal = build_ics(all_events)

    with open("schedule.ics", "w", encoding="utf-8") as f:
        f.writelines(cal)

    print(f"OK: событий {len(all_events)} (week {current_week}..{current_week+WEEKS_AHEAD-1})")

if __name__ == "__main__":
    main()
