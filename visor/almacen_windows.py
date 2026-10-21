"""Certificados del almacén de Windows («Personal» del usuario) para firmar sin exportar nada.

La clave privada nunca sale del almacén: se le pide a Windows que firme el resumen (CNG,
NCryptSignHash). Si el certificado está en una tarjeta (DNIe, tarjeta FNMT…), Windows muestra
su propia ventana para el PIN. Los certificados de software importados con proveedores antiguos
de CryptoAPI también funcionan (se reabren con el proveedor que admite SHA-256).
"""

from __future__ import annotations

import ctypes
import hashlib
import sys
from ctypes import wintypes as W
from dataclasses import dataclass

from asn1crypto import algos, x509

DISPONIBLE = sys.platform == "win32"

CERT_KEY_PROV_INFO_PROP_ID = 2
CRYPT_ACQUIRE_COMPARE_KEY_FLAG = 0x4
CRYPT_ACQUIRE_PREFER_NCRYPT_KEY_FLAG = 0x20000
CERT_NCRYPT_KEY_SPEC = 0xFFFFFFFF
BCRYPT_PAD_PKCS1 = 0x2
HP_HASHVAL = 2
PROV_RSA_AES = 24
MS_ENH_RSA_AES_PROV = "Microsoft Enhanced RSA and AES Cryptographic Provider"
CRYPT_MACHINE_KEYSET = 0x20
CALG = {"sha256": 0x800C, "sha384": 0x800D, "sha512": 0x800E}
BCRYPT_ALG = {"sha256": "SHA256", "sha384": "SHA384", "sha512": "SHA512"}
CANCELADO = {0x8010006E, 0x800704C7, 0x80090036, 0x000004C7}  # tarjeta/usuario cancelaron


class ErrorAlmacen(Exception):
    pass


if DISPONIBLE:
    class CERT_CONTEXT(ctypes.Structure):
        _fields_ = [("dwCertEncodingType", W.DWORD), ("pbCertEncoded", ctypes.POINTER(ctypes.c_ubyte)),
                    ("cbCertEncoded", W.DWORD), ("pCertInfo", ctypes.c_void_p), ("hCertStore", ctypes.c_void_p)]

    class CRYPT_KEY_PROV_INFO(ctypes.Structure):
        _fields_ = [("pwszContainerName", W.LPWSTR), ("pwszProvName", W.LPWSTR), ("dwProvType", W.DWORD),
                    ("dwFlags", W.DWORD), ("cProvParam", W.DWORD), ("rgProvParam", ctypes.c_void_p),
                    ("dwKeySpec", W.DWORD)]

    class BCRYPT_PKCS1_PADDING_INFO(ctypes.Structure):
        _fields_ = [("pszAlgId", W.LPCWSTR)]

    PCCERT_CONTEXT = ctypes.POINTER(CERT_CONTEXT)
    _crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    _ncrypt = ctypes.WinDLL("ncrypt")
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

    _crypt32.CertOpenSystemStoreW.argtypes = [ctypes.c_void_p, W.LPCWSTR]
    _crypt32.CertOpenSystemStoreW.restype = ctypes.c_void_p
    _crypt32.CertCloseStore.argtypes = [ctypes.c_void_p, W.DWORD]
    _crypt32.CertEnumCertificatesInStore.argtypes = [ctypes.c_void_p, PCCERT_CONTEXT]
    _crypt32.CertEnumCertificatesInStore.restype = PCCERT_CONTEXT
    _crypt32.CertDuplicateCertificateContext.argtypes = [PCCERT_CONTEXT]
    _crypt32.CertDuplicateCertificateContext.restype = PCCERT_CONTEXT
    _crypt32.CertFreeCertificateContext.argtypes = [PCCERT_CONTEXT]
    _crypt32.CertGetCertificateContextProperty.argtypes = [PCCERT_CONTEXT, W.DWORD, ctypes.c_void_p,
                                                           ctypes.POINTER(W.DWORD)]
    _crypt32.CertGetCertificateContextProperty.restype = W.BOOL
    _crypt32.CryptAcquireCertificatePrivateKey.argtypes = [
        PCCERT_CONTEXT, W.DWORD, ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(W.DWORD), ctypes.POINTER(W.BOOL)]
    _crypt32.CryptAcquireCertificatePrivateKey.restype = W.BOOL
    _ncrypt.NCryptSignHash.argtypes = [ctypes.c_size_t, ctypes.c_void_p, ctypes.c_char_p, W.DWORD,
                                       ctypes.c_void_p, W.DWORD, ctypes.POINTER(W.DWORD), W.DWORD]
    _ncrypt.NCryptSignHash.restype = ctypes.c_long
    _ncrypt.NCryptFreeObject.argtypes = [ctypes.c_size_t]
    _advapi32.CryptAcquireContextW.argtypes = [ctypes.POINTER(ctypes.c_size_t), W.LPCWSTR, W.LPCWSTR,
                                               W.DWORD, W.DWORD]
    _advapi32.CryptAcquireContextW.restype = W.BOOL
    _advapi32.CryptCreateHash.argtypes = [ctypes.c_size_t, ctypes.c_uint, ctypes.c_size_t, W.DWORD,
                                          ctypes.POINTER(ctypes.c_size_t)]
    _advapi32.CryptCreateHash.restype = W.BOOL
    _advapi32.CryptSetHashParam.argtypes = [ctypes.c_size_t, W.DWORD, ctypes.c_char_p, W.DWORD]
    _advapi32.CryptSetHashParam.restype = W.BOOL
    _advapi32.CryptSignHashW.argtypes = [ctypes.c_size_t, W.DWORD, W.LPCWSTR, W.DWORD, ctypes.c_void_p,
                                         ctypes.POINTER(W.DWORD)]
    _advapi32.CryptSignHashW.restype = W.BOOL
    _advapi32.CryptDestroyHash.argtypes = [ctypes.c_size_t]
    _advapi32.CryptReleaseContext.argtypes = [ctypes.c_size_t, W.DWORD]


