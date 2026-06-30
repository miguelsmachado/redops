"""Flask Entrypoint — domain objects never cross the session boundary into templates."""

from __future__ import annotations
import os, uuid
from datetime import datetime, timezone
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, abort,
)
from werkzeug.utils import secure_filename

from datetime import timezone, timedelta
BRT = timezone(timedelta(hours=-3), name='BRT')

def _now_brt() -> datetime:
    """Current time in Brasília (UTC-3)."""
    return datetime.now(tz=BRT)

def _fmt_brt(value) -> str:
    """Format datetime/string for display. 
    Datetimes are stored as BRT-naive — display as-is with BRT label.
    If timezone-aware, convert to BRT first.
    """
    if not value:
        return ''
    try:
        from datetime import datetime, timezone, timedelta
        _BRT = timezone(timedelta(hours=-3))
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, str):
            s = value.strip()
            if s.endswith('Z'):
                s = s[:-1] + '+00:00'
            dt = datetime.fromisoformat(s)
        else:
            return str(value)[:16]
        # If aware, convert to BRT; if naive, already in BRT — just display
        if dt.tzinfo is not None:
            dt = dt.astimezone(_BRT)
        return dt.strftime('%d/%m/%Y %H:%M') + ' (BRT -3)'
    except Exception:
        return str(value)[:16].replace('T', ' ')


def _parse_dt(s: str) -> datetime:
    """Parse datetime-local string as BRT-aware datetime."""
    if not s:
        return _now_brt()
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=BRT)
        return dt
    except ValueError:
        return _now_brt()


from src.adapters.orm.mappings import start_mappers

from src.service_layer import services
from src.service_layer.unit_of_work import SqlAlchemyUnitOfWork, configure_uow


def create_app() -> Flask:
    start_mappers()
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "../../templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "../../static"),
    )
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod")
    db_url = os.environ.get("DATABASE_URL", "sqlite:///redteam.db")
    engine = configure_uow(db_url)

    from src.adapters.orm.mappings import metadata
    metadata.create_all(engine)
    _seed_admin(db_url)

    app.jinja_env.filters["enumerate"] = enumerate
    app.jinja_env.filters["brt"] = _fmt_brt

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(operator_bp, url_prefix="/operator")
    app.register_blueprint(api_bp, url_prefix="/api")
    return app


def _seed_admin(db_url):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.adapters.orm.mappings import AdminUser
    engine = create_engine(db_url)
    S = sessionmaker(bind=engine, expire_on_commit=False)
    with S() as s:
        if not s.query(AdminUser).first():
            s.add(AdminUser(
                id=str(uuid.uuid4()),
                username=os.environ.get("ADMIN_USERNAME", "admin"),
                hashed_password=services._hash_password(
                    os.environ.get("ADMIN_PASSWORD", "admin123")),
                full_name="Exercise Administrator",
            ))
            s.commit()


# ---------------------------------------------------------------------------
# Helpers — return plain dicts from within sessions
# ---------------------------------------------------------------------------

def _uow(): return SqlAlchemyUnitOfWork()

def _get_active_ex():
    with _uow() as uow:
        ex = uow.exercises.get_active()
        if not ex: return None
        return {"id": ex.id, "name": ex.name, "logo_path": ex.logo_path,
                "status": ex.status.value}

def _get_operators():
    with _uow() as uow:
        return [{"id": o.id, "username": o.username, "full_name": o.full_name}
                for o in uow.operators.list()]

def _get_exercise_full(exercise_id):
    with _uow() as uow:
        ex = uow.exercises.get(exercise_id)
        if not ex: return None, None
        ex_data = {
            "id": ex.id, "name": ex.name, "logo_path": ex.logo_path,
            "status": ex.status.value,
            "blue_teams": [
                {"id": bt.id, "name": bt.name, "has_it": bt.has_it,
                 "has_ot": bt.has_ot, "scenario_id": bt.scenario_id}
                for bt in ex.blue_teams
            ],
            "scenarios": [
                {
                    "id": s.id, "name": s.name,
                    "machines": [{"id": m.id, "name": m.name, "description": m.description}
                                 for m in s.machines],
                    "control_lines": [
                        {"id": cl.id, "name": cl.name, "domain_type": cl.domain_type.value,
                         "order": cl.order}
                        for cl in s.control_lines
                    ],
                }
                for s in ex.scenarios
            ],
            "assignments": [
                {"operator_id": a.operator_id, "blue_team_id": a.blue_team_id}
                for a in ex.assignments
            ],
        }
        ops = [{"id": o.id, "username": o.username, "full_name": o.full_name}
               for o in uow.operators.list()]
        return ex_data, ops


