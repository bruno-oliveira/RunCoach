"""Web Push delivery — RFC 8291 payload encryption + RFC 8292 VAPID.

Written against ``cryptography`` and ``PyJWT`` (both already shipped for the
token encryption and the session JWTs) rather than taking ``pywebpush``, which
would drag ``aiohttp`` and ``requests`` onto a 512 MB machine and force a
``cryptography`` major upgrade for about eighty lines of well-specified work.

The protocol, in the order :func:`encrypt_payload` does it:

1. A fresh P-256 key pair per message; ECDH against the browser's ``p256dh``.
2. HKDF with the browser's ``auth`` secret → a 32-byte input key (RFC 8291 §3.3).
3. HKDF with a random 16-byte salt → the AES-128-GCM key and the 12-byte nonce.
4. One record: plaintext + ``0x02`` delimiter, sealed, behind the ``aes128gcm``
   header (salt ‖ record size ‖ key-id length ‖ our public key) — RFC 8188.

VAPID signs a short-lived ES256 JWT whose ``aud`` is the push service's origin,
which is how Apple/Google/Mozilla know the message came from the server that
owns the public key the browser subscribed with.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import struct
import time
from typing import Optional
from urllib.parse import urlparse

import httpx
import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.domain.notifications import PushMessage, PushOutcome, PushTarget

logger = logging.getLogger(__name__)

# A single record carries the whole payload; 4096 is the conventional size and
# comfortably above the ~3 KB push services accept.
_RECORD_SIZE = 4096
# How long a push service may hold an undeliverable message. A "plan adjusted"
# note that arrives two days late is noise, so a day is the ceiling.
_TTL_SECONDS = 86400
_VAPID_LIFETIME_SECONDS = 12 * 3600
_TIMEOUT = httpx.Timeout(10.0)

# Only real push services. The endpoint is browser-supplied, and we POST to it
# from the server — without this an attacker could subscribe "https://10.0.0.1/"
# and use us as a request relay into the private network.
PUSH_SERVICE_HOST_SUFFIXES = (
    "fcm.googleapis.com",
    "android.googleapis.com",
    "updates.push.services.mozilla.com",
    "push.services.mozilla.com",
    "push.apple.com",
    "notify.windows.com",
)


def b64url_decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode())


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def is_allowed_endpoint(endpoint: str) -> bool:
    """True for an ``https`` URL on a known browser push service."""
    try:
        parsed = urlparse(endpoint)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        return False
    return any(
        host == suffix or host.endswith("." + suffix)
        for suffix in PUSH_SERVICE_HOST_SUFFIXES
    )


def _public_bytes(key: ec.EllipticCurvePublicKey) -> bytes:
    return key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )


def load_vapid_private_key(value: str) -> ec.EllipticCurvePrivateKey:
    """Accept the raw base64url scalar most generators print, or a PEM."""
    value = value.strip()
    if value.startswith("-----BEGIN"):
        key = serialization.load_pem_private_key(value.encode(), password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey):
            raise ValueError("VAPID key must be an EC P-256 key")
        return key
    scalar = int.from_bytes(b64url_decode(value), "big")
    return ec.derive_private_key(scalar, ec.SECP256R1())


def vapid_public_key(private_key: ec.EllipticCurvePrivateKey) -> str:
    """The ``applicationServerKey`` the browser subscribes with (base64url)."""
    return b64url_encode(_public_bytes(private_key.public_key()))


def generate_vapid_private_key() -> str:
    """A new raw base64url VAPID private key (see scripts/generate_vapid_keys.py)."""
    key = ec.generate_private_key(ec.SECP256R1())
    return b64url_encode(key.private_numbers().private_value.to_bytes(32, "big"))


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(
        ikm
    )


def encrypt_payload(
    plaintext: bytes,
    p256dh: str,
    auth: str,
    *,
    salt: Optional[bytes] = None,
    sender_key: Optional[ec.EllipticCurvePrivateKey] = None,
) -> bytes:
    """Encrypt ``plaintext`` for one subscription as an ``aes128gcm`` body.

    ``salt`` and ``sender_key`` are injectable only so tests can pin them to
    the RFC 8291 worked example; production always draws fresh ones.
    """
    ua_public_raw = b64url_decode(p256dh)
    auth_secret = b64url_decode(auth)
    ua_public = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), ua_public_raw
    )
    as_private = sender_key or ec.generate_private_key(ec.SECP256R1())
    as_public_raw = _public_bytes(as_private.public_key())
    salt = salt or os.urandom(16)

    ecdh_secret = as_private.exchange(ec.ECDH(), ua_public)
    key_info = b"WebPush: info\x00" + ua_public_raw + as_public_raw
    ikm = _hkdf(auth_secret, ecdh_secret, key_info, 32)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)

    sealed = AESGCM(cek).encrypt(nonce, plaintext + b"\x02", None)
    header = (
        salt
        + struct.pack("!I", _RECORD_SIZE)
        + bytes([len(as_public_raw)])
        + as_public_raw
    )
    return header + sealed


def vapid_authorization(
    endpoint: str,
    private_key: ec.EllipticCurvePrivateKey,
    subject: str,
    *,
    now: Optional[int] = None,
) -> str:
    """The ``Authorization: vapid t=..., k=...`` header value for ``endpoint``."""
    parsed = urlparse(endpoint)
    claims = {
        "aud": f"{parsed.scheme}://{parsed.netloc}",
        "exp": int(now if now is not None else time.time()) + _VAPID_LIFETIME_SECONDS,
        "sub": subject,
    }
    token = jwt.encode(claims, private_key, algorithm="ES256")
    return f"vapid t={token}, k={vapid_public_key(private_key)}"


class WebPushSender:
    """Sends one encrypted notification per call. Implements ``PushSender``."""

    def __init__(
        self,
        private_key: Optional[str],
        subject: str,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self._key = load_vapid_private_key(private_key) if private_key else None
        self._subject = subject
        self._client = client

    @property
    def configured(self) -> bool:
        return self._key is not None

    @property
    def public_key(self) -> Optional[str]:
        return vapid_public_key(self._key) if self._key else None

    def send(self, target: PushTarget, message: PushMessage) -> str:
        if self._key is None:
            logger.info("Push not configured (VAPID_PRIVATE_KEY unset) — not sent")
            return PushOutcome.FAILED
        if not is_allowed_endpoint(target.endpoint):
            # Validated on subscribe too; a row that predates a tightened list
            # is treated as dead rather than contacted.
            return PushOutcome.GONE

        payload = json.dumps(
            {
                "title": message.title,
                "body": message.body,
                "url": message.url,
                "tag": message.tag,
            }
        ).encode()
        try:
            body = encrypt_payload(payload, target.p256dh, target.auth)
        except (ValueError, TypeError):
            # Keys the browser handed us that aren't a P-256 point: this
            # subscription can never be delivered to.
            return PushOutcome.GONE

        headers = {
            "Authorization": vapid_authorization(
                target.endpoint, self._key, self._subject
            ),
            "Content-Encoding": "aes128gcm",
            "Content-Type": "application/octet-stream",
            "TTL": str(_TTL_SECONDS),
            "Urgency": "normal",
        }
        if message.tag:
            # RFC 8030 Topic: the push service itself replaces an undelivered
            # message with the same topic (max 32 url-safe chars).
            headers["Topic"] = message.tag[:32]
        try:
            client = self._client or httpx.Client(timeout=_TIMEOUT)
            try:
                response = client.post(target.endpoint, content=body, headers=headers)
            finally:
                if self._client is None:
                    client.close()
        except httpx.HTTPError as error:
            logger.warning("Push delivery error: %s", error)
            return PushOutcome.FAILED

        if response.status_code in (404, 410):
            return PushOutcome.GONE
        if 200 <= response.status_code < 300:
            return PushOutcome.DELIVERED
        logger.warning("Push service answered %s", response.status_code)
        return PushOutcome.FAILED


def get_push_sender() -> WebPushSender:
    """The configured sender (an unconfigured one refuses and says so)."""
    from app.infrastructure.config import settings

    subject = settings.vapid_subject or settings.public_base_url
    if not subject.startswith(("mailto:", "https://")):
        # Apple rejects anything else; localhost dev has no https origin.
        subject = "mailto:coach@runcoach.invalid"
    return WebPushSender(settings.vapid_private_key or None, subject)
