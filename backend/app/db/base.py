from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Central declarative base for all PageTurner models.

    By isolating this here, we prevent circular imports between the modularized
    model files (e.g., models/users.py and models/books.py can both safely import this).

    Alembic's env.py will import this Base to auto-generate migrations.
    """

    pass
