from sqlalchemy import create_engine, Column, Integer, String, Boolean, Date, ForeignKey, func
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from config import DATABASE_URL
from typing import Optional
# Базовый класс для моделей
Base = declarative_base()

class Employee(Base):
    """Модель сотрудника предприятия"""
    __tablename__ = 'employees'

    id = Column(Integer, primary_key=True)
    full_name = Column(String(150), nullable=False)
    birth_date = Column(Date, nullable=False)
    telegram_id = Column(Integer, unique=True)
    is_head = Column(Boolean, default=False)
    department_id = Column(Integer, ForeignKey('departments.id'), nullable=False)
    department = relationship("Department", back_populates="employees")

    @classmethod
    def get_by_department(cls, session, department_id: int, page: int = 1, per_page: int = 5):
        """Получить сотрудников отдела с пагинацией"""
        offset = (page - 1) * per_page
        return (
            session.query(cls)
            .filter_by(department_id=department_id)
            .order_by(cls.full_name)
            .offset(offset)
            .limit(per_page)
            .all()
        )

    @classmethod
    def get_count_by_department(cls, session, department_id: int) -> int:
        """Количество сотрудников в отделе"""
        return session.query(func.count(cls.id)).filter_by(department_id=department_id).scalar()

    @classmethod
    def get_by_telegram_id(cls, session, tg_id: int) -> Optional["Employee"] | None:
        """Найти сотрудника по Telegram ID"""
        return session.query(cls).filter_by(telegram_id=tg_id).first()

class Department(Base):
    """Модель отдела предприятия"""
    __tablename__ = 'departments'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    employees = relationship("Employee", back_populates="department", cascade="all, delete-orphan")

    @classmethod
    def get_all(cls, session, page: int = 1, per_page: int = 5):
        """Получить отделы с пагинацией"""
        offset = (page - 1) * per_page
        return session.query(cls).order_by(cls.name).offset(offset).limit(per_page).all()
    @classmethod
    def get_head(cls, session, department_id: int) -> Employee | None:
        """Получить начальника отдела"""
        return (
            session.query(Employee)
            .filter_by(department_id=department_id, is_head=True)
            .first()
        )
    @classmethod
    def get_count(cls, session) -> int:
        """Общее количество отделов"""
        return session.query(func.count(cls.id)).scalar()




# Инициализация БД
engine = create_engine(DATABASE_URL)
Base.metadata.create_all(engine)

# Сессия для работы с БД
Session = sessionmaker(bind=engine)