Vector-only search, itsdangerous, k=5
Q1 expiry           -> rank 3   (TimestampSigner.unsign)
Q2 timing-safe      -> rank 1   (SigningAlgorithm, compare_digest on L28)
Q3 base64           -> rank 1   (base64_encode)
Q4 SignatureExpired -> MISS     (raised in unsign L142/149, not in top 5)