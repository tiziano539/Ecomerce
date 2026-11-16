from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import F, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from administrador.models import Productos, Usuarios, Ventas_detalles
from .forms import (
    CheckoutForm,
    ClienteAuthenticationForm,
    PerfilClienteForm,
    UserRegistrationForm,
    UsuarioForm,
)
from .models import Carrito, Cliente, DetallePedido, Pedido

def cliente_requerido(view_func):
    solo_clientes = user_passes_test(
        lambda user: not user.is_staff,
        login_url="index",
        redirect_field_name=None,
    )(view_func)
    return login_required(login_url="login_cliente")(solo_clientes)


def _obtener_o_crear_cliente(user):
    cliente, _ = Cliente.objects.get_or_create(usuario=user)
    return cliente


def login_cliente(request):
    if request.user.is_authenticated:
        return redirect("index" if request.user.is_staff else "panel_cliente")

    form = ClienteAuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.get_user()
        login(request, usuario)
        _obtener_o_crear_cliente(usuario)
        messages.success(request, "Sesión de cliente iniciada.")
        destino = request.POST.get("next", "")
        if url_has_allowed_host_and_scheme(
            destino, {request.get_host()}, require_https=request.is_secure()
        ):
            return redirect(destino)
        return redirect("panel_cliente")

    return render(request, "administrador/cliente/login_cliente.html", {"form": form})


def registro_cliente(request):
    if request.user.is_authenticated:
        return redirect("index" if request.user.is_staff else "panel_cliente")

    form = UserRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = form.save()
            Cliente.objects.create(usuario=user)
        login(request, user)
        messages.success(request, "¡Registro exitoso! Bienvenido/a.")
        return redirect("panel_cliente")

    return render(request, "administrador/cliente/registro.html", {"form": form})


def catalogo(request):
    productos = Productos.objects.select_related("marca_producto").order_by(
        "nombre_producto"
    )
    return render(
        request, "administrador/cliente/catalogo.html", {"productos": productos}
    )


def detalle_producto(request, producto_id):
    producto = get_object_or_404(
        Productos.objects.select_related("marca_producto"), pk=producto_id
    )
    return render(
        request, "administrador/cliente/detalle.html", {"producto": producto}
    )


@cliente_requerido
@require_POST
def agregar_al_carrito(request, producto_id):
    cantidad_texto = request.POST.get("cantidad", "1")
    try:
        cantidad = int(cantidad_texto)
    except (TypeError, ValueError):
        messages.error(request, "Ingresa una cantidad válida.")
        return redirect("detalle", producto_id=producto_id)
    if cantidad < 1:
        messages.error(request, "La cantidad debe ser al menos 1.")
        return redirect("detalle", producto_id=producto_id)

    cliente = _obtener_o_crear_cliente(request.user)
    with transaction.atomic():
        producto = get_object_or_404(
            Productos.objects.select_for_update(), pk=producto_id
        )
        if producto.precio <= 0:
            messages.error(request, "Este producto aún no tiene un precio válido.")
            return redirect("detalle", producto_id=producto.id)
        item = (
            Carrito.objects.select_for_update()
            .filter(cliente=cliente, producto=producto)
            .first()
        )
        nueva_cantidad = (item.cantidad if item else 0) + cantidad
        if nueva_cantidad > producto.stock:
            messages.warning(
                request,
                f"Solo hay {producto.stock} unidades disponibles de {producto.nombre_producto}.",
            )
            return redirect("detalle", producto_id=producto.id)
        if item:
            item.cantidad = nueva_cantidad
            item.save(update_fields=["cantidad"])
        else:
            Carrito.objects.create(
                cliente=cliente,
                producto=producto,
                cantidad=nueva_cantidad,
            )

    messages.success(request, f"{producto.nombre_producto} se agregó al carrito.")
    return redirect("carrito")


@cliente_requerido
def panel_cliente(request):
    cliente = _obtener_o_crear_cliente(request.user)
    ultimo_pedido = (
        Pedido.objects.filter(cliente=cliente).order_by("-fecha").first()
    )
    return render(
        request,
        "administrador/cliente/panel_cliente.html",
        {"cliente": cliente, "ultimo_pedido": ultimo_pedido},
    )


@cliente_requerido
def carrito(request):
    cliente = _obtener_o_crear_cliente(request.user)
    items = Carrito.objects.filter(cliente=cliente).select_related(
        "producto", "producto__marca_producto"
    )
    total = sum((item.subtotal() for item in items), Decimal("0.00"))
    return render(
        request,
        "administrador/cliente/carrito.html",
        {"items": items, "total": total},
    )


@cliente_requerido
@require_POST
def quitar_del_carrito(request, item_id):
    cliente = _obtener_o_crear_cliente(request.user)
    item = get_object_or_404(Carrito, pk=item_id, cliente=cliente)
    item.delete()
    messages.info(request, "Producto eliminado del carrito.")
    return redirect("carrito")


