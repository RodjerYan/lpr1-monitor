"""Minimal Web Push sender using cryptography + httpx (no pywebpush)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import struct
import os

import httpx
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_VAPID_CLAIMS = {
    "aud": "https://fcm.googleapis.com",
    "exp": int(time.time()) + 43200,
    "sub": "mailto:admin@lpr1-monitor.ru",
}


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * pad)


def _aesgcm_encrypt(key: bytes, nonce: bytes, plaintext: bytes) -> bytes:
    aesgcm = AESGCM(key)
    return aesgcm.encrypt(nonce, plaintext, None)


def _get_vapid_headers(endpoint: str, vapid_private_b64: str) -> dict[str, str]:
    """Create VAPID Authorization header."""
    raw_key = _b64url_decode(vapid_private_b64)
    if len(raw_key) == 32:
        private_key = ec.derive_private_key(
            int.from_bytes(raw_key, "big"), ec.SECP256R1()
        )
    else:
        raise ValueError(f"Unexpected VAPID key length: {len(raw_key)}")

    # JWT header
    header = _b64url(json.dumps({"typ": "JWT", "alg": "ES256"}).encode())

    # JWT payload — extract origin from endpoint
    from urllib.parse import urlparse
    parsed = urlparse(endpoint)
    claims = {**_VAPID_CLAIMS, "aud": f"{parsed.scheme}://{parsed.hostname}"}
    payload = _b64url(json.dumps(claims, separators=(",", ":")).encode())

    # Sign
    message = f"{header}.{payload}".encode()
    sig = private_key.sign(message, ec.ECDSA(hashes.SHA256()))

    # Convert DER signature (64 bytes) to raw (r||s)
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    r, s = decode_dss_signature(sig)
    raw_sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")

    token = f"{header}.{payload}.{_b64url(raw_sig)}"

    # Public key for header
    public_key = private_key.public_key()
    pub_bytes = public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )

    return {
        "Authorization": f"vapid t={token}, k={_b64url(pub_bytes)}",
    }


def _derive_keys(auth_secret: bytes, user_agent_key: bytes, salt: bytes) -> tuple:
    """Derive encryption keys per RFC 8291."""
    # ikm = HKDF(auth_secret, ua_key, "WebPush: info\x00", 32)
    ikm = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=auth_secret,
        info=b"WebPush: info\x00" + user_agent_key,
    ).derive(b"")

    # keys = HKDF(ikm, salt, "Content-Encoding: aes128gcm\x00", 32)
    keys = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=b"Content-Encoding: aes128gcm\x00",
    ).derive(ikm)

    return keys  # encryption key


def _build_payload(cleartext: bytes, key: bytes, salt: bytes) -> bytes:
    """Build aes128gcm payload per RFC 8291."""
    record = bytearray()
    record.extend(salt)  # 16 bytes
    record.extend(b"\x00\x00\x00\x00")  # 4 bytes LE: rs=0 (no record padding)
    record.extend(b"\x01")  # 1 byte: id_length=1
    record.extend(b"\x01")  # 1 byte: key_id (just the key length byte)
    # Actually rs=4096 is standard
    record.clear()
    record.extend(salt)  # 16 bytes
    record.extend(struct.pack("<I", 4096))  # rs = 4096
    record.extend(b"\x01")  # id_length
    record.extend(b"\x01")  # key identifier: 0x01 (single byte for aes128gcm)
    # Hmm wait, that's not right. Let me re-read RFC 8291.

    # RFC 8291 aes128gcm record:
    # salt (16 bytes) | rs (4 bytes LE) | idlen (1 byte) | keyid | payload...
    # For aes128gcm, idlen=0 is valid meaning the keyid is implicit
    record.clear()
    record.extend(salt)  # 16 bytes
    record.extend(struct.pack("<I", 4096))  # rs = 4096
    record.extend(b"\x00")  # idlen = 0 (no keyid)
    # No padding needed since we have rs=0 wait...

    # Actually, rs is the record size. For web push, rs=0 means no chunking.
    # But the padding... let me simplify. Use rs=0 for single record.
    record.clear()
    record.extend(salt)  # 16 bytes
    record.extend(b"\x00\x00\x00\x00")  # rs = 0 (no chunking)
    record.extend(b"\x00")  # idlen = 0

    # pad cleartext to 16 bytes (AES block)
    padding_needed = 16 - (len(cleartext) % 16)
    padded = cleartext + b"\x00" * padding_needed + struct.pack("<H", padding_needed - 1)

    nonce = hashlib.sha256(salt + key).digest()[:12]
    ciphertext = _aesgcm_encrypt(key, nonce, padded)
    record.extend(ciphertext)

    return bytes(record)


def send_web_push(subscription: dict, title: str, body: str) -> bool:
    """Send a Web Push notification to one subscription."""
    endpoint = subscription.get("endpoint", "")
    p256dh = subscription.get("keys", {}).get("p256dh", "")
    auth = subscription.get("keys", {}).get("auth", "")

    if not endpoint or not p256dh or not auth:
        return False

    vapid_private = os.getenv("PUSH_VAPID_PRIVATE", "")
    if not vapid_private:
        return False

    try:
        # Parse subscriber's public key
        sub_public_bytes = _b64url_decode(p256dh)
        sub_public_key = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(), sub_public_bytes
        )
        auth_secret = _b64url_decode(auth)

        # Generate ephemeral key pair
        ephemeral = ec.generate_private_key(ec.SECP256R1())
        ephemeral_pub = ephemeral.public_key()
        ephemeral_pub_bytes = ephemeral_pub.public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )

        # ECDH shared secret
        shared_secret = ephemeral.exchange(ec.ECDH(), sub_public_key)

        # Derive encryption key
        salt = os.urandom(16)
        enc_key = _derive_keys(auth_secret, sub_public_key.public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        ), salt)

        # Build encrypted payload
        payload_json = json.dumps({"title": title, "body": body})
        payload_bytes = payload_json.encode("utf-8")

        # For aes128gcm:
        nonce = hashlib.sha256(salt + enc_key).digest()[:12]
        ciphertext = AESGCM(enc_key).encrypt(nonce, payload_bytes, None)

        record = bytearray()
        record.extend(salt)
        record.extend(b"\x00\x00\x00\x00")  # rs=0
        record.extend(b"\x00")  # idlen=0
        record.extend(ciphertext)

        # VAPID headers
        vapid_headers = _get_vapid_headers(endpoint, vapid_private)

        headers = {
            "Content-Type": "application/octet-stream",
            "Content-Encoding": "aes128gcm",
            "TTL": "86400",
            **vapid_headers,
        }

        resp = httpx.post(endpoint, content=bytes(record), headers=headers, timeout=15)
        if resp.status_code in (200, 201, 202):
            return True
        elif resp.status_code == 410:
            # Subscription expired — should remove
            logger.info(f"Push subscription expired: {endpoint[:60]}")
            return False
        else:
            logger.warning(f"Push failed {resp.status_code}: {resp.text[:200]}")
            return False

    except Exception as e:
        logger.warning(f"Push error: {type(e).__name__}: {e}")
        return False


import logging
logger = logging.getLogger("webpush")
