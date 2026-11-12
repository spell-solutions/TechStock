import re
from pathlib import Path

base = Path(r"C:\Users\Andressa\Downloads\TechStock-Manager")
idx_html = (base / "templates" / "index.html").read_text(encoding="utf-8")

m_start = re.search(r'(.*?<aside[^>]*>.*?)(<a\b[^>]*>.*?</a>)', idx_html, re.DOTALL)
m_aside_end = re.search(r'(</aside>\s*<main[^>]*>)', idx_html, re.DOTALL)
m_end = re.search(r'(</main>.*)', idx_html, re.DOTALL)

topo = m_start.group(1)
m_attrs = re.search(r'<a([^>]*)>', m_start.group(2))
raw_attrs = m_attrs.group(1) if m_attrs else ""
clean_attrs = re.sub(r'\s*href="[^"]*"', '', raw_attrs)
clean_attrs = re.sub(r'\bactive\b', '', clean_attrs).strip()

entre = idx_html[m_start.end():m_aside_end.start()]
fecha_nav = "</nav>\n" if "</nav>" in entre else ""
abre_main = fecha_nav + m_aside_end.group(1)
fecha_tudo = m_end.group(1)

def montar_pagina(titulo, ativo, conteudo_main):
    itens = [
        ("inicio", "Painel inicial"),
        ("pdv", "Abrir PDV (Vendas)"),
        ("listar_vendas", "Histórico Vendas"),
        ("movimentacoes", "Movimentações"),
        ("relatorios", "Relatórios"),
    ]
    links_html = []
    for rota, label in itens:
        attrs = clean_attrs
        if rota == ativo:
            if 'class="' in attrs:
                attrs = attrs.replace('class="', 'class="active ')
            else:
                attrs = (attrs + ' class="active"').strip()
        attr_f = f" {attrs}" if attrs else ""
        links_html.append(f'<a href="{{{{ url_for(\'{rota}\') }}}}"{attr_f}>{label}</a>')

    rodape_user = (
        '<div style="margin-top:auto; padding-top:14px; border-top:1px solid rgba(255,255,255,0.15); font-size:13px; color:#e2e8f0;">'
        '<div style="font-weight:bold;">{{ session.usuario_nome }}</div>'
        '<span style="display:inline-block; background:#2563eb; color:#fff; padding:2px 8px; border-radius:4px; font-size:11px; margin:6px 0;">{{ session.perfil_acesso }}</span><br>'
        '<a href="{{ url_for(\'logout\') }}" style="color:#fca5a5; text-decoration:none; font-weight:bold;">Sair</a>'
        '</div>'
    )
    head_ajustado = re.sub(r'<title>.*?</title>', f'<title>{titulo} - TechStock Manager</title>', topo, count=1, flags=re.DOTALL)
    return head_ajustado + "\n".join(links_html) + "\n" + rodape_user + "\n" + abre_main + "\n" + conteudo_main + "\n" + fecha_tudo

