/**
 * Comprobación básica de las firmas digitales de un PDF (sin conexión):
 *  - integridad: el SHA-256 de los rangos de /ByteRange coincide con messageDigest
 *    y la firma criptográfica de los atributos es correcta con el certificado;
 *  - alcance: si la firma cubre todo el archivo o hay cambios posteriores.
 * No se valida la confianza en la autoridad emisora ni la revocación.
 */
import forge from 'node-forge';
import { PDFArray, PDFDict, PDFDocument, PDFHexString, PDFName, PDFNumber, PDFString } from 'pdf-lib';
import { OID } from './cms';
import { infoDeCertificado, partesCertificado } from './p12';
import { aBinario, concatenar, deBinario, sha256 } from './util';

const { asn1 } = forge;
type Nodo = forge.asn1.Asn1;

export interface EstadoFirma {
  campo: string;
  firmante: string;
  emisor: string;
  fecha?: Date;
  motivo?: string;
  lugar?: string;
  subFilter: string;
  integra: boolean;
  cubreTodo: boolean;
  caducado?: boolean;
  resumen: string;
}

function texto(v: unknown): string | undefined {
  if (v instanceof PDFString || v instanceof PDFHexString) return v.decodeText();
  return undefined;
}

function fechaDePdf(s?: string): Date | undefined {
  const m = s && /D:(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?([Z+-])?(\d{2})?'?(\d{2})?/.exec(s);
  if (!m) return undefined;
  const [, a, me = '01', d = '01', h = '00', mi = '00', se = '00', signo, oh = '00', om = '00'] = m;
  let ms = Date.UTC(+a, +me - 1, +d, +h, +mi, +se);
  if (signo === '+' || signo === '-') ms -= (signo === '+' ? 1 : -1) * (+oh * 60 + +om) * 60000;
  else if (!signo) ms += new Date().getTimezoneOffset() * 60000;
  return new Date(ms);
}

function camposFirma(doc: PDFDocument): Array<{ nombre: string; v: PDFDict }> {
  const res: Array<{ nombre: string; v: PDFDict }> = [];
  const acro = doc.catalog.lookupMaybe(PDFName.of('AcroForm'), PDFDict);
  const visitar = (arr: PDFArray | undefined, prefijo: string, prof: number) => {
    if (!arr || prof > 20) return;
    for (let i = 0; i < arr.size(); i++) {
      const c = doc.context.lookup(arr.get(i));
      if (!(c instanceof PDFDict)) continue;
      const parte = texto(c.lookup(PDFName.of('T'))) ?? '';
      const nombre = prefijo && parte ? `${prefijo}.${parte}` : parte || prefijo;
      const v = c.lookup(PDFName.of('V'));
      if (c.lookup(PDFName.of('FT')) === PDFName.of('Sig') && v instanceof PDFDict) res.push({ nombre, v });
      visitar(c.lookupMaybe(PDFName.of('Kids'), PDFArray), nombre, prof + 1);
    }
  };
  visitar(acro?.lookupMaybe(PDFName.of('Fields'), PDFArray), '', 0);
  return res;
}

/** Comprobación rápida de si un PDF contiene alguna firma (sin analizarlo entero). */
export function pareceFirmado(bytes: Uint8Array): boolean {
  const patron = [0x2f, 0x42, 0x79, 0x74, 0x65, 0x52, 0x61, 0x6e, 0x67, 0x65]; // /ByteRange
  externo: for (let i = 0; i <= bytes.length - patron.length; i++) {
    for (let j = 0; j < patron.length; j++) if (bytes[i + j] !== patron[j]) continue externo;
    return true;
  }
  return false;
}

async function comprobarCms(cmsDer: Uint8Array, contenido: Uint8Array): Promise<{ ok: boolean; certDer?: Uint8Array; error?: string }> {
  const raiz = asn1.fromDer(aBinario(cmsDer), { strict: false, parseAllBytes: false } as never);
  const sd = ((raiz.value as Nodo[])[1].value as Nodo[])[0].value as Nodo[];
  let i = 3;
  const certs: Uint8Array[] = [];
  if (sd[i] && sd[i].tagClass === asn1.Class.CONTEXT_SPECIFIC && sd[i].type === 0) {
    for (const c of sd[i].value as Nodo[]) certs.push(deBinario(asn1.toDer(c).getBytes()));
    i++;
  }
  while (sd[i] && sd[i].tagClass === asn1.Class.CONTEXT_SPECIFIC) i++; // CRLs
  const signerInfo = (sd[i].value as Nodo[])[0].value as Nodo[];
  const sid = signerInfo[1];
  const sidDer = asn1.toDer(sid).getBytes();
  const certDer = certs.find((c) => {
    const p = partesCertificado(c);
    return asn1.toDer(asn1.create(asn1.Class.UNIVERSAL, asn1.Type.SEQUENCE, true, [p.emisor, p.serie])).getBytes() === sidDer;
  }) ?? certs[0];
  if (!certDer) return { ok: false, error: 'La firma no incluye el certificado del firmante.' };
  const resumen = await sha256(contenido);
  let j = 3;
  let atributos: Nodo | undefined;
  if (signerInfo[j].tagClass === asn1.Class.CONTEXT_SPECIFIC && signerInfo[j].type === 0) atributos = signerInfo[j++];
  const algFirma = asn1.derToOid((signerInfo[j].value as Nodo[])[0].value as string);
  const firma = signerInfo[j + 1].value as string;
  let datosFirmados: string;
  if (atributos) {
    const md = (atributos.value as Nodo[]).find((a) => asn1.derToOid((a.value as Nodo[])[0].value as string) === OID.messageDigest);
    const valor = md ? (((md.value as Nodo[])[1].value as Nodo[])[0].value as string) : '';
    if (valor !== aBinario(resumen)) return { ok: false, certDer, error: 'El documento se ha modificado después de firmarlo.' };
    datosFirmados = asn1.toDer(asn1.create(asn1.Class.UNIVERSAL, asn1.Type.SET, true, atributos.value as Nodo[])).getBytes();
  } else {
    datosFirmados = aBinario(contenido);
  }
  const p = partesCertificado(certDer);
  if (algFirma.startsWith('1.2.840.10045')) {
    const subtle = (globalThis as { crypto?: Crypto }).crypto?.subtle;
    if (!subtle) return { ok: false, certDer, error: 'No se puede comprobar una firma ECDSA en este contexto.' };
    const spki = deBinario(asn1.toDer(p.spki).getBytes());
    const curvaOid = asn1.derToOid((((p.spki.value as Nodo[])[0].value as Nodo[])[1]).value as string);
    const curva = { '1.2.840.10045.3.1.7': 'P-256', '1.3.132.0.34': 'P-384', '1.3.132.0.35': 'P-521' }[curvaOid];
    if (!curva) return { ok: false, certDer, error: 'Curva elíptica no admitida.' };
    const clave = await subtle.importKey('spki', spki as BufferSource, { name: 'ECDSA', namedCurve: curva }, false, ['verify']);
    const sig = asn1.fromDer(firma).value as Nodo[];
    const tam = curva === 'P-256' ? 32 : curva === 'P-384' ? 48 : 66;
    const parte = (n: Nodo) => {
      let b = deBinario(n.value as string);
      while (b.length > tam && b[0] === 0) b = b.slice(1);
      const r = new Uint8Array(tam);
      r.set(b, tam - b.length);
      return r;
    };
    const ok = await subtle.verify({ name: 'ECDSA', hash: 'SHA-256' }, clave, concatenar([parte(sig[0]), parte(sig[1])]) as BufferSource,
      deBinario(datosFirmados) as BufferSource);
    return ok ? { ok, certDer } : { ok, certDer, error: 'La firma criptográfica no es válida.' };
  }
  const cert = forge.pki.certificateFromAsn1(asn1.fromDer(aBinario(certDer)));
  const md = forge.md.sha256.create();
  md.update(datosFirmados);
  let ok = false;
  try {
    ok = (cert.publicKey as forge.pki.rsa.PublicKey).verify(md.digest().getBytes(), firma);
  } catch {
    ok = false;
  }
  return ok ? { ok, certDer } : { ok, certDer, error: 'La firma criptográfica no es válida.' };
}

export async function verificarFirmas(bytes: Uint8Array): Promise<EstadoFirma[]> {
  if (!pareceFirmado(bytes)) return [];
  const doc = await PDFDocument.load(bytes, { updateMetadata: false, ignoreEncryption: true });
  const resultados: EstadoFirma[] = [];
  for (const { nombre, v } of camposFirma(doc)) {
    const subFilter = (v.lookup(PDFName.of('SubFilter')) as PDFName | undefined)?.decodeText() ?? '';
    const base: EstadoFirma = {
      campo: nombre, firmante: texto(v.lookup(PDFName.of('Name'))) ?? '?', emisor: '?',
      fecha: fechaDePdf(texto(v.lookup(PDFName.of('M')))), motivo: texto(v.lookup(PDFName.of('Reason'))),
      lugar: texto(v.lookup(PDFName.of('Location'))), subFilter, integra: false, cubreTodo: false, resumen: '',
    };
    try {
      const br = v.lookup(PDFName.of('ByteRange'), PDFArray).asArray().map((x) => (x as PDFNumber).asNumber());
      const contenidos = v.lookup(PDFName.of('Contents'));
      const cms = contenidos instanceof PDFHexString ? contenidos.asBytes()
        : contenidos instanceof PDFString ? contenidos.asBytes() : new Uint8Array();
      const [a, b, c, d] = br;
      if (br.length !== 4 || a !== 0 || b <= 0 || c <= b || c + d > bytes.length) throw new Error('/ByteRange no válido.');
      base.cubreTodo = c + d === bytes.length;
      const r = await comprobarCms(cms, concatenar([bytes.subarray(0, b), bytes.subarray(c, c + d)]));
      if (r.certDer) {
        const info = infoDeCertificado(r.certDer);
        base.firmante = info.titular;
        base.emisor = info.emisor;
        base.caducado = info.validoHasta.getTime() < (base.fecha ?? new Date()).getTime();
      }
      base.integra = r.ok;
      base.resumen = r.ok
        ? base.cubreTodo
          ? 'La firma es válida y el documento no se ha modificado desde que se firmó.'
          : 'La firma es válida, pero el documento tiene cambios posteriores (p. ej., otras firmas o anotaciones añadidas después).'
        : `LA FIRMA NO ES VÁLIDA: ${r.error ?? 'el documento se ha alterado.'}`;
    } catch (e) {
      base.resumen = `No se pudo comprobar la firma: ${(e as Error).message}`;
    }
    resultados.push(base);
  }
  return resultados;
}
