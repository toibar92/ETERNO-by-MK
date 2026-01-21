from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import csv
import io

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'eterno_calculadora_secret_key_2026')

DATABASE_URL = os.environ.get('DATABASE_URL')

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

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            nombre VARCHAR(100) NOT NULL,
            rol VARCHAR(20) DEFAULT 'usuario',
            activo BOOLEAN DEFAULT TRUE,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS pedidos (
            id SERIAL PRIMARY KEY,
            fecha DATE NOT NULL,
            cliente VARCHAR(100) NOT NULL,
            producto VARCHAR(50) NOT NULL,
            cantidad INTEGER DEFAULT 1,
            precio_unitario DECIMAL(10,2) NOT NULL,
            descuento DECIMAL(5,4) DEFAULT 0,
            cuotas_visa INTEGER DEFAULT 0,
            usuario_id INTEGER REFERENCES usuarios(id),
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cur.execute("SELECT * FROM usuarios WHERE username = 'admin'")
    if not cur.fetchone():
        hashed_password = generate_password_hash('eterno2026')
        cur.execute('''
            INSERT INTO usuarios (username, password, nombre, rol)
            VALUES (%s, %s, %s, %s)
        ''', ('admin', hashed_password, 'Administrador', 'admin'))
    
    conn.commit()
    cur.close()
    conn.close()

try:
    init_db()
except Exception as e:
    print(f"Error inicializando DB: {e}")

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

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('rol') != 'admin':
            flash('No tienes permisos', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

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
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT * FROM usuarios WHERE username = %s AND activo = TRUE', (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['nombre'] = user['nombre']
            session['rol'] = user['rol']
            return redirect(url_for('dashboard'))
        else:
            flash('Usuario o contraseña incorrectos', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    fecha_inicio = request.args.get('fecha_inicio', '')
    fecha_fin = request.args.get('fecha_fin', '')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    query = 'SELECT * FROM pedidos'
    params = []
    
    if fecha_inicio and fecha_fin:
        query += ' WHERE fecha BETWEEN %s AND %s'
        params = [fecha_inicio, fecha_fin]
    elif fecha_inicio:
        query += ' WHERE fecha >= %s'
        params = [fecha_inicio]
    elif fecha_fin:
        query += ' WHERE fecha <= %s'
        params = [fecha_fin]
    
    query += ' ORDER BY fecha DESC, id DESC'
    
    cur.execute(query, params)
    pedidos = cur.fetchall()
    cur.close()
    conn.close()
    
    total_ventas = 0
    total_costos = 0
    total_utilidad = 0
    pedidos_grande = 0
    pedidos_mediano = 0
    ventas_grande = 0
    ventas_mediano = 0
    costos_grande = 0
    costos_mediano = 0
    
    pedidos_procesados = []
    for pedido in pedidos:
        try:
            totales = calcular_totales(
                pedido['producto'],
                pedido['cantidad'],
                float(pedido['descuento']) if pedido['descuento'] else 0,
                pedido['cuotas_visa'] if pedido['cuotas_visa'] else 0
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
                costos_grande += totales['costo_total']
            else:
                pedidos_mediano += pedido['cantidad']
                ventas_mediano += totales['total_con_recargo']
                costos_mediano += totales['costo_total']
        except:
            continue
    
    margen_promedio = (total_utilidad / total_ventas * 100) if total_ventas > 0 else 0
    
    estadisticas = {
        'total_ventas': total_ventas,
        'total_costos': total_costos,
        'total_utilidad': total_utilidad,
        'margen_promedio': margen_promedio,
        'total_pedidos': len(pedidos_procesados),
        'pedidos_grande': pedidos_grande,
        'pedidos_mediano': pedidos_mediano,
        'ventas_grande': ventas_grande,
        'ventas_mediano': ventas_mediano,
        'costos_grande': costos_grande,
        'costos_mediano': costos_mediano
    }
    
    return render_template('dashboard.html', 
                         pedidos=pedidos_procesados, 
                         estadisticas=estadisticas,
                         productos_config=PRODUCTOS_CONFIG,
                         fecha_inicio=fecha_inicio,
                         fecha_fin=fecha_fin)

@app.route('/exportar-excel')
@login_required
def exportar_excel():
    fecha_inicio = request.args.get('fecha_inicio', '')
    fecha_fin = request.args.get('fecha_fin', '')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    query = 'SELECT * FROM pedidos'
    params = []
    
    if fecha_inicio and fecha_fin:
        query += ' WHERE fecha BETWEEN %s AND %s'
        params = [fecha_inicio, fecha_fin]
    elif fecha_inicio:
        query += ' WHERE fecha >= %s'
        params = [fecha_inicio]
    elif fecha_fin:
        query += ' WHERE fecha <= %s'
        params = [fecha_fin]
    
    query += ' ORDER BY fecha DESC'
    cur.execute(query, params)
    pedidos = cur.fetchall()
    cur.close()
    conn.close()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Fecha', 'Cliente', 'Producto', 'Cantidad', 'Total Venta', 'Recargo VISA', 'Total', 'Costo', 'Utilidad'])
    
    for pedido in pedidos:
        try:
            totales = calcular_totales(
                pedido['producto'],
                pedido['cantidad'],
                float(pedido['descuento']) if pedido['descuento'] else 0,
                pedido['cuotas_visa'] if pedido['cuotas_visa'] else 0
            )
            writer.writerow([
                pedido['fecha'],
                pedido['cliente'],
                pedido['producto'],
                pedido['cantidad'],
                totales['total_venta'],
                totales['recargo_visa'],
                totales['total_con_recargo'],
                totales['costo_total'],
                totales['utilidad']
            ])
        except:
            continue
    
    output.seek(0)
    filename = f"pedidos_{datetime.now().strftime('%Y%m%d')}.csv"
    
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

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
        
        precio_unitario = PRODUCTOS_CONFIG[producto]['precio']
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO pedidos (fecha, cliente, producto, cantidad, precio_unitario, descuento, cuotas_visa, usuario_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (fecha, cliente, producto, cantidad, precio_unitario, descuento, cuotas_visa, session['user_id']))
        conn.commit()
        cur.close()
        conn.close()
        
        flash('Pedido registrado exitosamente', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('nuevo_pedido.html', productos=PRODUCTOS_CONFIG, recargos_visa=RECARGOS_VISA)

@app.route('/editar-pedido/<int:pedido_id>', methods=['GET', 'POST'])
@login_required
def editar_pedido(pedido_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == 'POST':
        fecha = request.form['fecha']
        cliente = request.form['cliente']
        producto = request.form['producto']
        cantidad = int(request.form['cantidad'])
        descuento = float(request.form.get('descuento', 0)) / 100
        cuotas_visa = int(request.form.get('cuotas_visa', 0))
        precio_unitario = PRODUCTOS_CONFIG[producto]['precio']
        
        cur.execute('''
            UPDATE pedidos SET fecha=%s, cliente=%s, producto=%s, cantidad=%s, precio_unitario=%s, descuento=%s, cuotas_visa=%s WHERE id=%s
        ''', (fecha, cliente, producto, cantidad, precio_unitario, descuento, cuotas_visa, pedido_id))
        conn.commit()
        cur.close()
        conn.close()
        
        flash('Pedido actualizado', 'success')
        return redirect(url_for('dashboard'))
    
    cur.execute('SELECT * FROM pedidos WHERE id = %s', (pedido_id,))
    pedido = cur.fetchone()
    cur.close()
    conn.close()
    
    return render_template('editar_pedido.html', pedido=pedido, productos=PRODUCTOS_CONFIG, recargos_visa=RECARGOS_VISA)

@app.route('/eliminar-pedido/<int:pedido_id>')
@login_required
def eliminar_pedido(pedido_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('DELETE FROM pedidos WHERE id = %s', (pedido_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash('Pedido eliminado', 'success')
    return redirect(url_for('dashboard'))

@app.route('/usuarios')
@admin_required
def usuarios():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM usuarios ORDER BY id')
    users = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('usuarios.html', usuarios=users)

@app.route('/usuarios/nuevo', methods=['GET', 'POST'])
@admin_required
def nuevo_usuario():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        nombre = request.form['nombre']
        rol = request.form.get('rol', 'usuario')
        hashed_password = generate_password_hash(password)
        
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute('INSERT INTO usuarios (username, password, nombre, rol) VALUES (%s, %s, %s, %s)',
                       (username, hashed_password, nombre, rol))
            conn.commit()
            flash('Usuario creado', 'success')
        except:
            flash('El usuario ya existe', 'error')
        cur.close()
        conn.close()
        return redirect(url_for('usuarios'))
    
    return render_template('nuevo_usuario.html')

@app.route('/usuarios/editar/<int:id>', methods=['GET', 'POST'])
@admin_required
def editar_usuario(id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == 'POST':
        nombre = request.form['nombre']
        rol = request.form.get('rol', 'usuario')
        activo = 'activo' in request.form
        cur.execute('UPDATE usuarios SET nombre=%s, rol=%s, activo=%s WHERE id=%s', (nombre, rol, activo, id))
        conn.commit()
        cur.close()
        conn.close()
        flash('Usuario actualizado', 'success')
        return redirect(url_for('usuarios'))
    
    cur.execute('SELECT * FROM usuarios WHERE id = %s', (id,))
    usuario = cur.fetchone()
    cur.close()
    conn.close()
    return render_template('editar_usuario.html', usuario=usuario)

@app.route('/usuarios/eliminar/<int:id>')
@admin_required
def eliminar_usuario(id):
    if id == session['user_id']:
        flash('No puedes eliminarte', 'error')
        return redirect(url_for('usuarios'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('DELETE FROM usuarios WHERE id = %s', (id,))
    conn.commit()
    cur.close()
    conn.close()
    flash('Usuario eliminado', 'success')
    return redirect(url_for('usuarios'))

@app.route('/cambiar-contrasena', methods=['GET', 'POST'])
@login_required
def cambiar_contrasena():
    if request.method == 'POST':
        actual = request.form['password_actual']
        nueva = request.form['password_nueva']
        confirmar = request.form['password_confirmar']
        
        if nueva != confirmar:
            flash('Las contraseñas no coinciden', 'error')
            return redirect(url_for('cambiar_contrasena'))
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT password FROM usuarios WHERE id = %s', (session['user_id'],))
        user = cur.fetchone()
        
        if not check_password_hash(user['password'], actual):
            flash('Contraseña actual incorrecta', 'error')
            cur.close()
            conn.close()
            return redirect(url_for('cambiar_contrasena'))
        
        hashed = generate_password_hash(nueva)
        cur.execute('UPDATE usuarios SET password = %s WHERE id = %s', (hashed, session['user_id']))
        conn.commit()
        cur.close()
        conn.close()
        flash('Contraseña actualizada', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('cambiar_contrasena.html')

if __name__ == '__main__':
    app.run(debug=True)