rel_body = """
<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:22px;">
    <div>
        <h1 style="margin:0 0 4px;">Relatórios Gerenciais</h1>
        <p style="margin:0; color:#64748b;">Indicadores consolidados de estoque e movimentações.</p>
    </div>
    <div style="display:flex; gap:10px; align-items:center;">
        <button onclick="window.print()" style="padding:8px 14px; background:#1e3a8a; color:#fff; border:none; border-radius:6px; cursor:pointer; font-weight:600;">Imprimir Relatório</button>
        <span style="background:#dcfce7; color:#166534; padding:6px 14px; border-radius:999px; font-size:0.8rem; font-weight:600;">Sistema online</span>
    </div>
</div>
<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(165px, 1fr)); gap:16px; margin-bottom:22px;">
    <div style="background:#fff; padding:18px; border-radius:10px; border:1px solid #e2e8f0;"><small style="color:#64748b; display:block; margin-bottom:6px;">Total de produtos</small><strong style="font-size:1.7rem;">{{ total_produtos }}</strong></div>
    <div style="background:#fff; padding:18px; border-radius:10px; border:1px solid #e2e8f0;"><small style="color:#64748b; display:block; margin-bottom:6px;">Unidades em estoque</small><strong style="font-size:1.7rem;">{{ total_unidades }}</strong></div>
    <div style="background:#fff; padding:18px; border-radius:10px; border:1px solid #e2e8f0;"><small style="color:#64748b; display:block; margin-bottom:6px;">Estoque baixo</small><strong style="font-size:1.7rem; color:#dc2626;">{{ produtos_baixos }}</strong></div>
    <div style="background:#fff; padding:18px; border-radius:10px; border:1px solid #e2e8f0;"><small style="color:#64748b; display:block; margin-bottom:6px;">Total de entradas</small><strong style="font-size:1.7rem; color:#16a34a;">{{ total_entradas }}</strong></div>
    <div style="background:#fff; padding:18px; border-radius:10px; border:1px solid #e2e8f0;"><small style="color:#64748b; display:block; margin-bottom:6px;">Total de saídas</small><strong style="font-size:1.7rem; color:#1d4ed8;">{{ total_saidas }}</strong></div>
</div>
<div style="background:#fff; padding:22px; border-radius:10px; border:1px solid #e2e8f0;">
    <h3 style="margin-top:0;">Últimas 20 Movimentações</h3>
    <table style="width:100%; border-collapse:collapse;">
        <thead><tr style="background:#f8fafc; border-bottom:1px solid #e2e8f0; text-align:left;"><th style="padding:10px;">SKU</th><th>Produto</th><th>Operação</th><th>Quantidade</th><th>Data e hora</th></tr></thead>
        <tbody>
            {% for item in historico %}
            <tr style="border-bottom:1px solid #e2e8f0;">
                <td style="padding:10px;">{{ item.sku }}</td>
                <td><strong>{{ item.produto }}</strong></td>
                <td><span style="padding:3px 10px; border-radius:999px; font-size:0.78rem; font-weight:600; background:{{ '#dcfce7' if item.tipo_operacao=='Entrada' else '#fee2e2' }}; color:{{ '#166534' if item.tipo_operacao=='Entrada' else '#991b1b' }};">{{ item.tipo_operacao }}</span></td>
                <td>{{ item.quantidade }}</td>
                <td>{{ item.data_hora }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
"""

