from app.extensions import ma
from app.patients import Patient
from marshmallow import fields


class PatientCreateSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = Patient
        exclude = ("id", "hospital_id", "created_at", "updated_at")



class PatientResponseSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = Patient
        include_fk = True

    full_name = fields.Method("get_full_name")
    has_portal_account = fields.Method("get_has_portal_account")
    portal_email = fields.Method("get_portal_email")

    def get_full_name(self, obj):
        return obj.full_name

    def get_has_portal_account(self, obj):
        return obj.portal_user is not None

    def get_portal_email(self, obj):
        return obj.portal_user.email if obj.portal_user else None


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
            "has_portal_account",
            "portal_email",
            "assigned_doctor_name",
        )

    has_portal_account = fields.Method("get_has_portal_account")
    portal_email = fields.Method("get_portal_email")
    assigned_doctor_name = fields.Method("get_assigned_doctor_name")

    def get_has_portal_account(self, obj):
        return obj.portal_user is not None

    def get_portal_email(self, obj):
        return obj.portal_user.email if obj.portal_user else None

    def get_assigned_doctor_name(self, obj):
        if not obj.assigned_doctor:
            return None
        return obj.assigned_doctor.full_name
