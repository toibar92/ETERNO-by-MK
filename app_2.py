from flask import Flask, render_template, request, redirect, url_for, session, flash
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'tu_clave_secreta_aqui')

# Configuración de la base de datos
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Tabla de usuarios
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
    
    # Tabla de pedidos
    cur.execute('''
        CREATE TABLE IF NOT EXISTS pedidos (
            id SERIAL PRIMARY KEY,
            fecha DATE NOT NULL,
            cliente VARCHAR(100) NOT NULL,
            descripcion TEXT,
            cantidad INTEGER DEFAULT 1,
            precio_unitario DECIMAL(10,2) NOT NULL,
            total DECIMAL(10,2) NOT NULL,
            estado VARCHAR(20) DEFAULT 'pendiente',
            usuario_id INTEGER REFERENCES usuarios(id),
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Crear usuario admin por defecto si no existe
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

# Inicializar base de datos al arrancar
try:
    init_db()
except Exception as e:
    print(f"Error inicializando DB: {e}")

# Decorador para requerir login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Decorador para requerir admin
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('rol') != 'admin':
            flash('No tienes permisos para acceder a esta sección', 'error')
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
    # Obtener fechas del filtro
    fecha_inicio = request.args.get('fecha_inicio', '')
    fecha_fin = request.args.get('fecha_fin', '')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Construir query con filtros
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
    
    # Calcular totales
    total_ventas = sum(p['total'] for p in pedidos) if pedidos else 0
    total_pedidos = len(pedidos)
    
    cur.close()
    conn.close()
    
    return render_template('dashboard.html', 
                         pedidos=pedidos, 
                         total_ventas=total_ventas,
                         total_pedidos=total_pedidos,
                         fecha_inicio=fecha_inicio,
                         fecha_fin=fecha_fin)

@app.route('/registro', methods=['GET', 'POST'])
@login_required
def registro():
    if request.method == 'POST':
        fecha = request.form['fecha']
        cliente = request.form['cliente']
        descripcion = request.form.get('descripcion', '')
        cantidad = int(request.form.get('cantidad', 1))
        precio_unitario = float(request.form['precio_unitario'])
        total = cantidad * precio_unitario
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO pedidos (fecha, cliente, descripcion, cantidad, precio_unitario, total, usuario_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (fecha, cliente, descripcion, cantidad, precio_unitario, total, session['user_id']))
        conn.commit()
        cur.close()
        conn.close()
        
        flash('Pedido registrado exitosamente', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('registro.html', fecha_hoy=datetime.now().strftime('%Y-%m-%d'))

@app.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == 'POST':
        fecha = request.form['fecha']
        cliente = request.form['cliente']
        descripcion = request.form.get('descripcion', '')
        cantidad = int(request.form.get('cantidad', 1))
        precio_unitario = float(request.form['precio_unitario'])
        total = cantidad * precio_unitario
        
        cur.execute('''
            UPDATE pedidos 
            SET fecha=%s, cliente=%s, descripcion=%s, cantidad=%s, precio_unitario=%s, total=%s
            WHERE id=%s
        ''', (fecha, cliente, descripcion, cantidad, precio_unitario, total, id))
        conn.commit()
        cur.close()
        conn.close()
        
        flash('Pedido actualizado exitosamente', 'success')
        return redirect(url_for('dashboard'))
    
    cur.execute('SELECT * FROM pedidos WHERE id = %s', (id,))
    pedido = cur.fetchone()
    cur.close()
    conn.close()
    
    return render_template('registro.html', pedido=pedido, editar=True)

@app.route('/eliminar/<int:id>')
@login_required
def eliminar(id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('DELETE FROM pedidos WHERE id = %s', (id,))
    conn.commit()
    cur.close()
    conn.close()
    
    flash('Pedido eliminado', 'success')
    return redirect(url_for('dashboard'))

# ==================== GESTIÓN DE USUARIOS ====================

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
            cur.execute('''
                INSERT INTO usuarios (username, password, nombre, rol)
                VALUES (%s, %s, %s, %s)
            ''', (username, hashed_password, nombre, rol))
            conn.commit()
            flash('Usuario creado exitosamente', 'success')
        except psycopg2.IntegrityError:
            conn.rollback()
            flash('El nombre de usuario ya existe', 'error')
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
        
        cur.execute('''
            UPDATE usuarios SET nombre=%s, rol=%s, activo=%s WHERE id=%s
        ''', (nombre, rol, activo, id))
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
        flash('No puedes eliminar tu propio usuario', 'error')
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
            flash('Las contraseñas nuevas no coinciden', 'error')
            return redirect(url_for('cambiar_contrasena'))
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT password FROM usuarios WHERE id = %s', (session['user_id'],))
        user = cur.fetchone()
        
        if not check_password_hash(user['password'], actual):
            flash('La contraseña actual es incorrecta', 'error')
            cur.close()
            conn.close()
            return redirect(url_for('cambiar_contrasena'))
        
        hashed = generate_password_hash(nueva)
        cur.execute('UPDATE usuarios SET password = %s WHERE id = %s', (hashed, session['user_id']))
        conn.commit()
        cur.close()
        conn.close()
        
        flash('Contraseña actualizada exitosamente', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('cambiar_contrasena.html')

if __name__ == '__main__':
    app.run(debug=True)
