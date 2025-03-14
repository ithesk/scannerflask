# app.py
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, session
import os
import csv
import json
import xmlrpc.client
from collections import Counter
import pandas as pd
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'odoo_transfer_secret_key'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'csv', 'txt'}

# Asegurar que exista el directorio de uploads
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Archivo de configuración
CONFIG_FILE = 'config.json'

# Configuración por defecto
DEFAULT_CONFIG = {
    'url': 'http://localhost:8069',
    'db': 'odoo12',
    'username': 'admin',
    'password': 'admin'
}

# Variable global de configuración
ODOO_CONFIG = {}

# Cargar configuración
def load_config():
    global ODOO_CONFIG
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                ODOO_CONFIG = json.load(f)
        else:
            ODOO_CONFIG = DEFAULT_CONFIG.copy()
            save_config()
    except Exception as e:
        print(f"Error al cargar configuración: {str(e)}")
        ODOO_CONFIG = DEFAULT_CONFIG.copy()

# Guardar configuración
def save_config():
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(ODOO_CONFIG, f, indent=4)
        return True
    except Exception as e:
        print(f"Error al guardar configuración: {str(e)}")
        return False

# Inicializar configuración al iniciar la aplicación
load_config()

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def get_odoo_locations():
    """Obtener lista de ubicaciones desde Odoo"""
    try:
        # Conexión con Odoo
        common = xmlrpc.client.ServerProxy(f"{ODOO_CONFIG['url']}/xmlrpc/2/common")
        uid = common.authenticate(ODOO_CONFIG['db'], ODOO_CONFIG['username'], ODOO_CONFIG['password'], {})
        models = xmlrpc.client.ServerProxy(f"{ODOO_CONFIG['url']}/xmlrpc/2/object")
        
        # Buscar ubicaciones
        location_ids = models.execute_kw(
            ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
            'stock.location', 'search_read',
            [[('usage', '=', 'internal')]], 
            {'fields': ['id', 'name', 'complete_name']}
        )
        
        return location_ids
    except Exception as e:
        print(f"Error al obtener ubicaciones: {str(e)}")
        return []

def get_odoo_connection():
    """Establecer conexión con Odoo y devolver uid y models"""
    try:
        common = xmlrpc.client.ServerProxy(f"{ODOO_CONFIG['url']}/xmlrpc/2/common")
        uid = common.authenticate(ODOO_CONFIG['db'], ODOO_CONFIG['username'], ODOO_CONFIG['password'], {})
        models = xmlrpc.client.ServerProxy(f"{ODOO_CONFIG['url']}/xmlrpc/2/object")
        return uid, models
    except Exception as e:
        print(f"Error al conectar con Odoo: {str(e)}")
        return None, None

