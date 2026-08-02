from app import create_app
from app.extensions import db
from app.access_control.models import Role, RoleName

app = create_app()

with app.app_context():
    new_roles_added = False
    for role in RoleName:
        exists = Role.query.filter_by(role_name=role).first()
        if not exists:
            db.session.add(Role(role_name=role))
            new_roles_added = True

    db.session.commit()
    print("New roles added" if new_roles_added else "Roles already exist, nothing to add")