@cliente_requerido
def checkout(request):
    cliente = _obtener_o_crear_cliente(request.user)
    if request.method == "POST":
        form = CheckoutForm(request.POST)
    else:
        form = CheckoutForm(
            initial={
                "direccion": cliente.direccion,
                "ciudad": cliente.ciudad,
            }
        )

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            items = list(
                Carrito.objects.filter(cliente=cliente)
                .select_related("producto")
                .select_for_update()
            )
            if not items:
                messages.warning(request, "Tu carrito está vacío.")
                return redirect("carrito")

            productos = {
                producto.pk: producto
                for producto in Productos.objects.select_for_update().filter(
                    pk__in=[item.producto_id for item in items]
                )
            }
            for item in items:
                producto = productos[item.producto_id]
                if item.cantidad > producto.stock or producto.precio <= 0:
                    messages.error(
                        request,
                        f"No se puede completar la compra de {producto.nombre_producto}; revisa precio y existencias.",
                    )
                    return redirect("carrito")

            total = sum(
                (
                    productos[item.producto_id].precio * item.cantidad
                    for item in items
                ),
                Decimal("0.00"),
            )
            cliente.direccion = form.cleaned_data["direccion"]
            cliente.ciudad = form.cleaned_data["ciudad"]
            cliente.save(update_fields=["direccion", "ciudad"])

            pedido = Pedido.objects.create(
                cliente=cliente,
                total=total,
                metodo_pago=form.cleaned_data["metodo_pago"],
                direccion_envio=cliente.direccion,
                ciudad_envio=cliente.ciudad,
            )
            usuario_venta, _ = Usuarios.objects.update_or_create(
                nombre_usuario=request.user.username,
                defaults={"email_usuario": request.user.email or ""},
            )

            for item in items:
                producto = productos[item.producto_id]
                DetallePedido.objects.create(
                    pedido=pedido,
                    producto=producto,
                    cantidad=item.cantidad,
                    precio_unitario=producto.precio,
                )
                Ventas_detalles.objects.create(
                    monto=float(producto.precio * item.cantidad),
                    fecha_venta=timezone.localdate(),
                    forma_de_pago=pedido.metodo_pago,
                    producto=producto,
                    usuario=usuario_venta,
                    pedido=pedido,
                )
                producto.stock -= item.cantidad
                producto.save(update_fields=["stock"])

            Carrito.objects.filter(pk__in=[item.pk for item in items]).delete()

        messages.success(request, "¡Compra realizada con éxito!")
        return redirect("mis_pedidos")

    items = Carrito.objects.filter(cliente=cliente).select_related("producto")
    if not items.exists():
        messages.warning(request, "Tu carrito está vacío.")
        return redirect("carrito")
    total = sum((item.subtotal() for item in items), Decimal("0.00"))
    return render(
        request,
        "administrador/cliente/checkout.html",
        {"items": items, "total": total, "form": form},
    )


@cliente_requerido
def mis_pedidos(request):
    cliente = _obtener_o_crear_cliente(request.user)
    pedidos = (
        Pedido.objects.filter(cliente=cliente)
        .annotate(items_count=Sum("items__cantidad"))
        .order_by("-fecha")
    )
    return render(
        request, "administrador/cliente/pedidos.html", {"pedidos": pedidos}
    )


@cliente_requerido
@require_POST
def confirmar_pedido(request, pedido_id):
    cliente = _obtener_o_crear_cliente(request.user)
    pedido = get_object_or_404(Pedido, pk=pedido_id, cliente=cliente)
    if pedido.estado != "pendiente":
        messages.warning(request, "Solo puedes confirmar pedidos pendientes.")
        return redirect("mis_pedidos")
    pedido.estado = "pagado"
    pedido.save(update_fields=["estado"])
    messages.success(request, f"El pedido #{pedido.id} fue confirmado.")
    return redirect("mis_pedidos")


@cliente_requerido
@require_POST
def cancelar_pedido(request, pedido_id):
    cliente = _obtener_o_crear_cliente(request.user)
    with transaction.atomic():
        pedido = get_object_or_404(
            Pedido.objects.select_for_update(), pk=pedido_id, cliente=cliente
        )
        if pedido.estado != "pendiente":
            messages.warning(request, "Solo puedes cancelar pedidos pendientes.")
            return redirect("mis_pedidos")

        detalles = list(
            DetallePedido.objects.filter(pedido=pedido).select_related("producto")
        )
        for detalle in detalles:
            Productos.objects.filter(pk=detalle.producto_id).update(
                stock=F("stock") + detalle.cantidad
            )
        Ventas_detalles.objects.filter(pedido=pedido).delete()
        pedido.estado = "cancelado"
        pedido.save(update_fields=["estado"])

    messages.success(request, f"El pedido #{pedido.id} fue cancelado.")
    return redirect("mis_pedidos")


@cliente_requerido
def perfil_cliente(request):
    cliente = _obtener_o_crear_cliente(request.user)
    if request.method == "POST":
        usuario_form = UsuarioForm(request.POST, instance=request.user)
        perfil_form = PerfilClienteForm(request.POST, instance=cliente)
        if usuario_form.is_valid() and perfil_form.is_valid():
            with transaction.atomic():
                usuario_form.save()
                perfil_form.save()
            messages.success(request, "Tus datos se actualizaron correctamente.")
            return redirect("perfil_cliente")
    else:
        usuario_form = UsuarioForm(instance=request.user)
        perfil_form = PerfilClienteForm(instance=cliente)

    return render(
        request,
        "administrador/cliente/perfil.html",
        {"usuario_form": usuario_form, "perfil_form": perfil_form},
    )


@require_POST
def logout_cliente(request):
    logout(request)
    messages.success(request, "Sesión cerrada correctamente.")
    return redirect("index")