class Identidad:
    """Certificado del almacén con clave privada (mantiene vivo su contexto de Windows)."""

    def __init__(self, contexto, der: bytes, proveedor: str):
        self._contexto = contexto
        self.der = der
        self.proveedor = proveedor

    @property
    def en_tarjeta(self) -> bool:
        p = self.proveedor.lower()
        return "smart card" in p or "tarjeta" in p or "dnie" in p or "card" in p

    def __del__(self):
        try:
            _crypt32.CertFreeCertificateContext(self._contexto)
        except Exception:
            pass


def _der(contexto) -> bytes:
    c = contexto.contents
    return ctypes.string_at(c.pbCertEncoded, c.cbCertEncoded)


@dataclass
class InfoClave:
    contenedor: str
    proveedor: str
    flags: int
    tipo_clave: int


def _info_proveedor(contexto) -> InfoClave | None:
    tam = W.DWORD(0)
    if not _crypt32.CertGetCertificateContextProperty(contexto, CERT_KEY_PROV_INFO_PROP_ID, None, ctypes.byref(tam)):
        return None  # sin clave privada asociada
    buf = ctypes.create_string_buffer(tam.value)
    if not _crypt32.CertGetCertificateContextProperty(contexto, CERT_KEY_PROV_INFO_PROP_ID, buf, ctypes.byref(tam)):
        return None
    # Las cadenas apuntan dentro de `buf`: se copian mientras sigue vivo
    info = ctypes.cast(buf, ctypes.POINTER(CRYPT_KEY_PROV_INFO)).contents
    return InfoClave(info.pwszContainerName or "", info.pwszProvName or "", info.dwFlags, info.dwKeySpec)


def certificados_almacen(nombre: str) -> list[bytes]:
    """DER de todos los certificados de un almacén del sistema («MY», «CA», «ROOT»…)."""
    if not DISPONIBLE:
        return []
    almacen = _crypt32.CertOpenSystemStoreW(None, nombre)
    if not almacen:
        return []
    resultado, contexto = [], None
    try:
        while True:
            contexto = _crypt32.CertEnumCertificatesInStore(almacen, contexto)
            if not contexto:
                break
            resultado.append(_der(contexto))
    finally:
        _crypt32.CertCloseStore(almacen, 0)
    return resultado


def identidades() -> list[Identidad]:
    """Certificados del almacén «Personal» que tienen clave privada (incluidos los de tarjetas)."""
    if not DISPONIBLE:
        return []
    almacen = _crypt32.CertOpenSystemStoreW(None, "MY")
    if not almacen:
        return []
    resultado, contexto = [], None
    try:
        while True:
            contexto = _crypt32.CertEnumCertificatesInStore(almacen, contexto)
            if not contexto:
                break
            info = _info_proveedor(contexto)
            if info is None:
                continue
            resultado.append(Identidad(_crypt32.CertDuplicateCertificateContext(contexto), _der(contexto),
                                       info.proveedor))
    finally:
        _crypt32.CertCloseStore(almacen, 0)  # los contextos duplicados lo mantienen vivo
    return resultado


def cadena(cert: x509.Certificate) -> list[x509.Certificate]:
    """Intermedios (y raíz) del certificado, buscados en los almacenes «CA» y «ROOT» de Windows."""
    candidatos = []
    for nombre in ("CA", "ROOT"):
        for der in certificados_almacen(nombre):
            try:
                candidatos.append(x509.Certificate.load(der))
            except Exception:
                pass
    resultado, actual, vistos = [], cert, {cert.dump()}
    for _ in range(8):
        if actual.self_signed in ("yes", "maybe"):
            break
        aki = actual.authority_key_identifier
        emisor = next((c for c in candidatos if c.subject == actual.issuer and c.dump() not in vistos
                       and (aki is None or c.key_identifier is None or c.key_identifier == aki)), None)
        if emisor is None:
            break
        resultado.append(emisor)
        vistos.add(emisor.dump())
        actual = emisor
    return resultado


def raices() -> list[x509.Certificate]:
    resultado = []
    for der in certificados_almacen("ROOT"):
        try:
            resultado.append(x509.Certificate.load(der))
        except Exception:
            pass
    return resultado


