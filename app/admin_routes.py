import calendar as calendar_stdlib
import json
from datetime import date
from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from app.auth import admin_required
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
    User,
)
from app.uploads_util import save_upload

bp = Blueprint("admin", __name__)

NEWS_LEVELS = [
    ("local", "Clube (local)"),
    ("regional", "Associação (regional)"),
    ("estadual", "União (estadual)"),
    ("mundial", "Divisão mundial"),
]


def _safe_remove_upload(rel_path: str | None) -> None:
    if not rel_path:
        return
    p = Path(current_app.config["UPLOAD_FOLDER"]) / rel_path
    if p.is_file():
        p.unlink()


def _process_member_photo(member: Member) -> None:
    if request.form.get("remove_photo") == "1":
        _safe_remove_upload(member.photo_filename)
        member.photo_filename = None
        return
    f = request.files.get("photo")
    saved = save_upload(f, current_app.config["UPLOAD_FOLDER"], "members")
    if saved:
        _safe_remove_upload(member.photo_filename)
        member.photo_filename = saved


def parent_users_query():
    return User.query.filter_by(role="parent").order_by(User.created_at.desc()).all()


def parse_parent_id(raw):
    if raw is None or raw == "" or raw == "0":
        return None
    try:
        pid = int(raw)
    except (TypeError, ValueError):
        return None
    p = db.session.get(User, pid)
    if not p or p.role != "parent":
        return None
    return pid


def normalize_cpf_digits(value: str | None) -> str | None:
    if not value:
        return None
    d = "".join(c for c in value if c.isdigit())
    if len(d) != 11:
        return None
    return d


def format_cpf_display(digits: str) -> str:
    return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"


def parse_notebook_checklist_from_form(form) -> list[bool]:
    return [form.get(f"nb_{i}") == "1" for i in range(1, 31)]


def _emergency_phone_ok(phone: str) -> bool:
    digits = "".join(c for c in (phone or "") if c.isdigit())
    return len(digits) >= 10


def apply_member_form(m: Member, form, member_id_exclude=None):
    name = (form.get("full_name") or "").strip()
    if not name:
        raise ValueError("Nome completo é obrigatório.")
    m.full_name = name

    unit = (form.get("unit") or "").strip()
    if not unit:
        raise ValueError('Nome da unidade (classe) é obrigatório — ex.: Amigo, Companheiro, "Duque de Caxias", etc.')
    m.unit = unit

    bd_raw = (form.get("birth_date") or "").strip()
    if not bd_raw:
        raise ValueError("Data de nascimento é obrigatória.")
    try:
        m.birth_date = date.fromisoformat(bd_raw)
    except ValueError:
        raise ValueError("Data de nascimento inválida.")

    cpf_field = (form.get("cpf") or "").strip()
    if not cpf_field:
        m.cpf = None
    else:
        cpf_raw = normalize_cpf_digits(cpf_field)
        if not cpf_raw:
            raise ValueError("CPF inválido. Informe 11 dígitos.")
        q = Member.query.filter(Member.cpf == cpf_raw)
        if member_id_exclude:
            q = q.filter(Member.id != member_id_exclude)
        if q.first():
            raise ValueError("CPF já cadastrado para outro membro.")
        m.cpf = cpf_raw

    blood = (form.get("blood_type") or "").strip()
    if not blood:
        raise ValueError("Tipo sanguíneo é obrigatório.")
    m.blood_type = blood

    father = (form.get("father_name") or "").strip()
    mother = (form.get("mother_name") or "").strip()
    if not father:
        raise ValueError("Nome do pai ou responsável é obrigatório.")
    if not mother:
        raise ValueError("Nome da mãe ou responsável é obrigatório.")
    m.father_name = father
    m.mother_name = mother

    em_name = (form.get("emergency_contact_name") or "").strip()
    em_phone = (form.get("emergency_contact_phone") or "").strip()
    if not em_name:
        raise ValueError("Contato de emergência — nome é obrigatório.")
    if not em_phone:
        raise ValueError("Contato de emergência — telefone é obrigatório.")
    if not _emergency_phone_ok(em_phone):
        raise ValueError("Telefone de emergência deve ter pelo menos 10 dígitos.")
    m.emergency_contact_name = em_name
    m.emergency_contact_phone = em_phone

    m.notebook_current = (form.get("notebook_current") or "").strip() or None
    m.parent_id = parse_parent_id(form.get("parent_id"))
    m.overall_performance = m.computed_overall_performance()


