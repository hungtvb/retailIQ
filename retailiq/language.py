"""Small, deterministic language hint for the demo's English/Vietnamese UI."""
import re


def is_vietnamese(text: str) -> bool:
    if re.search(r'[ăâđêôơưĂÂĐÊÔƠƯàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]', text):
        return True
    return bool(re.search(r'\b(bao nhiêu|là gì|xin chào|cảm ơn|giúp tôi|sản phẩm|doanh thu|bán chạy|tồn kho)\b', text.casefold()))
