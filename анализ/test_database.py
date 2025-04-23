from datetime import date
from database import Session, Department, Employee

def test_database():
    # Создаём тестовые данные
    with Session() as session:
        # Создаём отделы
        hr = Department(name="HR")
        it = Department(name="IT")

        # Создаём сотрудников
        emp1 = Employee(
            full_name="Иванов Иван Иванович",
            birth_date=date(1990, 5, 15),
            telegram_id=123456789,
            department=hr
        )

        emp2 = Employee(
            full_name="Петров Петр Петрович",
            birth_date=date(1985, 8, 22),
            is_head=True,
            department=it
        )

        # Добавляем в БД
        session.add_all([hr, it, emp1, emp2])
        session.commit()

    # Проверяем данные
    with Session() as session:
        # Проверка отделов
        departments = session.query(Department).all()
        print(f"Найдено отделов: {len(departments)}")
        for dept in departments:
            print(f"Отдел: {dept.name}")

        # Проверка сотрудников
        employees = session.query(Employee).all()
        print(f"\nВсе сотрудники:")
        for emp in employees:
            print(f"{emp.full_name} -> {emp.department.name}")

        # Проверка пагинации
        print("\nТест пагинации отделов:")
        depts_page = Department.get_all(session, page=1, per_page=1)
        print(f"Первая страница: {[dept.name for dept in depts_page]}")

        # Проверка каскадного удаления
        session.delete(hr)
        session.commit()
        hr_employees = session.query(Employee).filter_by(department_id=hr.id).all()
        print(f"\nСотрудники отдела HR после удаления: {len(hr_employees)}")

if __name__ == "__main__":
    test_database()