@bp.before_request
@login_required
@admin_required
def _admin_guard():
    pass


@bp.route("/")
def dashboard():
    n_members = Member.query.count()
    n_parents = User.query.filter_by(role="parent").count()
    n_dir = DirectorateMember.query.count()
    n_news = ClubNews.query.count()
    recent = BoardPost.query.order_by(BoardPost.created_at.desc()).limit(3).all()
    unit_rows = (
        db.session.query(Member.unit, func.count(Member.id))
        .group_by(Member.unit)
        .order_by(func.count(Member.id).desc())
        .all()
    )
    unit_stats = []
    for u, cnt in unit_rows:
        label = u or "Sem unidade"
        unit_stats.append({"label": label, "count": cnt})
    max_u = max((s["count"] for s in unit_stats), default=1)
    directorate_preview = (
        DirectorateMember.query.order_by(
            DirectorateMember.display_order, DirectorateMember.full_name
        )
        .limit(12)
        .all()
    )
    return render_template(
        "admin/dashboard.html",
        n_members=n_members,
        n_parents=n_parents,
        n_dir=n_dir,
        n_news=n_news,
        recent_posts=recent,
        unit_stats=unit_stats,
        max_unit_count=max_u,
        directorate_preview=directorate_preview,
    )


@bp.route("/responsaveis")
def parents_list():
    parents = parent_users_query()
    rows = []
    for p in parents:
        kids = list(p.children)
        rows.append({"user": p, "children": kids, "n_children": len(kids)})
    return render_template("admin/parents_list.html", rows=rows)


@bp.route("/responsaveis/<int:user_id>", methods=["GET", "POST"])
def parent_detail(user_id):
    p = db.session.get(User, user_id)
    if not p or p.role != "parent":
        flash("Responsável não encontrado.", "danger")
        return redirect(url_for("admin.parents_list"))

    if request.method == "POST":
        action = request.form.get("action")
        if action == "link":
            mid_raw = request.form.get("member_id")
            try:
                mid = int(mid_raw)
            except (TypeError, ValueError):
                flash("Selecione um desbravador.", "warning")
                return redirect(url_for("admin.parent_detail", user_id=user_id))
            m = db.session.get(Member, mid)
            if not m:
                flash("Membro inválido.", "danger")
                return redirect(url_for("admin.parent_detail", user_id=user_id))
            if m.parent_id is not None and m.parent_id != p.id:
                flash("Este desbravador já está vinculado a outro responsável.", "warning")
                return redirect(url_for("admin.parent_detail", user_id=user_id))
            m.parent_id = p.id
            db.session.commit()
            flash("Vínculo criado.", "success")
            return redirect(url_for("admin.parent_detail", user_id=user_id))
        if action == "unlink":
            mid_raw = request.form.get("member_id")
            try:
                mid = int(mid_raw)
            except (TypeError, ValueError):
                return redirect(url_for("admin.parent_detail", user_id=user_id))
            m = db.session.get(Member, mid)
            if m and m.parent_id == p.id:
                m.parent_id = None
                db.session.commit()
                flash("Vínculo removido.", "info")
            return redirect(url_for("admin.parent_detail", user_id=user_id))

    linked = list(p.children)
    unlinked = Member.query.filter(Member.parent_id.is_(None)).order_by(Member.full_name).all()
    return render_template(
        "admin/parent_detail.html",
        parent_user=p,
        linked=linked,
        unlinked=unlinked,
    )


