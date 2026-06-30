"""
Service Layer — all use cases.
Works exclusively with primitives at its API boundary.
Depends on AbstractUnitOfWork only.
"""

from __future__ import annotations
import uuid, hashlib, hmac, os
from datetime import datetime, timezone
from typing import Optional

from src.domain.model import (
    Exercise, ExerciseStatus, Operator, BlueTeam, Scenario,
    TargetMachine, ControlLine, DomainType, OperatorBTAssignment,
)
from src.service_layer.unit_of_work import AbstractUnitOfWork

from datetime import timedelta
BRT = timezone(timedelta(hours=-3), name='BRT')

def _now_brt():
    return datetime.now(tz=BRT)


def _as_utc(dt: datetime) -> datetime:
    """Normalize datetime to UTC-aware. SQLite returns naive datetimes; this fixes that."""
    if dt is None:
        return dt
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt



# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    digest = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}${digest}"

def _verify_password(password: str, hashed: str) -> bool:
    try:
        salt, digest = hashed.split("$", 1)
        expected = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
        return hmac.compare_digest(expected, digest)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Exercise lifecycle
# ---------------------------------------------------------------------------

def create_exercise(name: str, logo_path: Optional[str], uow: AbstractUnitOfWork) -> str:
    with uow:
        if uow.exercises.get_active():
            raise ValueError("There is already an active exercise.")
        ex = Exercise(
            id=str(uuid.uuid4()), name=name, logo_path=logo_path,
            status=ExerciseStatus.ACTIVE,
            created_at=_now_brt(),
        )
        uow.exercises.add(ex)
        uow.commit()
        return ex.id


def close_exercise(exercise_id: str, uow: AbstractUnitOfWork) -> datetime:
    with uow:
        ex = _get_or_raise(exercise_id, uow)
        closed_at = ex.close()
        uow.commit()
        return closed_at


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

def create_operator(username: str, password: str, full_name: str,
                    uow: AbstractUnitOfWork) -> str:
    with uow:
        if uow.operators.get_by_username(username):
            raise ValueError(f"Username '{username}' already taken.")
        op = Operator(
            id=str(uuid.uuid4()), username=username,
            hashed_password=_hash_password(password), full_name=full_name,
        )
        uow.operators.add(op)
        uow.commit()
        return op.id


def authenticate_operator(username: str, password: str,
                           uow: AbstractUnitOfWork) -> Optional[str]:
    with uow:
        op = uow.operators.get_by_username(username)
        if op and _verify_password(password, op.hashed_password):
            return op.id
        return None


def authenticate_admin(username: str, password: str,
                        uow: AbstractUnitOfWork) -> Optional[str]:
    with uow:
        admin = uow.admins.get_by_username(username)
        if admin and _verify_password(password, admin.hashed_password):
            return admin.id
        return None


# ---------------------------------------------------------------------------
# Blue Teams
# ---------------------------------------------------------------------------

def add_blue_team(exercise_id: str, name: str, has_it: bool, has_ot: bool,
                  uow: AbstractUnitOfWork) -> str:
    with uow:
        ex = _get_or_raise(exercise_id, uow)
        bt = BlueTeam(id=str(uuid.uuid4()), exercise_id=exercise_id,
                      name=name, has_it=has_it, has_ot=has_ot)
        ex.add_blue_team(bt)
        uow.commit()
        return bt.id


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def add_scenario(exercise_id: str, name: str, uow: AbstractUnitOfWork) -> str:
    with uow:
        ex = _get_or_raise(exercise_id, uow)
        scenario = Scenario(id=str(uuid.uuid4()), exercise_id=exercise_id, name=name)
        ex.add_scenario(scenario)
        uow.commit()
        return scenario.id


