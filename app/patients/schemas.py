from app.extensions import ma
from app.patients import Patient
from marshmallow import fields


class PatientCreateSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = Patient
        exclude = ("id", "hospital_id", "created_at", "updated_at")

    portal_email = fields.Email(required=False)
    portal_password = fields.Str(required=False, load_only=True)


class PatientResponseSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = Patient
        include_fk = True

    full_name = fields.Method("get_full_name")
    has_portal_account = fields.Method("get_has_portal_account")

    def get_full_name(self, obj):
        return obj.full_name

    def get_has_portal_account(self, obj):
        from app.auth import User
        return User.query.filter_by(patient_id=obj.id).first() is not None

class PatientUpdateSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = Patient
        include_fk = True
        fields = (
            "first_name",
            "last_name",
            "age",
            "gender",
            "phone",
            "address",
            "assigned_doctor_id",
            "blood_group",
            "ward",
            "status",
        )


class PatientListItemSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = Patient
        fields = (
            "id",
            "hospital_id",
            "first_name",
            "last_name",
            "age",
            "phone",
            "status",
        )
