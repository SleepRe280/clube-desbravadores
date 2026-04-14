"""Lógica compartilhada do calendário mensal (admin e família)."""

import calendar as calendar_stdlib
from datetime import date
from typing import Any

MONTH_NAMES_PT = [
    "",
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
]


def agenda_add_months(y: int, m: int, delta: int) -> tuple[int, int]:
    idx = y * 12 + (m - 1) + delta
    return idx // 12, idx % 12 + 1


def agenda_clamp_day_in_month(y: int, m: int, day: int) -> date:
    last = calendar_stdlib.monthrange(y, m)[1]
    return date(y, m, min(max(1, day), last))


def agenda_sort_day_events(evs: list[Any]) -> list[Any]:
    def key(ev):
        t = ev.event_time or "99:99:99"
        return (t, ev.id)

    return sorted(evs, key=key)


def agenda_month_bounds(year: int, month: int) -> tuple[date, date]:
    last_dom = calendar_stdlib.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_dom)


def agenda_weeks(year: int, month: int):
    return calendar_stdlib.monthcalendar(year, month)


def agenda_resolve_selected_day(
    year: int, month: int, sel_raw: str, today: date
) -> date:
    selected_day = None
    if len(sel_raw) >= 10:
        try:
            candidate = date.fromisoformat(sel_raw[:10])
        except ValueError:
            candidate = None
        if candidate:
            if candidate.year == year and candidate.month == month:
                selected_day = candidate
            else:
                selected_day = agenda_clamp_day_in_month(year, month, candidate.day)
    if selected_day is None:
        selected_day = (
            today
            if today.year == year and today.month == month
            else date(year, month, 1)
        )
    return selected_day