pdv_body = """
<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:22px;">
    <div>
        <h1 style="margin:0 0 4px;">Frente de Caixa (PDV)</h1>
        <p style="margin:0; color:#64748b;">Registro de vendas multi-itens com baixa atômica no estoque.</p>
    </div>
    <span style="background:#dcfce7; color:#166534; padding:6px 14px; border-radius:999px; font-size:0.8rem; font-weight:600;">Sistema online</span>
</div>
<div id="alerta-erro" style="display:none; background:#fee2e2; border-left:5px solid #dc2626; color:#991b1b; padding:14px 16px; border-radius:6px; margin-bottom:20px; font-weight:600;"></div>
<div style="display:grid; grid-template-columns:1fr 1.35fr; gap:22px;">
    <div style="background:#fff; padding:22px; border-radius:10px; border:1px solid #e2e8f0;">
        <h3 style="margin-top:0;">1. Selecionar Produto / Licença</h3>
        <label style="display:block; font-weight:600; margin-bottom:6px;">Item disponível em estoque</label>
        <select id="produto-select" style="width:100%; padding:10px; border:1px solid #cbd5e1; border-radius:6px; margin-bottom:14px;">
            {% for p in produtos %}
            <option value="{{ p.id }}" data-nome="[{{ p.sku }}] {{ p.nome }}" data-preco="{{ p.preco_venda }}" data-estoque="{{ p.quantidade_estoque }}">[{{ p.sku }}] {{ p.nome }} — R$ {{ "%.2f"|format(p.preco_venda) }} (Saldo: {{ p.quantidade_estoque }})</option>
            {% endfor %}
        </select>
        <label style="display:block; font-weight:600; margin-bottom:6px;">Quantidade</label>
        <input type="number" id="qtd-input" value="1" min="1" style="width:100%; box-sizing:border-box; padding:10px; border:1px solid #cbd5e1; border-radius:6px; margin-bottom:16px;">
        <button type="button" onclick="adicionarItem()" style="width:100%; padding:11px; background:#1e3a8a; color:#fff; border:none; border-radius:6px; font-weight:600; cursor:pointer;">+ Adicionar ao Carrinho</button>
    </div>
    <div style="background:#fff; padding:22px; border-radius:10px; border:1px solid #e2e8f0;">
        <h3 style="margin-top:0;">2. Carrinho Multi-Itens & Checkout</h3>
        <table style="width:100%; border-collapse:collapse; margin-bottom:14px;">
            <thead><tr style="background:#f8fafc; border-bottom:1px solid #e2e8f0; text-align:left;"><th style="padding:8px;">Item</th><th>Qtd</th><th>Unit.</th><th>Subtotal</th><th></th></tr></thead>
            <tbody id="carrinho-body"></tbody>
        </table>
        <div style="text-align:right; font-size:1.25rem; font-weight:700; margin-bottom:16px;">Total Geral: R$ <span id="total-geral">0.00</span></div>
        <input type="text" id="cliente-nome" placeholder="Nome Completo ou Razão Social" style="width:100%; box-sizing:border-box; padding:10px; border:1px solid #cbd5e1; border-radius:6px; margin-bottom:10px;">
        <input type="text" id="cliente-doc" placeholder="CPF ou CNPJ" style="width:100%; box-sizing:border-box; padding:10px; border:1px solid #cbd5e1; border-radius:6px; margin-bottom:10px;">
        <select id="forma-pagamento" style="width:100%; padding:10px; border:1px solid #cbd5e1; border-radius:6px; margin-bottom:16px;">
            <option value="PIX">PIX Instantâneo</option>
            <option value="CARTAO_CREDITO">Cartão de Crédito</option>
            <option value="BOLETO_FATURADO">Boleto Faturado Corporativo</option>
        </select>
        <button type="button" onclick="finalizarCompra()" style="width:100%; padding:12px; background:#15803d; color:#fff; border:none; border-radius:6px; font-weight:600; cursor:pointer;">Confirmar Venda (Checkout ACID)</button>
    </div>
</div>
<script>
    let carrinho = [];
    function adicionarItem() {
        const sel = document.getElementById("produto-select");
        if (!sel.options.length) return;
        const opt = sel.options[sel.selectedIndex];
        const produto_id = parseInt(opt.value);
        const nome = opt.dataset.nome;
        const preco = parseFloat(opt.dataset.preco);
        const estoque = parseInt(opt.dataset.estoque);
        const quantidade = parseInt(document.getElementById("qtd-input").value);
        if (!quantidade || quantidade <= 0) return;
        const ex = carrinho.find(i => i.produto_id === produto_id);
        if (ex) ex.quantidade += quantidade; else carrinho.push({ produto_id, nome, preco, estoque, quantidade });
        renderCarrinho();
    }
    function removerItem(idx) { carrinho.splice(idx, 1); renderCarrinho(); }
    function renderCarrinho() {
        const tbody = document.getElementById("carrinho-body");
        tbody.innerHTML = "";
        let total = 0;
        carrinho.forEach((item, idx) => {
            const sub = item.preco * item.quantidade;
            total += sub;
            const semSaldo = item.quantidade > item.estoque;
            tbody.innerHTML += `<tr style="border-bottom:1px solid #e2e8f0;"><td style="padding:8px; ${semSaldo ? 'color:#dc2626; font-weight:bold;' : ''}">${item.nome} ${semSaldo ? '(Saldo: ' + item.estoque + ')' : ''}</td><td>${item.quantidade}</td><td>R$ ${item.preco.toFixed(2)}</td><td>R$ ${sub.toFixed(2)}</td><td><button type="button" onclick="removerItem(${idx})" style="color:#dc2626; border:none; background:none; cursor:pointer; font-weight:bold;">✕</button></td></tr>`;
        });
        document.getElementById("total-geral").innerText = total.toFixed(2);
    }
    async function finalizarCompra() {
        const alerta = document.getElementById("alerta-erro");
        alerta.style.display = "none";
        const resp = await fetch("{{ url_for('finalizar_venda') }}", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                cliente_nome: document.getElementById("cliente-nome").value,
                cliente_documento: document.getElementById("cliente-doc").value,
                forma_pagamento: document.getElementById("forma-pagamento").value,
                itens: carrinho.map(i => ({ produto_id: i.produto_id, quantidade: i.quantidade }))
            })
        });
        const data = await resp.json();
        if (data.sucesso) window.location.href = data.redirect_url;
        else { alerta.innerText = "ERRO NA TRANSAÇÃO (ROLLBACK EXECUTADO): " + data.erro; alerta.style.display = "block"; window.scrollTo({ top: 0, behavior: "smooth" }); }
    }
</script>
"""

