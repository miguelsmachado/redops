import abc
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from src.domain.ports import (
    AbstractExerciseRepository, AbstractOperatorRepository, AbstractAdminRepository,
)
from src.adapters.repository.sqlalchemy_repos import (
    SqlAlchemyExerciseRepository, SqlAlchemyOperatorRepository, SqlAlchemyAdminRepository,
)

DEFAULT_SESSION_FACTORY = None


class AbstractUnitOfWork(abc.ABC):
    exercises: AbstractExerciseRepository
    operators: AbstractOperatorRepository
    admins: AbstractAdminRepository

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.rollback()

    def commit(self):
        self._commit()

    @abc.abstractmethod
    def _commit(self): raise NotImplementedError

    @abc.abstractmethod
    def rollback(self): raise NotImplementedError


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    def __init__(self, session_factory=None):
        if session_factory is None:
            if DEFAULT_SESSION_FACTORY is None:
                raise RuntimeError("Session factory not configured.")
            session_factory = DEFAULT_SESSION_FACTORY
        self.session_factory = session_factory

    def __enter__(self):
        self.session: Session = self.session_factory()
        self.exercises = SqlAlchemyExerciseRepository(self.session)
        self.operators = SqlAlchemyOperatorRepository(self.session)
        self.admins = SqlAlchemyAdminRepository(self.session)
        return super().__enter__()

    def __exit__(self, *args):
        super().__exit__(*args)
        self.session.close()

    def _commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()


# Fake repos for unit tests
class FakeExerciseRepository:
    def __init__(self, exercises=None):
        self._exercises = list(exercises or [])
    def add(self, e): self._exercises.append(e)
    def get(self, eid):
        from src.domain.model import ExerciseStatus
        return next((e for e in self._exercises if e.id == eid), None)
    def get_active(self):
        from src.domain.model import ExerciseStatus
        return next((e for e in self._exercises if e.status == ExerciseStatus.ACTIVE), None)

class FakeOperatorRepository:
    def __init__(self, operators=None):
        self._operators = list(operators or [])
    def add(self, o): self._operators.append(o)
    def get(self, oid): return next((o for o in self._operators if o.id == oid), None)
    def get_by_username(self, u): return next((o for o in self._operators if o.username == u), None)
    def list(self): return list(self._operators)

class FakeAdminRepository:
    def __init__(self, admins=None):
        self._admins = list(admins or [])
    def get_by_username(self, u): return next((a for a in self._admins if a.username == u), None)
    def get(self, aid): return next((a for a in self._admins if a.id == aid), None)

class FakeUnitOfWork(AbstractUnitOfWork):
    def __init__(self):
        self.exercises = FakeExerciseRepository()
        self.operators = FakeOperatorRepository()
        self.admins = FakeAdminRepository()
        self.committed = False
    def _commit(self): self.committed = True
    def rollback(self): pass


def configure_uow(database_url: str):
    global DEFAULT_SESSION_FACTORY
    engine = create_engine(database_url)
    DEFAULT_SESSION_FACTORY = sessionmaker(bind=engine, expire_on_commit=False)
    return engine
