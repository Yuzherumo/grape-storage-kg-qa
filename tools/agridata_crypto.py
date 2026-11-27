"""agridata 站点前端加解密的最小实现（纯标准库，便于任何环境复现）。

包含两块：
1. RSA：解析站点公钥（SubjectPublicKeyInfo DER），PKCS#1 v1.5 加密，
   用于生成请求信封里的 `common.aes16`。
2. AES-128-ECB：解密服务端回包（服务端用请求里的 aes16 当密钥）。

AES 部分用 FIPS-197 附录 C.1 的官方测试向量自检，
不依赖 cryptography / pycryptodome / requests。
"""
from __future__ import annotations

import base64
import os


# --------------------------------------------------------------------------
# DER / RSA
# --------------------------------------------------------------------------
def _der_header(buf: bytes, pos: int) -> tuple[int, int, int]:
    """解析 TLV 头，返回 (tag, 内容起始偏移, 内容长度)。"""
    tag = buf[pos]
    pos += 1
    first = buf[pos]
    pos += 1
    if first < 0x80:
        length = first
    else:
        nbytes = first & 0x7F
        length = int.from_bytes(buf[pos : pos + nbytes], "big")
        pos += nbytes
    return tag, pos, length


def _der_children(buf: bytes, start: int, end: int) -> list[tuple[int, int, int, int]]:
    """遍历内容区间里的子 TLV，返回 [(tag, tlv起点, 内容起点, 内容长度)]。"""
    out = []
    pos = start
    while pos < end:
        tag, cstart, clen = _der_header(buf, pos)
        out.append((tag, pos, cstart, clen))
        pos = cstart + clen
    return out


def rsa_public_key(b64_der: str) -> tuple[int, int]:
    """从 SubjectPublicKeyInfo 的 base64 中取出 (modulus, exponent)。"""
    der = base64.b64decode(b64_der)
    tag, start, length = _der_header(der, 0)
    if tag != 0x30:
        raise ValueError("不是 SubjectPublicKeyInfo SEQUENCE")
    kids = _der_children(der, start, start + length)
    if [k[0] for k in kids] != [0x30, 0x03]:
        raise ValueError(f"SPKI 子节点异常: {[hex(k[0]) for k in kids]}")
    bit_start, bit_len = kids[1][2], kids[1][3]
    inner = der[bit_start + 1 : bit_start + bit_len]  # 跳过 unused-bits 字节
    tag, rstart, rlen = _der_header(inner, 0)
    if tag != 0x30:
        raise ValueError("不是 RSAPublicKey SEQUENCE")
    ints = _der_children(inner, rstart, rstart + rlen)
    if [k[0] for k in ints] != [0x02, 0x02]:
        raise ValueError("RSAPublicKey 应含两个 INTEGER")
    n = int.from_bytes(inner[ints[0][2] : ints[0][2] + ints[0][3]], "big")
    e = int.from_bytes(inner[ints[1][2] : ints[1][2] + ints[1][3]], "big")
    return n, e


def rsa_encrypt_pkcs1v15(text: str, b64_der: str) -> str:
    """PKCS#1 v1.5 加密（与前端 jsencrypt 行为一致），返回 base64。"""
    n, e = rsa_public_key(b64_der)
    k = (n.bit_length() + 7) // 8
    msg = text.encode("utf-8")
    pad_len = k - 3 - len(msg)
    if pad_len < 8:
        raise ValueError("明文过长，无法用该 RSA 密钥加密")
    padding = bytes(int.from_bytes(os.urandom(1), "big") % 255 + 1 for _ in range(pad_len))
    em = b"\x00\x02" + padding + b"\x00" + msg
    c = pow(int.from_bytes(em, "big"), e, n)
    return base64.b64encode(c.to_bytes(k, "big")).decode("ascii")


# --------------------------------------------------------------------------
# AES-128-ECB（解密用；S 盒按定义生成，不硬编码大表）
# --------------------------------------------------------------------------
def _gf_mul(a: int, b: int) -> int:
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= 0x1B
        b >>= 1
    return p


def _gf_pow(a: int, e: int) -> int:
    r = 1
    while e:
        if e & 1:
            r = _gf_mul(r, a)
        a = _gf_mul(a, a)
        e >>= 1
    return r


def _build_sbox() -> tuple[list[int], list[int]]:
    sbox = [0] * 256
    for x in range(256):
        inv = 0 if x == 0 else _gf_pow(x, 254)
        s = inv
        for shift in (1, 2, 3, 4):
            s ^= ((inv << shift) | (inv >> (8 - shift))) & 0xFF
        sbox[x] = s ^ 0x63
    inv_sbox = [0] * 256
    for i, v in enumerate(sbox):
        inv_sbox[v] = i
    return sbox, inv_sbox


SBOX, INV_SBOX = _build_sbox()
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]


