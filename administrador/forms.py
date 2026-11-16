from decimal import Decimal

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.db import transaction

from administrador.models import Marcas, Productos, Usuarios, Ventas_detalles, MensajeContacto


class FormularioEstilizado:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault(
                "class", "rounded-lg border border-outline-variant p-3"
            )


class ImagenProductoInput(forms.FileInput):
    template_name = "django/forms/widgets/file.html"


class MarcaForm(FormularioEstilizado, forms.ModelForm):
    class Meta:
        model = Marcas
        fields = ["nombre_marca"]
        labels = {"nombre_marca": "Nombre de la marca"}


class ProductoForm(FormularioEstilizado, forms.ModelForm):
    precio = forms.CharField(
        label="Precio",
        widget=forms.TextInput(attrs={"inputmode": "decimal", "placeholder": "5.000.000,00"}),
    )

    def clean_precio(self):
        texto = self.cleaned_data["precio"].strip()
        if texto.count(".") >= 2 or ("." in texto and "," in texto):
            texto = texto.replace(".", "")
        texto = texto.replace(",", ".")
        try:
            precio = Decimal(texto)
        except Exception as exc:
            raise forms.ValidationError("Ingresá un precio válido.") from exc
        if precio < Decimal("0.01"):
            raise forms.ValidationError("El precio debe ser mayor que cero.")
        if precio.as_tuple().exponent < -2:
            raise forms.ValidationError("El precio puede tener como máximo dos decimales.")
        if len(precio.as_tuple().digits) > 12 or precio.adjusted() > 9:
            raise forms.ValidationError("El precio supera el máximo permitido.")
        return precio

    class Meta:
        model = Productos
        fields = ["nombre_producto", "marca_producto", "precio", "stock", "imagen"]
        labels = {
            "nombre_producto": "Nombre del producto",
            "marca_producto": "Marca",
            "precio": "Precio",
            "stock": "Unidades disponibles",
            "imagen": "Foto del producto",
        }
        widgets = {
            "stock": forms.NumberInput(attrs={"min": "0", "step": "1"}),
            "imagen": ImagenProductoInput(attrs={"accept": "image/*"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        imagen_actual = self.instance.imagen if self.instance.pk else None
        self._imagen_anterior = imagen_actual.name if imagen_actual else ""
        self.fields["imagen"].help_text = (
            "Selecciona una imagen para usarla como foto principal."
        )

    def save(self, commit=True):
        producto = super().save(commit=commit)
        imagen_nueva = producto.imagen.name if producto.imagen else ""
        if commit and self._imagen_anterior and self._imagen_anterior != imagen_nueva:
            almacen = producto.imagen.storage
            nombre_anterior = self._imagen_anterior
            transaction.on_commit(lambda: almacen.delete(nombre_anterior))
        return producto


class UsuarioForm(FormularioEstilizado, forms.ModelForm):
    class Meta:
        model = Usuarios
        fields = ["nombre_usuario", "email_usuario"]
        labels = {
            "nombre_usuario": "Nombre",
            "email_usuario": "Correo electrónico",
        }


class VentaForm(FormularioEstilizado, forms.ModelForm):
    monto = forms.FloatField(min_value=0.01, label="Monto")
    fecha_venta = forms.DateField(
        label="Fecha de venta",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    class Meta:
        model = Ventas_detalles
        fields = ["usuario", "producto", "monto", "fecha_venta", "forma_de_pago"]
        labels = {
            "usuario": "Cliente",
            "producto": "Producto",
            "forma_de_pago": "Forma de pago",
        }


class RegistroForm(FormularioEstilizado, UserCreationForm):
    email = forms.EmailField(label="Correo electrónico")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ["username", "email"]
        labels = {"username": "Nombre de usuario"}

    def clean_email(self):
        email = self.cleaned_data["email"]
        if Usuarios.objects.filter(email_usuario__iexact=email).exists():
            raise forms.ValidationError("Ya existe un usuario registrado con este correo.")
        return email

class ContactoForm(FormularioEstilizado, forms.ModelForm):
    class Meta:
        model = MensajeContacto
        fields = ["nombre", "email", "mensaje"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Tu nombre"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "tu_correo@ejemplo.com"}),
            "mensaje": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Escribí tu consulta aquí"}),
        }