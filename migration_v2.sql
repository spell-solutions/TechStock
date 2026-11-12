PRAGMA foreign_keys = ON;

-- 1. Tabela de Usuários (Operadores e Gerência)
CREATE TABLE IF NOT EXISTS Usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome_completo TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    senha_hash TEXT NOT NULL,
    perfil_acesso TEXT NOT NULL CHECK (perfil_acesso IN ('OPERADOR', 'GERENTE')),
    status TEXT NOT NULL DEFAULT 'ATIVO' CHECK (status IN ('ATIVO', 'INATIVO'))
);

-- 2. Tabela de Vendas (Cabeçalho da Transação)
CREATE TABLE IF NOT EXISTS Vendas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_pedido TEXT NOT NULL UNIQUE,
    data_hora DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    cliente_nome TEXT NOT NULL,
    cliente_documento TEXT NOT NULL,
    forma_pagamento TEXT NOT NULL CHECK (forma_pagamento IN ('PIX', 'CARTAO_CREDITO', 'BOLETO_FATURADO')),
    valor_total REAL NOT NULL CHECK (valor_total >= 0),
    status_venda TEXT NOT NULL DEFAULT 'CONCLUIDA' CHECK (status_venda IN ('CONCLUIDA', 'CANCELADA')),
    usuario_id INTEGER NOT NULL,
    FOREIGN KEY (usuario_id) REFERENCES Usuarios(id)
);

-- 3. Tabela de Itens_Venda (Composição do Carrinho)
CREATE TABLE IF NOT EXISTS Itens_Venda (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venda_id INTEGER NOT NULL,
    produto_id INTEGER NOT NULL,
    quantidade_vendida INTEGER NOT NULL CHECK (quantidade_vendida > 0),
    preco_unitario_praticado REAL NOT NULL CHECK (preco_unitario_praticado > 0),
    subtotal_item REAL NOT NULL CHECK (subtotal_item > 0),
    FOREIGN KEY (venda_id) REFERENCES Vendas(id),
    FOREIGN KEY (produto_id) REFERENCES Produtos(id)
);