@bp.route("/presencas")
def attendance_overview():
    members = Member.query.order_by(Member.full_name).all()
    stats = []
    for m in members:
        pr, tot, pct = m.attendance_stats()
        last = (
            Attendance.query.filter_by(member_id=m.id)
            .order_by(Attendance.meeting_date.desc())
            .first()
        )
        stats.append(
            {
                "member": m,
                "present": pr,
                "total": tot,
                "rate": pct if tot else None,
                "last_meeting": last.meeting_date if last else None,
            }
        )
    return render_template("admin/attendance_overview.html", stats=stats)


@bp.route("/membros")
def members():
    rows = Member.query.order_by(Member.full_name).all()
    return render_template("admin/members.html", members=rows, format_cpf_display=format_cpf_display)


def _member_form_ctx(member, parents):
    return dict(member=member, parent_users=parents)


@bp.route("/membros/novo", methods=["GET", "POST"])
def member_new():
    parents = parent_users_query()
    if request.method == "POST":
        m = Member(full_name="—")
        try:
            apply_member_form(m, request.form)
        except ValueError as e:
            flash(str(e), "warning")
            return render_template("admin/member_form.html", **_member_form_ctx(None, parents))
        db.session.add(m)
        db.session.flush()
        _process_member_photo(m)
        db.session.commit()
        flash("Desbravador cadastrado.", "success")
        return redirect(url_for("admin.member_edit", id=m.id))

    return render_template(
        "admin/member_form.html", **_member_form_ctx(None, parents)
    )


@bp.route("/membros/<int:id>/editar", methods=["GET", "POST"])
def member_edit(id):
    m = Member.query.get_or_404(id)
    parents = parent_users_query()
    if request.method == "POST":
        try:
            apply_member_form(m, request.form, member_id_exclude=m.id)
        except ValueError as e:
            flash(str(e), "warning")
            return render_template("admin/member_form.html", **_member_form_ctx(m, parents))
        _process_member_photo(m)
        db.session.commit()
        flash("Dados atualizados.", "success")
        return redirect(url_for("admin.member_edit", id=m.id))
    return render_template("admin/member_form.html", **_member_form_ctx(m, parents))


@bp.route("/membros/<int:id>/excluir", methods=["POST"])
def member_delete(id):
    m = Member.query.get_or_404(id)
    ActivityRecord.query.filter_by(member_id=m.id).delete()
    Attendance.query.filter_by(member_id=m.id).delete()
    MeetingDuque.query.filter_by(member_id=m.id).delete()
    _safe_remove_upload(m.photo_filename)
    db.session.delete(m)
    db.session.commit()
    flash("Desbravador removido do sistema.", "info")
    return redirect(url_for("admin.members"))


def _parse_agenda_form(form):
    title = (form.get("title") or "").strip()
    if not title:
        raise ValueError("Título é obrigatório.")
    body = (form.get("body") or "").strip() or None
    d_raw = (form.get("event_date") or "").strip()
    if not d_raw:
        raise ValueError("Data é obrigatória.")
    try:
        evd = date.fromisoformat(d_raw)
    except ValueError:
        raise ValueError("Data inválida.")
    tm = (form.get("event_time") or "").strip() or None
    if tm and len(tm) > 8:
        tm = tm[:8]
    return title, body, evd, tm


def _agenda_year_months(year: int):
    months = []
    for month in range(1, 13):
        weeks = calendar_stdlib.monthcalendar(year, month)
        months.append({"n": month, "weeks": weeks})
    return months


