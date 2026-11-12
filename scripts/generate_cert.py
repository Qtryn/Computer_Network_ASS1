"""Generate a self-signed localhost TLS certificate for the assignment demo."""
import ipaddress
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def main():
    directory = Path("config/local_tls")
    certificate_path, key_path = directory / "server.pem", directory / "server-key.pem"
    if certificate_path.exists() or key_path.exists():
        raise SystemExit("TLS files already exist; keep them or choose another certificate manually")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                   .public_key(key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now - timedelta(minutes=1))
                   .not_valid_after(now + timedelta(days=30))
                   .add_extension(x509.SubjectAlternativeName([
                       x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), False)
                   .sign(key, hashes.SHA256()))
    directory.mkdir(parents=True, exist_ok=True)
    with key_path.open("xb") as output:
        output.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
    with certificate_path.open("xb") as output:
        output.write(certificate.public_bytes(serialization.Encoding.PEM))
    print(f"Created localhost certificate: {certificate_path}")
    print("Trust server.pem with --tls-ca; keep server-key.pem on the server only")


if __name__ == "__main__":
    main()
