from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Base class for all future SQLAlchemy database models in Regal Fitness.
    Business models will inherit from this class.
    """
    pass