def _error(estado: int, accion: str) -> ErrorAlmacen:
    codigo = estado & 0xFFFFFFFF
    if codigo in CANCELADO:
        return ErrorAlmacen("Se ha cancelado el uso del certificado (o el PIN de la tarjeta).")
    return ErrorAlmacen(f"Windows no ha podido {accion} (código 0x{codigo:08X}).")


def firmar(identidad: Identidad, datos: bytes, resumen: str, es_ec: bool) -> bytes:
    """Firma `datos` con la clave del certificado. Devuelve la firma lista para CMS (ECDSA en DER)."""
    resumen = resumen.lower()
    if resumen not in BCRYPT_ALG:
        raise ErrorAlmacen(f"Algoritmo de resumen no admitido: {resumen}")
    h = hashlib.new(resumen, datos).digest()
    clave, tipo, liberar = ctypes.c_size_t(0), W.DWORD(0), W.BOOL(False)
    if not _crypt32.CryptAcquireCertificatePrivateKey(
            identidad._contexto, CRYPT_ACQUIRE_PREFER_NCRYPT_KEY_FLAG | CRYPT_ACQUIRE_COMPARE_KEY_FLAG, None,
            ctypes.byref(clave), ctypes.byref(tipo), ctypes.byref(liberar)):
        raise _error(ctypes.get_last_error(), "abrir la clave privada del certificado")
    try:
        if tipo.value == CERT_NCRYPT_KEY_SPEC:
            firma = _firmar_cng(clave.value, h, resumen, es_ec)
        else:
            firma = _firmar_capi(identidad, clave.value, tipo.value, h, resumen)
    finally:
        if liberar.value:
            if tipo.value == CERT_NCRYPT_KEY_SPEC:
                _ncrypt.NCryptFreeObject(clave.value)
            else:
                _advapi32.CryptReleaseContext(clave.value, 0)
    if es_ec:  # CNG devuelve r‖s; CMS espera la estructura DER
        firma = algos.DSASignature.from_p1363(firma).dump()
    return firma


def _firmar_cng(clave: int, h: bytes, resumen: str, es_ec: bool) -> bytes:
    relleno = None
    flags = 0
    if not es_ec:
        info = BCRYPT_PKCS1_PADDING_INFO(BCRYPT_ALG[resumen])
        relleno, flags = ctypes.byref(info), BCRYPT_PAD_PKCS1
    tam = W.DWORD(0)
    estado = _ncrypt.NCryptSignHash(clave, relleno, h, len(h), None, 0, ctypes.byref(tam), flags)
    if estado != 0:
        raise _error(estado, "preparar la firma")
    salida = ctypes.create_string_buffer(tam.value)
    estado = _ncrypt.NCryptSignHash(clave, relleno, h, len(h), salida, tam, ctypes.byref(tam), flags)
    if estado != 0:
        raise _error(estado, "firmar con el certificado")
    return salida.raw[:tam.value]


def _firmar_capi(identidad: Identidad, proveedor: int, tipo_clave: int, h: bytes, resumen: str) -> bytes:
    """CryptoAPI antigua. Si su proveedor no admite SHA-256, se reabre la clave con el que sí."""
    try:
        return _firmar_capi_con(proveedor, tipo_clave, h, resumen)
    except ErrorAlmacen:
        info = _info_proveedor(identidad._contexto)
        if info is None:
            raise
        prov = ctypes.c_size_t(0)
        if not _advapi32.CryptAcquireContextW(ctypes.byref(prov), info.contenedor, MS_ENH_RSA_AES_PROV,
                                              PROV_RSA_AES, info.flags & CRYPT_MACHINE_KEYSET):
            raise
        try:
            return _firmar_capi_con(prov.value, info.tipo_clave or tipo_clave, h, resumen)
        finally:
            _advapi32.CryptReleaseContext(prov.value, 0)


def _firmar_capi_con(proveedor: int, tipo_clave: int, h: bytes, resumen: str) -> bytes:
    resumen_h = ctypes.c_size_t(0)
    if not _advapi32.CryptCreateHash(proveedor, CALG[resumen], 0, 0, ctypes.byref(resumen_h)):
        raise _error(ctypes.get_last_error(), "preparar el resumen")
    try:
        if not _advapi32.CryptSetHashParam(resumen_h.value, HP_HASHVAL, h, 0):
            raise _error(ctypes.get_last_error(), "preparar el resumen")
        tam = W.DWORD(0)
        if not _advapi32.CryptSignHashW(resumen_h.value, tipo_clave, None, 0, None, ctypes.byref(tam)):
            raise _error(ctypes.get_last_error(), "preparar la firma")
        salida = ctypes.create_string_buffer(tam.value)
        if not _advapi32.CryptSignHashW(resumen_h.value, tipo_clave, None, 0, salida, ctypes.byref(tam)):
            raise _error(ctypes.get_last_error(), "firmar con el certificado")
        return salida.raw[:tam.value][::-1]  # CryptoAPI la devuelve al revés (little-endian)
    finally:
        _advapi32.CryptDestroyHash(resumen_h.value)
