from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import user_passes_test
from django.core.mail import EmailMessage, send_mail
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST, require_http_methods

from administrador.forms import (
    ContactoForm,
    MarcaForm,
    ProductoForm,
    RegistroForm,
    UsuarioForm,
    VentaForm,
)
from administrador.models import (
    ImagenProducto,
    Marcas,
    MensajeContacto,
    Productos,
    Usuarios,
    Ventas_detalles,
)


def mostrar_index(request):
    productos = Productos.objects.select_related("marca_producto").order_by("-id")[:6]
    marcas = Marcas.objects.order_by("nombre_marca")
    return render(request, "administrador/index.html", {"productos": productos, "marcas": marcas})


def registro(request):
    if request.user.is_authenticated:
        return redirect("index")

    form = RegistroForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            usuario_auth = form.save()
            Usuarios.objects.create(
                nombre_usuario=usuario_auth.username,
                email_usuario=usuario_auth.email,
            )
        messages.success(request, "Tu cuenta fue creada. Ya puedes iniciar sesión.")
        return redirect("login")

    return render(request, "administrador/registro.html", {"form": form})


def about(request):
    return render(request, "administrador/about.html")


def mostrar_productos(request):
    productos = Productos.objects.select_related("marca_producto").order_by("nombre_producto")
    return render(request, "administrador/productos.html", {"productos": productos})


def _es_personal(user):
    return user.is_authenticated and user.is_staff


requiere_personal = user_passes_test(_es_personal, login_url="login")


@requiere_personal
def mostrar_marcas(request):
    marcas = Marcas.objects.order_by("nombre_marca")
    return render(request, "administrador/marcas.html", {"marcas": marcas})


@requiere_personal
def mostrar_usuarios(request):
    usuarios = Usuarios.objects.order_by("nombre_usuario")
    return render(request, "administrador/usuarios.html", {"usuarios": usuarios})


@requiere_personal
def mostrar_ventas_detalles(request):
    ventas = Ventas_detalles.objects.select_related("producto", "usuario").order_by("-fecha_venta", "-id")
    return render(request, "administrador/ventas.html", {"ventas": ventas})


