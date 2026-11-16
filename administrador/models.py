from django.db import models
from django.utils import timezone

# Nuevo modelo para gestionar las marcas de forma dinámica
class Marcas(models.Model):
    nombre_marca = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.nombre_marca

class Usuarios(models.Model):
    nombre_usuario = models.CharField(max_length=30)
    email_usuario = models.EmailField()

    def __str__(self):
        return f'Nombre_usuario: {self.nombre_usuario}, Email_usuario: {self.email_usuario}'

class Productos(models.Model):
    nombre_producto = models.CharField(max_length=30)
    # Reemplazamos el CharField por la relación al modelo Marcas
    marca_producto = models.ForeignKey(Marcas, on_delete=models.PROTECT)
    precio = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    stock = models.PositiveIntegerField(default=0)
    imagen = models.ImageField(upload_to="productos/", blank=True)

    def __str__(self):
        return f'Nombre_producto: {self.nombre_producto}, Marca_Producto: {self.marca_producto.nombre_marca}'

class ImagenProducto(models.Model):
    producto = models.ForeignKey(
        Productos, related_name="galeria", on_delete=models.CASCADE
    )
    imagen = models.ImageField(upload_to="productos/galeria/")
    es_principal = models.BooleanField(default=False)

    class Meta:
        ordering = ["-es_principal", "id"]

    def __str__(self):
        return f"Imagen de {self.producto.nombre_producto}"


class Ventas_detalles(models.Model):
    monto = models.FloatField()
    fecha_venta = models.DateField()
    forma_de_pago = models.CharField(max_length=25)
    producto = models.ForeignKey(Productos, on_delete=models.PROTECT)
    usuario = models.ForeignKey(Usuarios, on_delete=models.PROTECT)
    pedido = models.ForeignKey(
        "cliente.Pedido",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ventas",
    )

    def __str__(self):
        return f'Monto: {self.monto}, Fecha_venta: {self.fecha_venta}, Forma_de_pago: {self.forma_de_pago}, producto: {self.producto.nombre_producto}, usuario: {self.usuario.nombre_usuario}'
    
    
    
class MensajeContacto(models.Model):
    nombre = models.CharField(max_length=100)
    email = models.EmailField()
    mensaje = models.TextField()
    fecha_envio = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f'mensaje de {self.nombre} - ({self.email}) enviado el {self.fecha_envio}'