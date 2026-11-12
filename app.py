import re
import os, secrets
import sqlite3
import uuid
import hashlib
from datetime import datetime
from pathlib import Path
from decimal import Decimal
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.setdefault("TECHSTOCK_KEY", secrets.token_hex(16))
BANCO = Path(__file__).resolve().parent / "techstock.db"


def conectar_banco(modo_transacao_manual=False):
    conexao = sqlite3.connect(BANCO, isolation_level=None if modo_transacao_manual else "")
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    return conexao


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
            html_negado = f"""
            <div style="font-family:sans-serif; max-width:520px; margin:80px auto; padding:30px; border:1px solid #fecaca; background:#fef2f2; border-radius:10px; color:#991b1b;">
                <h2 style="margin-top:0;">403 — Acesso Negado (RBAC)</h2>
                <p>Seu perfil atual é <strong>{session.get('perfil_acesso')}</strong>. Esta operação exige perfil <strong>GERENTE</strong>.</p>
                <a href="{url_for('pdv')}" style="display:inline-block; margin-top:12px; padding:10px 16px; background:#1e293b; color:#fff; text-decoration:none; border-radius:6px;">Voltar ao PDV</a>
                <a href="{url_for('inicio')}" style="display:inline-block; margin-top:12px; margin-left:8px; padding:10px 16px; background:#475569; color:#fff; text-decoration:none; border-radius:6px;">Voltar ao Catálogo</a>
            </div>
            """
            return html_negado, 403
        return f(*args, **kwargs)
    return decorated


@app.after_request
def injetar_barra_sessao(response):
    if response.status_code == 200 and "text/html" in response.content_type and "usuario_id" in session and request.endpoint not in ("login", "pdv", "recibo_venda", "listar_vendas", "relatorios"):
        html = response.get_data(as_text=True)
        m = re.search(r'<a([^>]*)>\s*Movimentações\s*</a>', html)
        attrs = m.group(1) if m else ' style="display:block; padding:10px 14px; color:#cbd5e1; text-decoration:none; border-radius:6px; margin-bottom:4px;"'
        attrs = re.sub(r'href="[^"]*"', '', attrs).replace('active', '')
        links_pdv = f'\n<a href="{url_for("pdv")}"{attrs}>Abrir PDV (Vendas)</a>\n<a href="{url_for("listar_vendas")}"{attrs}>Histórico Vendas</a>'
        if "Painel inicial</a>" in html and "Abrir PDV (Vendas)" not in html:
            html = html.replace("Painel inicial</a>", "Painel inicial</a>" + links_pdv, 1)
        rodape = f'<div style="margin-top:auto; padding-top:14px; border-top:1px solid rgba(255,255,255,0.15); font-size:13px; color:#e2e8f0;"><div style="font-weight:bold;">{session.get("usuario_nome")}</div><span style="display:inline-block; background:#2563eb; color:#fff; padding:2px 8px; border-radius:4px; font-size:11px; margin:6px 0;">{session.get("perfil_acesso")}</span><br><a href="{url_for("logout")}" style="color:#fca5a5; text-decoration:none; font-weight:bold;">Sair</a></div>'
        if "</aside>" in html and "Sair</a>" not in html:
            html = html.replace("</aside>", rodape + "</aside>", 1)
        response.set_data(html)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        conexao = conectar_banco()
        try:
            usuario = conexao.execute("SELECT * FROM Usuarios WHERE email = ? AND status = 'ATIVO'", (email,)).fetchone()
        finally:
            conexao.close()

        if usuario and check_password_hash(usuario["senha_hash"], senha):
            session["usuario_id"] = usuario["id"]
            session["usuario_nome"] = usuario["nome_completo"]
            session["perfil_acesso"] = usuario["perfil_acesso"]
            flash(f"Bem-vindo(a), {usuario['nome_completo']}!", "sucesso")
            return redirect(url_for("inicio"))
        flash("E-mail ou senha inválidos, ou usuário inativo.", "erro")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Sessão encerrada com segurança.", "sucesso")
    return redirect(url_for("login"))


