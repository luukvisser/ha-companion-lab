"""Make the stack's TLS material in /out (run once by stack.sh, in the stack image):

  ca.pem / ca.key      a lab CA, valid 1 year, used for nothing else
  tuya.pem / tuya.key  a server certificate for the Tuya API host names, signed by that CA
  bundle.pem           the image's own CA bundle plus the lab CA: the test HA trusts it through
                       REQUESTS_CA_BUNDLE and SSL_CERT_FILE, nothing else on the machine does

Keys are written with mode 600. Existing files are kept while they are valid for RENEW_DAYS more
days and cover HOSTS; otherwise everything is made anew and "certificates renewed" is printed (the
caller then restarts the services that read them).
"""
import datetime
import os
import sys

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

OUT = sys.argv[1] if len(sys.argv) > 1 else "/out"
HOSTS = ["a1.tuyaeu.com", "a1.tuyaus.com", "a1.tuyain.com", "a1.tuyacn.com"]


def write(name: str, data: bytes, mode: int) -> None:
    path = os.path.join(OUT, name)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def key_pem(key) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


RENEW_DAYS = 30
now = datetime.datetime.now(datetime.timezone.utc)


def still_good() -> str | None:
    """None when the existing material can stay, else why it cannot."""
    try:
        with open(os.path.join(OUT, "ca.pem"), "rb") as f:
            ca_cert = x509.load_pem_x509_certificate(f.read())
        with open(os.path.join(OUT, "tuya.pem"), "rb") as f:
            srv_cert = x509.load_pem_x509_certificate(f.read())
        for name in ("ca.key", "tuya.key", "bundle.pem"):
            if not os.path.exists(os.path.join(OUT, name)):
                return f"{name} missing"
    except (OSError, ValueError) as err:
        return f"unreadable ({err})"
    limit = now + datetime.timedelta(days=RENEW_DAYS)
    for label, cert in (("lab CA", ca_cert), ("server certificate", srv_cert)):
        if cert.not_valid_after_utc < limit:
            return f"{label} expires {cert.not_valid_after_utc:%Y-%m-%d}"
    names = srv_cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    if sorted(names.get_values_for_type(x509.DNSName)) != sorted(HOSTS):
        return "server certificate does not cover the current host names"
    return None


existing = os.path.exists(os.path.join(OUT, "bundle.pem"))
reason = still_good() if existing else "none yet"
if reason is None:
    print("certificates valid; kept")
    sys.exit(0)
ca_key = ec.generate_private_key(ec.SECP256R1())
ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ha-companion-lab test CA")])
ca = (
    x509.CertificateBuilder()
    .subject_name(ca_name)
    .issuer_name(ca_name)
    .public_key(ca_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - datetime.timedelta(minutes=5))
    .not_valid_after(now + datetime.timedelta(days=365))
    .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
    .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
    .add_extension(
        x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True
    )
    .sign(ca_key, hashes.SHA256())
)

srv_key = ec.generate_private_key(ec.SECP256R1())
srv = (
    x509.CertificateBuilder()
    .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, HOSTS[0])]))
    .issuer_name(ca_name)
    .public_key(srv_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - datetime.timedelta(minutes=5))
    .not_valid_after(now + datetime.timedelta(days=365))
    .add_extension(x509.SubjectAlternativeName([x509.DNSName(h) for h in HOSTS]), critical=False)
    .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    .add_extension(x509.SubjectKeyIdentifier.from_public_key(srv_key.public_key()), critical=False)
    # Python 3.14's OpenSSL refuses a chain without it ("Missing Authority Key Identifier").
    .add_extension(
        x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False
    )
    .sign(ca_key, hashes.SHA256())
)

ca_pem = ca.public_bytes(serialization.Encoding.PEM)
write("ca.key", key_pem(ca_key), 0o600)
write("ca.pem", ca_pem, 0o644)
write("tuya.key", key_pem(srv_key), 0o600)
write("tuya.pem", srv.public_bytes(serialization.Encoding.PEM), 0o644)
with open("/etc/ssl/certs/ca-certificates.crt", "rb") as f:
    system = f.read()
write("bundle.pem", system + b"\n" + ca_pem, 0o644)
print(("certificates renewed" if existing else "certificates written") + f" ({reason}): lab CA, server certificate for",
      ", ".join(HOSTS))
