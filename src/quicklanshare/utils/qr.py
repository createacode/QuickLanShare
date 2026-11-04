"""二维码生成（data URI），供网页客户端与桌面界面共用。"""

from __future__ import annotations

import base64
import io

import qrcode


def qr_data_uri(url: str) -> str:
    """把 *url* 生成 PNG 二维码并编码为 ``data:image/png;base64,...``。"""
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="#0F172A", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"
