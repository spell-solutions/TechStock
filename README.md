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

## 4. Estrutura do Projeto

```text
TechStock-Manager/
│
├── app.py
├── techstock.db
├── database.sql
├── README.md
│
├── templates/
│   ├── index.html
│   ├── produto_form.html
│   ├── editar_produto.html
│   ├── movimentacoes.html
│   └── movimentacao_form.html
│
└── static/
    └── style.css
```

## 5. Requisitos para Execução

- Python 3 instalado.
- Flask instalado.
- Visual Studio Code ou outro editor de código.
- Navegador de internet.

## 6. Instalação e Configuração

Abra o terminal na pasta do projeto e execute:

```bash
pip install flask
```

## 7. Configuração do Banco de Dados

O projeto utiliza o banco de dados SQLite.

O arquivo `database.sql` contém os comandos para criação das tabelas, definição das chaves primárias e estrangeiras e inserção dos dados iniciais para testes.

Para criar o banco a partir desse arquivo, caso necessário, execute:

```bash
python -c "import sqlite3; c=sqlite3.connect('techstock.db'); c.executescript(open('database.sql', encoding='utf-8').read()); c.close()"
```

**Atenção:** execute esse comando somente quando for criar o banco inicial. Não o execute sobre um banco que já contém dados importantes.

## 8. Execução da Aplicação

No terminal, dentro da pasta do projeto, execute:

```bash
python app.py
```

Depois, abra o navegador e acesse:

http://127.0.0.1:5000/

## 9. Banco de Dados e Integridade

O banco de dados possui quatro entidades principais:

- Categorias;
- Fornecedores;
- Produtos;
- Movimentações.

Foram utilizadas chaves primárias, chaves estrangeiras e restrições de integridade para garantir a consistência dos dados e evitar operações inválidas no estoque.

## 10. Objetivo Final

O TechStock Manager busca oferecer uma solução simples e organizada para o controle de inventário, reduzindo inconsistências de estoque e facilitando o acompanhamento das operações da empresa TechStore Informática.
