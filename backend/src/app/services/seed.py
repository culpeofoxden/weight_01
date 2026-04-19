from sqlalchemy.orm import Session

from app.models.models import RoleAssignment, Station, User, UserRole
from app.security import hash_password


def seed_initial_data(db: Session) -> None:
    if not db.query(User).filter(User.email == "admin@example.com").one_or_none():
        admin = User(email="admin@example.com", password_hash=hash_password("admin123"))
        viewer = User(email="viewer@example.com", password_hash=hash_password("viewer123"))
        db.add_all([admin, viewer])
        db.flush()
        db.add_all(
            [
                RoleAssignment(user_id=admin.id, role_name=UserRole.admin),
                RoleAssignment(user_id=viewer.id, role_name=UserRole.viewer),
            ]
        )

    if not db.query(Station).filter(Station.station_id == "primary-line-01").one_or_none():
        db.add_all(
            [
                Station(station_id="primary-line-01", station_type="primary", display_name="Primary Line 01"),
                Station(station_id="control-room-01", station_type="control", display_name="Control Room 01"),
            ]
        )

    db.commit()