def add_machine_to_scenario(exercise_id: str, scenario_id: str, name: str,
                             description: str, uow: AbstractUnitOfWork) -> str:
    with uow:
        ex = _get_or_raise(exercise_id, uow)
        scenario = next((s for s in ex.scenarios if s.id == scenario_id), None)
        if not scenario:
            raise ValueError(f"Scenario {scenario_id!r} not found.")
        machine = TargetMachine(id=str(uuid.uuid4()), scenario_id=scenario_id,
                                name=name, description=description)
        scenario.add_machine(machine)
        uow.commit()
        return machine.id


def add_control_line_to_scenario(exercise_id: str, scenario_id: str, name: str,
                                  description: str, domain_type: str, order: int,
                                  uow: AbstractUnitOfWork) -> str:
    with uow:
        ex = _get_or_raise(exercise_id, uow)
        scenario = next((s for s in ex.scenarios if s.id == scenario_id), None)
        if not scenario:
            raise ValueError(f"Scenario {scenario_id!r} not found.")
        try:
            dt = DomainType(domain_type.upper())
        except ValueError:
            raise ValueError(f"domain_type must be IT or OT, got {domain_type!r}")
        cl = ControlLine(id=str(uuid.uuid4()), scenario_id=scenario_id,
                         name=name, description=description, domain_type=dt, order=order)
        scenario.add_control_line(cl)
        uow.commit()
        return cl.id


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------

def assign_operator_to_bt(exercise_id: str, operator_id: str, blue_team_id: str,
                           uow: AbstractUnitOfWork):
    with uow:
        ex = _get_or_raise(exercise_id, uow)
        op = uow.operators.get(operator_id)
        if not op:
            raise ValueError(f"Operator {operator_id!r} not found.")
        ex.add_operator(op)
        ex.assign_operator_to_bt(operator_id, blue_team_id)
        _persist_assignment(uow, exercise_id, operator_id, blue_team_id)
        uow.commit()


def assign_scenario_to_bt(exercise_id: str, scenario_id: str, blue_team_id: str,
                           uow: AbstractUnitOfWork):
    with uow:
        ex = _get_or_raise(exercise_id, uow)
        ex.assign_scenario_to_bt(scenario_id, blue_team_id)
        uow.commit()


def _persist_assignment(uow, exercise_id, operator_id, blue_team_id):
    try:
        from src.service_layer.unit_of_work import SqlAlchemyUnitOfWork
        if isinstance(uow, SqlAlchemyUnitOfWork):
            from src.adapters.orm.mappings import operator_bt_assignments_table
            from sqlalchemy import select
            existing = uow.session.execute(
                select(operator_bt_assignments_table).where(
                    operator_bt_assignments_table.c.exercise_id == exercise_id,
                    operator_bt_assignments_table.c.operator_id == operator_id,
                    operator_bt_assignments_table.c.blue_team_id == blue_team_id,
                )
            ).first()
            if not existing:
                uow.session.execute(
                    operator_bt_assignments_table.insert().values(
                        id=str(uuid.uuid4()),
                        exercise_id=exercise_id,
                        operator_id=operator_id,
                        blue_team_id=blue_team_id,
                    )
                )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Attack actions
# ---------------------------------------------------------------------------

def register_attack(exercise_id: str, operator_id: str, blue_team_id: str,
                    machine_id: str, summary: str, detail: str,
                    occurred_at: datetime, timezone_name: str,
                    uow: AbstractUnitOfWork) -> str:
    with uow:
        ex = _get_or_raise(exercise_id, uow)
        action = ex.register_attack(operator_id, blue_team_id, machine_id,
                                    summary, detail, occurred_at, timezone_name)
        uow.commit()
        return action.id


def update_attack(exercise_id: str, action_id: str, operator_id: str,
                  summary: str, detail: str, machine_id: str,
                  occurred_at: datetime, uow: AbstractUnitOfWork):
    with uow:
        ex = _get_or_raise(exercise_id, uow)
        ex.update_attack(action_id, operator_id, summary, detail, machine_id, occurred_at)
        uow.commit()


def delete_attack(exercise_id: str, action_id: str, operator_id: str,
                  uow: AbstractUnitOfWork):
    with uow:
        ex = _get_or_raise(exercise_id, uow)
        ex.delete_attack(action_id, operator_id)
        uow.commit()


