/**
 * Lectura de certificados PKCS#12 (.p12 / .pfx) con node-forge.
 *
 * node-forge admite tanto los cifrados modernos (PBES2 + AES, el que usa OpenSSL 3)
 * como los antiguos (3DES / RC2), que son los que aún usan el Llavero de macOS,
 * Firefox o Windows al exportar certificados de la FNMT. La contraseña solo se usa
 * en memoria para abrir el archivo; nunca se guarda.
 */
import forge from 'node-forge';
import { aBinario, deBinario, utf8 } from './util';

const { asn1, pki } = forge;

export class ErrorCertificado extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = 'ErrorCertificado';
  }
}

export interface InfoCertificado {
  titular: string;
  emisor: string;
  validoDesde: Date;
  validoHasta: Date;
  numeroSerie: string;
  /** NIF/NIE si aparece en el certificado (serialNumber del sujeto). */
  nif?: string;
  organizacion?: string;
}

export interface Credencial {
  info: InfoCertificado;
  /** Certificado del firmante (DER original, sin reconstruir). */
  certificadoDer: Uint8Array;
  /** Resto de certificados del .p12 (cadena), en DER. */
  cadenaDer: Uint8Array[];
  tipoClave: 'RSA' | 'EC';
  /** OID del algoritmo de firma para SignerInfo.signatureAlgorithm. */
  algoritmoFirma: { oid: string; parametrosNulos: boolean };
  /** Firma `datos` (SHA-256 + clave privada) y devuelve el valor de la firma. */
  firmar(datos: Uint8Array): Promise<Uint8Array>;
}

/* ------------------------------------------------------------------------ */
/* Nombres y certificados (análisis directo del DER, válido para RSA y EC)   */
/* ------------------------------------------------------------------------ */

const OID_NOMBRES: Record<string, string> = {
  '2.5.4.3': 'CN', '2.5.4.4': 'SN', '2.5.4.42': 'GN', '2.5.4.5': 'serialNumber', '2.5.4.6': 'C',
  '2.5.4.7': 'L', '2.5.4.8': 'ST', '2.5.4.10': 'O', '2.5.4.11': 'OU', '2.5.4.97': 'organizationIdentifier',
  '1.2.840.113549.1.9.1': 'E',
};

function decodificarCadena(nodo: forge.asn1.Asn1): string {
  const v = typeof nodo.value === 'string' ? nodo.value : '';
  switch (nodo.type as number) {
    case asn1.Type.UTF8:
      try {
        return forge.util.decodeUtf8(v);
      } catch {
        return v;
      }
    case asn1.Type.BMPSTRING: {
      let s = '';
      for (let i = 0; i + 1 < v.length; i += 2) s += String.fromCharCode((v.charCodeAt(i) << 8) | v.charCodeAt(i + 1));
      return s;
    }
    case 28: { // UniversalString (UTF-32BE)
      let s = '';
      for (let i = 0; i + 3 < v.length; i += 4) {
        s += String.fromCodePoint(((v.charCodeAt(i) << 24) | (v.charCodeAt(i + 1) << 16) |
          (v.charCodeAt(i + 2) << 8) | v.charCodeAt(i + 3)) >>> 0);
      }
      return s;
    }
    default:
      return v;
  }
}

function leerNombre(nombre: forge.asn1.Asn1): Record<string, string> {
  const res: Record<string, string> = {};
  for (const rdn of nombre.value as forge.asn1.Asn1[]) {
    for (const atv of rdn.value as forge.asn1.Asn1[]) {
      const partes = atv.value as forge.asn1.Asn1[];
      const oid = asn1.derToOid(partes[0].value as string);
      const clave = OID_NOMBRES[oid] ?? oid;
      const valor = decodificarCadena(partes[1]);
      res[clave] = res[clave] ? `${res[clave]}, ${valor}` : valor;
    }
  }
  return res;
}

function nombreLegible(n: Record<string, string>): string {
  if (n.CN) return n.CN;
  if (n.O) return n.O;
  if (n.GN || n.SN) return [n.GN, n.SN].filter(Boolean).join(' ');
  return Object.values(n).join(', ') || 'Desconocido';
}

function leerFecha(nodo: forge.asn1.Asn1): Date {
  const v = nodo.value as string;
  return nodo.type === asn1.Type.UTCTIME ? asn1.utcTimeToDate(v) : asn1.generalizedTimeToDate(v);
}

export interface PartesCertificado {
  tbs: forge.asn1.Asn1;
  serie: forge.asn1.Asn1;
  emisor: forge.asn1.Asn1;
  sujeto: forge.asn1.Asn1;
  validez: forge.asn1.Asn1;
  spki: forge.asn1.Asn1;
}

export function partesCertificado(der: Uint8Array): PartesCertificado {
  const cert = asn1.fromDer(aBinario(der), { strict: false, parseAllBytes: false } as never);
  const tbs = (cert.value as forge.asn1.Asn1[])[0];
  const campos = tbs.value as forge.asn1.Asn1[];
  const d = campos[0].tagClass === asn1.Class.CONTEXT_SPECIFIC ? 1 : 0;
  return {
    tbs,
    serie: campos[d],
    emisor: campos[d + 2],
    validez: campos[d + 3],
    sujeto: campos[d + 4],
    spki: campos[d + 5],
  };
}

