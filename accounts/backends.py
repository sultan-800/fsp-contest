from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrUsernameBackend(ModelBackend):
    """Вход по логину или email. Время ответа выравнивается для несуществующих пользователей."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        if not username or not password:
            return None
        field = "email__iexact" if "@" in username else "username__iexact"
        try:
            user = User.objects.get(**{field: username.strip()})
        except (User.DoesNotExist, User.MultipleObjectsReturned):
            User().set_password(password)  # защита от timing-атак на перебор логинов
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
