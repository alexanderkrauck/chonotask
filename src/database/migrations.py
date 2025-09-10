"""Database migration utilities."""

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from models.task import Base
import logging

logger = logging.getLogger(__name__)


def check_and_migrate(session: Session):
    """Check database schema and apply migrations if needed."""
    inspector = inspect(session.bind)
    existing_tables = inspector.get_table_names()
    
    # Get expected tables from models
    expected_tables = Base.metadata.tables.keys()
    
    # Check for missing tables
    missing_tables = set(expected_tables) - set(existing_tables)
    
    if missing_tables:
        logger.info(f"Creating missing tables: {missing_tables}")
        Base.metadata.create_all(bind=session.bind, tables=[
            Base.metadata.tables[table] for table in missing_tables
        ])
    
    # Check for schema version (for future migrations)
    if "schema_version" not in existing_tables:
        session.execute(text("""
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        session.execute(text("INSERT INTO schema_version (version) VALUES (1)"))
        session.commit()
        logger.info("Schema version table created")
    
    # Get current version
    result = session.execute(text("SELECT MAX(version) FROM schema_version")).scalar()
    current_version = result or 0
    
    # Apply migrations based on version
    migrations = get_migrations()
    
    for version, migration_func in migrations.items():
        if version > current_version:
            logger.info(f"Applying migration version {version}")
            migration_func(session)
            session.execute(text("INSERT INTO schema_version (version) VALUES (:version)"), {"version": version})
            session.commit()
    
    logger.info("Database migrations complete")


def get_migrations():
    """Return dictionary of migration functions by version."""
    migrations = {}
    
    # Example migration for version 2
    def migration_v2(session: Session):
        # Add any new columns or tables for v2
        pass
    
    # migrations[2] = migration_v2
    
    return migrations