"""
SQLAlchemy ORM — classical mapping style.
ORM depends on the domain model, never the other way around.
"""

from sqlalchemy import (
    Column, String, Boolean, DateTime, Integer, Text,
    ForeignKey, Table, MetaData,
    Enum as SAEnum, create_engine,
)
from sqlalchemy.orm import registry, relationship

from src.domain.model import (
    Exercise, ExerciseStatus,
    Operator, BlueTeam, Scenario,
    TargetMachine, ControlLine, ControlLineAchievement,
    AttackAction, DomainType,
)

mapper_registry = registry()
metadata = mapper_registry.metadata

# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

admins_table = Table("admins", metadata,
    Column("id", String(36), primary_key=True),
    Column("username", String(100), unique=True, nullable=False),
    Column("hashed_password", String(256), nullable=False),
    Column("full_name", String(200), nullable=False),
)

operators_table = Table("operators", metadata,
    Column("id", String(36), primary_key=True),
    Column("username", String(100), unique=True, nullable=False),
    Column("hashed_password", String(256), nullable=False),
    Column("full_name", String(200), nullable=False),
)

exercises_table = Table("exercises", metadata,
    Column("id", String(36), primary_key=True),
    Column("name", String(200), nullable=False),
    Column("logo_path", String(500), nullable=True),
    Column("status", SAEnum(ExerciseStatus), nullable=False, default=ExerciseStatus.ACTIVE),
    Column("created_at", DateTime, nullable=False),
    Column("closed_at", DateTime, nullable=True),
)

scenarios_table = Table("scenarios", metadata,
    Column("id", String(36), primary_key=True),
    Column("exercise_id", String(36), ForeignKey("exercises.id"), nullable=False),
    Column("name", String(200), nullable=False),
)

blue_teams_table = Table("blue_teams", metadata,
    Column("id", String(36), primary_key=True),
    Column("exercise_id", String(36), ForeignKey("exercises.id"), nullable=False),
    Column("name", String(200), nullable=False),
    Column("has_it", Boolean, nullable=False, default=True),
    Column("has_ot", Boolean, nullable=False, default=False),
    Column("scenario_id", String(36), ForeignKey("scenarios.id"), nullable=True),
)

operator_bt_assignments_table = Table("operator_bt_assignments", metadata,
    Column("id", String(36), primary_key=True),
    Column("exercise_id", String(36), ForeignKey("exercises.id"), nullable=False),
    Column("operator_id", String(36), ForeignKey("operators.id"), nullable=False),
    Column("blue_team_id", String(36), ForeignKey("blue_teams.id"), nullable=False),
)

target_machines_table = Table("target_machines", metadata,
    Column("id", String(36), primary_key=True),
    Column("scenario_id", String(36), ForeignKey("scenarios.id"), nullable=False),
    Column("name", String(200), nullable=False),
    Column("description", Text, nullable=False, default=""),
)

control_lines_table = Table("control_lines", metadata,
    Column("id", String(36), primary_key=True),
    Column("scenario_id", String(36), ForeignKey("scenarios.id"), nullable=False),
    Column("name", String(200), nullable=False),
    Column("description", Text, nullable=False, default=""),
    Column("domain_type", SAEnum(DomainType), nullable=False),
    Column("order", Integer, nullable=False, default=0),
)

control_line_achievements_table = Table("control_line_achievements", metadata,
    Column("id", String(36), primary_key=True),
    Column("exercise_id", String(36), ForeignKey("exercises.id"), nullable=False),
    Column("control_line_id", String(36), ForeignKey("control_lines.id"), nullable=False),
    Column("operator_id", String(36), ForeignKey("operators.id"), nullable=False),
    Column("blue_team_id", String(36), ForeignKey("blue_teams.id"), nullable=False),
    Column("achieved_at", DateTime, nullable=False),
)

attack_actions_table = Table("attack_actions", metadata,
    Column("id", String(36), primary_key=True),
    Column("exercise_id", String(36), ForeignKey("exercises.id"), nullable=False),
    Column("operator_id", String(36), ForeignKey("operators.id"), nullable=False),
    Column("blue_team_id", String(36), ForeignKey("blue_teams.id"), nullable=False),
    Column("machine_id", String(36), ForeignKey("target_machines.id"), nullable=False),
    Column("summary", String(500), nullable=False),
    Column("detail", Text, nullable=False),
    Column("occurred_at", DateTime, nullable=False),
    Column("timezone_name", String(100), nullable=False, default="UTC"),
)

# ---------------------------------------------------------------------------
# AdminUser plain class
# ---------------------------------------------------------------------------

class AdminUser:
    def __init__(self, id, username, hashed_password, full_name):
        self.id = id
        self.username = username
        self.hashed_password = hashed_password
        self.full_name = full_name


# ---------------------------------------------------------------------------
# Mappings
# ---------------------------------------------------------------------------

def start_mappers():
    if mapper_registry.mappers:
        return  # Idempotent

    mapper_registry.map_imperatively(AdminUser, admins_table)
    mapper_registry.map_imperatively(Operator, operators_table)

    mapper_registry.map_imperatively(TargetMachine, target_machines_table)
    mapper_registry.map_imperatively(ControlLine, control_lines_table)
    mapper_registry.map_imperatively(ControlLineAchievement, control_line_achievements_table)
    mapper_registry.map_imperatively(AttackAction, attack_actions_table)

    mapper_registry.map_imperatively(Scenario, scenarios_table, properties={
        "machines": relationship(
            TargetMachine,
            primaryjoin=(scenarios_table.c.id == target_machines_table.c.scenario_id),
            foreign_keys=[target_machines_table.c.scenario_id],
            cascade="all, delete-orphan",
        ),
        "control_lines": relationship(
            ControlLine,
            primaryjoin=(scenarios_table.c.id == control_lines_table.c.scenario_id),
            foreign_keys=[control_lines_table.c.scenario_id],
            cascade="all, delete-orphan",
            order_by=control_lines_table.c.order,
        ),
    })

    mapper_registry.map_imperatively(BlueTeam, blue_teams_table)

    mapper_registry.map_imperatively(Exercise, exercises_table, properties={
        "blue_teams": relationship(
            BlueTeam,
            primaryjoin=(exercises_table.c.id == blue_teams_table.c.exercise_id),
            foreign_keys=[blue_teams_table.c.exercise_id],
            cascade="all, delete-orphan",
        ),
        "scenarios": relationship(
            Scenario,
            primaryjoin=(exercises_table.c.id == scenarios_table.c.exercise_id),
            foreign_keys=[scenarios_table.c.exercise_id],
            cascade="all, delete-orphan",
        ),
        "achievements": relationship(
            ControlLineAchievement,
            primaryjoin=(exercises_table.c.id == control_line_achievements_table.c.exercise_id),
            foreign_keys=[control_line_achievements_table.c.exercise_id],
            cascade="all, delete-orphan",
        ),
        "actions": relationship(
            AttackAction,
            primaryjoin=(exercises_table.c.id == attack_actions_table.c.exercise_id),
            foreign_keys=[attack_actions_table.c.exercise_id],
            cascade="all, delete-orphan",
            order_by=attack_actions_table.c.occurred_at.desc(),
        ),
        "operators": relationship(
            Operator,
            secondary=operator_bt_assignments_table,
            primaryjoin=(exercises_table.c.id == operator_bt_assignments_table.c.exercise_id),
            secondaryjoin=(operators_table.c.id == operator_bt_assignments_table.c.operator_id),
            viewonly=True,
        ),
    })
