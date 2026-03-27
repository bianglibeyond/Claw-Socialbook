import os
import sqlite3
import time
from typing import Optional, Tuple, List, Dict
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives import serialization
import base64


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
        cur.execute(
            "create table if not exists fragments ("
            "fragment_id text primary key,"
            "hint text not null,"
            "ephemeral_pubkey blob not null,"
            "ephemeral_privkey blob not null,"
            "created_at integer not null"
            ")"
        )
        cur.execute(
            "create table if not exists kv ("
            "k text primary key,"
            "v text not null"
            ")"
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

    def store_fragment(self, fragment_id: str, hint: str, eph_pub: bytes, eph_priv: bytes) -> None:
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute(
            "insert or replace into fragments(fragment_id, hint, ephemeral_pubkey, ephemeral_privkey, created_at) values(?,?,?,?,?)",
            (fragment_id, hint, eph_pub, eph_priv, int(time.time())),
        )
        con.commit()
        con.close()

    def get_fragment_by_ephemeral_pub(self, eph_pub: bytes) -> Optional[Dict[str, bytes]]:
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute(
            "select fragment_id, hint, ephemeral_pubkey, ephemeral_privkey from fragments where ephemeral_pubkey = ?",
            (eph_pub,),
        )
        row = cur.fetchone()
        con.close()
        if not row:
            return None
        return {
            "fragment_id": row[0].encode("utf-8"),
            "hint": row[1].encode("utf-8"),
            "ephemeral_pubkey": row[2],
            "ephemeral_privkey": row[3],
        }

    def get_private_key_for_ephemeral_pub(self, eph_pub: bytes) -> Optional[x25519.X25519PrivateKey]:
        rec = self.get_fragment_by_ephemeral_pub(eph_pub)
        if not rec:
            return None
        return x25519.X25519PrivateKey.from_private_bytes(rec["ephemeral_privkey"])

    def list_ephemeral_pubkeys(self) -> List[str]:
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute("select ephemeral_pubkey from fragments")
        rows = cur.fetchall()
        con.close()
        out: List[str] = []
        for (b,) in rows:
            s = base64.urlsafe_b64encode(b).rstrip(b"=").decode("utf-8")
            out.append(s)
        return out

    def set_kv(self, k: str, v: str) -> None:
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute("insert or replace into kv(k, v) values(?,?)", (k, v))
        con.commit()
        con.close()

    def get_kv(self, k: str) -> Optional[str]:
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute("select v from kv where k = ?", (k,))
        row = cur.fetchone()
        con.close()
        return row[0] if row else None
