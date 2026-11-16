from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from administrador.models import Marcas, Productos, Usuarios, Ventas_detalles
from .models import Carrito, Cliente, DetallePedido, Pedido


class ClienteViewsTests(TestCase):
    def setUp(self):
        self.marca = Marcas.objects.create(nombre_marca="AURA")
        self.producto = Productos.objects.create(
            nombre_producto="Lámpara",
            marca_producto=self.marca,
            precio=Decimal("1250.00"),
            stock=5,
        )
        self.user = User.objects.create_user(
            username="comprador",
            email="comprador@example.com",
            password="SecurePass123!",
        )
        self.cliente = Cliente.objects.create(usuario=self.user)

    def test_public_catalog_and_product_detail_render(self):
        response = self.client.get(reverse("catalogo"))
        self.assertContains(response, self.producto.nombre_producto)
        self.assertContains(response, "$1250.00")
        self.assertContains(response, "Inicia sesión para comprar")

        response = self.client.get(reverse("detalle", args=[self.producto.id]))
        self.assertContains(response, self.producto.nombre_producto)
        self.assertContains(response, self.marca.nombre_marca)
        self.assertContains(response, "Inicia sesión para comprar")

    def test_registration_creates_customer_and_logs_in(self):
        response = self.client.post(
            reverse("registro_cliente"),
            {
                "username": "cliente_nuevo",
                "email": "nuevo@example.com",
                "password1": "StrongPassword456!",
                "password2": "StrongPassword456!",
            },
        )
        self.assertRedirects(response, reverse("panel_cliente"))
        user = User.objects.get(username="cliente_nuevo")
        self.assertTrue(Cliente.objects.filter(usuario=user).exists())
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.id)

    def test_login_rejects_admin_account(self):
        admin = User.objects.create_user(
            username="admin",
            password="SecurePass123!",
            is_staff=True,
        )
        response = self.client.post(
            reverse("login_cliente"),
            {"username": admin.username, "password": "SecurePass123!"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "acceso de administrador")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_add_to_cart_and_checkout_creates_order_and_sale(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("agregar_al_carrito", args=[self.producto.id]),
            {"cantidad": "2"},
        )
        self.assertRedirects(response, reverse("carrito"))
        item = Carrito.objects.get(cliente=self.cliente, producto=self.producto)
        self.assertEqual(item.cantidad, 2)

        response = self.client.post(
            reverse("checkout"),
            {
                "direccion": "Calle 123",
                "ciudad": "Buenos Aires",
                "metodo_pago": "tarjeta",
            },
        )
        self.assertRedirects(response, reverse("mis_pedidos"))
        pedido = Pedido.objects.get(cliente=self.cliente)
        self.assertEqual(pedido.total, Decimal("2500.00"))
        self.assertEqual(pedido.direccion_envio, "Calle 123")
        self.assertEqual(pedido.items.get().cantidad, 2)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 3)
        self.assertFalse(Carrito.objects.filter(cliente=self.cliente).exists())
        self.assertTrue(Ventas_detalles.objects.filter(pedido=pedido).exists())
        self.assertTrue(Usuarios.objects.filter(nombre_usuario=self.user.username).exists())
        response = self.client.get(reverse("mis_pedidos"))
        self.assertContains(response, self.producto.nombre_producto)
        response = self.client.get(reverse("panel_cliente"))
        self.assertContains(response, f"Orden #{pedido.id}")

    def test_customer_can_log_in_with_username_and_password(self):
        response = self.client.post(
            reverse("login_cliente"),
            {"username": self.user.username, "password": "SecurePass123!"},
        )
        self.assertRedirects(response, reverse("panel_cliente"))
        self.assertIn("_auth_user_id", self.client.session)

    def test_checkout_rejects_insufficient_stock_without_partial_order(self):
        self.client.force_login(self.user)
        Carrito.objects.create(
            cliente=self.cliente, producto=self.producto, cantidad=3
        )
        self.producto.stock = 1
        self.producto.save(update_fields=["stock"])

        response = self.client.post(
            reverse("checkout"),
            {
                "direccion": "Calle 123",
                "ciudad": "Buenos Aires",
                "metodo_pago": "tarjeta",
            },
        )
        self.assertRedirects(response, reverse("carrito"))
        self.assertFalse(Pedido.objects.exists())
        self.assertEqual(
            Carrito.objects.get(cliente=self.cliente, producto=self.producto).cantidad,
            3,
        )
        self.assertEqual(Productos.objects.get(pk=self.producto.pk).stock, 1)

    def test_customer_can_cancel_own_pending_order_and_restore_inventory(self):
        self.client.force_login(self.user)
        pedido = Pedido.objects.create(cliente=self.cliente, total=Decimal("1250.00"))
        DetallePedido.objects.create(
            pedido=pedido,
            producto=self.producto,
            cantidad=1,
            precio_unitario=self.producto.precio,
        )
        self.producto.stock -= 1
        self.producto.save(update_fields=["stock"])

        response = self.client.post(
            reverse("cancelar_pedido", args=[pedido.id])
        )
        self.assertRedirects(response, reverse("mis_pedidos"))
        pedido.refresh_from_db()
        self.producto.refresh_from_db()
        self.assertEqual(pedido.estado, "cancelado")
        self.assertEqual(self.producto.stock, 5)

    def test_customer_pages_require_login(self):
        for route in ("panel_cliente", "carrito", "checkout", "mis_pedidos", "perfil_cliente"):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertRedirects(
                    response,
                    f"{reverse('login_cliente')}?next={reverse(route)}",
                    fetch_redirect_response=False,
                )

    def test_staff_accounts_are_redirected_out_of_customer_account_pages(self):
        admin = User.objects.create_user(
            username="admin",
            password="SecurePass123!",
            is_staff=True,
        )
        self.client.force_login(admin)
        response = self.client.get(reverse("panel_cliente"))
        self.assertRedirects(response, reverse("index"))
        response = self.client.get(reverse("carrito"))
        self.assertRedirects(response, reverse("index"))

    def test_authenticated_customer_pages_render(self):
        self.client.force_login(self.user)
        Carrito.objects.create(
            cliente=self.cliente, producto=self.producto, cantidad=1
        )
        for route in ("panel_cliente", "carrito", "checkout", "mis_pedidos", "perfil_cliente"):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)

        response = self.client.post(
            reverse("perfil_cliente"),
            {
                "first_name": "Ana",
                "last_name": "García",
                "email": "ana@example.com",
                "telefono": "555-0101",
                "direccion": "Calle 123",
                "ciudad": "Buenos Aires",
            },
        )
        self.assertRedirects(response, reverse("perfil_cliente"))
        self.user.refresh_from_db()
        self.cliente.refresh_from_db()
        self.assertEqual(self.user.first_name, "Ana")
        self.assertEqual(self.cliente.direccion, "Calle 123")