export function infoDeCertificado(der: Uint8Array): InfoCertificado {
  const p = partesCertificado(der);
  const sujeto = leerNombre(p.sujeto);
  const emisor = leerNombre(p.emisor);
  const validez = p.validez.value as forge.asn1.Asn1[];
  const serieHex = forge.util.bytesToHex(p.serie.value as string).replace(/^(00)+(?=.)/, '').toUpperCase();
  return {
    titular: nombreLegible(sujeto),
    emisor: nombreLegible(emisor),
    validoDesde: leerFecha(validez[0]),
    validoHasta: leerFecha(validez[1]),
    numeroSerie: serieHex,
    nif: sujeto.serialNumber?.replace(/^IDCES-/, ''),
    organizacion: sujeto.O,
  };
}

function esCertificadoCA(der: Uint8Array): boolean {
  try {
    const cert = pki.certificateFromAsn1(asn1.fromDer(aBinario(der)));
    const bc = cert.getExtension('basicConstraints') as { cA?: boolean } | null;
    return !!bc?.cA;
  } catch {
    return false;
  }
}

/* ------------------------------------------------------------------------ */
/* PKCS#12                                                                   */
/* ------------------------------------------------------------------------ */

interface BolsaCert { der: Uint8Array; idLocal?: string; cert: forge.pki.Certificate | null }
interface BolsaClave { clave: forge.pki.rsa.PrivateKey | null; asn1?: forge.asn1.Asn1; idLocal?: string }

function leerBolsas(p12Asn1: forge.asn1.Asn1, contrasena: string): { certs: BolsaCert[]; claves: BolsaClave[] } {
  // Se intercepta certificateFromAsn1 para quedarse con el DER original de cada
  // certificado (node-forge reconstruiría el certificado y podría alterarlo).
  const originales = new Map<forge.pki.Certificate, Uint8Array>();
  const original = pki.certificateFromAsn1;
  (pki as { certificateFromAsn1: typeof original }).certificateFromAsn1 = function (obj, computeHash) {
    const c = original.call(pki, obj, computeHash);
    try {
      originales.set(c, deBinario(asn1.toDer(obj).getBytes()));
    } catch {
      /* se reconstruirá más abajo */
    }
    return c;
  };
  let p12: forge.pkcs12.Pkcs12Pfx;
  try {
    p12 = forge.pkcs12.pkcs12FromAsn1(p12Asn1, false, contrasena);
  } finally {
    (pki as { certificateFromAsn1: typeof original }).certificateFromAsn1 = original;
  }
  const certs: BolsaCert[] = [];
  const claves: BolsaClave[] = [];
  for (const contenido of p12.safeContents) {
    for (const bolsa of contenido.safeBags) {
      const idLocal = bolsa.attributes?.localKeyId?.[0] as string | undefined;
      if (bolsa.type === pki.oids.certBag) {
        let der: Uint8Array | undefined;
        if (bolsa.cert) der = originales.get(bolsa.cert) ?? deBinario(asn1.toDer(pki.certificateToAsn1(bolsa.cert)).getBytes());
        else if (bolsa.asn1) der = deBinario(asn1.toDer(bolsa.asn1).getBytes());
        if (der) certs.push({ der, idLocal, cert: bolsa.cert ?? null });
      } else if (bolsa.type === pki.oids.pkcs8ShroudedKeyBag || bolsa.type === pki.oids.keyBag) {
        claves.push({ clave: (bolsa.key as forge.pki.rsa.PrivateKey) ?? null, asn1: bolsa.asn1, idLocal });
      }
    }
  }
  return { certs, claves };
}

const OID_EC = '1.2.840.10045.2.1';
const CURVAS: Record<string, string> = {
  '1.2.840.10045.3.1.7': 'P-256',
  '1.3.132.0.34': 'P-384',
  '1.3.132.0.35': 'P-521',
};

/** Convierte una firma ECDSA «r||s» (WebCrypto) a DER (SEQUENCE { r, s }). */
function ecdsaADer(firma: Uint8Array): Uint8Array {
  const mitad = firma.length / 2;
  const entero = (b: Uint8Array) => {
    let i = 0;
    while (i < b.length - 1 && b[i] === 0) i++;
    let v = b.slice(i);
    if (v[0] & 0x80) v = Uint8Array.from([0, ...v]);
    return asn1.create(asn1.Class.UNIVERSAL, asn1.Type.INTEGER, false, aBinario(v));
  };
  const seq = asn1.create(asn1.Class.UNIVERSAL, asn1.Type.SEQUENCE, true, [
    entero(firma.slice(0, mitad)), entero(firma.slice(mitad)),
  ]);
  return deBinario(asn1.toDer(seq).getBytes());
}