# ---------------------------------------------------------------------------
# Auth decorators
# ---------------------------------------------------------------------------

def admin_required(f):
    @wraps(f)
    def d(*a, **kw):
        if not session.get("admin_id"):
            return redirect(url_for("admin.login"))
        return f(*a, **kw)
    return d

def operator_required(f):
    @wraps(f)
    def d(*a, **kw):
        if not session.get("operator_id"):
            return redirect(url_for("operator.login"))
        return f(*a, **kw)
    return d


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------
from flask import Blueprint
public_bp = Blueprint("public", __name__)

@public_bp.route("/")
def index():
    ex = _get_active_ex()
    if not ex:
        return render_template("dashboard/no_exercise.html")
    try:
        data = services.get_dashboard_data(ex["id"], _uow())
        return render_template("dashboard/index.html", data=data)
    except Exception as e:
        return render_template("dashboard/no_exercise.html", error=str(e))


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
admin_bp = Blueprint("admin", __name__)

@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        admin_id = services.authenticate_admin(
            request.form["username"], request.form["password"], _uow())
        if admin_id:
            session["admin_id"] = admin_id
            # First-time wizard: redirect to setup if no exercise
            ex = _get_active_ex()
            return redirect(url_for("admin.setup_exercise") if not ex
                            else url_for("admin.dashboard"))
        flash("Invalid credentials", "error")
    return render_template("admin/login.html")

@admin_bp.route("/logout")
def logout():
    session.pop("admin_id", None)
    return redirect(url_for("admin.login"))

@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    exercise = _get_active_ex()
    operators = _get_operators()
    exercise_data = None
    if exercise:
        try:
            exercise_data = services.get_dashboard_data(exercise["id"], _uow())
        except Exception:
            exercise_data = exercise
    return render_template("admin/dashboard.html",
                           exercise=exercise, exercise_data=exercise_data,
                           operators=operators)

# ── Wizard Step 1: Create exercise ──
@admin_bp.route("/setup/exercise", methods=["GET", "POST"])
@admin_required
def setup_exercise():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        logo_path = None
        if "logo" in request.files:
            f = request.files["logo"]
            if f and f.filename:
                filename = secure_filename(f.filename)
                upload_dir = os.path.join(os.path.dirname(__file__), "../../static/img")
                os.makedirs(upload_dir, exist_ok=True)
                f.save(os.path.join(upload_dir, filename))
                logo_path = f"/static/img/{filename}"
        try:
            eid = services.create_exercise(name, logo_path, _uow())
            flash(f"Exercise '{name}' created!", "success")
            return redirect(url_for("admin.setup_operators", exercise_id=eid))
        except ValueError as e:
            flash(str(e), "error")
    return render_template("admin/wizard/step1_exercise.html")

# ── Wizard Step 2: Operators ──
@admin_bp.route("/setup/<exercise_id>/operators", methods=["GET", "POST"])
@admin_required
def setup_operators(exercise_id):
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        full_name = request.form.get("full_name", "").strip()
        try:
            services.create_operator(username, password, full_name, _uow())
            flash(f"Operator '{full_name}' created.", "success")
        except ValueError as e:
            flash(str(e), "error")
        return redirect(url_for("admin.setup_operators", exercise_id=exercise_id))
    operators = _get_operators()
    return render_template("admin/wizard/step2_operators.html",
                           exercise_id=exercise_id, operators=operators)

