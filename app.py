‎app.py.py‎
-651
Lines changed: 0 additions & 651 deletions
Original file line number	Diff line number	Diff line change
@@ -1,651 +0,0 @@
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime, timedelta
from functools import wraps
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'eterno_calculadora_secret_key_2026')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)
# Configuración de base de datos
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
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
    """Obtener conexión a la base de datos"""
    if DATABASE_URL:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(DATABASE_URL)
        return conn, True  # True = PostgreSQL
    else:
        import sqlite3
        conn = sqlite3.connect('calculadora_eterno.db')
        conn.row_factory = sqlite3.Row
        return conn, False  # False = SQLite
def execute_query(query, params=None, fetch_one=False, fetch_all=False, return_id=False):
    """Ejecutar query con soporte para PostgreSQL y SQLite"""
    conn, is_postgres = get_db()
    
    if is_postgres:
        import psycopg2.extras
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # Convertir placeholders de SQLite (?) a PostgreSQL (%s)
        if params:
            query = query.replace('?', '%s')
        # Para INSERT con RETURNING en PostgreSQL
        if return_id and 'INSERT' in query.upper():
            query = query.rstrip(';') + ' RETURNING id'
    else:
        cursor = conn.cursor()
    
    try:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        result = None
        if fetch_one:
            row = cursor.fetchone()
            if row and is_postgres:
                result = dict(row)
            else:
                result = row
        elif fetch_all:
            rows = cursor.fetchall()
            if rows and is_postgres:
                result = [dict(row) for row in rows]
            else:
                result = rows
        elif return_id and is_postgres:
            result = cursor.fetchone()['id']
        
        conn.commit()
        return result
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()
def init_db():
    """Inicializar la base de datos"""
    conn, is_postgres = get_db()
    cursor = conn.cursor()
    
    try:
        if is_postgres:
            # PostgreSQL
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS usuarios (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(255) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    nombre VARCHAR(255) NOT NULL,
                    es_admin BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pedidos (
                    id SERIAL PRIMARY KEY,
                    fecha DATE NOT NULL,
                    cliente VARCHAR(255) NOT NULL,
                    producto VARCHAR(50) NOT NULL,
                    cantidad INTEGER NOT NULL,
                    precio_unitario REAL NOT NULL,
                    descuento REAL DEFAULT 0,
                    cuotas_visa INTEGER DEFAULT 0,
                    usuario_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
                )
            ''')
            
            # Verificar si ya existen usuarios
            cursor.execute('SELECT COUNT(*) as count FROM usuarios')
            count = cursor.fetchone()[0]
            
            if count == 0:
                cursor.execute('''
                    INSERT INTO usuarios (username, password, nombre, es_admin) 
                    VALUES (%s, %s, %s, %s)
                ''', ('admin', generate_password_hash('eterno2026'), 'Administrador', True))
                
                cursor.execute('''
                    INSERT INTO usuarios (username, password, nombre, es_admin) 
                    VALUES (%s, %s, %s, %s)
                ''', ('usuario', generate_password_hash('eterno2026'), 'Usuario', False))
        else:
            # SQLite
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    nombre TEXT NOT NULL,
                    es_admin INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
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
            
            cursor.execute('SELECT COUNT(*) as count FROM usuarios')
            if cursor.fetchone()[0] == 0:
                cursor.execute('''
                    INSERT INTO usuarios (username, password, nombre, es_admin) 
                    VALUES (?, ?, ?, ?)
                ''', ('admin', generate_password_hash('eterno2026'), 'Administrador', 1))
                
                cursor.execute('''
                    INSERT INTO usuarios (username, password, nombre, es_admin) 
                    VALUES (?, ?, ?, ?)
                ''', ('usuario', generate_password_hash('eterno2026'), 'Usuario', 0))
        
        conn.commit()
        print("✅ Base de datos inicializada correctamente")
        if DATABASE_URL:
            print("✅ Usando PostgreSQL (datos persistentes)")
        else:
            print("⚠️ Usando SQLite (datos temporales)")
    except Exception as e:
        print(f"❌ Error inicializando BD: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Por favor inicia sesión para acceder.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Por favor inicia sesión para acceder.', 'warning')
            return redirect(url_for('login'))
        if not session.get('es_admin'):
            flash('No tienes permisos de administrador.', 'danger')
            return redirect(url_for('dashboard'))
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
        
        user = execute_query('SELECT * FROM usuarios WHERE username = ?', (username,), fetch_one=True)
        
        if user and check_password_hash(user['password'], password):
            session.permanent = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['nombre'] = user['nombre']
            session['es_admin'] = bool(user['es_admin'])
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
    # Obtener filtros de fecha
    fecha_inicio = request.args.get('fecha_inicio', '')
    fecha_fin = request.args.get('fecha_fin', '')
    
    # Construir query con filtros
    if fecha_inicio and fecha_fin:
        pedidos = execute_query(
            'SELECT * FROM pedidos WHERE fecha >= ? AND fecha <= ? ORDER BY fecha DESC, id DESC',
            (fecha_inicio, fecha_fin),
            fetch_all=True
        )
    elif fecha_inicio:
        pedidos = execute_query(
            'SELECT * FROM pedidos WHERE fecha >= ? ORDER BY fecha DESC, id DESC',
            (fecha_inicio,),
            fetch_all=True
        )
    elif fecha_fin:
        pedidos = execute_query(
            'SELECT * FROM pedidos WHERE fecha <= ? ORDER BY fecha DESC, id DESC',
            (fecha_fin,),
            fetch_all=True
        )
    else:
        pedidos = execute_query(
            'SELECT * FROM pedidos ORDER BY fecha DESC, id DESC',
            fetch_all=True
        )
    
    if pedidos is None:
        pedidos = []
    
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
            pedido['descuento'] or 0,
            pedido['cuotas_visa'] or 0
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
                         productos_config=PRODUCTOS_CONFIG,
                         fecha_inicio=fecha_inicio,
                         fecha_fin=fecha_fin)
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
        
        execute_query('''
            INSERT INTO pedidos (fecha, cliente, producto, cantidad, precio_unitario, 
                               descuento, cuotas_visa, usuario_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (fecha, cliente, producto, cantidad, precio_unitario, descuento, 
              cuotas_visa, session['user_id']))
        
        flash('Pedido registrado exitosamente.', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('nuevo_pedido.html', 
                         productos=PRODUCTOS_CONFIG,
                         recargos_visa=RECARGOS_VISA)
@app.route('/editar-pedido/<int:pedido_id>', methods=['GET', 'POST'])
@login_required
def editar_pedido(pedido_id):
    if request.method == 'POST':
        fecha = request.form['fecha']
        cliente = request.form['cliente']
        producto = request.form['producto']
        cantidad = int(request.form['cantidad'])
        descuento = float(request.form.get('descuento', 0)) / 100
        cuotas_visa = int(request.form.get('cuotas_visa', 0))
        
        precio_unitario = PRODUCTOS_CONFIG[producto]['precio']
        
        execute_query('''
            UPDATE pedidos 
            SET fecha=?, cliente=?, producto=?, cantidad=?, precio_unitario=?,
                descuento=?, cuotas_visa=?
            WHERE id=?
        ''', (fecha, cliente, producto, cantidad, precio_unitario, 
              descuento, cuotas_visa, pedido_id))
        
        flash('Pedido actualizado exitosamente.', 'success')
        return redirect(url_for('dashboard'))
    
    pedido = execute_query('SELECT * FROM pedidos WHERE id = ?', (pedido_id,), fetch_one=True)
    
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
    execute_query('DELETE FROM pedidos WHERE id = ?', (pedido_id,))
    flash('Pedido eliminado exitosamente.', 'success')
    return redirect(url_for('dashboard'))
# ==================== GESTIÓN DE USUARIOS ====================
@app.route('/usuarios')
@admin_required
def lista_usuarios():
    usuarios = execute_query('SELECT id, username, nombre, es_admin, created_at FROM usuarios ORDER BY id', fetch_all=True)
    if usuarios is None:
        usuarios = []
    return render_template('usuarios.html', usuarios=usuarios)
@app.route('/usuario/nuevo', methods=['GET', 'POST'])
@admin_required
def nuevo_usuario():
    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        password = request.form['password']
        nombre = request.form['nombre'].strip()
        es_admin = 'es_admin' in request.form
        
        # Verificar si el usuario ya existe
        existente = execute_query('SELECT id FROM usuarios WHERE username = ?', (username,), fetch_one=True)
        if existente:
            flash('El nombre de usuario ya existe.', 'danger')
            return render_template('nuevo_usuario.html')
        
        execute_query('''
            INSERT INTO usuarios (username, password, nombre, es_admin)
            VALUES (?, ?, ?, ?)
        ''', (username, generate_password_hash(password), nombre, es_admin))
        
        flash(f'Usuario "{username}" creado exitosamente.', 'success')
        return redirect(url_for('lista_usuarios'))
    
    return render_template('nuevo_usuario.html')
@app.route('/usuario/editar/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def editar_usuario(user_id):
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        es_admin = 'es_admin' in request.form
        new_password = request.form.get('new_password', '').strip()
        
        if new_password:
            execute_query('''
                UPDATE usuarios SET nombre=?, es_admin=?, password=? WHERE id=?
            ''', (nombre, es_admin, generate_password_hash(new_password), user_id))
        else:
            execute_query('''
                UPDATE usuarios SET nombre=?, es_admin=? WHERE id=?
            ''', (nombre, es_admin, user_id))
        
        flash('Usuario actualizado exitosamente.', 'success')
        return redirect(url_for('lista_usuarios'))
    
    usuario = execute_query('SELECT * FROM usuarios WHERE id = ?', (user_id,), fetch_one=True)
    if not usuario:
        flash('Usuario no encontrado.', 'danger')
        return redirect(url_for('lista_usuarios'))
    
    return render_template('editar_usuario.html', usuario=usuario)
@app.route('/usuario/eliminar/<int:user_id>')
@admin_required
def eliminar_usuario(user_id):
    # No permitir eliminar el propio usuario
    if user_id == session['user_id']:
        flash('No puedes eliminar tu propio usuario.', 'danger')
        return redirect(url_for('lista_usuarios'))
    
    execute_query('DELETE FROM usuarios WHERE id = ?', (user_id,))
    flash('Usuario eliminado exitosamente.', 'success')
    return redirect(url_for('lista_usuarios'))
@app.route('/cambiar-contrasena', methods=['GET', 'POST'])
@login_required
def cambiar_contrasena():
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        # Verificar contraseña actual
        user = execute_query('SELECT * FROM usuarios WHERE id = ?', (session['user_id'],), fetch_one=True)
        
        if not check_password_hash(user['password'], current_password):
            flash('La contraseña actual es incorrecta.', 'danger')
            return render_template('cambiar_contrasena.html')
        
        if new_password != confirm_password:
            flash('Las contraseñas nuevas no coinciden.', 'danger')
            return render_template('cambiar_contrasena.html')
        
        if len(new_password) < 6:
            flash('La contraseña debe tener al menos 6 caracteres.', 'danger')
            return render_template('cambiar_contrasena.html')
        
        execute_query('UPDATE usuarios SET password = ? WHERE id = ?', 
                     (generate_password_hash(new_password), session['user_id']))
        
        flash('Contraseña cambiada exitosamente.', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('cambiar_contrasena.html')
# ==================== EXPORTAR ====================
@app.route('/exportar-excel')
@login_required
def exportar_excel():
    # Obtener filtros de fecha si existen
    fecha_inicio = request.args.get('fecha_inicio', '')
    fecha_fin = request.args.get('fecha_fin', '')
    
    if fecha_inicio and fecha_fin:
        pedidos = execute_query(
            'SELECT * FROM pedidos WHERE fecha >= ? AND fecha <= ? ORDER BY fecha DESC',
            (fecha_inicio, fecha_fin),
            fetch_all=True
        )
    else:
        pedidos = execute_query('SELECT * FROM pedidos ORDER BY fecha DESC', fetch_all=True)
    
    if pedidos is None:
        pedidos = []
    
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
            pedido['descuento'] or 0,
            pedido['cuotas_visa'] or 0
        )
        
        ws.cell(row=idx, column=1, value=pedido['id'])
        ws.cell(row=idx, column=2, value=str(pedido['fecha']))
        ws.cell(row=idx, column=3, value=pedido['cliente'])
        ws.cell(row=idx, column=4, value=pedido['producto'])
        ws.cell(row=idx, column=5, value=pedido['cantidad'])
        ws.cell(row=idx, column=6, value=totales['precio_unitario'])
        ws.cell(row=idx, column=7, value=totales['subtotal'])
        ws.cell(row=idx, column=8, value=(pedido['descuento'] or 0) * 100)
        ws.cell(row=idx, column=9, value=totales['total_venta'])
        ws.cell(row=idx, column=10, value=pedido['cuotas_visa'] if pedido['cuotas_visa'] and pedido['cuotas_visa'] > 0 else '')
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
# Inicializar base de datos al importar
init_db()
if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
0 commit comments
Comments
0
