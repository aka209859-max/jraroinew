"""
PostgreSQL接続設定

接続先: pckeiba (JRA-VAN + JRDB統合DB)
注意: 全カラムがcharacter varying（文字列型）。
      数値演算を行う前に必ずCAST/astype変換を実装すること。
"""
from dataclasses import dataclass
from typing import Optional

import psycopg2
from psycopg2.extensions import connection as PgConnection


@dataclass(frozen=True)
class DBConfig:
    """PostgreSQL接続パラメータ"""
    host: str = "127.0.0.1"
    port: int = 5432
    database: str = "pckeiba"
    user: str = "postgres"
    password: str = "postgres123"


def get_connection(config: Optional[DBConfig] = None) -> PgConnection:
    """
    PostgreSQLへの接続を取得する。

    Args:
        config: 接続設定。省略時はデフォルト設定を使用。

    Returns:
        psycopg2のconnectionオブジェクト

    Raises:
        psycopg2.OperationalError: 接続に失敗した場合
    """
    if config is None:
        config = DBConfig()

    return psycopg2.connect(
        host=config.host,
        port=config.port,
        database=config.database,
        user=config.user,
        password=config.password,
    )
