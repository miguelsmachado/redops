"""Unit tests for the domain model — pure domain, no database."""
import pytest
from datetime import datetime, timezone
from src.domain.model import (
    Exercise, ExerciseStatus, Operator, BlueTeam, Scenario,
    TargetMachine, ControlLine, DomainType, OperatorBTAssignment,
)

EX_ID = "ex-001"
NOW = datetime.now(tz=timezone.utc)


def make_exercise():
    return Exercise(id=EX_ID, name="Test", logo_path=None,
                    status=ExerciseStatus.ACTIVE, created_at=NOW)

def make_operator(id="op-001", username="red01"):
    return Operator(id=id, username=username, hashed_password="x", full_name="Red Operator")

def make_bt(id="bt-001", name="Alpha"):
    return BlueTeam(id=id, exercise_id=EX_ID, name=name, has_it=True, has_ot=True)

def make_scenario(id="sc-001"):
    s = Scenario(id=id, exercise_id=EX_ID, name="Corp Network")
    m = TargetMachine(id="m-001", scenario_id=id, name="DC01")
    cl_it = ControlLine(id="cl-it-1", scenario_id=id, name="Phishing sent",
                        description="", domain_type=DomainType.IT, order=0)
    cl_ot = ControlLine(id="cl-ot-1", scenario_id=id, name="HMI access",
                        description="", domain_type=DomainType.OT, order=0)
    s.add_machine(m)
    s.add_control_line(cl_it)
    s.add_control_line(cl_ot)
    return s


def full_setup():
    ex = make_exercise()
    op = make_operator()
    bt = make_bt()
    sc = make_scenario()
    ex.add_operator(op)
    ex.add_blue_team(bt)
    ex.add_scenario(sc)
    ex.assign_operator_to_bt(op.id, bt.id)
    ex.assign_scenario_to_bt(sc.id, bt.id)
    return ex, op, bt, sc


class TestSetup:
    def test_add_blue_team(self):
        ex = make_exercise()
        bt = make_bt()
        ex.add_blue_team(bt)
        assert bt in ex.blue_teams

    def test_no_duplicate_blue_teams(self):
        ex = make_exercise()
        bt = make_bt()
        ex.add_blue_team(bt); ex.add_blue_team(bt)
        assert len(ex.blue_teams) == 1

    def test_assign_operator_to_bt(self):
        ex, op, bt, sc = full_setup()
        assert OperatorBTAssignment(op.id, bt.id) in ex.assignments

    def test_assign_scenario_to_bt(self):
        ex, op, bt, sc = full_setup()
        assert bt.scenario_id == sc.id

    def test_get_scenario_for_bt(self):
        ex, op, bt, sc = full_setup()
        assert ex.get_scenario_for_bt(bt.id) == sc


class TestAttacks:
    def test_register_attack(self):
        ex, op, bt, sc = full_setup()
        a = ex.register_attack(op.id, bt.id, "m-001", "Phishing", "Detail", NOW)
        assert a in ex.actions

    def test_register_attack_raises_event(self):
        ex, op, bt, sc = full_setup()
        ex.register_attack(op.id, bt.id, "m-001", "Phishing", "Detail", NOW)
        from src.domain.model import AttackRegistered
        assert any(isinstance(e, AttackRegistered) for e in ex.events)

    def test_wrong_assignment_raises(self):
        ex = make_exercise()
        op = make_operator(); bt = make_bt(); sc = make_scenario()
        ex.add_operator(op); ex.add_blue_team(bt); ex.add_scenario(sc)
        ex.assign_scenario_to_bt(sc.id, bt.id)
        with pytest.raises(ValueError, match="not assigned"):
            ex.register_attack(op.id, bt.id, "m-001", "Test", "d", NOW)

    def test_invalid_machine_raises(self):
        ex, op, bt, sc = full_setup()
        with pytest.raises(ValueError, match="not in"):
            ex.register_attack(op.id, bt.id, "bad-machine", "Test", "d", NOW)

    def test_update_attack(self):
        ex, op, bt, sc = full_setup()
        a = ex.register_attack(op.id, bt.id, "m-001", "Old", "d", NOW)
        ex.update_attack(a.id, op.id, "New", "d2", "m-001", NOW)
        assert a.summary == "New"

    def test_delete_attack(self):
        ex, op, bt, sc = full_setup()
        a = ex.register_attack(op.id, bt.id, "m-001", "X", "d", NOW)
        ex.delete_attack(a.id, op.id)
        assert a not in ex.actions


class TestControlLines:
    def test_achieve_creates_record(self):
        ex, op, bt, sc = full_setup()
        ach = ex.achieve_control_line("cl-it-1", op.id, bt.id, NOW)
        assert ach in ex.achievements
        assert ex.is_cl_achieved("cl-it-1", op.id, bt.id)

    def test_achieve_idempotent(self):
        ex, op, bt, sc = full_setup()
        ex.achieve_control_line("cl-it-1", op.id, bt.id, NOW)
        ex.achieve_control_line("cl-it-1", op.id, bt.id, NOW)
        assert len([a for a in ex.achievements if a.control_line_id == "cl-it-1"]) == 1

    def test_revert(self):
        ex, op, bt, sc = full_setup()
        ex.achieve_control_line("cl-it-1", op.id, bt.id, NOW)
        ex.revert_control_line("cl-it-1", op.id, bt.id)
        assert not ex.is_cl_achieved("cl-it-1", op.id, bt.id)


class TestProgress:
    def test_it_progress(self):
        ex, op, bt, sc = full_setup()
        ex.achieve_control_line("cl-it-1", op.id, bt.id, NOW)
        prog = ex.control_line_progress(op.id, bt.id, DomainType.IT, sc.id)
        assert prog["achieved"] == 1
        assert prog["total"] == 1
        assert prog["percent"] == 100.0

    def test_leaderboard(self):
        ex, op, bt, sc = full_setup()
        op2 = make_operator("op-2", "red02")
        bt2 = make_bt("bt-2", "Bravo")
        sc2 = make_scenario("sc-2")
        ex.add_operator(op2); ex.add_blue_team(bt2); ex.add_scenario(sc2)
        ex.assign_operator_to_bt(op2.id, bt2.id)
        ex.assign_scenario_to_bt(sc2.id, bt2.id)
        ex.register_attack(op2.id, bt2.id, "m-001", "A", "d", NOW)
        ex.register_attack(op2.id, bt2.id, "m-001", "B", "d", NOW)
        ex.register_attack(op.id, bt.id, "m-001", "C", "d", NOW)
        lb = ex.leaderboard()
        assert lb[0]["operator_id"] == op2.id


class TestLifecycle:
    def test_close(self):
        ex = make_exercise()
        ex.close()
        assert ex.status == ExerciseStatus.CLOSED

    def test_attack_on_closed_raises(self):
        ex, op, bt, sc = full_setup()
        ex.close()
        with pytest.raises(ValueError, match="not active"):
            ex.register_attack(op.id, bt.id, "m-001", "X", "d", NOW)

    def test_close_twice_raises(self):
        ex = make_exercise()
        ex.close()
        with pytest.raises(ValueError, match="already closed"):
            ex.close()
