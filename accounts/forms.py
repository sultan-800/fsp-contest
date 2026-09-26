from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.models import Discipline, Qualification

from .models import User

NAME_RE = r"^[A-Za-zА-Яа-яЁё\- ']+$"


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, **kw):
        super().__init__(format="%Y-%m-%d", **kw)


def validate_birth(value):
    if value:
        today = timezone.localdate()
        if value > today or value.year < today.year - 100:
            raise ValidationError("Укажите корректную дату рождения")


class RegistrationForm(UserCreationForm):
    last_name = forms.RegexField(NAME_RE, label="Фамилия", max_length=150,
                                 error_messages={"invalid": "Только буквы, дефис и пробел"})
    first_name = forms.RegexField(NAME_RE, label="Имя", max_length=150,
                                  error_messages={"invalid": "Только буквы, дефис и пробел"})
    middle_name = forms.RegexField(NAME_RE, label="Отчество", max_length=150, required=False,
                                   error_messages={"invalid": "Только буквы, дефис и пробел"})
    email = forms.EmailField(label="Email", help_text="Не публикуется. Нужен для связи и входа.")
    city = forms.CharField(label="Город", max_length=120)
    institution = forms.CharField(label="Учебное заведение / организация", max_length=200, required=False)
    birth_date = forms.DateField(label="Дата рождения", required=False, widget=DateInput(),
                                 validators=[validate_birth], help_text="Видна только организатору")
    qualification = forms.ModelChoiceField(Qualification.objects.all(), label="Разряд / звание", required=False,
                                           empty_label="Без разряда",
                                           help_text="Учитывается в рейтинге после подтверждения организатором")
    disciplines = forms.ModelMultipleChoiceField(Discipline.objects.filter(is_active=True), label="Дисциплины",
                                                 required=False, widget=forms.CheckboxSelectMultiple)
    consent = forms.BooleanField(label="Я даю согласие на обработку персональных данных в соответствии с политикой конфиденциальности",
                                 required=True, error_messages={"required": "Без согласия регистрация невозможна"})
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))

    class Meta:
        model = User
        fields = ["last_name", "first_name", "middle_name", "username", "email", "city", "institution",
                  "birth_date", "qualification", "disciplines"]
        labels = {"username": "Логин"}
        help_texts = {"username": "Латиница, цифры и символы @/./+/-/_"}

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("Этот email уже зарегистрирован")
        return email

    def clean_username(self):
        u = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=u).exists():
            raise ValidationError("Этот логин уже занят")
        return u

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise ValidationError("Бот обнаружен")
        return ""

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.ATHLETE
        user.consent_at = timezone.now()
        user.qualification_verified = False
        if commit:
            user.save()
            self.save_m2m()
        return user


class LoginForm(AuthenticationForm):
    username = forms.CharField(label="Логин или email", max_length=254,
                               widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}))
    error_messages = {
        "invalid_login": "Неверный логин или пароль.",
        "inactive": "Учётная запись отключена.",
    }


class ProfileForm(forms.ModelForm):
    last_name = forms.RegexField(NAME_RE, label="Фамилия", max_length=150)
    first_name = forms.RegexField(NAME_RE, label="Имя", max_length=150)
    middle_name = forms.RegexField(NAME_RE, label="Отчество", max_length=150, required=False)
    birth_date = forms.DateField(label="Дата рождения", required=False, widget=DateInput(), validators=[validate_birth])

    class Meta:
        model = User
        fields = ["last_name", "first_name", "middle_name", "email", "city", "institution", "birth_date",
                  "qualification", "disciplines", "bio"]
        widgets = {"disciplines": forms.CheckboxSelectMultiple, "bio": forms.Textarea(attrs={"rows": 3})}
        help_texts = {"qualification": "При смене разряда требуется повторное подтверждение организатором"}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["qualification"].empty_label = "Без разряда"
        self.fields["disciplines"].queryset = Discipline.objects.filter(is_active=True)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Этот email уже используется")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        if "qualification" in self.changed_data and not user.is_organizer:
            user.qualification_verified = False
        if commit:
            user.save()
            self.save_m2m()
        return user


class PrivacyForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["is_profile_public", "show_institution"]
        labels = {"is_profile_public": "Публичный профиль — другие участники видят мою историю и дисциплины",
                  "show_institution": "Показывать учебное заведение в публичном профиле и рейтинге"}


class DeleteAccountForm(forms.Form):
    password = forms.CharField(label="Текущий пароль", widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))
    confirm = forms.BooleanField(label="Я понимаю, что персональные данные будут безвозвратно удалены")

    def __init__(self, user, *a, **kw):
        self.user = user
        super().__init__(*a, **kw)

    def clean_password(self):
        if not self.user.check_password(self.cleaned_data["password"]):
            raise ValidationError("Неверный пароль")
        return ""
