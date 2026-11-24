import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash

import app as app_module
import seed_v2


PROJECT_DIR = Path(__file__).resolve().parents[1]


class TechStockAppTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = app_module.DB_PATH
        self.original_testing = app_module.app.config["TESTING"]
        app_module.DB_PATH = os.path.join(self.temp_dir.name, "test.db")
        app_module.app.config.update(TESTING=True, SECRET_KEY="test-secret")

        conn = sqlite3.connect(app_module.DB_PATH)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript((PROJECT_DIR / "database.sql").read_text(encoding="utf-8"))
        conn.executescript((PROJECT_DIR / "migration_v2.sql").read_text(encoding="utf-8"))
        conn.executemany(
            """
            INSERT INTO Usuarios
                (nome_completo, email, senha_hash, perfil_acesso, status)
            VALUES (?, ?, ?, ?, 'ATIVO')
            """,
            (
                ("Operador de Teste", "operador@test.local", generate_password_hash("operador123"), "OPERADOR"),
                ("Gerente de Teste", "gerente@test.local", generate_password_hash("gerente123"), "GERENTE"),
            ),
        )
        conn.commit()
        conn.close()
        self.client = app_module.app.test_client()

    def tearDown(self):
        app_module.DB_PATH = self.original_db_path
        app_module.app.config["TESTING"] = self.original_testing
        self.temp_dir.cleanup()

    def login_as(self, role):
        credentials = {
            "OPERADOR": ("operador@test.local", "operador123"),
            "GERENTE": ("gerente@test.local", "gerente123"),
        }
        email, password = credentials[role]
        response = self.client.post(
            "/login", data={"email": email, "senha": password}
        )
        self.assertEqual(response.status_code, 302)

    def connect(self):
        conn = sqlite3.connect(app_module.DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def product_id(self, sku):
        conn = self.connect()
        try:
            return conn.execute(
                "SELECT id FROM Produtos WHERE sku = ?", (sku,)
            ).fetchone()["id"]
        finally:
            conn.close()

    def test_dashboard_uses_joined_names_and_low_stock_threshold(self):
        conn = self.connect()
        conn.execute(
            "UPDATE Produtos SET quantidade_estoque = estoque_minimo WHERE sku = 'RAM001'"
        )
        conn.commit()
        conn.close()

        self.login_as("OPERADOR")
        response = self.client.get("/inicio")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Tech Distribuidora LTDA", body)
        self.assertIn("Risco de Ruptura / Reposição Necessária", body)
        self.assertIn("Memoria RAM 16GB", body)

    def test_manager_can_create_product_and_initial_movement(self):
        self.login_as("GERENTE")
        conn = self.connect()
        categoria_id = conn.execute(
            "SELECT id FROM categorias WHERE nome = 'Hardware'"
        ).fetchone()["id"]
        fornecedor_id = conn.execute(
            "SELECT id FROM fornecedores WHERE cnpj = '00000000000101'"
        ).fetchone()["id"]
        conn.close()

        response = self.client.post(
            "/produtos/novo",
            data={
                "sku": "TESTE001",
                "nome": "Produto de Teste",
                "fabricante": "TechStock",
                "classificacao": "Hardware",
                "especificacao": "Unidade de teste",
                "modalidade_licenca": "",
                "preco_venda": "99.90",
                "quantidade_estoque": "3",
                "estoque_minimo": "1",
                "localizacao": "Prateleira T1",
                "categoria_id": str(categoria_id),
                "fornecedor_id": str(fornecedor_id),
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)

        conn = self.connect()
        try:
            produto = conn.execute(
                "SELECT id, quantidade_estoque FROM Produtos WHERE sku = 'TESTE001'"
            ).fetchone()
            movimento = conn.execute(
                """
                SELECT tipo_operacao, quantidade FROM Movimentacoes
                WHERE produto_id = ?
                """,
                (produto["id"],),
            ).fetchone()
            self.assertEqual(produto["quantidade_estoque"], 3)
            self.assertEqual(tuple(movimento), ("Entrada", 3))
        finally:
            conn.close()

    def test_product_form_rejects_duplicate_sku_and_nonpositive_price(self):
        self.login_as("GERENTE")
        conn = self.connect()
        categoria_id = conn.execute(
            "SELECT id FROM categorias WHERE nome = 'Hardware'"
        ).fetchone()["id"]
        fornecedor_id = conn.execute(
            "SELECT id FROM fornecedores WHERE cnpj = '00000000000101'"
        ).fetchone()["id"]
        conn.close()
        form = {
            "sku": "RAM001",
            "nome": "Produto inválido",
            "fabricante": "TechStock",
            "classificacao": "Hardware",
            "preco_venda": "99.90",
            "quantidade_estoque": "0",
            "estoque_minimo": "0",
            "categoria_id": str(categoria_id),
            "fornecedor_id": str(fornecedor_id),
        }

        duplicate = self.client.post("/produtos/novo", data=form)
        self.assertIn("SKU duplicado", duplicate.get_data(as_text=True))
        form["sku"] = "TESTE-PRICE"
        form["preco_venda"] = "0"
        invalid_price = self.client.post("/produtos/novo", data=form)
        self.assertIn("deve ser maior que zero", invalid_price.get_data(as_text=True))
        form["sku"] = "TESTE-SUBCENT"
        form["preco_venda"] = "0.001"
        sub_cent_price = self.client.post("/produtos/novo", data=form)
        self.assertIn("deve ser maior que zero", sub_cent_price.get_data(as_text=True))

    def test_operator_cannot_open_manager_routes(self):
        self.login_as("OPERADOR")
        response = self.client.get("/relatorios", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Acesso negado", response.get_data(as_text=True))
        response = self.client.get("/produtos/novo", follow_redirects=True)
        self.assertIn("Acesso negado", response.get_data(as_text=True))

    def test_manager_report_shows_completed_sales_and_revenue(self):
        self.login_as("GERENTE")
        product_id = self.product_id("RAM001")
        conn = self.connect()
        price = conn.execute(
            "SELECT preco_venda FROM Produtos WHERE id = ?", (product_id,)
        ).fetchone()["preco_venda"]
        conn.close()

        sale = self.client.post(
            "/pdv/finalizar",
            json={
                "cliente_nome": "Cliente de Teste",
                "cliente_documento": "12.345.678/0001-00",
                "forma_pagamento": "PIX",
                "itens": [{"produto_id": product_id, "quantidade": 1}],
            },
        )
        self.assertEqual(sale.status_code, 200)

        report = self.client.get("/relatorios")
        body = report.get_data(as_text=True)
        self.assertEqual(report.status_code, 200)
        self.assertIn("Faturamento concluído", body)
        self.assertIn("Vendas recentes", body)
        self.assertIn(f"R$ {price:.2f}", body)

    def test_inventory_movement_rolls_back_insufficient_outflow(self):
        self.login_as("GERENTE")
        product_id = self.product_id("RAM001")
        conn = self.connect()
        before_stock = conn.execute(
            "SELECT quantidade_estoque FROM Produtos WHERE id = ?", (product_id,)
        ).fetchone()[0]
        before_count = conn.execute(
            "SELECT COUNT(*) FROM Movimentacoes"
        ).fetchone()[0]
        conn.close()

        response = self.client.post(
            "/movimentacoes/nova",
            data={
                "produto_id": str(product_id),
                "tipo_operacao": "Saída",
                "quantidade": str(before_stock + 1),
                "observacao": "Teste de saldo insuficiente",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Saldo insuficiente", response.get_data(as_text=True))

        conn = self.connect()
        try:
            after_stock = conn.execute(
                "SELECT quantidade_estoque FROM Produtos WHERE id = ?",
                (product_id,),
            ).fetchone()[0]
            after_count = conn.execute(
                "SELECT COUNT(*) FROM Movimentacoes"
            ).fetchone()[0]
            self.assertEqual(after_stock, before_stock)
            self.assertEqual(after_count, before_count)
        finally:
            conn.close()

    def test_manager_can_register_entry_and_outflow(self):
        self.login_as("GERENTE")
        product_id = self.product_id("RAM001")
        for operation, quantity in (("Entrada", 2), ("Saída", 3)):
            response = self.client.post(
                "/movimentacoes/nova",
                data={
                    "produto_id": str(product_id),
                    "tipo_operacao": operation,
                    "quantidade": str(quantity),
                    "observacao": "Teste de movimentação",
                },
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)

        conn = self.connect()
        try:
            self.assertEqual(
                conn.execute(
                    "SELECT quantidade_estoque FROM Produtos WHERE id = ?",
                    (product_id,),
                ).fetchone()[0],
                14,
            )
            self.assertEqual(
                conn.execute(
                    """
                    SELECT COUNT(*) FROM Movimentacoes
                    WHERE produto_id = ? AND observacao = 'Teste de movimentação'
                    """,
                    (product_id,),
                ).fetchone()[0],
                2,
            )
        finally:
            conn.close()

    def test_manager_soft_deactivation_preserves_product_record(self):
        self.login_as("GERENTE")
        product_id = self.product_id("RAM001")
        response = self.client.post(
            f"/produtos/{product_id}/desativar", follow_redirects=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            "RAM001",
            self.client.get("/pdv").get_data(as_text=True),
        )

        conn = self.connect()
        try:
            produto = conn.execute(
                "SELECT ativo FROM Produtos WHERE id = ?", (product_id,)
            ).fetchone()
            self.assertEqual(produto["ativo"], 0)
        finally:
            conn.close()

    def test_checkout_is_atomic_and_aggregates_duplicate_products(self):
        self.login_as("OPERADOR")
        ram_id = self.product_id("RAM001")
        software_id = self.product_id("LIC001")
        response = self.client.post(
            "/pdv/finalizar",
            json={
                "cliente_nome": "Empresa de Teste",
                "cliente_documento": "12.345.678/0001-00",
                "forma_pagamento": "PIX",
                "itens": [
                    {"produto_id": ram_id, "quantidade": 2},
                    {"produto_id": ram_id, "quantidade": 2},
                    {"produto_id": software_id, "quantidade": 1},
                ],
            },
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        payload = response.get_json()

        conn = self.connect()
        try:
            venda = conn.execute(
                "SELECT * FROM Vendas WHERE id = ?", (payload["venda_id"],)
            ).fetchone()
            itens = conn.execute(
                "SELECT produto_id, quantidade_vendida FROM Itens_Venda WHERE venda_id = ? ORDER BY produto_id",
                (payload["venda_id"],),
            ).fetchall()
            ram_stock = conn.execute(
                "SELECT quantidade_estoque FROM Produtos WHERE id = ?", (ram_id,)
            ).fetchone()[0]
            sale_movements = conn.execute(
                """
                SELECT COUNT(*) FROM Movimentacoes
                WHERE observacao LIKE ?
                """,
                (f"%{venda['numero_pedido']}%",),
            ).fetchone()[0]
            self.assertEqual(len(itens), 2)
            self.assertEqual(
                {row["produto_id"]: row["quantidade_vendida"] for row in itens},
                {ram_id: 4, software_id: 1},
            )
            self.assertEqual(ram_stock, 11)
            self.assertEqual(sale_movements, 2)
            self.assertEqual(venda["valor_total"], 1450.0)
        finally:
            conn.close()

        receipt = self.client.get(payload["redirect_url"])
        receipt_body = receipt.get_data(as_text=True)
        self.assertEqual(receipt.status_code, 200)
        self.assertIn("Componente Físico", receipt_body)
        self.assertIn("Licença Digital Corporativa", receipt_body)

    def test_checkout_insufficient_stock_leaves_no_partial_records(self):
        self.login_as("OPERADOR")
        product_id = self.product_id("RAM001")
        conn = self.connect()
        before = {
            "stock": conn.execute(
                "SELECT quantidade_estoque FROM Produtos WHERE id = ?", (product_id,)
            ).fetchone()[0],
            "sales": conn.execute("SELECT COUNT(*) FROM Vendas").fetchone()[0],
            "items": conn.execute("SELECT COUNT(*) FROM Itens_Venda").fetchone()[0],
            "movements": conn.execute("SELECT COUNT(*) FROM Movimentacoes").fetchone()[0],
        }
        conn.close()

        response = self.client.post(
            "/pdv/finalizar",
            json={
                "cliente_nome": "Empresa de Teste",
                "cliente_documento": "12.345.678/0001-00",
                "forma_pagamento": "PIX",
                "itens": [{"produto_id": product_id, "quantidade": before["stock"] + 1}],
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Estoque insuficiente", response.get_json()["erro"])
        self.assertIn("Nenhuma alteração foi salva", response.get_json()["erro"])

        conn = self.connect()
        try:
            self.assertEqual(
                conn.execute(
                    "SELECT quantidade_estoque FROM Produtos WHERE id = ?",
                    (product_id,),
                ).fetchone()[0],
                before["stock"],
            )
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM Vendas").fetchone()[0], before["sales"])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM Itens_Venda").fetchone()[0], before["items"])
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM Movimentacoes").fetchone()[0],
                before["movements"],
            )
        finally:
            conn.close()

    def test_checkout_rejects_fractional_item_quantity(self):
        self.login_as("OPERADOR")
        response = self.client.post(
            "/pdv/finalizar",
            json={
                "cliente_nome": "Cliente de Teste",
                "cliente_documento": "12.345.678/0001-00",
                "forma_pagamento": "PIX",
                "itens": [
                    {"produto_id": self.product_id("RAM001"), "quantidade": 1.5}
                ],
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("número inteiro", response.get_json()["erro"])

    def test_manager_can_cancel_sale_and_restore_inventory(self):
        self.login_as("OPERADOR")
        product_id = self.product_id("RAM001")
        response = self.client.post(
            "/pdv/finalizar",
            json={
                "cliente_nome": "Empresa de Teste",
                "cliente_documento": "12.345.678/0001-00",
                "forma_pagamento": "PIX",
                "itens": [{"produto_id": product_id, "quantidade": 2}],
            },
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        venda_id = response.get_json()["venda_id"]

        self.client.get("/logout")
        self.login_as("GERENTE")
        response = self.client.post(f"/vendas/{venda_id}/cancelar", follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        conn = self.connect()
        try:
            self.assertEqual(
                conn.execute(
                    "SELECT status_venda FROM Vendas WHERE id = ?", (venda_id,)
                ).fetchone()[0],
                "CANCELADA",
            )
            self.assertEqual(
                conn.execute(
                    "SELECT quantidade_estoque FROM Produtos WHERE id = ?",
                    (product_id,),
                ).fetchone()[0],
                15,
            )
            self.assertEqual(
                conn.execute(
                    """
                    SELECT COUNT(*) FROM Movimentacoes
                    WHERE produto_id = ? AND tipo_operacao = 'Entrada'
                      AND observacao LIKE 'Estorno Cancelamento%'
                    """,
                    (product_id,),
                ).fetchone()[0],
                1,
            )
        finally:
            conn.close()

    def test_seed_v2_creates_demo_sale_and_audit_once(self):
        original_seed_db_path = seed_v2.DB_PATH
        seed_v2.DB_PATH = Path(app_module.DB_PATH)
        try:
            seed_v2.run_migration_and_seed()
            seed_v2.run_migration_and_seed()
        finally:
            seed_v2.DB_PATH = original_seed_db_path

        conn = self.connect()
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM Vendas").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM Itens_Venda").fetchone()[0], 2)
            self.assertEqual(
                conn.execute(
                    """
                    SELECT COUNT(*) FROM Movimentacoes
                    WHERE observacao LIKE 'Venda simulada PED-DEMO-%'
                    """
                ).fetchone()[0],
                2,
            )
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
