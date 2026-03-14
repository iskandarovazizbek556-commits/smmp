import hashlib, hmac, secrets

def hash_pw(pw):      return hashlib.sha256(pw.encode()).hexdigest()
def check_pw(pw, h):  return hmac.compare_digest(hash_pw(pw), h)
def gen_key():        return secrets.token_hex(16)
def gen_ref():        return secrets.token_hex(4).upper()