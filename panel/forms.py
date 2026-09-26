from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from competitions.models import Competition, Submission, Task
from core.files import ALLOWED_MATERIAL_EXT, safe_filename
from core.models import FAQ, CompetitionLevel, Discipline, Document, News, Qualification

DT_FORMAT = "%Y-%m-%dT%H:%M"


class DateTimeLocal(forms.DateTimeInput):
    input_type = "datetime-local"

    def __init__(self, **kw):
        super().__init__(format=DT_FORMAT, **kw)


def validate_material(f, max_size=None):
    if not f or not hasattr(f, "size"):
        return f
    if f.size > (max_size or settings.MATERIAL_MAX_FILE_SIZE):
        raise ValidationError("Файл слишком большой (максимум 10 МБ)")
    if Path(f.name).suffix.lower() not in ALLOWED_MATERIAL_EXT:
        raise ValidationError("Недопустимый тип файла. Разрешены: " + ", ".join(sorted(ALLOWED_MATERIAL_EXT)))
    return f


class CompetitionForm(forms.ModelForm):
    class Meta:
        model = Competition
        fields = ["title", "short_description", "discipline", "level", "format", "location",
                  "start_at", "end_at", "registration_start", "registration_end", "max_participants",
                  "has_contest", "max_attempts", "show_live_standings", "description", "rules",
                  "external_platform", "external_url"]
        widgets = {
            "start_at": DateTimeLocal(), "end_at": DateTimeLocal(),
            "registration_start": DateTimeLocal(), "registration_end": DateTimeLocal(),
            "description": forms.Textarea(attrs={"rows": 6}), "rules": forms.Textarea(attrs={"rows": 8}),
            "short_description": forms.TextInput(),
        }

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        for f in ("start_at", "end_at", "registration_start", "registration_end"):
            self.fields[f].input_formats = [DT_FORMAT, "%Y-%m-%d %H:%M"]
        self.fields["discipline"].queryset = Discipline.objects.filter(is_active=True)
        self.fields["discipline"].empty_label = "— выберите —"
        self.fields["level"].empty_label = "— выберите —"

    def clean(self):
        d = super().clean()
        s, e = d.get("start_at"), d.get("end_at")
        rs, re_ = d.get("registration_start"), d.get("registration_end")
        if s and e and e <= s:
            self.add_error("end_at", "Окончание должно быть позже начала")
        if rs and re_ and re_ <= rs:
            self.add_error("registration_end", "Окончание регистрации должно быть позже её начала")
        if e and re_ and re_ > e:
            self.add_error("registration_end", "Регистрация не может закончиться позже соревнования")
        return d


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title", "max_score", "limits", "statement", "input_spec", "output_spec",
                  "sample_input", "sample_output", "notes", "attachment", "link"]
        widgets = {
            "statement": forms.Textarea(attrs={"rows": 10}),
            "input_spec": forms.Textarea(attrs={"rows": 3}), "output_spec": forms.Textarea(attrs={"rows": 3}),
            "sample_input": forms.Textarea(attrs={"rows": 4, "class": "mono"}),
            "sample_output": forms.Textarea(attrs={"rows": 4, "class": "mono"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_attachment(self):
        return validate_material(self.cleaned_data.get("attachment"))

    def save(self, commit=True):
        t = super().save(commit=False)
        f = self.cleaned_data.get("attachment")
        if f and hasattr(f, "size") and "attachment" in self.changed_data:
            t.attachment_name = safe_filename(f.name)
        if commit:
            t.save()
        return t


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ["score", "comment"]
        widgets = {"comment": forms.Textarea(attrs={"rows": 4, "placeholder": "Комментарий для спортсмена (необязательно)"})}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["score"].required = True
        self.fields["score"].widget.attrs.update({"min": 0, "max": self.instance.task.max_score})

    def clean_score(self):
        s = self.cleaned_data["score"]
        if s is None or s < 0 or s > self.instance.task.max_score:
            raise ValidationError(f"Баллы должны быть от 0 до {self.instance.task.max_score}")
        return s


class AthleteAdminForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ["qualification", "qualification_verified", "is_active"]
        labels = {"is_active": "Учётная запись активна"}


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["title", "category", "description", "body", "file", "url", "order", "is_published", "published_at"]
        widgets = {"body": forms.Textarea(attrs={"rows": 12}), "published_at": DateTimeLocal()}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["published_at"].input_formats = [DT_FORMAT]

    def clean_file(self):
        return validate_material(self.cleaned_data.get("file"))


class NewsForm(forms.ModelForm):
    class Meta:
        model = News
        fields = ["title", "tag", "excerpt", "body", "is_pinned", "is_published", "published_at"]
        widgets = {"body": forms.Textarea(attrs={"rows": 12}), "published_at": DateTimeLocal()}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["published_at"].input_formats = [DT_FORMAT]


class FAQForm(forms.ModelForm):
    class Meta:
        model = FAQ
        fields = ["question", "answer", "category", "order", "is_published"]
        widgets = {"answer": forms.Textarea(attrs={"rows": 6})}


class DisciplineForm(forms.ModelForm):
    class Meta:
        model = Discipline
        fields = ["name", "code", "description", "order", "is_active"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class LevelForm(forms.ModelForm):
    class Meta:
        model = CompetitionLevel
        fields = ["name", "coefficient", "order"]


class QualificationForm(forms.ModelForm):
    class Meta:
        model = Qualification
        fields = ["name", "short", "points", "order"]
