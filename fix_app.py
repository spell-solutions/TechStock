from pathlib import Path
import re

p = Path("app.py")
txt = p.read_text(encoding="utf-8")

if "import re" not in txt:
    txt = "import re\n" + txt

novo_hook = """@app.after_request
def injetar_barra_sessao(response):
    if response.status_code == 200 and "text/html" in response.content_type and "usuario_id" in session and request.endpoint not in ("login", "pdv", "recibo_venda", "listar_vendas", "relatorios"):
        html = response.get_data(as_text=True)
        m = re.search(r'<a([^>]*)>\\s*Movimentações\\s*</a>', html)
        attrs = m.group(1) if m else ' style="display:block; padding:10px 14px; color:#cbd5e1; text-decoration:none; border-radius:6px; margin-bottom:4px;"'
        attrs = re.sub(r'href="[^"]*"', '', attrs).replace('active', '')
        links_pdv = f'\\n<a href="{url_for("pdv")}"{attrs}>Abrir PDV (Vendas)</a>\\n<a href="{url_for("listar_vendas")}"{attrs}>Histórico Vendas</a>'
        if "Painel inicial</a>" in html and "Abrir PDV (Vendas)" not in html:
            html = html.replace("Painel inicial</a>", "Painel inicial</a>" + links_pdv, 1)
        rodape = f'<div style="margin-top:auto; padding-top:14px; border-top:1px solid rgba(255,255,255,0.15); font-size:13px; color:#e2e8f0;"><div style="font-weight:bold;">{session.get("usuario_nome")}</div><span style="display:inline-block; background:#2563eb; color:#fff; padding:2px 8px; border-radius:4px; font-size:11px; margin:6px 0;">{session.get("perfil_acesso")}</span><br><a href="{url_for("logout")}" style="color:#fca5a5; text-decoration:none; font-weight:bold;">Sair</a></div>'
        if "</aside>" in html and "Sair</a>" not in html:
            html = html.replace("</aside>", rodape + "</aside>", 1)
        response.set_data(html)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


"""

inicio = txt.index("@app.after_request")
fim = txt.index('@app.route("/login"')
txt = txt[:inicio] + novo_hook + txt[fim:]
p.write_text(txt, encoding="utf-8")
print("APP_ATUALIZADO_COM_SUCESSO")