def achieve_control_line(exercise_id: str, control_line_id: str, operator_id: str,
                         blue_team_id: str, at: datetime, uow: AbstractUnitOfWork) -> str:
    with uow:
        ex = _get_or_raise(exercise_id, uow)
        ach = ex.achieve_control_line(control_line_id, operator_id, blue_team_id, at)
        uow.commit()
        return ach.id


def revert_control_line(exercise_id: str, control_line_id: str, operator_id: str,
                        blue_team_id: str, uow: AbstractUnitOfWork):
    with uow:
        ex = _get_or_raise(exercise_id, uow)
        ex.revert_control_line(control_line_id, operator_id, blue_team_id)
        uow.commit()


# ---------------------------------------------------------------------------
# Read queries
# ---------------------------------------------------------------------------

def get_dashboard_data(exercise_id: str, uow: AbstractUnitOfWork) -> dict:
    with uow:
        ex = _get_or_raise(exercise_id, uow)

        # Leaderboard
        leaderboard = []
        for entry in ex.leaderboard():
            op = uow.operators.get(entry["operator_id"])
            bt = next((b for b in ex.blue_teams if b.id == entry["blue_team_id"]), None)
            leaderboard.append({
                "operator_name": op.full_name if op else "?",
                "blue_team_name": bt.name if bt else "?",
                "action_count": entry["action_count"],
            })

        # BT statuses grouped by scenario
        bt_statuses = []
        for bt in ex.blue_teams:
            scenario = ex.get_scenario_for_bt(bt.id)
            scenario_data = None
            if scenario:
                it_lines = [cl for cl in scenario.control_lines if cl.domain_type == DomainType.IT]
                ot_lines = [cl for cl in scenario.control_lines if cl.domain_type == DomainType.OT]

                # Aggregate progress across all operators assigned to this BT
                def bt_progress(lines):
                    if not lines: return {"achieved": 0, "total": 0, "percent": 0.0}
                    # A line is "achieved" if ANY operator on that BT achieved it
                    bt_assignments = [a for a in ex.assignments if a.blue_team_id == bt.id]
                    achieved = sum(
                        1 for cl in lines
                        if any(ex.is_cl_achieved(cl.id, a.operator_id, bt.id)
                               for a in bt_assignments)
                    )
                    total = len(lines)
                    return {"achieved": achieved, "total": total,
                            "percent": round(100 * achieved / total, 1)}

                cl_details = []
                for cl in scenario.control_lines:
                    bt_assignments = [a for a in ex.assignments if a.blue_team_id == bt.id]
                    ach = next(
                        (a for a in ex.achievements
                         if a.control_line_id == cl.id and a.blue_team_id == bt.id),
                        None
                    )
                    cl_details.append({
                        "id": cl.id,
                        "name": cl.name,
                        "domain_type": cl.domain_type.value,
                        "achieved": ach is not None,
                        "achieved_at": ach.achieved_at.isoformat() if ach else None,
                    })

                it_prog = bt_progress(it_lines)
                ot_prog = bt_progress(ot_lines)
                scenario_data = {
                    "id": scenario.id,
                    "name": scenario.name,
                    "it_progress": it_prog,
                    "ot_progress": ot_prog,
                    "overall_percent": _overall(it_prog, ot_prog),
                    "control_lines": cl_details,
                }

            # Operators for this BT
            bt_ops = [
                {"operator_id": a.operator_id,
                 "operator_name": (uow.operators.get(a.operator_id).full_name
                                   if uow.operators.get(a.operator_id) else "?")}
                for a in ex.assignments if a.blue_team_id == bt.id
            ]

            # Count all attacks on this BT
            bt_attack_count = sum(1 for a in ex.actions if a.blue_team_id == bt.id)

            bt_statuses.append({
                "blue_team_id": bt.id,
                "blue_team_name": bt.name,
                "has_it": bt.has_it,
                "has_ot": bt.has_ot,
                "scenario": scenario_data,
                "operators": bt_ops,
                "attack_count": bt_attack_count,
            })

        # Recent feed
        recent = []
        for action in ex.recent_actions(20):
            op = uow.operators.get(action.operator_id)
            bt = next((b for b in ex.blue_teams if b.id == action.blue_team_id), None)
            # Find machine across all scenarios
            machine = None
            for s in ex.scenarios:
                machine = next((m for m in s.machines if m.id == action.machine_id), None)
                if machine:
                    break
            recent.append({
                "id": action.id,
                "summary": action.summary,
                "operator_name": op.full_name if op else "?",
                "blue_team_name": bt.name if bt else "?",
                "machine_name": machine.name if machine else "?",
                "occurred_at": action.occurred_at.isoformat(),
                "timezone_name": action.timezone_name,
            })

        return {
            "exercise_id": ex.id,
            "exercise_name": ex.name,
            "logo_path": ex.logo_path,
            "status": ex.status.value,
            "blue_team_statuses": bt_statuses,
            "leaderboard": leaderboard,
            "recent_actions": recent,
        }


