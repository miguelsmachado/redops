"""
Domain Model — Red Team Platform
Following Architecture Patterns with Python:
  - Entities: Exercise (aggregate root), Operator, BlueTeam, Scenario,
               TargetMachine, ControlLine, ControlLineAchievement, AttackAction
  - Value Objects: OperatorBTAssignment, DomainType
  - Domain Events raised by the Exercise aggregate
"""

from __future__ import annotations
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Set
from sqlalchemy.orm import reconstructor


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DomainType(str, Enum):
    IT = "IT"
    OT = "OT"


class ExerciseStatus(str, Enum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


# ---------------------------------------------------------------------------
# Domain Events
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AttackRegistered:
    exercise_id: str
    action_id: str
    operator_id: str
    blue_team_id: str
    machine_id: str
    summary: str
    occurred_at: datetime

@dataclass(frozen=True)
class AttackUpdated:
    action_id: str
    exercise_id: str

@dataclass(frozen=True)
class AttackDeleted:
    action_id: str
    exercise_id: str

@dataclass(frozen=True)
class ControlLineAchieved:
    exercise_id: str
    control_line_id: str
    operator_id: str
    blue_team_id: str
    achieved_at: datetime

@dataclass(frozen=True)
class ControlLineReverted:
    exercise_id: str
    control_line_id: str

@dataclass(frozen=True)
class ExerciseClosed:
    exercise_id: str
    closed_at: datetime


# ---------------------------------------------------------------------------
# Value Objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OperatorBTAssignment:
    operator_id: str
    blue_team_id: str


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------

class Operator:
    def __init__(self, id: str, username: str, hashed_password: str, full_name: str):
        self.id = id
        self.username = username
        self.hashed_password = hashed_password
        self.full_name = full_name

    def __eq__(self, other):
        return isinstance(other, Operator) and self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return f"Operator(id={self.id!r}, username={self.username!r})"


class TargetMachine:
    """Belongs to a Scenario (template). Neutral — no IT/OT classification."""

    def __init__(self, id: str, scenario_id: str, name: str, description: str = ""):
        self.id = id
        self.scenario_id = scenario_id
        self.name = name
        self.description = description

    def __eq__(self, other):
        return isinstance(other, TargetMachine) and self.id == other.id

    def __hash__(self):
        return hash(self.id)


class ControlLine:
    """
    Attack-path milestone. Belongs to a Scenario (template).
    Classified as IT or OT.
    Achievement state is tracked via ControlLineAchievement records —
    NOT stored in-memory on the object (avoids ORM reconstructor issues).
    """

    def __init__(self, id: str, scenario_id: str, name: str,
                 description: str, domain_type: DomainType, order: int = 0):
        self.id = id
        self.scenario_id = scenario_id
        self.name = name
        self.description = description
        self.domain_type = domain_type
        self.order = order

    def __eq__(self, other):
        return isinstance(other, ControlLine) and self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return f"ControlLine(id={self.id!r}, name={self.name!r})"


class ControlLineAchievement:
    """Persistent record: (ControlLine, operator, BlueTeam) achieved at timestamp."""

    def __init__(self, id: str, control_line_id: str, operator_id: str,
                 blue_team_id: str, achieved_at: datetime):
        self.id = id
        self.control_line_id = control_line_id
        self.operator_id = operator_id
        self.blue_team_id = blue_team_id
        self.achieved_at = achieved_at

    def __eq__(self, other):
        return isinstance(other, ControlLineAchievement) and self.id == other.id

    def __hash__(self):
        return hash(self.id)


class Scenario:
    """
    Template: named collection of TargetMachines + ControlLines.
    Multiple BlueTeal teams can share the same Scenario template,
    each with independent progress tracked via ControlLineAchievements.
    """

    def __init__(self, id: str, exercise_id: str, name: str):
        self.id = id
        self.exercise_id = exercise_id
        self.name = name
        self.machines: List[TargetMachine] = []
        self.control_lines: List[ControlLine] = []

    def add_machine(self, machine: TargetMachine):
        self.machines.append(machine)

    def add_control_line(self, cl: ControlLine):
        self.control_lines.append(cl)

    def __eq__(self, other):
        return isinstance(other, Scenario) and self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return f"Scenario(id={self.id!r}, name={self.name!r})"


class BlueTeam:
    """Defending team. Has exactly one Scenario assigned (or None during setup)."""

    def __init__(self, id: str, exercise_id: str, name: str,
                 has_it: bool = True, has_ot: bool = False,
                 scenario_id: Optional[str] = None):
        self.id = id
        self.exercise_id = exercise_id
        self.name = name
        self.has_it = has_it
        self.has_ot = has_ot
        self.scenario_id = scenario_id   # FK to Scenario

    def assign_scenario(self, scenario_id: str):
        self.scenario_id = scenario_id

    def __eq__(self, other):
        return isinstance(other, BlueTeam) and self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return f"BlueTeam(id={self.id!r}, name={self.name!r})"


class AttackAction:
    """Single attack step by an operator against a target machine."""

    def __init__(self, id: str, exercise_id: str, operator_id: str,
                 blue_team_id: str, machine_id: str, summary: str,
                 detail: str, occurred_at: datetime, timezone_name: str = "UTC"):
        self.id = id
        self.exercise_id = exercise_id
        self.operator_id = operator_id
        self.blue_team_id = blue_team_id
        self.machine_id = machine_id
        self.summary = summary
        self.detail = detail
        self.occurred_at = occurred_at
        self.timezone_name = timezone_name

    def update(self, summary: str, detail: str, machine_id: str, occurred_at: datetime):
        self.summary = summary
        self.detail = detail
        self.machine_id = machine_id
        self.occurred_at = occurred_at

    def __eq__(self, other):
        return isinstance(other, AttackAction) and self.id == other.id

    def __hash__(self):
        return hash(self.id)


# ---------------------------------------------------------------------------
# Aggregate Root — Exercise
# ---------------------------------------------------------------------------

class Exercise:
    """
    Root aggregate. All mutations go through Exercise methods.
    """

    def __init__(self, id: str, name: str, logo_path: Optional[str],
                 status: ExerciseStatus, created_at: datetime,
                 closed_at: Optional[datetime] = None):
        self.id = id
        self.name = name
        self.logo_path = logo_path
        self.status = status
        self.created_at = created_at
        self.closed_at = closed_at
        self._init_collections()

    @reconstructor
    def init_on_load(self):
        """Called by SQLAlchemy after loading from DB — bypasses __init__."""
        self._init_collections()

    def _init_collections(self):
        """Initialize transient/unmapped collections."""
        self.assignments: List[OperatorBTAssignment] = []
        self.events: List = []
        if not hasattr(self, "operators"):
            self.operators: List[Operator] = []
        if not hasattr(self, "blue_teams"):
            self.blue_teams: List[BlueTeam] = []
        if not hasattr(self, "scenarios"):
            self.scenarios: List[Scenario] = []
        if not hasattr(self, "achievements"):
            self.achievements: List[ControlLineAchievement] = []
        if not hasattr(self, "actions"):
            self.actions: List[AttackAction] = []

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def add_blue_team(self, bt: BlueTeam):
        if bt not in self.blue_teams:
            self.blue_teams.append(bt)

    def add_operator(self, op: Operator):
        if op not in self.operators:
            self.operators.append(op)

    def assign_operator_to_bt(self, operator_id: str, blue_team_id: str):
        a = OperatorBTAssignment(operator_id=operator_id, blue_team_id=blue_team_id)
        if a not in self.assignments:
            self.assignments.append(a)

    def add_scenario(self, scenario: Scenario):
        if scenario not in self.scenarios:
            self.scenarios.append(scenario)

    def assign_scenario_to_bt(self, scenario_id: str, blue_team_id: str):
        bt = self._get_bt(blue_team_id)
        bt.assign_scenario(scenario_id)

    # ------------------------------------------------------------------
    # Attack actions
    # ------------------------------------------------------------------

    def register_attack(self, operator_id: str, blue_team_id: str,
                        machine_id: str, summary: str, detail: str,
                        occurred_at: datetime, timezone_name: str = "UTC") -> AttackAction:
        self._assert_active()
        self._assert_assignment(operator_id, blue_team_id)
        self._assert_machine_in_bt_scenario(machine_id, blue_team_id)

        action = AttackAction(
            id=str(uuid.uuid4()), exercise_id=self.id,
            operator_id=operator_id, blue_team_id=blue_team_id,
            machine_id=machine_id, summary=summary, detail=detail,
            occurred_at=occurred_at, timezone_name=timezone_name,
        )
        self.actions.append(action)
        self.events.append(AttackRegistered(
            exercise_id=self.id, action_id=action.id,
            operator_id=operator_id, blue_team_id=blue_team_id,
            machine_id=machine_id, summary=summary, occurred_at=occurred_at,
        ))
        return action

    def update_attack(self, action_id: str, operator_id: str, summary: str,
                      detail: str, machine_id: str, occurred_at: datetime) -> AttackAction:
        self._assert_active()
        action = self._get_action(action_id)
        if action.operator_id != operator_id:
            raise PermissionError("Operator can only edit their own attacks.")
        action.update(summary, detail, machine_id, occurred_at)
        self.events.append(AttackUpdated(action_id=action_id, exercise_id=self.id))
        return action

    def delete_attack(self, action_id: str, operator_id: str):
        self._assert_active()
        action = self._get_action(action_id)
        if action.operator_id != operator_id:
            raise PermissionError("Operator can only delete their own attacks.")
        self.actions.remove(action)
        self.events.append(AttackDeleted(action_id=action_id, exercise_id=self.id))

    # ------------------------------------------------------------------
    # Control lines — achievement state tracked via records, not in-memory set
    # ------------------------------------------------------------------

    def achieve_control_line(self, control_line_id: str, operator_id: str,
                             blue_team_id: str, at: datetime) -> ControlLineAchievement:
        self._assert_active()
        self._assert_assignment(operator_id, blue_team_id)

        # Idempotent: return existing if already achieved
        existing = self._find_achievement(control_line_id, operator_id, blue_team_id)
        if existing:
            return existing

        ach = ControlLineAchievement(
            id=str(uuid.uuid4()),
            control_line_id=control_line_id,
            operator_id=operator_id,
            blue_team_id=blue_team_id,
            achieved_at=at,
        )
        self.achievements.append(ach)
        self.events.append(ControlLineAchieved(
            exercise_id=self.id, control_line_id=control_line_id,
            operator_id=operator_id, blue_team_id=blue_team_id, achieved_at=at,
        ))
        return ach

    def revert_control_line(self, control_line_id: str, operator_id: str, blue_team_id: str):
        self._assert_active()
        existing = self._find_achievement(control_line_id, operator_id, blue_team_id)
        if existing:
            self.achievements.remove(existing)
        self.events.append(ControlLineReverted(
            exercise_id=self.id, control_line_id=control_line_id,
        ))

    def is_cl_achieved(self, control_line_id: str, operator_id: str, blue_team_id: str) -> bool:
        return self._find_achievement(control_line_id, operator_id, blue_team_id) is not None

    def _find_achievement(self, cl_id: str, op_id: str, bt_id: str):
        return next(
            (a for a in self.achievements
             if a.control_line_id == cl_id and a.operator_id == op_id and a.blue_team_id == bt_id),
            None,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> datetime:
        if self.status == ExerciseStatus.CLOSED:
            raise ValueError("Exercise already closed.")
        self.status = ExerciseStatus.CLOSED
        self.closed_at = datetime.now(tz=timezone.utc)
        self.events.append(ExerciseClosed(exercise_id=self.id, closed_at=self.closed_at))
        return self.closed_at

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def get_scenario_for_bt(self, blue_team_id: str) -> Optional[Scenario]:
        bt = next((b for b in self.blue_teams if b.id == blue_team_id), None)
        if not bt or not bt.scenario_id:
            return None
        return next((s for s in self.scenarios if s.id == bt.scenario_id), None)

    def control_line_progress(self, operator_id: str, blue_team_id: str,
                               domain_type: Optional[DomainType] = None,
                               scenario_id: Optional[str] = None) -> dict:
        """Progress for a given (op, bt) pair, optionally filtered by domain or scenario."""
        # Collect relevant control lines
        lines = []
        for scenario in self.scenarios:
            if scenario_id and scenario.id != scenario_id:
                continue
            for cl in scenario.control_lines:
                if domain_type is None or cl.domain_type == domain_type:
                    lines.append(cl)

        if not lines:
            return {"achieved": 0, "total": 0, "percent": 0.0}

        achieved = sum(
            1 for cl in lines
            if self.is_cl_achieved(cl.id, operator_id, blue_team_id)
        )
        total = len(lines)
        return {"achieved": achieved, "total": total,
                "percent": round(100 * achieved / total, 1)}

    def action_count(self, operator_id: str, blue_team_id: str) -> int:
        return sum(1 for a in self.actions
                   if a.operator_id == operator_id and a.blue_team_id == blue_team_id)

    def leaderboard(self) -> List[dict]:
        counts: dict = {}
        for a in self.actions:
            key = (a.operator_id, a.blue_team_id)
            counts[key] = counts.get(key, 0) + 1
        result = [
            {"operator_id": op, "blue_team_id": bt, "action_count": cnt}
            for (op, bt), cnt in counts.items()
        ]
        result.sort(key=lambda x: x["action_count"], reverse=True)
        return result

    def recent_actions(self, limit: int = 20) -> List[AttackAction]:
        return sorted(self.actions, key=lambda a: a.occurred_at, reverse=True)[:limit]

    # ------------------------------------------------------------------
    # Private guards
    # ------------------------------------------------------------------

    def _assert_active(self):
        if self.status != ExerciseStatus.ACTIVE:
            raise ValueError("Exercise is not active.")

    def _assert_assignment(self, operator_id: str, blue_team_id: str):
        a = OperatorBTAssignment(operator_id=operator_id, blue_team_id=blue_team_id)
        if a not in self.assignments:
            raise ValueError(
                f"Operator {operator_id!r} is not assigned to BlueTeam {blue_team_id!r}.")

    def _assert_machine_in_bt_scenario(self, machine_id: str, blue_team_id: str):
        scenario = self.get_scenario_for_bt(blue_team_id)
        if not scenario:
            raise ValueError("No scenario assigned to this Blue Team.")
        ids = {m.id for m in scenario.machines}
        if machine_id not in ids:
            raise ValueError(f"Machine {machine_id!r} not in Blue Team's scenario.")

    def _get_action(self, action_id: str) -> AttackAction:
        for a in self.actions:
            if a.id == action_id:
                return a
        raise ValueError(f"AttackAction {action_id!r} not found.")

    def _get_bt(self, blue_team_id: str) -> BlueTeam:
        bt = next((b for b in self.blue_teams if b.id == blue_team_id), None)
        if not bt:
            raise ValueError(f"BlueTeam {blue_team_id!r} not found.")
        return bt

    def __eq__(self, other):
        return isinstance(other, Exercise) and self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return f"Exercise(id={self.id!r}, name={self.name!r}, status={self.status!r})"
