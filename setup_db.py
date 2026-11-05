
import sqlite3
from pathlib import Path

# Local onde esta o projeto
pasta_projeto = Path(__file__).resolve().parent

# Caminho do arquivo SQL
arquivo_sql = pasta_projeto / "database.sql"

# Nome do banco de dados
arquivo_banco = pasta_projeto / "techstock.db"

# Conectar ao banco de dados
conexao = sqlite3.connect(arquivo_banco)

# Ativar as chaves estrangeiras
conexao.execute("PRAGMA foreign_keys = ON")

# Ler e executar o arquivo SQL
with open(arquivo_sql, "r", encoding="utf-8") as arquivo:
    comandos = arquivo.read()
    conexao.executescript(comandos)

# Salvar e fechar
conexao.commit()
conexao.close()

print("Banco de dados criado com sucesso!")
print("As 4 tabelas foram preparadas.")
