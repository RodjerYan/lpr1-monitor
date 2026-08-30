"""Web Push sender per RFC 8291 + VAPID per RFC 8292."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import time
from urllib.parse import urlparse

import httpx
from cryptography.hazmat.primitives.asymmetric import ec, utils as asym_utils
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import logging
logger = logging.getLogger("webpush")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * pad)


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(), length=length, salt=salt, info=info,
    ).derive(ikm)


def _get_vapid_headers(endpoint: str, vapid_private_b64: str) -> dict[str, str]:
    raw_key = _b64url_decode(vapid_private_b64)
    if len(raw_key) != 32:
        raise ValueError(f"Bad VAPID key length: {len(raw_key)}")

    private_key = ec.derive_private_key(
        int.from_bytes(raw_key, "big"), ec.SECP256R1()
    )

    parsed = urlparse(endpoint)
    aud = f"{parsed.scheme}://{parsed.hostname}"
    exp = int(time.time()) + 43200

    header_b64 = _b64url(json.dumps({"typ": "JWT", "alg": "ES256"}).encode())
    payload_b64 = _b64url(json.dumps({
        "aud": aud, "exp": exp, "sub": "mailto:admin@lpr1-monitor.ru"
    }, separators=(",", ":")).encode())

    message = f"{header_b64}.{payload_b64}".encode()
    sig_der = private_key.sign(message, ec.ECDSA(hashes.SHA256()))
    r, s = asym_utils.decode_dss_signature(sig_der)
    sig_raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")

    token = f"{header_b64}.{payload_b64}.{_b64url(sig_raw)}"

    pub = private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    return {"Authorization": f"vapid t={token}, k={_b64url(pub)}"}


def send_web_push(subscription: dict, title: str, body: str) -> bool:
    endpoint = subscription.get("endpoint", "")
    p256dh = subscription.get("keys", {}).get("p256dh", "")
    auth_b64 = subscription.get("keys", {}).get("auth", "")

    if not endpoint or not p256dh or not auth_b64:
        logger.warning("Missing subscription fields")
        return False

    vapid_private = os.getenv("PUSH_VAPID_PRIVATE", "")
    if not vapid_private:
        logger.warning("PUSH_VAPID_PRIVATE not set")
        return False

    try:
        sub_pub_bytes = _b64url_decode(p256dh)
        sub_pub = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(), sub_pub_bytes
        )
        auth_secret = _b64url_decode(auth_b64)

        ephemeral = ec.generate_private_key(ec.SECP256R1())
        ephemeral_pub_bytes = ephemeral.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )

        # ECDH shared secret
        ikm = ephemeral.exchange(ec.ECDH(), sub_pub)

        salt = os.urandom(16)

        # RFC 8291 Section 3.3 key derivation
        prk = _hkdf(auth_secret, ikm, b"WebPush: info\x00" + sub_pub_bytes, 32)
        key = _hkdf(salt, prk, b"Content-Encoding: aes128gcm\x00", 32)
        nonce = _hkdf(salt, prk, b"Content-Encoding: nonce\x00", 12)

        # Encrypt
        payload = json.dumps({"title": title, "body": body}).encode()
        ciphertext = AESGCM(key).encrypt(nonce, payload, None)

        # aes128gcm record: salt(16) + rs(4 LE) + idlen(1) + ciphertext
        record = salt + struct.pack("<I", 0) + b"\x00" + ciphertext

        # VAPID
        vapid_headers = _get_vapid_headers(endpoint, vapid_private)

        resp = httpx.post(
            endpoint,
            content=record,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Encoding": "aes128gcm",
                "TTL": "86400",
                **vapid_headers,
            },
            timeout=15,
        )

        if resp.status_code in (200, 201, 202):
            logger.info(f"Push OK: {endpoint[:50]}")
            return True
        elif resp.status_code == 410:
            logger.info(f"Push subscription expired: {endpoint[:50]}")
            return False
        else:
            logger.warning(f"Push {resp.status_code}: {resp.text[:200]}")
            return False

    except Exception as e:
        logger.warning(f"Push error: {type(e).__name__}: {e}")
        return False
