
-- ==========================================
-- TECHSTOCK MANAGER
-- CRIACAO DAS 4 TABELAS DO BANCO DE DADOS
-- ==========================================

PRAGMA foreign_keys = ON;

-- 1. TABELA DE CATEGORIAS
CREATE TABLE IF NOT EXISTS categorias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL COLLATE NOCASE UNIQUE,
    descricao TEXT
);

-- 2. TABELA DE FORNECEDORES
CREATE TABLE IF NOT EXISTS fornecedores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    razao_social TEXT NOT NULL,
    cnpj TEXT NOT NULL UNIQUE,
    telefone TEXT NOT NULL,
    email TEXT NOT NULL
);

-- 3. TABELA DE PRODUTOS
CREATE TABLE IF NOT EXISTS produtos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL UNIQUE,
    nome TEXT NOT NULL,
    fabricante TEXT NOT NULL,
    classificacao TEXT NOT NULL
        CHECK (classificacao IN ('Hardware', 'Software', 'Periférico')),
    especificacao TEXT,
    modalidade_licenca TEXT,
    preco_venda REAL NOT NULL CHECK (preco_venda > 0),
    quantidade_estoque INTEGER NOT NULL DEFAULT 0
        CHECK (quantidade_estoque >= 0),
    estoque_minimo INTEGER NOT NULL DEFAULT 0
        CHECK (estoque_minimo >= 0),
    localizacao TEXT,
    categoria_id INTEGER NOT NULL,
    fornecedor_id INTEGER NOT NULL,
    ativo INTEGER NOT NULL DEFAULT 1
        CHECK (ativo IN (0, 1)),
    FOREIGN KEY (categoria_id)
        REFERENCES categorias(id)
        ON DELETE RESTRICT,
    FOREIGN KEY (fornecedor_id)
        REFERENCES fornecedores(id)
        ON DELETE RESTRICT
);

-- 4. TABELA DE MOVIMENTACOES
CREATE TABLE IF NOT EXISTS movimentacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    produto_id INTEGER NOT NULL,
    tipo_operacao TEXT NOT NULL
        CHECK (tipo_operacao IN ('Entrada', 'Saída')),
    quantidade INTEGER NOT NULL CHECK (quantidade > 0),
    data_hora TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    observacao TEXT,
    FOREIGN KEY (produto_id)
        REFERENCES produtos(id)
        ON DELETE RESTRICT
);

-- INDICES PARA MELHORAR AS CONSULTAS
CREATE INDEX IF NOT EXISTS idx_produtos_categoria
ON produtos(categoria_id);

CREATE INDEX IF NOT EXISTS idx_produtos_fornecedor
ON produtos(fornecedor_id);

CREATE INDEX IF NOT EXISTS idx_movimentacoes_produto
ON movimentacoes(produto_id);
