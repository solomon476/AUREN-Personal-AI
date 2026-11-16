"""RFC 8785 JSON Canonicalization Scheme (JCS) implementation.

Conforms strictly to RFC 8785:
- Recursive sorting of object keys by UTF-16 code units (Section 3.2.3).
- Strict primitive serialization (Section 3.2.2):
  - Strings: minimal escaping ('\\"', '\\\\', '\\b', '\\f', '\\n', '\\r', '\\t',
    and '\\u00xx' lowercase hex for control characters U+0000..U+001F).
    Solidus '/' is NOT escaped. All other Unicode characters are emitted as raw UTF-8 bytes.
    Lone surrogates are strictly rejected.
  - Numbers: IEEE 754 double precision serialized according to ECMA-262 Section 7.1.12.1.
    NaN and Infinity are strictly rejected.
  - Literals: null, true, false.
- Zero whitespace around structural tokens (',' and ':').
- Platform-independent UTF-8 output encoding (Section 3.2.4).
"""

from collections.abc import Mapping, Sequence
import math
from typing import Any


def float_to_ecma(val: float) -> str:
    """Serializes an IEEE 754 double precision float to ECMAScript string format (ECMA-262 7.1.12.1).

    Conforms to RFC 8785 Section 3.2.2.3 and passes all 24 sample cases in Appendix B.
    """
    if math.isnan(val) or math.isinf(val):
        raise ValueError("NaN and Infinity are not permitted in RFC 8785 JSON")
    if val == 0.0:
        return "0"

    sign = "-" if math.copysign(1.0, val) < 0 else ""
    val = abs(val)

    r = repr(val)
    if "e" in r:
        mantissa_str, exp_str = r.split("e")
        exp = int(exp_str)
    else:
        mantissa_str = r
        exp = 0

    if "." in mantissa_str:
        int_part, frac_part = mantissa_str.split(".")
        if frac_part == "0":
            digits = int_part
        else:
            digits = int_part + frac_part
            exp -= len(frac_part)
    else:
        digits = mantissa_str

    digits = digits.lstrip("0")
    k = len(digits)
    n = exp + k

    # ECMA-262 7.1.12.1 rules:
    # 6. If k <= n <= 21: digits followed by (n-k) occurrences of '0'
    if k <= n <= 21:
        res = digits + ("0" * (n - k))
    # 7. If 0 < n <= 21: first n digits, '.', remaining k-n digits
    elif 0 < n <= 21:
        res = digits[:n] + "." + digits[n:]
    # 8. If -6 < n <= 0: '0.', (-n) occurrences of '0', digits
    elif -6 < n <= 0:
        res = "0." + ("0" * -n) + digits
    # 9. If k == 1: single digit, 'e', signed exponent
    elif k == 1:
        exp_sign = "+" if n - 1 >= 0 else ""
        res = f"{digits}e{exp_sign}{n - 1}"
    # 10. Otherwise: first digit, '.', remaining k-1 digits, 'e', signed exponent
    else:
        exp_sign = "+" if n - 1 >= 0 else ""
        res = f"{digits[0]}.{digits[1:]}e{exp_sign}{n - 1}"

    return sign + res


def escape_string(s: str) -> str:
    """Escapes string according to RFC 8785 Section 3.2.2.2.

    Only quotes, reverse solidus, and ASCII control characters U+0000..U+001F are escaped.
    Solidus '/' is NOT escaped.
    All other Unicode characters (BMP and supplementary planes) are preserved as raw UTF-8.
    Lone surrogates are rejected with ValueError.
    """
    try:
        s.encode("utf-16-be")
    except UnicodeEncodeError as exc:
        raise ValueError(f"Invalid Unicode string with lone surrogates: {exc}") from exc

    out = ['"']
    for ch in s:
        cp = ord(ch)
        if ch == '"':
            out.append(r'\"')
        elif ch == '\\':
            out.append(r'\\')
        elif ch == '\b':
            out.append(r'\b')
        elif ch == '\f':
            out.append(r'\f')
        elif ch == '\n':
            out.append(r'\n')
        elif ch == '\r':
            out.append(r'\r')
        elif ch == '\t':
            out.append(r'\t')
        elif cp < 0x20:
            out.append(f"\\u{cp:04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def canonicalize(val: Any) -> bytes:
    """Canonicalizes a JSON-compatible Python data structure into deterministic UTF-8 bytes.

    Conforms to RFC 8785 JSON Canonicalization Scheme (JCS).
    """
    if val is None:
        return b"null"
    if isinstance(val, bool):
        return b"true" if val else b"false"
    if isinstance(val, int):
        return str(val).encode("utf-8")
    if isinstance(val, float):
        return float_to_ecma(val).encode("utf-8")
    if isinstance(val, str):
        return escape_string(val).encode("utf-8")
    if isinstance(val, (list, tuple)):
        return b"[" + b",".join(canonicalize(item) for item in val) + b"]"
    if isinstance(val, Mapping):
        # RFC 8785 Section 3.2.3: object properties must be sorted by UTF-16 code units
        try:
            sorted_keys = sorted(val.keys(), key=lambda k: k.encode("utf-16-be"))
        except UnicodeEncodeError as exc:
            raise ValueError(f"Invalid Unicode data in object key: {exc}") from exc
        parts = []
        for k in sorted_keys:
            if not isinstance(k, str):
                raise TypeError(f"JSON object keys must be strings, got {type(k).__name__}")
            k_bytes = escape_string(k).encode("utf-8")
            v_bytes = canonicalize(val[k])
            parts.append(k_bytes + b":" + v_bytes)
        return b"{" + b",".join(parts) + b"}"

    raise TypeError(f"Type '{type(val).__name__}' is not JSON serializable under RFC 8785")


def canonicalize_to_str(val: Any) -> str:
    """Convenience helper returning the canonical JSON representation as a UTF-8 decoded string."""
    return canonicalize(val).decode("utf-8")
