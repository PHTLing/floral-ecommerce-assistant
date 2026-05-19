# app/utils/constants.py

FLOWER_TYPE_ALIASES = {
    "hoa hướng dương": ["hoa hướng dương", "hướng dương", "sunflower"],
    "hoa hồng": ["hoa hồng", "hồng", "rose", "only rose"],
    "hoa sen đá": ["hoa sen đá", "sen đá", "succulent"],
    "hoa cúc": ["hoa cúc", "cúc", "daisy"],
    "hoa ly": ["hoa ly", "ly", "lily", "loa kèn"],
    "hoa lan": ["hoa lan", "lan", "orchid"],
    "hoa baby": ["hoa baby", "baby"],
    "hoa tulip": ["hoa tulip", "tulip"],
    "hoa đồng tiền": ["hoa đồng tiền", "đồng tiền"],
    "hoa cẩm chướng": ["hoa cẩm chướng", "cẩm chướng", "carnation"],
    "hoa cẩm tú cầu": ["hoa cẩm tú cầu", "cẩm tú cầu", "hydrangea"],
    "hoa mẫu đơn": ["hoa mẫu đơn", "mẫu đơn", "peony"],
    "hoa cát tường": ["hoa cát tường", "cát tường", "lisianthus"],
    "hoa lan hồ điệp": ["hoa lan hồ điệp", "lan hồ điệp", "phalaenopsis"],
}

COLOR_ALIASES = {
    "đỏ": ["đỏ", "red"],
    "vàng": ["vàng", "yellow"],
    "trắng": ["trắng", "white"],
    "hồng": ["hồng", "pink"],
    "cam": ["cam", "orange"],
    "tím": ["tím", "purple", "violet"],
    "xanh lá": ["xanh lá", "green"],
    "xanh dương": ["xanh dương", "blue"],
    "xanh ngọc": ["xanh ngọc", "turquoise"],
}

STYLE_ALIASES = {
    "đơn giản": ["đơn giản", "simple", "minimal"],
    "sang trọng": ["sang trọng", "luxury", "elegant"],
    "nhẹ nhàng": ["nhẹ nhàng", "gentle", "soft"],
    "hiện đại": ["hiện đại", "modern"],
    "pastel": ["pastel"],
}

COLORS = list(COLOR_ALIASES.keys())
STYLES = list(STYLE_ALIASES.keys())
FLOWER_TYPES = list(FLOWER_TYPE_ALIASES.keys())