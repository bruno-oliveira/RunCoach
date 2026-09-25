"""Web Push transport: RFC 8291 encryption, VAPID, and the endpoint allowlist.

The encryption is pinned to the RFC's own worked example (Appendix A), byte for
byte — a push service rejects anything else silently, as "the phone never
buzzed", so this is the only place a mistake would ever show up.
"""

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.domain.notifications import PushMessage, PushOutcome, PushTarget
from app.infrastructure.notifications.webpush import (
    WebPushSender,
    b64url_decode,
    b64url_encode,
    encrypt_payload,
    generate_vapid_private_key,
    is_allowed_endpoint,
    load_vapid_private_key,
    vapid_authorization,
    vapid_public_key,
)

# RFC 8291 Appendix A.
_PLAINTEXT = b"When I grow up, I want to be a watermelon"
_SENDER_PRIVATE = "yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"
_UA_PRIVATE = "q1dXpw3UpT5VOmu_cf_v6ih07Aems3njxI-JWgLcM94"
_UA_PUBLIC = "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"
_AUTH = "BTBZMqHH6r4Tts7J_aSIgg"
_SALT = "DGv6ra1nlYgDCS1FRnbzlw"
_EXPECTED = (
    "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vC"
    "YLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXL"
    "WyouBWLVWGNWQexSgSxsj_Qulcy4a-fN"
)

ENDPOINT = "https://fcm.googleapis.com/fcm/send/abc123"


def _decrypt(body: bytes, ua_private_b64: str, auth_b64: str) -> bytes:
    """The browser's side of RFC 8291, for round-trip tests."""
    salt, keyid_len = body[:16], body[20]
    as_public_raw = body[21 : 21 + keyid_len]
    sealed = body[21 + keyid_len :]
    ua_private = load_vapid_private_key(ua_private_b64)
    ua_public_raw = b64url_decode(vapid_public_key(ua_private))
    as_public = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), as_public_raw
    )
    secret = ua_private.exchange(ec.ECDH(), as_public)
    info = b"WebPush: info\x00" + ua_public_raw + as_public_raw
    ikm = HKDF(hashes.SHA256(), 32, b64url_decode(auth_b64), info).derive(secret)
    cek = HKDF(hashes.SHA256(), 16, salt, b"Content-Encoding: aes128gcm\x00").derive(
        ikm
    )
    nonce = HKDF(hashes.SHA256(), 12, salt, b"Content-Encoding: nonce\x00").derive(ikm)
    padded = AESGCM(cek).decrypt(nonce, sealed, None)
    assert padded.endswith(b"\x02")
    return padded[:-1]


def test_encryption_matches_rfc8291_worked_example():
    body = encrypt_payload(
        _PLAINTEXT,
        _UA_PUBLIC,
        _AUTH,
        salt=b64url_decode(_SALT),
        sender_key=load_vapid_private_key(_SENDER_PRIVATE),
    )
    assert b64url_encode(body) == _EXPECTED


def test_fresh_encryption_round_trips_through_the_browser_side():
    body = encrypt_payload(_PLAINTEXT, _UA_PUBLIC, _AUTH)
    assert _decrypt(body, _UA_PRIVATE, _AUTH) == _PLAINTEXT
    # Fresh salt and key every time: two sends never share ciphertext.
    assert encrypt_payload(_PLAINTEXT, _UA_PUBLIC, _AUTH)[:16] != body[:16]


def test_vapid_header_is_a_verifiable_es256_token_for_the_push_origin():
    private = load_vapid_private_key(generate_vapid_private_key())
    header = vapid_authorization(
        ENDPOINT, private, "mailto:coach@example.com", now=1_700_000_000
    )
    token = header.split("t=")[1].split(",")[0]
    public = header.split("k=")[1]
    assert public == vapid_public_key(private)
    claims = jwt.decode(
        token,
        private.public_key(),
        algorithms=["ES256"],
        audience="https://fcm.googleapis.com",
        options={"verify_exp": False},
    )
    assert claims["sub"] == "mailto:coach@example.com"
    assert claims["exp"] == 1_700_000_000 + 12 * 3600


@pytest.mark.parametrize(
    "endpoint,allowed",
    [
        ("https://fcm.googleapis.com/fcm/send/x", True),
        ("https://updates.push.services.mozilla.com/wpush/v2/x", True),
        ("https://web.push.apple.com/QGx", True),
        ("https://db5p.notify.windows.com/w/?token=x", True),
        ("http://fcm.googleapis.com/fcm/send/x", False),
        ("https://10.0.0.1/push", False),
        ("https://localhost/push", False),
        ("https://evil.com/fcm.googleapis.com", False),
        ("https://fcm.googleapis.com.evil.com/x", False),
        ("not a url", False),
    ],
)
def test_only_real_push_services_are_contacted(endpoint, allowed):
    """The endpoint is browser-supplied and we POST to it from the server."""
    assert is_allowed_endpoint(endpoint) is allowed


def _sender(handler) -> WebPushSender:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return WebPushSender(generate_vapid_private_key(), "mailto:x@example.com", client)


def _target() -> PushTarget:
    return PushTarget(endpoint=ENDPOINT, p256dh=_UA_PUBLIC, auth=_AUTH)


def test_sender_posts_an_encrypted_body_the_browser_can_read():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["headers"] = request.headers
        seen["body"] = request.content
        return httpx.Response(201)

    outcome = _sender(handler).send(
        _target(), PushMessage(title="Hi", body="There", url="/plan/1", tag="plan-1")
    )
    assert outcome == PushOutcome.DELIVERED
    assert seen["headers"]["content-encoding"] == "aes128gcm"
    assert seen["headers"]["authorization"].startswith("vapid t=")
    assert seen["headers"]["topic"] == "plan-1"
    plaintext = _decrypt(seen["body"], _UA_PRIVATE, _AUTH)
    assert b'"url": "/plan/1"' in plaintext


@pytest.mark.parametrize(
    "status,outcome",
    [(404, PushOutcome.GONE), (410, PushOutcome.GONE), (500, PushOutcome.FAILED)],
)
def test_push_service_answers_map_to_outcomes(status, outcome):
    sender = _sender(lambda request: httpx.Response(status))
    assert sender.send(_target(), PushMessage(title="t", body="b")) == outcome


def test_unconfigured_sender_refuses_rather_than_pretends():
    sender = WebPushSender(None, "mailto:x@example.com")
    assert sender.configured is False
    assert sender.send(_target(), PushMessage(title="t", body="b")) == (
        PushOutcome.FAILED
    )


def test_a_disallowed_endpoint_is_treated_as_gone_not_contacted():
    def handler(request):  # pragma: no cover - must not be reached
        raise AssertionError("contacted a non-push host")

    sender = _sender(handler)
    target = PushTarget(endpoint="https://10.0.0.1/x", p256dh=_UA_PUBLIC, auth=_AUTH)
    assert sender.send(target, PushMessage(title="t", body="b")) == PushOutcome.GONE