@bp.route("/agenda")
def agenda_list():
    try:
        year = int(request.args.get("year") or date.today().year)
    except (TypeError, ValueError):
        year = date.today().year
    year = max(2000, min(2100, year))
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    rows = (
        AgendaEvent.query.filter(
            AgendaEvent.event_date >= start, AgendaEvent.event_date <= end
        )
        .order_by(AgendaEvent.event_date.asc(), AgendaEvent.id.asc())
        .all()
    )
    events_by_date = {}
    for ev in rows:
        key = ev.event_date.isoformat()
        events_by_date.setdefault(key, []).append(ev)
    months = _agenda_year_months(year)
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
        "admin/agenda_calendar.html",
        year=year,
        year_prev=year - 1,
        year_next=year + 1,
        months=months,
        events_by_date=events_by_date,
        all_events=rows,
    )


@bp.route("/agenda/nova", methods=["GET", "POST"])
def agenda_new():
    prefill = (request.args.get("date") or "").strip()
    back_year = date.today().year
    if len(prefill) >= 10:
        try:
            back_year = date.fromisoformat(prefill[:10]).year
        except ValueError:
            pass
    if request.method == "POST":
        try:
            title, body, evd, tm = _parse_agenda_form(request.form)
        except ValueError as e:
            flash(str(e), "warning")
            return render_template(
                "admin/agenda_form.html",
                ev=None,
                prefill_date=prefill or None,
                back_year=back_year,
            )
        ev = AgendaEvent(title=title, body=body, event_date=evd, event_time=tm)
        db.session.add(ev)
        db.session.commit()
        flash("Evento agendado.", "success")
        return redirect(url_for("admin.agenda_list", year=evd.year))
    return render_template(
        "admin/agenda_form.html",
        ev=None,
        prefill_date=prefill or None,
        back_year=back_year,
    )


@bp.route("/agenda/<int:eid>/editar", methods=["GET", "POST"])
def agenda_edit(eid):
    ev = AgendaEvent.query.get_or_404(eid)
    if request.method == "POST":
        try:
            title, body, evd, tm = _parse_agenda_form(request.form)
        except ValueError as e:
            flash(str(e), "warning")
            return render_template(
                "admin/agenda_form.html", ev=ev, prefill_date=None, back_year=ev.event_date.year
            )
        ev.title = title
        ev.body = body
        ev.event_date = evd
        ev.event_time = tm
        db.session.commit()
        flash("Agenda atualizada.", "success")
        return redirect(url_for("admin.agenda_list", year=evd.year))
    return render_template(
        "admin/agenda_form.html", ev=ev, prefill_date=None, back_year=ev.event_date.year
    )


@bp.route("/agenda/<int:eid>/excluir", methods=["POST"])
def agenda_delete(eid):
    ev = AgendaEvent.query.get_or_404(eid)
    y = ev.event_date.year
    db.session.delete(ev)
    db.session.commit()
    flash("Evento removido.", "info")
    return redirect(url_for("admin.agenda_list", year=y))


@bp.route("/membros/<int:member_id>/caderno/checklist", methods=["POST"])
def member_notebook_checklist_save(member_id):
    m = Member.query.get_or_404(member_id)
    m.notebook_checklist_30_json = json.dumps(parse_notebook_checklist_from_form(request.form))
    db.session.commit()
    flash("Checklist do caderno (1–30) atualizado.", "success")
    return redirect(url_for("admin.member_activity", id=m.id))


