/**
 * Construcción de la firma CMS (PKCS#7 SignedData, «detached») para PAdES.
 *
 * Atributos firmados: contentType, signingTime, messageDigest y signingCertificateV2
 * (ESS, RFC 5035), como exige CAdES-BES. El resumen del documento se calcula fuera
 * (SHA-256 de los rangos de /ByteRange); aquí solo se firma el conjunto de atributos.
 * Opcionalmente se añade un sello de tiempo RFC 3161 como atributo no firmado.
 */
import forge from 'node-forge';
import type { Credencial } from './p12';
import { partesCertificado } from './p12';
import { aBinario, bytesAleatorios, deBinario, sha256 } from './util';

const { asn1 } = forge;
type Nodo = forge.asn1.Asn1;

export const OID = {
  data: '1.2.840.113549.1.7.1',
  signedData: '1.2.840.113549.1.7.2',
  contentType: '1.2.840.113549.1.9.3',
  messageDigest: '1.2.840.113549.1.9.4',
  signingTime: '1.2.840.113549.1.9.5',
  signingCertificateV2: '1.2.840.113549.1.9.16.2.47',
  timeStampToken: '1.2.840.113549.1.9.16.2.14',
  sha256: '2.16.840.1.101.3.4.2.1',
};

const U = asn1.Class.UNIVERSAL;
const T = asn1.Type;

export const secuencia = (v: Nodo[]): Nodo => asn1.create(U, T.SEQUENCE, true, v);
export const conjunto = (v: Nodo[]): Nodo => asn1.create(U, T.SET, true, v);
export const oid = (o: string): Nodo => asn1.create(U, T.OID, false, asn1.oidToDer(o).getBytes());
export const octetos = (b: Uint8Array): Nodo => asn1.create(U, T.OCTETSTRING, false, aBinario(b));
const nulo = (): Nodo => asn1.create(U, T.NULL, false, '');
const entero = (n: number): Nodo => asn1.create(U, T.INTEGER, false, asn1.integerToDer(n).getBytes());
const explicito = (tag: number, v: Nodo[]): Nodo => asn1.create(asn1.Class.CONTEXT_SPECIFIC, tag, true, v);
export const derDe = (n: Nodo): Uint8Array => deBinario(asn1.toDer(n).getBytes());
const nodoDe = (der: Uint8Array): Nodo => asn1.fromDer(aBinario(der), { strict: false, parseAllBytes: false } as never);

function hora(fecha: Date): Nodo {
  // UTCTime hasta 2049 (RFC 5280); GeneralizedTime a partir de 2050.
  return fecha.getUTCFullYear() < 2050
    ? asn1.create(U, T.UTCTIME, false, asn1.dateToUtcTime(fecha))
    : asn1.create(U, T.GENERALIZEDTIME, false, asn1.dateToGeneralizedTime(fecha));
}

function atributo(tipo: string, valores: Nodo[]): Nodo {
  return secuencia([oid(tipo), conjunto(valores)]);
}

/** DER exige que los elementos de un SET OF vayan ordenados por su codificación. */
function ordenarConjunto(elementos: Nodo[]): Nodo[] {
  const conDer = elementos.map((e) => ({ e, d: asn1.toDer(e).getBytes() }));
  conDer.sort((a, b) => (a.d < b.d ? -1 : a.d > b.d ? 1 : 0));
  return conDer.map((x) => x.e);
}

export interface OpcionesCms {
  /** SHA-256 del contenido firmado (los rangos de /ByteRange del PDF). */
  resumen: Uint8Array;
  credencial: Credencial;
  fecha: Date;
  /** Incluir el atributo signingTime (la hora del dispositivo). */
  incluirHoraFirma?: boolean;
  /** URL de una autoridad de sellado de tiempo (RFC 3161). Opcional. */
  urlTsa?: string;
}