# ── Wizard Step 3: Blue Teams ──
@admin_bp.route("/setup/<exercise_id>/blueteams", methods=["GET", "POST"])
@admin_required
def setup_blueteams(exercise_id):
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        has_it = "has_it" in request.form
        has_ot = "has_ot" in request.form
        try:
            services.add_blue_team(exercise_id, name, has_it, has_ot, _uow())
            flash(f"Blue Team '{name}' added.", "success")
        except ValueError as e:
            flash(str(e), "error")
        return redirect(url_for("admin.setup_blueteams", exercise_id=exercise_id))
    ex_data, _ = _get_exercise_full(exercise_id)
    if not ex_data: abort(404)
    return render_template("admin/wizard/step3_blueteams.html",
                           exercise_id=exercise_id, blue_teams=ex_data["blue_teams"])

# ── Wizard Step 4: Scenarios ──
@admin_bp.route("/setup/<exercise_id>/scenarios")
@admin_required
def setup_scenarios(exercise_id):
    ex_data, _ = _get_exercise_full(exercise_id)
    if not ex_data: abort(404)
    return render_template("admin/wizard/step4_scenarios.html",
                           exercise_id=exercise_id, scenarios=ex_data["scenarios"])

# ── Wizard Step 5: Assignments ──
@admin_bp.route("/setup/<exercise_id>/assignments")
@admin_required
def setup_assignments(exercise_id):
    ex_data, ops = _get_exercise_full(exercise_id)
    if not ex_data: abort(404)
    return render_template("admin/wizard/step5_assignments.html",
                           exercise_id=exercise_id,
                           blue_teams=ex_data["blue_teams"],
                           scenarios=ex_data["scenarios"],
                           operators=ops,
                           assignments=ex_data["assignments"])

@admin_bp.route("/exercise/<exercise_id>/close", methods=["POST"])
@admin_required
def close_exercise(exercise_id):
    try:
        services.close_exercise(exercise_id, _uow())
        flash("Exercise closed. Final report generated.", "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/report/<exercise_id>")
@admin_required
def full_report(exercise_id):
    data = services.generate_full_report(exercise_id, _uow())
    return render_template("reports/full_report.html", data=data)


# ---------------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------------
operator_bp = Blueprint("operator", __name__)

@operator_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        op_id = services.authenticate_operator(
            request.form["username"], request.form["password"], _uow())
        if op_id:
            session["operator_id"] = op_id
            return redirect(url_for("operator.dashboard"))
        flash("Invalid credentials", "error")
    return render_template("operator/login.html")

@operator_bp.route("/logout")
def logout():
    session.pop("operator_id", None)
    return redirect(url_for("operator.login"))

@operator_bp.route("/dashboard")
@operator_required
def dashboard():
    ex = _get_active_ex()
    if not ex:
        return render_template("operator/no_exercise.html")
    data = services.get_operator_dashboard(ex["id"], session["operator_id"], _uow())
    return render_template("operator/dashboard.html", data=data)

@operator_bp.route("/attack/new", methods=["POST"])
@operator_required
def new_attack():
    ex = _get_active_ex()
    if not ex:
        flash("No active exercise", "error")
        return redirect(url_for("operator.dashboard"))
    try:
        occurred_str = request.form.get("occurred_at", "")
        occurred_at = (_parse_dt(occurred_str)
                       if occurred_str else _now_brt())
        services.register_attack(
            ex["id"], session["operator_id"],
            request.form["blue_team_id"], request.form["machine_id"],
            request.form["summary"].strip(), request.form["detail"].strip(),
            occurred_at, request.form.get("timezone_name", "UTC"), _uow(),
        )
        flash("Attack registered.", "success")
    except (ValueError, PermissionError) as e:
        flash(str(e), "error")
    return redirect(url_for("operator.dashboard"))

@operator_bp.route("/attack/<action_id>/edit", methods=["GET", "POST"])
@operator_required
def edit_attack(action_id):
    ex = _get_active_ex()
    if not ex: abort(404)
    with _uow() as uow:
        exercise = uow.exercises.get(ex["id"])
        if not exercise: abort(404)
        action = exercise._get_action(action_id)
        action_data = {
            "id": action.id, "blue_team_id": action.blue_team_id,
            "machine_id": action.machine_id, "summary": action.summary,
            "detail": action.detail, "occurred_at_str": action.occurred_at.isoformat()[:16],
        }
        machines = [{"id": m.id, "name": m.name}
                    for s in exercise.scenarios for m in s.machines]
        blue_teams = [{"id": bt.id, "name": bt.name} for bt in exercise.blue_teams]

    if request.method == "POST":
        try:
            occurred_at = _parse_dt(
                request.form["occurred_at"])
            services.update_attack(
                ex["id"], action_id, session["operator_id"],
                request.form["summary"].strip(), request.form["detail"].strip(),
                request.form["machine_id"], occurred_at, _uow(),
            )
            flash("Attack updated.", "success")
        except (ValueError, PermissionError) as e:
            flash(str(e), "error")
        return redirect(url_for("operator.dashboard"))
    return render_template("operator/edit_attack.html",
                           action=action_data, machines=machines, blue_teams=blue_teams)