def get_operator_dashboard(exercise_id: str, operator_id: str,
                           uow: AbstractUnitOfWork) -> dict:
    with uow:
        ex = _get_or_raise(exercise_id, uow)
        op = uow.operators.get(operator_id)
        if not op:
            raise ValueError("Operator not found.")

        my_bts = [
            bt for bt in ex.blue_teams
            if OperatorBTAssignment(operator_id=operator_id, blue_team_id=bt.id)
            in ex.assignments
        ]

        bt_details = []
        for bt in my_bts:
            scenario = ex.get_scenario_for_bt(bt.id)
            scenario_data = None
            if scenario:
                it_prog = ex.control_line_progress(operator_id, bt.id, DomainType.IT, scenario.id)
                ot_prog = ex.control_line_progress(operator_id, bt.id, DomainType.OT, scenario.id)
                lines = []
                for cl in scenario.control_lines:
                    ach = ex._find_achievement(cl.id, operator_id, bt.id)
                    lines.append({
                        "id": cl.id,
                        "name": cl.name,
                        "description": cl.description,
                        "domain_type": cl.domain_type.value,
                        "achieved": ach is not None,
                        "achieved_at": ach.achieved_at.isoformat() if ach else None,
                    })
                scenario_data = {
                    "id": scenario.id,
                    "name": scenario.name,
                    "it_progress": it_prog,
                    "ot_progress": ot_prog,
                    "overall_percent": _overall(it_prog, ot_prog),
                    "control_lines": lines,
                    "machines": [
                        {"id": m.id, "name": m.name, "description": m.description}
                        for m in scenario.machines
                    ],
                }
            bt_details.append({
                "blue_team_id": bt.id,
                "blue_team_name": bt.name,
                "has_it": bt.has_it,
                "has_ot": bt.has_ot,
                "scenario": scenario_data,
            })

        my_actions = sorted(
            [a for a in ex.actions if a.operator_id == operator_id],
            key=lambda a: a.occurred_at, reverse=True,
        )
        actions_data = []
        for a in my_actions:
            bt = next((b for b in ex.blue_teams if b.id == a.blue_team_id), None)
            machine = None
            for s in ex.scenarios:
                machine = next((m for m in s.machines if m.id == a.machine_id), None)
                if machine: break
            actions_data.append({
                "id": a.id,
                "blue_team_id": a.blue_team_id,
                "blue_team_name": bt.name if bt else "?",
                "machine_id": a.machine_id,
                "machine_name": machine.name if machine else "?",
                "summary": a.summary,
                "detail": a.detail,
                "occurred_at": a.occurred_at.isoformat(),
                "timezone_name": a.timezone_name,
            })

        return {
            "exercise_id": ex.id,
            "exercise_name": ex.name,
            "logo_path": ex.logo_path,
            "operator_id": operator_id,
            "operator_name": op.full_name,
            "blue_teams": bt_details,
            "actions": actions_data,
        }


