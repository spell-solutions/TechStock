import hashlib
import hmac
import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
from pathlib import Path
from flask import Flask, abort, flash, get_flashed_messages, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "TECHSTOCK_SECRET_KEY", "techstock-local-development-key"
)
app.permanent_session_lifetime = timedelta(days=7)
DB_PATH = str(Path(__file__).resolve().with_name("techstock.db"))
SELLER_CNPJ = os.environ.get("TECHSTOCK_CNPJ", "00.000.000/0000-00")


def get_db(autocommit_mode=False):
    # isolation_level=None permite controle explícito de BEGIN TRANSACTION / COMMIT / ROLLBACK
    conn = sqlite3.connect(DB_PATH, isolation_level=None if autocommit_mode else "")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


# --- CONTROLE DE ACESSO (RBAC) ---
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Faça login para acessar o sistema.", "erro")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def gerente_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Faça login para continuar.", "erro")
            return redirect(url_for("login"))
        if session.get("perfil_acesso") != "GERENTE":
            flash("Acesso negado: esta operação exige perfil GERENTE.", "erro")
            return redirect(url_for("inicio"))
        return f(*args, **kwargs)
    return decorated


def parse_integer(value, label, minimum=0):
    if isinstance(value, bool):
        raise ValueError(f"{label} deve ser um número inteiro válido.")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{label} deve ser um número inteiro válido.")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} deve ser um número inteiro válido.") from None
    if parsed < minimum:
        raise ValueError(f"{label} deve ser maior ou igual a {minimum}.")
    return parsed


def parse_price(value):
    try:
        price = Decimal(str(value))
        price = price.quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Informe um preço válido.") from None
    if not price.is_finite() or price <= 0:
        raise ValueError("O preço de venda deve ser maior que zero.")
    return float(price)


def valid_cpf(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:\d{11}|\d{3}\.\d{3}\.\d{3}-\d{2})", value.strip()
    ):
        return False
    digits = re.sub(r"\D", "", value)
    if len(set(digits)) == 1:
        return False
    for length in (9, 10):
        total = sum(int(digits[index]) * (length + 1 - index) for index in range(length))
        check_digit = (total * 10) % 11
        if check_digit == 10:
            check_digit = 0
        if check_digit != int(digits[length]):
            return False
    return True