@app.route("/")
@login_required
def inicio():
    busca = request.args.get("busca", "").strip()
    termo = f"%{busca}%"
    conexao = conectar_banco()
    try:
        produtos = conexao.execute("""
            SELECT p.id, p.sku, p.nome, p.fabricante, p.preco_venda, p.quantidade_estoque, p.estoque_minimo, c.nome AS categoria, f.razao_social AS fornecedor
            FROM produtos p
            INNER JOIN categorias c ON p.categoria_id = c.id
            INNER JOIN fornecedores f ON p.fornecedor_id = f.id
            WHERE p.ativo = 1 AND (p.sku LIKE ? OR p.nome LIKE ? OR p.fabricante LIKE ?)
            ORDER BY p.nome
        """, (termo, termo, termo)).fetchall()
        total_produtos = conexao.execute("SELECT COUNT(*) FROM produtos WHERE ativo = 1").fetchone()[0]
        total_unidades = conexao.execute("SELECT COALESCE(SUM(quantidade_estoque), 0) FROM produtos WHERE ativo = 1").fetchone()[0]
        total_categorias = conexao.execute("SELECT COUNT(*) FROM categorias").fetchone()[0]
    finally:
        conexao.close()
    produtos_baixos = [p for p in produtos if p["quantidade_estoque"] < p["estoque_minimo"]]
    return render_template("index.html", produtos=produtos, total_produtos=total_produtos, total_unidades=total_unidades, total_categorias=total_categorias, produtos_baixos=produtos_baixos, total_alertas=len(produtos_baixos), busca=busca)


@app.route("/produtos/novo", methods=["GET", "POST"])
@gerente_required
def novo_produto():
    conexao = conectar_banco()
    try:
        if request.method == "GET":
            return render_template("produto_form.html", categorias=conexao.execute("SELECT id, nome FROM categorias ORDER BY nome").fetchall(), fornecedores=conexao.execute("SELECT id, razao_social FROM fornecedores ORDER BY razao_social").fetchall())
        preco = Decimal(request.form.get("preco_venda", "0").replace(",", "."))
        quantidade = int(request.form.get("quantidade_estoque", "0"))
        with conexao:
            cur = conexao.execute(
                "INSERT INTO produtos (sku, nome, fabricante, classificacao, especificacao, modalidade_licenca, preco_venda, quantidade_estoque, estoque_minimo, localizacao, categoria_id, fornecedor_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (request.form.get("sku", "").strip(), request.form.get("nome", "").strip(), request.form.get("fabricante", "").strip(), request.form.get("classificacao", "").strip(), request.form.get("especificacao", "").strip(), request.form.get("modalidade_licenca", "").strip(), float(preco), quantidade, int(request.form.get("estoque_minimo", "0")), request.form.get("localizacao", "").strip(), int(request.form.get("categoria_id", "0")), int(request.form.get("fornecedor_id", "0"))),
            )
            if quantidade > 0:
                conexao.execute("INSERT INTO movimentacoes (produto_id, tipo_operacao, quantidade, observacao) VALUES (?, 'Entrada', ?, 'Estoque inicial')", (cur.lastrowid, quantidade))
        flash("Produto cadastrado com sucesso!", "sucesso")
        return redirect(url_for("inicio"))
    except Exception as e:
        flash(f"Erro ao cadastrar produto: {e}", "erro")
        return redirect(url_for("novo_produto"))
    finally:
        conexao.close()


@app.route("/produtos/<int:produto_id>/editar", methods=["GET", "POST"])
@gerente_required
def editar_produto(produto_id):
    conexao = conectar_banco()
    try:
        produto = conexao.execute("SELECT * FROM produtos WHERE id = ? AND ativo = 1", (produto_id,)).fetchone()
        if not produto:
            flash("Produto não encontrado.", "erro")
            return redirect(url_for("inicio"))
        if request.method == "GET":
            return render_template("editar_produto.html", produto=produto, categorias=conexao.execute("SELECT id, nome FROM categorias ORDER BY nome").fetchall(), fornecedores=conexao.execute("SELECT id, razao_social FROM fornecedores ORDER BY razao_social").fetchall())
        preco = Decimal(request.form.get("preco_venda", "0").replace(",", "."))
        with conexao:
            conexao.execute(
                "UPDATE produtos SET sku=?, nome=?, fabricante=?, classificacao=?, especificacao=?, modalidade_licenca=?, preco_venda=?, estoque_minimo=?, localizacao=?, categoria_id=?, fornecedor_id=? WHERE id=?",
                (request.form.get("sku", "").strip(), request.form.get("nome", "").strip(), request.form.get("fabricante", "").strip(), request.form.get("classificacao", "").strip(), request.form.get("especificacao", "").strip(), request.form.get("modalidade_licenca", "").strip(), float(preco), int(request.form.get("estoque_minimo", "0")), request.form.get("localizacao", "").strip(), int(request.form.get("categoria_id", "0")), int(request.form.get("fornecedor_id", "0")), produto_id),
            )
        flash("Produto atualizado com sucesso!", "sucesso")
        return redirect(url_for("inicio"))
    except Exception as e:
        flash(f"Erro ao editar: {e}", "erro")
        return redirect(url_for("editar_produto", produto_id=produto_id))
    finally:
        conexao.close()


