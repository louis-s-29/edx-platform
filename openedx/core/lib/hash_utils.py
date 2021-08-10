"""
Utilities related to hashing

This duplicates functionality in django-oauth-provider,
specifically long_token and short token functions which was used to create
random tokens
"""
import hashlib
from base64 import urlsafe_b64encode

from django.utils.encoding import force_bytes
from django.utils.crypto import get_random_string
from django.conf import settings
from opaque_keys.edx.keys import UsageKey


def create_hash256(max_length=None):
    """
    Generate a hash that can be used as an application secret
    Warning: this is not sufficiently secure for tasks like encription
    Currently, this is just meant to create sufficiently random tokens
    """
    hash_object = hashlib.sha256(force_bytes(get_random_string(32)))
    hash_object.update(force_bytes(settings.SECRET_KEY))
    output_hash = hash_object.hexdigest()
    if max_length is not None and len(output_hash) > max_length:
        return output_hash[:max_length]
    return output_hash


def short_token():
    """
    Generates a hash of length 32
    Warning: this is not sufficiently secure for tasks like encription
    Currently, this is just meant to create sufficiently random tokens
    """
    return create_hash256(max_length=32)


def hash_usage_key(usage_key: UsageKey) -> str:
    """
    Get the blake2b hash key for the given usage_key and encode the value. The
    hash key will be added to the usage key's mapping dictionary for decoding
    in LMS.

    Args:
        usage_key: the id of the location to which to generate the path

    Returns:
        The string of the encoded hashed key.
    """
    short_key = hashlib.blake2b(bytes(str(usage_key), 'utf-8'), digest_size=6)
    encoded_hash = urlsafe_b64encode(bytes(short_key.hexdigest(), 'utf-8'))
    return str(encoded_hash, 'utf-8')


def is_potential_usage_key_hash(string: str) -> bool:
    """
    Is this string a possible output of `hash_usage_key`?
    """
    lowers = {chr(i) for i in range(ord('a'), ord('z') + 1)}
    uppers = {chr(i) for i in range(ord('A'), ord('Z') + 1)}
    digits = {chr(i) for i in range(ord('0'), ord('9') + 1)}
    symbols = {"-", "_"}
    all_hash_characters = lowers | uppers | digits | symbols
    return set(string).issubset(all_hash_characters)
