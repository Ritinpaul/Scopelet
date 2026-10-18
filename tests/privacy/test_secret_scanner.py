"""
Unit tests for the Scopelet Secret Scanner.
Covers 30+ test cases across credentials, tokens, private keys, URIs, Shannon entropy and masking.
"""

from pathlib import Path
import pytest

from scopelet.privacy.scanner.secret_scanner import (
    SecretScanner,
    calculate_shannon_entropy,
    mask_secret,
)


@pytest.fixture
def scanner() -> SecretScanner:
    return SecretScanner()


# 1. AWS Keys
def test_detect_aws_access_key(scanner: SecretScanner):
    text = "const AWS_KEY = 'AKIAIOSFODNN7EXAMPLE';"
    findings = scanner.scan_text(text)
    assert any(f.category == "aws_access_key" and f.severity == "CRITICAL" for f in findings)


def test_detect_aws_secret_key(scanner: SecretScanner):
    text = "aws_secret_access_key = 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'"
    findings = scanner.scan_text(text)
    assert any(f.category == "aws_secret_key" for f in findings)


# 2. Stripe Keys
def test_detect_stripe_live_secret_key(scanner: SecretScanner):
    key = "sk_" + "live_" + "fake_SECRET_12345678901234567890"
    text = f"const key = '{key}';"
    findings = scanner.scan_text(text)
    assert any(f.category == "stripe_api_key" and f.severity == "CRITICAL" for f in findings)


def test_detect_stripe_test_secret_key(scanner: SecretScanner):
    key = "sk_" + "test_" + "51MzXYZabc12345678901234567890"
    text = f"const key = '{key}';"
    findings = scanner.scan_text(text)
    assert any(f.category == "stripe_api_key" for f in findings)


def test_detect_stripe_publishable_key(scanner: SecretScanner):
    key = "pk_" + "live_" + "51MzXYZabc12345678901234567890"
    text = f"const key = '{key}';"
    findings = scanner.scan_text(text)
    assert any(f.category == "stripe_api_key" for f in findings)


# 3. GitHub Tokens
def test_detect_github_personal_access_token(scanner: SecretScanner):
    token = "ghp_" + "0123456789abcdefghijklmnopqrstuvwxyz01"
    text = f"export GITHUB_TOKEN='{token}';"
    findings = scanner.scan_text(text)
    assert any(f.category == "github_token" for f in findings)


def test_detect_github_fine_grained_pat(scanner: SecretScanner):
    token = "github_" + "pat_" + "11A0123456789abcdefghijklmnopqrstuvwxyz0123456789abcdef"
    text = f"export GITHUB_TOKEN='{token}';"
    findings = scanner.scan_text(text)
    assert any(f.category == "github_token" for f in findings)


# 4. Google Cloud API Key
def test_detect_google_api_key(scanner: SecretScanner):
    key = "AIza" + "SyA0123456789abcdefghijklmnopqrst-01"
    text = f"const API_KEY = '{key}';"
    findings = scanner.scan_text(text)
    assert any(f.category == "google_api_key" for f in findings)


# 5. Cryptographic Private Keys
def test_detect_rsa_private_key(scanner: SecretScanner):
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0\n-----END RSA PRIVATE KEY-----"
    findings = scanner.scan_text(text)
    assert any(f.category == "private_key" and f.severity == "CRITICAL" for f in findings)


def test_detect_ec_private_key(scanner: SecretScanner):
    text = "-----BEGIN EC PRIVATE KEY-----\nMHQCAQEEI..."
    findings = scanner.scan_text(text)
    assert any(f.category == "private_key" for f in findings)


def test_detect_openssh_private_key(scanner: SecretScanner):
    text = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNza..."
    findings = scanner.scan_text(text)
    assert any(f.category == "private_key" for f in findings)


# 6. Database Connection URIs
def test_detect_postgres_database_uri(scanner: SecretScanner):
    text = "DATABASE_URL=postgres://admin:SuperSecretPass123!@db.internal.corp:5432/production"
    findings = scanner.scan_text(text)
    assert any(f.category == "database_uri" and f.severity == "CRITICAL" for f in findings)


def test_detect_mysql_database_uri(scanner: SecretScanner):
    text = "MYSQL_URI=mysql://root:p@ssw0rd99@10.0.1.5:3306/billing"
    findings = scanner.scan_text(text)
    assert any(f.category == "database_uri" for f in findings)


def test_detect_mongodb_database_uri(scanner: SecretScanner):
    text = "MONGO_URL=mongodb://clusterAdmin:ClusterSecret2026@mongo.lan:27017/analytics"
    findings = scanner.scan_text(text)
    assert any(f.category == "database_uri" for f in findings)


