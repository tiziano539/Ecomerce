from django.db import models
from django.contrib.auth.models import User
from administrador.models import Productos

class Cliente(models.Model):
    """Perfil de comprador asociado uno a uno con una cuenta de autenticacion Django."""

    # Cada cuenta tiene un solo perfil; al eliminar la cuenta, se elimina el perfil.
    usuario = models.OneToOneField(User, on_delete=models.CASCADE)
    # Datos de contacto opcionales del comprador.
    telefono = models.CharField(max_length=20, blank=True, null=True)
    direccion = models.CharField(max_length=255, blank=True, null=True)
    ciudad = models.CharField(max_length=80, blank=True, null=True)
    # Momento de creacion del perfil, asignado automaticamente.
    fecha_registro = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        """Devuelve el nombre de usuario de la cuenta asociada."""
        return self.usuario.username


class Carrito(models.Model):
    """Producto y cantidad que un cliente mantiene en su carrito."""

    # Si se elimina el cliente o producto, tambien se elimina esta linea del carrito.
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE)
    producto = models.ForeignKey(Productos, on_delete=models.CASCADE)
    # Unidades solicitadas y fecha en que el producto se agrego al carrito.
    cantidad = models.PositiveIntegerField(default=1)
    fecha_agregado = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["cliente", "producto"],
                name="unique_cliente_producto_carrito",
            )
        ]

    def subtotal(self):
        """Calcula el precio actual del producto multiplicado por la cantidad."""
        return self.producto.precio * self.cantidad


class Pedido(models.Model):
    """Compra de un cliente con fecha, total, estado y metodo de pago."""

    # Estados permitidos para seguir el progreso de la compra.
    ESTADOS = [
        ("pendiente", "Pendiente"),
        ("pagado", "Pagado"),
        ("enviado", "Enviado"),
        ("entregado", "Entregado"),
        ("cancelado", "Cancelado"),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE)
    fecha = models.DateTimeField(auto_now_add=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente")
    metodo_pago = models.CharField(max_length=50, default="efectivo")
    direccion_envio = models.CharField(max_length=255, blank=True)
    ciudad_envio = models.CharField(max_length=80, blank=True)

    def __str__(self):
        """Identifica el pedido por su numero y cliente."""
        return f"Pedido {self.id} - {self.cliente}"


class DetallePedido(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="items")
    producto = models.ForeignKey(Productos, on_delete=models.CASCADE)
    cantidad = models.PositiveIntegerField()
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)

    def subtotal(self):
        """Calcula el subtotal usando el precio unitario guardado en el pedido."""
        return self.cantidad * self.precio_unitario