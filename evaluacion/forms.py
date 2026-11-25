from django import forms

from .models import Categoria, Evaluacion, Organizacion


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["nombre"]
        widgets = {
            "nombre": forms.TextInput(attrs={
                "class": "form-control evaluation-input",
                "id": "cat_nombre",
                "placeholder": "Ej. ERP, Ofimática, Educación",
            }),
        }

    def clean_nombre(self):
        nombre = " ".join(self.cleaned_data["nombre"].split())
        if not nombre:
            raise forms.ValidationError("El nombre de la categoría es obligatorio.")
        if Categoria.objects.filter(nombre__iexact=nombre).exists():
            raise forms.ValidationError("Esa categoría ya existe.")
        return nombre

# ==========================================
# FORMULARIO: ORGANIZACIÓN (RF-02 / HU-02)
# ==========================================

class OrganizacionForm(forms.ModelForm):
    """Registra una organización asociada al usuario autenticado."""

    class Meta:
        model = Organizacion
        fields = ["nombre"]
        widgets = {
            "nombre": forms.TextInput(attrs={
                "class": "form-control evaluation-input",
                "id": "org_nombre",
                "placeholder": "Ej. Municipio de Milagro",
            }),

        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_nombre(self):
        nombre = self.cleaned_data["nombre"].strip()
        if not nombre:
            raise forms.ValidationError("El nombre de la organización es obligatorio.")
        # Una organización ya registrada por el usuario no se duplica
        existe = Organizacion.objects.filter(usuario=self.user, nombre__iexact=nombre)
        if self.instance.pk:
            existe = existe.exclude(pk=self.instance.pk)
        if self.user and existe.exists():
            raise forms.ValidationError("Ya registraste una organización con ese nombre.")
        return nombre

    def save(self, commit=True):
        org = super().save(commit=False)
        org.usuario = self.user
        if commit:
            org.save()
        return org


# ==========================================
# FORMULARIO: EVALUACIÓN (RF-03 / HU-03)
# ==========================================

class EvaluacionForm(forms.ModelForm):
    """Crea una evaluación; solo muestra las organizaciones del usuario."""

    class Meta:
        model = Evaluacion
        fields = ["organizacion", "software", "categoria", "descripcion"]
        labels = {
            "organizacion": "Organización",
            "software": "Nombre del software",
            "categoria": "Categoría",
            "descripcion": "Descripción",
        }
        widgets = {
            "organizacion": forms.Select(attrs={
                "class": "form-select evaluation-input",
                "id": "organizacion",
            }),
            "software": forms.TextInput(attrs={
                "class": "form-control evaluation-input",
                "id": "software",
                "placeholder": "Ej. Odoo ERP",
            }),
            "categoria": forms.Select(attrs={
                "class": "form-select evaluation-input",
                "id": "categoria",
            }),
            "descripcion": forms.Textarea(attrs={
                "class": "form-control evaluation-input",
                "id": "descripcion",
                "rows": 3,
                "placeholder": "¿Qué necesidad busca resolver?",
            }),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo las organizaciones registradas por este usuario
        if user is not None:
            self.fields["organizacion"].queryset = Organizacion.objects.filter(usuario=user)
        else:
            self.fields["organizacion"].queryset = Organizacion.objects.none()

        self.fields["organizacion"].empty_label = "Selecciona una organización"
        self.fields["categoria"].empty_label = "Selecciona una categoría"
        self.fields["descripcion"].required = False  # opcional según el informe

    def clean_software(self):
        software = self.cleaned_data["software"].strip()
        if not software:
            raise forms.ValidationError("Indica el software a evaluar.")
        return software