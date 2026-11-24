
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

-- CARGA INICIAL DE DEMONSTRACAO (reexecutavel sem duplicar SKUs/CNPJs)
INSERT OR IGNORE INTO categorias (nome, descricao) VALUES
('Hardware', 'Pecas internas de computadores'),
('Software', 'Programas e licencas'),
('Periféricos', 'Acessorios de computadores'),
('Armazenamento', 'Dispositivos para guardar dados');

INSERT OR IGNORE INTO fornecedores (razao_social, cnpj, telefone, email) VALUES
('Tech Distribuidora LTDA', '00000000000101', '(62) 3000-1000', 'tech@exemplo.com'),
('Info Center Comercial LTDA', '00000000000102', '(62) 3000-2000', 'info@exemplo.com'),
('Digital Solutions LTDA', '00000000000103', '(62) 3000-3000', 'digital@exemplo.com');

INSERT OR IGNORE INTO produtos (
    sku, nome, fabricante, classificacao, especificacao, modalidade_licenca,
    preco_venda, quantidade_estoque, estoque_minimo, localizacao,
    categoria_id, fornecedor_id
)
SELECT 'RAM001', 'Memoria RAM 16GB', 'Kingston', 'Hardware', 'DDR4 16GB', NULL,
       250.00, 15, 5, 'Prateleira A1', c.id, f.id
FROM categorias c JOIN fornecedores f ON f.cnpj = '00000000000101'
WHERE c.nome = 'Hardware';

INSERT OR IGNORE INTO produtos (
    sku, nome, fabricante, classificacao, especificacao, modalidade_licenca,
    preco_venda, quantidade_estoque, estoque_minimo, localizacao,
    categoria_id, fornecedor_id
)
SELECT 'SSD001', 'SSD 480GB', 'Kingston', 'Hardware', 'SSD SATA 480GB', NULL,
       320.00, 8, 5, 'Prateleira A2', c.id, f.id
FROM categorias c JOIN fornecedores f ON f.cnpj = '00000000000101'
WHERE c.nome = 'Armazenamento';

INSERT OR IGNORE INTO produtos (
    sku, nome, fabricante, classificacao, especificacao, modalidade_licenca,
    preco_venda, quantidade_estoque, estoque_minimo, localizacao,
    categoria_id, fornecedor_id
)
SELECT 'CPU001', 'Processador Ryzen 5', 'AMD', 'Hardware', 'Ryzen 5 5600', NULL,
       850.00, 10, 3, 'Prateleira A3', c.id, f.id
FROM categorias c JOIN fornecedores f ON f.cnpj = '00000000000102'
WHERE c.nome = 'Hardware';

INSERT OR IGNORE INTO produtos (
    sku, nome, fabricante, classificacao, especificacao, modalidade_licenca,
    preco_venda, quantidade_estoque, estoque_minimo, localizacao,
    categoria_id, fornecedor_id
)
SELECT 'MON001', 'Monitor 24 polegadas', 'LG', 'Periférico', 'Monitor Full HD', NULL,
       780.00, 4, 5, 'Prateleira B1', c.id, f.id
FROM categorias c JOIN fornecedores f ON f.cnpj = '00000000000102'
WHERE c.nome = 'Periféricos';

INSERT OR IGNORE INTO produtos (
    sku, nome, fabricante, classificacao, especificacao, modalidade_licenca,
    preco_venda, quantidade_estoque, estoque_minimo, localizacao,
    categoria_id, fornecedor_id
)
SELECT 'LIC001', 'Licenca Microsoft 365', 'Microsoft', 'Software',
       'Licenca de produtividade', 'Anual', 450.00, 20, 5, 'Cofre Digital',
       c.id, f.id
FROM categorias c JOIN fornecedores f ON f.cnpj = '00000000000103'
WHERE c.nome = 'Software';

INSERT OR IGNORE INTO produtos (
    sku, nome, fabricante, classificacao, especificacao, modalidade_licenca,
    preco_venda, quantidade_estoque, estoque_minimo, localizacao,
    categoria_id, fornecedor_id
)
SELECT 'LIC002', 'Licenca de Seguranca', 'ESET', 'Software',
       'Software de protecao', 'Anual', 180.00, 3, 5, 'Cofre Digital',
       c.id, f.id
FROM categorias c JOIN fornecedores f ON f.cnpj = '00000000000103'
WHERE c.nome = 'Software';

INSERT INTO movimentacoes (produto_id, tipo_operacao, quantidade, observacao)
SELECT p.id, 'Entrada', p.quantidade_estoque, 'Estoque inicial de demonstracao'
FROM produtos p
WHERE p.sku IN ('RAM001', 'SSD001', 'CPU001', 'MON001', 'LIC001', 'LIC002')
  AND p.quantidade_estoque > 0
  AND NOT EXISTS (
      SELECT 1
      FROM movimentacoes m
      WHERE m.produto_id = p.id
        AND m.tipo_operacao = 'Entrada'
        AND m.observacao LIKE 'Estoque inicial%'
  );