def generate_report(exercise_id: str, operator_id: str, blue_team_id: str,
                    start_dt: datetime, end_dt: datetime,
                    uow: AbstractUnitOfWork) -> dict:
    with uow:
        ex = _get_or_raise(exercise_id, uow)
        op = uow.operators.get(operator_id)
        bt = next((b for b in ex.blue_teams if b.id == blue_team_id), None)
        if not bt:
            raise ValueError(f"BlueTeam {blue_team_id!r} not found.")
        scenario = ex.get_scenario_for_bt(blue_team_id)

        actions_in_window = sorted([
            a for a in ex.actions
            if a.operator_id == operator_id and a.blue_team_id == blue_team_id
            and start_dt <= _as_utc(a.occurred_at) <= end_dt
        ], key=lambda a: a.occurred_at)

        achieved_lines = []
        if scenario:
            for cl in scenario.control_lines:
                ach = ex._find_achievement(cl.id, operator_id, blue_team_id)
                if ach:
                    achieved_lines.append({
                        "name": cl.name,
                        "description": cl.description,
                        "domain_type": cl.domain_type.value,
                        "achieved_at": ach.achieved_at.isoformat(),
                    })

        return {
            "exercise_name": ex.name,
            "operator_name": op.full_name if op else "?",
            "blue_team_name": bt.name,
            "scenario_name": scenario.name if scenario else "N/A",
            "start_dt": start_dt.isoformat(),
            "end_dt": end_dt.isoformat(),
            "achieved_control_lines": achieved_lines,
            "actions": [
                {
                    "occurred_at": a.occurred_at.isoformat(),
                    "timezone_name": a.timezone_name,
                    "machine_name": _find_machine_name(ex, a.machine_id),
                    "summary": a.summary,
                    "detail": a.detail,
                }
                for a in actions_in_window
            ],
        }