@bp.route("/membros/<int:id>/atividade", methods=["GET", "POST"])
def member_activity(id):
    m = Member.query.get_or_404(id)
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        category = (request.form.get("category") or "").strip() or None
        notes = (request.form.get("notes") or "").strip() or None
        try:
            pct = int(request.form.get("progress_percent") or 0)
        except ValueError:
            pct = 0
        pct = max(0, min(100, pct))
        completed = request.form.get("completed") == "1"
        rec = ActivityRecord(
            member_id=m.id,
            title=title or "Atividade",
            category=category,
            notes=notes,
            progress_percent=pct,
            completed=completed,
        )
        db.session.add(rec)
        m.overall_performance = m.computed_overall_performance()
        db.session.commit()
        flash("Registro do caderno salvo.", "success")
        return redirect(url_for("admin.member_activity", id=m.id))

    records = (
        ActivityRecord.query.filter_by(member_id=m.id)
        .order_by(ActivityRecord.recorded_at.desc(), ActivityRecord.id.desc())
        .limit(80)
        .all()
    )
    completed_recs = [r for r in records if r.completed]
    open_recs = [r for r in records if not r.completed]
    n_done = len(completed_recs)
    n_open = len(open_recs)
    notebook_pct = m.notebook_checklist_progress_percent()
    checklist_30 = m.get_notebook_checklist_30()
    checklist_done_count = sum(1 for x in checklist_30 if x)
    duques_rows = (
        MeetingDuque.query.filter_by(member_id=m.id)
        .order_by(MeetingDuque.meeting_date.desc(), MeetingDuque.id.desc())
        .limit(60)
        .all()
    )
    duques_total = (
        db.session.query(func.coalesce(func.sum(MeetingDuque.duques), 0))
        .filter(MeetingDuque.member_id == m.id)
        .scalar()
        or 0
    )
    return render_template(
        "admin/member_activity.html",
        member=m,
        records=records,
        completed_recs=completed_recs,
        open_recs=open_recs,
        n_done=n_done,
        n_open=n_open,
        notebook_pct=notebook_pct,
        checklist_30=checklist_30,
        checklist_done_count=checklist_done_count,
        duques_rows=duques_rows,
        duques_total=int(duques_total),
        today_iso=date.today().isoformat(),
    )


@bp.route("/membros/<int:member_id>/atividade/<int:rec_id>/excluir", methods=["POST"])
def activity_delete(member_id, rec_id):
    m = Member.query.get_or_404(member_id)
    rec = ActivityRecord.query.filter_by(id=rec_id, member_id=m.id).first_or_404()
    db.session.delete(rec)
    m.overall_performance = m.computed_overall_performance()
    db.session.commit()
    flash("Registro removido.", "info")
    return redirect(url_for("admin.member_activity", id=member_id))


@bp.route("/membros/<int:member_id>/atividade/<int:rec_id>/concluir", methods=["POST"])
def activity_toggle_completed(member_id, rec_id):
    m = Member.query.get_or_404(member_id)
    rec = ActivityRecord.query.filter_by(id=rec_id, member_id=m.id).first_or_404()
    rec.completed = request.form.get("completed") == "1"
    if rec.completed and rec.progress_percent < 100:
        rec.progress_percent = 100
    m.overall_performance = m.computed_overall_performance()
    db.session.commit()
    flash("Status atualizado.", "success")
    return redirect(url_for("admin.member_activity", id=member_id))


@bp.route("/membros/<int:member_id>/atividade/duques", methods=["POST"])
def member_duques_add(member_id):
    m = Member.query.get_or_404(member_id)
    md_raw = (request.form.get("meeting_date") or "").strip()
    try:
        md = date.fromisoformat(md_raw)
    except ValueError:
        flash("Informe uma data de reunião válida.", "warning")
        return redirect(url_for("admin.member_activity", id=m.id))
    try:
        dq = int(request.form.get("duques") or 0)
    except ValueError:
        dq = 0
    dq = max(0, dq)
    note = (request.form.get("note") or "").strip() or None
    row = MeetingDuque(
        member_id=m.id,
        meeting_date=md,
        duques=dq,
        note=note,
    )
    db.session.add(row)
    db.session.commit()
    flash("Duques da reunião registrados.", "success")
    return redirect(url_for("admin.member_activity", id=m.id))


@bp.route("/membros/<int:member_id>/atividade/duques/<int:duque_id>/excluir", methods=["POST"])
def member_duques_delete(member_id, duque_id):
    m = Member.query.get_or_404(member_id)
    row = MeetingDuque.query.filter_by(id=duque_id, member_id=m.id).first_or_404()
    db.session.delete(row)
    db.session.commit()
    flash("Registro de duques removido.", "info")
    return redirect(url_for("admin.member_activity", id=m.id))


