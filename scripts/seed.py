from pathlib import Path
from datetime import date,timedelta
import sqlite3,random,json,os
ROOT=Path(__file__).resolve().parents[1];DB=ROOT/'data'/'retailiq.sqlite3'
ASOF=date.fromisoformat(os.getenv('RETAILIQ_AS_OF','2026-10-28'))
PRODUCTS=[('EL-001','AlphaBook Pro 14','Laptop',18990000,'14-inch, 16GB RAM, USB-C PD 65W'),('EL-002','NovaPhone X','Phone',12990000,'OLED 6.2-inch, 128GB, USB-C 25W'),('EL-003','USB-C GaN Charger 65W','Accessory',699000,'PD 3.0 up to 65W single port; cable not included'),('EL-004','USB-C Cable 100W 2m','Accessory',259000,'USB-C to USB-C, 100W E-marker'),('EL-005','AirPulse Earbuds','Audio',1590000,'Bluetooth 5.3, ANC'),('EL-006','SwiftMouse Wireless','Peripheral',429000,'Bluetooth and 2.4GHz'),('EL-007','ViewMax 27 Monitor','Display',4290000,'27 inch QHD IPS 75Hz'),('EL-008','Orbit Mechanical Keyboard','Peripheral',1790000,'Mechanical USB-C wired'),('EL-009','USB-C Hub 7-in-1','Accessory',1090000,'HDMI and PD passthrough, requires host DP Alt Mode'),('EL-010','NovaTab 11','Tablet',8990000,'11-inch 128GB WiFi')]
LOC=[('WH-HCM','HCMC Warehouse','warehouse'),('ST-HCM','HCMC Store','store'),('ST-HN','Hanoi Store','store')]
def seed(db_path: Path = DB, *, write_support_files: bool = True, reference_date: date = ASOF):
 db_path.parent.mkdir(parents=True, exist_ok=True)
 if db_path.exists(): db_path.unlink()
 c=sqlite3.connect(db_path)
 c.executescript('''CREATE TABLE products(sku TEXT PRIMARY KEY,name TEXT,category TEXT,price_vnd INTEGER,spec TEXT,catalog_added_at TEXT NOT NULL);
 CREATE TABLE locations(id TEXT PRIMARY KEY,name TEXT,channel TEXT);
 CREATE TABLE inventory(sku TEXT,location_id TEXT,on_hand INT,reserved INT,updated_at TEXT,PRIMARY KEY(sku,location_id),CHECK(on_hand>=reserved AND reserved>=0));
 CREATE TABLE orders(id TEXT PRIMARY KEY,ordered_at TEXT,channel TEXT,status TEXT);
 CREATE TABLE order_lines(id INT PRIMARY KEY,order_id TEXT,sku TEXT,quantity INT,unit_price_vnd INT,discount_vnd INT);''')
 c.executemany('INSERT INTO products VALUES(?,?,?,?,?,?)',
               [(*product,(reference_date-timedelta(days=(len(PRODUCTS)-1-index)*7)).isoformat())
                for index,product in enumerate(PRODUCTS)])
 c.executemany('INSERT INTO locations VALUES(?,?,?)',LOC)
 for j,p in enumerate(PRODUCTS):
  for i,l in enumerate(LOC):c.execute('INSERT INTO inventory VALUES(?,?,?,?,?)',(p[0],l[0],25+((j*9+i*13)%70),(j+i*2)%7,reference_date.isoformat()+' 09:00 +07:00'))
 random.seed(20261028)
 for k in range(1,121):
  d=reference_date-timedelta(days=k%47);ch='online' if k%4 else 'store'; status='completed' if k%10 else 'cancelled'
  c.execute('INSERT INTO orders VALUES(?,?,?,?)',(f'ORD-{k:04}',d.isoformat(),ch,status))
  for i in range(1+(k%5==0)):
   p=PRODUCTS[(k*7+i*3)%len(PRODUCTS)]
   c.execute('INSERT INTO order_lines VALUES(?,?,?,?,?,?)',(k*10+i,f'ORD-{k:04}',p[0],1+k%3,p[3],50000 if k%7==0 else 0))
 c.commit();c.close()
 if write_support_files:
  for sku,name,cat,price,spec in PRODUCTS:
   (ROOT/'data'/'product_docs'/f'{sku}.md').write_text(f'# {name}\nSKU: {sku}\nCategory: {cat}\nList price: {price:,} VND\nProduct specifications: {spec}.\nWarranty: 12 months (synthetic retailer policy, not a real warranty claim).\nDo not infer real-time inventory from this document.\n',encoding='utf8')
  (ROOT/'data'/'demo_cases.json').write_text(json.dumps([{'question':q,'expected_intent':i} for q,i in [('How many units of AlphaBook Pro 14 are currently in stock?','stock'),('What is the revenue this month?','revenue'),('Which products are top sellers?','top'),('Tell me about USB-C GaN Charger 65W','product')]],indent=2))
 print('Seeded',db_path,'products',len(PRODUCTS),'inventory',len(PRODUCTS)*len(LOC),'orders',120)
if __name__=='__main__': seed()
