
import sqlite3
from pathlib import Path

# Encontrar o banco de dados
pasta = Path(__file__).resolve().parent
banco = pasta / "techstock.db"

# Abrir conexao
conexao = sqlite3.connect(banco)
conexao.execute("PRAGMA foreign_keys = ON")

try:
    # =====================================
    # 1. CADASTRAR 4 CATEGORIAS
    # =====================================

    categorias = [
        ("Hardware", "Pecas internas de computadores"),
        ("Software", "Programas e licencas"),
        ("Periféricos", "Acessorios de computadores"),
        ("Armazenamento", "Dispositivos para guardar dados")
    ]

    for nome, descricao in categorias:
        conexao.execute(
            """INSERT OR IGNORE INTO categorias
            (nome, descricao) VALUES (?, ?)""",
            (nome, descricao)
        )

    # =====================================
    # 2. CADASTRAR 3 FORNECEDORES
    # =====================================

    fornecedores = [
        ("Tech Distribuidora LTDA", "00000000000101",
         "(62) 3000-1000", "tech@exemplo.com"),

        ("Info Center Comercial LTDA", "00000000000102",
         "(62) 3000-2000", "info@exemplo.com"),

        ("Digital Solutions LTDA", "00000000000103",
         "(62) 3000-3000", "digital@exemplo.com")
    ]

    for fornecedor in fornecedores:
        conexao.execute(
            """INSERT OR IGNORE INTO fornecedores
            (razao_social, cnpj, telefone, email)
            VALUES (?, ?, ?, ?)""",
            fornecedor
        )

    # =====================================
    # 3. CADASTRAR 6 PRODUTOS
    # =====================================

    produtos = [
        (
            "RAM001", "Memoria RAM 16GB", "Kingston",
            "Hardware", "DDR4 16GB", None, 250.00,
            15, 5, "Prateleira A1", "Hardware",
            "00000000000101"
        ),
        (
            "SSD001", "SSD 480GB", "Kingston",
            "Hardware", "SSD SATA 480GB", None, 320.00,
            8, 5, "Prateleira A2", "Armazenamento",
            "00000000000101"
        ),
        (
            "CPU001", "Processador Ryzen 5", "AMD",
            "Hardware", "Ryzen 5 5600", None, 850.00,
            10, 3, "Prateleira A3", "Hardware",
            "00000000000102"
        ),
        (
            "MON001", "Monitor 24 polegadas", "LG",
            "Periférico", "Monitor Full HD", None, 780.00,
            4, 5, "Prateleira B1", "Periféricos",
            "00000000000102"
        ),
        (
            "LIC001", "Licenca Microsoft 365", "Microsoft",
            "Software", "Licenca de produtividade", "Anual",
            450.00, 20, 5, "Cofre Digital",
            "Software", "00000000000103"
        ),
        (
            "LIC002", "Licenca de Seguranca", "ESET",
            "Software", "Software de protecao", "Anual",
            180.00, 3, 5, "Cofre Digital",
            "Software", "00000000000103"
        )
    ]

    for produto in produtos:
        (
            sku, nome, fabricante, classificacao,
            especificacao, licenca, preco, estoque,
            minimo, localizacao, categoria_nome, cnpj
        ) = produto

        # Buscar o ID da categoria pelo nome
        categoria = conexao.execute(
            "SELECT id FROM categorias WHERE nome = ?",
            (categoria_nome,)
        ).fetchone()

        # Buscar o ID do fornecedor pelo CNPJ
        fornecedor = conexao.execute(
            "SELECT id FROM fornecedores WHERE cnpj = ?",
            (cnpj,)
        ).fetchone()

        # Cadastrar produto
        cursor = conexao.execute(
            """INSERT OR IGNORE INTO produtos
            (sku, nome, fabricante, classificacao,
             especificacao, modalidade_licenca,
             preco_venda, quantidade_estoque,
             estoque_minimo, localizacao,
             categoria_id, fornecedor_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sku, nome, fabricante, classificacao,
                especificacao, licenca, preco, estoque,
                minimo, localizacao, categoria[0],
                fornecedor[0]
            )
        )

        # Registrar a entrada inicial no historico
        if cursor.rowcount == 1 and estoque > 0:
            conexao.execute(
                """INSERT INTO movimentacoes
                (produto_id, tipo_operacao, quantidade, observacao)
                VALUES (
                    (SELECT id FROM produtos WHERE sku = ?),
                    'Entrada', ?, 'Estoque inicial de teste'
                )""",
                (sku, estoque)
            )

    conexao.commit()

    print("CADASTRO REALIZADO COM SUCESSO!")
    print("4 categorias cadastradas.")
    print("3 fornecedores cadastrados.")
    print("6 produtos cadastrados.")
    print("Entradas iniciais registradas no historico.")

except Exception as erro:
    conexao.rollback()
    print("Erro ao cadastrar:", erro)

finally:
    conexao.close()
