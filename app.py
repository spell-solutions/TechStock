import sqlite3
import uuid
import hashlib
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import check_password_hash

app = Flask(__name__)
app.secret_key = "techstore_chave_secreta_corporativa_2026"
DB_PATH = "techstock.db"


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
            return redirect(url_for("index")), 403
        return f(*args, **kwargs)
    return decorated


# --- AUTENTICAÇÃO ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM Usuarios WHERE email = ? AND status = 'ATIVO'", (email,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["senha_hash"], senha):
            session["usuario_id"] = user["id"]
            session["usuario_nome"] = user["nome_completo"]
            session["perfil_acesso"] = user["perfil_acesso"]
            flash(f"Bem-vindo(a), {user['nome_completo']} ({user['perfil_acesso']}).", "sucesso")
            return redirect(url_for("pdv"))
        else:
            flash("Credenciais inválidas ou usuário inativo.", "erro")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Sessão encerrada com segurança.", "sucesso")
    return redirect(url_for("login"))


# --- PROTEÇÃO NAS ROTAS LEGADAS ---
# Aplique @login_required nas rotas de listagem (index, movimentacoes)
# Aplique @gerente_required nas rotas de cadastrar produto, editar produto/preço, excluir produto e relatórios!


# --- FRENTE DE CAIXA / PDV MULTI-ITENS ---
@app.route("/pdv", methods=["GET"])
@login_required
def pdv():
    conn = get_db()
    produtos = conn.execute("SELECT * FROM Produtos ORDER BY nome ASC").fetchall()
    conn.close()
    return render_template("pdv.html", produtos=produtos)


