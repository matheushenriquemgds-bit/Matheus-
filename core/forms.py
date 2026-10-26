from django import forms


class EstiloBootstrap:
    """Aplica as classes CSS do Bootstrap aos widgets do formulário."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            w = campo.widget
            if isinstance(w, forms.CheckboxInput):
                css = "form-check-input"
            elif isinstance(w, (forms.Select, forms.SelectMultiple)):
                css = "form-select"
            else:
                css = "form-control"
            w.attrs["class"] = f"{w.attrs.get('class', '')} {css}".strip()
            if isinstance(w, forms.Textarea):
                w.attrs.setdefault("rows", 3)


class FormBase(EstiloBootstrap, forms.ModelForm):
    pass


class DataInput(forms.DateInput):
    input_type = "date"

    def __init__(self, attrs=None):
        super().__init__(attrs, format="%Y-%m-%d")


class HoraInput(forms.TimeInput):
    input_type = "time"

    def __init__(self, attrs=None):
        super().__init__(attrs, format="%H:%M")
