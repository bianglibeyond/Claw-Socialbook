import os
import sqlite3
from typing import Optional, Tuple
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives import serialization


class Vault:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_db()

    def _ensure_db(self) -> None:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute(
            "create table if not exists keys (id integer primary key, public_key blob not null, private_key blob not null)"
        )
        con.commit()
        con.close()

    def has_keypair(self) -> bool:
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute("select count(1) from keys")
        row = cur.fetchone()
        con.close()
        return bool(row and row[0] > 0)

    def generate(self) -> Tuple[bytes, bytes]:
        private_key = x25519.X25519PrivateKey.generate()
        public_key = private_key.public_key()
        private_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute("delete from keys")
        cur.execute(
            "insert into keys(id, public_key, private_key) values(1, ?, ?)",
            (public_bytes, private_bytes),
        )
        con.commit()
        con.close()
        return public_bytes, private_bytes

    def get_keypair(self) -> Optional[Tuple[bytes, bytes]]:
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute("select public_key, private_key from keys where id = 1")
        row = cur.fetchone()
        con.close()
        if not row:
            return None
        return row[0], row[1]

    def get_private_key(self) -> Optional[x25519.X25519PrivateKey]:
        kp = self.get_keypair()
        if not kp:
            return None
        _, priv = kp
        return x25519.X25519PrivateKey.from_private_bytes(priv)

    def get_public_key_bytes(self) -> Optional[bytes]:
        kp = self.get_keypair()
        if not kp:
            return None
        pub, _ = kp
        return pub