@bp.route("/membros/<int:id>/presenca", methods=["GET", "POST"])
def member_attendance(id):
    m = Member.query.get_or_404(id)
    if request.method == "POST":
        md_raw = request.form.get("meeting_date") or ""
        try:
            md = date.fromisoformat(md_raw)
        except ValueError:
            flash("Data da reunião inválida.", "warning")
            return redirect(url_for("admin.member_attendance", id=m.id))
        present = request.form.get("present") == "1"
        note = (request.form.get("note") or "").strip() or None
        row = Attendance(
            member_id=m.id,
            meeting_date=md,
            present=present,
            note=note,
        )
        db.session.add(row)
        m.overall_performance = m.computed_overall_performance()
        db.session.commit()
        flash("Presença registrada.", "success")
        return redirect(url_for("admin.member_attendance", id=m.id))

    rows = (
        Attendance.query.filter_by(member_id=m.id)
        .order_by(Attendance.meeting_date.desc())
        .limit(80)
        .all()
    )
    pr, tot, pct = m.attendance_stats()
    return render_template(
        "admin/member_attendance.html",
        member=m,
        rows=rows,
        att_present=pr,
        att_total=tot,
        att_rate=pct if tot else None,
    )


@bp.route("/membros/<int:member_id>/presenca/<int:att_id>/excluir", methods=["POST"])
def attendance_delete(member_id, att_id):
    m = Member.query.get_or_404(member_id)
    row = Attendance.query.filter_by(id=att_id, member_id=m.id).first_or_404()
    db.session.delete(row)
    m.overall_performance = m.computed_overall_performance()
    db.session.commit()
    flash("Registro de presença excluído.", "info")
    return redirect(url_for("admin.member_attendance", id=member_id))


@bp.route("/publicacoes")
def posts():
    rows = BoardPost.query.order_by(BoardPost.created_at.desc()).all()
    return render_template("admin/posts.html", posts=rows)


@bp.route("/publicacoes/nova", methods=["GET", "POST"])
def post_new():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        body = (request.form.get("body") or "").strip()
        if not title or not body:
            flash("Título e texto são obrigatórios.", "warning")
            return render_template("admin/post_form.html", post=None)
        p = BoardPost(title=title, body=body, author_id=current_user.id)
        db.session.add(p)
        db.session.commit()
        flash("Publicação criada.", "success")
        return redirect(url_for("admin.posts"))
    return render_template("admin/post_form.html", post=None)


@bp.route("/publicacoes/<int:post_id>/excluir", methods=["POST"])
def post_delete(post_id):
    p = BoardPost.query.get_or_404(post_id)
    db.session.delete(p)
    db.session.commit()
    flash("Publicação excluída.", "info")
    return redirect(url_for("admin.posts"))


@bp.route("/diretoria")
def directorate_list():
    rows = DirectorateMember.query.order_by(
        DirectorateMember.display_order, DirectorateMember.full_name
    ).all()
    return render_template("admin/directorate_list.html", members=rows)


@bp.route("/diretoria/novo", methods=["GET", "POST"])
def directorate_new():
    if request.method == "POST":
        name = (request.form.get("full_name") or "").strip()
        cargo = (request.form.get("cargo") or "").strip()
        if not name or not cargo:
            flash("Nome e cargo são obrigatórios.", "warning")
            return render_template("admin/directorate_form.html", m=None)
        d = DirectorateMember(full_name=name, cargo=cargo)
        _apply_directorate_form(d, request.form, request.files)
        db.session.add(d)
        db.session.commit()
        flash("Membro da diretoria cadastrado.", "success")
        return redirect(url_for("admin.directorate_list"))
    return render_template("admin/directorate_form.html", m=None)