@app.route("/produtos/<int:produto_id>/desativar", methods=["POST"])
@gerente_required
def desativar_produto(produto_id):
    conexao = conectar_banco()
    try:
        with conexao:
            conexao.execute("UPDATE produtos SET ativo = 0 WHERE id = ? AND ativo = 1", (produto_id,))
        flash("Produto desativado com sucesso!", "sucesso")
        return redirect(url_for("inicio"))
    finally:
        conexao.close()


@app.route("/movimentacoes")
@login_required
def movimentacoes():
    conexao = conectar_banco()
    try:
        registros = conexao.execute("SELECT m.id, p.sku, p.nome AS produto, m.tipo_operacao, m.quantidade, m.data_hora, m.observacao FROM movimentacoes m INNER JOIN produtos p ON m.produto_id = p.id ORDER BY m.data_hora DESC, m.id DESC").fetchall()
    finally:
        conexao.close()
    return render_template("movimentacoes.html", registros=registros)


@app.route("/movimentacoes/nova", methods=["GET", "POST"])
@gerente_required
def nova_movimentacao():
    conexao = conectar_banco()
    try:
        produtos = conexao.execute("SELECT id, sku, nome, quantidade_estoque FROM produtos WHERE ativo = 1 ORDER BY nome").fetchall()
        if request.method == "GET":
            return render_template("movimentacao_form.html", produtos=produtos)
        produto_id = int(request.form.get("produto_id", "0"))
        tipo_operacao = request.form.get("tipo_operacao", "").strip()
        quantidade = int(request.form.get("quantidade", "0"))
        observacao = request.form.get("observacao", "").strip()
        with conexao:
            if tipo_operacao == "Entrada":
                res = conexao.execute("UPDATE produtos SET quantidade_estoque = quantidade_estoque + ? WHERE id = ? AND ativo = 1", (quantidade, produto_id))
            else:
                res = conexao.execute("UPDATE produtos SET quantidade_estoque = quantidade_estoque - ? WHERE id = ? AND ativo = 1 AND quantidade_estoque >= ?", (quantidade, produto_id, quantidade))
            if res.rowcount == 0:
                flash("Estoque insuficiente ou produto inválido.", "erro")
                return redirect(url_for("nova_movimentacao"))
            conexao.execute("INSERT INTO movimentacoes (produto_id, tipo_operacao, quantidade, observacao) VALUES (?, ?, ?, ?)", (produto_id, tipo_operacao, quantidade, observacao))
        flash("Movimentação registrada!", "sucesso")
        return redirect(url_for("movimentacoes"))
    finally:
        conexao.close()


@app.route("/relatorios")
@gerente_required
def relatorios():
    conexao = conectar_banco()
    try:
        total_produtos = conexao.execute("SELECT COUNT(*) FROM produtos WHERE ativo = 1").fetchone()[0]
        total_unidades = conexao.execute("SELECT COALESCE(SUM(quantidade_estoque), 0) FROM produtos WHERE ativo = 1").fetchone()[0]
        produtos_baixos = conexao.execute("SELECT COUNT(*) FROM produtos WHERE ativo = 1 AND quantidade_estoque < estoque_minimo").fetchone()[0]
        total_entradas = conexao.execute("SELECT COALESCE(SUM(quantidade), 0) FROM movimentacoes WHERE tipo_operacao = 'Entrada'").fetchone()[0]
        total_saidas = conexao.execute("SELECT COALESCE(SUM(quantidade), 0) FROM movimentacoes WHERE tipo_operacao = 'Saída'").fetchone()[0]
        historico = conexao.execute("SELECT p.sku, p.nome AS produto, m.tipo_operacao, m.quantidade, m.data_hora FROM movimentacoes m INNER JOIN produtos p ON m.produto_id = p.id ORDER BY m.data_hora DESC, m.id DESC LIMIT 20").fetchall()
    finally:
        conexao.close()
    return render_template("relatorios.html", total_produtos=total_produtos, total_unidades=total_unidades, produtos_baixos=produtos_baixos, total_entradas=total_entradas, total_saidas=total_saidas, historico=historico)


