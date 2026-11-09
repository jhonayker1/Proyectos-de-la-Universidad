from app.database.session import SessionLocal, check_database_connection, init_db
from app.main import seed_initial_admin


def main() -> None:
    check_database_connection()
    init_db()
    with SessionLocal() as db:
        seed_initial_admin(db)
    print("Base de datos del inventario lista.")


if __name__ == "__main__":
    main()
