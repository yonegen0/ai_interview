"""Guard the vendored botocore CA bundle against compromised eMudhra trust paths."""

import ssl
from pathlib import Path

import botocore


def test_bundled_ca_store_distrusts_emudhra_linked_comodo_root():
    bundle = Path(botocore.__file__).with_name("cacert.pem")
    assert bundle.is_file()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cafile=str(bundle))
    assert context.verify_mode == ssl.CERT_REQUIRED
    subjects = {
        value
        for cert in context.get_ca_certs()
        for part in cert["subject"]
        for key, value in part
        if key == "commonName"
    }
    assert len(subjects) > 20
    assert "AAA Certificate Services" not in subjects
    assert "emSign ECC Root CA - G3" not in subjects
