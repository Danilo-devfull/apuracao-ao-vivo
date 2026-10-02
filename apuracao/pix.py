"""Gera o código Pix "copia e cola" (BR Code estático, sem valor fixo) e o QR em SVG."""
import io
import unicodedata
import segno


def _limpo(texto, limite):
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return t.upper()[:limite]


def _campo(id_, valor):
    return f"{id_}{len(valor):02d}{valor}"


def _crc16(payload):
    crc = 0xFFFF
    for byte in payload.encode():
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return f"{crc:04X}"


def br_code(chave, nome, cidade):
    conta = _campo("00", "br.gov.bcb.pix") + _campo("01", chave)
    payload = (
        _campo("00", "01")
        + _campo("26", conta)
        + _campo("52", "0000")
        + _campo("53", "986")
        + _campo("58", "BR")
        + _campo("59", _limpo(nome, 25))
        + _campo("60", _limpo(cidade, 15))
        + _campo("62", _campo("05", "***"))
        + "6304"
    )
    return payload + _crc16(payload)


def qr_svg(codigo):
    buf = io.BytesIO()
    segno.make(codigo, error="m").save(buf, kind="svg", scale=6, border=2, xmldecl=False, svgns=True)
    return buf.getvalue().decode()