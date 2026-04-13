import calendar as calendar_stdlib
from collections import defaultdict
from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.auth import parent_required
from sqlalchemy import func

from app.extensions import db
from app.models import (
    ActivityRecord,
    AgendaEvent,
    Attendance,
    BoardPost,
    ClubNews,
    DirectorateMember,
    MeetingDuque,
    Member,
)

bp = Blueprint("parent", __name__)

NEWS_LABELS = {
    "local": "Local",
    "regional": "Regional",
    "estadual": "Estadual",
    "mundial": "Mundial",
}


@bp.before_request
@login_required
@parent_required
def _parent_guard():
    pass


@bp.route("/")
def home():
    children = list(current_user.children)
    duques_by_member = {}
    if children:
        ids = [c.id for c in children]
        q = (
            db.session.query(MeetingDuque.member_id, func.sum(MeetingDuque.duques))
            .filter(MeetingDuque.member_id.in_(ids))
            .group_by(MeetingDuque.member_id)
            .all()
        )
        duques_by_member = {mid: int(t or 0) for mid, t in q}
    board_posts = BoardPost.query.order_by(BoardPost.created_at.desc()).limit(12).all()
    news_items = ClubNews.query.order_by(ClubNews.created_at.desc()).limit(20).all()
    news_by_level = defaultdict(list)
    for n in news_items:
        news_by_level[n.level].append(n)
    return render_template(
        "parent/home.html",
        children=children,
        duques_by_member=duques_by_member,
        board_posts=board_posts,
        news_by_level=dict(news_by_level),
        news_labels=NEWS_LABELS,
    )


def _parent_agenda_months(year: int):
    months = []
    for month in range(1, 13):
        weeks = calendar_stdlib.monthcalendar(year, month)
        months.append({"n": month, "weeks": weeks})
    return months


@bp.route("/agenda")
def parent_agenda():
    try:
        year = int(request.args.get("year") or date.today().year)
    except (TypeError, ValueError):
        year = date.today().year
    year = max(2000, min(2100, year))
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    rows = (
        AgendaEvent.query.filter(AgendaEvent.event_date >= start, AgendaEvent.event_date <= end)
        .order_by(AgendaEvent.event_date.asc(), AgendaEvent.id.asc())
        .all()
    )
    events_by_date = {}
    for ev in rows:
        key = ev.event_date.isoformat()
        events_by_date.setdefault(key, []).append(ev)
    months = _parent_agenda_months(year)
    month_names_pt = [
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
    for m in months:
        m["label"] = month_names_pt[m["n"]]
    return render_template(
        "parent/agenda_calendar.html",
        year=year,
        year_prev=year - 1,
        year_next=year + 1,
        months=months,
        events_by_date=events_by_date,
        all_events=rows,
    )


@bp.route("/clube/membros")
def club_directory():
    members = Member.query.order_by(Member.full_name).all()
    return render_template("parent/club_directory.html", members=members)


@bp.route("/clube/diretoria")
def club_directorate():
    team = DirectorateMember.query.order_by(
        DirectorateMember.display_order, DirectorateMember.full_name
    ).all()
    return render_template("parent/club_directorate.html", team=team)


@bp.route("/noticias")
def news_feed():
    level = (request.args.get("nivel") or "").strip()
    q = ClubNews.query.order_by(ClubNews.created_at.desc())
    if level in NEWS_LABELS:
        q = q.filter_by(level=level)
    items = q.limit(50).all()
    return render_template(
        "parent/news_feed.html",
        items=items,
        active_level=level if level in NEWS_LABELS else None,
        news_labels=NEWS_LABELS,
    )


@bp.route("/conta")
def account():
    return render_template("parent/account.html")


@bp.route("/filho/<int:member_id>")
def child_detail(member_id):
    m = Member.query.get_or_404(member_id)
    if m.parent_id != current_user.id:
        flash("Você não tem permissão para ver este perfil.", "danger")
        return redirect(url_for("parent.home"))

    activities = (
        ActivityRecord.query.filter_by(member_id=m.id)
        .order_by(ActivityRecord.recorded_at.desc())
        .limit(40)
        .all()
    )
    done = [a for a in activities if a.completed]
    open_act = [a for a in activities if not a.completed]
    attendances = (
        Attendance.query.filter_by(member_id=m.id)
        .order_by(Attendance.meeting_date.desc())
        .limit(40)
        .all()
    )
    pr, tot_all, att_rate = m.attendance_stats()
    act_avg = m.activity_progress_avg()
    duques_total = (
        db.session.query(func.coalesce(func.sum(MeetingDuque.duques), 0))
        .filter(MeetingDuque.member_id == m.id)
        .scalar()
        or 0
    )
    duques_rows = (
        MeetingDuque.query.filter_by(member_id=m.id)
        .order_by(MeetingDuque.meeting_date.desc(), MeetingDuque.id.desc())
        .limit(24)
        .all()
    )
    return render_template(
        "parent/child_detail.html",
        member=m,
        activities_open=open_act,
        activities_done=done,
        attendances=attendances,
        present_count=pr,
        attendance_total=tot_all,
        attendance_rate=att_rate if tot_all else None,
        activity_avg=act_avg,
        duques_total=int(duques_total),
        duques_rows=duques_rows,
        notebook_checklist_pct=m.notebook_checklist_progress_percent(),
    )
