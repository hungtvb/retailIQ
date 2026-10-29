"""Render verified business evidence as the single RetailIQ user-facing reply.

Formatting is deliberately deterministic for the Week 1 demo. Specialist
agents own data retrieval and verification, not final answer presentation.
"""
from .analytics import month
from .language import is_vietnamese


def retailiq_reply(state: dict) -> dict:
    """The sole user-facing reply step; specialist identity stays in metadata."""
    rows = state.get('records') or []
    category = state['intent']
    if category == 'latest':
        if not rows:
            return {'answer': 'Chưa có dữ liệu ngày thêm vào danh mục.' if is_vietnamese(state['question']) else 'No catalog addition dates are available.'}
        if is_vietnamese(state['question']):
            return {'answer': 'Sản phẩm mới nhất theo ngày thêm vào danh mục mẫu: ' + '; '.join(f"{row['name']} ({row['sku']}), ngày {row['catalog_added_at']}" for row in rows) + '. Đây không phải ngày ra mắt thị trường.'}
        return {'answer': 'Newest products by date added to the sample catalog: ' + '; '.join(f"{row['name']} ({row['sku']}), {row['catalog_added_at']}" for row in rows) + '. These are not market release dates.'}
    if category == 'product' and rows and 'price_vnd' in rows[0]:
        item = rows[0]
        if is_vietnamese(state['question']):
            return {'answer': f"Giá niêm yết trong danh mục mẫu của {item['name']} ({item['sku']}) là {item['price_vnd']:,} VND."}
        return {'answer': f"The sample catalog list price for {item['name']} ({item['sku']}) is {item['price_vnd']:,} VND."}
    if not is_vietnamese(state['question']):
        return {'answer': state['answer']}
    if category == 'stock' and rows and len({row['sku'] for row in rows}) > 1:
        # A ranked group is multiple independent inventory checks. Never
        # attribute its combined availability to the first product.
        grouped = {}
        for row in rows:
            sku = row['sku']
            if sku not in grouped:
                grouped[sku] = {'name': row['name'], 'available': 0}
            grouped[sku]['available'] += row['available']
        context = (' theo thứ tự doanh số tháng ' + state['period']
                   if state.get('period') else '')
        details = '; '.join(
            f"{item['name']} ({sku}): {item['available']} có thể bán"
            for sku, item in grouped.items()
        )
        return {'answer': 'Tồn kho các sản phẩm' + context + ': ' + details + '.'}
    if category == 'stock' and rows:
        total = sum(row['available'] for row in rows)
        detail = '; '.join(f"{row['location']}: {row['available']} có thể bán" for row in rows)
        return {'answer': f"{rows[0]['name']} ({rows[0]['sku']}) hiện có {total} sản phẩm có thể bán. {detail}."}
    if category == 'revenue' and rows:
        total = sum(row['net_revenue_vnd'] for row in rows)
        return {'answer': f"Doanh thu thuần tháng {state.get('period', month())}: {total:,} VND từ đơn hoàn tất, sau giảm giá và trước hàng trả. " + '; '.join(f"{row['channel']}: {row['net_revenue_vnd']:,} VND" for row in rows) + '.'}
    if category == 'revenue' and not rows:
        return {'answer': f"Không có dữ liệu doanh thu từ đơn hoàn tất trong tháng {state.get('period', month())}."}
    if category == 'top' and rows:
        return {'answer': f"Sản phẩm bán chạy theo số lượng trong tháng {state.get('period', month())}: " + '; '.join(f"{i+1}. {row['name']} ({row['sku']}): {row['units_sold']} sản phẩm" for i, row in enumerate(rows)) + '.'}
    if category == 'top' and not rows:
        return {'answer': f"Không có dữ liệu sản phẩm bán chạy trong tháng {state.get('period', month())}."}
    if category == 'decision' and len(rows) > 1:
        leader = rows[0]
        available = sum(row['available'] for row in rows[1:])
        priority = 'Cần xem xét bổ sung hàng.' if available < leader['units_sold'] else 'Chưa cần ưu tiên bổ sung theo quy tắc đánh giá hiện tại.'
        return {'answer': f"Đánh giá bổ sung hàng tháng {month()}: {leader['name']} bán {leader['units_sold']} sản phẩm, còn {available} sản phẩm có thể bán. {priority} Đây không phải dự báo hay đơn đặt hàng."}
    if category == 'stock' and not rows:
        return {'answer': 'Vui lòng nêu tên sản phẩm hoặc mã SKU đã biết.'}
    if category == 'product' and not state.get('contexts'):
        return {'answer': 'Không tìm thấy tài liệu sản phẩm phù hợp để xác minh câu trả lời.'}
    return {'answer': state['answer']}