@operator_bp.route("/attack/<action_id>/delete", methods=["POST"])
@operator_required
def delete_attack(action_id):
    ex = _get_active_ex()
    if not ex: abort(404)
    try:
        services.delete_attack(ex["id"], action_id, session["operator_id"], _uow())
        flash("Attack deleted.", "success")
    except (ValueError, PermissionError) as e:
        flash(str(e), "error")
    return redirect(url_for("operator.dashboard"))

@operator_bp.route("/control-line/achieve", methods=["POST"])
@operator_required
def achieve_control_line():
    ex = _get_active_ex()
    if not ex:
        flash("No active exercise", "error")
        return redirect(url_for("operator.dashboard"))
    try:
        services.achieve_control_line(
            ex["id"], request.form["control_line_id"],
            session["operator_id"], request.form["blue_team_id"],
            _now_brt(), _uow(),
        )
    except (ValueError, PermissionError) as e:
        flash(str(e), "error")
    return redirect(url_for("operator.dashboard"))

@operator_bp.route("/control-line/revert", methods=["POST"])
@operator_required
def revert_control_line():
    ex = _get_active_ex()
    if not ex:
        flash("No active exercise", "error")
        return redirect(url_for("operator.dashboard"))
    try:
        services.revert_control_line(
            ex["id"], request.form["control_line_id"],
            session["operator_id"], request.form["blue_team_id"], _uow(),
        )
    except (ValueError, PermissionError) as e:
        flash(str(e), "error")
    return redirect(url_for("operator.dashboard"))

@operator_bp.route("/report")
@operator_required
def report():
    ex = _get_active_ex()
    if not ex:
        return render_template("operator/no_exercise.html")
    with _uow() as uow:
        exercise = uow.exercises.get(ex["id"])
        if not exercise: return render_template("operator/no_exercise.html")
        my_bts = [
            {"id": bt.id, "name": bt.name}
            for bt in exercise.blue_teams
            if any(a.operator_id == session["operator_id"] and a.blue_team_id == bt.id
                   for a in exercise.assignments)
        ]
    return render_template("operator/report_form.html", blue_teams=my_bts)

@operator_bp.route("/report/generate", methods=["POST"])
@operator_required
def generate_report():
    ex = _get_active_ex()
    if not ex: abort(404)
    try:
        start_dt = _parse_dt(request.form["start_dt"])
        end_dt = _parse_dt(request.form["end_dt"])
        data = services.generate_report(
            ex["id"], session["operator_id"], request.form["blue_team_id"],
            start_dt, end_dt, _uow(),
        )
        return render_template("reports/operator_report.html", data=data)
    except Exception as e:
        flash(str(e), "error")
        return redirect(url_for("operator.report"))


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
api_bp = Blueprint("api", __name__)

@api_bp.route("/dashboard/live")
def live_dashboard():
    ex = _get_active_ex()
    if not ex:
        return jsonify({"error": "No active exercise"}), 404
    try:
        return jsonify(services.get_dashboard_data(ex["id"], _uow()))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def _admin_only():
    if not session.get("admin_id"):
        return jsonify({"error": "Unauthorized"}), 401
    return None

@api_bp.route("/exercise/<eid>/setup/blue-team", methods=["POST"])
def api_add_bt(eid):
    if (r := _admin_only()): return r
    d = request.get_json()
    try:
        bid = services.add_blue_team(eid, d["name"], d.get("has_it", True),
                                      d.get("has_ot", False), _uow())
        return jsonify({"id": bid}), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

