"""Service layer tests using FakeUnitOfWork."""
import pytest
from datetime import datetime, timezone
from src.service_layer import services
from src.service_layer.unit_of_work import FakeUnitOfWork
from src.service_layer.services import _hash_password
from src.domain.model import (
    Operator, BlueTeam, Scenario, TargetMachine, ControlLine,
    DomainType, Exercise, ExerciseStatus,
)

NOW = datetime.now(tz=timezone.utc)


def make_seeded_uow():
    uow = FakeUnitOfWork()
    ex = Exercise(id="ex-001", name="Test", logo_path=None,
                  status=ExerciseStatus.ACTIVE, created_at=NOW)
    bt = BlueTeam(id="bt-001", exercise_id="ex-001", name="Alpha", has_it=True, has_ot=False)
    op = Operator(id="op-001", username="red01",
                  hashed_password=_hash_password("pass"), full_name="Red Op")
    sc = Scenario(id="sc-001", exercise_id="ex-001", name="Corp")
    m = TargetMachine(id="m-001", scenario_id="sc-001", name="DC01")
    cl = ControlLine(id="cl-001", scenario_id="sc-001", name="Phishing",
                     description="", domain_type=DomainType.IT, order=0)
    sc.add_machine(m); sc.add_control_line(cl)
    ex.add_blue_team(bt); ex.add_operator(op); ex.add_scenario(sc)
    ex.assign_operator_to_bt("op-001", "bt-001")
    ex.assign_scenario_to_bt("sc-001", "bt-001")
    uow.exercises.add(ex); uow.operators.add(op)
    return uow


class TestCreateExercise:
    def test_returns_id(self):
        uow = FakeUnitOfWork()
        eid = services.create_exercise("Test", None, uow)
        assert eid and uow.committed

    def test_no_two_active(self):
        uow = FakeUnitOfWork()
        services.create_exercise("First", None, uow)
        with pytest.raises(ValueError, match="already an active"):
            services.create_exercise("Second", None, uow)


class TestAuth:
    def test_correct_password(self):
        uow = make_seeded_uow()
        assert services.authenticate_operator("red01", "pass", uow) == "op-001"

    def test_wrong_password(self):
        uow = make_seeded_uow()
        assert services.authenticate_operator("red01", "wrong", uow) is None


class TestAttacks:
    def test_register(self):
        uow = make_seeded_uow()
        aid = services.register_attack("ex-001","op-001","bt-001","m-001",
                                       "SQL inj","Detail",NOW,"UTC",uow)
        assert aid and uow.committed

    def test_bad_exercise(self):
        uow = FakeUnitOfWork()
        with pytest.raises(ValueError):
            services.register_attack("no","op","bt","m","s","d",NOW,"UTC",uow)


class TestControlLines:
    def test_achieve_and_revert(self):
        uow = make_seeded_uow()
        services.achieve_control_line("ex-001","cl-001","op-001","bt-001",NOW,uow)
        ex = uow.exercises.get("ex-001")
        assert ex.is_cl_achieved("cl-001","op-001","bt-001")
        services.revert_control_line("ex-001","cl-001","op-001","bt-001",uow)
        assert not ex.is_cl_achieved("cl-001","op-001","bt-001")


class TestClose:
    def test_close(self):
        uow = make_seeded_uow()
        closed = services.close_exercise("ex-001", uow)
        assert closed and uow.committed

    def test_close_missing(self):
        uow = FakeUnitOfWork()
        with pytest.raises(ValueError):
            services.close_exercise("no-such", uow)
