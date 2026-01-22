from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta, date
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import io
import secrets

app = Flask(__name__)

# CONFIGURACIÓN DE SEGURIDAD
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

if os.environ.get('RENDER'):
    app.config['SESSION_COOKIE_SECURE'] = True

DATABASE_URL = os.environ.get('DATABASE_URL')

# CAMBIO 1: Mediano → Pequeño (manteniendo los mismos valores)
PRODUCTOS_CONFIG = {
    'Grande': {
        'medidas': '94 x 152 cms',
        'precio': 15750,
        'costos': {'enmarcado': 1990, 'impresion': 887, 'drytac': 576, 'acrilico': 740, 'montaje': 300, 'papel': 340}
    },
    'Pequeño': {  # ← CAMBIO: Era "Mediano"
        'medidas': '75 x 122 cms',
        'precio': 13125,
        'costos': {'enmarcado': 1500, 'impresion': 595, 'drytac': 576, 'acrilico': 470, 'montaje': 300, 'papel': 320}
    }
}

COSTOS_VISA = {2: 0.05, 3: 0.0575, 6: 0.07, 10: 0.07, 12: 0.08}
METODOS_PAGO = ['Efectivo', 'Transferencia', 'Tarjeta débito', 'Pendiente']  # ← CAMBIO: Agregado "Pendiente"

# FUNCIONES DE SEGURIDAD
def get_client_ip():
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr or '0.0.0.0'

def log_security_event(event_type, user_id=None, details=""):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('INSERT INTO security_log (event_type, user_id, ip_address, details, timestamp) VALUES (%s, %s, %s, %s, NOW())',
                   (event_type, user_id, get_client_ip(), details))
        conn.commit()
        cur.close()
        conn.close()
    except:
        pass

def check_login_attempts(username, ip_address):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as attempts FROM login_attempts WHERE username = %s AND success = FALSE AND attempt_time > NOW() - INTERVAL '15 minutes'", (username,))
        result = cur.fetchone()
        cur.close()
        conn.close()
        if result and result['attempts'] >= 5:
            return False, "Demasiados intentos fallidos. Intenta en 15 minutos."
        return True, ""
    except:
        return True, ""

