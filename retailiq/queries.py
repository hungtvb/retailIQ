"""Read-only retail question lookup.

No orchestration imports: LangGraph and the offline entrypoint share these
business operations without depending on each other.
"""
from .analytics import products, inventory, revenue, top, month, requested_month
from .retrieval import retrieve
from .language import is_vietnamese
from .reply import retailiq_reply


def is_price_extreme(question: str) -> bool:
 text = question.casefold()
 return any(term in text for term in (
     'mắc nhất', 'đắt nhất', 'rẻ nhất', 'most expensive', 'cheapest',
     'least expensive', 'highest priced', 'lowest priced'))



def has_ranked_revenue_reference(question: str) -> bool:
 """Avoid silently converting a product-ranking revenue request to store revenue."""
 text=question.casefold()
 has_metric=any(x in text for x in ('doanh thu', 'revenue'))
 has_ranking=any(x in text for x in (
     'top seller', 'top 1 seller', 'best seller', 'bán chạy',
     'number one seller', '#1 seller')) or bool(__import__('re').search(
         r'\btop\s*[1-9]\d*\b', text))
 return has_metric and has_ranking


def ranked_revenue_sku_rank(question: str) -> int | None:
 """Return a single product rank only when the user's wording is unambiguous.

 'Top 5 sellers' denotes a group, not fifth place; ask for clarification
 rather than silently returning the total store revenue.
 """
 import re
 text=question.casefold()
 if not has_ranked_revenue_reference(question):
  return None
 if re.search(r'\btop\s*([2-9]\d*)\b', text):
  return None  # A top-N group is not an Nth-place product
 if ('bán chạy nhất' in text or 'number one seller' in text or
     '#1 seller' in text or
     re.search(r'\b(?:top|best)\s+seller\b(?!s)', text) or
     re.search(r'\btop\s*1(?:\s|$)', text)):
  return 1
 rank=re.search(r'(?:đứng|xếp)\s*thứ\s*([1-5])', text)
 if rank and 'bán chạy' in text:
  return int(rank.group(1))
 return None


def highest_price(question: str) -> bool:
 text = question.casefold()
 return any(term in text for term in ('mắc nhất', 'đắt nhất', 'most expensive', 'highest priced'))


def requested_top_count(question: str) -> int:
 import re
 match = re.search(r'\btop\s*([1-5])\b', question.casefold())
 if match:
  return int(match.group(1))
 if 'top five' in question.casefold():
  return 5
 return 1 if wants_single_top_product(question) else 5


def is_multi_stock_question(question: str) -> bool:
 """Stock of a ranked group, not a replenishment review."""
 import re
 text = question.casefold()
 stock = any(x in text for x in ('stock','inventory','tồn kho','available','còn hàng'))
 ranked = any(x in text for x in ('bán chạy','best seller','top seller'))
 plural = bool(re.search(r'\btop\s*[2-5]\b', text)) or 'top five' in text
 return stock and ranked and plural


