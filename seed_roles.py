from app import create_app
from app import system as core
from app.extensions import db

app = create_app()

with app.app_context():
    new_roles_added = False

    for role in core.RoleName:
        exists = core.Role.query.filter_by(role_name=role.value).first()
        if not exists:
            role_obj = core.Role()
            role_obj.role_name = role
            db.session.add(role_obj)
            new_roles_added = True

    db.session.commit()
    print("New roles added" if new_roles_added else "Roles already exist, nothing to add")