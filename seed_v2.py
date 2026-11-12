import sqlite3
from werkzeug.security import generate_password_hash

DB_PATH = "techstock.db"

def run_migration_and_seed():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")

    with open("migration_v2.sql", "r", encoding="utf-8") as f:
        conn.executescript(f.read())

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

    for u in usuarios:
        conn.execute(
            """
            INSERT OR IGNORE INTO Usuarios (nome_completo, email, senha_hash, perfil_acesso, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            u,
        )

    # Inserir venda simulada caso ainda não exista
    existe_venda = conn.execute("SELECT COUNT(*) FROM Vendas").fetchone()[0]
    produtos = conn.execute("SELECT id, preco_venda FROM Produtos WHERE estoque >= 2 LIMIT 2").fetchall()
    operador_id = conn.execute("SELECT id FROM Usuarios WHERE email = 'operador@techstore.com'").fetchone()[0]

    if existe_venda == 0 and len(produtos) >= 1:
        p1_id, p1_preco = produtos[0]
        subtotal = round(p1_preco * 1, 2)
        cur = conn.execute(
            """
            INSERT INTO Vendas (numero_pedido, cliente_nome, cliente_documento, forma_pagamento, valor_total, status_venda, usuario_id)
            VALUES (?, ?, ?, ?, ?, 'CONCLUIDA', ?)
            """,
            ("PED-2026-0001", "Empresa Alfa Ltda", "12.345.678/0001-99", "BOLETO_FATURADO", subtotal, operador_id),
        )
        venda_id = cur.lastrowid
        conn.execute(
            """
            INSERT INTO Itens_Venda (venda_id, produto_id, quantidade_vendida, preco_unitario_praticado, subtotal_item)
            VALUES (?, ?, ?, ?, ?)
            """,
            (venda_id, p1_id, 1, p1_preco, subtotal),
        )

    conn.commit()
    conn.close()
    print("Migration v2 e carga inicial aplicadas com sucesso!")

if __name__ == "__main__":
    run_migration_and_seed()