def _expand_key(key: bytes) -> list[list[int]]:
    if len(key) != 16:
        raise ValueError("仅支持 AES-128（16 字节密钥）")
    words = [list(key[4 * i : 4 * i + 4]) for i in range(4)]
    for i in range(4, 44):
        temp = list(words[i - 1])
        if i % 4 == 0:
            temp = temp[1:] + temp[:1]
            temp = [SBOX[b] for b in temp]
            temp[0] ^= _RCON[i // 4 - 1]
        words.append([words[i - 4][j] ^ temp[j] for j in range(4)])
    return [sum(words[4 * r : 4 * r + 4], []) for r in range(11)]


def _add_round_key(state: list[int], rk: list[int]) -> None:
    for i in range(16):
        state[i] ^= rk[i]


def _inv_shift_rows(s: list[int]) -> list[int]:
    out = [0] * 16
    for r in range(4):
        for c in range(4):
            out[r + 4 * c] = s[r + 4 * ((c - r) % 4)]
    return out


def _inv_mix_columns(s: list[int]) -> list[int]:
    out = [0] * 16
    for c in range(4):
        a = s[4 * c : 4 * c + 4]
        out[4 * c + 0] = _gf_mul(a[0], 14) ^ _gf_mul(a[1], 11) ^ _gf_mul(a[2], 13) ^ _gf_mul(a[3], 9)
        out[4 * c + 1] = _gf_mul(a[0], 9) ^ _gf_mul(a[1], 14) ^ _gf_mul(a[2], 11) ^ _gf_mul(a[3], 13)
        out[4 * c + 2] = _gf_mul(a[0], 13) ^ _gf_mul(a[1], 9) ^ _gf_mul(a[2], 14) ^ _gf_mul(a[3], 11)
        out[4 * c + 3] = _gf_mul(a[0], 11) ^ _gf_mul(a[1], 13) ^ _gf_mul(a[2], 9) ^ _gf_mul(a[3], 14)
    return out


def aes128_ecb_decrypt_block(block: bytes, round_keys: list[list[int]]) -> bytes:
    state = list(block)
    _add_round_key(state, round_keys[10])
    for r in range(9, 0, -1):
        state = _inv_shift_rows(state)
        state = [INV_SBOX[b] for b in state]
        _add_round_key(state, round_keys[r])
        state = _inv_mix_columns(state)
    state = _inv_shift_rows(state)
    state = [INV_SBOX[b] for b in state]
    _add_round_key(state, round_keys[0])
    return bytes(state)


def aes128_ecb_decrypt(data: bytes, key: bytes) -> bytes:
    if len(data) % 16:
        raise ValueError("密文长度不是 16 的倍数")
    rks = _expand_key(key)
    return b"".join(aes128_ecb_decrypt_block(data[i : i + 16], rks) for i in range(0, len(data), 16))


def pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        raise ValueError("空数据无法去填充")
    pad = data[-1]
    if pad < 1 or pad > 16 or data[-pad:] != bytes([pad]) * pad:
        raise ValueError("PKCS#7 填充非法")
    return data[:-pad]


def _aes_ecb_decrypt_fast(data: bytes, key: bytes) -> bytes | None:
    """若装了 cryptography，用 OpenSSL 实现（大数据集回包快 3 个数量级）。"""
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except Exception:  # noqa: BLE001  # 未安装则回退纯 Python
        return None
    decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    return decryptor.update(data) + decryptor.finalize()


def aes_decrypt_b64(b64_content: str, key_text: str) -> bytes:
    """服务端回包解密：base64 密文 + 密钥为请求里生成的 aes16（16 字符）。"""
    raw = base64.b64decode(b64_content)
    key = key_text.encode("utf-8")
    fast = _aes_ecb_decrypt_fast(raw, key)
    if fast is not None:
        return pkcs7_unpad(fast)
    return pkcs7_unpad(aes128_ecb_decrypt(raw, key))


def self_test() -> None:
    """FIPS-197 C.1 官方向量 + PKCS#7 + 公钥解析自检。"""
    key = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
    ct = bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a")
    rks = _expand_key(key)
    assert aes128_ecb_decrypt_block(ct, rks).hex() == "00112233445566778899aabbccddeeff"
    # 加密侧也验证一下（用逆过程重建：仅校验子密钥与 S 盒一致性）
    assert SBOX[0x00] == 0x63 and SBOX[0x53] == 0xED and INV_SBOX[0x63] == 0x00
    assert pkcs7_unpad(b"abc" + b"\x05" * 5) == b"abc"
    n, e = rsa_public_key(
        "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC49WMjbNPNK+NIw+H+PJ7oLEzy6b14eYXB1vi17Kc5Qe2J"
        "/bhQsXO9qw+T91fANliBGeMZlnWK56G0KpHxpj40Wi58VGGOo3XfCKWqOGASLXR42ppspdIV9QKzSg4GoilcD"
        "PAlsAOSSbpv3O1ckPSWOzG4QpagaKQpYZpSIFBzCQIDAQAB"
    )
    assert e == 65537 and n.bit_length() == 1024, (e, n.bit_length())
    if __name__ == "__main__":
        print("self-test OK: AES-128-ECB / PKCS#7 / RSA(1024, e=65537)")


if __name__ == "__main__":
    self_test()
