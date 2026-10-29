"""Read-only retail question lookup and deterministic reply formatting.

No orchestration imports: LangGraph and the offline entrypoint share these
business operations without depending on each other.
"""
from .analytics import products, inventory, revenue, top, month, requested_month
from .retrieval import retrieve
from .language import is_vietnamese


def intent(q):
 q=q.lower()
 if any(x in q for x in ['top seller','best seller','bán chạy']):return 'top'
 if any(x in q for x in ['revenue','doanh thu','sales performance']):return 'revenue'
 if any(x in q for x in ['stock','inventory','tồn kho','in stock','available units','còn hàng','còn bao nhiêu']):return 'stock'
 if any(x in q for x in ['product','sản phẩm','spec','specification','warranty','bảo hành','charger','laptop','usb-c','alphabook','guide','manual','policy','chính sách']):return 'product'
 if product_sku(q):return 'product'
 return 'general'
def product_sku(q):
 """Recognize only a unique full product name or an explicit SKU."""
 import re
 text=q.casefold()
 matches={p['sku'] for p in products()
          if re.search(r'(?<![\w-])'+re.escape(p['sku'].casefold())+r'(?![\w-])',text)
          or re.search(r'(?<!\w)'+re.escape(p['name'].casefold())+r'(?!\w)',text)}
 return next(iter(matches)) if len(matches)==1 else None

def wants_single_top_product(q: str) -> bool:
 import re
 text=q.casefold()
 if re.search(r'\b(top\s*[2-9]|top\s*10|top\s+five|top\s+products|best sellers|top sellers)\b',text):
  return False
 return bool(re.search(r'bán chạy nhất|bán chạy số 1|sản phẩm bán chạy nhất|best seller\b|top\s*1\b|number one seller|#1 seller',text))

def wants_single_latest_product(q: str) -> bool:
 import re
 text=q.casefold()
 if re.search(r'\b(top\s*[2-9]|top\s*10|latest products|newest products|new products)\b',text):
  return False
 return 'mới nhất' in text or bool(re.search(r'\b(latest product|newest product|top\s*1)\b',text))
def do(q,category):
 if category=='latest':
  from .domain.analytics import newest_products
  rows=newest_products(1 if wants_single_latest_product(q) else 5)
  answer=retailiq_reply({'question':q,'intent':'latest','records':rows,'answer':''})['answer']
  return {'answer':answer,'records':rows,'contexts':[]}
 if category=='general':
  from .language import is_vietnamese
  answer=('Xin chào! Tôi là RetailIQ. Bạn có thể hỏi về tồn kho, doanh thu, hàng bán chạy hoặc thông tin sản phẩm.'
          if is_vietnamese(q) else
          'Hello! I am RetailIQ. You can ask about inventory, revenue, top sellers, or product information.')
  return {'answer':answer,'records':[],'contexts':[]}
 if category=='stock':
  sku=product_sku(q)
  if not sku:return {'answer':'Please specify a known product name or SKU.','records':[],'contexts':[]}
  rows=inventory(sku)
  if not rows:
   return {'answer':f'No inventory records are available for SKU {sku}.', 'records':[], 'contexts':[]}
  total=sum(r['available'] for r in rows)
  return {'answer':f"{rows[0]['name']} ({sku}): {total} available units across locations. "+'; '.join(f"{r['location']}: {r['available']} available (on hand {r['on_hand']}, reserved {r['reserved']})" for r in rows)+'.','records':rows,'contexts':[]}
 if category=='revenue':
  period=requested_month(q)
  rows=revenue(period) if period!=month() else revenue()
  if not rows:
   return {'answer':f'No completed-order sales records for {period}.', 'records':[], 'contexts':[], 'period':period}
  total=sum(r['net_revenue_vnd'] for r in rows)
  return {'answer':f'Net sales revenue in {period}: {total:,} VND (completed orders, after line discounts, before returns). '+'; '.join(f"{r['channel']}: {r['net_revenue_vnd']:,} VND" for r in rows)+'.','records':rows,'contexts':[], 'period':period}
 if category=='top':
  period=requested_month(q)
  ranked=top(period) if period!=month() else top()
  rows=ranked[:1] if wants_single_top_product(q) else ranked
  if not rows:
   return {'answer':f'No completed-order top sellers for {period}.','records':[],'contexts':[], 'period':period}
  return {'answer':f'Top sellers by units in {period} (completed orders): '+ '; '.join(f"{i+1}. {r['name']} ({r['sku']}): {r['units_sold']} units" for i,r in enumerate(rows))+'.','records':rows,'contexts':[], 'period':period}
 if category=='product' and any(word in q.casefold() for word in ('giá','price','cost')) and product_sku(q):
  from .domain.analytics import catalog_product
  item=catalog_product(product_sku(q))
  rows=[item] if item else []
  answer=retailiq_reply({'question':q,'intent':'product','records':rows,'answer':''})['answer'] if rows else 'No matching catalog product.'
  return {'answer':answer,'records':rows,'contexts':[]}
 docs=retrieve(q)
 return {'answer':f"Source: {docs[0]['source']}\n{docs[0]['text']}" if docs else 'No matching product documentation.','records':[],'contexts':docs}

def retailiq_reply(state: dict) -> dict:
    """The sole user-facing reply step; specialist identity stays in metadata."""
    rows = state.get('records') or []
    category = state['intent']
    if category == 'latest':
        if not rows:
            return {'answer': 'Chưa có dữ liệu ngày thêm vào danh mục.' if is_vietnamese(state['question']) else 'No catalog addition dates are available.'}
        if is_vietnamese(state['question']):
            return {'answer': 'Sản phẩm mới nhất theo ngày thêm vào danh mục demo: ' + '; '.join(f"{row['name']} ({row['sku']}), ngày {row['catalog_added_at']}" for row in rows) + '. Đây không phải ngày ra mắt thị trường.'}
        return {'answer': 'Newest products by date added to the demo catalog: ' + '; '.join(f"{row['name']} ({row['sku']}), {row['catalog_added_at']}" for row in rows) + '. These are not market release dates.'}
    if category == 'product' and rows and 'price_vnd' in rows[0]:
        item = rows[0]
        if is_vietnamese(state['question']):
            return {'answer': f"Giá niêm yết trong danh mục demo của {item['name']} ({item['sku']}) là {item['price_vnd']:,} VND."}
        return {'answer': f"The demo catalog list price for {item['name']} ({item['sku']}) is {item['price_vnd']:,} VND."}
    if not is_vietnamese(state['question']):
        return {'answer': state['answer']}
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
        priority = 'Cần xem xét bổ sung hàng.' if available < leader['units_sold'] else 'Chưa cần ưu tiên bổ sung theo quy tắc demo.'
        return {'answer': f"Đánh giá bổ sung hàng tháng {month()}: {leader['name']} bán {leader['units_sold']} sản phẩm, còn {available} sản phẩm có thể bán. {priority} Đây không phải dự báo hay đơn đặt hàng."}
    if category == 'stock' and not rows:
        return {'answer': 'Vui lòng nêu tên sản phẩm hoặc mã SKU đã biết.'}
    if category == 'product' and not state.get('contexts'):
        return {'answer': 'Không tìm thấy tài liệu sản phẩm phù hợp để xác minh câu trả lời.'}
    return {'answer': state['answer']}
