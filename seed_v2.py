import sqlite3
from pathlib import Path
from werkzeug.security import generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
BANCO = BASE_DIR / "techstock.db"


def executar_migracao_e_carga():
    conexao = sqlite3.connect(BANCO)
    conexao.execute("PRAGMA foreign_keys = ON;")

    db_sql = BASE_DIR / "database.sql"
    if db_sql.exists():
        conexao.executescript(db_sql.read_text(encoding="utf-8"))

    mig_sql = BASE_DIR / "migration_v2.sql"
    conexao.executescript(mig_sql.read_text(encoding="utf-8"))

    if conexao.execute("SELECT COUNT(*) FROM produtos").fetchone()[0] == 0:
        conexao.execute("INSERT OR IGNORE INTO categorias (id, nome, descricao) VALUES (1, 'Hardware', 'Componentes'), (2, 'Software', 'Licenças')")
        conexao.execute("INSERT OR IGNORE INTO fornecedores (id, razao_social, cnpj, telefone, email) VALUES (1, 'Distribuidora Tech Brasil', '11.222.333/0001-44', '11999990000', 'contato@techbrasil.com')")
        conexao.execute("""
            INSERT INTO produtos (sku, nome, fabricante, classificacao, especificacao, modalidade_licenca, preco_venda, quantidade_estoque, estoque_minimo, localizacao, categoria_id, fornecedor_id)
            VALUES
            ('RAM-DDR4-16G', 'Memória RAM 16GB DDR4 3200MHz', 'Kingston', 'Hardware', 'DDR4 3200MHz', '', 289.90, 10, 3, 'A1', 1, 1),
            ('WIN11-PRO-ESD', 'Licença Windows 11 Pro Corporativo', 'Microsoft', 'Software', 'Chave ESD Vitalícia', 'Vitalícia', 899.00, 5, 2, 'DIGITAL', 2, 1)
        """)

    usuarios = [
        ("Carlos Mendes (Operador Balcão)", "operador@techstore.com", generate_password_hash("operador123"), "OPERADOR", "ATIVO"),
        ("Ana Paula Silva (Gerente Comercial)", "gerente@techstore.com", generate_password_hash("gerente123"), "GERENTE", "ATIVO"),
    ]
    for u in usuarios:
        conexao.execute(
            "INSERT OR IGNORE INTO Usuarios (nome_completo, email, senha_hash, perfil_acesso, status) VALUES (?, ?, ?, ?, ?)",
            u,
        )

    qtd_vendas = conexao.execute("SELECT COUNT(*) FROM Vendas").fetchone()[0]
    produtos = conexao.execute("SELECT id, preco_venda FROM produtos WHERE ativo = 1 AND quantidade_estoque >= 2 LIMIT 1").fetchall()
    operador = conexao.execute("SELECT id FROM Usuarios WHERE email = 'operador@techstore.com'").fetchone()

    if qtd_vendas == 0 and operador and produtos:
        p1_id, p1_preco = produtos[0]
        sub1 = round(float(p1_preco), 2)
        cur = conexao.execute(
            """
            INSERT INTO Vendas (numero_pedido, data_hora, cliente_nome, cliente_documento, forma_pagamento, valor_total, status_venda, usuario_id)
            VALUES ('PED-20261112-DEMO01', datetime('now', 'localtime'), 'Construtora Horizonte S.A.', '12.345.678/0001-90', 'BOLETO_FATURADO', ?, 'CONCLUIDA', ?)
            """,
            (sub1, operador[0]),
        )
        conexao.execute(
            "INSERT INTO Itens_Venda (venda_id, produto_id, quantidade_vendida, preco_unitario_praticado, subtotal_item) VALUES (?, ?, 1, ?, ?)",
            (cur.lastrowid, p1_id, sub1, sub1),
        )

    conexao.commit()
    cadastrados = conexao.execute("SELECT email, perfil_acesso FROM Usuarios").fetchall()
    conexao.close()
    print("OK! Usuarios ativos no banco:", cadastrados)


if __name__ == "__main__":
    executar_migracao_e_carga()