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

    def get_full_name(self, obj):
        return obj.full_name


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
        )


class PatientListItemSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = Patient
        fields = ("id", "hospital_id", "first_name", "last_name", "age", "phone")