def intent(q):
 q=q.lower()
 if is_price_extreme(q):return 'product'
 if has_ranked_revenue_reference(q):return 'revenue'
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
def do(q,category, *, stock_lookup=None):
 # Optional trusted read-only inventory adapter. Default stays reviewed SQL.
 stock_read = stock_lookup if stock_lookup is not None else inventory
 if category=='latest':
  from .domain.analytics import newest_products
  rows=newest_products(1 if wants_single_latest_product(q) else 5)
  answer=retailiq_reply({'question':q,'intent':'latest','records':rows,'answer':''})['answer']
  return {'answer':answer,'records':rows,'contexts':[]}
 if category=='general':
  answer=('Xin chào! Tôi là RetailIQ. Bạn có thể hỏi về tồn kho, doanh thu, hàng bán chạy hoặc thông tin sản phẩm.'
          if is_vietnamese(q) else
          'Hello! I am RetailIQ. You can ask about inventory, revenue, top sellers, or product information.')
  return {'answer':answer,'records':[],'contexts':[]}
 if category=='stock':
  if is_multi_stock_question(q):
   period=requested_month(q)
   ranked=top(period)[:requested_top_count(q)]
   rows=[record for item in ranked for record in stock_read(item['sku'])]
   by_sku={item['sku']:sum(row['available'] for row in rows
                           if row['sku']==item['sku']) for item in ranked}
   answer=('Available stock for ranked completed-order products in '+period+': '+
           '; '.join(item['name']+' ('+item['sku']+'): '+str(by_sku[item['sku']])+
                     ' units' for item in ranked)+'.')
   if not ranked: answer='No completed-order top sellers found for '+period+'.'
   return {'answer':answer,'records':rows,'contexts':[],'period':period}
  sku=product_sku(q)
  if not sku:return {'answer':'Please specify a known product name or SKU.','records':[],'contexts':[]}
  rows=stock_read(sku)
  if not rows:
   return {'answer':f'No inventory records are available for SKU {sku}.', 'records':[], 'contexts':[]}
  total=sum(r['available'] for r in rows)
  return {'answer':f"{rows[0]['name']} ({sku}): {total} available units across locations. "+'; '.join(f"{r['location']}: {r['available']} available (on hand {r['on_hand']}, reserved {r['reserved']})" for r in rows)+'.','records':rows,'contexts':[]}
 if category=='revenue':
  from .domain.analytics import revenue_for_sku
  from .domain.revenue_plan import build_revenue_plan, with_selected_sku, verify_revenue_evidence
  plan=build_revenue_plan(
   q,resolve_sku=product_sku,
   is_ranked=has_ranked_revenue_reference,
   ranked_position=ranked_revenue_sku_rank)
  period=plan.period
  if plan.scope=='clarify':
   answer=('Cần làm rõ yêu cầu doanh thu: '+plan.reason+'.'
           if is_vietnamese(q) else 'Please clarify the revenue request: '+plan.reason+'.')
   verify_revenue_evidence(plan,[])
   return {'answer':answer,'records':[],'contexts':[],'period':period,
           'query_plan':plan.to_dict()}

  if plan.scope=='ranked_product':
   ranked=top(period)
   if plan.rank is None or plan.rank>len(ranked):
    return {'answer':'Không có sản phẩm ở thứ hạng này trong '+period+'.'
            if is_vietnamese(q) else 'No product exists at this rank in '+period+'.',
            'records':[],'contexts':[],'period':period,'query_plan':plan.to_dict()}
   plan=with_selected_sku(plan,ranked[plan.rank-1]['sku'])

  rows=(revenue_for_sku(plan.sku,period)
        if plan.scope in ('product','ranked_product')
        else revenue(period))
  if plan.channel:
   rows=[row for row in rows if row['channel']==plan.channel]
  verify_revenue_evidence(plan,rows)
  if not rows:
   answer=('Không có doanh thu từ đơn hoàn tất trong '+period+
           (' của '+plan.sku if plan.sku else '')+
           (' trên kênh '+plan.channel if plan.channel else '')+'.'
           if is_vietnamese(q) else
           'No completed-order revenue for '+period+
           (' and SKU '+plan.sku if plan.sku else '')+
           (' on channel '+plan.channel if plan.channel else '')+'.')
   return {'answer':answer,'records':[],'contexts':[],'period':period,
           'query_plan':plan.to_dict()}

  total=sum(row['net_revenue_vnd'] for row in rows)
  subject= ('product '+rows[0]['name']+' ('+plan.sku+')'
            if plan.sku else 'store')
  answer=('Net sales revenue in '+period+' for '+subject+
          (' via '+plan.channel if plan.channel else '')+
          ': '+f'{total:,}'+' VND (completed orders, after line discounts, before returns).')
  return {'answer':answer,'records':rows,'contexts':[],'period':period,
          'query_plan':plan.to_dict()}
 if category=='top':
  period=requested_month(q)
  ranked=top(period) if period!=month() else top()
  rows=ranked[:requested_top_count(q)]
  if not rows:
   return {'answer':f'No completed-order top sellers for {period}.','records':[],'contexts':[], 'period':period}
  return {'answer':f'Top sellers by units in {period} (completed orders): '+ '; '.join(f"{i+1}. {r['name']} ({r['sku']}): {r['units_sold']} units" for i,r in enumerate(rows))+'.','records':rows,'contexts':[], 'period':period}
 if category=='product' and is_price_extreme(q):
   from .domain.analytics import price_extreme
   category_filter='Accessory' if ('phụ kiện' in q.casefold() or 'accessor' in q.casefold()) else None
   rows=price_extreme(highest=highest_price(q),category=category_filter)
   if not rows:return {'answer':'No catalog products match this price filter.', 'records':[], 'contexts':[]}
   leader=rows[0]
   return {'answer':leader['name']+' ('+leader['sku']+'): '+
           f"{leader['price_vnd']:,} VND list price in the synthetic catalog."+
           (' Category: '+category_filter+'.' if category_filter else ''),
           'records':rows,'contexts':[]}
 if category=='product' and any(word in q.casefold() for word in ('giá','price','cost')) and product_sku(q):
  from .domain.analytics import catalog_product
  item=catalog_product(product_sku(q))
  rows=[item] if item else []
  answer=retailiq_reply({'question':q,'intent':'product','records':rows,'answer':''})['answer'] if rows else 'No matching catalog product.'
  return {'answer':answer,'records':rows,'contexts':[]}
 docs=retrieve(q)
 return {'answer':f"Source: {docs[0]['source']}\n{docs[0]['text']}" if docs else 'No matching product documentation.','records':[],'contexts':docs}