def create_inventory_transfer(source_location_id, dest_location_id, products_data):
    """
    Crear transferencia interna en Odoo
    
    Args:
        source_location_id: ID de la ubicación origen
        dest_location_id: ID de la ubicación destino
        products_data: diccionario {barcode: quantity}
    
    Returns:
        dict: Resultado de la operación
    """
    try:
        # Log para depuración
        print(f"Source location ID: {source_location_id}, type: {type(source_location_id)}")
        print(f"Dest location ID: {dest_location_id}, type: {type(dest_location_id)}")
        print(f"Número de productos diferentes: {len(products_data)}")
        print(f"Total de unidades: {sum(products_data.values())}")
        
        # Verificar que las ubicaciones son válidas
        if not source_location_id or not dest_location_id:
            return {'success': False, 'message': 'Debes seleccionar ubicaciones de origen y destino'}
            
        # Convertir a enteros después de validar
        source_location_id = int(source_location_id)
        dest_location_id = int(dest_location_id)
        
        # Limitar cantidades grandes de productos (XML-RPC generalmente tiene límite de 2^31-1)
        max_int = 100  # Limitamos a 100 unidades por producto para evitar problemas
        limited_products = {}
        for barcode, qty in products_data.items():
            if qty > max_int:
                print(f"Producto {barcode} tiene {qty} unidades, limitando a {max_int}")
                limited_products[barcode] = max_int
            else:
                limited_products[barcode] = qty
        
        # Si hay más de 20 productos diferentes, dividirlos en lotes
        max_products = 20
        if len(limited_products) > max_products:
            print(f"Demasiados productos diferentes, limitando a {max_products}")
            limited_products = dict(list(limited_products.items())[:max_products])
        
        # Conexión con Odoo
        uid, models = get_odoo_connection()
        if not uid or not models:
            return {'success': False, 'message': 'Error de conexión con Odoo'}
        
        # Crear picking (transferencia)
        picking_type_ids = models.execute_kw(
            ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
            'stock.picking.type', 'search',
            [[('code', '=', 'internal')]]
        )
        
        if not picking_type_ids:
            return {'success': False, 'message': 'No se encontró tipo de transferencia interna'}
        
        picking_vals = {
            'picking_type_id': picking_type_ids[0],
            'location_id': source_location_id,
            'location_dest_id': dest_location_id,
            'origin': 'Transferencia desde App Scanner'
        }
        
        picking_id = models.execute_kw(
            ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
            'stock.picking', 'create', [picking_vals]
        )
        
        # Procesar cada producto
        moves_to_create = []
        products_not_found = []
        
        for barcode, qty in limited_products.items():
            # Buscar producto por código de barras
            product_ids = models.execute_kw(
                ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
                'product.product', 'search',
                [[('barcode', '=', barcode)]]
            )
            
            if not product_ids:
                products_not_found.append(barcode)
                continue
                
            product_id = product_ids[0]
            
            # Obtener la unidad de medida del producto
            product_data = models.execute_kw(
                ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
                'product.product', 'read',
                [product_id],
                {'fields': ['uom_id']}
            )
            
            uom_id = product_data[0]['uom_id'][0] if product_data and product_data[0].get('uom_id') else 1
            
            # Crear movimiento de stock
            move_vals = {
                'name': f'Movimiento de {barcode}',
                'product_id': product_id,
                'product_uom_qty': qty,
                'picking_id': picking_id,
                'location_id': source_location_id,
                'location_dest_id': dest_location_id,
                'product_uom': uom_id,
            }
            
            moves_to_create.append(move_vals)
        
        # Crear los movimientos en lote, máximo 5 a la vez para evitar límites
        batch_size = 5
        for i in range(0, len(moves_to_create), batch_size):
            batch = moves_to_create[i:i+batch_size]
            models.execute_kw(
                ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
                'stock.move', 'create', [batch]
            )
            print(f"Creado lote {i//batch_size + 1} de {(len(moves_to_create) + batch_size - 1) // batch_size}")
        
        # Confirmar la transferencia si se crearon movimientos
        if moves_to_create:
            models.execute_kw(
                ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
                'stock.picking', 'action_confirm', [picking_id]
            )
            
            result = {
                'success': True,
                'picking_id': picking_id,
                'products_count': len(moves_to_create),
                'products_not_found': products_not_found
            }
        else:
            # Eliminar picking si no hay productos válidos
            models.execute_kw(
                ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
                'stock.picking', 'unlink', [picking_id]
            )
            result = {
                'success': False,
                'message': 'No se encontraron productos válidos',
                'products_not_found': products_not_found
            }
            
        return result
        
    except Exception as e:
        print(f"Error en create_inventory_transfer: {str(e)}")
        return {'success': False, 'message': str(e)}

def get_pending_transfers(location_id=None, search_term=None):
    """Obtener transferencias pendientes para recepción"""
    try:
        uid, models = get_odoo_connection()
        if not uid or not models:
            return []
        
        # Construir dominio para búsqueda
        domain = [('state', 'in', ['assigned', 'partially_available', 'confirmed'])]
        
        if location_id:
            domain.append(('location_dest_id', '=', int(location_id)))
            
        if search_term:
            domain.append('|')
            domain.append(('name', 'ilike', search_term))
            domain.append(('origin', 'ilike', search_term))
        
        # Obtener transferencias
        transfers = models.execute_kw(
            ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
            'stock.picking', 'search_read',
            [domain],
            {'fields': ['id', 'name', 'origin', 'state', 'location_id', 'location_dest_id', 'move_line_ids', 'create_date']}
        )
        
        # Obtener nombres de ubicaciones
        location_ids = set()
        for transfer in transfers:
            location_ids.add(transfer['location_id'][0])
            location_ids.add(transfer['location_dest_id'][0])
        
        locations = {}
        if location_ids:
            loc_data = models.execute_kw(
                ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
                'stock.location', 'read',
                [list(location_ids)],
                {'fields': ['id', 'name', 'complete_name']}
            )
            for loc in loc_data:
                locations[loc['id']] = loc['complete_name'] or loc['name']
        
        # Contar productos por transferencia
        for transfer in transfers:
            # Añadir nombres de ubicaciones
            transfer['location_name'] = locations.get(transfer['location_id'][0], 'Desconocido')
            transfer['location_dest_name'] = locations.get(transfer['location_dest_id'][0], 'Desconocido')
            
            # Contar productos
            if transfer['move_line_ids']:
                move_lines = models.execute_kw(
                    ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
                    'stock.move.line', 'read',
                    [transfer['move_line_ids']],
                    {'fields': ['product_id', 'product_uom_qty']}
                )
                transfer['products_count'] = len(move_lines)
            else:
                transfer['products_count'] = 0
                
            # Estado en texto
            states = {
                'draft': 'Borrador',
                'confirmed': 'Esperando disponibilidad',
                'waiting': 'Esperando otra operación',
                'partially_available': 'Parcialmente disponible',
                'assigned': 'Listo para transferir',
                'done': 'Realizado',
                'cancel': 'Cancelado'
            }
            transfer['state_label'] = states.get(transfer['state'], transfer['state'])
            
            # Formatear fecha
            if transfer.get('create_date'):
                try:
                    date_obj = datetime.strptime(transfer['create_date'], "%Y-%m-%d %H:%M:%S")
                    transfer['create_date'] = date_obj.strftime("%d/%m/%Y %H:%M")
                except:
                    pass
        
        return transfers
        
    except Exception as e:
        print(f"Error al obtener transferencias: {str(e)}")
        return []