/**
 * Abre un .p12/.pfx con su contraseña y devuelve la credencial para firmar.
 * Lanza ErrorCertificado con un mensaje en español si algo falla.
 */
export function abrirP12(bytes: Uint8Array, contrasena: string): Credencial {
  let p12Asn1: forge.asn1.Asn1;
  try {
    p12Asn1 = asn1.fromDer(aBinario(bytes), { strict: false, parseAllBytes: false } as never);
  } catch {
    throw new ErrorCertificado('El archivo no es un certificado .p12/.pfx válido.');
  }
  let bolsas: { certs: BolsaCert[]; claves: BolsaClave[] };
  try {
    bolsas = leerBolsas(p12Asn1, contrasena);
  } catch (e) {
    const msg = (e as Error).message || '';
    // Contraseñas con tildes o eñes: el MAC usa la contraseña en UCS-2 (ya verificada),
    // pero PBES2 la usa en UTF-8. Se reintenta sin el MAC con la contraseña en UTF-8.
    if (!/MAC could not be verified/i.test(msg) && /[^\x00-\x7f]/.test(contrasena)) {
      try {
        const sinMac = { ...p12Asn1, value: (p12Asn1.value as forge.asn1.Asn1[]).slice(0, 2) } as forge.asn1.Asn1;
        bolsas = leerBolsas(sinMac, aBinario(utf8(contrasena)));
      } catch {
        throw new ErrorCertificado('No se pudo abrir el certificado. ¿La contraseña es correcta?');
      }
    } else if (/MAC could not be verified|Invalid password|wrong password|decrypt/i.test(msg)) {
      throw new ErrorCertificado('Contraseña incorrecta.');
    } else {
      throw new ErrorCertificado(`No se pudo abrir el certificado: ${msg}`);
    }
  }
  const { certs, claves } = bolsas;
  if (!certs.length) throw new ErrorCertificado('El archivo no contiene ningún certificado.');
  const clave = claves[0];
  if (!clave) throw new ErrorCertificado('El archivo no contiene la clave privada (exporta el certificado «con clave privada»).');

  // Certificado del firmante: el que comparte localKeyId con la clave, o el que
  // tiene la misma clave pública, o el primero que no sea de una autoridad (CA).
  let firmante = certs.find((c) => clave.idLocal && c.idLocal === clave.idLocal);
  if (!firmante && clave.clave) {
    firmante = certs.find((c) => {
      const pub = c.cert?.publicKey as forge.pki.rsa.PublicKey | undefined;
      return pub?.n && pub.n.equals(clave.clave!.n);
    });
  }
  firmante ??= certs.find((c) => !esCertificadoCA(c.der)) ?? certs[0];
  const cadenaDer = certs.filter((c) => c !== firmante).map((c) => c.der);
  const info = infoDeCertificado(firmante.der);

  if (clave.clave) {
    const privada = clave.clave;
    return {
      info,
      certificadoDer: firmante.der,
      cadenaDer,
      tipoClave: 'RSA',
      algoritmoFirma: { oid: '1.2.840.113549.1.1.1', parametrosNulos: true }, // rsaEncryption
      async firmar(datos: Uint8Array) {
        const md = forge.md.sha256.create();
        md.update(aBinario(datos));
        return deBinario(privada.sign(md));
      },
    };
  }

  // Clave de curva elíptica: node-forge no la admite, se firma con WebCrypto.
  const pkcs8 = clave.asn1;
  const alg = pkcs8 ? ((pkcs8.value as forge.asn1.Asn1[])[1]?.value as forge.asn1.Asn1[]) : undefined;
  const oidAlg = alg ? asn1.derToOid(alg[0].value as string) : '';
  const curva = alg && alg[1] && alg[1].type === asn1.Type.OID ? CURVAS[asn1.derToOid(alg[1].value as string)] : undefined;
  const subtle = (globalThis as { crypto?: Crypto }).crypto?.subtle;
  if (!pkcs8 || oidAlg !== OID_EC || !curva || !subtle) {
    throw new ErrorCertificado('El tipo de clave del certificado no es compatible (se admiten RSA y ECDSA P-256/384/521).');
  }
  const der = deBinario(asn1.toDer(pkcs8).getBytes());
  return {
    info,
    certificadoDer: firmante.der,
    cadenaDer,
    tipoClave: 'EC',
    algoritmoFirma: { oid: '1.2.840.10045.4.3.2', parametrosNulos: false }, // ecdsa-with-SHA256
    async firmar(datos: Uint8Array) {
      const k = await subtle.importKey('pkcs8', der as BufferSource, { name: 'ECDSA', namedCurve: curva }, false, ['sign']);
      const firma = new Uint8Array(await subtle.sign({ name: 'ECDSA', hash: 'SHA-256' }, k, datos as BufferSource));
      return ecdsaADer(firma);
    },
  };
}

/** Lee solo los datos del certificado (para mostrarlos tras importarlo). */
export function leerInfoP12(bytes: Uint8Array, contrasena: string): InfoCertificado {
  return abrirP12(bytes, contrasena).info;
}
