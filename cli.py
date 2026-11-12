import sqlite3
import uuid
import hashlib
from datetime import datetime
from pathlib import Path
from werkzeug.security import check_password_hash

BANCO = Path(__file__).resolve().parent / "techstock.db"


def conectar(manual=False):
    conn = sqlite3.connect(BANCO, isolation_level=None if manual else "")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def autenticar():
    print("=" * 60)
    print("   TECHSTORE CORPORATIVO - SISTEMA DE VENDAS & ESTOQUE (CLI)")
    print("=" * 60)
    while True:
        email = input("\nE-mail corporativo: ").strip().lower()
        senha = input("Senha: ").strip()

        conn = conectar()
        try:
            user = conn.execute(
                "SELECT * FROM Usuarios WHERE email = ? AND status = 'ATIVO'",
                (email,),
            ).fetchone()
        finally:
            conn.close()

        if user and check_password_hash(user["senha_hash"], senha):
            print(f"\n[OK] Login realizado! Bem-vindo(a), {user['nome_completo']} [{user['perfil_acesso']}]")
            return dict(user)
        print("[ERRO] E-mail ou senha inválidos, ou usuário inativo. Tente novamente.")


def listar_catalogo():
    conn = conectar()
    try:
        produtos = conn.execute(
            "SELECT id, sku, nome, classificacao, preco_venda, quantidade_estoque, estoque_minimo FROM produtos WHERE ativo = 1 ORDER BY id"
        ).fetchall()
    finally:
        conn.close()

    print("\n" + "-" * 78)
    print(f"{'ID':<4} | {'SKU':<14} | {'PRODUTO':<32} | {'PREÇO':<10} | {'ESTOQUE':<7}")
    print("-" * 78)
    for p in produtos:
        alerta = " (!)" if p["quantidade_estoque"] < p["estoque_minimo"] else ""
        print(
            f"{p['id']:<4} | {p['sku']:<14} | {p['nome'][:32]:<32} | R$ {p['preco_venda']:>6.2f} | {p['quantidade_estoque']}{alerta}"
        )
    print("-" * 78)


