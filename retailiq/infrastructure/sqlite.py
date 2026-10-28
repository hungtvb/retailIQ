from pathlib import Path
import sqlite3
DB=Path(__file__).resolve().parents[2]/'data'/'retailiq.sqlite3'
def query(sql,args=()):
 if not sql.strip().lower().startswith('select'):raise ValueError('Only reviewed SELECT queries permitted')
 with sqlite3.connect(f'file:{DB}?mode=ro',uri=True) as c:
  c.row_factory=sqlite3.Row
  return [dict(x) for x in c.execute(sql,args).fetchall()]