# --- CHECKOUT TRANSACIONAL COM GARANTIA ACID (REQ-04) ---
@app.route("/pdv/finalizar", methods=["POST"])
@login_required
def finalizar_venda():
    dados = request.get_json()
    if not dados:
        return jsonify({"sucesso": False, "erro": "Payload inválido."}), 400

    cliente_nome = dados.get("cliente_nome", "").strip()
    cliente_documento = dados.get("cliente_documento", "").strip()
    forma_pagamento = dados.get("forma_pagamento", "").strip()
    itens = dados.get("itens", [])

    if not cliente_nome or not cliente_documento or forma_pagamento not in ("PIX", "CARTAO_CREDITO", "BOLETO_FATURADO"):
        return jsonify({"sucesso": False, "erro": "Preencha nome do cliente, CPF/CNPJ e forma de pagamento válida."}), 400

    if not itens:
        return jsonify({"sucesso": False, "erro": "O carrinho está vazio. Adicione ao menos um item."}), 400

    conn = get_db(autocommit_mode=True)
    try:
        # INÍCIO DA TRANSAÇÃO EXPLÍCITA (ACID)
        conn.execute("BEGIN IMMEDIATE;")

        valor_total = 0.0
        itens_validados = []

        # 1. Validação estrita de estoque e congelamento de preços
        for item in itens:
            produto_id = int(item["produto_id"])
            qtd = int(item["quantidade"])
            if qtd <= 0:
                raise ValueError("A quantidade de cada item deve ser maior que zero.")

            prod = conn.execute(
                "SELECT id, nome, estoque, preco_venda FROM Produtos WHERE id = ?",
                (produto_id,),
            ).fetchone()

            if not prod:
                raise ValueError(f"Produto ID {produto_id} não encontrado no catálogo.")

            # CLÁUSULA DE ABORTO: Impede saldo negativo
            if prod["estoque"] < qtd:
                raise ValueError(
                    f"Estoque insuficiente para '{prod['nome']}'. "
                    f"Disponível: {prod['estoque']} un. | Solicitado: {qtd} un. Operação abortada."
                )

            preco_praticado = float(prod["preco_venda"])
            subtotal = round(preco_praticado * qtd, 2)
            valor_total = round(valor_total + subtotal, 2)

            itens_validados.append({
                "produto_id": prod["id"],
                "nome": prod["nome"],
                "quantidade": qtd,
                "preco_unitario": preco_praticado,
                "subtotal": subtotal,
            })

        # 2. Cria o cabeçalho da venda
        numero_pedido = f"PED-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        cursor = conn.execute(
            """
            INSERT INTO Vendas (numero_pedido, data_hora, cliente_nome, cliente_documento, forma_pagamento, valor_total, status_venda, usuario_id)
            VALUES (?, ?, ?, ?, ?, ?, 'CONCLUIDA', ?)
            """,
            (
                numero_pedido,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                cliente_nome,
                cliente_documento,
                forma_pagamento,
                valor_total,
                session["usuario_id"],
            ),
        )
        venda_id = cursor.lastrowid

        # 3. Insere itens, debita estoque e registra auditoria em Movimentacoes
        for iv in itens_validados:
            conn.execute(
                """
                INSERT INTO Itens_Venda (venda_id, produto_id, quantidade_vendida, preco_unitario_praticado, subtotal_item)
                VALUES (?, ?, ?, ?, ?)
                """,
                (venda_id, iv["produto_id"], iv["quantidade"], iv["preco_unitario"], iv["subtotal"]),
            )

            conn.execute(
                "UPDATE Produtos SET estoque = estoque - ? WHERE id = ?",
                (iv["quantidade"], iv["produto_id"]),
            )

            # Ajuste os nomes das colunas abaixo caso sua tabela Movimentacoes tenha colunas diferentes
            conn.execute(
                """
                INSERT INTO Movimentacoes (produto_id, tipo, quantidade, observacao)
                VALUES (?, 'SAIDA', ?, ?)
                """,
                (iv["produto_id"], iv["quantidade"], f"Venda PDV {numero_pedido} - Operador #{session['usuario_id']}"),
            )

        # CONFIRMAÇÃO ATÔMICA DA TRANSAÇÃO
        conn.execute("COMMIT;")
        return jsonify({
            "sucesso": True,
            "venda_id": venda_id,
            "redirect_url": url_for("recibo_venda", venda_id=venda_id),
        })

    except Exception as e:
        # ROLLBACK INTEGRAL EM CASO DE QUALQUER ERRO
        conn.execute("ROLLBACK;")
        return jsonify({"sucesso": False, "erro": str(e)}), 400
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

    itens = conn.execute(
        """
        SELECT iv.*, p.nome AS produto_nome
        FROM Itens_Venda iv
        JOIN Produtos p ON iv.produto_id = p.id
        WHERE iv.venda_id = ?
        """,
        (venda_id,),
    ).fetchall()
    conn.close()

    # Gera chave de autenticidade SHA-256 resumida para o comprovante corporativo
    raw_sig = f"{venda['numero_pedido']}|{venda['cliente_documento']}|{venda['valor_total']}|{venda['data_hora']}"
    chave_autenticidade = hashlib.sha256(raw_sig.encode()).hexdigest()[:24].upper()

    return render_template("recibo.html", venda=venda, itens=itens, chave_autenticidade=chave_autenticidade)


# --- HISTÓRICO E CANCELAMENTO DE VENDA (APENAS GERENTE) ---
@app.route("/vendas")
@login_required
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
                "UPDATE Produtos SET estoque = estoque + ? WHERE id = ?",
                (item["quantidade_vendida"], item["produto_id"]),
            )
            conn.execute(
                "INSERT INTO Movimentacoes (produto_id, tipo, quantidade, observacao) VALUES (?, 'ENTRADA', ?, ?)",
                (item["produto_id"], item["quantidade_vendida"], f"Estorno Cancelamento {venda['numero_pedido']}"),
            )

        conn.execute("UPDATE Vendas SET status_venda = 'CANCELADA' WHERE id = ?", (venda_id,))
        conn.execute("COMMIT;")
        flash(f"Pedido {venda['numero_pedido']} cancelado e estoque estornado com sucesso.", "sucesso")
    except Exception as e:
        conn.execute("ROLLBACK;")
        flash(f"Erro ao cancelar venda: {e}", "erro")
    finally:
        conn.close()

    return redirect(url_for("listar_vendas"))