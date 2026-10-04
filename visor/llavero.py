"""Certificados del sistema (Llavero de macOS) para firmar sin exportar nada.

La clave privada nunca sale del Llavero: se le pide a macOS que firme (SecKeyCreateSignature).
La primera vez, macOS pregunta al usuario si permite el uso de la clave («Permitir siempre»
evita que vuelva a preguntar). También aparecen las tarjetas criptográficas (DNIe…) que
macOS reconozca mediante CryptoTokenKit.
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

from asn1crypto import algos, x509
from pyhanko.sign import signers
from pyhanko_certvalidator.registry import SimpleCertificateStore

DISPONIBLE = False
if sys.platform == "darwin":
    try:
        import Security as S
        from Foundation import NSData
        DISPONIBLE = True
    except ImportError:
        pass

# Algoritmos de SecKeyCreateSignature: el sistema calcula el resumen del mensaje.
_ALG_RSA = {
    "sha256": "kSecKeyAlgorithmRSASignatureMessagePKCS1v15SHA256",
    "sha384": "kSecKeyAlgorithmRSASignatureMessagePKCS1v15SHA384",
    "sha512": "kSecKeyAlgorithmRSASignatureMessagePKCS1v15SHA512",
}
_ALG_EC = {
    "sha256": "kSecKeyAlgorithmECDSASignatureMessageX962SHA256",
    "sha384": "kSecKeyAlgorithmECDSASignatureMessageX962SHA384",
    "sha512": "kSecKeyAlgorithmECDSASignatureMessageX962SHA512",
}


class ErrorLlavero(Exception):
    pass


@dataclass
class CertificadoSistema:
    titular: str
    emisor: str
    valido_desde: datetime
    valido_hasta: datetime
    huella: str              # SHA-1 en hexadecimal, como la muestra Acceso a Llaveros
    en_tarjeta: bool
    cert: x509.Certificate
    _identidad: object = field(repr=False)

    @property
    def caducado(self) -> bool:
        return self.valido_hasta < datetime.now(timezone.utc)

    @property
    def aun_no_valido(self) -> bool:
        return self.valido_desde > datetime.now(timezone.utc)

    @property
    def utilizable(self) -> bool:
        return not self.caducado and not self.aun_no_valido


def _nombre(name: x509.Name) -> str:
    datos = name.native
    for clave in ("common_name", "organization_name"):
        if datos.get(clave):
            return str(datos[clave])
    return name.human_friendly


def _sirve_para_firmar(cert: x509.Certificate) -> bool:
    if cert.ca:
        return False
    uso = cert.key_usage_value
    if uso is None:
        return True
    usos = set(uso.native)
    return bool(usos & {"digital_signature", "non_repudiation"})


def _consulta(extra: dict) -> list:
    consulta = {
        S.kSecClass: S.kSecClassIdentity,
        S.kSecReturnRef: True,
        S.kSecMatchLimit: S.kSecMatchLimitAll,
    }
    consulta.update(extra)
    estado, resultado = S.SecItemCopyMatching(consulta, None)
    if estado != 0 or resultado is None:
        return []
    return list(resultado) if isinstance(resultado, (list, tuple)) or hasattr(resultado, "count") else [resultado]


def listar_certificados(rutas_llaveros: list[str] | None = None) -> list[CertificadoSistema]:
    """Certificados con clave privada aptos para firmar, ordenados: vigentes primero.

    `rutas_llaveros` limita la búsqueda a llaveros concretos (se usa en las pruebas).
    """
    if not DISPONIBLE:
        return []
    identidades = []
    if rutas_llaveros:
        llaveros = []
        for ruta in rutas_llaveros:
            estado, kc = S.SecKeychainOpen(ruta.encode() if isinstance(ruta, str) else ruta, None)
            if estado == 0 and kc is not None:
                llaveros.append(kc)
        identidades += [(i, False) for i in _consulta({S.kSecMatchSearchList: llaveros})]
    else:
        identidades += [(i, False) for i in _consulta({})]
        try:  # tarjetas inteligentes (DNIe, tarjetas FNMT…) vía CryptoTokenKit
            identidades += [(i, True) for i in _consulta({S.kSecAttrAccessGroup: S.kSecAttrAccessGroupToken})]
        except Exception:
            pass

    vistos: dict[str, CertificadoSistema] = {}
    for identidad, en_tarjeta in identidades:
        estado, cert_ref = S.SecIdentityCopyCertificate(identidad, None)
        if estado != 0 or cert_ref is None:
            continue
        der = bytes(S.SecCertificateCopyData(cert_ref))
        try:
            cert = x509.Certificate.load(der)
            if not _sirve_para_firmar(cert):
                continue
            validez = cert["tbs_certificate"]["validity"]
        except Exception:
            continue
        huella = hashlib.sha1(der).hexdigest().upper()
        if huella in vistos and not en_tarjeta:
            continue
        vistos[huella] = CertificadoSistema(
            titular=_nombre(cert.subject),
            emisor=_nombre(cert.issuer),
            valido_desde=validez["not_before"].native,
            valido_hasta=validez["not_after"].native,
            huella=huella,
            en_tarjeta=en_tarjeta,
            cert=cert,
            _identidad=identidad,
        )
    return sorted(vistos.values(), key=lambda c: (not c.utilizable, c.titular.lower(), -c.valido_hasta.timestamp()))


def _cadena(identidad, cert_firmante: x509.Certificate) -> list[x509.Certificate]:
    """Certificados intermedios (y raíz) que macOS encuentra para el certificado."""
    estado, cert_ref = S.SecIdentityCopyCertificate(identidad, None)
    estado, confianza = S.SecTrustCreateWithCertificates([cert_ref], S.SecPolicyCreateBasicX509(), None)
    if estado != 0 or confianza is None:
        return []
    S.SecTrustEvaluateWithError(confianza, None)  # construye la cadena aunque no sea de confianza
    cadena = S.SecTrustCopyCertificateChain(confianza) or []
    resultado = []
    for ref in cadena:
        c = x509.Certificate.load(bytes(S.SecCertificateCopyData(ref)))
        if c.dump() != cert_firmante.dump():
            resultado.append(c)
    return resultado


class FirmanteLlavero(signers.Signer):
    """Firmante de pyHanko que delega la operación criptográfica en el Llavero de macOS."""

    def __init__(self, certificado: CertificadoSistema):
        if not DISPONIBLE:
            raise ErrorLlavero("El Llavero solo está disponible en macOS.")
        self.certificado = certificado
        estado, clave = S.SecIdentityCopyPrivateKey(certificado._identidad, None)
        if estado != 0 or clave is None:
            raise ErrorLlavero("No se ha podido acceder a la clave privada del certificado.")
        self._clave = clave
        algoritmo_clave = certificado.cert.public_key.algorithm  # 'rsa' o 'ec'
        self._es_ec = algoritmo_clave == "ec"
        if self._es_ec:
            self._tam_firma = 2 * ((certificado.cert.public_key.bit_size + 7) // 8) + 8
            mecanismo = "sha256_ecdsa"
        else:
            self._tam_firma = (certificado.cert.public_key.bit_size + 7) // 8
            mecanismo = "sha256_rsa"
        super().__init__(
            signing_cert=certificado.cert,
            cert_registry=SimpleCertificateStore.from_certs(_cadena(certificado._identidad, certificado.cert)),
            signature_mechanism=algos.SignedDigestAlgorithm({"algorithm": mecanismo}),
        )

    async def async_sign_raw(self, data: bytes, digest_algorithm: str, dry_run=False) -> bytes:
        if dry_run:
            # Estimación de tamaño: no molestamos al usuario con el aviso del Llavero.
            return bytes(self._tam_firma)
        tabla = _ALG_EC if self._es_ec else _ALG_RSA
        nombre = tabla.get(digest_algorithm.lower())
        if nombre is None:
            raise ErrorLlavero(f"Algoritmo de resumen no admitido: {digest_algorithm}")
        algoritmo = getattr(S, nombre)
        firma, error = S.SecKeyCreateSignature(self._clave, algoritmo, NSData.dataWithBytes_length_(data, len(data)), None)
        if firma is None:
            codigo = error.code() if error is not None else 0
            if codigo in (-128, -25293, -25308):  # cancelado / autenticación denegada
                raise ErrorLlavero("Se ha cancelado el permiso para usar el certificado.")
            descripcion = error.localizedDescription() if error is not None else "error desconocido"
            raise ErrorLlavero(f"macOS no ha podido firmar con el certificado: {descripcion}")
        return bytes(firma)