def get_transfer_details(transfer_id):
    """Obtener detalles de una transferencia específica"""
    try:
        uid, models = get_odoo_connection()
        if not uid or not models:
            return None, []
        
        # Obtener datos de la transferencia
        transfer_data = models.execute_kw(
            ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
            'stock.picking', 'read',
            [int(transfer_id)],
            {'fields': ['id', 'name', 'origin', 'state', 'location_id', 'location_dest_id', 'move_ids_without_package', 'create_date']}
        )
        
        if not transfer_data:
            return None, []
            
        transfer = transfer_data[0]
        
        # Obtener nombres de ubicaciones
        loc_data = models.execute_kw(
            ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
            'stock.location', 'read',
            [[transfer['location_id'][0], transfer['location_dest_id'][0]]],
            {'fields': ['id', 'name', 'complete_name']}
        )
        
        locations = {}
        for loc in loc_data:
            locations[loc['id']] = loc['complete_name'] or loc['name']
            
        transfer['location_name'] = locations.get(transfer['location_id'][0], 'Desconocido')
        transfer['location_dest_name'] = locations.get(transfer['location_dest_id'][0], 'Desconocido')
        
        # Estado en texto
        states = {
            'draft': 'Borrador',
            'confirmed': 'Esperando disponibilidad',
            'waiting': 'Esperando otra operación',
            'partially_available': 'Parcialmente disponible',
            'assigned': 'Listo para transferir',
            'done': 'Realizado',
            'cancel': 'Cancelado'
        }
        transfer['state_label'] = states.get(transfer['state'], transfer['state'])
        
        # Formatear fecha
        if transfer.get('create_date'):
            try:
                date_obj = datetime.strptime(transfer['create_date'], "%Y-%m-%d %H:%M:%S")
                transfer['create_date'] = date_obj.strftime("%d/%m/%Y %H:%M")
            except:
                pass
        
        # Obtener productos de la transferencia
        productos = []
        
        if transfer['move_ids_without_package']:
            moves = models.execute_kw(
                ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
                'stock.move', 'read',
                [transfer['move_ids_without_package']],
                {'fields': ['product_id', 'product_uom_qty', 'state']}
            )
            
            product_ids = [move['product_id'][0] for move in moves]
            products_data = models.execute_kw(
                ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
                'product.product', 'read',
                [product_ids],
                {'fields': ['id', 'name', 'barcode']}
            )
            
            products_dict = {prod['id']: prod for prod in products_data}
            
            for move in moves:
                product = products_dict.get(move['product_id'][0])
                if product:
                    productos.append({
                        'id': product['id'],
                        'name': product['name'],
                        'barcode': product['barcode'] or 'SIN CÓDIGO',
                        'qty': move['product_uom_qty'],
                        'state': move['state']
                    })
        
        return transfer, productos
        
    except Exception as e:
        print(f"Error al obtener detalles de transferencia: {str(e)}")
        return None, []

