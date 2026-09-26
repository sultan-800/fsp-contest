from pathlib import Path

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError

from core.files import ALLOWED_CODE_EXT, safe_filename

from .models import Submission


class SubmissionForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ["language", "code", "file"]
        widgets = {
            "code": forms.Textarea(attrs={"spellcheck": "false", "autocomplete": "off", "autocapitalize": "off",
                                          "wrap": "off", "rows": 18, "placeholder": "// Вставьте или напишите решение здесь…",
                                          "data-editor": "1"}),
        }

    def clean_code(self):
        code = self.cleaned_data.get("code", "")
        if len(code) > settings.SUBMISSION_MAX_CODE_LENGTH:
            raise ValidationError(f"Код слишком длинный (максимум {settings.SUBMISSION_MAX_CODE_LENGTH} символов)")
        return code.replace("\x00", "")

    def clean_file(self):
        f = self.cleaned_data.get("file")
        if not f:
            return f
        if f.size > settings.SUBMISSION_MAX_FILE_SIZE:
            raise ValidationError("Файл больше 256 КБ")
        ext = Path(f.name).suffix.lower()
        if ext not in ALLOWED_CODE_EXT:
            raise ValidationError("Недопустимое расширение. Разрешены исходные коды: " + ", ".join(sorted(ALLOWED_CODE_EXT)))
        return f

    def clean(self):
        data = super().clean()
        code, f = (data.get("code") or "").strip(), data.get("file")
        if not code and not f:
            raise ValidationError("Введите код решения или прикрепите файл")
        if code and f:
            raise ValidationError("Выберите один способ: код в редакторе или файл")
        return data

    def save(self, commit=True):
        sub = super().save(commit=False)
        f = self.cleaned_data.get("file")
        if f:
            sub.original_filename = safe_filename(f.name, "solution.txt")
            raw = f.read()
            f.seek(0)
            try:
                sub.code = raw.decode("utf-8").replace("\x00", "")
            except UnicodeDecodeError:
                try:
                    sub.code = raw.decode("cp1251")
                except UnicodeDecodeError:
                    sub.code = ""
        if commit:
            sub.save()
        return sub
