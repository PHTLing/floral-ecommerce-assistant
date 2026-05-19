# Vai trò
# Chỉ là LangChain tool wrapper.
from langchain_core.tools import tool

from app.schemas.flower import SearchFlowerInput
from app.services.flower_search_service import search_flowers_service
from app.services.flower_detail_service import get_flower_detail_service
from app.services.order_service import create_order

@tool(args_schema=SearchFlowerInput)
def search_flowers(
    query: str,
    type_of_flower: str = None,
    min_price: int = None,
    max_price: int = None,
    color: str = None,
    style: str = None,
):
    return search_flowers_service(
        query=query,
        type_of_flower=type_of_flower,
        min_price=min_price,
        max_price=max_price,
        color=color,
        style=style,
    )

@tool
def get_flower_details(
    flower_name: str, 
    flower_id: int = None
):
    return get_flower_detail_service(
        flower_name=flower_name,
        flower_id=flower_id
    )

@tool
def process_order(
    ten_khach: str,
    sdt: str,
    dia_chi: str,
    loai_hang: str,
    so_luong: str,
    ngay_nhan: str,
    gio_nhan: str,
):
    return create_order({
        "ten_khach": ten_khach,
        "sdt": sdt,
        "dia_chi": dia_chi,
        "loai_hang": loai_hang,
        "so_luong": so_luong,
        "ngay_nhan": ngay_nhan,
        "gio_nhan": gio_nhan,
    })