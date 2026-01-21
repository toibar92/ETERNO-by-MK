from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
from datetime import datetime, timedelta
from functools import wraps
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

app = Flask(__name__)
app.secret_key = 'eterno_calculadora_secret_key_2026'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)

DATABASE = 'calculadora_eterno.db'

# Configuración de productos
PRODUCTOS_CONFIG = {
    'Grande': {
        'medidas': '94 x 152 cms',
        'precio': 15750,
        'costos': {
            'enmarcado': 1990,
            'impresion': 887,
            'drytac': 576,
            'acrilico': 740,
            'montaje': 300,
            'papel': 340
        }
    },
    'Mediano': {
        'medidas': '75 x 122 cms',
        'precio': 13125,
        'costos': {
            'enmarcado': 1500,
            'impresion': 595,
            'drytac': 576,
            'acrilico': 470,
            'montaje': 300,
            'papel': 320
        }
    }
}

RECARGOS_VISA = {
    2: 0.05,
    3: 0.0575,
    6: 0.07,
    10: 0.07,
    12: 0.08
}

def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    with app.app_context():
        db = get_db()
        db.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                nombre TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        db.execute('''
            CREATE TABLE IF NOT EXISTS pedidos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha DATE NOT NULL,
                cliente TEXT NOT NULL,
                producto TEXT NOT NULL,
                cantidad INTEGER NOT NULL,
                precio_unitario REAL NOT NULL,
                descuento REAL DEFAULT 0,
                cuotas_visa INTEGER DEFAULT 0,
                usuario_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
            )
        ''')
        
        # Crear usuarios por defecto si no existen
        cursor = db.execute('SELECT COUNT(*) as count FROM usuarios')
        if cursor.fetchone()['count'] == 0:
            db.execute('''
                INSERT INTO usuarios (username, password, nombre) 
                VALUES (?, ?, ?)
            ''', ('admin', generate_password_hash('eterno2026'), 'Administrador'))
            
            db.execute('''
                INSERT INTO usuarios (username, password, nombre) 
                VALUES (?, ?, ?)
            ''', ('usuario', generate_password_hash('eterno2026'), 'Usuario'))
        
        db.commit()
        db.close()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Por favor inicia sesión para acceder.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def calcular_totales(producto, cantidad, descuento=0, cuotas_visa=0):
    config = PRODUCTOS_CONFIG[producto]
    precio_unitario = config['precio']
    costo_unitario = sum(config['costos'].values())
    
    subtotal = precio_unitario * cantidad
    total_venta = subtotal * (1 - descuento)
    
    recargo_visa = 0
    if cuotas_visa > 0 and cuotas_visa in RECARGOS_VISA:
        recargo_visa = total_venta * RECARGOS_VISA[cuotas_visa]
    
    total_con_recargo = total_venta + recargo_visa
    costo_total = costo_unitario * cantidad
    utilidad = total_con_recargo - costo_total
    porcentaje_utilidad = (utilidad / total_con_recargo * 100) if total_con_recargo > 0 else 0
    
    return {
        'precio_unitario': precio_unitario,
        'subtotal': subtotal,
        'total_venta': total_venta,
        'recargo_visa': recargo_visa,
        'total_con_recargo': total_con_recargo,
        'costo_total': costo_total,
        'utilidad': utilidad,
        'porcentaje_utilidad': porcentaje_utilidad,
        'reserva_costos': costo_total
    }

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        db = get_db()
        user = db.execute('SELECT * FROM usuarios WHERE username = ?', (username,)).fetchone()
        db.close()
        
        if user and check_password_hash(user['password'], password):
            session.permanent = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['nombre'] = user['nombre']
            flash(f'¡Bienvenido {user["nombre"]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Usuario o contraseña incorrectos.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Sesión cerrada correctamente.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    pedidos = db.execute('''
        SELECT * FROM pedidos 
        ORDER BY fecha DESC, id DESC
    ''').fetchall()
    db.close()
    
    # Calcular estadísticas
    total_ventas = 0
    total_costos = 0
    total_utilidad = 0
    pedidos_grande = 0
    pedidos_mediano = 0
    ventas_grande = 0
    ventas_mediano = 0
    utilidad_grande = 0
    utilidad_mediano = 0
    
    pedidos_procesados = []
    for pedido in pedidos:
        totales = calcular_totales(
            pedido['producto'],
            pedido['cantidad'],
            pedido['descuento'],
            pedido['cuotas_visa']
        )
        
        pedidos_procesados.append({
            'id': pedido['id'],
            'fecha': pedido['fecha'],
            'cliente': pedido['cliente'],
            'producto': pedido['producto'],
            'cantidad': pedido['cantidad'],
            **totales
        })
        
        total_ventas += totales['total_con_recargo']
        total_costos += totales['costo_total']
        total_utilidad += totales['utilidad']
        
        if pedido['producto'] == 'Grande':
            pedidos_grande += pedido['cantidad']
            ventas_grande += totales['total_con_recargo']
            utilidad_grande += totales['utilidad']
        else:
            pedidos_mediano += pedido['cantidad']
            ventas_mediano += totales['total_con_recargo']
            utilidad_mediano += totales['utilidad']
    
    margen_promedio = (total_utilidad / total_ventas * 100) if total_ventas > 0 else 0
    
    estadisticas = {
        'total_ventas': total_ventas,
        'total_costos': total_costos,
        'total_utilidad': total_utilidad,
        'margen_promedio': margen_promedio,
        'total_pedidos': len(pedidos),
        'pedidos_grande': pedidos_grande,
        'pedidos_mediano': pedidos_mediano,
        'ventas_grande': ventas_grande,
        'ventas_mediano': ventas_mediano,
        'utilidad_grande': utilidad_grande,
        'utilidad_mediano': utilidad_mediano
    }
    
    return render_template('dashboard.html', 
                         pedidos=pedidos_procesados, 
                         estadisticas=estadisticas,
                         productos_config=PRODUCTOS_CONFIG)

@app.route('/nuevo-pedido', methods=['GET', 'POST'])
@login_required
def nuevo_pedido():
    if request.method == 'POST':
        fecha = request.form['fecha']
        cliente = request.form['cliente']
        producto = request.form['producto']
        cantidad = int(request.form['cantidad'])
        descuento = float(request.form.get('descuento', 0)) / 100
        cuotas_visa = int(request.form.get('cuotas_visa', 0))
        
        db = get_db()
        precio_unitario = PRODUCTOS_CONFIG[producto]['precio']
        
        db.execute('''
            INSERT INTO pedidos (fecha, cliente, producto, cantidad, precio_unitario, 
                               descuento, cuotas_visa, usuario_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (fecha, cliente, producto, cantidad, precio_unitario, descuento, 
              cuotas_visa, session['user_id']))
        
        db.commit()
        db.close()
        
        flash('Pedido registrado exitosamente.', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('nuevo_pedido.html', 
                         productos=PRODUCTOS_CONFIG,
                         recargos_visa=RECARGOS_VISA)

@app.route('/editar-pedido/<int:pedido_id>', methods=['GET', 'POST'])
@login_required
def editar_pedido(pedido_id):
    db = get_db()
    
    if request.method == 'POST':
        fecha = request.form['fecha']
        cliente = request.form['cliente']
        producto = request.form['producto']
        cantidad = int(request.form['cantidad'])
        descuento = float(request.form.get('descuento', 0)) / 100
        cuotas_visa = int(request.form.get('cuotas_visa', 0))
        
        precio_unitario = PRODUCTOS_CONFIG[producto]['precio']
        
        db.execute('''
            UPDATE pedidos 
            SET fecha=?, cliente=?, producto=?, cantidad=?, precio_unitario=?,
                descuento=?, cuotas_visa=?
            WHERE id=?
        ''', (fecha, cliente, producto, cantidad, precio_unitario, 
              descuento, cuotas_visa, pedido_id))
        
        db.commit()
        db.close()
        
        flash('Pedido actualizado exitosamente.', 'success')
        return redirect(url_for('dashboard'))
    
    pedido = db.execute('SELECT * FROM pedidos WHERE id = ?', (pedido_id,)).fetchone()
    db.close()
    
    if not pedido:
        flash('Pedido no encontrado.', 'danger')
        return redirect(url_for('dashboard'))
    
    return render_template('editar_pedido.html', 
                         pedido=pedido,
                         productos=PRODUCTOS_CONFIG,
                         recargos_visa=RECARGOS_VISA)

@app.route('/eliminar-pedido/<int:pedido_id>')
@login_required
def eliminar_pedido(pedido_id):
    db = get_db()
    db.execute('DELETE FROM pedidos WHERE id = ?', (pedido_id,))
    db.commit()
    db.close()
    
    flash('Pedido eliminado exitosamente.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/exportar-excel')
@login_required
def exportar_excel():
    db = get_db()
    pedidos = db.execute('SELECT * FROM pedidos ORDER BY fecha DESC').fetchall()
    db.close()
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Pedidos Eterno"
    
    # Encabezados
    headers = ['No.', 'Fecha', 'Cliente', 'Producto', 'Cantidad', 'Precio Unit.', 
               'Subtotal', 'Descuento %', 'Total Venta', 'Cuotas VISA', 'Recargo VISA',
               'Total c/Recargo', 'Costo Total', 'Utilidad', '% Utilidad', 'Reserva Costos']
    
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col)
        cell.value = header
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
        cell.alignment = Alignment(horizontal='center', vertical='center')
    
    # Datos
    for idx, pedido in enumerate(pedidos, 2):
        totales = calcular_totales(
            pedido['producto'],
            pedido['cantidad'],
            pedido['descuento'],
            pedido['cuotas_visa']
        )
        
        ws.cell(row=idx, column=1, value=pedido['id'])
        ws.cell(row=idx, column=2, value=pedido['fecha'])
        ws.cell(row=idx, column=3, value=pedido['cliente'])
        ws.cell(row=idx, column=4, value=pedido['producto'])
        ws.cell(row=idx, column=5, value=pedido['cantidad'])
        ws.cell(row=idx, column=6, value=totales['precio_unitario'])
        ws.cell(row=idx, column=7, value=totales['subtotal'])
        ws.cell(row=idx, column=8, value=pedido['descuento'] * 100)
        ws.cell(row=idx, column=9, value=totales['total_venta'])
        ws.cell(row=idx, column=10, value=pedido['cuotas_visa'] if pedido['cuotas_visa'] > 0 else '')
        ws.cell(row=idx, column=11, value=totales['recargo_visa'])
        ws.cell(row=idx, column=12, value=totales['total_con_recargo'])
        ws.cell(row=idx, column=13, value=totales['costo_total'])
        ws.cell(row=idx, column=14, value=totales['utilidad'])
        ws.cell(row=idx, column=15, value=totales['porcentaje_utilidad'])
        ws.cell(row=idx, column=16, value=totales['reserva_costos'])
    
    # Ajustar anchos
    for col in range(1, 17):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = 14
    
    filename = f'backup_eterno_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    filepath = os.path.join('/tmp', filename)
    wb.save(filepath)
    
    return send_file(filepath, as_attachment=True, download_name=filename)

init_db()

   if __name__ == '__main__':
       app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
