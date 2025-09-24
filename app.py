from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import sqlite3
import matplotlib.pyplot as plt
import io

app = Flask(__name__)
CORS(app)

def get_db():
    conn = sqlite3.connect('compras.db')
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def home():
    return jsonify({"mensaje": "Hola desde Flask en Render!"})


@app.route('/compras', methods=['GET'])
def listar_compras():
    db = get_db()
    compras = db.execute('SELECT * FROM compras ORDER BY fecha DESC').fetchall()
    db.close()
    return jsonify([dict(row) for row in compras])

@app.route('/compras', methods=['POST'])
def crear_compra():
    data = request.json
    db = get_db()
    db.execute(
        'INSERT INTO compras (nombre, apellidos, cedula, direccion, correo, carrito, totalPagado, fecha) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (
            data['nombre'],
            data['apellidos'],
            data['cedula'],
            data['direccion'],
            data['correo'],
            str(data['carrito']),
            data['totalPagado'],
            data['fecha']
        )
    )
    db.commit()
    db.close()
    return jsonify({'status': 'ok'}), 201

@app.route('/compras', methods=['DELETE'])
def borrar_compras():
    db = get_db()
    db.execute('DELETE FROM compras')
    db.commit()
    db.close()
    return jsonify({'status': 'ok'})
    
@app.route('/grafica-ventas-articulos', methods=['GET'])
def grafica_ventas_articulos():
    import json
    metrica = request.args.get('metrica', 'cantidad')
    sin_fecha = request.args.get('sin_fecha', '0') == '1'
    conn = sqlite3.connect('compras.db')
    cursor = conn.cursor()
    cursor.execute("SELECT carrito, fecha FROM compras")
    rows = cursor.fetchall()
    conn.close()

    if sin_fecha:
        # Agrupar totales por artículo desde el carrito
        totales = {}
        for carrito_str, fecha in rows:
            try:
                carrito = json.loads(carrito_str.replace("'", '"'))
            except Exception:
                carrito = []
            for item in carrito:
                nombre = item.get('nombre', 'Desconocido')
                cantidad = int(item.get('cantidad', 1))
                ingreso = float(item.get('precio', 0)) * cantidad
                if nombre not in totales:
                    totales[nombre] = {'cantidad': 0, 'ingreso': 0}
                totales[nombre]['cantidad'] += cantidad
                totales[nombre]['ingreso'] += ingreso

        nombres = list(totales.keys())
        valores = [totales[n][metrica] for n in nombres]

        import numpy as np
        plt.figure(figsize=(12, 6))
        plt.bar(nombres, valores, color='#1a237e')
        plt.xlabel('Artículo')
        plt.ylabel('Cantidad' if metrica == 'cantidad' else 'Ingreso')
        plt.title('Ventas totales por artículo')
        plt.xticks(rotation=45)
        # Eje Y: enteros de 1 a 10
        plt.yticks(np.arange(1, 11, 1))
        plt.ylim(1, 10)
        plt.tight_layout()
    else:
        # Agrupar por artículo y fecha desde el carrito
        datos = {}
        fechas_set = set()
        for carrito_str, fecha in rows:
            try:
                carrito = json.loads(carrito_str.replace("'", '"'))
            except Exception:
                carrito = []
            for item in carrito:
                nombre = item.get('nombre', 'Desconocido')
                cantidad = int(item.get('cantidad', 1))
                ingreso = float(item.get('precio', 0)) * cantidad
                if nombre not in datos:
                    datos[nombre] = {}
                if fecha not in datos[nombre]:
                    datos[nombre][fecha] = {'cantidad': 0, 'ingreso': 0}
                datos[nombre][fecha]['cantidad'] += cantidad
                datos[nombre][fecha]['ingreso'] += ingreso
                fechas_set.add(fecha)

        fechas = sorted(fechas_set)

        import numpy as np
        plt.figure(figsize=(12, 6))
        for nombre, serie in datos.items():
            valores = [serie.get(fecha, {}).get(metrica, 0) for fecha in fechas]
            plt.plot(fechas, valores, label=nombre)

        plt.xlabel('Fecha')
        plt.ylabel('Cantidad' if metrica == 'cantidad' else 'Ingreso')
        plt.title('Evolución de ventas por artículo')
        plt.legend()
        plt.xticks(rotation=45)
        # Eje Y: enteros de 1 a 10
        plt.yticks(np.arange(1, 11, 1))
        plt.ylim(1, 10)
        plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    plt.close()
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

if __name__ == '__main__':
    # Inicializar la base de datos si no existe
    conn = sqlite3.connect('compras.db')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS compras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            apellidos TEXT,
            cedula TEXT,
            direccion TEXT,
            correo TEXT,
            carrito TEXT,
            totalPagado INTEGER,
            fecha TEXT
        )
    ''')
    conn.close()
    app.run(debug=True)

# Endpoint para métricas de ventas
from datetime import datetime, timedelta
import json

@app.route('/ventas-metricas', methods=['GET'])
def ventas_metricas():
    metrica = request.args.get('metrica', 'cantidad')
    db = get_db()
    fecha_limite = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    compras = db.execute('SELECT carrito, totalPagado, fecha FROM compras ').fetchall()
    db.close()

    # Procesar carritos y agrupar por producto
    productos = {}
    serie_diaria = {}
    for row in compras:
        fecha = row['fecha'][:10]  # Solo yyyy-mm-dd
        try:
            carrito = json.loads(row['carrito'].replace("'", '"'))
        except Exception:
            carrito = []
        for item in carrito:
            nombre = item.get('nombre', 'Desconocido')
            cantidad = int(item.get('cantidad', 1))
            ingreso = float(item.get('precio', 0)) * cantidad
            if nombre not in productos:
                productos[nombre] = {'cantidad': 0, 'ingreso': 0}
            productos[nombre]['cantidad'] += cantidad
            productos[nombre]['ingreso'] += ingreso
            # Serie diaria por producto
            if nombre not in serie_diaria:
                serie_diaria[nombre] = {}
            if fecha not in serie_diaria[nombre]:
                serie_diaria[nombre][fecha] = {'cantidad': 0, 'ingreso': 0}
            serie_diaria[nombre][fecha]['cantidad'] += cantidad
            serie_diaria[nombre][fecha]['ingreso'] += ingreso

    # Top 6 productos por metrica
    top6 = sorted(productos.items(), key=lambda x: x[1][metrica], reverse=True)[:6]
    # Top 5 productos para serie diaria
    top5_nombres = [x[0] for x in sorted(productos.items(), key=lambda x: x[1][metrica], reverse=True)[:5]]
    serie_top5 = {nombre: serie_diaria[nombre] for nombre in top5_nombres}

    return jsonify({
        'top6': [{
            'nombre': nombre,
            'cantidad': datos['cantidad'],
            'ingreso': datos['ingreso']
        } for nombre, datos in top6],
        'serie_top5': serie_top5
    })
import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Render inyecta PORT
    app.run(host="0.0.0.0", port=port, debug=True)