def realizar_venda(usuario):
    listar_catalogo()
    carrinho = []
    print("\n--- MONTAGEM DO CARRINHO MULTI-ITENS ---")
    while True:
        id_str = input("Digite o ID do produto (ou ENTER para ir ao pagamento): ").strip()
        if not id_str:
            break
        if not id_str.isdigit():
            print("[AVISO] Informe um ID numérico válido.")
            continue
        qtd_str = input("Quantidade desejada: ").strip()
        if not qtd_str.isdigit() or int(qtd_str) <= 0:
            print("[AVISO] Quantidade deve ser maior que zero.")
            continue
        carrinho.append({"produto_id": int(id_str), "quantidade": int(qtd_str)})
        print(f"  -> Item ID {id_str} (qtd: {qtd_str}) adicionado ao carrinho.")

    if not carrinho:
        print("[CANCELADO] Nenhum item adicionado.")
        return

    cliente_nome = input("\nNome Completo ou Razão Social do Cliente: ").strip()
    cliente_doc = input("CPF ou CNPJ: ").strip()
    print("Forma de Pagamento: [1] PIX  |  [2] CARTAO_CREDITO  |  [3] BOLETO_FATURADO")
    op_pag = input("Escolha (1/2/3): ").strip()
    mapa_pag = {"1": "PIX", "2": "CARTAO_CREDITO", "3": "BOLETO_FATURADO"}
    forma_pagamento = mapa_pag.get(op_pag, "")

    if not cliente_nome or not cliente_doc or not forma_pagamento:
        print("[ERRO] Dados do cliente ou forma de pagamento inválidos.")
        return

    conn = conectar(manual=True)
    try:
        conn.execute("BEGIN IMMEDIATE;")
        qtd_agrupada = {}
        for item in carrinho:
            qtd_agrupada[item["produto_id"]] = qtd_agrupada.get(item["produto_id"], 0) + item["quantidade"]

        itens_validados = []
        valor_total = 0.0

        for pid, qtd in qtd_agrupada.items():
            prod = conn.execute(
                "SELECT id, sku, nome, preco_venda, quantidade_estoque FROM produtos WHERE id = ? AND ativo = 1",
                (pid,),
            ).fetchone()
            if not prod:
                raise ValueError(f"Produto ID {pid} não existe no catálogo.")
            if prod["quantidade_estoque"] < qtd:
                raise ValueError(
                    f"Estoque insuficiente para '{prod['nome']}' (SKU {prod['sku']}). "
                    f"Disponível: {prod['quantidade_estoque']} | Solicitado: {qtd}."
                )
            preco = float(prod["preco_venda"])
            subtotal = round(preco * qtd, 2)
            valor_total = round(valor_total + subtotal, 2)
            itens_validados.append(
                {"produto_id": pid, "sku": prod["sku"], "nome": prod["nome"], "qtd": qtd, "preco": preco, "subtotal": subtotal}
            )

        numero_pedido = f"PED-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cur = conn.execute(
            """
            INSERT INTO Vendas (numero_pedido, data_hora, cliente_nome, cliente_documento, forma_pagamento, valor_total, status_venda, usuario_id)
            VALUES (?, ?, ?, ?, ?, ?, 'CONCLUIDA', ?)
            """,
            (numero_pedido, agora, cliente_nome, cliente_doc, forma_pagamento, valor_total, usuario["id"]),
        )
        venda_id = cur.lastrowid

        for iv in itens_validados:
            conn.execute(
                "INSERT INTO Itens_Venda (venda_id, produto_id, quantidade_vendida, preco_unitario_praticado, subtotal_item) VALUES (?, ?, ?, ?, ?)",
                (venda_id, iv["produto_id"], iv["qtd"], iv["preco"], iv["subtotal"]),
            )
            conn.execute(
                "UPDATE produtos SET quantidade_estoque = quantidade_estoque - ? WHERE id = ?",
                (iv["qtd"], iv["produto_id"]),
            )
            conn.execute(
                "INSERT INTO movimentacoes (produto_id, tipo_operacao, quantidade, data_hora, observacao) VALUES (?, 'Saída', ?, ?, ?)",
                (iv["produto_id"], iv["qtd"], agora, f"Venda CLI {numero_pedido} | Operador: {usuario['nome_completo']}"),
            )

        conn.execute("COMMIT;")

        chave = hashlib.sha256(f"{numero_pedido}|{cliente_doc}|{valor_total}|{agora}".encode()).hexdigest()[:24].upper()
        print("\n" + "=" * 60)
        print(f"   RECIBO OFICIAL DE VENDA - {numero_pedido}")
        print("=" * 60)
        print(f"Data/Hora: {agora} | Operador: {usuario['nome_completo']}")
        print(f"Cliente:   {cliente_nome} ({cliente_doc})")
        print(f"Pagamento: {forma_pagamento}")
        print("-" * 60)
        for iv in itens_validados:
            print(f" - [{iv['sku']}] {iv['nome']} | {iv['qtd']}x R$ {iv['preco']:.2f} = R$ {iv['subtotal']:.2f}")
        print("-" * 60)
        print(f"TOTAL FATURADO: R$ {valor_total:.2f}")
        print(f"CHAVE SHA-256:  {chave}")
        print("=" * 60)

    except Exception as e:
        if conn.in_transaction:
            conn.execute("ROLLBACK;")
        print(f"\n[ROLLBACK ACID EXECUTADO] Transação abortada sem alterar estoque: {e}")
    finally:
        conn.close()


def historico_vendas():
    conn = conectar()
    try:
        vendas = conn.execute(
            "SELECT v.id, v.numero_pedido, v.data_hora, v.cliente_nome, v.forma_pagamento, v.valor_total, v.status_venda, u.nome_completo AS operador FROM Vendas v INNER JOIN Usuarios u ON v.usuario_id = u.id ORDER BY v.id DESC"
        ).fetchall()
    finally:
        conn.close()

    print("\n" + "-" * 92)
    print(f"{'ID':<3} | {'PEDIDO':<20} | {'CLIENTE':<24} | {'TOTAL':<10} | {'STATUS':<10} | {'OPERADOR'}")
    print("-" * 92)
    for v in vendas:
        print(
            f"{v['id']:<3} | {v['numero_pedido']:<20} | {v['cliente_nome'][:24]:<24} | R$ {v['valor_total']:>6.2f} | {v['status_venda']:<10} | {v['operador']}"
        )
    print("-" * 92)


