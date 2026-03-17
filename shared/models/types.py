"""
Cross-database type compatibiliteit.
Gebruikt PostgreSQL-specifieke types waar beschikbaar,
valt terug op generieke types voor SQLite (development).
"""

import json
import uuid

from sqlalchemy import String, Text, TypeDecorator
from sqlalchemy.types import CHAR, JSON


class UUIDType(TypeDecorator):
    """
    Platform-onafhankelijk UUID type.
    Gebruikt PostgreSQL's native UUID waar beschikbaar,
    slaat op als CHAR(36) in SQLite.
    """
    impl = CHAR(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return str(value)
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(str(value))
        except (ValueError, AttributeError):
            return value

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import UUID as PG_UUID
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))


class JSONType(TypeDecorator):
    """
    Platform-onafhankelijk JSON type.
    Gebruikt PostgreSQL JSONB waar beschikbaar,
    slaat op als TEXT met JSON serialisatie in SQLite.
    """
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value  # PostgreSQL handelt JSON natively af
        return json.dumps(value, ensure_ascii=False)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value  # Komt al als dict terug
        if isinstance(value, str):
            return json.loads(value)
        return value

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import JSONB
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(Text())


class INETType(TypeDecorator):
    """
    Platform-onafhankelijk INET type.
    Gebruikt PostgreSQL INET waar beschikbaar,
    slaat op als String(45) in SQLite.
    """
    impl = String(45)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import INET
            return dialect.type_descriptor(INET())
        return dialect.type_descriptor(String(45))