def test_detect_redis_database_uri(scanner: SecretScanner):
    text = "REDIS_URL=redis://default:AuthToken7788@cache.internal:6379/0"
    findings = scanner.scan_text(text)
    assert any(f.category == "database_uri" for f in findings)


# 7. JWT Tokens
def test_detect_jwt_token(scanner: SecretScanner):
    jwt_sample = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    findings = scanner.scan_text(f"Authorization: Bearer {jwt_sample}")
    assert any(f.category == "jwt_token" for f in findings)


# 8. IP Addresses & Endpoints
def test_detect_private_ip_10_network(scanner: SecretScanner):
    text = "const target = '10.240.12.89';"
    findings = scanner.scan_text(text)
    assert any(f.category == "private_ip" for f in findings)


def test_detect_private_ip_192_168_network(scanner: SecretScanner):
    text = "const host = '192.168.1.100';"
    findings = scanner.scan_text(text)
    assert any(f.category == "private_ip" for f in findings)


def test_detect_private_ip_172_network(scanner: SecretScanner):
    text = "const host = '172.20.14.5';"
    findings = scanner.scan_text(text)
    assert any(f.category == "private_ip" for f in findings)


def test_ignore_localhost_ip(scanner: SecretScanner):
    text = "const loopback = '127.0.0.1';"
    findings = scanner.scan_text(text)
    assert not any(f.category == "private_ip" for f in findings)


def test_detect_internal_corporate_url(scanner: SecretScanner):
    text = "const endpoint = 'https://payments.billing.internal.corp/v1/charge';"
    findings = scanner.scan_text(text)
    assert any(f.category == "internal_url" for f in findings)


# 9. Email Addresses
def test_detect_sensitive_email_address(scanner: SecretScanner):
    text = "const ceo = 'satya.nadella@microsoft.com';"
    findings = scanner.scan_text(text)
    assert any(f.category == "email_address" for f in findings)


def test_ignore_example_com_email_address(scanner: SecretScanner):
    text = "const dummy = 'user@example.com';"
    findings = scanner.scan_text(text)
    assert not any(f.category == "email_address" for f in findings)


# 10. Shannon Entropy Analysis
def test_shannon_entropy_calculation_empty():
    assert calculate_shannon_entropy("") == 0.0


def test_shannon_entropy_low_for_repeated_string():
    low_entropy = calculate_shannon_entropy("aaaaaaaaaaaaaaaaaaaa")
    assert low_entropy == 0.0


def test_shannon_entropy_high_for_random_token():
    random_token = "4fA9zK8qL2vX7mP1wB6jC3tY5uR0sD8e"
    entropy = calculate_shannon_entropy(random_token)
    assert entropy > 4.5


def test_detect_high_entropy_secret_token(scanner: SecretScanner):
    text = "const secretKey = '8f94cb9e72da104ba9f03c28da5e8210';"
    findings = scanner.scan_text(text)
    assert any(f.category == "high_entropy" for f in findings)


# 11. Secret Masking
def test_mask_secret_long():
    masked = mask_secret("sk_live_1234567890abcdef")
    assert masked.startswith("sk_l")
    assert masked.endswith("cdef")
    assert "..." in masked


def test_mask_secret_short():
    assert mask_secret("short") == "****"


# 12. File Scanning & Multi-line
def test_scan_file_reports_line_numbers(tmp_path: Path, scanner: SecretScanner):
    f = tmp_path / "secrets.ts"
    stripe_key = "sk_" + "live_" + "testsecretkey1234567890123456"
    gh_token = "ghp_" + "0123456789abcdefghijklmnopqrstuvwxyz01"
    f.write_text(
        "// Line 1\n"
        "const safe = 1;\n"
        f"const stripe = '{stripe_key}';\n"
        "const anotherSafe = 2;\n"
        f"const token = '{gh_token}';\n",
        encoding="utf-8",
    )
    findings = scanner.scan_file(f, rel_path="secrets.ts")
    assert len(findings) >= 2
    assert any(item.line_number == 3 and item.category == "stripe_api_key" for item in findings)
    assert any(item.line_number == 5 and item.category == "github_token" for item in findings)


def test_scan_clean_file_yields_zero_findings(tmp_path: Path, scanner: SecretScanner):
    f = tmp_path / "clean.ts"
    f.write_text("export function sum(a: number, b: number) { return a + b; }", encoding="utf-8")
    findings = scanner.scan_file(f)
    assert len(findings) == 0
