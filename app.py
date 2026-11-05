
import sqlite3
from pathlib import Path
from decimal import Decimal, InvalidOperation

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash
)

# Criar nossa aplicação
app = Flask(__name__)

# Chave para utilizar mensagens temporarias do Flask
app.secret_key = "techstock-chave-local"

# Localizacao do banco de dados
BANCO = Path(__file__).resolve().parent / "techstock.db"


# ==========================================
# CONEXAO COM O BANCO DE DADOS
# ==========================================

def conectar_banco():
    conexao = sqlite3.connect(BANCO)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    return conexao


# ==========================================
# PAINEL PRINCIPAL
# ==========================================

@app.route("/")
def inicio():
    busca = request.args.get("busca", "").strip()
    termo = f"%{busca}%"
    conexao = conectar_banco()

    try:
        produtos = conexao.execute("""
            SELECT
                p.id,
                p.sku,
                p.nome,
                p.fabricante,
                p.preco_venda,
                p.quantidade_estoque,
                p.estoque_minimo,
                c.nome AS categoria,
                f.razao_social AS fornecedor

            FROM produtos p

            INNER JOIN categorias c
                ON p.categoria_id = c.id

            INNER JOIN fornecedores f
                ON p.fornecedor_id = f.id

           WHERE p.ativo = 1
AND (
    p.sku LIKE ?
    OR p.nome LIKE ?
    OR p.fabricante LIKE ?
)
ORDER BY p.nome
        """, (termo, termo, termo)).fetchall()

        total_produtos = conexao.execute("""
            SELECT COUNT(*)
            FROM produtos
            WHERE ativo = 1
        """).fetchone()[0]

        total_unidades = conexao.execute("""
            SELECT COALESCE(SUM(quantidade_estoque), 0)
            FROM produtos
            WHERE ativo = 1
        """).fetchone()[0]

        total_categorias = conexao.execute("""
            SELECT COUNT(*)
            FROM categorias
        """).fetchone()[0]

    finally:
        conexao.close()

    # Identificar produtos abaixo do estoque minimo
    produtos_baixos = [
        produto for produto in produtos
        if produto["quantidade_estoque"]
        < produto["estoque_minimo"]
    ]

    total_alertas = len(produtos_baixos)

    return render_template(
        "index.html",
        produtos=produtos,
        total_produtos=total_produtos,
        total_unidades=total_unidades,
        total_categorias=total_categorias,
        produtos_baixos=produtos_baixos,
        total_alertas=total_alertas,
        busca=busca,
    )


# ==========================================
# CADASTRAR NOVO PRODUTO
# ==========================================