vendas_body = """
<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:22px;">
    <div>
        <h1 style="margin:0 0 4px;">Histórico de Vendas & Faturamento</h1>
        <p style="margin:0; color:#64748b;">Pedidos faturados no PDV, recibos oficiais e estornos.</p>
    </div>
    <span style="background:#dcfce7; color:#166534; padding:6px 14px; border-radius:999px; font-size:0.8rem; font-weight:600;">Sistema online</span>
</div>
{% with messages = get_flashed_messages(with_categories=true) %}
  {% for cat, msg in messages %}
    <div style="padding:12px 16px; margin-bottom:18px; border-radius:6px; background:{{ '#fee2e2' if cat=='erro' else '#dcfce7' }}; color:{{ '#991b1b' if cat=='erro' else '#166534' }}; font-weight:600;">{{ msg }}</div>
  {% endfor %}
{% endwith %}
<div style="background:#fff; padding:22px; border-radius:10px; border:1px solid #e2e8f0;">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
        <h3 style="margin:0;">Pedidos Registrados</h3>
        <a href="{{ url_for('pdv') }}" style="padding:8px 14px; background:#1e3a8a; color:#fff; text-decoration:none; border-radius:6px; font-size:0.85rem; font-weight:600;">+ Nova Venda (PDV)</a>
    </div>
    <table style="width:100%; border-collapse:collapse;">
        <thead><tr style="background:#f8fafc; border-bottom:1px solid #e2e8f0; text-align:left;"><th style="padding:10px;">Pedido</th><th>Data / Hora</th><th>Cliente</th><th>Pagamento</th><th>Operador</th><th>Total</th><th>Status</th><th>Ações</th></tr></thead>
        <tbody>
            {% for v in vendas %}
            <tr style="border-bottom:1px solid #e2e8f0;">
                <td style="padding:10px;"><strong>{{ v.numero_pedido }}</strong></td>
                <td>{{ v.data_hora }}</td>
                <td>{{ v.cliente_nome }}</td>
                <td>{{ v.forma_pagamento }}</td>
                <td>{{ v.operador_nome }}</td>
                <td><strong>R$ {{ "%.2f"|format(v.valor_total) }}</strong></td>
                <td><span style="padding:3px 9px; border-radius:999px; font-size:0.78rem; font-weight:600; background:{{ '#dcfce7' if v.status_venda=='CONCLUIDA' else '#fee2e2' }}; color:{{ '#166534' if v.status_venda=='CONCLUIDA' else '#991b1b' }};">{{ v.status_venda }}</span></td>
                <td style="display:flex; gap:8px; padding:10px 0;">
                    <a href="{{ url_for('recibo_venda', venda_id=v.id) }}" style="padding:5px 10px; background:#1e3a8a; color:#fff; text-decoration:none; border-radius:6px; font-size:0.8rem; font-weight:600;">Recibo</a>
                    {% if session.perfil_acesso == 'GERENTE' and v.status_venda == 'CONCLUIDA' %}
                    <form method="POST" action="{{ url_for('cancelar_venda', venda_id=v.id) }}" onsubmit="return confirm('Confirmar cancelamento e estorno de estoque?');" style="margin:0;">
                        <button type="submit" style="padding:5px 10px; background:#dc2626; color:#fff; border:none; border-radius:6px; cursor:pointer; font-size:0.8rem; font-weight:600;">Cancelar</button>
                    </form>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
"""

(base / "templates" / "relatorios.html").write_text(montar_pagina("Relatórios", "relatorios", rel_body), encoding="utf-8")
(base / "templates" / "pdv.html").write_text(montar_pagina("Abrir PDV (Vendas)", "pdv", pdv_body), encoding="utf-8")
(base / "templates" / "vendas.html").write_text(montar_pagina("Histórico Vendas", "listar_vendas", vendas_body), encoding="utf-8")
print("TELAS_PADRONIZADAS_COM_SUCESSO")