def _guardar_formulario(
    request,
    form_class,
    titulo,
    success_url,
    instance=None,
    template="administrador/formulario.html",
):
    form = form_class(request.POST or None, request.FILES or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        producto_guardado = form.save()
        if isinstance(producto_guardado, Productos):
            if request.FILES.get("imagen"):
                producto_guardado.galeria.all().delete()
                ImagenProducto.objects.create(
                    producto=producto_guardado,
                    imagen=producto_guardado.imagen.name,
                    es_principal=True,
                )
            imagenes_nuevas = request.FILES.getlist("imagenes_adicionales")
            for imagen in imagenes_nuevas:
                ImagenProducto.objects.create(
                    producto=producto_guardado,
                    imagen=imagen,
                    es_principal=False,
                )
            if imagenes_nuevas and not producto_guardado.imagen:
                primera = producto_guardado.galeria.first()
                if primera:
                    primera.es_principal = True
                    primera.save(update_fields=["es_principal"])
                    producto_guardado.imagen = primera.imagen.name
                    producto_guardado.save(update_fields=["imagen"])
        messages.success(request, f"{titulo} guardado correctamente.")
        return redirect(success_url)
    return render(
        request,
        template,
        {"form": form, "titulo": titulo, "producto": instance},
    )


@requiere_personal
def crear_producto(request):
    return _guardar_formulario(
        request,
        ProductoForm,
        "Crear producto",
        "mostrar_productos",
        template="administrador/crear_producto.html",
    )


@requiere_personal
def crear_marca(request):
    return _guardar_formulario(request, MarcaForm, "Crear marca", "mostrar_marcas")


@requiere_personal
def editar_marca(request, marca_id):
    marca = get_object_or_404(Marcas, pk=marca_id)
    return _guardar_formulario(request, MarcaForm, "Editar marca", "mostrar_marcas", marca)


@requiere_personal
@require_POST
def eliminar_marca(request, marca_id):
    marca = get_object_or_404(Marcas, pk=marca_id)
    try:
        marca.delete()
    except ProtectedError:
        messages.error(request, "No se puede eliminar esta marca porque tiene productos asociados.")
    else:
        messages.success(request, "Marca eliminada correctamente.")
    return redirect("mostrar_marcas")


@requiere_personal
def editar_producto(request, producto_id):
    producto = get_object_or_404(Productos, pk=producto_id)
    return _guardar_formulario(
        request,
        ProductoForm,
        "Producto actualizado",
        "mostrar_productos",
        producto,
        "administrador/actualizar_producto.html",
    )


@requiere_personal
@require_POST
def eliminar_imagen_producto(request, producto_id):
    producto = get_object_or_404(Productos, pk=producto_id)
    nombre_imagen = producto.imagen.name if producto.imagen else ""
    if nombre_imagen:
        producto.galeria.filter(es_principal=True).delete()
        Productos.objects.filter(pk=producto.pk).update(imagen="")
        producto.refresh_from_db()
        producto._meta.get_field("imagen").storage.delete(nombre_imagen)
        siguiente = producto.galeria.order_by("id").first()
        if siguiente:
            siguiente.es_principal = True
            siguiente.save(update_fields=["es_principal"])
            producto.imagen.name = siguiente.imagen.name
            producto.save(update_fields=["imagen"])
        messages.success(request, "La foto principal se eliminó correctamente.")
    else:
        messages.info(request, "Este producto no tiene una foto principal.")
    return redirect("editar_producto", producto_id=producto.id)


@requiere_personal
@require_POST
def establecer_imagen_principal(request, producto_id, imagen_id):
    producto = get_object_or_404(Productos, pk=producto_id)
    producto.galeria.update(es_principal=False)
    imagen = get_object_or_404(ImagenProducto, pk=imagen_id, producto=producto)
    imagen.es_principal = True
    imagen.save(update_fields=["es_principal"])
    producto.imagen.name = imagen.imagen.name
    producto.save(update_fields=["imagen"])
    messages.success(request, "Se cambió la foto principal del producto.")
    return redirect("editar_producto", producto_id=producto.id)


@requiere_personal
@require_POST
def eliminar_foto_galeria(request, producto_id, imagen_id):
    producto = get_object_or_404(Productos, pk=producto_id)
    imagen = get_object_or_404(ImagenProducto, pk=imagen_id, producto=producto)
    era_principal = imagen.es_principal
    imagen.imagen.delete(save=False)
    imagen.delete()
    if era_principal:
        siguiente = producto.galeria.order_by("id").first()
        if siguiente:
            siguiente.es_principal = True
            siguiente.save(update_fields=["es_principal"])
            producto.imagen.name = siguiente.imagen.name
        else:
            producto.imagen = ""
        producto.save(update_fields=["imagen"])
    messages.success(request, "Foto eliminada correctamente.")
    return redirect("editar_producto", producto_id=producto.id)


@requiere_personal
@require_http_methods(["GET", "POST"])
def eliminar_producto(request, producto_id):
    producto = get_object_or_404(Productos, pk=producto_id)
    if request.method == "GET":
        return render(
            request,
            "administrador/eliminar_producto.html",
            {"producto": producto},
        )
    try:
        producto.delete()
    except ProtectedError:
        messages.error(request, "No se puede eliminar este producto porque tiene ventas asociadas.")
    else:
        messages.success(request, "Producto eliminado correctamente.")
    return redirect("mostrar_productos")


@requiere_personal
def crear_usuario(request):
    return _guardar_formulario(
        request,
        UsuarioForm,
        "Crear usuario",
        "mostrar_usuarios",
        template="administrador/crear_usuarios.html",
    )


@requiere_personal
def editar_usuario(request, usuario_id):
    usuario = get_object_or_404(Usuarios, pk=usuario_id)
    return _guardar_formulario(
        request,
        UsuarioForm,
        "Editar usuario",
        "mostrar_usuarios",
        usuario,
        "administrador/actualizar.usuario.html",
    )

@requiere_personal
@require_http_methods(["GET", "POST"])
def eliminar_usuario(request, usuario_id):
    usuario = get_object_or_404(Usuarios, pk=usuario_id)
    if request.method == "GET":
        return render(
            request,
            "administrador/eliminar_usuarios.html",
            {"usuario": usuario},
        )
    try:
        usuario.delete()
    except ProtectedError:
        messages.error(request, "No se puede eliminar este usuario porque tiene ventas asociadas.")
    else:
        messages.success(request, "Usuario eliminado correctamente.")
    return redirect("mostrar_usuarios")


@requiere_personal
def crear_venta(request):
    return _guardar_formulario(
        request,
        VentaForm,
        "Crear venta",
        "mostrar_ventas_detalles",
        template="administrador/crear_ventas.html",
    )


@requiere_personal
def editar_venta(request, venta_id):
    venta = get_object_or_404(Ventas_detalles, pk=venta_id)
    return _guardar_formulario(
        request,
        VentaForm,
        "Editar venta",
        "mostrar_ventas_detalles",
        venta,
        "administrador/actualizar_ventas_detalles.html",
    )


@requiere_personal
@require_http_methods(["GET", "POST"])
def eliminar_venta(request, venta_id):
    venta = get_object_or_404(Ventas_detalles, pk=venta_id)
    if request.method == "GET":
        return render(
            request,
            "administrador/eliminar_ventas_detalle.html",
            {"detalle": venta},
        )
    venta.delete()
    messages.success(request, "Venta eliminada correctamente.")
    return redirect("mostrar_ventas_detalles")


def login(request):
    if request.user.is_authenticated:
        return redirect("index")

    error = None
    if request.method == "POST":
        username = request.POST.get("username", "")
        password = request.POST.get("password", "")
        usuario = authenticate(request, username=username, password=password)
        if usuario is not None:
            auth_login(request, usuario)
            destino = request.POST.get("next", "")
            if url_has_allowed_host_and_scheme(destino, {request.get_host()}):
                return redirect(destino)
            return redirect("mostrar_usuarios" if usuario.is_staff else "index")
        error = "El usuario o la contraseña no son correctos."

    return render(request, "administrador/login.html", {"error": error})


def logout(request):
    if request.method == "POST":
        auth_logout(request)
    return redirect("index")


def buscar_productos(request):
    marca_producto = request.GET.get("marca_producto", "").strip()
    productos = Productos.objects.select_related("marca_producto").order_by("nombre_producto")
    if marca_producto:
        productos = productos.filter(
            marca_producto__nombre_marca__icontains=marca_producto
        )
    contexto = {"productos": productos, "marca_producto": marca_producto}
    if marca_producto and not productos.exists():
        contexto["respuesta"] = (
            f"No se encontraron productos para la marca {marca_producto}."
        )
    elif not marca_producto:
        contexto["respuesta"] = (
            "Por favor, ingresa el nombre de una marca para buscar productos."
        )
    return render(request, "administrador/productos.html", contexto)


@requiere_personal
def buscar_usuarios(request):
    consulta = request.GET.get("usuario", "").strip()
    if consulta:
        resultados = Usuarios.objects.filter(
            Q(nombre_usuario__icontains=consulta)
            | Q(email_usuario__icontains=consulta)
        ).order_by("nombre_usuario")
    else:
        resultados = Usuarios.objects.none()
    return render(
        request,
        "administrador/buscar_usuarios.html",
        {"resultados": resultados, "consulta": consulta},
    )


@requiere_personal
def buscar_ventas_detalle(request):
    orden = request.GET.get("orden", "").strip()
    resultados = Ventas_detalles.objects.select_related(
        "producto", "usuario"
    ).order_by("-fecha_venta", "-id")
    if orden.isdecimal():
        resultados = resultados.filter(pk=int(orden))
    else:
        resultados = Ventas_detalles.objects.none()
    return render(
        request,
        "administrador/buscar_ventas_detalle.html",
        {"resultados": resultados, "orden": orden},
    )
    
def politica_privacidad(request):
    return render(request, "administrador/politica_privacidad.html")

def terminos_condiciones(request):
    return render(request, "administrador/terminos_condiciones.html")

def contacto(request):
    if request.method == 'POST':
        form = ContactoForm(request.POST)
        if form.is_valid():
            contacto_obj = form.save()
            
            # Correo HTML al administrador
            template_html = render_to_string('administrador/email-template.html', {
                'nombre': contacto_obj.nombre,
                'email': contacto_obj.email,
                'mensaje': contacto_obj.mensaje,
                'fecha': contacto_obj.fecha_envio,
                'asunto': 'Nueva consulta web - AutoPartes UDOTEC', # <--- Asunto definido de forma estática
            })
            
            email_admin = EmailMessage(
                subject=f'Nuevo mensaje de contacto de {contacto_obj.nombre}',
                body=template_html,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[settings.CONTACT_EMAIL],
            )
            email_admin.content_subtype = "html"
            try:
                email_admin.send(fail_silently=False)
            except Exception as exc:
                messages.warning(request, 'La consulta fue guardada, pero el correo al administrador no pudo enviarse. Revisa la configuración SMTP.')
                print(f'Error al enviar correo al administrador: {exc}')
            
            # Respuesta automática al usuario
            try:
                send_mail(
                    subject='Hemos recibido tu consulta - AutoPartes UDOTEC',
                    message=f'Hola {contacto_obj.nombre},\n\nGracias por comunicarte con nosotros. Hemos recibido tu mensaje y te responderemos a la brevedad.\n\nAtentamente,\nEl equipo de AutoPartes UDOTEC.',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[contacto_obj.email],
                    fail_silently=False,
                )
            except Exception as exc:
                print(f'Error al enviar correo de confirmación: {exc}')
            
            # Agregamos el mensaje de éxito que capturará tu template con Toastr
            messages.success(request, '¡Tu mensaje ha sido enviado con éxito!')
            return redirect('gracias') # <--- Redirige a la página de gracias
    else:
        form = ContactoForm()
        
    return render(request, 'administrador/contacto.html', {'form': form})

def pagina_de_gracias(request):
    return render(request, 'administrador/gracias.html')

@requiere_personal
def listar_mensajes(request):
    # Recuperamos todos los mensajes ordenados por fecha de envio descendente
    mensajes_listado = MensajeContacto.objects.all().order_by('-fecha_envio')

    # Configuramos el paginador (por ejemplo, 5 mensajes por página)
    paginator = Paginator(mensajes_listado, 5)
    page_number = request.GET.get('page')
    mensajes = paginator.get_page(page_number)

    return render(request, 'administrador/listar_mensaje.html', {'mensajes': mensajes})