"""Generate the VAPID key pair for Web Push — run once per deployment.

    python3 scripts/generate_vapid_keys.py

Store the private key as a secret (``fly secrets set VAPID_PRIVATE_KEY=...``);
the public key is derived from it at runtime and served to browsers, so it
needs no configuration. Rotating the private key invalidates every existing
browser subscription — runners would have to switch notifications on again.
"""

from app.infrastructure.notifications.webpush import (
    generate_vapid_private_key,
    load_vapid_private_key,
    vapid_public_key,
)

if __name__ == "__main__":
    private = generate_vapid_private_key()
    public = vapid_public_key(load_vapid_private_key(private))
    print(f"VAPID_PRIVATE_KEY={private}")
    print(f"# public key (derived automatically, for reference): {public}")