@app.route("/pdv", methods=["GET"])
@login_required
def pdv():
    conexao = conectar_banco()
    try:
        produtos = conexao.execute("SELECT id, sku, nome, fabricante, classificacao, modalidade_licenca, preco_venda, quantidade_estoque FROM produtos WHERE ativo = 1 ORDER BY nome ASC").fetchall()
    finally:
        conexao.close()
    return render_template("pdv.html", produtos=produtos)


@app.route("/pdv/finalizar", methods=["POST"])
@login_required
def finalizar_venda():
    dados = request.get_json(silent=True) or {}
    cliente_nome = dados.get("cliente_nome", "").strip()
    cliente_documento = dados.get("cliente_documento", "").strip()
    forma_pagamento = dados.get("forma_pagamento", "").strip()
    itens = dados.get("itens", [])

    if not cliente_nome or not cliente_documento or forma_pagamento not in ("PIX", "CARTAO_CREDITO", "BOLETO_FATURADO") or not itens:
        return jsonify({"sucesso": False, "erro": "Preencha cliente, CPF/CNPJ, forma de pagamento e adicione ao menos 1 item."}), 400

    conexao = conectar_banco(modo_transacao_manual=True)
    try:
        conexao.execute("BEGIN IMMEDIATE;")
        valor_total = 0.0
        itens_validados = []
        qtd_por_produto = {}

        for item in itens:
            pid = int(item["produto_id"])
            qtd = int(item["quantidade"])
            if qtd <= 0:
                raise ValueError("Quantidade deve ser maior que zero.")
            qtd_por_produto[pid] = qtd_por_produto.get(pid, 0) + qtd

        for produto_id, qtd in qtd_por_produto.items():
            prod = conexao.execute("SELECT id, sku, nome, preco_venda, quantidade_estoque FROM produtos WHERE id = ? AND ativo = 1", (produto_id,)).fetchone()
            if not prod:
                raise ValueError(f"Produto ID {produto_id} não encontrado.")
            if prod["quantidade_estoque"] < qtd:
                raise ValueError(f"Estoque insuficiente para '{prod['nome']}' (SKU {prod['sku']}). Disponível: {prod['quantidade_estoque']} | Solicitado: {qtd}. Operação abortada (ROLLBACK).")
            preco_praticado = float(prod["preco_venda"])
            subtotal = round(preco_praticado * qtd, 2)
            valor_total = round(valor_total + subtotal, 2)
            itens_validados.append({"produto_id": prod["id"], "quantidade": qtd, "preco_unitario": preco_praticado, "subtotal": subtotal})

        numero_pedido = f"PED-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        data_hora_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor = conexao.execute(
            "INSERT INTO Vendas (numero_pedido, data_hora, cliente_nome, cliente_documento, forma_pagamento, valor_total, status_venda, usuario_id) VALUES (?, ?, ?, ?, ?, ?, 'CONCLUIDA', ?)",
            (numero_pedido, data_hora_atual, cliente_nome, cliente_documento, forma_pagamento, valor_total, session["usuario_id"]),
        )
        venda_id = cursor.lastrowid

        for iv in itens_validados:
            conexao.execute("INSERT INTO Itens_Venda (venda_id, produto_id, quantidade_vendida, preco_unitario_praticado, subtotal_item) VALUES (?, ?, ?, ?, ?)", (venda_id, iv["produto_id"], iv["quantidade"], iv["preco_unitario"], iv["subtotal"]))
            conexao.execute("UPDATE produtos SET quantidade_estoque = quantidade_estoque - ? WHERE id = ?", (iv["quantidade"], iv["produto_id"]))
            conexao.execute("INSERT INTO movimentacoes (produto_id, tipo_operacao, quantidade, data_hora, observacao) VALUES (?, 'Saída', ?, ?, ?)", (iv["produto_id"], iv["quantidade"], data_hora_atual, f"Venda PDV {numero_pedido} | Operador: {session['usuario_nome']}"))

        conexao.execute("COMMIT;")
        return jsonify({"sucesso": True, "venda_id": venda_id, "redirect_url": url_for("recibo_venda", venda_id=venda_id)})
    except Exception as e:
        if conexao.in_transaction:
            conexao.execute("ROLLBACK;")
        return jsonify({"sucesso": False, "erro": str(e)}), 400
    finally:
        conexao.close()


