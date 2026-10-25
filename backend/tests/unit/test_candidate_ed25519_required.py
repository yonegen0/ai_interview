"""Mandatory real crypto, including RFC 8032 section 7.1 TEST 1/2/3.

https://www.rfc-editor.org/rfc/rfc8032.html#section-7.1
Only published test seeds are used. Missing cryptography fails collection.
"""

import base64
import json
from copy import deepcopy

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from test_candidate_signed_approval import registry, sample  # noqa: F401

VECTORS = [
    (
        "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
        "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
        "",
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
        "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b",
    ),
    (
        "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
        "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
        "72",
        "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
        "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00",
    ),
    (
        "c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
        "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
        "af82",
        "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac"
        "18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a",
    ),
]


@pytest.mark.parametrize("seed,public,message,signature", VECTORS)
def test_rfc8032_official_sign_verify_and_reject(seed, public, message, signature):
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed))
    public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public))
    raw, expected = bytes.fromhex(message), bytes.fromhex(signature)
    assert key.public_key().public_bytes_raw() == bytes.fromhex(public)
    assert key.sign(raw) == expected
    public_key.verify(expected, raw)
    for altered in (raw + b"x", b"wrong-domain\0" + raw):
        with pytest.raises(InvalidSignature):
            public_key.verify(expected, altered)
    with pytest.raises(InvalidSignature):
        public_key.verify(bytes([expected[0] ^ 1]) + expected[1:], raw)


@pytest.mark.parametrize("mutation", [None, "operation", "domain", "message", "key", "signature"])
def test_mandatory_approval_real_crypto_keeps_trust_and_authority_separate(sample, mutation):  # noqa: F811
    m, now, claim, expected, _ = sample
    private = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(VECTORS[0][0]))
    public = private.public_key().public_bytes_raw()
    signed_bytes = m.signed_bytes(claim)
    if mutation == "domain":
        signed_bytes = signed_bytes.replace(m.DOMAIN, b"producer-receipt\0", 1)
    signature = private.sign(signed_bytes)
    if mutation == "signature":
        signature = bytes([signature[0] ^ 1]) + signature[1:]
    envelope = deepcopy(claim) | {"signature": base64.b64encode(signature).decode()}
    if mutation == "operation":
        envelope["operation"] = expected["operation"] = "recovery-apply"
    elif mutation == "message":
        envelope["source_sha"] = expected["source_sha"] = "9" * 40
    elif mutation == "key":
        public = (
            Ed25519PrivateKey.from_private_bytes(bytes.fromhex(VECTORS[1][0]))
            .public_key()
            .public_bytes_raw()
        )
    trust = registry(m, envelope, now, public_key=public)
    raw = json.dumps(envelope).encode()
    if mutation:
        with pytest.raises(ValueError, match="BadSignatureHOLD"):
            m.verify_signed_approval(raw, expected, trust_registry=trust, now=now)
    else:
        result = m.verify_signed_approval(raw, expected, trust_registry=trust, now=now)
        assert result["signature_verified"] is True
        assert result["trust_enrollment_authenticated"] is False
        assert result["clock_authenticated"] is False
        assert result["authorized"] is False
