from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.forms.widgets import PasswordInput
from .models import Cliente


class ClienteAuthenticationForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        label="Nombre de usuario",
        widget=forms.TextInput(
            attrs={"autocomplete": "username", "class": "form-control-input"}
        ),
    )
    password = forms.CharField(
        label="Contraseña",
        widget=PasswordInput(
            attrs={"autocomplete": "current-password", "class": "form-control-input"}
        ),
    )

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.user = None

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get("username")
        password = cleaned_data.get("password")
        if username and password:
            self.user = authenticate(
                self.request,
                username=username,
                password=password,
            )
            if self.user is None:
                raise forms.ValidationError("Usuario o contraseña incorrectos.")
            if self.user.is_staff:
                raise forms.ValidationError(
                    "Usa el acceso de administrador para usuarios del panel."
                )
        return cleaned_data

    def get_user(self):
        return self.user


class UserRegistrationForm(UserCreationForm):
    """
    Formulario para registrar un nuevo usuario desde la parte cliente.
    Hereda de UserCreationForm para reutilizar la lógica de creación de usuarios
    de Django y agrega campos personalizados para la información básica.
    """
    # Campo para el nombre de usuario que se mostrará en el formulario.
    username = forms.CharField(max_length=150, label="Nombre de usuario")
    # Correo electrónico obligatorio del usuario.
    email = forms.EmailField(label="Correo electrónico")
    # Contraseña con entrada ocultada para que no se vea al escribir.
    password1 = forms.CharField(widget=PasswordInput, label="Contraseña")
    # Confirmación de la contraseña para validar que ambas coinciden.
    password2 = forms.CharField(widget=PasswordInput, label="Confirmar contraseña")

    class Meta:
        model = User
        # Campos que se renderizan en el formulario y se guardan en el modelo User.
        fields = ['username', 'email', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control-input"

    def clean(self):
        """
        Valida que las dos contraseñas ingresadas coincidan antes de guardar.
        Si no coinciden, agrega un error visual al campo de confirmación.
        """
        cleaned_data = super().clean()
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')

        if password1 and password2 and password1 != password2:
            self.add_error('password2', 'Las contraseñas no coinciden.')

        return cleaned_data

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "Ya existe una cuenta registrada con este correo electrónico."
            )
        return email


class UsuarioForm(forms.ModelForm):
    """
    Formulario para editar la información personal del usuario autenticado.
    Se usa para actualizar nombre, apellido y correo desde el perfil del cliente.
    """
    class Meta:
        model = User
        # Campos del modelo User que se pueden modificar desde este formulario.
        fields = ['first_name', 'last_name', 'email']
        labels = {
            'first_name': 'Nombre',
            'last_name': 'Apellido',
            'email': 'Correo electrónico',
        }
        widgets = {
            # La clase CSS ayuda a mantener un estilo visual consistente en la interfaz.
            'first_name': forms.TextInput(attrs={'class': 'form-control-input', 'placeholder': 'Tu nombre'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control-input', 'placeholder': 'Tu apellido'}),
            'email': forms.EmailInput(attrs={'class': 'form-control-input', 'placeholder': 'ejemplo@correo.com'}),
        }


class PerfilClienteForm(forms.ModelForm):
    """
    Formulario para completar los datos del perfil de un cliente.
    Se usa para guardar información adicional como teléfono, dirección y ciudad.
    """
    class Meta:
        model = Cliente
        # Campos del modelo Cliente que se pueden editar desde el perfil.
        fields = ['telefono', 'direccion', 'ciudad']
        labels = {
            'telefono': 'Teléfono',
            'direccion': 'Dirección',
            'ciudad': 'Ciudad',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control-input"


class CheckoutForm(forms.Form):
    METODOS_PAGO = [
        ("tarjeta", "Tarjeta de crédito o débito"),
        ("transferencia", "Transferencia bancaria"),
        ("efectivo", "Efectivo"),
    ]

    direccion = forms.CharField(max_length=255, label="Dirección de entrega")
    ciudad = forms.CharField(max_length=80, label="Ciudad")
    metodo_pago = forms.ChoiceField(
        choices=METODOS_PAGO,
        label="Método de pago",
        widget=forms.RadioSelect,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["direccion"].widget.attrs["class"] = "form-control-input"
        self.fields["ciudad"].widget.attrs["class"] = "form-control-input"