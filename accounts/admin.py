from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as Base

from .models import User


@admin.register(User)
class UserAdmin(Base):
    list_display = ("username", "email", "last_name", "first_name", "role", "rating", "is_active")
    list_filter = ("role", "is_active", "qualification_verified")
    fieldsets = Base.fieldsets + (("ФСП Контест", {"fields": (
        "role", "middle_name", "birth_date", "city", "institution", "qualification", "qualification_verified",
        "disciplines", "bio", "is_profile_public", "show_institution", "consent_at", "rating", "rating_position")}),)
