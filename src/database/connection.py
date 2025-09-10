"""Database connection and session management."""

from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from config import settings
from models.task import Base
import logging

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self):
        self.engine = None
        self.SessionLocal = None
        
    def initialize(self):
        """Initialize database connection and create tables."""
        # Ensure database directory exists for SQLite
        if "sqlite" in settings.database_url:
            import os
            from pathlib import Path
            # Extract path from SQLite URL - handle both relative and absolute paths
            if "sqlite:///" in settings.database_url and not "sqlite:////" in settings.database_url:
                # Relative path (three slashes)
                db_path = settings.database_url.replace("sqlite:///", "")
            else:
                # Absolute path (four slashes)
                db_path = settings.database_url.replace("sqlite:////", "/")
            
            db_dir = os.path.dirname(db_path)
            if db_dir:
                Path(db_dir).mkdir(parents=True, exist_ok=True)
        
        # Use StaticPool for SQLite to avoid connection issues
        connect_args = {"check_same_thread": False} if "sqlite" in settings.database_url else {}
        poolclass = StaticPool if "sqlite" in settings.database_url else None
        
        self.engine = create_engine(
            settings.database_url,
            connect_args=connect_args,
            poolclass=poolclass,
            echo=settings.database_echo
        )
        
        # Create all tables
        Base.metadata.create_all(bind=self.engine)
        
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
        
        logger.info(f"Database initialized at {settings.database_url}")
    
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Get a database session."""
        if not self.SessionLocal:
            self.initialize()
            
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def close(self):
        """Close database connection."""
        if self.engine:
            self.engine.dispose()
            logger.info("Database connection closed")


# Global database manager instance
db_manager = DatabaseManager()


def get_db() -> Generator[Session, None, None]:
    """Dependency for FastAPI to get database session."""
    with db_manager.get_session() as session:
        yield session