def valid_customer_document(value):
    if not isinstance(value, str):
        return False
    document = value.strip()
    if re.fullmatch(r"\d{11}", document) or re.fullmatch(
        r"\d{3}\.\d{3}\.\d{3}-\d{2}", document
    ):
        return valid_cpf(document)
    return bool(
        re.fullmatch(r"\d{14}", document)
        or re.fullmatch(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", document)
    )


def product_form_choices(conn):
    categorias = conn.execute("SELECT id, nome FROM categorias ORDER BY nome").fetchall()
    fornecedores = conn.execute(
        "SELECT id, razao_social FROM fornecedores ORDER BY razao_social"
    ).fetchall()
    return categorias, fornecedores


def product_form_values(form, include_stock=False):
    sku = form.get("sku", "").strip()
    nome = form.get("nome", "").strip()
    fabricante = form.get("fabricante", "").strip()
    classificacao = form.get("classificacao", "").strip()
    if not sku or not nome or not fabricante:
        raise ValueError("Preencha SKU, nome e fabricante.")
    if classificacao not in ("Hardware", "Software", "Periférico"):
        raise ValueError("Selecione uma classificação válida.")

    categoria_id = parse_integer(form.get("categoria_id"), "Categoria", 1)
    fornecedor_id = parse_integer(form.get("fornecedor_id"), "Fornecedor", 1)
    values = (
        sku,
        nome,
        fabricante,
        classificacao,
        form.get("especificacao", "").strip(),
        form.get("modalidade_licenca", "").strip(),
        parse_price(form.get("preco_venda")),
        parse_integer(form.get("estoque_minimo", 0), "Estoque mínimo"),
        form.get("localizacao", "").strip(),
        categoria_id,
        fornecedor_id,
    )
    if include_stock:
        return values, parse_integer(form.get("quantidade_estoque", 0), "Estoque")
    return values


# --- AUTENTICAÇÃO ---
@app.route("/")
def home():
    endpoint = "inicio" if session.get("usuario_id") else "login"
    return redirect(url_for(endpoint))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")

        if not email or not senha:
            flash("Preencha o e-mail e a senha.", "erro")
        else:
            conn = get_db()
            user = conn.execute(
                "SELECT * FROM Usuarios WHERE email = ? AND status = 'ATIVO'", (email,)
            ).fetchone()
            conn.close()

            if user and check_password_hash(user["senha_hash"], senha):
                session.permanent = True
                session["usuario_id"] = user["id"]
                session["usuario_nome"] = user["nome_completo"]
                session["perfil_acesso"] = user["perfil_acesso"]
                get_flashed_messages()
                return redirect(url_for("inicio"))
            else:
                flash("Credenciais inválidas ou usuário inativo.", "erro")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Sessão encerrada com segurança.", "sucesso")
    return redirect(url_for("login"))


# --- PAINEL DE INVENTÁRIO ---
@app.route("/inicio")
@login_required
def inicio():
    busca = request.args.get("busca", "").strip()
    filtros = ["p.ativo = 1"]
    parametros = []
    if busca:
        filtros.append("(p.sku LIKE ? OR p.nome LIKE ? OR p.fabricante LIKE ?)")
        termo = f"%{busca}%"
        parametros.extend((termo, termo, termo))

    conn = get_db()
    try:
        produtos = conn.execute(
            f"""
            SELECT p.*, c.nome AS categoria, f.razao_social AS fornecedor
            FROM Produtos p
            INNER JOIN categorias c ON c.id = p.categoria_id
            INNER JOIN fornecedores f ON f.id = p.fornecedor_id
            WHERE {' AND '.join(filtros)}
            ORDER BY p.nome
            """,
            parametros,
        ).fetchall()
        total_produtos = conn.execute(
            "SELECT COUNT(*) FROM Produtos WHERE ativo = 1"
        ).fetchone()[0]
        total_unidades = conn.execute(
            "SELECT COALESCE(SUM(quantidade_estoque), 0) FROM Produtos WHERE ativo = 1"
        ).fetchone()[0]
        total_categorias = conn.execute(
            "SELECT COUNT(*) FROM categorias"
        ).fetchone()[0]
        produtos_baixos = conn.execute(
            """
            SELECT nome, quantidade_estoque, estoque_minimo
            FROM Produtos
            WHERE ativo = 1 AND quantidade_estoque <= estoque_minimo
            ORDER BY quantidade_estoque, nome
            """
        ).fetchall()
        vendas_diarias = []
        if session.get("perfil_acesso") == "GERENTE":
            desde = (datetime.now().date() - timedelta(days=13)).isoformat()
            totais_por_dia = {
                row["dia"]: row["total"]
                for row in conn.execute(
                    """
                    SELECT date(data_hora) AS dia, SUM(valor_total) AS total
                    FROM Vendas
                    WHERE status_venda = 'CONCLUIDA'
                      AND date(data_hora) >= ?
                    GROUP BY date(data_hora)
                    """,
                    (desde,),
                ).fetchall()
            }
            dias = [
                (datetime.now().date() - timedelta(days=offset))
                for offset in range(13, -1, -1)
            ]
            maior_total = max(
                (float(totais_por_dia.get(dia.isoformat(), 0) or 0) for dia in dias),
                default=0,
            )
            vendas_diarias = [
                {
                    "data": dia.strftime("%d/%m"),
                    "total": float(totais_por_dia.get(dia.isoformat(), 0) or 0),
                    "altura": (
                        max(4, round(float(totais_por_dia.get(dia.isoformat(), 0) or 0) / maior_total * 100))
                        if maior_total
                        else 0
                    ),
                }
                for dia in dias
            ]
    finally:
        conn.close()

    produtos_por_categoria = {}
    for produto in produtos:
        produtos_por_categoria.setdefault(produto["categoria"], []).append(produto)

    ordem_categorias = {
        "Hardware": 0,
        "Software": 1,
        "Periféricos": 2,
        "Armazenamento": 3,
    }
    produtos_por_categoria = [
        {"nome": categoria, "produtos": itens}
        for categoria, itens in sorted(
            produtos_por_categoria.items(),
            key=lambda item: (
                ordem_categorias.get(item[0], len(ordem_categorias)),
                item[0].casefold(),
            ),
        )
    ]

    return render_template(
        "index.html",
        produtos=produtos,
        produtos_por_categoria=produtos_por_categoria,
        busca=busca,
        total_produtos=total_produtos,
        total_unidades=total_unidades,
        total_categorias=total_categorias,
        produtos_baixos=produtos_baixos,
        vendas_diarias=vendas_diarias,
    )


@app.route("/usuarios/novo", methods=["GET", "POST"])
@gerente_required
def novo_usuario():
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        senha_confirmacao = request.form.get("senha_confirmacao", "")
        if not nome or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            flash("Informe um nome e um e-mail válido.", "erro")
        elif len(senha) < 8:
            flash("A senha deve ter pelo menos 8 caracteres.", "erro")
        elif senha != senha_confirmacao:
            flash("As senhas não conferem.", "erro")
        else:
            conn = get_db()
            try:
                conn.execute(
                    """
                    INSERT INTO Usuarios
                        (nome_completo, email, senha_hash, perfil_acesso, status)
                    VALUES (?, ?, ?, 'OPERADOR', 'ATIVO')
                    """,
                    (nome, email, generate_password_hash(senha)),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                flash("Já existe um usuário com esse e-mail.", "erro")
            else:
                flash(f"Operador {nome} cadastrado com sucesso.", "sucesso")
                return redirect(url_for("inicio"))
            finally:
                conn.close()
    return render_template("usuario_form.html")


@app.route("/produtos/novo", methods=["GET", "POST"])
@gerente_required
def novo_produto():
    conn = get_db()
    try:
        categorias, fornecedores = product_form_choices(conn)
        if request.method == "POST":
            values, estoque = product_form_values(request.form, include_stock=True)
            conn.execute("BEGIN IMMEDIATE")
            for table, record_id in (
                ("categorias", values[9]),
                ("fornecedores", values[10]),
            ):
                if not conn.execute(
                    f"SELECT 1 FROM {table} WHERE id = ?", (record_id,)
                ).fetchone():
                    raise ValueError("A categoria ou o fornecedor selecionado não existe.")

            cursor = conn.execute(
                """
                INSERT INTO Produtos (
                    sku, nome, fabricante, classificacao, especificacao,
                    modalidade_licenca, preco_venda, quantidade_estoque,
                    estoque_minimo, localizacao, categoria_id, fornecedor_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    *values[:7],
                    estoque,
                    *values[7:],
                ),
            )
            if estoque:
                conn.execute(
                    """
                    INSERT INTO Movimentacoes
                        (produto_id, tipo_operacao, quantidade, observacao)
                    VALUES (?, 'Entrada', ?, 'Estoque inicial do produto')
                    """,
                    (cursor.lastrowid, estoque),
                )
            conn.commit()
            flash("Produto cadastrado com sucesso.", "sucesso")
            return redirect(url_for("inicio"))
    except ValueError as error:
        if conn.in_transaction:
            conn.rollback()
        flash(str(error), "erro")
    except sqlite3.IntegrityError as error:
        if conn.in_transaction:
            conn.rollback()
        app.logger.info("Cadastro de produto rejeitado: %s", error)
        flash("SKU duplicado ou associação inválida. Confira os dados e tente novamente.", "erro")
    except sqlite3.Error:
        if conn.in_transaction:
            conn.rollback()
        app.logger.exception("Falha ao cadastrar produto")
        flash("Não foi possível salvar o produto. Nenhuma alteração foi aplicada.", "erro")
    finally:
        conn.close()

    if request.method == "POST":
        conn = get_db()
        try:
            categorias, fornecedores = product_form_choices(conn)
        finally:
            conn.close()
    return render_template(
        "produto_form.html", categorias=categorias, fornecedores=fornecedores
    )


@app.route("/produtos/<int:produto_id>/editar", methods=["GET", "POST"])
@gerente_required
def editar_produto(produto_id):
    conn = get_db()
    try:
        produto = conn.execute(
            "SELECT * FROM Produtos WHERE id = ? AND ativo = 1", (produto_id,)
        ).fetchone()
        if not produto:
            abort(404)
        categorias, fornecedores = product_form_choices(conn)
        if request.method == "POST":
            values = product_form_values(request.form)
            conn.execute("BEGIN IMMEDIATE")
            for table, record_id in (
                ("categorias", values[9]),
                ("fornecedores", values[10]),
            ):
                if not conn.execute(
                    f"SELECT 1 FROM {table} WHERE id = ?", (record_id,)
                ).fetchone():
                    raise ValueError("A categoria ou o fornecedor selecionado não existe.")

            conn.execute(
                """
                UPDATE Produtos
                SET sku = ?, nome = ?, fabricante = ?, classificacao = ?,
                    especificacao = ?, modalidade_licenca = ?, preco_venda = ?,
                    estoque_minimo = ?, localizacao = ?, categoria_id = ?,
                    fornecedor_id = ?
                WHERE id = ?
                """,
                (*values, produto_id),
            )
            conn.commit()
            flash("Produto atualizado com sucesso.", "sucesso")
            return redirect(url_for("inicio"))
    except ValueError as error:
        if conn.in_transaction:
            conn.rollback()
        flash(str(error), "erro")
    except sqlite3.IntegrityError as error:
        if conn.in_transaction:
            conn.rollback()
        app.logger.info("Edição de produto rejeitada: %s", error)
        flash("SKU duplicado ou associação inválida. Confira os dados e tente novamente.", "erro")
    except sqlite3.Error:
        if conn.in_transaction:
            conn.rollback()
        app.logger.exception("Falha ao editar produto %s", produto_id)
        flash("Não foi possível atualizar o produto. Nenhuma alteração foi aplicada.", "erro")
    finally:
        conn.close()

    conn = get_db()
    try:
        produto = conn.execute(
            "SELECT * FROM Produtos WHERE id = ? AND ativo = 1", (produto_id,)
        ).fetchone()
        categorias, fornecedores = product_form_choices(conn)
    finally:
        conn.close()
    if not produto:
        abort(404)
    return render_template(
        "editar_produto.html",
        produto=produto,
        categorias=categorias,
        fornecedores=fornecedores,
    )


@app.route("/produtos/<int:produto_id>/desativar", methods=["POST"])
@gerente_required
def desativar_produto(produto_id):
    conn = get_db()
    try:
        cursor = conn.execute(
            "UPDATE Produtos SET ativo = 0 WHERE id = ? AND ativo = 1",
            (produto_id,),
        )
        if cursor.rowcount == 0:
            flash("Produto não encontrado ou já desativado.", "erro")
        else:
            flash("Produto desativado. O histórico de vendas foi preservado.", "sucesso")
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("inicio"))


# --- MOVIMENTAÇÕES DO ESTOQUE ---
@app.route("/movimentacoes")
@login_required
def movimentacoes():
    conn = get_db()
    try:
        registros = conn.execute(
            """
            SELECT m.id, p.sku, p.nome AS produto, m.tipo_operacao,
                   m.quantidade, m.data_hora, m.observacao
            FROM Movimentacoes m
            INNER JOIN Produtos p ON p.id = m.produto_id
            ORDER BY m.id DESC
            """
        ).fetchall()
    finally:
        conn.close()
    return render_template("movimentacoes.html", registros=registros)


@app.route("/movimentacoes/nova", methods=["GET", "POST"])
@gerente_required
def nova_movimentacao():
    conn = get_db()
    try:
        produtos = conn.execute(
            """
            SELECT id, sku, nome, quantidade_estoque
            FROM Produtos WHERE ativo = 1 ORDER BY nome
            """
        ).fetchall()
        if request.method == "POST":
            produto_id = parse_integer(request.form.get("produto_id"), "Produto", 1)
            quantidade = parse_integer(
                request.form.get("quantidade"), "Quantidade", 1
            )
            tipo = request.form.get("tipo_operacao", "").strip()
            observacao = request.form.get("observacao", "").strip()
            if tipo not in ("Entrada", "Saída"):
                raise ValueError("Selecione uma operação válida.")

            conn.execute("BEGIN IMMEDIATE")
            produto = conn.execute(
                """
                SELECT quantidade_estoque FROM Produtos
                WHERE id = ? AND ativo = 1
                """,
                (produto_id,),
            ).fetchone()
            if not produto:
                raise ValueError("O produto selecionado não existe ou está desativado.")

            saldo = produto["quantidade_estoque"]
            if tipo == "Saída" and quantidade > saldo:
                raise ValueError(
                    f"Saldo insuficiente. Disponível: {saldo}; solicitado: {quantidade}."
                )
            novo_saldo = saldo + quantidade if tipo == "Entrada" else saldo - quantidade
            conn.execute(
                "UPDATE Produtos SET quantidade_estoque = ? WHERE id = ?",
                (novo_saldo, produto_id),
            )
            conn.execute(
                """
                INSERT INTO Movimentacoes
                    (produto_id, tipo_operacao, quantidade, observacao)
                VALUES (?, ?, ?, ?)
                """,
                (produto_id, tipo, quantidade, observacao or None),
            )
            conn.commit()
            flash("Movimentação registrada e saldo atualizado.", "sucesso")
            return redirect(url_for("movimentacoes"))
    except ValueError as error:
        if conn.in_transaction:
            conn.rollback()
        flash(str(error), "erro")
    except sqlite3.IntegrityError as error:
        if conn.in_transaction:
            conn.rollback()
        app.logger.exception("Falha de integridade ao registrar movimentação: %s", error)
        flash("Não foi possível registrar a movimentação. Confira o produto e tente novamente.", "erro")
    except sqlite3.Error:
        if conn.in_transaction:
            conn.rollback()
        app.logger.exception("Falha ao registrar movimentação")
        flash("Não foi possível registrar a movimentação. O saldo não foi alterado.", "erro")
    finally:
        conn.close()

    if request.method == "POST":
        conn = get_db()
        try:
            produtos = conn.execute(
                """
                SELECT id, sku, nome, quantidade_estoque
                FROM Produtos WHERE ativo = 1 ORDER BY nome
                """
            ).fetchall()
        finally:
            conn.close()
    return render_template("movimentacao_form.html", produtos=produtos)


@app.route("/relatorios")
@gerente_required
def relatorios():
    conn = get_db()
    try:
        total_produtos, total_unidades, produtos_baixos = conn.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(quantidade_estoque), 0),
                   COALESCE(SUM(quantidade_estoque <= estoque_minimo), 0)
            FROM Produtos WHERE ativo = 1
            """
        ).fetchone()
        total_entradas = conn.execute(
            "SELECT COALESCE(SUM(quantidade), 0) FROM Movimentacoes WHERE tipo_operacao = 'Entrada'"
        ).fetchone()[0]
        total_saidas = conn.execute(
            "SELECT COALESCE(SUM(quantidade), 0) FROM Movimentacoes WHERE tipo_operacao = 'Saída'"
        ).fetchone()[0]
        total_vendas, faturamento_total = conn.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(valor_total), 0)
            FROM Vendas WHERE status_venda = 'CONCLUIDA'
            """
        ).fetchone()
        historico = conn.execute(
            """
            SELECT p.sku, p.nome AS produto, m.tipo_operacao,
                   m.quantidade, m.data_hora
            FROM Movimentacoes m
            INNER JOIN Produtos p ON p.id = m.produto_id
            ORDER BY m.id DESC LIMIT 20
            """
        ).fetchall()
        vendas_recentes = conn.execute(
            """
            SELECT id, numero_pedido, data_hora, cliente_nome,
                   valor_total, status_venda
            FROM Vendas
            ORDER BY id DESC LIMIT 10
            """
        ).fetchall()
    finally:
        conn.close()
    return render_template(
        "relatorios.html",
        total_produtos=total_produtos,
        total_unidades=total_unidades,
        produtos_baixos=produtos_baixos,
        total_entradas=total_entradas,
        total_saidas=total_saidas,
        total_vendas=total_vendas,
        faturamento_total=faturamento_total,
        historico=historico,
        vendas_recentes=vendas_recentes,
    )


# --- FRENTE DE CAIXA / PDV MULTI-ITENS ---
@app.route("/pdv", methods=["GET"])
@login_required
def pdv():
    conn = get_db()
    try:
        produtos = conn.execute(
            """
            SELECT id, sku, nome, classificacao, preco_venda,
                   quantidade_estoque, modalidade_licenca
            FROM Produtos
            WHERE ativo = 1
            ORDER BY nome ASC
            """
        ).fetchall()
    finally:
        conn.close()
    return render_template("pdv.html", produtos=produtos)


# --- CHECKOUT TRANSACIONAL COM GARANTIA ACID (REQ-04) ---
@app.route("/pdv/finalizar", methods=["POST"])
@login_required
def finalizar_venda():
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        return jsonify({"sucesso": False, "erro": "Payload inválido."}), 400

    cliente_nome = dados.get("cliente_nome")
    cliente_documento = dados.get("cliente_documento")
    forma_pagamento = dados.get("forma_pagamento")
    if not all(
        isinstance(value, str)
        for value in (cliente_nome, cliente_documento, forma_pagamento)
    ):
        return jsonify({"sucesso": False, "erro": "Preencha os dados do cliente e o pagamento."}), 400
    cliente_nome = cliente_nome.strip()
    cliente_documento = cliente_documento.strip()
    forma_pagamento = forma_pagamento.strip()
    itens = dados.get("itens", [])

    if not cliente_nome or not cliente_documento or forma_pagamento not in ("PIX", "CARTAO_CREDITO", "BOLETO_FATURADO"):
        return jsonify({"sucesso": False, "erro": "Preencha nome do cliente, CPF/CNPJ e forma de pagamento válida."}), 400
    if not valid_customer_document(cliente_documento):
        return jsonify({"sucesso": False, "erro": "Informe um CPF válido ou CNPJ com 14 dígitos, sem letras."}), 400

    if not isinstance(itens, list) or not itens:
        return jsonify({"sucesso": False, "erro": "O carrinho está vazio. Adicione ao menos um item."}), 400

    quantidades = {}
    try:
        for item in itens:
            if not isinstance(item, dict):
                raise ValueError("Há um item inválido no carrinho.")
            produto_id = parse_integer(item.get("produto_id"), "Produto", 1)
            quantidade = parse_integer(item.get("quantidade"), "Quantidade", 1)
            quantidades[produto_id] = quantidades.get(produto_id, 0) + quantidade
    except ValueError as error:
        return jsonify({"sucesso": False, "erro": str(error)}), 400

    conn = get_db(autocommit_mode=True)
    try:
        conn.execute("BEGIN IMMEDIATE")
        itens_validados = []
        valor_total = Decimal("0.00")
        for produto_id, quantidade in quantidades.items():
            prod = conn.execute(
                """
                SELECT id, nome, quantidade_estoque, preco_venda
                FROM Produtos WHERE id = ? AND ativo = 1
                """,
                (produto_id,),
            ).fetchone()
            if not prod:
                raise ValueError("Um produto do carrinho não existe ou está desativado.")
            if prod["quantidade_estoque"] < quantidade:
                raise ValueError(
                    f"Estoque insuficiente para '{prod['nome']}'. "
                    f"Disponível: {prod['quantidade_estoque']} un. | "
                    f"Solicitado: {quantidade} un. Nenhuma alteração foi salva."
                )

            preco_praticado = Decimal(str(prod["preco_venda"])).quantize(
                Decimal("0.01")
            )
            subtotal = (preco_praticado * quantidade).quantize(Decimal("0.01"))
            valor_total += subtotal
            itens_validados.append({
                "produto_id": prod["id"],
                "nome": prod["nome"],
                "quantidade": quantidade,
                "preco_unitario": float(preco_praticado),
                "subtotal": float(subtotal),
            })

        numero_pedido = f"PED-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        cursor = conn.execute(
            """
            INSERT INTO Vendas
                (numero_pedido, data_hora, cliente_nome, cliente_documento,
                 forma_pagamento, valor_total, status_venda, status_pagamento, usuario_id)
            VALUES (?, ?, ?, ?, ?, ?, 'CONCLUIDA', ?, ?)
            """,
            (
                numero_pedido,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                cliente_nome,
                cliente_documento,
                forma_pagamento,
                float(valor_total),
                "PENDENTE" if forma_pagamento == "BOLETO_FATURADO" else "PAGO",
                session["usuario_id"],
            ),
        )
        venda_id = cursor.lastrowid

        for iv in itens_validados:
            conn.execute(
                """
                INSERT INTO Itens_Venda (venda_id, produto_id, quantidade_vendida, preco_unitario_praticado, subtotal_item)
                VALUES (?, ?, ?, ?, ?)
                """,
                (venda_id, iv["produto_id"], iv["quantidade"], iv["preco_unitario"], iv["subtotal"]),
            )
            atualizacao = conn.execute(
                """
                UPDATE Produtos
                SET quantidade_estoque = quantidade_estoque - ?
                WHERE id = ? AND ativo = 1 AND quantidade_estoque >= ?
                """,
                (iv["quantidade"], iv["produto_id"], iv["quantidade"]),
            )
            if atualizacao.rowcount != 1:
                raise ValueError(
                    f"Estoque insuficiente para '{iv['nome']}'. Nenhuma alteração foi salva."
                )
            conn.execute(
                """
                INSERT INTO Movimentacoes
                    (produto_id, tipo_operacao, quantidade, observacao)
                VALUES (?, 'Saída', ?, ?)
                """,
                (iv["produto_id"], iv["quantidade"], f"Venda PDV {numero_pedido} - Operador #{session['usuario_id']}"),
            )

        conn.execute("COMMIT")
        return jsonify({
            "sucesso": True,
            "venda_id": venda_id,
            "redirect_url": url_for("recibo_venda", venda_id=venda_id),
        })
    except ValueError as error:
        if conn.in_transaction:
            conn.rollback()
        return jsonify({"sucesso": False, "erro": str(error)}), 400
    except sqlite3.IntegrityError:
        if conn.in_transaction:
            conn.rollback()
        app.logger.exception("Falha de integridade no checkout")
        return jsonify({
            "sucesso": False,
            "erro": "A venda foi cancelada por uma regra de integridade; nenhuma alteração foi salva.",
        }), 400
    except sqlite3.Error:
        if conn.in_transaction:
            conn.rollback()
        app.logger.exception("Falha de banco de dados no checkout")
        return jsonify({
            "sucesso": False,
            "erro": "Não foi possível concluir a venda; nenhuma alteração foi salva.",
        }), 500
    finally:
        conn.close()


# --- RECIBO FORMAL DE FATURAMENTO (REQ-05) ---
@app.route("/vendas/<int:venda_id>/recibo")
@login_required
def recibo_venda(venda_id):
    conn = get_db()
    venda = conn.execute(
        """
        SELECT v.*, u.nome_completo AS operador_nome, u.email AS operador_email
        FROM Vendas v
        JOIN Usuarios u ON v.usuario_id = u.id
        WHERE v.id = ?
        """,
        (venda_id,),
    ).fetchone()

    if not venda:
        conn.close()
        flash("Venda não encontrada.", "erro")
        return redirect(url_for("pdv"))
    if (
        session.get("perfil_acesso") != "GERENTE"
        and venda["usuario_id"] != session.get("usuario_id")
    ):
        conn.close()
        abort(403)

    itens = conn.execute(
        """
        SELECT iv.*, p.nome AS produto_nome, p.classificacao
        FROM Itens_Venda iv
        JOIN Produtos p ON iv.produto_id = p.id
        WHERE iv.venda_id = ?
        """,
        (venda_id,),
    ).fetchall()
    conn.close()

    # Gera chave de autenticidade SHA-256 resumida para o comprovante corporativo
    raw_sig = f"{venda['numero_pedido']}|{venda['cliente_documento']}|{venda['valor_total']}|{venda['data_hora']}"
    chave_autenticidade = hmac.new(
        app.config["SECRET_KEY"].encode(),
        raw_sig.encode(),
        hashlib.sha256,
    ).hexdigest()[:24].upper()

    return render_template(
        "recibo.html",
        venda=venda,
        itens=itens,
        chave_autenticidade=chave_autenticidade,
        seller_cnpj=SELLER_CNPJ,
    )


# --- HISTÓRICO E CANCELAMENTO DE VENDA (APENAS GERENTE) ---
@app.route("/vendas")
@gerente_required
def listar_vendas():
    conn = get_db()
    vendas = conn.execute(
        """
        SELECT v.*, u.nome_completo AS operador_nome
        FROM Vendas v
        JOIN Usuarios u ON v.usuario_id = u.id
        ORDER BY v.id DESC
        """
    ).fetchall()
    conn.close()
    return render_template("vendas.html", vendas=vendas)


@app.route("/vendas/<int:venda_id>/editar", methods=["GET", "POST"])
@gerente_required
def editar_venda(venda_id):
    if request.method == "GET":
        conn = get_db()
        try:
            venda = conn.execute(
                "SELECT * FROM Vendas WHERE id = ?", (venda_id,)
            ).fetchone()
            if not venda:
                abort(404)
            if venda["status_pagamento"] != "PENDENTE" or venda["status_venda"] != "CONCLUIDA":
                flash("Somente vendas ainda não pagas podem ser editadas.", "erro")
                return redirect(url_for("listar_vendas"))
            produtos = conn.execute(
                """
                SELECT id, nome, preco_venda, quantidade_estoque
                FROM Produtos WHERE ativo = 1 ORDER BY nome
                """
            ).fetchall()
            itens = conn.execute(
                """
                SELECT produto_id, quantidade_vendida
                FROM Itens_Venda WHERE venda_id = ?
                """,
                (venda_id,),
            ).fetchall()
        finally:
            conn.close()
        return render_template(
            "editar_venda.html", venda=venda, produtos=produtos, itens=itens
        )

    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        return jsonify({"sucesso": False, "erro": "Dados da edição inválidos."}), 400
    cliente_nome = dados.get("cliente_nome")
    forma_pagamento = dados.get("forma_pagamento")
    itens_enviados = dados.get("itens")
    if not isinstance(cliente_nome, str) or not cliente_nome.strip():
        return jsonify({"sucesso": False, "erro": "Informe o nome do cliente."}), 400
    if forma_pagamento not in ("PIX", "CARTAO_CREDITO", "BOLETO_FATURADO"):
        return jsonify({"sucesso": False, "erro": "Forma de pagamento inválida."}), 400
    if not isinstance(itens_enviados, list) or not itens_enviados:
        return jsonify({"sucesso": False, "erro": "A venda precisa ter ao menos um produto."}), 400

    quantidades = {}
    try:
        for item in itens_enviados:
            if not isinstance(item, dict):
                raise ValueError("Há um item inválido na venda.")
            produto_id = parse_integer(item.get("produto_id"), "Produto", 1)
            quantidade = parse_integer(item.get("quantidade"), "Quantidade", 1)
            quantidades[produto_id] = quantidades.get(produto_id, 0) + quantidade
    except ValueError as error:
        return jsonify({"sucesso": False, "erro": str(error)}), 400

    conn = get_db(autocommit_mode=True)
    try:
        conn.execute("BEGIN IMMEDIATE")
        venda = conn.execute(
            "SELECT * FROM Vendas WHERE id = ?", (venda_id,)
        ).fetchone()
        if (
            not venda
            or venda["status_venda"] != "CONCLUIDA"
            or venda["status_pagamento"] != "PENDENTE"
        ):
            raise ValueError("Esta venda já foi paga ou não pode ser editada.")
        itens_anteriores = conn.execute(
            "SELECT * FROM Itens_Venda WHERE venda_id = ?", (venda_id,)
        ).fetchall()
        for item in itens_anteriores:
            conn.execute(
                "UPDATE Produtos SET quantidade_estoque = quantidade_estoque + ? WHERE id = ?",
                (item["quantidade_vendida"], item["produto_id"]),
            )
            conn.execute(
                """
                INSERT INTO Movimentacoes
                    (produto_id, tipo_operacao, quantidade, observacao)
                VALUES (?, 'Entrada', ?, ?)
                """,
                (
                    item["produto_id"],
                    item["quantidade_vendida"],
                    f"Devolução por edição da venda {venda['numero_pedido']}",
                ),
            )

        itens_novos = []
        valor_total = Decimal("0.00")
        for produto_id, quantidade in quantidades.items():
            produto = conn.execute(
                """
                SELECT id, nome, preco_venda, quantidade_estoque
                FROM Produtos WHERE id = ? AND ativo = 1
                """,
                (produto_id,),
            ).fetchone()
            if not produto:
                raise ValueError("Um produto selecionado não existe ou está desativado.")
            if produto["quantidade_estoque"] < quantidade:
                raise ValueError(
                    f"Estoque insuficiente para '{produto['nome']}'. "
                    "Nenhuma alteração foi salva."
                )
            preco = Decimal(str(produto["preco_venda"])).quantize(Decimal("0.01"))
            subtotal = (preco * quantidade).quantize(Decimal("0.01"))
            valor_total += subtotal
            itens_novos.append((produto, quantidade, float(preco), float(subtotal)))

        conn.execute("DELETE FROM Itens_Venda WHERE venda_id = ?", (venda_id,))
        for produto, quantidade, preco, subtotal in itens_novos:
            atualizacao = conn.execute(
                """
                UPDATE Produtos SET quantidade_estoque = quantidade_estoque - ?
                WHERE id = ? AND quantidade_estoque >= ?
                """,
                (quantidade, produto["id"], quantidade),
            )
            if atualizacao.rowcount != 1:
                raise ValueError(
                    f"Estoque insuficiente para '{produto['nome']}'. "
                    "Nenhuma alteração foi salva."
                )
            conn.execute(
                """
                INSERT INTO Itens_Venda
                    (venda_id, produto_id, quantidade_vendida,
                     preco_unitario_praticado, subtotal_item)
                VALUES (?, ?, ?, ?, ?)
                """,
                (venda_id, produto["id"], quantidade, preco, subtotal),
            )
            conn.execute(
                """
                INSERT INTO Movimentacoes
                    (produto_id, tipo_operacao, quantidade, observacao)
                VALUES (?, 'Saída', ?, ?)
                """,
                (
                    produto["id"],
                    quantidade,
                    f"Nova baixa por edição da venda {venda['numero_pedido']}",
                ),
            )

        pagamento_status = (
            "PENDENTE" if forma_pagamento == "BOLETO_FATURADO" else "PAGO"
        )
        conn.execute(
            """
            UPDATE Vendas
            SET cliente_nome = ?, forma_pagamento = ?, valor_total = ?,
                status_pagamento = ?
            WHERE id = ?
            """,
            (
                cliente_nome.strip(),
                forma_pagamento,
                float(valor_total),
                pagamento_status,
                venda_id,
            ),
        )
        conn.execute("COMMIT")
        return jsonify(
            {
                "sucesso": True,
                "redirect_url": url_for("listar_vendas"),
            }
        )
    except ValueError as error:
        if conn.in_transaction:
            conn.rollback()
        return jsonify({"sucesso": False, "erro": str(error)}), 400
    except sqlite3.Error:
        if conn.in_transaction:
            conn.rollback()
        app.logger.exception("Falha ao editar venda %s", venda_id)
        return jsonify(
            {"sucesso": False, "erro": "Não foi possível salvar as alterações da venda."}
        ), 500
    finally:
        conn.close()


@app.route("/vendas/<int:venda_id>/pagamento", methods=["POST"])
@gerente_required
def confirmar_pagamento(venda_id):
    conn = get_db(autocommit_mode=True)
    try:
        conn.execute("BEGIN IMMEDIATE")
        venda = conn.execute(
            "SELECT status_venda, status_pagamento FROM Vendas WHERE id = ?",
            (venda_id,),
        ).fetchone()
        if (
            not venda
            or venda["status_venda"] != "CONCLUIDA"
            or venda["status_pagamento"] != "PENDENTE"
        ):
            conn.rollback()
            flash("A venda não está pendente de pagamento.", "erro")
        else:
            atualizacao = conn.execute(
                """
                UPDATE Vendas SET status_pagamento = 'PAGO'
                WHERE id = ? AND status_venda = 'CONCLUIDA'
                  AND status_pagamento = 'PENDENTE'
                """,
                (venda_id,),
            )
            if atualizacao.rowcount != 1:
                conn.rollback()
                flash("A venda não está pendente de pagamento.", "erro")
                return redirect(url_for("listar_vendas"))
            conn.commit()
            flash("Pagamento confirmado. A venda não poderá mais ser editada.", "sucesso")
    except sqlite3.Error:
        if conn.in_transaction:
            conn.rollback()
        app.logger.exception("Falha ao confirmar pagamento da venda %s", venda_id)
        flash("Não foi possível confirmar o pagamento.", "erro")
    finally:
        conn.close()
    return redirect(url_for("listar_vendas"))


@app.route("/vendas/<int:venda_id>/cancelar", methods=["POST"])
@gerente_required
def cancelar_venda(venda_id):
    conn = get_db(autocommit_mode=True)
    try:
        conn.execute("BEGIN IMMEDIATE;")
        venda = conn.execute("SELECT * FROM Vendas WHERE id = ?", (venda_id,)).fetchone()
        if not venda or venda["status_venda"] == "CANCELADA":
            raise ValueError("Venda inválida ou já cancelada.")

        itens = conn.execute("SELECT * FROM Itens_Venda WHERE venda_id = ?", (venda_id,)).fetchall()
        for item in itens:
            conn.execute(
                "UPDATE Produtos SET quantidade_estoque = quantidade_estoque + ? WHERE id = ?",
                (item["quantidade_vendida"], item["produto_id"]),
            )
            conn.execute(
                """
                INSERT INTO Movimentacoes
                    (produto_id, tipo_operacao, quantidade, observacao)
                VALUES (?, 'Entrada', ?, ?)
                """,
                (item["produto_id"], item["quantidade_vendida"], f"Estorno Cancelamento {venda['numero_pedido']}"),
            )

        conn.execute("UPDATE Vendas SET status_venda = 'CANCELADA' WHERE id = ?", (venda_id,))
        conn.execute("COMMIT;")
        flash(f"Pedido {venda['numero_pedido']} cancelado e estoque estornado com sucesso.", "sucesso")
    except ValueError as error:
        if conn.in_transaction:
            conn.rollback()
        flash(str(error), "erro")
    except sqlite3.Error:
        if conn.in_transaction:
            conn.rollback()
        app.logger.exception("Falha ao cancelar venda %s", venda_id)
        flash("Não foi possível cancelar a venda; estoque e histórico permaneceram inalterados.", "erro")
    finally:
        conn.close()

    return redirect(url_for("listar_vendas"))


if __name__ == "__main__":
    app.run()