export async function construirCms(o: OpcionesCms): Promise<Uint8Array> {
  const { credencial } = o;
  const partes = partesCertificado(credencial.certificadoDer);
  const algResumen = secuencia([oid(OID.sha256)]); // RFC 5754: sin parámetros

  // signingCertificateV2 { certs: [ ESSCertIDv2 { certHash, issuerSerial } ] }
  // (hashAlgorithm se omite porque su valor por defecto ya es SHA-256).
  const hashCert = await sha256(credencial.certificadoDer);
  const essCertIdV2 = secuencia([
    octetos(hashCert),
    secuencia([secuencia([explicito(4, [partes.emisor])]), partes.serie]),
  ]);

  const atributos: Nodo[] = [
    atributo(OID.contentType, [oid(OID.data)]),
    atributo(OID.messageDigest, [octetos(o.resumen)]),
    atributo(OID.signingCertificateV2, [secuencia([secuencia([essCertIdV2])])]),
  ];
  if (o.incluirHoraFirma !== false) atributos.push(atributo(OID.signingTime, [hora(o.fecha)]));
  const ordenados = ordenarConjunto(atributos);

  // Se firma la codificación DER del SET OF atributos (etiqueta 0x31).
  const firma = await credencial.firmar(derDe(conjunto(ordenados)));

  const algFirma = secuencia(
    credencial.algoritmoFirma.parametrosNulos
      ? [oid(credencial.algoritmoFirma.oid), nulo()]
      : [oid(credencial.algoritmoFirma.oid)],
  );

  const camposSignerInfo: Nodo[] = [
    entero(1),
    secuencia([partes.emisor, partes.serie]), // IssuerAndSerialNumber
    algResumen,
    asn1.create(asn1.Class.CONTEXT_SPECIFIC, 0, true, ordenados), // [0] IMPLICIT signedAttrs
    algFirma,
    octetos(firma),
  ];

  if (o.urlTsa) {
    const token = await solicitarSelloTiempo(o.urlTsa, firma);
    camposSignerInfo.push(
      asn1.create(asn1.Class.CONTEXT_SPECIFIC, 1, true, [atributo(OID.timeStampToken, [token])]),
    );
  }

  const certificados = [credencial.certificadoDer, ...credencial.cadenaDer].map(nodoDe);
  const signedData = secuencia([
    entero(1),
    conjunto([algResumen]),
    secuencia([oid(OID.data)]), // encapContentInfo sin contenido (firma separada)
    asn1.create(asn1.Class.CONTEXT_SPECIFIC, 0, true, certificados), // [0] IMPLICIT certificates
    conjunto([secuencia(camposSignerInfo)]),
  ]);
  return derDe(secuencia([oid(OID.signedData), explicito(0, [signedData])]));
}

/**
 * Pide un sello de tiempo RFC 3161 sobre el valor de la firma. Solo se usa si el
 * usuario lo activa; la TSA debe permitir peticiones desde el navegador (CORS).
 */
export async function solicitarSelloTiempo(url: string, firma: Uint8Array): Promise<Nodo> {
  const resumen = await sha256(firma);
  const nonce = bytesAleatorios(8);
  nonce[0] &= 0x7f;
  const peticion = secuencia([
    entero(1),
    secuencia([secuencia([oid(OID.sha256)]), octetos(resumen)]),
    asn1.create(U, T.INTEGER, false, aBinario(nonce)),
    asn1.create(U, T.BOOLEAN, false, String.fromCharCode(0xff)),
  ]);
  let respuesta: Response;
  try {
    respuesta = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/timestamp-query' },
      body: derDe(peticion) as BodyInit,
    });
  } catch {
    throw new Error('No se pudo contactar con el servidor de sellado de tiempo (¿sin conexión o no admite CORS?).');
  }
  if (!respuesta.ok) throw new Error(`El servidor de sellado de tiempo respondió con el error ${respuesta.status}.`);
  const datos = new Uint8Array(await respuesta.arrayBuffer());
  const resp = nodoDe(datos);
  const valores = resp.value as Nodo[];
  const estado = (valores[0].value as Nodo[])[0];
  const codigo = forge.util.createBuffer(estado.value as string).getInt(8 * (estado.value as string).length);
  if (codigo !== 0 && codigo !== 1) throw new Error('El servidor de sellado de tiempo rechazó la petición.');
  if (!valores[1]) throw new Error('La respuesta de sellado de tiempo no contiene el sello.');
  return valores[1];
}
