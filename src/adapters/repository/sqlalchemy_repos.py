from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.domain.model import Exercise, ExerciseStatus, Operator, OperatorBTAssignment
from src.domain.ports import (
    AbstractExerciseRepository, AbstractOperatorRepository, AbstractAdminRepository,
)
from src.adapters.orm.mappings import AdminUser, operator_bt_assignments_table


class SqlAlchemyExerciseRepository(AbstractExerciseRepository):
    def __init__(self, session: Session):
        self.session = session

    def add(self, exercise: Exercise):
        self.session.add(exercise)

    def get(self, exercise_id: str) -> Optional[Exercise]:
        ex = self.session.query(Exercise).filter_by(id=exercise_id).first()
        if ex:
            self._load_assignments(ex)
            self._refresh_collections(ex)
        return ex

    def get_active(self) -> Optional[Exercise]:
        ex = self.session.query(Exercise).filter_by(status=ExerciseStatus.ACTIVE).first()
        if ex:
            self._load_assignments(ex)
            self._refresh_collections(ex)
        return ex

    def _load_assignments(self, exercise: Exercise):
        """Load OperatorBTAssignment value objects from the join table."""
        rows = self.session.execute(
            select(
                operator_bt_assignments_table.c.operator_id,
                operator_bt_assignments_table.c.blue_team_id,
            ).where(operator_bt_assignments_table.c.exercise_id == exercise.id)
        ).fetchall()
        exercise.assignments = [
            OperatorBTAssignment(operator_id=r.operator_id, blue_team_id=r.blue_team_id)
            for r in rows
        ]

    def _refresh_collections(self, exercise: Exercise):
        """
        Force SQLAlchemy to reload scenario.control_lines and scenario.machines
        from the database on every request.

        Why this is needed:
        - The session factory uses expire_on_commit=False to avoid
          DetachedInstanceError when objects are passed to templates.
        - This means SQLAlchemy never automatically invalidates cached
          collections between sessions.
        - When the admin adds new control lines to an active exercise
          (from a different session), those lines are invisible to the
          operator's next request because the Scenario object still holds
          the stale collection from when it was first loaded.
        - session.expire(obj, attrs) marks those specific attributes as
          stale, forcing SQLAlchemy to re-query on next access.
        """
        for scenario in exercise.scenarios:
            self.session.expire(scenario, ["control_lines", "machines"])


class SqlAlchemyOperatorRepository(AbstractOperatorRepository):
    def __init__(self, session: Session):
        self.session = session

    def add(self, operator: Operator):
        self.session.add(operator)

    def get(self, operator_id: str) -> Optional[Operator]:
        return self.session.query(Operator).filter_by(id=operator_id).first()

    def get_by_username(self, username: str) -> Optional[Operator]:
        return self.session.query(Operator).filter_by(username=username).first()

    def list(self) -> List[Operator]:
        return self.session.query(Operator).all()


class SqlAlchemyAdminRepository(AbstractAdminRepository):
    def __init__(self, session: Session):
        self.session = session

    def get_by_username(self, username: str) -> Optional[AdminUser]:
        return self.session.query(AdminUser).filter_by(username=username).first()

    def get(self, admin_id: str) -> Optional[AdminUser]:
        return self.session.query(AdminUser).filter_by(id=admin_id).first()