@app.route("/vendas/<int:venda_id>/recibo")
@login_required
def recibo_venda(venda_id):
    conexao = conectar_banco()
    try:
        venda = conexao.execute("SELECT v.*, u.nome_completo AS operador_nome FROM Vendas v INNER JOIN Usuarios u ON v.usuario_id = u.id WHERE v.id = ?", (venda_id,)).fetchone()
        if not venda:
            flash("Venda não encontrada.", "erro")
            return redirect(url_for("inicio"))
        itens = conexao.execute("SELECT iv.*, p.sku, p.nome AS produto_nome, p.classificacao, p.modalidade_licenca FROM Itens_Venda iv INNER JOIN produtos p ON iv.produto_id = p.id WHERE iv.venda_id = ?", (venda_id,)).fetchall()
    finally:
        conexao.close()
    assinatura = f"{venda['numero_pedido']}|{venda['cliente_documento']}|{venda['valor_total']}|{venda['data_hora']}"
    chave_autenticidade = hashlib.sha256(assinatura.encode("utf-8")).hexdigest()[:24].upper()
    return render_template("recibo.html", venda=venda, itens=itens, chave_autenticidade=chave_autenticidade)


@app.route("/vendas")
@login_required
def listar_vendas():
    conexao = conectar_banco()
    try:
        vendas = conexao.execute("SELECT v.*, u.nome_completo AS operador_nome FROM Vendas v INNER JOIN Usuarios u ON v.usuario_id = u.id ORDER BY v.id DESC").fetchall()
    finally:
        conexao.close()
    return render_template("vendas.html", vendas=vendas)


@app.route("/vendas/<int:venda_id>/cancelar", methods=["POST"])
@gerente_required
def cancelar_venda(venda_id):
    conexao = conectar_banco(modo_transacao_manual=True)
    try:
        conexao.execute("BEGIN IMMEDIATE;")
        venda = conexao.execute("SELECT * FROM Vendas WHERE id = ?", (venda_id,)).fetchone()
        if not venda or venda["status_venda"] == "CANCELADA":
            raise ValueError("Venda inválida ou já cancelada.")
        itens = conexao.execute("SELECT * FROM Itens_Venda WHERE venda_id = ?", (venda_id,)).fetchall()
        data_hora_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for item in itens:
            conexao.execute("UPDATE produtos SET quantidade_estoque = quantidade_estoque + ? WHERE id = ?", (item["quantidade_vendida"], item["produto_id"]))
            conexao.execute("INSERT INTO movimentacoes (produto_id, tipo_operacao, quantidade, data_hora, observacao) VALUES (?, 'Entrada', ?, ?, ?)", (item["produto_id"], item["quantidade_vendida"], data_hora_atual, f"Estorno Cancelamento {venda['numero_pedido']} | Gerente: {session['usuario_nome']}"))
        conexao.execute("UPDATE Vendas SET status_venda = 'CANCELADA' WHERE id = ?", (venda_id,))
        conexao.execute("COMMIT;")
        flash(f"Pedido {venda['numero_pedido']} cancelado e estoque estornado!", "sucesso")
    except Exception as e:
        if conexao.in_transaction:
            conexao.execute("ROLLBACK;")
        flash(f"Erro ao cancelar: {e}", "erro")
    finally:
        conexao.close()
    return redirect(url_for("listar_vendas"))


if __name__ == "__main__":
    app.run(debug=True)