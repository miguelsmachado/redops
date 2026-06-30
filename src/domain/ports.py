import abc
from typing import Optional
from src.domain.model import Exercise, Operator


class AbstractExerciseRepository(abc.ABC):
    @abc.abstractmethod
    def add(self, exercise: Exercise): raise NotImplementedError
    @abc.abstractmethod
    def get(self, exercise_id: str) -> Optional[Exercise]: raise NotImplementedError
    @abc.abstractmethod
    def get_active(self) -> Optional[Exercise]: raise NotImplementedError


class AbstractOperatorRepository(abc.ABC):
    @abc.abstractmethod
    def add(self, operator: Operator): raise NotImplementedError
    @abc.abstractmethod
    def get(self, operator_id: str) -> Optional[Operator]: raise NotImplementedError
    @abc.abstractmethod
    def get_by_username(self, username: str) -> Optional[Operator]: raise NotImplementedError
    @abc.abstractmethod
    def list(self): raise NotImplementedError


class AbstractAdminRepository(abc.ABC):
    @abc.abstractmethod
    def get_by_username(self, username: str): raise NotImplementedError
    @abc.abstractmethod
    def get(self, admin_id: str): raise NotImplementedError
