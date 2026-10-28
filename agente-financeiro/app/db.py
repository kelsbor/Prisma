from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text, create_engine, func

from app.config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
metadata = MetaData()

# Dados financeiros: tudo criptografado, titular só como hash
registros = Table(
    "registros",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("titular_hash", String(64), nullable=False, index=True),
    Column("finalidade", String(120), nullable=False),
    Column("dados_cifrados", Text, nullable=False),
    Column("criado_em", DateTime(timezone=True), server_default=func.now()),
)

# Trilha de auditoria: quem fez o quê e quando, SEM conteúdo dos dados
auditoria = Table(
    "auditoria",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("acao", String(30), nullable=False),
    Column("titular_hash", String(64), nullable=False),
    Column("quantidade", Integer, nullable=False, default=0),
    Column("quando", DateTime(timezone=True), server_default=func.now()),
)

metadata.create_all(engine)
