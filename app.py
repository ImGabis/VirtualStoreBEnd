
import os, time, sqlite3, random
from datetime import datetime, timedelta
from threading import Event as ThreadEvent
from flask import Flask, request, jsonify, Response, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, "dist")
DB_PATH  = os.path.join(BASE_DIR, "tienda.db")

app = Flask(__name__, static_folder=DIST_DIR, static_url_path="/")
ventas_event = ThreadEvent()

def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

with get_conn() as conn:
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS productos (id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT NOT NULL, precio REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS pedidos (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL, correo TEXT NOT NULL, creado_en TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS pedido_items (id INTEGER PRIMARY KEY AUTOINCREMENT, pedido_id INTEGER NOT NULL, producto_id INTEGER NOT NULL, cantidad INTEGER NOT NULL, precio_unitario REAL NOT NULL,
            FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE,
            FOREIGN KEY (producto_id) REFERENCES productos(id));
    """)

@app.get("/api/health")
def health(): return {"ok": True}

@app.get("/api/productos")
def productos_listar():
    with get_conn() as conn:
        rows = conn.execute("SELECT id, titulo, precio FROM productos ORDER BY id").fetchall()
        return jsonify([dict(r) for r in rows])

@app.post("/api/pedidos")
def pedidos_crear():
    data = request.get_json(force=True) or {}
    nombre = str(data.get("nombre") or "").strip()
    correo = str(data.get("correo") or "").strip()
    items = data.get("items") or []
    if not nombre or not correo or not isinstance(items, list) or len(items)==0:
        return jsonify({"error":"Datos incompletos"}), 400
    with get_conn() as conn:
        cur = conn.cursor()
        ts = datetime.now().isoformat(timespec="seconds")
        cur.execute("INSERT INTO pedidos(nombre, correo, creado_en) VALUES(?,?,?)", (nombre, correo, ts))
        pedido_id = cur.lastrowid
        for it in items:
            pid = it.get("id"); titulo = str(it.get("titulo") or "").strip(); qty = int(it.get("qty") or 1)
            try: precio_unit = float(it.get("precio"))
            except Exception: precio_unit = 0.0
            prod_row = None
            if pid is not None:
                prod_row = cur.execute("SELECT id, precio FROM productos WHERE id=?", (int(pid),)).fetchone()
            if prod_row is None and titulo:
                prod_row = cur.execute("SELECT id, precio FROM productos WHERE lower(trim(titulo))=lower(trim(?))", (titulo,)).fetchone()
            if prod_row is None:
                cur.execute("INSERT INTO productos(titulo, precio) VALUES(?,?)", (titulo, precio_unit))
                producto_id = cur.lastrowid
            else:
                producto_id = prod_row["id"]
                if not precio_unit: precio_unit = float(prod_row["precio"])
            cur.execute("INSERT INTO pedido_items(pedido_id, producto_id, cantidad, precio_unitario) VALUES(?,?,?,?)", (pedido_id, producto_id, qty, precio_unit))
        conn.commit(); ventas_event.set()
    return jsonify({"ok": True, "pedido_id": pedido_id})

@app.get("/api/ventas-top")
def ventas_top():
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT prod.titulo AS titulo, SUM(pi.cantidad) AS cantidad, SUM(pi.cantidad*pi.precio_unitario) AS ingreso
            FROM pedidos ped JOIN pedido_items pi ON pi.pedido_id=ped.id JOIN productos prod ON prod.id=pi.producto_id
            WHERE ped.creado_en >= DATETIME('now', '-30 days') GROUP BY prod.titulo
            ORDER BY SUM(pi.cantidad) DESC LIMIT 6
        """).fetchall()
    return jsonify([dict(r) for r in rows])

@app.post("/api/seed")
def seed():
    titles = ["Leggings Pro", "Top Compresión", "Jogger Fit", "Short Runner", "Camiseta Dry"]; precios = [120000,90000,135000,80000,70000]
    hoy = datetime.now()
    with get_conn() as conn:
        cur = conn.cursor()
        for t,p in zip(titles,precios): cur.execute("INSERT INTO productos(titulo, precio) VALUES(?,?)",(t,p))
        for i in range(12):
            fecha = (hoy - timedelta(days=random.randint(0,14))).replace(hour=12,minute=0,second=0)
            cur.execute("INSERT INTO pedidos(nombre, correo, creado_en) VALUES(?,?,?)",(f"Cliente {i+1}", f"c{i+1}@mail.com", fecha.isoformat(timespec="seconds")))
            pedido_id = cur.lastrowid
            for _ in range(random.randint(1,3)):
                prod = cur.execute("SELECT id, precio FROM productos ORDER BY RANDOM() LIMIT 1").fetchone()
                qty = random.randint(1,4)
                cur.execute("INSERT INTO pedido_items(pedido_id, producto_id, cantidad, precio_unitario) VALUES(?,?,?,?)", (pedido_id, prod["id"], qty, prod["precio"]))
        conn.commit()
    try: ventas_event.set()
    except: pass
    return {"ok": True, "msg": "Sembrado con éxito"}

@app.get("/assets/<path:path>")
def serve_assets(path): return send_from_directory(os.path.join(DIST_DIR, "assets"), path)

@app.get("/", defaults={"path": ""})
@app.get("/<path:path>")
def spa(path):
    full = os.path.join(DIST_DIR, path)
    if path and os.path.exists(full): return send_from_directory(DIST_DIR, path)
    return send_from_directory(DIST_DIR, "index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
