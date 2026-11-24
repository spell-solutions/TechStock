# TechStock Manager

## 1. Apresentação do Projeto

O TechStock Manager é um sistema web desenvolvido para a empresa TechStore Informática, com o objetivo de facilitar o gerenciamento de produtos, componentes de hardware, periféricos e licenças de software.

O sistema permite controlar o cadastro de produtos, fornecedores, categorias, entradas e saídas de estoque, além de acompanhar alertas de reposição.

## 2. Tecnologias Utilizadas

- Python 3
- Flask
- SQLite
- HTML5
- CSS3

## 3. Funcionalidades

- Cadastro de produtos e licenças.
- Cadastro e associação de categorias e fornecedores.
- Consulta e pesquisa de produtos.
- Edição e desativação de produtos.
- Registro de entradas e saídas de estoque.
- Histórico de movimentações.
- Bloqueio de saídas com quantidade superior ao estoque disponível.
- Dashboard com indicadores e alertas de estoque mínimo.
- Relatórios de estoque.
- Login com perfis de operador e gerente.
- Carrinho multi-itens com checkout atômico, rollback e auditoria de estoque.
- Recibo imprimível e histórico de vendas com cancelamento controlado.
- Relatório gerencial de vendas, faturamento e movimentações.

## 4. Estrutura do Projeto

```text
TechStock-main/
│
├── app.py
├── techstock.db
├── database.sql
├── migration_v2.sql
├── seed_data.py
├── seed_v2.py
├── setup_db.py
├── README.md
├── static/
├── templates/
└── tests/
    └── test_app.py
```

## 5. Requisitos para Execução

- Python 3 instalado.
- Flask instalado.
- Visual Studio Code ou outro editor de código.
- Navegador de internet.

## 6. Instalação e Configuração

Abra o terminal na pasta do projeto e execute:

```bash
python -m pip install Flask
```

## 7. Configuração do Banco de Dados

O projeto utiliza o banco de dados SQLite.

O arquivo `database.sql` cria as quatro tabelas do inventário, seus índices e uma carga de demonstração idempotente (4 categorias, 3 fornecedores e 6 produtos).
Em uma instalação nova, prepare o banco e depois crie as tabelas e usuários do PDV:

```bash
python setup_db.py
python seed_v2.py
```

Os scripts usam `CREATE TABLE IF NOT EXISTS` e `INSERT OR IGNORE`, mas faça backup antes de aplicá-los a um banco com dados importantes. O arquivo `migration_v2.sql` define `Usuarios`, `Vendas` e `Itens_Venda`; `seed_v2.py` também cadastra uma venda multi-itens de demonstração, com baixa de estoque e auditoria, quando ainda não há vendas.

No banco de demonstração, use `operador@techstore.com` / `operador123` ou `gerente@techstore.com` / `gerente123`. Essas credenciais são apenas para desenvolvimento local.

## 8. Execução da Aplicação

No terminal, dentro da pasta do projeto, execute:

```bash
python app.py
```

Depois, abra o navegador e acesse:

http://127.0.0.1:5000/

Para implantação, defina `TECHSTOCK_SECRET_KEY` no ambiente antes de iniciar o servidor. O valor de desenvolvimento padrão não deve ser usado em produção.

## 9. Roteiro de Demonstração

1. Entre como operador e confira o painel, os nomes de categorias/fornecedores e os alertas de reposição.
2. No PDV, adicione dois produtos, informe os dados do cliente e finalize a venda. O sistema deve abrir o recibo imprimível.
3. Tente vender uma quantidade acima do saldo. A interface deve mostrar o motivo e a venda, os itens, o saldo e o livro-razão devem permanecer inalterados.
4. Entre como gerente para cadastrar/editar/desativar produtos, registrar entrada/saída, consultar o histórico, abrir relatórios e cancelar a venda de demonstração.
5. Confira o esquema e os registros pelo terminal, conforme o exemplo abaixo.

Para inspecionar as tabelas do banco em PowerShell sem alterar dados:

```powershell
@'
import sqlite3

conn = sqlite3.connect("file:techstock.db?mode=ro", uri=True)
for (table,) in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
):
    count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    print(f"{table}: {count} registros")
conn.close()
'@ | python -
```

Para conferir a última venda, seus itens e o livro-razão:

```powershell
@'
import sqlite3

conn = sqlite3.connect("file:techstock.db?mode=ro", uri=True)
print("Vendas e itens:")
for row in conn.execute("""
    SELECT v.numero_pedido, p.nome, i.quantidade_vendida,
           i.preco_unitario_praticado, i.subtotal_item
    FROM Vendas v
    INNER JOIN Itens_Venda i ON i.venda_id = v.id
    INNER JOIN Produtos p ON p.id = i.produto_id
    ORDER BY v.id DESC
    LIMIT 10
"""):
    print(row)

print("Movimentações recentes:")
for row in conn.execute("""
    SELECT p.sku, m.tipo_operacao, m.quantidade, m.observacao
    FROM Movimentacoes m
    INNER JOIN Produtos p ON p.id = m.produto_id
    ORDER BY m.id DESC
    LIMIT 10
"""):
    print(row)
conn.close()
'@ | python -
```

Para executar os testes automatizados:

```bash
python -m unittest discover -s tests -v
```

## 10. Banco de Dados e Integridade

O banco possui sete entidades: Categorias, Fornecedores, Produtos, Movimentacoes, Usuarios, Vendas e Itens_Venda. As operações de venda, movimentação de estoque e cancelamento usam transações explícitas para manter os saldos e o histórico consistentes.

## 11. Objetivo Final

O TechStock Manager busca oferecer uma solução simples e organizada para o controle de inventário, reduzindo inconsistências de estoque e facilitando o acompanhamento das operações da empresa TechStore Informática.