@app.route("/produtos/novo", methods=["GET", "POST"])
def novo_produto():

    conexao = conectar_banco()

    try:

        # Quando o usuario abre o formulario
        if request.method == "GET":

            categorias = conexao.execute("""
                SELECT id, nome
                FROM categorias
                ORDER BY nome
            """).fetchall()

            fornecedores = conexao.execute("""
                SELECT id, razao_social
                FROM fornecedores
                ORDER BY razao_social
            """).fetchall()

            return render_template(
                "produto_form.html",
                categorias=categorias,
                fornecedores=fornecedores
            )

        # Quando o usuario envia o formulario

        sku = request.form.get("sku", "").strip()
        nome = request.form.get("nome", "").strip()
        fabricante = request.form.get("fabricante", "").strip()
        classificacao = request.form.get("classificacao", "").strip()

        especificacao = request.form.get("especificacao", "").strip()
        modalidade = request.form.get("modalidade_licenca", "").strip()
        localizacao = request.form.get("localizacao", "").strip()

        preco_texto = request.form.get("preco_venda", "").strip()
        quantidade_texto = request.form.get("quantidade_estoque", "").strip()
        minimo_texto = request.form.get("estoque_minimo", "").strip()

        categoria_texto = request.form.get("categoria_id", "").strip()
        fornecedor_texto = request.form.get("fornecedor_id", "").strip()

        # Verificar campos obrigatorios
        if not all([
            sku, nome, fabricante, classificacao,
            preco_texto, quantidade_texto, minimo_texto,
            categoria_texto, fornecedor_texto
        ]):
            flash("Preencha todos os campos obrigatorios.", "erro")
            return redirect(url_for("novo_produto"))

        # Verificar classificacao
        classificacoes_validas = [
            "Hardware",
            "Software",
            "Periférico"
        ]

        if classificacao not in classificacoes_validas:
            flash("Classificacao invalida.", "erro")
            return redirect(url_for("novo_produto"))

        # Verificar preco
        try:
            preco = Decimal(preco_texto.replace(",", "."))

            if not preco.is_finite() or preco <= 0:
                raise ValueError

        except (InvalidOperation, ValueError):
            flash("O preco deve ser maior que zero.", "erro")
            return redirect(url_for("novo_produto"))

        # Verificar quantidades
        try:
            quantidade = int(quantidade_texto)
            estoque_minimo = int(minimo_texto)
            categoria_id = int(categoria_texto)
            fornecedor_id = int(fornecedor_texto)

            if quantidade < 0 or estoque_minimo < 0:
                raise ValueError

        except ValueError:
            flash("Verifique as quantidades e selecoes informadas.", "erro")
            return redirect(url_for("novo_produto"))

        # Verificar se categoria e fornecedor existem
        categoria = conexao.execute("""
            SELECT id FROM categorias WHERE id = ?
        """, (categoria_id,)).fetchone()

        fornecedor = conexao.execute("""
            SELECT id FROM fornecedores WHERE id = ?
        """, (fornecedor_id,)).fetchone()

        if categoria is None or fornecedor is None:
            flash("Selecione uma categoria e um fornecedor validos.", "erro")
            return redirect(url_for("novo_produto"))

        try:

            # Iniciar transacao no banco
            with conexao:

                # Inserir produto
                cursor = conexao.execute("""
                    INSERT INTO produtos (
                        sku,
                        nome,
                        fabricante,
                        classificacao,
                        especificacao,
                        modalidade_licenca,
                        preco_venda,
                        quantidade_estoque,
                        estoque_minimo,
                        localizacao,
                        categoria_id,
                        fornecedor_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    sku,
                    nome,
                    fabricante,
                    classificacao,
                    especificacao,
                    modalidade,
                    float(preco),
                    quantidade,
                    estoque_minimo,
                    localizacao,
                    categoria_id,
                    fornecedor_id
                ))

                produto_id = cursor.lastrowid

                # Registrar entrada inicial no historico
                if quantidade > 0:

                    conexao.execute("""
                        INSERT INTO movimentacoes (
                            produto_id,
                            tipo_operacao,
                            quantidade,
                            observacao
                        )
                        VALUES (?, 'Entrada', ?, ?)
                    """, (
                        produto_id,
                        quantidade,
                        "Estoque inicial do cadastro"
                    ))

        except sqlite3.IntegrityError:
            flash(
                "Nao foi possivel cadastrar. Verifique se o SKU ja existe ou se algum dado viola as regras do banco.",
                "erro"
            )
            return redirect(url_for("novo_produto"))

        flash("Produto cadastrado com sucesso!", "sucesso")

        return redirect(url_for("inicio"))

    finally:
        conexao.close()

       
# ==========================================
# EDITAR PRODUTO
# ==========================================

@app.route("/produtos/<int:produto_id>/editar", methods=["GET", "POST"])
def editar_produto(produto_id):

    conexao = conectar_banco()

    try:
        produto = conexao.execute("""
            SELECT *
            FROM produtos
            WHERE id = ? AND ativo = 1
        """, (produto_id,)).fetchone()

        if produto is None:
            flash("Produto não encontrado.", "erro")
            return redirect(url_for("inicio"))

        categorias = conexao.execute("""
            SELECT id, nome
            FROM categorias
            ORDER BY nome
        """).fetchall()

        fornecedores = conexao.execute("""
            SELECT id, razao_social
            FROM fornecedores
            ORDER BY razao_social
        """).fetchall()

        if request.method == "GET":
            return render_template(
                "editar_produto.html",
                produto=produto,
                categorias=categorias,
                fornecedores=fornecedores
            )

        sku = request.form.get("sku", "").strip()
        nome = request.form.get("nome", "").strip()
        fabricante = request.form.get("fabricante", "").strip()
        classificacao = request.form.get("classificacao", "").strip()
        especificacao = request.form.get("especificacao", "").strip()
        modalidade = request.form.get("modalidade_licenca", "").strip()
        localizacao = request.form.get("localizacao", "").strip()

        preco_texto = request.form.get("preco_venda", "").strip()
        minimo_texto = request.form.get("estoque_minimo", "").strip()
        categoria_texto = request.form.get("categoria_id", "").strip()
        fornecedor_texto = request.form.get("fornecedor_id", "").strip()

        if not all([
            sku, nome, fabricante, classificacao,
            preco_texto, minimo_texto,
            categoria_texto, fornecedor_texto
        ]):
            flash("Preencha todos os campos obrigatórios.", "erro")
            return redirect(url_for("editar_produto", produto_id=produto_id))

        if classificacao not in ["Hardware", "Software", "Periférico"]:
            flash("Classificação inválida.", "erro")
            return redirect(url_for("editar_produto", produto_id=produto_id))

        try:
            preco = Decimal(preco_texto.replace(",", "."))
            estoque_minimo = int(minimo_texto)
            categoria_id = int(categoria_texto)
            fornecedor_id = int(fornecedor_texto)

            if not preco.is_finite() or preco <= 0:
                raise ValueError

            if estoque_minimo < 0:
                raise ValueError

        except (ValueError, InvalidOperation):
            flash("Verifique o preço e os dados numéricos.", "erro")
            return redirect(url_for("editar_produto", produto_id=produto_id))

        with conexao:
            conexao.execute("""
                UPDATE produtos
                SET sku = ?,
                    nome = ?,
                    fabricante = ?,
                    classificacao = ?,
                    especificacao = ?,
                    modalidade_licenca = ?,
                    preco_venda = ?,
                    estoque_minimo = ?,
                    localizacao = ?,
                    categoria_id = ?,
                    fornecedor_id = ?
                WHERE id = ?
            """, (
                sku,
                nome,
                fabricante,
                classificacao,
                especificacao,
                modalidade,
                float(preco),
                estoque_minimo,
                localizacao,
                categoria_id,
                fornecedor_id,
                produto_id
            ))

        flash("Produto atualizado com sucesso!", "sucesso")
        return redirect(url_for("inicio"))

    except sqlite3.IntegrityError:
        flash("Não foi possível atualizar. Verifique se o SKU já está cadastrado.", "erro")
        return redirect(url_for("editar_produto", produto_id=produto_id))

    finally:
        conexao.close()
 
# ==========================================
# DESATIVAR PRODUTO
# ==========================================

@app.route("/produtos/<int:produto_id>/desativar", methods=["POST"])
def desativar_produto(produto_id):

    conexao = conectar_banco()

    try:
        with conexao:
            resultado = conexao.execute("""
                UPDATE produtos
                SET ativo = 0
                WHERE id = ? AND ativo = 1
            """, (produto_id,))

        if resultado.rowcount > 0:
            flash("Produto desativado com sucesso!", "sucesso")
        else:
            flash("Produto não encontrado ou já desativado.", "erro")

        return redirect(url_for("inicio"))

    finally:
        conexao.close()


# ==========================================
# HISTORICO DE MOVIMENTACOES
# ==========================================

@app.route("/movimentacoes")
def movimentacoes():

    conexao = conectar_banco()

    try:
        registros = conexao.execute("""
            SELECT
                m.id,
                p.sku,
                p.nome AS produto,
                m.tipo_operacao,
                m.quantidade,
                m.data_hora,
                m.observacao

            FROM movimentacoes m

            INNER JOIN produtos p
                ON m.produto_id = p.id

            ORDER BY m.data_hora DESC, m.id DESC
        """).fetchall()

    finally:
        conexao.close()

    return render_template(
        "movimentacoes.html",
        registros=registros
    )


# ==========================================
# REGISTRAR NOVA MOVIMENTACAO
# ==========================================

@app.route("/movimentacoes/nova", methods=["GET", "POST"])
def nova_movimentacao():

    conexao = conectar_banco()

    try:

        # Buscar produtos ativos para o formulario
        produtos = conexao.execute("""
            SELECT id, sku, nome, quantidade_estoque
            FROM produtos
            WHERE ativo = 1
            ORDER BY nome
        """).fetchall()

        # Quando o usuario abre a pagina
        if request.method == "GET":
            return render_template(
                "movimentacao_form.html",
                produtos=produtos
            )

        # Quando o usuario envia o formulario
        produto_id_texto = request.form.get("produto_id", "").strip()
        tipo_operacao = request.form.get("tipo_operacao", "").strip()
        quantidade_texto = request.form.get("quantidade", "").strip()
        observacao = request.form.get("observacao", "").strip()

        # Verificar se os campos obrigatorios foram preenchidos
        if not all([produto_id_texto, tipo_operacao, quantidade_texto]):
            flash("Preencha todos os campos obrigatorios.", "erro")
            return redirect(url_for("nova_movimentacao"))

        # Verificar o tipo de operacao
        if tipo_operacao not in ["Entrada", "Saída"]:
            flash("Tipo de operacao invalido.", "erro")
            return redirect(url_for("nova_movimentacao"))

        # Converter os dados para numeros inteiros
        try:
            produto_id = int(produto_id_texto)
            quantidade = int(quantidade_texto)

            if produto_id <= 0 or quantidade <= 0:
                raise ValueError

        except ValueError:
            flash("Informe um produto e uma quantidade valida.", "erro")
            return redirect(url_for("nova_movimentacao"))

        # Atualizar estoque e registrar historico
        with conexao:

            if tipo_operacao == "Entrada":

                resultado = conexao.execute("""
                    UPDATE produtos
                    SET quantidade_estoque = quantidade_estoque + ?
                    WHERE id = ? AND ativo = 1
                """, (quantidade, produto_id))

            else:

                resultado = conexao.execute("""
                    UPDATE produtos
                    SET quantidade_estoque = quantidade_estoque - ?
                    WHERE id = ?
                    AND ativo = 1
                    AND quantidade_estoque >= ?
                """, (quantidade, produto_id, quantidade))

            # Verificar se algum produto foi atualizado
            if resultado.rowcount == 0:

                flash(
                    "Produto nao encontrado ou estoque insuficiente.",
                    "erro"
                )

                return redirect(url_for("nova_movimentacao"))

            # Registrar a operacao no historico
            conexao.execute("""
                INSERT INTO movimentacoes (
                    produto_id,
                    tipo_operacao,
                    quantidade,
                    observacao
                )
                VALUES (?, ?, ?, ?)
            """, (
                produto_id,
                tipo_operacao,
                quantidade,
                observacao
            ))

        flash("Movimentacao registrada com sucesso!", "sucesso")

        return redirect(url_for("movimentacoes"))

    finally:
        conexao.close()


# ==========================================
# RELATORIOS DO ESTOQUE
# ==========================================

@app.route("/relatorios")
def relatorios():

    conexao = conectar_banco()

    try:
        total_produtos = conexao.execute("""
            SELECT COUNT(*)
            FROM produtos
            WHERE ativo = 1
        """).fetchone()[0]

        total_unidades = conexao.execute("""
            SELECT COALESCE(SUM(quantidade_estoque), 0)
            FROM produtos
            WHERE ativo = 1
        """).fetchone()[0]

        produtos_baixos = conexao.execute("""
            SELECT COUNT(*)
            FROM produtos
            WHERE ativo = 1
            AND quantidade_estoque < estoque_minimo
        """).fetchone()[0]

        total_entradas = conexao.execute("""
            SELECT COALESCE(SUM(quantidade), 0)
            FROM movimentacoes
            WHERE tipo_operacao = 'Entrada'
        """).fetchone()[0]

        total_saidas = conexao.execute("""
            SELECT COALESCE(SUM(quantidade), 0)
            FROM movimentacoes
            WHERE tipo_operacao = 'Saída'
        """).fetchone()[0]

        historico = conexao.execute("""
            SELECT
                p.sku,
                p.nome AS produto,
                m.tipo_operacao,
                m.quantidade,
                m.data_hora
            FROM movimentacoes m
            INNER JOIN produtos p
                ON m.produto_id = p.id
            ORDER BY m.data_hora DESC, m.id DESC
            LIMIT 20
        """).fetchall()

    finally:
        conexao.close()

    return render_template(
        "relatorios.html",
        total_produtos=total_produtos,
        total_unidades=total_unidades,
        produtos_baixos=produtos_baixos,
        total_entradas=total_entradas,
        total_saidas=total_saidas,
        historico=historico
    )


 
# ==========================================
# INICIAR A APLICACAO
# ==========================================

if __name__ == "__main__":
    app.run(debug=True)

