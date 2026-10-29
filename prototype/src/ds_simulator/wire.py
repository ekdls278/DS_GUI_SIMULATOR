"""Explicit raw bytes only: never guess an Excel ICD's binary representation."""
import re

MAX_RAW_BYTES = 65536


def encode_raw(kind, text):
    if not isinstance(text, str) or len(text) > MAX_RAW_BYTES * 6:
        raise ValueError('송신 입력은 너무 길거나 형식이 잘못되었습니다.')
    if kind == 'hex':
        tokens = text.split()
        parts = [token[2:] if token.lower().startswith('0x') else token for token in tokens]
        if not parts or any(not re.fullmatch(r'[0-9a-fA-F]+', part) or len(part) % 2 for part in parts):
            raise ValueError('HEX는 두 자리 바이트로 입력하세요. 예: AA BB 00 01 또는 AABB0001')
        data = bytes.fromhex(''.join(parts))
    elif kind == 'utf8':
        try:
            data = text.encode('utf-8')
        except UnicodeError:
            raise ValueError('UTF-8로 변환할 수 없는 문자입니다.') from None
    else:
        raise ValueError('지원하지 않는 송신 형식입니다.')
    if not 1 <= len(data) <= MAX_RAW_BYTES:
        raise ValueError(f'송신 데이터는 1~{MAX_RAW_BYTES:,}바이트여야 합니다.')
    return data