def cancelar_venda(usuario):
    if usuario["perfil_acesso"] != "GERENTE":
        print("\n[403 ACESSO NEGADO - RBAC] Seu perfil é OPERADOR. Apenas GERENTE pode cancelar vendas.")
        return

    historico_vendas()
    vid = input("\nDigite o ID da venda para cancelar (ou ENTER para voltar): ").strip()
    if not vid.isdigit():
        return

    conn = conectar(manual=True)
    try:
        conn.execute("BEGIN IMMEDIATE;")
        venda = conn.execute("SELECT * FROM Vendas WHERE id = ?", (int(vid),)).fetchone()
        if not venda or venda["status_venda"] == "CANCELADA":
            raise ValueError("Venda não encontrada ou já cancelada.")

        itens = conn.execute("SELECT * FROM Itens_Venda WHERE venda_id = ?", (int(vid),)).fetchall()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for item in itens:
            conn.execute(
                "UPDATE produtos SET quantidade_estoque = quantidade_estoque + ? WHERE id = ?",
                (item["quantidade_vendida"], item["produto_id"]),
            )
            conn.execute(
                "INSERT INTO movimentacoes (produto_id, tipo_operacao, quantidade, data_hora, observacao) VALUES (?, 'Entrada', ?, ?, ?)",
                (item["produto_id"], item["quantidade_vendida"], agora, f"Estorno CLI {venda['numero_pedido']} | Gerente: {usuario['nome_completo']}"),
            )
        conn.execute("UPDATE Vendas SET status_venda = 'CANCELADA' WHERE id = ?", (int(vid),))
        conn.execute("COMMIT;")
        print(f"\n[SUCESSO] Pedido {venda['numero_pedido']} cancelado e estoque estornado!")
    except Exception as e:
        if conn.in_transaction:
            conn.execute("ROLLBACK;")
        print(f"\n[ERRO] {e}")
    finally:
        conn.close()


def relatorio_gerencial(usuario):
    if usuario["perfil_acesso"] != "GERENTE":
        print("\n[403 ACESSO NEGADO - RBAC] Seu perfil é OPERADOR. Relatórios gerenciais exigem perfil GERENTE.")
        return

    conn = conectar()
    try:
        tot_prod = conn.execute("SELECT COUNT(*) FROM produtos WHERE ativo = 1").fetchone()[0]
        tot_unid = conn.execute("SELECT COALESCE(SUM(quantidade_estoque), 0) FROM produtos WHERE ativo = 1").fetchone()[0]
        tot_vendas = conn.execute("SELECT COUNT(*), COALESCE(SUM(valor_total), 0) FROM Vendas WHERE status_venda = 'CONCLUIDA'").fetchone()
    finally:
        conn.close()

    print("\n" + "=" * 50)
    print("   RELATÓRIO GERENCIAL CONSOLIDADO (GERENTE)")
    print("=" * 50)
    print(f"Produtos Ativos no Catálogo:  {tot_prod}")
    print(f"Unidades Totais em Estoque:   {tot_unid}")
    print(f"Vendas Concluídas:            {tot_vendas[0]}")
    print(f"Faturamento Bruto Total:      R$ {tot_vendas[1]:.2f}")
    print("=" * 50)


def main():
    while True:
        usuario = autenticar()
        while True:
            print(f"\n--- MENU PRINCIPAL ({usuario['nome_completo']} | {usuario['perfil_acesso']}) ---")
            print("[1] Consultar Catálogo / Estoque")
            print("[2] Realizar Venda no PDV (Checkout ACID)")
            print("[3] Consultar Histórico de Vendas")
            print("[4] Cancelar Venda e Estornar Estoque (Somente GERENTE)")
            print("[5] Relatório Gerencial Consolidado (Somente GERENTE)")
            print("[0] Sair / Trocar de Usuário")

            opcao = input("Escolha uma opção: ").strip()
            if opcao == "1":
                listar_catalogo()
            elif opcao == "2":
                realizar_venda(usuario)
            elif opcao == "3":
                historico_vendas()
            elif opcao == "4":
                cancelar_venda(usuario)
            elif opcao == "5":
                relatorio_gerencial(usuario)
            elif opcao == "0":
                print("\nSessão encerrada.\n")
                break
            else:
                print("[AVISO] Opção inválida.")


if __name__ == "__main__":
    main()