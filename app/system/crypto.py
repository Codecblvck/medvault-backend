import json
import base64
from Crypto.Cipher import AES, PKCS1_OAEP
from Crypto.PublicKey import RSA
from Crypto.Random import get_random_bytes
from app.config import Config


def get_rsa_public_key():
    path = Config.RSA_PUBLIC_KEY_PATH
    if path is None:
        raise ValueError("RSA private key path is not configured")

    with open(path, "rb") as f:
        return RSA.import_key(f.read())


def get_rsa_private_key():
    path = Config.RSA_PRIVATE_KEY_PATH
    if path is None:
        raise ValueError("RSA private key path is not configured")

    with open(path, "rb") as f:
        return RSA.import_key(f.read())


def encrypt_data(data_dict):
    """
    Encrypts record data using a freshly generated AES key, then wraps
    that AES key using the RSA public key.

    Returns a tuple: (encrypted_data_str, wrapped_aes_key_str)
    Both are base64-encoded strings, ready to store in two separate
    columns on the Record model.
    """
    # Step 1: fresh AES-256 key, unique to this one record
    aes_key = get_random_bytes(32)

    # Step 2: encrypt the actual record data, same AES-GCM approach as before
    json_bytes = json.dumps(data_dict).encode("utf-8")
    cipher = AES.new(aes_key, AES.MODE_GCM)
    ciphertext, tag = cipher.encrypt_and_digest(json_bytes)

    nonce = bytes(cipher.nonce)
    combined = nonce + tag + ciphertext
    encrypted_data_str = base64.b64encode(combined).decode("utf-8")

    # Step 3: wrap the fresh AES key using RSA, so it's useless without
    # the private key
    public_key = get_rsa_public_key()
    rsa_cipher = PKCS1_OAEP.new(public_key)
    wrapped_key = rsa_cipher.encrypt(aes_key)
    wrapped_key_str = base64.b64encode(wrapped_key).decode("utf-8")

    return encrypted_data_str, wrapped_key_str


def decrypt_data(encrypted_str, wrapped_key_str):
    """
    Reverses encrypt_data. Needs both the encrypted record data AND
    the wrapped AES key that was stored alongside it, since there is
    no longer one fixed AES key for everything.
    """
    # Step 1: unwrap the AES key using the RSA private key
    private_key = get_rsa_private_key()
    rsa_cipher = PKCS1_OAEP.new(private_key)
    wrapped_key = base64.b64decode(wrapped_key_str)
    aes_key = rsa_cipher.decrypt(wrapped_key)

    # Step 2: use the recovered AES key to decrypt the record, same
    # AES-GCM approach as before
    combined = base64.b64decode(encrypted_str)
    nonce = combined[:16]
    tag = combined[16:32]
    ciphertext = combined[32:]

    cipher = AES.new(aes_key, AES.MODE_GCM, nonce=nonce)
    json_bytes = cipher.decrypt_and_verify(ciphertext, tag)

    return json.loads(json_bytes.decode("utf-8"))