def log_login_attempt(username, ip_address, success):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('INSERT INTO login_attempts (username, ip_address, success, attempt_time) VALUES (%s, %s, %s, NOW())', (username, ip_address, success))
        conn.commit()
        cur.close()
        conn.close()
    except:
        pass

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY, username VARCHAR(50) UNIQUE NOT NULL, password VARCHAR(255) NOT NULL,
        nombre VARCHAR(100) NOT NULL, rol VARCHAR(20) DEFAULT 'usuario', activo BOOLEAN DEFAULT TRUE,
        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS pedidos (
        id SERIAL PRIMARY KEY, fecha DATE NOT NULL, cliente VARCHAR(100) NOT NULL, producto VARCHAR(50) NOT NULL,
        cantidad INTEGER DEFAULT 1, precio_unitario DECIMAL(10,2) NOT NULL, descuento DECIMAL(5,4) DEFAULT 0,
        anticipo DECIMAL(10,2) DEFAULT 0, metodo_pago_anticipo VARCHAR(50), cuotas_visa_anticipo INTEGER DEFAULT 0,
        fecha_sesion DATE, metodo_pago_saldo VARCHAR(50), cuotas_visa_saldo INTEGER DEFAULT 0,
        saldo_pagado BOOLEAN DEFAULT FALSE,
        usuario_id INTEGER REFERENCES usuarios(id), fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS login_attempts (
        id SERIAL PRIMARY KEY, username VARCHAR(50) NOT NULL, ip_address VARCHAR(45) NOT NULL,
        success BOOLEAN NOT NULL, attempt_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS security_log (
        id SERIAL PRIMARY KEY, event_type VARCHAR(50) NOT NULL, user_id INTEGER REFERENCES usuarios(id),
        ip_address VARCHAR(45), details TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    try:
        cur.execute('ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS anticipo DECIMAL(10,2) DEFAULT 0')
        cur.execute('ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS metodo_pago_anticipo VARCHAR(50)')
        cur.execute('ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS cuotas_visa_anticipo INTEGER DEFAULT 0')
        cur.execute('ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS fecha_sesion DATE')
        cur.execute('ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS metodo_pago_saldo VARCHAR(50)')
        cur.execute('ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS cuotas_visa_saldo INTEGER DEFAULT 0')
        cur.execute('ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS saldo_pagado BOOLEAN DEFAULT FALSE')  # ← NUEVO CAMPO
    except:
        pass
    
    cur.execute("SELECT * FROM usuarios WHERE username = 'admin'")
    if not cur.fetchone():
        hashed_password = generate_password_hash('Eterno2026!')
        cur.execute('INSERT INTO usuarios (username, password, nombre, rol) VALUES (%s, %s, %s, %s)',
                   ('admin', hashed_password, 'Administrador', 'admin'))
    
    conn.commit()
    cur.close()
    conn.close()

try:
    init_db()
except Exception as e:
    print(f"Error inicializando DB: {e}")

# CAMBIO 2: Función mejorada para calcular si el saldo está pendiente
def calcular_totales(producto, cantidad, descuento=0, anticipo=0, cuotas_visa_anticipo=0, cuotas_visa_saldo=0, fecha_sesion=None, saldo_pagado=False):
    config = PRODUCTOS_CONFIG[producto]
    precio_unitario = config['precio']
    costos_detalle = {k: v * cantidad for k, v in config['costos'].items()}
    costo_produccion = sum(costos_detalle.values())
    subtotal = precio_unitario * cantidad
    total_venta = subtotal * (1 - descuento)
    saldo_restante = total_venta - anticipo
    costo_visa_anticipo = anticipo * COSTOS_VISA.get(cuotas_visa_anticipo, 0) if cuotas_visa_anticipo > 0 else 0
    costo_visa_saldo = saldo_restante * COSTOS_VISA.get(cuotas_visa_saldo, 0) if cuotas_visa_saldo > 0 else 0
    costo_visa_total = costo_visa_anticipo + costo_visa_saldo
    costo_total = costo_produccion + costo_visa_total
    utilidad = total_venta - costo_total
    porcentaje_utilidad = (utilidad / total_venta * 100) if total_venta > 0 else 0
    disponible_anticipo = anticipo - costo_produccion - costo_visa_anticipo
    
    # NUEVA LÓGICA: Si la fecha de sesión ya pasó O está marcado como pagado, NO es saldo pendiente
    es_saldo_pendiente = False
    if saldo_restante > 0 and not saldo_pagado:
        if fecha_sesion:
            # Si tiene fecha de sesión, verificar si ya pasó
            if isinstance(fecha_sesion, str):
                fecha_sesion = datetime.strptime(fecha_sesion, '%Y-%m-%d').date()
            es_saldo_pendiente = fecha_sesion > date.today()
        else:
            # Si no tiene fecha de sesión, siempre es pendiente
            es_saldo_pendiente = True
    
    return {
        'precio_unitario': precio_unitario, 'subtotal': subtotal, 'total_venta': total_venta,
        'anticipo': anticipo, 'saldo_restante': saldo_restante, 'costos_detalle': costos_detalle,
        'costo_produccion': costo_produccion, 'costo_visa_anticipo': costo_visa_anticipo,
        'costo_visa_saldo': costo_visa_saldo, 'costo_visa_total': costo_visa_total,
        'costo_total': costo_total, 'utilidad': utilidad, 'porcentaje_utilidad': porcentaje_utilidad,
        'disponible_anticipo': disponible_anticipo, 'es_saldo_pendiente': es_saldo_pendiente
    }

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Debes iniciar sesión', 'warning')
            return redirect(url_for('login'))
        if 'last_activity' in session:
            try:
                last_activity = datetime.fromisoformat(session['last_activity'])
                if datetime.now() - last_activity > timedelta(minutes=30):
                    session.clear()
                    flash('Tu sesión ha expirado', 'warning')
                    return redirect(url_for('login'))
            except:
                session.clear()
                return redirect(url_for('login'))
        session['last_activity'] = datetime.now().isoformat()
        session.modified = True
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Debes iniciar sesión', 'warning')
            return redirect(url_for('login'))
        if session.get('rol') != 'admin':
            flash('No tienes permisos', 'error')
            return redirect(url_for('dashboard'))
        if 'last_activity' in session:
            try:
                last_activity = datetime.fromisoformat(session['last_activity'])
                if datetime.now() - last_activity > timedelta(minutes=30):
                    session.clear()
                    return redirect(url_for('login'))
            except:
                session.clear()
                return redirect(url_for('login'))
        session['last_activity'] = datetime.now().isoformat()
        session.modified = True
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if not username or not password:
            flash('Usuario y contraseña son requeridos', 'error')
            return render_template('login.html')
        ip_address = get_client_ip()
        can_attempt, message = check_login_attempts(username, ip_address)
        if not can_attempt:
            flash(message, 'error')
            log_security_event('login_rate_limit_exceeded', None, f"Usuario: {username}")
            return render_template('login.html')
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT * FROM usuarios WHERE username = %s AND activo = TRUE', (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        if user and check_password_hash(user['password'], password):
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['nombre'] = user['nombre']
            session['rol'] = user['rol']
            session['last_activity'] = datetime.now().isoformat()
            session.permanent = True
            log_login_attempt(username, ip_address, True)
            log_security_event('login_success', user['id'])
            flash(f'Bienvenido, {user["nombre"]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            log_login_attempt(username, ip_address, False)
            log_security_event('login_failed', None, f"Usuario: {username}")
            flash('Usuario o contraseña incorrectos', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    user_id = session.get('user_id')
    log_security_event('logout', user_id)
    session.clear()
    flash('Sesión cerrada exitosamente', 'info')
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
    total_anticipos = total_saldos_pendientes = total_costos = total_utilidad = 0
    pedidos_grande = pedidos_pequeno = anticipos_grande = anticipos_pequeno = 0
    saldos_grande = saldos_pequeno = costos_grande = costos_pequeno = 0
    pedidos_procesados = []
    for pedido in pedidos:
        try:
            anticipo = float(pedido['anticipo']) if pedido.get('anticipo') else 0
            totales = calcular_totales(pedido['producto'], pedido['cantidad'],
                                      float(pedido['descuento']) if pedido['descuento'] else 0,
                                      anticipo, pedido.get('cuotas_visa_anticipo') or 0,
                                      pedido.get('cuotas_visa_saldo') or 0,
                                      pedido.get('fecha_sesion'), pedido.get('saldo_pagado', False))
            pedidos_procesados.append({'id': pedido['id'], 'fecha': pedido['fecha'], 'cliente': pedido['cliente'],
                                      'producto': pedido['producto'], 'cantidad': pedido['cantidad'],
                                      'fecha_sesion': pedido.get('fecha_sesion'),
                                      'metodo_pago_anticipo': pedido.get('metodo_pago_anticipo', ''),
                                      'metodo_pago_saldo': pedido.get('metodo_pago_saldo', ''),
                                      'saldo_pagado': pedido.get('saldo_pagado', False), **totales})
            total_anticipos += anticipo
            # Solo sumar a pendientes si realmente es pendiente
            if totales['es_saldo_pendiente']:
                total_saldos_pendientes += totales['saldo_restante']
            total_costos += totales['costo_total']
            total_utilidad += totales['utilidad']
            if pedido['producto'] == 'Grande':
                pedidos_grande += pedido['cantidad']
                anticipos_grande += anticipo
                if totales['es_saldo_pendiente']:
                    saldos_grande += totales['saldo_restante']
                costos_grande += totales['costo_total']
            else:
                pedidos_pequeno += pedido['cantidad']
                anticipos_pequeno += anticipo
                if totales['es_saldo_pendiente']:
                    saldos_pequeno += totales['saldo_restante']
                costos_pequeno += totales['costo_total']
        except:
            continue
    total_ventas_proyectadas = total_anticipos + total_saldos_pendientes
    margen_promedio = (total_utilidad / total_ventas_proyectadas * 100) if total_ventas_proyectadas > 0 else 0
    estadisticas = {
        'total_anticipos': total_anticipos, 'total_saldos_pendientes': total_saldos_pendientes,
        'total_ventas_proyectadas': total_ventas_proyectadas, 'total_costos': total_costos,
        'total_utilidad': total_utilidad, 'margen_promedio': margen_promedio, 'total_pedidos': len(pedidos_procesados),
        'pedidos_grande': pedidos_grande, 'pedidos_pequeno': pedidos_pequeno,
        'anticipos_grande': anticipos_grande, 'anticipos_pequeno': anticipos_pequeno,
        'saldos_grande': saldos_grande, 'saldos_pequeno': saldos_pequeno,
        'costos_grande': costos_grande, 'costos_pequeno': costos_pequeno
    }
    return render_template('dashboard.html', pedidos=pedidos_procesados, estadisticas=estadisticas,
                         fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)

# NUEVA RUTA: Módulo de Saldos Pendientes
@app.route('/saldos-pendientes')
@login_required
def saldos_pendientes():
    conn = get_db_connection()
    cur = conn.cursor()
    # Obtener solo pedidos con saldo pendiente real
    cur.execute('''SELECT * FROM pedidos 
                   WHERE (fecha_sesion IS NULL OR fecha_sesion > CURRENT_DATE) 
                   AND saldo_pagado = FALSE
                   ORDER BY fecha_sesion ASC NULLS LAST, fecha DESC''')
    pedidos = cur.fetchall()
    cur.close()
    conn.close()
    
    pedidos_pendientes = []
    for pedido in pedidos:
        try:
            anticipo = float(pedido['anticipo']) if pedido.get('anticipo') else 0
            totales = calcular_totales(pedido['producto'], pedido['cantidad'],
                                      float(pedido['descuento']) if pedido['descuento'] else 0,
                                      anticipo, pedido.get('cuotas_visa_anticipo') or 0,
                                      pedido.get('cuotas_visa_saldo') or 0,
                                      pedido.get('fecha_sesion'), False)
            if totales['saldo_restante'] > 0:
                pedidos_pendientes.append({
                    'id': pedido['id'],
                    'fecha': pedido['fecha'],
                    'cliente': pedido['cliente'],
                    'producto': pedido['producto'],
                    'cantidad': pedido['cantidad'],
                    'fecha_sesion': pedido.get('fecha_sesion'),
                    'metodo_pago_saldo': pedido.get('metodo_pago_saldo', 'Pendiente'),
                    'cuotas_visa_saldo': pedido.get('cuotas_visa_saldo', 0),
                    **totales
                })
        except:
            continue
    
    return render_template('saldos_pendientes.html', pedidos=pedidos_pendientes, metodos_pago=METODOS_PAGO, costos_visa=COSTOS_VISA)

# NUEVA RUTA: Marcar saldo como pagado
@app.route('/marcar-saldo-pagado/<int:pedido_id>', methods=['POST'])
@login_required
def marcar_saldo_pagado(pedido_id):
    metodo_pago = request.form.get('metodo_pago_saldo', '')
    cuotas_visa = int(request.form.get('cuotas_visa_saldo', 0))
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''UPDATE pedidos SET saldo_pagado = TRUE, metodo_pago_saldo = %s, cuotas_visa_saldo = %s 
                   WHERE id = %s''', (metodo_pago, cuotas_visa, pedido_id))
    conn.commit()
    cur.close()
    conn.close()
    
    flash('Saldo marcado como pagado exitosamente', 'success')
    return redirect(url_for('saldos_pendientes'))

# Continúa con las demás rutas (exportar-excel, nuevo-pedido, etc.)...
# [El resto del código permanece igual, solo cambiando las referencias]