def generate_full_report(exercise_id: str, uow: AbstractUnitOfWork) -> dict:
    with uow:
        ex = _get_or_raise(exercise_id, uow)
        bt_reports = []
        for bt in ex.blue_teams:
            scenario = ex.get_scenario_for_bt(bt.id)
            bt_actions = sorted(
                [a for a in ex.actions if a.blue_team_id == bt.id],
                key=lambda a: a.occurred_at,
            )
            bt_achievements = [
                {
                    "control_line_name": _find_cl_name(ex, ach.control_line_id),
                    "domain_type": _find_cl_domain(ex, ach.control_line_id),
                    "operator_name": (uow.operators.get(ach.operator_id).full_name
                                      if uow.operators.get(ach.operator_id) else "?"),
                    "achieved_at": ach.achieved_at.isoformat(),
                }
                for ach in ex.achievements if ach.blue_team_id == bt.id
            ]
            bt_reports.append({
                "blue_team_name": bt.name,
                "scenario_name": scenario.name if scenario else "N/A",
                "achievements": bt_achievements,
                "actions": [
                    {
                        "occurred_at": a.occurred_at.isoformat(),
                        "timezone_name": a.timezone_name,
                        "operator_name": (uow.operators.get(a.operator_id).full_name
                                          if uow.operators.get(a.operator_id) else "?"),
                        "machine_name": _find_machine_name(ex, a.machine_id),
                        "summary": a.summary,
                        "detail": a.detail,
                    }
                    for a in bt_actions
                ],
            })

        return {
            "exercise_name": ex.name,
            "created_at": ex.created_at.isoformat(),
            "closed_at": ex.closed_at.isoformat() if ex.closed_at else None,
            "blue_teams": bt_reports,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_or_raise(exercise_id: str, uow: AbstractUnitOfWork) -> "Exercise":
    ex = uow.exercises.get(exercise_id)
    if not ex:
        raise ValueError(f"Exercise {exercise_id!r} not found.")
    return ex


def _overall(it_prog: dict, ot_prog: dict) -> float:
    total = it_prog["total"] + ot_prog["total"]
    if total == 0:
        return 0.0
    return round(100 * (it_prog["achieved"] + ot_prog["achieved"]) / total, 1)


def _find_machine_name(ex, machine_id: str) -> str:
    for s in ex.scenarios:
        m = next((m for m in s.machines if m.id == machine_id), None)
        if m:
            return m.name
    return "?"


def _find_cl_name(ex, cl_id: str) -> str:
    for s in ex.scenarios:
        cl = next((c for c in s.control_lines if c.id == cl_id), None)
        if cl:
            return cl.name
    return "?"


def _find_cl_domain(ex, cl_id: str) -> str:
    for s in ex.scenarios:
        cl = next((c for c in s.control_lines if c.id == cl_id), None)
        if cl:
            return cl.domain_type.value
    return "?"


# ---------------------------------------------------------------------------
# Edit / Delete — Exercise
# ---------------------------------------------------------------------------

def update_exercise(exercise_id: str, name: str, logo_path,
                    uow: AbstractUnitOfWork):
    with uow:
        ex = _get_or_raise(exercise_id, uow)
        ex.name = name
        if logo_path is not None:
            ex.logo_path = logo_path
        uow.commit()


# ---------------------------------------------------------------------------
# Edit / Delete — Operators
# ---------------------------------------------------------------------------

def update_operator(operator_id: str, full_name: str, new_password,
                    uow: AbstractUnitOfWork):
    with uow:
        op = uow.operators.get(operator_id)
        if not op:
            raise ValueError("Operator not found.")
        op.full_name = full_name
        if new_password:
            op.hashed_password = _hash_password(new_password)
        uow.commit()


def delete_operator(operator_id: str, uow: AbstractUnitOfWork):
    with uow:
        from src.service_layer.unit_of_work import SqlAlchemyUnitOfWork
        if isinstance(uow, SqlAlchemyUnitOfWork):
            from src.adapters.orm.mappings import operator_bt_assignments_table
            uow.session.execute(
                operator_bt_assignments_table.delete().where(
                    operator_bt_assignments_table.c.operator_id == operator_id
                )
            )
            op = uow.operators.get(operator_id)
            if op:
                uow.session.delete(op)
        uow.commit()


# ---------------------------------------------------------------------------
# Edit / Delete — Blue Teams
# ---------------------------------------------------------------------------

def update_blue_team(exercise_id: str, blue_team_id: str, name: str,
                     has_it: bool, has_ot: bool, uow: AbstractUnitOfWork):
    with uow:
        ex = _get_or_raise(exercise_id, uow)
        bt = next((b for b in ex.blue_teams if b.id == blue_team_id), None)
        if not bt:
            raise ValueError("Blue team not found.")
        bt.name = name
        bt.has_it = has_it
        bt.has_ot = has_ot
        uow.commit()


def delete_blue_team(exercise_id: str, blue_team_id: str, uow: AbstractUnitOfWork):
    with uow:
        ex = _get_or_raise(exercise_id, uow)
        bt = next((b for b in ex.blue_teams if b.id == blue_team_id), None)
        if not bt:
            raise ValueError("Blue team not found.")
        ex.blue_teams.remove(bt)
        from src.service_layer.unit_of_work import SqlAlchemyUnitOfWork
        if isinstance(uow, SqlAlchemyUnitOfWork):
            from src.adapters.orm.mappings import operator_bt_assignments_table
            uow.session.execute(
                operator_bt_assignments_table.delete().where(
                    operator_bt_assignments_table.c.blue_team_id == blue_team_id
                )
            )
            uow.session.delete(bt)
        uow.commit()


# ---------------------------------------------------------------------------
# Edit / Delete — Scenarios, Machines, Control Lines
# ---------------------------------------------------------------------------

def update_scenario(exercise_id: str, scenario_id: str, name: str,
                    uow: AbstractUnitOfWork):
    with uow:
        ex = _get_or_raise(exercise_id, uow)
        sc = next((s for s in ex.scenarios if s.id == scenario_id), None)
        if not sc:
            raise ValueError("Scenario not found.")
        sc.name = name
        uow.commit()


def delete_scenario(exercise_id: str, scenario_id: str, uow: AbstractUnitOfWork):
    with uow:
        ex = _get_or_raise(exercise_id, uow)
        sc = next((s for s in ex.scenarios if s.id == scenario_id), None)
        if not sc:
            raise ValueError("Scenario not found.")
        ex.scenarios.remove(sc)
        from src.service_layer.unit_of_work import SqlAlchemyUnitOfWork
        if isinstance(uow, SqlAlchemyUnitOfWork):
            uow.session.delete(sc)
        uow.commit()


def update_machine(exercise_id: str, scenario_id: str, machine_id: str,
                   name: str, description: str, uow: AbstractUnitOfWork):
    with uow:
        ex = _get_or_raise(exercise_id, uow)
        sc = next((s for s in ex.scenarios if s.id == scenario_id), None)
        if not sc:
            raise ValueError("Scenario not found.")
        m = next((m for m in sc.machines if m.id == machine_id), None)
        if not m:
            raise ValueError("Machine not found.")
        m.name = name
        m.description = description
        uow.commit()


def delete_machine(exercise_id: str, scenario_id: str, machine_id: str,
                   uow: AbstractUnitOfWork):
    with uow:
        ex = _get_or_raise(exercise_id, uow)
        sc = next((s for s in ex.scenarios if s.id == scenario_id), None)
        if not sc:
            raise ValueError("Scenario not found.")
        m = next((m for m in sc.machines if m.id == machine_id), None)
        if not m:
            raise ValueError("Machine not found.")
        sc.machines.remove(m)
        from src.service_layer.unit_of_work import SqlAlchemyUnitOfWork
        if isinstance(uow, SqlAlchemyUnitOfWork):
            uow.session.delete(m)
        uow.commit()


def update_control_line(exercise_id: str, scenario_id: str, cl_id: str,
                        name: str, description: str, domain_type: str,
                        uow: AbstractUnitOfWork):
    with uow:
        ex = _get_or_raise(exercise_id, uow)
        sc = next((s for s in ex.scenarios if s.id == scenario_id), None)
        if not sc:
            raise ValueError("Scenario not found.")
        cl = next((c for c in sc.control_lines if c.id == cl_id), None)
        if not cl:
            raise ValueError("Control line not found.")
        cl.name = name
        cl.description = description
        cl.domain_type = DomainType(domain_type.upper())
        uow.commit()


def delete_control_line(exercise_id: str, scenario_id: str, cl_id: str,
                        uow: AbstractUnitOfWork):
    with uow:
        ex = _get_or_raise(exercise_id, uow)
        sc = next((s for s in ex.scenarios if s.id == scenario_id), None)
        if not sc:
            raise ValueError("Scenario not found.")
        cl = next((c for c in sc.control_lines if c.id == cl_id), None)
        if not cl:
            raise ValueError("Control line not found.")
        sc.control_lines.remove(cl)
        from src.service_layer.unit_of_work import SqlAlchemyUnitOfWork
        if isinstance(uow, SqlAlchemyUnitOfWork):
            uow.session.delete(cl)
        uow.commit()


# ---------------------------------------------------------------------------
# Remove assignment
# ---------------------------------------------------------------------------

def remove_operator_from_bt(exercise_id: str, operator_id: str,
                             blue_team_id: str, uow: AbstractUnitOfWork):
    with uow:
        from src.service_layer.unit_of_work import SqlAlchemyUnitOfWork
        if isinstance(uow, SqlAlchemyUnitOfWork):
            from src.adapters.orm.mappings import operator_bt_assignments_table
            uow.session.execute(
                operator_bt_assignments_table.delete().where(
                    operator_bt_assignments_table.c.exercise_id == exercise_id,
                    operator_bt_assignments_table.c.operator_id == operator_id,
                    operator_bt_assignments_table.c.blue_team_id == blue_team_id,
                )
            )
        uow.commit()