@bp.route("/diretoria/<int:id>/editar", methods=["GET", "POST"])
def directorate_edit(id):
    d = DirectorateMember.query.get_or_404(id)
    if request.method == "POST":
        d.full_name = (request.form.get("full_name") or "").strip() or d.full_name
        d.cargo = (request.form.get("cargo") or "").strip() or d.cargo
        _apply_directorate_form(d, request.form, request.files)
        db.session.commit()
        flash("Dados atualizados.", "success")
        return redirect(url_for("admin.directorate_list"))
    return render_template("admin/directorate_form.html", m=d)


@bp.route("/diretoria/<int:id>/excluir", methods=["POST"])
def directorate_delete(id):
    d = DirectorateMember.query.get_or_404(id)
    _safe_remove_upload(d.photo_filename)
    db.session.delete(d)
    db.session.commit()
    flash("Registro removido.", "info")
    return redirect(url_for("admin.directorate_list"))


def _apply_directorate_form(d: DirectorateMember, form, files) -> None:
    d.phone = (form.get("phone") or "").strip() or None
    d.email_public = (form.get("email_public") or "").strip() or None
    d.bio = (form.get("bio") or "").strip() or None
    try:
        d.display_order = int(form.get("display_order") or 0)
    except ValueError:
        d.display_order = 0

    if form.get("remove_photo") == "1":
        _safe_remove_upload(d.photo_filename)
        d.photo_filename = None
    else:
        f = files.get("photo")
        saved = save_upload(f, current_app.config["UPLOAD_FOLDER"], "directorate")
        if saved:
            _safe_remove_upload(d.photo_filename)
            d.photo_filename = saved


@bp.route("/noticias-desbravadores")
def club_news_list():
    rows = ClubNews.query.order_by(ClubNews.created_at.desc()).all()
    return render_template("admin/club_news_list.html", news_list=rows, levels=NEWS_LEVELS)


@bp.route("/noticias-desbravadores/nova", methods=["GET", "POST"])
def club_news_new():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        body = (request.form.get("body") or "").strip()
        level = (request.form.get("level") or "local").strip()
        if level not in dict(NEWS_LEVELS):
            level = "local"
        if not title or not body:
            flash("Título e texto são obrigatórios.", "warning")
            return render_template(
                "admin/club_news_form.html", item=None, levels=NEWS_LEVELS
            )
        n = ClubNews(title=title, body=body, level=level, author_id=current_user.id)
        f = request.files.get("image")
        saved = save_upload(f, current_app.config["UPLOAD_FOLDER"], "news")
        if saved:
            n.image_filename = saved
        db.session.add(n)
        db.session.commit()
        flash("Notícia publicada.", "success")
        return redirect(url_for("admin.club_news_list"))
    return render_template("admin/club_news_form.html", item=None, levels=NEWS_LEVELS)


@bp.route("/noticias-desbravadores/<int:nid>/editar", methods=["GET", "POST"])
def club_news_edit(nid):
    n = ClubNews.query.get_or_404(nid)
    if request.method == "POST":
        n.title = (request.form.get("title") or "").strip() or n.title
        n.body = (request.form.get("body") or "").strip() or n.body
        level = (request.form.get("level") or n.level).strip()
        if level in dict(NEWS_LEVELS):
            n.level = level
        if request.form.get("remove_image") == "1":
            _safe_remove_upload(n.image_filename)
            n.image_filename = None
        else:
            f = request.files.get("image")
            saved = save_upload(f, current_app.config["UPLOAD_FOLDER"], "news")
            if saved:
                _safe_remove_upload(n.image_filename)
                n.image_filename = saved
        db.session.commit()
        flash("Notícia atualizada.", "success")
        return redirect(url_for("admin.club_news_list"))
    return render_template("admin/club_news_form.html", item=n, levels=NEWS_LEVELS)


@bp.route("/noticias-desbravadores/<int:nid>/excluir", methods=["POST"])
def club_news_delete(nid):
    n = ClubNews.query.get_or_404(nid)
    _safe_remove_upload(n.image_filename)
    db.session.delete(n)
    db.session.commit()
    flash("Notícia excluída.", "info")
    return redirect(url_for("admin.club_news_list"))