def validate_transfer(transfer_id):
    """Validar una transferencia en Odoo"""
    try:
        uid, models = get_odoo_connection()
        if not uid or not models:
            return False, "Error de conexión con Odoo"
        
        # Validar la transferencia
        result = models.execute_kw(
            ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
            'stock.picking', 'button_validate',
            [int(transfer_id)]
        )
        
        # Si devuelve un diccionario, podría ser un wizard que requiere confirmación adicional
        if isinstance(result, dict) and result.get('res_model') == 'stock.immediate.transfer':
            wizard_id = result.get('res_id')
            if wizard_id:
                # Confirmar el wizard de transferencia inmediata
                models.execute_kw(
                    ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
                    'stock.immediate.transfer', 'process',
                    [wizard_id]
                )
        
        return True, "Transferencia validada correctamente"
        
    except Exception as e:
        error_msg = str(e)
        return False, f"Error al validar transferencia: {error_msg}"

@app.route('/')
def index():
    locations = get_odoo_locations()
    return render_template('index.html', locations=locations)

@app.route('/scan', methods=['POST'])
def process_scan():
    """Procesar los códigos de barras escaneados directamente"""
    source_location = request.form.get('source_location')
    dest_location = request.form.get('dest_location')
    scanned_codes = request.form.get('scanned_codes', '')
    
    if not scanned_codes:
        flash('No se han proporcionado códigos de barras', 'error')
        return redirect(url_for('index'))
    
    # Procesar los códigos escaneados (uno por línea)
    codes_list = [code.strip() for code in scanned_codes.strip().split('\n') if code.strip()]
    products_counter = Counter(codes_list)
    
    # Crear la transferencia
    result = create_inventory_transfer(source_location, dest_location, products_counter)
    
    if result.get('success'):
        flash(f'Transferencia creada con éxito. Se transfirieron {result["products_count"]} productos.', 'success')
        if result.get('products_not_found'):
            flash(f'No se encontraron {len(result["products_not_found"])} productos: {", ".join(result["products_not_found"])}', 'warning')
    else:
        flash(f'Error al crear transferencia: {result.get("message")}', 'error')
    
    return redirect(url_for('index'))