@api_bp.route("/exercise/<eid>/setup/scenario", methods=["POST"])
def api_add_scenario(eid):
    if (r := _admin_only()): return r
    d = request.get_json()
    try:
        sid = services.add_scenario(eid, d["name"], _uow())
        return jsonify({"id": sid}), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

@api_bp.route("/exercise/<eid>/setup/scenario/<sid>/machine", methods=["POST"])
def api_add_machine(eid, sid):
    if (r := _admin_only()): return r
    d = request.get_json()
    try:
        mid = services.add_machine_to_scenario(eid, sid, d["name"],
                                               d.get("description", ""), _uow())
        return jsonify({"id": mid}), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

@api_bp.route("/exercise/<eid>/setup/scenario/<sid>/control-line", methods=["POST"])
def api_add_cl(eid, sid):
    if (r := _admin_only()): return r
    d = request.get_json()
    try:
        cl_id = services.add_control_line_to_scenario(
            eid, sid, d["name"], d.get("description", ""),
            d["domain_type"], d.get("order", 0), _uow())
        return jsonify({"id": cl_id}), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

@api_bp.route("/exercise/<eid>/setup/assign-operator", methods=["POST"])
def api_assign_op(eid):
    if (r := _admin_only()): return r
    d = request.get_json()
    try:
        services.assign_operator_to_bt(eid, d["operator_id"], d["blue_team_id"], _uow())
        return jsonify({"status": "ok"}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

@api_bp.route("/exercise/<eid>/setup/assign-scenario", methods=["POST"])
def api_assign_scenario(eid):
    if (r := _admin_only()): return r
    d = request.get_json()
    try:
        services.assign_scenario_to_bt(eid, d["scenario_id"], d["blue_team_id"], _uow())
        return jsonify({"status": "ok"}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


# ===========================================================================
# EDIT / DELETE ROUTES — Admin
# ===========================================================================

# ── Exercise ──
@admin_bp.route("/exercise/<eid>/edit", methods=["POST"])
@admin_required
def edit_exercise(eid):
    name = request.form.get("name", "").strip()
    logo_path = None
    if "logo" in request.files:
        f = request.files["logo"]
        if f and f.filename:
            from werkzeug.utils import secure_filename
            filename = secure_filename(f.filename)
            upload_dir = os.path.join(os.path.dirname(__file__), "../../static/img")
            os.makedirs(upload_dir, exist_ok=True)
            f.save(os.path.join(upload_dir, filename))
            logo_path = f"/static/img/{filename}"
    try:
        services.update_exercise(eid, name, logo_path, _uow())
        flash("Exercise updated.", "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("admin.dashboard"))


# ── Operators ──
@admin_bp.route("/operator/<op_id>/edit", methods=["POST"])
@admin_required
def edit_operator(op_id):
    full_name = request.form.get("full_name", "").strip()
    new_password = request.form.get("password", "").strip() or None
    try:
        services.update_operator(op_id, full_name, new_password, _uow())
        flash("Operator updated.", "success")
    except ValueError as e:
        flash(str(e), "error")
    ref = request.referrer or url_for("admin.dashboard")
    return redirect(ref)


@admin_bp.route("/operator/<op_id>/delete", methods=["POST"])
@admin_required
def delete_operator(op_id):
    try:
        services.delete_operator(op_id, _uow())
        flash("Operator deleted.", "success")
    except ValueError as e:
        flash(str(e), "error")
    ref = request.referrer or url_for("admin.dashboard")
    return redirect(ref)


# ── Blue Teams ──
@admin_bp.route("/exercise/<eid>/blueteam/<btid>/edit", methods=["POST"])
@admin_required
def edit_blueteam(eid, btid):
    try:
        services.update_blue_team(eid, btid,
            request.form["name"].strip(),
            "has_it" in request.form,
            "has_ot" in request.form,
            _uow())
        flash("Blue team updated.", "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("admin.setup_blueteams", exercise_id=eid))


@admin_bp.route("/exercise/<eid>/blueteam/<btid>/delete", methods=["POST"])
@admin_required
def delete_blueteam(eid, btid):
    try:
        services.delete_blue_team(eid, btid, _uow())
        flash("Blue team deleted.", "success")
    except Exception as e:
        flash(str(e), "error")
    return redirect(url_for("admin.setup_blueteams", exercise_id=eid))


# ── Scenarios ──
@admin_bp.route("/exercise/<eid>/scenario/<sid>/edit", methods=["POST"])
@admin_required
def edit_scenario(eid, sid):
    try:
        services.update_scenario(eid, sid, request.form["name"].strip(), _uow())
        flash("Scenario updated.", "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("admin.setup_scenarios", exercise_id=eid))


@admin_bp.route("/exercise/<eid>/scenario/<sid>/delete", methods=["POST"])
@admin_required
def delete_scenario(eid, sid):
    try:
        services.delete_scenario(eid, sid, _uow())
        flash("Scenario deleted.", "success")
    except Exception as e:
        flash(str(e), "error")
    return redirect(url_for("admin.setup_scenarios", exercise_id=eid))


# ── Machines (API) ──
@api_bp.route("/exercise/<eid>/setup/scenario/<sid>/machine/<mid>/edit", methods=["POST"])
def api_edit_machine(eid, sid, mid):
    if (r := _admin_only()): return r
    d = request.get_json()
    try:
        services.update_machine(eid, sid, mid, d["name"], d.get("description",""), _uow())
        return jsonify({"status": "ok"}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@api_bp.route("/exercise/<eid>/setup/scenario/<sid>/machine/<mid>/delete", methods=["POST"])
def api_delete_machine(eid, sid, mid):
    if (r := _admin_only()): return r
    try:
        services.delete_machine(eid, sid, mid, _uow())
        return jsonify({"status": "ok"}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


# ── Control Lines (API) ──
@api_bp.route("/exercise/<eid>/setup/scenario/<sid>/control-line/<clid>/edit", methods=["POST"])
def api_edit_cl(eid, sid, clid):
    if (r := _admin_only()): return r
    d = request.get_json()
    try:
        services.update_control_line(eid, sid, clid, d["name"],
                                     d.get("description",""), d["domain_type"], _uow())
        return jsonify({"status": "ok"}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@api_bp.route("/exercise/<eid>/setup/scenario/<sid>/control-line/<clid>/delete", methods=["POST"])
def api_delete_cl(eid, sid, clid):
    if (r := _admin_only()): return r
    try:
        services.delete_control_line(eid, sid, clid, _uow())
        return jsonify({"status": "ok"}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


# ── Assignments removal (API) ──
@api_bp.route("/exercise/<eid>/setup/remove-assignment", methods=["POST"])
def api_remove_assignment(eid):
    if (r := _admin_only()): return r
    d = request.get_json()
    try:
        services.remove_operator_from_bt(eid, d["operator_id"], d["blue_team_id"], _uow())
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ===========================================================================
# Control line toggle via AJAX (stays on page)
# ===========================================================================

@operator_bp.route("/control-line/toggle", methods=["POST"])
@operator_required
def toggle_control_line():
    """AJAX endpoint — returns JSON, no redirect."""
    ex = _get_active_ex()
    if not ex:
        return jsonify({"error": "No active exercise"}), 400
    cl_id = request.form.get("control_line_id")
    bt_id = request.form.get("blue_team_id")
    action = request.form.get("action")  # "achieve" or "revert"
    operator_id = session["operator_id"]
    try:
        if action == "achieve":
            services.achieve_control_line(
                ex["id"], cl_id, operator_id, bt_id,
                _now_brt(), _uow(),
            )
        else:
            services.revert_control_line(ex["id"], cl_id, operator_id, bt_id, _uow())
        return jsonify({"status": "ok", "action": action}), 200
    except (ValueError, PermissionError) as e:
        return jsonify({"error": str(e)}), 400

@api_bp.route('/exercise/<eid>/setup/scenario/<sid>/edit', methods=['POST'])
def api_edit_scenario(eid, sid):
    if (r := _admin_only()): return r
    d = request.get_json()
    try:
        services.update_scenario(eid, sid, d['name'], _uow())
        return jsonify({'status': 'ok'}), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

@api_bp.route('/exercise/<eid>/setup/scenario/<sid>/delete', methods=['POST'])
def api_delete_scenario(eid, sid):
    if (r := _admin_only()): return r
    try:
        services.delete_scenario(eid, sid, _uow())
        return jsonify({'status': 'ok'}), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
