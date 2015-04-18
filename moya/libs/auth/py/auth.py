from __future__ import unicode_literals
from __future__ import print_function

import moya
from moya.compat import text_type, PY2, py2bytes

import hashlib
import random
import time
try:
    random = random.SystemRandom()
    using_sysrandom = True
except NotImplementedError:
    using_sysrandom = False


from passlib.context import CryptContext

if PY2:
    moya_pwd_context = CryptContext(
        schemes=[b"bcrypt", b"sha512_crypt", b"pbkdf2_sha512"],
        default=b"pbkdf2_sha512",
        all__vary_rounds=0.1,
    )
else:
    moya_pwd_context = CryptContext(
        schemes=["bcrypt", "sha512_crypt", "pbkdf2_sha512"],
        default="pbkdf2_sha512",
        all__vary_rounds=0.1,
    )

UNUSABLE_PASSWORD = "!"


def get_random_string(length=12,
                      allowed_chars='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
                      secret=''):
    """
    Returns a securely generated random string.

    The default length of 12 with the a-z, A-Z, 0-9 character set returns
    a 71-bit value. log_2((26+26+10)^12) =~ 71 bits
    """
    if not using_sysrandom:
        # This is ugly, and a hack, but it makes things better than
        # the alternative of predictability. This re-seeds the PRNG
        # using a value that is hard for an attacker to predict, every
        # time a random string is required. This may change the
        # properties of the chosen random sequence slightly, but this
        # is better than absolute predictability.
        random.seed(
            hashlib.sha256(
                "%s%s%s" % (
                    random.getstate(),
                    time.time(),
                    secret)
            ).digest())
    return ''.join([random.choice(allowed_chars) for i in range(length)])


@moya.expose.macro("makesessionkey")
def makesessionkey(app):
    return get_random_string(secret=app.settings.get('secret', ''))


@moya.expose.macro("hashpassword")
def hashpassword(app, password):
    if password is None:
        return None
    rounds = app.settings.get_int('rounds', 10000)
    scheme = text_type(app.settings.get('scheme', 'pbkdf2_sha512'))
    try:
        password_hash = moya_pwd_context.encrypt(password,
                                                 scheme=py2bytes(scheme),
                                                 rounds=rounds)
    except Exception as e:
        app.throw('moya.auth.password-hash-fail', text_type(e))
    return password_hash


@moya.expose.macro("checkpassword")
def checkpassword(app, password, stored_password):
    if not password or password == UNUSABLE_PASSWORD:
        return False
    try:
        passed = moya_pwd_context.verify(password, stored_password)
    except Exception:
        app.log.exception('error when verifying password')
        passed = False
    return passed