@app.route('/upload', methods=['POST'])
def upload_file():
    """Procesar archivo CSV subido"""
    if 'file' not in request.files:
        flash('No se seleccionó ningún archivo', 'error')
        return redirect(url_for('index'))
    
    file = request.files['file']
    source_location = request.form.get('source_location')
    dest_location = request.form.get('dest_location')
    
    if file.filename == '':
        flash('No se seleccionó ningún archivo', 'error')
        return redirect(url_for('index'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        try:
            # Leer el archivo como una sola columna de códigos
            df = pd.read_csv(filepath, header=None, names=['barcode'])
            products_counter = Counter(df['barcode'].tolist())
            
            # Crear la transferencia
            result = create_inventory_transfer(source_location, dest_location, products_counter)
            
            if result.get('success'):
                flash(f'Transferencia creada con éxito. Se transfirieron {result["products_count"]} productos.', 'success')
                if result.get('products_not_found'):
                    flash(f'No se encontraron {len(result["products_not_found"])} productos: {", ".join(result["products_not_found"])}', 'warning')
            else:
                flash(f'Error al crear transferencia: {result.get("message")}', 'error')
                
        except Exception as e:
            flash(f'Error al procesar el archivo: {str(e)}', 'error')
    else:
        flash('Tipo de archivo no permitido', 'error')
    
    return redirect(url_for('index'))

@app.route('/config', methods=['GET', 'POST'])
def config():
    """Página de configuración para los parámetros de Odoo"""
    if request.method == 'POST':
        # Actualizar configuración
        ODOO_CONFIG['url'] = request.form.get('url')
        ODOO_CONFIG['db'] = request.form.get('db')
        ODOO_CONFIG['username'] = request.form.get('username')
        ODOO_CONFIG['password'] = request.form.get('password')
        
        # Guardar configuración en archivo
        save_config()
        
        # Probar conexión
        try:
            common = xmlrpc.client.ServerProxy(f"{ODOO_CONFIG['url']}/xmlrpc/2/common")
            uid = common.authenticate(ODOO_CONFIG['db'], ODOO_CONFIG['username'], ODOO_CONFIG['password'], {})
            if uid:
                flash('Conexión exitosa a Odoo. Configuración guardada.', 'success')
            else:
                flash('Error de autenticación en Odoo. Configuración guardada de todos modos.', 'warning')
        except Exception as e:
            flash(f'Error de conexión: {str(e)}. Configuración guardada de todos modos.', 'warning')
        
        return redirect(url_for('config'))
    
    return render_template('config.html', config=ODOO_CONFIG)

@app.route('/add_barcode', methods=['POST'])
def add_barcode():
    """API para añadir un código de barras escaneado (para AJAX)"""
    barcode = request.json.get('barcode')
    if barcode:
        return jsonify({'success': True, 'barcode': barcode})
    return jsonify({'success': False, 'message': 'Código de barras no proporcionado'})

@app.route('/recepcion')
def recepcion():
    """Página de recepción de transferencias"""
    # Obtener parámetros de filtro
    ubicacion_id = request.args.get('ubicacion')
    busqueda = request.args.get('buscar', '')
    
    # Obtener transferencias pendientes
    transferencias = get_pending_transfers(ubicacion_id, busqueda)
    
    # Obtener ubicaciones para el filtro
    ubicaciones = get_odoo_locations()
    
    return render_template('recepcion.html', 
                          transferencias=transferencias, 
                          ubicaciones=ubicaciones,
                          ubicacion_seleccionada=ubicacion_id,
                          busqueda=busqueda)

@app.route('/recepcion/<int:id>')
def procesar_recepcion(id):
    """Página para procesar la recepción de una transferencia específica"""
    # Obtener información de la transferencia
    transferencia, productos = get_transfer_details(id)
    
    if not transferencia:
        flash('No se encontró la transferencia solicitada', 'error')
        return redirect(url_for('recepcion'))
    
    # Obtener productos verificados de la sesión
    productos_verificados = session.get(f'verificados_{id}', [])
    
    # Calcular progreso
    if productos:
        progress = (len(productos_verificados) / len(productos)) * 100
        all_verified = len(productos_verificados) == len(productos)
    else:
        progress = 0
        all_verified = False
    
    return render_template('procesar_recepcion.html',
                           transferencia=transferencia,
                           productos=productos,
                           productos_verificados=productos_verificados,
                           progress=progress,
                           all_verified=all_verified)

@app.route('/verificar/<int:id>', methods=['POST'])
def verificar_producto(id):
    """Verificar un producto escaneado"""
    barcode = request.form.get('barcode', '').strip()
    
    if not barcode:
        flash('No se proporcionó un código de barras válido', 'error')
        return redirect(url_for('procesar_recepcion', id=id))
    
    # Obtener la transferencia y sus productos
    transferencia, productos = get_transfer_details(id)
    
    if not transferencia or not productos:
        flash('No se encontró la transferencia solicitada', 'error')
        return redirect(url_for('recepcion'))
    
    # Verificar si el código de barras pertenece a algún producto de la transferencia
    producto_encontrado = False
    for producto in productos:
        if producto['barcode'] == barcode:
            producto_encontrado = True
            break
    
    # Obtener lista de productos verificados
    productos_verificados = session.get(f'verificados_{id}', [])
    
    if producto_encontrado:
        if barcode not in productos_verificados:
            productos_verificados.append(barcode)
            session[f'verificados_{id}'] = productos_verificados
            flash(f'Producto "{barcode}" verificado correctamente', 'success')
        else:
            flash(f'El producto "{barcode}" ya ha sido verificado', 'info')
    else:
        flash(f'Error: El producto "{barcode}" no pertenece a esta transferencia', 'error')
    
    return redirect(url_for('procesar_recepcion', id=id))

@app.route('/validar/<int:id>', methods=['POST'])
def validar_transferencia(id):
    """Validar una transferencia después de verificar todos los productos"""
    # Obtener la transferencia
    transferencia, productos = get_transfer_details(id)
    
    if not transferencia:
        flash('No se encontró la transferencia solicitada', 'error')
        return redirect(url_for('recepcion'))
    
    # Verificar que todos los productos han sido escaneados
    productos_verificados = session.get(f'verificados_{id}', [])
    all_verified = len(productos_verificados) == len(productos)
    
    if not all_verified:
        flash('No se pueden validar la transferencia. Algunos productos no han sido verificados', 'error')
        return redirect(url_for('procesar_recepcion', id=id))
    
    # Validar la transferencia
    success, message = validate_transfer(id)
    
    if success:
        # Limpiar la sesión
        if f'verificados_{id}' in session:
            del session[f'verificados_{id}']
        
        flash(message, 'success')
        return redirect(url_for('recepcion'))
    else:
        flash(message, 'error')
        return redirect(url_for('procesar_recepcion', id=id))

@app.route('/menu')
def menu():
    """Página de menú principal"""
    return render_template('menu.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5010)