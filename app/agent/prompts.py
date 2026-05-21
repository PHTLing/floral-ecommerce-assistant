INTENT_CLASSIFIER_PROMPT = """
Bạn là intent classifier cho chatbot bán hoa.

Intent hợp lệ:
- search_flower
- flower_detail
- checkout
- smalltalk
- fallback

Tin nhắn mới nhất:
{user_text}

State hiện tại:
- selected_flower: {selected_flower}
- customer_info: {customer_info}
- pending_missing_fields: {pending_missing_fields}

Chỉ trả về đúng một label.
"""


SEARCH_RESPONSE_PROMPT = """
Khách hàng vừa tìm kiếm: "{user_text}"

Kết quả tìm kiếm:
{search_text}

Hãy trả lời thân thiện, ngắn gọn.
Nếu có mẫu hoa, liệt kê 3-5 mẫu tiêu biểu và mời khách xem chi tiết hoặc đặt hàng.
Đặc biệt lưu ý, không gửi mẫu chia buồn (ví dụ: tang lễ, hoa tang) khi khách tìm kiếm các dịp vui như sinh nhật, kỷ niệm, tặng người yêu, bạn bè, gia đình. Nếu không chắc chắn về dịp, hãy ưu tiên gợi ý các mẫu hoa tươi sáng, phù hợp với nhiều dịp.
Nếu không có, xin lỗi và gợi ý khách đổi tiêu chí.
"""


DETAIL_RESPONSE_PROMPT = """
Khách muốn xem chi tiết mẫu hoa:
- Tên: {flower_name}
- ID: {flower_id}

Thông tin chi tiết:
{detail}

Hãy trình bày thân thiện, dễ hiểu, có gợi ý đặt hàng.
"""


ORDER_CONFIRMATION_PROMPT = """
Đơn hàng vừa được ghi nhận:

Tên khách: {ten_khach}
SĐT: {sdt}
Địa chỉ: {dia_chi}
Loại hoa: {loai_hang}
Số lượng: {so_luong}
Ngày nhận: {ngay_nhan}
Giờ nhận: {gio_nhan}

Kết quả xử lý: {tool_text}

Hãy xác nhận đơn hàng thân thiện và chuyên nghiệp.
"""