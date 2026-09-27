"""Regression coverage for the PyJWT crypto extra used by Supabase tokens."""

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa


def test_pyjwt_can_sign_and_verify_an_rs256_token() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    token = jwt.encode({"sub": "synthetic-user"}, private_key, algorithm="RS256")
    claims = jwt.decode(token, public_key, algorithms=["RS256"])

    assert claims["sub"] == "synthetic-user"
