import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from werkzeug.security import generate_password_hash

PROJECT_DIR = Path(__file__).resolve().parent
DB_PATH = PROJECT_DIR / "techstock.db"

def run_migration_and_seed():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")

    migration_path = PROJECT_DIR / "migration_v2.sql"
    with migration_path.open("r", encoding="utf-8") as migration:
        conn.executescript(migration.read())

    try:
        conn.execute("BEGIN IMMEDIATE")
        usuarios = [
            (
                "Carlos Operador Balcão",
                "operador@techstore.com",
                generate_password_hash("operador123"),
                "OPERADOR",
                "ATIVO",
            ),
            (
                "Ana Gerente Comercial",
                "gerente@techstore.com",
                generate_password_hash("gerente123"),
                "GERENTE",
                "ATIVO",
            ),
        ]
        conn.executemany(
            """
            INSERT OR IGNORE INTO Usuarios
                (nome_completo, email, senha_hash, perfil_acesso, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            usuarios,
        )

        existe_venda = conn.execute("SELECT COUNT(*) FROM Vendas").fetchone()[0]
        if existe_venda == 0:
            produtos = []
            for classificacao in ("Hardware", "Software"):
                produto = conn.execute(
                    """
                    SELECT id, preco_venda
                    FROM Produtos
                    WHERE ativo = 1 AND quantidade_estoque > 0
                      AND classificacao = ?
                    ORDER BY id
                    LIMIT 1
                    """,
                    (classificacao,),
                ).fetchone()
                if produto:
                    produtos.append(produto)

            if len(produtos) < 2:
                produtos = conn.execute(
                    """
                    SELECT id, preco_venda
                    FROM Produtos
                    WHERE ativo = 1 AND quantidade_estoque > 0
                    ORDER BY id
                    LIMIT 2
                    """
                ).fetchall()

            if len(produtos) >= 2:
                numero_pedido = (
                    f"PED-DEMO-{datetime.now().strftime('%Y%m%d')}-"
                    f"{uuid.uuid4().hex[:6].upper()}"
                )
                valor_total = round(sum(float(p[1]) for p in produtos), 2)
                operador_id = conn.execute(
                    "SELECT id FROM Usuarios WHERE email = 'operador@techstore.com'"
                ).fetchone()[0]
                venda_id = conn.execute(
                    """
                    INSERT INTO Vendas (
                        numero_pedido, cliente_nome, cliente_documento,
                        forma_pagamento, valor_total, status_venda, usuario_id
                    )
                    VALUES (?, ?, ?, 'BOLETO_FATURADO', ?, 'CONCLUIDA', ?)
                    """,
                    (
                        numero_pedido,
                        "Empresa Alfa Ltda",
                        "12.345.678/0001-99",
                        valor_total,
                        operador_id,
                    ),
                ).lastrowid

                for produto_id, preco in produtos:
                    conn.execute(
                        """
                        INSERT INTO Itens_Venda (
                            venda_id, produto_id, quantidade_vendida,
                            preco_unitario_praticado, subtotal_item
                        )
                        VALUES (?, ?, 1, ?, ?)
                        """,
                        (venda_id, produto_id, preco, preco),
                    )
                    atualizado = conn.execute(
                        """
                        UPDATE Produtos
                        SET quantidade_estoque = quantidade_estoque - 1
                        WHERE id = ? AND quantidade_estoque > 0
                        """,
                        (produto_id,),
                    )
                    if atualizado.rowcount != 1:
                        raise RuntimeError("Saldo mudou durante a criação da venda simulada.")
                    conn.execute(
                        """
                        INSERT INTO Movimentacoes (
                            produto_id, tipo_operacao, quantidade, observacao
                        )
                        VALUES (?, 'Saída', 1, ?)
                        """,
                        (produto_id, f"Venda simulada {numero_pedido}"),
                    )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    print("Migration v2 e carga inicial aplicadas com sucesso!")

if __name__ == "__main__":
    run_migration_and_seed()