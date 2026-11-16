from decimal import Decimal
from io import BytesIO
from tempfile import TemporaryDirectory
from datetime import date

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from administrador.forms import ProductoForm
from administrador.models import Marcas, Productos, Usuarios, Ventas_detalles


class TiendaViewsTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="admin", password="StrongPassword123", is_staff=True
        )
        self.marca = Marcas.objects.create(nombre_marca="AURA")
        self.producto = Productos.objects.create(
            nombre_producto="Lámpara", marca_producto=self.marca
        )
        self.usuario = Usuarios.objects.create(
            nombre_usuario="Cliente", email_usuario="cliente@example.com"
        )

    def test_product_price_accepts_thousands_separator(self):
        form = ProductoForm(data={
            "nombre_producto": "Televisor",
            "marca_producto": self.marca.id,
            "precio": "5.000.000,50",
            "stock": 1,
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["precio"], Decimal("5000000.50"))

    def test_public_pages_render(self):
        for url_name in ("index", "registro", "about", "mostrar_productos", "login"):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)

    def test_staff_pages_require_staff_login(self):
        for url_name in (
            "mostrar_marcas",
            "mostrar_usuarios",
            "mostrar_ventas_detalles",
            "buscar_usuarios",
            "buscar_ventas_detalle",
        ):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertRedirects(
                    response,
                    f"{reverse('login')}?next={reverse(url_name)}",
                    fetch_redirect_response=False,
                )

    def test_regular_account_cannot_open_staff_pages(self):
        usuario = User.objects.create_user(
            username="cliente", password="StrongPassword123"
        )
        self.client.force_login(usuario)
        response = self.client.get(reverse("mostrar_usuarios"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("login")))

    def test_product_management_is_visible_and_available_only_to_staff(self):
        response = self.client.get(reverse("mostrar_productos"))
        self.assertNotContains(response, reverse("crear_producto"))
        self.assertNotContains(
            response, reverse("editar_producto", args=[self.producto.id])
        )
        self.assertContains(response, "Iniciar sesión como personal")

        usuario = User.objects.create_user(username="cliente", password="StrongPassword123")
        self.client.force_login(usuario)
        response = self.client.get(reverse("crear_producto"))
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('crear_producto')}",
            fetch_redirect_response=False,
        )
        response = self.client.get(reverse("editar_producto", args=[self.producto.id]))
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('editar_producto', args=[self.producto.id])}",
            fetch_redirect_response=False,
        )

        self.client.force_login(self.staff)
        response = self.client.get(reverse("mostrar_productos"))
        self.assertContains(response, reverse("crear_producto"))
        self.assertContains(
            response, reverse("editar_producto", args=[self.producto.id])
        )

    def test_staff_pages_and_crud_forms_render(self):
        self.client.force_login(self.staff)
        venta = Ventas_detalles.objects.create(
            monto=100,
            fecha_venta=date(2026, 10, 26),
            forma_de_pago="Efectivo",
            producto=self.producto,
            usuario=self.usuario,
        )
        urls = (
            "mostrar_marcas",
            "mostrar_usuarios",
            "mostrar_ventas_detalles",
            "crear_marca",
            "editar_marca",
            "crear_producto",
            "editar_producto",
            "crear_usuario",
            "editar_usuario",
            "crear_venta",
            "editar_venta",
            "eliminar_producto",
            "eliminar_usuario",
            "eliminar_venta",
            "buscar_usuarios",
            "buscar_ventas_detalle",
        )
        arguments = {
            "editar_marca": [self.marca.id],
            "editar_producto": [self.producto.id],
            "editar_usuario": [self.usuario.id],
            "editar_venta": [venta.id],
            "eliminar_producto": [self.producto.id],
            "eliminar_usuario": [self.usuario.id],
            "eliminar_venta": [venta.id],
        }
        for url_name in urls:
            with self.subTest(url_name=url_name):
                response = self.client.get(
                    reverse(url_name, args=arguments.get(url_name, []))
                )
                self.assertEqual(response.status_code, 200)

    def test_search_pages_filter_existing_records(self):
        self.client.force_login(self.staff)
        venta = Ventas_detalles.objects.create(
            monto=100,
            fecha_venta=date(2026, 10, 26),
            forma_de_pago="Efectivo",
            producto=self.producto,
            usuario=self.usuario,
        )

        response = self.client.get(
            reverse("buscar_usuarios"), {"usuario": "cliente@example.com"}
        )
        self.assertContains(response, self.usuario.nombre_usuario)
        self.assertContains(response, self.usuario.email_usuario)

        response = self.client.get(
            reverse("buscar_ventas_detalle"), {"orden": str(venta.id)}
        )
        self.assertContains(response, self.producto.nombre_producto)
        self.assertContains(response, self.usuario.nombre_usuario)

        response = self.client.get(
            reverse("buscar_productos"), {"marca_producto": self.marca.nombre_marca}
        )
        self.assertContains(response, self.producto.nombre_producto)

    def test_registration_creates_login_and_customer_profile(self):
        response = self.client.post(
            reverse("registro"),
            {
                "username": "nuevo",
                "email": "nuevo@example.com",
                "password1": "DjangoSecurePassword456!",
                "password2": "DjangoSecurePassword456!",
            },
        )
        self.assertRedirects(response, reverse("login"))
        self.assertTrue(User.objects.filter(username="nuevo").exists())
        self.assertTrue(
            Usuarios.objects.filter(
                nombre_usuario="nuevo", email_usuario="nuevo@example.com"
            ).exists()
        )

    def test_product_create_update_delete(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("crear_producto"),
            {
                "nombre_producto": "Silla",
                "marca_producto": self.marca.id,
                "precio": "120.00",
                "stock": "8",
            },
        )
        self.assertRedirects(response, reverse("mostrar_productos"))
        producto = Productos.objects.get(nombre_producto="Silla")

        response = self.client.post(
            reverse("editar_producto", args=[producto.id]),
            {
                "nombre_producto": "Silla nueva",
                "marca_producto": self.marca.id,
                "precio": "125.00",
                "stock": "6",
            },
        )
        self.assertRedirects(response, reverse("mostrar_productos"))
        producto.refresh_from_db()
        self.assertEqual(producto.nombre_producto, "Silla nueva")

        response = self.client.post(reverse("eliminar_producto", args=[producto.id]))
        self.assertRedirects(response, reverse("mostrar_productos"))
        self.assertFalse(Productos.objects.filter(pk=producto.id).exists())

    def test_product_image_upload_edit_and_catalog_display(self):
        self.client.force_login(self.staff)
        image_buffer = BytesIO()
        Image.new("RGB", (2, 2), color="red").save(image_buffer, format="PNG")
        image_bytes = image_buffer.getvalue()

        with TemporaryDirectory() as media_directory:
            with override_settings(MEDIA_ROOT=media_directory):
                response = self.client.post(
                    reverse("crear_producto"),
                    {
                        "nombre_producto": "Mesa",
                        "marca_producto": self.marca.id,
                        "precio": "250.00",
                        "stock": "4",
                        "imagen": SimpleUploadedFile(
                            "mesa.png", image_bytes, content_type="image/png"
                        ),
                    },
                )
                self.assertRedirects(response, reverse("mostrar_productos"))
                producto = Productos.objects.get(nombre_producto="Mesa")
                self.assertTrue(producto.imagen.name.startswith("productos/"))
                self.assertTrue(producto.imagen.storage.exists(producto.imagen.name))

                response = self.client.get(
                    reverse("editar_producto", args=[producto.id])
                )
                self.assertNotContains(response, "Eliminar foto actual")
                self.assertContains(response, "Eliminar imagen")
                self.assertContains(response, "Agregar más fotos")

                response = self.client.get(reverse("catalogo"))
                self.assertContains(response, producto.imagen.url)
                response = self.client.get(reverse("detalle", args=[producto.id]))
                self.assertContains(response, producto.imagen.url)

                with self.captureOnCommitCallbacks(execute=True):
                    response = self.client.post(
                        reverse("editar_producto", args=[producto.id]),
                        {
                            "nombre_producto": producto.nombre_producto,
                            "marca_producto": self.marca.id,
                            "precio": "275.00",
                            "stock": "5",
                            "imagen": SimpleUploadedFile(
                                "mesa-editada.png",
                                image_bytes,
                                content_type="image/png",
                            ),
                        },
                    )
                self.assertRedirects(response, reverse("mostrar_productos"))
                producto.refresh_from_db()
                self.assertTrue(producto.imagen.name.endswith("mesa-editada.png"))
                self.assertEqual(producto.precio, 275)
                self.assertFalse(
                    producto.imagen.storage.exists("productos/mesa.png")
                )

                response = self.client.post(
                    reverse("eliminar_imagen_producto", args=[producto.id])
                )
                self.assertRedirects(
                    response, reverse("editar_producto", args=[producto.id])
                )
                producto.refresh_from_db()
                self.assertFalse(producto.imagen)
                self.assertFalse(
                    producto.imagen.storage.exists("productos/mesa-editada.png")
                )

                response = self.client.post(
                    reverse("editar_producto", args=[producto.id]),
                    {
                        "nombre_producto": producto.nombre_producto,
                        "marca_producto": self.marca.id,
                        "precio": "275.00",
                        "stock": "5",
                        "imagen": SimpleUploadedFile(
                            "mesa-boton.png", image_bytes, content_type="image/png"
                        ),
                    },
                )
                self.assertRedirects(response, reverse("mostrar_productos"))
                producto.refresh_from_db()
                nombre_imagen_boton = producto.imagen.name

                response = self.client.post(
                    reverse("eliminar_imagen_producto", args=[producto.id])
                )
                self.assertRedirects(
                    response, reverse("editar_producto", args=[producto.id])
                )
                producto.refresh_from_db()
                self.assertFalse(producto.imagen)
                self.assertFalse(producto.imagen.storage.exists(nombre_imagen_boton))

    def test_brand_create_update_delete_and_protect_associated_products(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("crear_marca"), {"nombre_marca": "Norte"}
        )
        self.assertRedirects(response, reverse("mostrar_marcas"))
        marca = Marcas.objects.get(nombre_marca="Norte")

        response = self.client.post(
            reverse("editar_marca", args=[marca.id]), {"nombre_marca": "Sur"}
        )
        self.assertRedirects(response, reverse("mostrar_marcas"))
        marca.refresh_from_db()
        self.assertEqual(marca.nombre_marca, "Sur")

        Productos.objects.create(nombre_producto="Mesa", marca_producto=marca)
        response = self.client.post(reverse("eliminar_marca", args=[marca.id]))
        self.assertRedirects(response, reverse("mostrar_marcas"))
        self.assertTrue(Marcas.objects.filter(pk=marca.id).exists())

    def test_user_create_update_delete(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("crear_usuario"),
            {"nombre_usuario": "Nuevo cliente", "email_usuario": "nuevo@example.com"},
        )
        self.assertRedirects(response, reverse("mostrar_usuarios"))
        usuario = Usuarios.objects.get(email_usuario="nuevo@example.com")

        response = self.client.post(
            reverse("editar_usuario", args=[usuario.id]),
            {"nombre_usuario": "Cliente actualizado", "email_usuario": "nuevo@example.com"},
        )
        self.assertRedirects(response, reverse("mostrar_usuarios"))
        usuario.refresh_from_db()
        self.assertEqual(usuario.nombre_usuario, "Cliente actualizado")

        response = self.client.post(reverse("eliminar_usuario", args=[usuario.id]))
        self.assertRedirects(response, reverse("mostrar_usuarios"))
        self.assertFalse(Usuarios.objects.filter(pk=usuario.id).exists())

    def test_sale_create_update_delete_and_protect_related_records(self):
        self.client.force_login(self.staff)
        sale_data = {
            "usuario": self.usuario.id,
            "producto": self.producto.id,
            "monto": "1200.50",
            "fecha_venta": "2026-10-26",
            "forma_de_pago": "Tarjeta",
        }
        response = self.client.post(reverse("crear_venta"), sale_data)
        self.assertRedirects(response, reverse("mostrar_ventas_detalles"))
        venta = Ventas_detalles.objects.get()
        self.assertEqual(venta.fecha_venta, date(2026, 10, 26))
        self.assertEqual(venta.monto, 1200.5)

        updated_data = {**sale_data, "monto": "1500", "forma_de_pago": "Efectivo"}
        response = self.client.post(
            reverse("editar_venta", args=[venta.id]), updated_data
        )
        self.assertRedirects(response, reverse("mostrar_ventas_detalles"))
        venta.refresh_from_db()
        self.assertEqual(venta.forma_de_pago, "Efectivo")

        response = self.client.post(
            reverse("eliminar_producto", args=[self.producto.id])
        )
        self.assertRedirects(response, reverse("mostrar_productos"))
        self.assertTrue(Productos.objects.filter(pk=self.producto.id).exists())
        response = self.client.post(
            reverse("eliminar_usuario", args=[self.usuario.id])
        )
        self.assertRedirects(response, reverse("mostrar_usuarios"))
        self.assertTrue(Usuarios.objects.filter(pk=self.usuario.id).exists())

        response = self.client.post(
            reverse("eliminar_venta", args=[venta.id])
        )
        self.assertRedirects(response, reverse("mostrar_ventas_detalles"))
        self.assertFalse(Ventas_detalles.objects.filter(pk=venta.id).exists())

    def test_invalid_sale_amount_is_not_saved(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("crear_venta"),
            {
                "usuario": self.usuario.id,
                "producto": self.producto.id,
                "monto": "-10",
                "fecha_venta": "2026-10-26",
                "forma_de_pago": "Tarjeta",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Ventas_detalles.objects.count(), 0)

    def test_user_can_log_in_and_log_out(self):
        response = self.client.post(
            reverse("login"),
            {"username": self.staff.username, "password": "StrongPassword123"},
        )
        self.assertRedirects(response, reverse("mostrar_usuarios"))
        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("index"))
